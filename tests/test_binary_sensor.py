"""Tests for the router, service and middleware problem aggregate binary sensors.

The coordinator is a MagicMock whose ``data`` is a real TraefikSnapshot built
through the model parsers (``make_snapshot`` / ``snapshot_from_fixture``).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.traefik_proxy import binary_sensor
from custom_components.traefik_proxy.binary_sensor import PROBLEM_SENSORS, TraefikProblemBinarySensor
from custom_components.traefik_proxy.const import DOMAIN
from custom_components.traefik_proxy.models import TraefikSnapshot
from tests.conftest import FIXTURE_VERSIONS, make_snapshot, snapshot_from_fixture


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
# Problem aggregates: one class plus three descriptions
# ---------------------------------------------------------------------------

PROBLEM_KEYS = ("routers_problem", "services_problem", "middlewares_problem")
PROBLEM_UNIQUE_IDS = {
    "routers_problem": "test-entry_diagnostics_any_router_failing",
    "services_problem": "test-entry_diagnostics_any_service_failing",
    "middlewares_problem": "test-entry_diagnostics_any_middleware_failing",
}


def _problem(key: str, snapshot: TraefikSnapshot) -> Any:
    description = next(d for d in PROBLEM_SENSORS if d.key == key)
    return TraefikProblemBinarySensor(_entry_with_snapshot(snapshot), description)


def test_problem_descriptions_enabled_by_default_without_category() -> None:
    """Three PROBLEM descriptions, translation_key = key, enabled by default, no entity category."""
    descriptions = binary_sensor.PROBLEM_SENSORS
    assert tuple(d.key for d in descriptions) == PROBLEM_KEYS
    for description in descriptions:
        assert description.translation_key == description.key
        assert description.device_class is BinarySensorDeviceClass.PROBLEM
        assert description.entity_registry_enabled_default is True
        assert description.entity_category is None
    assert binary_sensor.PARALLEL_UPDATES == 0


@pytest.mark.parametrize("key", PROBLEM_KEYS)
def test_problem_sensor_keeps_unique_id_on_main_device(key: str) -> None:
    """The kept unique_id, the main device, no explicit entity_id."""
    entity = _problem(key, make_snapshot())
    assert entity.unique_id == PROBLEM_UNIQUE_IDS[key]
    assert entity.device_info == {"identifiers": {(DOMAIN, "test-entry")}}
    assert entity.entity_id is None
    assert entity.translation_key == key


def test_routers_problem_lists_sorted_problem_names() -> None:
    """On when any router is not enabled; problems are sorted, internal routers excluded."""
    snapshot = make_snapshot(
        routers=[
            _router("ok@file", "enabled"),
            _router("warn@file", "warning"),
            _router("broken@file", "disabled", error=["boom"]),
            _router("api@internal", "disabled"),
        ]
    )
    entity = _problem("routers_problem", snapshot)
    assert entity.is_on is True
    assert entity.extra_state_attributes == {"problems": ["broken@file", "warn@file"], "problem_count": 2}


def test_services_problem_on_for_status_and_down_server() -> None:
    """A non-enabled service and an enabled service with one DOWN server are problems; 1/1 is not."""
    snapshot = make_snapshot(
        services=[
            {"name": "broken@file", "status": "error"},
            {
                "name": "lb-mixed@file",
                "status": "enabled",
                "serverStatus": {"http://192.0.2.10:80": "DOWN", "http://backend.example.com:80": "UP"},
            },
            {"name": "healthy@file", "status": "enabled", "serverStatus": {"http://192.0.2.11:80": "UP"}},
        ]
    )
    entity = _problem("services_problem", snapshot)
    assert entity.is_on is True
    assert entity.extra_state_attributes == {"problems": ["broken@file", "lb-mixed@file"], "problem_count": 2}


def test_middlewares_problem_counts_warning_and_disabled() -> None:
    """Warning and disabled middlewares are problems."""
    snapshot = make_snapshot(
        middlewares=[
            {"name": "auth@file", "status": "enabled"},
            {"name": "rate-limit@file", "status": "warning"},
            {"name": "off-mw@file", "status": "disabled"},
        ]
    )
    entity = _problem("middlewares_problem", snapshot)
    assert entity.is_on is True
    assert entity.extra_state_attributes == {"problems": ["off-mw@file", "rate-limit@file"], "problem_count": 2}


def test_problem_names_capped_at_fifty() -> None:
    """51 problem routers: the first 50 sorted names, problem_count 51."""
    snapshot = make_snapshot(routers=[_router(f"r{i:02d}@file", "disabled") for i in range(51)])
    attrs = _problem("routers_problem", snapshot).extra_state_attributes
    assert attrs["problem_count"] == 51
    assert attrs["problems"] == [f"r{i:02d}@file" for i in range(50)]


def test_empty_traefik_turns_every_problem_sensor_off() -> None:
    """No items: every problem sensor is off with problems [] and problem_count 0."""
    for key in PROBLEM_KEYS:
        entity = _problem(key, make_snapshot())
        assert entity.is_on is False, key
        assert entity.extra_state_attributes == {"problems": [], "problem_count": 0}, key


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_problem_sensors_from_capture(version: str) -> None:
    """The captured scenario turns all three problem sensors on with the known problems."""
    snapshot = snapshot_from_fixture(version)
    expected = {
        "routers_problem": ["broken-missing-service@file", "chain-router@file", "warn-unknown-entrypoint@file"],
        "services_problem": ["lb-mixed@file"],
        "middlewares_problem": ["broken-chain@file"],
    }
    for key, names in expected.items():
        entity = _problem(key, snapshot)
        assert entity.is_on is True, key
        assert entity.extra_state_attributes == {"problems": names, "problem_count": len(names)}, key
