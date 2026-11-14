"""Tests for the any-*-failing aggregate binary sensors.

The coordinator is a MagicMock whose ``data`` is a real TraefikSnapshot built
through the model parsers (``make_snapshot`` / ``snapshot_from_fixture``).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.traefik_proxy.binary_sensor import (
    TraefikProxyAnyMiddlewareFailingBinarySensor,
    TraefikProxyAnyRouterFailingBinarySensor,
    TraefikProxyAnyServiceFailingBinarySensor,
)
from custom_components.traefik_proxy.models import TraefikSnapshot
from tests.conftest import FIXTURE_VERSIONS, make_snapshot, snapshot_from_fixture

_AGGREGATES = (
    TraefikProxyAnyRouterFailingBinarySensor,
    TraefikProxyAnyServiceFailingBinarySensor,
    TraefikProxyAnyMiddlewareFailingBinarySensor,
)


def _router(name: str, status: str, **extra: Any) -> dict[str, Any]:
    return {
        "name": name,
        "rule": f"Host(`{name}.example.com`)",
        "service": f"backend-{name}",
        "status": status,
        **extra,
    }


def _entry_with_snapshot(snapshot: TraefikSnapshot) -> MagicMock:
    """Build a MagicMock entry whose ``runtime_data.coordinator`` publishes ``snapshot``."""
    coord = MagicMock()
    coord.data = snapshot
    coord.last_update_success = True
    entry = MagicMock()
    entry.entry_id = "test-entry"
    entry.data = {"url": "https://traefik.example.com:8080"}
    entry.runtime_data = MagicMock(coordinator=coord)
    return entry


# ---------------------------------------------------------------------------
# Any-*-failing aggregates
# ---------------------------------------------------------------------------


def _aggregate(cls: type, snapshot: TraefikSnapshot) -> Any:
    entry = _entry_with_snapshot(snapshot)
    return cls(entry, entry.runtime_data.coordinator)


def test_any_router_failing_lists_problem_routers() -> None:
    """ON when any router is not enabled; names come sorted from the snapshot."""
    snapshot = make_snapshot(
        routers=[
            _router("ok@file", "enabled"),
            _router("warn@file", "warning"),
            _router("broken@file", "disabled", error=["boom"]),
            _router("api@internal", "disabled"),
        ]
    )
    entity = _aggregate(TraefikProxyAnyRouterFailingBinarySensor, snapshot)
    assert entity.is_on is True
    assert entity.extra_state_attributes == {
        "failing_router_count": 2,
        "failing_router_names": ["broken@file", "warn@file"],
    }


def test_any_service_failing_aggregates_status() -> None:
    """ON when any service is not enabled."""
    snapshot = make_snapshot(
        services=[{"name": "ok@file", "status": "enabled"}, {"name": "broken@file", "status": "error"}]
    )
    entity = _aggregate(TraefikProxyAnyServiceFailingBinarySensor, snapshot)
    assert entity.is_on is True
    attrs = entity.extra_state_attributes
    assert attrs["failing_service_count"] == 1
    assert attrs["failing_service_names"] == ["broken@file"]


def test_enabled_service_with_down_server_is_a_problem() -> None:
    """An enabled service with one server DOWN counts as failing."""
    snapshot = make_snapshot(
        services=[
            {
                "name": "lb-mixed@file",
                "status": "enabled",
                "serverStatus": {"http://192.0.2.10:80": "DOWN", "http://backend.example.com:80": "UP"},
            },
            {"name": "healthy@file", "status": "enabled", "serverStatus": {"http://192.0.2.11:80": "UP"}},
        ]
    )
    entity = _aggregate(TraefikProxyAnyServiceFailingBinarySensor, snapshot)
    assert entity.is_on is True
    assert entity.extra_state_attributes["failing_service_names"] == ["lb-mixed@file"]


def test_any_service_failing_off_when_all_enabled() -> None:
    """All-enabled services: is_on False, count 0, names []."""
    snapshot = make_snapshot(
        services=[{"name": "ok-1@file", "status": "enabled"}, {"name": "ok-2@file", "status": "enabled"}]
    )
    entity = _aggregate(TraefikProxyAnyServiceFailingBinarySensor, snapshot)
    assert entity.is_on is False
    assert entity.extra_state_attributes == {"failing_service_count": 0, "failing_service_names": []}


def test_any_middleware_failing_aggregates_status() -> None:
    """Warning and disabled middlewares both count as failing."""
    snapshot = make_snapshot(
        middlewares=[
            {"name": "auth@file", "status": "enabled"},
            {"name": "rate-limit@file", "status": "warning"},
            {"name": "strip@docker", "status": "enabled"},
            {"name": "off-mw@file", "status": "disabled"},
        ]
    )
    entity = _aggregate(TraefikProxyAnyMiddlewareFailingBinarySensor, snapshot)
    assert entity.is_on is True
    attrs = entity.extra_state_attributes
    assert attrs["failing_middleware_count"] == 2
    assert attrs["failing_middleware_names"] == ["off-mw@file", "rate-limit@file"]


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_aggregates_from_capture(version: str) -> None:
    """The captured scenario turns all three aggregates on with the known problems."""
    snapshot = snapshot_from_fixture(version)
    routers, services, middlewares = (_aggregate(cls, snapshot) for cls in _AGGREGATES)
    assert routers.extra_state_attributes["failing_router_names"] == [
        "broken-missing-service@file",
        "chain-router@file",
        "warn-unknown-entrypoint@file",
    ]
    assert services.extra_state_attributes["failing_service_names"] == ["lb-mixed@file"]
    assert middlewares.extra_state_attributes["failing_middleware_names"] == ["broken-chain@file"]
    assert routers.is_on and services.is_on and middlewares.is_on


def test_empty_traefik_turns_every_aggregate_off() -> None:
    """No routers, services or middlewares: all three aggregates are off with zero counts."""
    snapshot = make_snapshot()
    for cls in _AGGREGATES:
        entity = _aggregate(cls, snapshot)
        assert entity.is_on is False
        attrs = entity.extra_state_attributes
        assert attrs[next(k for k in attrs if k.endswith("_count"))] == 0
        assert attrs[next(k for k in attrs if k.endswith("_names"))] == []


def test_any_failing_disabled_by_default() -> None:
    """The PROBLEM aggregates are registered disabled by default.

    HA's ``CachedProperties`` metaclass moves class-level ``_attr_*`` attrs
    to ``__attr_*`` names, so the raw value is read from ``cls.__dict__``.
    """
    for cls in _AGGREGATES:
        assert cls.__dict__.get("__attr_entity_registry_enabled_default") is False
