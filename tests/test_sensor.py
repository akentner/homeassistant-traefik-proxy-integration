"""Unit tests for the sensor platform entities.

Covers TraefikProxyEntrypointSensor, TraefikProxyServiceSensor, and the three
TraefikProxyXxxCountSensor aggregate counters. The coordinator is a MagicMock
whose ``data`` is a real TraefikSnapshot built through the model parsers
(``make_snapshot`` / ``snapshot_from_fixture``), so the assertions run on the
same shapes the integration publishes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.util import slugify

from custom_components.traefik_proxy.const import DOMAIN, ITEM_STATE_OPTIONS, STATE_MISSING
from custom_components.traefik_proxy.models import TraefikSnapshot
from custom_components.traefik_proxy.sensor import (
    TraefikProxyEntrypointSensor,
    TraefikProxyMiddlewaresCountSensor,
    TraefikProxyRoutersCountSensor,
    TraefikProxyServicesCountSensor,
    TraefikProxyServiceSensor,
)
from tests.conftest import FIXTURE_VERSIONS, make_snapshot, snapshot_from_fixture


def _entry_with_snapshot(snapshot: TraefikSnapshot) -> tuple[MagicMock, MagicMock]:
    """Build a (entry, coordinator) pair whose coordinator publishes ``snapshot``.

    The entry's ``runtime_data.coordinator`` slot holds the coordinator so
    ``TraefikProxyEntity.__init__`` resolves ``self.coordinator`` to it.
    """
    entry = MagicMock()
    entry.entry_id = "test-entry"
    entry.data = {"url": "https://traefik.example.com:8080"}
    coord = MagicMock()
    coord.data = snapshot
    coord.last_update_success = True
    entry.runtime_data = MagicMock(coordinator=coord)
    entry.runtime_data.entity_manager.missing_since.return_value = None
    return entry, coord


def _routers(*statuses: str) -> list[dict[str, Any]]:
    """Raw router items named ``r<i>@file`` with the given statuses."""
    return [{"name": f"r{i}@file", "status": status} for i, status in enumerate(statuses)]


# ---------------------------------------------------------------------------
# Entrypoint sensors
# ---------------------------------------------------------------------------


def test_entrypoint_sensor_state_from_address() -> None:
    """TraefikProxyEntrypointSensor.native_value is the entrypoint address."""
    snapshot = make_snapshot(entrypoints=[{"name": "websecure", "address": ":443"}])
    entry, coord = _entry_with_snapshot(snapshot)
    entity = TraefikProxyEntrypointSensor(entry, coord, snapshot.entrypoints["websecure"])
    assert entity.native_value == ":443"


def test_entrypoint_sensor_entity_id_and_unique_id() -> None:
    """Entrypoint entity_id follows the traefik_http_entrypoint_<slug> convention."""
    snapshot = make_snapshot(entrypoints=[{"name": "websecure", "address": ":443"}])
    entry, coord = _entry_with_snapshot(snapshot)
    entity = TraefikProxyEntrypointSensor(entry, coord, snapshot.entrypoints["websecure"])
    assert entity.entity_id == f"sensor.traefik_http_entrypoint_{slugify('websecure')}"
    assert entity.unique_id == "test-entry_http_entrypoint_websecure"


def test_entrypoint_sensor_attributes_include_name_address_transport() -> None:
    """Attributes expose name, address, the transport protocol and the name alias."""
    snapshot = make_snapshot(
        entrypoints=[{"name": "websecure", "address": ":443"}, {"name": "udp-ep", "address": ":9999/udp"}]
    )
    entry, coord = _entry_with_snapshot(snapshot)
    tcp = TraefikProxyEntrypointSensor(entry, coord, snapshot.entrypoints["websecure"])
    udp = TraefikProxyEntrypointSensor(entry, coord, snapshot.entrypoints["udp-ep"])
    assert tcp.extra_state_attributes == {
        "name": "websecure",
        "address": ":443",
        "transport": "tcp",
        "entrypoint_name": "websecure",
    }
    assert udp.extra_state_attributes["transport"] == "udp"


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_entrypoint_sensors_from_capture(version: str) -> None:
    """Every captured entrypoint yields its address and protocol."""
    snapshot = snapshot_from_fixture(version)
    entry, coord = _entry_with_snapshot(snapshot)
    states = {
        name: (
            TraefikProxyEntrypointSensor(entry, coord, ep).native_value,
            TraefikProxyEntrypointSensor(entry, coord, ep).extra_state_attributes["transport"],
        )
        for name, ep in snapshot.entrypoints.items()
    }
    assert states == {
        "traefik": (":8080", "tcp"),
        "udp-ep": (":9999/udp", "udp"),
        "web": (":80", "tcp"),
        "websecure": (":443", "tcp"),
    }


def test_entrypoint_sensor_reads_latest_snapshot() -> None:
    """The entity resolves its model from the current snapshot on every read."""
    snapshot = make_snapshot(entrypoints=[{"name": "web", "address": ":80"}])
    entry, coord = _entry_with_snapshot(snapshot)
    entity = TraefikProxyEntrypointSensor(entry, coord, snapshot.entrypoints["web"])

    coord.data = make_snapshot(entrypoints=[{"name": "web", "address": ":8081"}])
    assert entity.native_value == ":8081"


# ---------------------------------------------------------------------------
# Service sensors
# ---------------------------------------------------------------------------


def _lb_service(name: str, status: str, server_status: dict[str, str]) -> dict[str, Any]:
    """Raw list-form load-balancer service item."""
    return {
        "name": name,
        "provider": "file",
        "type": "loadbalancer",
        "status": status,
        "loadBalancer": {"servers": [{"url": url} for url in server_status]},
        "serverStatus": server_status,
    }


def test_service_sensor_state_is_service_status() -> None:
    """TraefikProxyServiceSensor.native_value is the parsed service status."""
    snapshot = make_snapshot(
        services=[
            _lb_service("ok@file", "enabled", {"http://192.0.2.1:80": "UP"}),
            {"name": "broken@file", "status": "disabled", "error": ["boom"]},
        ]
    )
    entry, coord = _entry_with_snapshot(snapshot)
    ok = TraefikProxyServiceSensor(entry, coord, snapshot.services["ok@file"])
    broken = TraefikProxyServiceSensor(entry, coord, snapshot.services["broken@file"])
    assert ok.native_value == "enabled"
    assert broken.native_value == "error"


def test_service_sensor_server_counts_from_server_status() -> None:
    """server_count counts every server, servers_up only the ones reported UP."""
    snapshot = make_snapshot(
        services=[
            _lb_service(
                "mixed@file",
                "enabled",
                {"http://192.0.2.10:80": "DOWN", "http://backend.example.com:80": "UP"},
            )
        ]
    )
    entry, coord = _entry_with_snapshot(snapshot)
    entity = TraefikProxyServiceSensor(entry, coord, snapshot.services["mixed@file"])
    assert entity.extra_state_attributes == {
        "name": "mixed@file",
        "status": "enabled",
        "type": "loadbalancer",
        "server_count": 2,
        "servers_up": 1,
        "service_name": "mixed@file",
    }


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_service_sensor_attributes_expose_no_backend_url(version: str) -> None:
    """No service attribute carries the server list or any backend URL."""
    snapshot = snapshot_from_fixture(version)
    entry, coord = _entry_with_snapshot(snapshot)
    for service in snapshot.services.values():
        attrs = TraefikProxyServiceSensor(entry, coord, service).extra_state_attributes
        assert "servers" not in attrs
        assert not any("://" in str(value) for value in attrs.values()), service.name
    mixed = TraefikProxyServiceSensor(entry, coord, snapshot.services["lb-mixed@file"]).extra_state_attributes
    assert (mixed["server_count"], mixed["servers_up"]) == (2, 1)


def test_service_sensor_entity_id_and_unique_id() -> None:
    """Service entity_id follows the traefik_http_service_<slug> convention."""
    snapshot = make_snapshot(services=[{"name": "whoami@docker", "status": "enabled"}])
    entry, coord = _entry_with_snapshot(snapshot)
    entity = TraefikProxyServiceSensor(entry, coord, snapshot.services["whoami@docker"])
    assert entity.entity_id == f"sensor.traefik_http_service_{slugify('whoami@docker')}"
    assert entity.unique_id == "test-entry_http_service_whoami@docker"


def test_service_sensor_reads_latest_snapshot() -> None:
    """The service state follows the current snapshot without re-instantiation."""
    snapshot = make_snapshot(services=[{"name": "svc@file", "status": "enabled"}])
    entry, coord = _entry_with_snapshot(snapshot)
    entity = TraefikProxyServiceSensor(entry, coord, snapshot.services["svc@file"])

    coord.data = make_snapshot(services=[{"name": "svc@file", "status": "warning"}])
    assert entity.native_value == "warning"


# ---------------------------------------------------------------------------
# Aggregate count sensors
# ---------------------------------------------------------------------------


def test_routers_count_sensor_excludes_internal_items() -> None:
    """Traefik-internal routers are not part of the snapshot, so they are not counted."""
    entry, _coord = _entry_with_snapshot(
        make_snapshot(routers=[{"name": "user-router@file"}, {"name": "api@internal"}])
    )
    assert TraefikProxyRoutersCountSensor(entry).native_value == 1


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_count_sensors_from_capture(version: str) -> None:
    """Counts and http_count of the real captures; tcp/udp counts are gone."""
    entry, _coord = _entry_with_snapshot(snapshot_from_fixture(version))
    routers = TraefikProxyRoutersCountSensor(entry)
    services = TraefikProxyServicesCountSensor(entry)
    middlewares = TraefikProxyMiddlewaresCountSensor(entry)

    assert routers.native_value == 128
    router_attrs = routers.extra_state_attributes
    assert router_attrs["filtered_count"] == 128
    assert router_attrs["http_count"] == 128
    assert router_attrs["status_breakdown"] == {"success": 125, "warning": 1, "error": 2, "disabled": 0}
    assert "tcp_count" not in router_attrs
    assert "udp_count" not in router_attrs

    assert services.native_value == 4
    assert services.extra_state_attributes["http_count"] == 4

    assert middlewares.native_value == 2
    middleware_attrs = middlewares.extra_state_attributes
    assert middleware_attrs["success_count"] == 1
    assert middleware_attrs["error_count"] == 1
    assert middleware_attrs["success_pct"] == 50.0
    assert "http_count" not in middleware_attrs


def test_aggregate_count_updates_on_coordinator_cycle() -> None:
    """Counts follow the current snapshot, not the one present at construction."""
    entry, coord = _entry_with_snapshot(make_snapshot())
    entity = TraefikProxyRoutersCountSensor(entry)
    assert entity.native_value == 0

    coord.data = make_snapshot(routers=_routers("enabled", "enabled"))
    assert entity.native_value == 2
    assert entity.extra_state_attributes["filtered_count"] == 2
    assert entity.extra_state_attributes["http_count"] == 2


def test_services_count_sensor_excludes_internal_items() -> None:
    """Services count excludes api@internal."""
    entry, _coord = _entry_with_snapshot(
        make_snapshot(services=[{"name": "backend-api@file"}, {"name": "backend-warn@file"}, {"name": "api@internal"}])
    )
    assert TraefikProxyServicesCountSensor(entry).native_value == 2


def test_middlewares_count_sensor_counts_user_items() -> None:
    """Provider-suffixed user middlewares count; ``@internal`` ones do not."""
    entry, _coord = _entry_with_snapshot(
        make_snapshot(
            middlewares=[
                {"name": "auth-headers@file", "status": "enabled"},
                {"name": "rate-limit@file", "status": "enabled"},
                {"name": "strip@docker", "status": "enabled"},
                {"name": "dashboard_stripprefix@internal", "status": "enabled"},
            ]
        )
    )
    entity = TraefikProxyMiddlewaresCountSensor(entry)
    attrs = entity.extra_state_attributes
    assert entity.native_value == 3
    assert attrs["filtered_count"] == 3
    assert attrs["success_count"] == 3
    assert attrs["warning_count"] == 0
    assert attrs["error_count"] == 0
    assert attrs["disabled_count"] == 0
    assert attrs["success_pct"] == 100.0


def test_middlewares_have_no_transport_counts() -> None:
    """Middlewares expose neither http_count nor tcp/udp counts."""
    entry, _coord = _entry_with_snapshot(make_snapshot(middlewares=[{"name": "x@file", "status": "enabled"}]))
    attrs = TraefikProxyMiddlewaresCountSensor(entry).extra_state_attributes
    assert attrs["filtered_count"] == 1
    assert attrs["success_count"] == 1
    assert "http_count" not in attrs
    assert "tcp_count" not in attrs
    assert "udp_count" not in attrs


def test_aggregate_routers_breakdown_attributes() -> None:
    """sensor.traefik_routers exposes success/warning/error/disabled counts."""
    entry, _coord = _entry_with_snapshot(
        make_snapshot(
            routers=[
                {"name": "ha-nextgen@file", "status": "enabled"},
                {"name": "ha@file", "status": "enabled"},
                {"name": "httpsredirect@file", "status": "enabled"},
                {"name": "n8n@file", "status": "enabled"},
                {"name": "opencode@file", "status": "enabled"},
                {"name": "traccar@file", "status": "enabled"},
                {"name": "api@internal", "status": "enabled"},
                {"name": "dashboard@internal", "status": "enabled"},
                {"name": "web-to-websecure@internal", "status": "enabled"},
            ]
        )
    )
    attrs = TraefikProxyRoutersCountSensor(entry).extra_state_attributes
    assert attrs["filtered_count"] == 6
    assert attrs["success_count"] == 6
    assert attrs["warning_count"] == 0
    assert attrs["error_count"] == 0
    assert attrs["disabled_count"] == 0
    assert attrs["success_pct"] == 100.0
    assert attrs["status_breakdown"] == {"success": 6, "warning": 0, "error": 0, "disabled": 0}


def test_aggregate_breakdown_reflects_mixed_status() -> None:
    """Each status lands in its own bucket; disabled with errors counts as error."""
    entry, _coord = _entry_with_snapshot(
        make_snapshot(
            routers=[
                *_routers("enabled", "enabled", "warning", "disabled"),
                {"name": "err@file", "status": "disabled", "error": ["the service does not exist"]},
            ]
        )
    )
    attrs = TraefikProxyRoutersCountSensor(entry).extra_state_attributes
    assert attrs["filtered_count"] == 5
    assert attrs["success_count"] == 2
    assert attrs["warning_count"] == 1
    assert attrs["error_count"] == 1
    assert attrs["disabled_count"] == 1
    # success_pct = success / (success + warning + error) = 2 / 4 = 50.0
    assert attrs["success_pct"] == 50.0


def test_aggregate_success_pct_excludes_disabled() -> None:
    """success_pct denominator excludes disabled items."""
    entry, _coord = _entry_with_snapshot(make_snapshot(routers=_routers("enabled", "disabled", "disabled")))
    assert TraefikProxyRoutersCountSensor(entry).extra_state_attributes["success_pct"] == 100.0


def test_aggregate_success_pct_when_everything_disabled() -> None:
    """Only disabled items: success_pct is 100.0 (no item to judge)."""
    entry, _coord = _entry_with_snapshot(make_snapshot(routers=_routers("disabled", "disabled")))
    attrs = TraefikProxyRoutersCountSensor(entry).extra_state_attributes
    assert attrs["filtered_count"] == 2
    assert attrs["success_count"] == 0
    assert attrs["success_pct"] == 100.0


def test_aggregate_breakdown_refreshes_on_coordinator_cycle() -> None:
    """Breakdown attributes follow every new snapshot."""
    entry, coord = _entry_with_snapshot(make_snapshot(routers=_routers("enabled")))
    entity = TraefikProxyRoutersCountSensor(entry)
    assert entity.extra_state_attributes["success_count"] == 1
    assert entity.extra_state_attributes["warning_count"] == 0

    coord.data = make_snapshot(routers=_routers("enabled", "warning"))
    assert entity.extra_state_attributes["success_count"] == 1
    assert entity.extra_state_attributes["warning_count"] == 1
    assert entity.extra_state_attributes["success_pct"] == 50.0


def test_empty_traefik_reads_zero_everywhere() -> None:
    """A Traefik without routers, services or middlewares: every count is 0, success_pct 100."""
    entry, _coord = _entry_with_snapshot(make_snapshot())
    for sensor_cls in (
        TraefikProxyRoutersCountSensor,
        TraefikProxyServicesCountSensor,
        TraefikProxyMiddlewaresCountSensor,
    ):
        entity = sensor_cls(entry)
        attrs = entity.extra_state_attributes
        assert entity.native_value == 0
        assert attrs["filtered_count"] == 0
        assert attrs["status_breakdown"] == {"success": 0, "warning": 0, "error": 0, "disabled": 0}
        assert attrs["success_pct"] == 100.0


# ---------------------------------------------------------------------------
# Service and entrypoint sensors managed by the entity manager
# ---------------------------------------------------------------------------

SERVICE_ATTRIBUTES = {"type", "provider", "servers_up", "servers_total", "used_by", "errors"}
MISSING_SINCE = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)


@pytest.mark.xfail(strict=True, reason="RED: TraefikServiceSensor not implemented yet")
def test_service_sensor_shape() -> None:
    """ENUM sensor on the Services sub-device, translation_key service, unique_id kept, no explicit entity_id."""
    from custom_components.traefik_proxy.sensor import TraefikServiceSensor

    entry, _coord = _entry_with_snapshot(make_snapshot(services=[{"name": "whoami@docker", "status": "enabled"}]))
    entity = TraefikServiceSensor(entry, "whoami@docker")
    assert entity.unique_id == "test-entry_http_service_whoami@docker"
    assert entity.device_class is SensorDeviceClass.ENUM
    assert entity.options == list(ITEM_STATE_OPTIONS)
    assert entity.translation_key == "service"
    assert entity.device_info == {"identifiers": {(DOMAIN, "test-entry_services")}}
    assert entity.entity_id is None
    assert entity.name == "whoami@docker"


@pytest.mark.xfail(strict=True, reason="RED: TraefikServiceSensor not implemented yet")
def test_service_sensor_state_and_attributes() -> None:
    """State is the Traefik status; attributes are exactly the canonical service keys."""
    from custom_components.traefik_proxy.sensor import TraefikServiceSensor

    snapshot = make_snapshot(
        services=[
            {**_lb_service("mixed@file", "enabled", {"http://192.0.2.10:80": "DOWN", "http://b.example.com:80": "UP"})},
            {"name": "broken@file", "status": "disabled", "error": ["boom"], "usedBy": ["r@file"]},
        ]
    )
    entry, _coord = _entry_with_snapshot(snapshot)
    mixed = TraefikServiceSensor(entry, "mixed@file")
    broken = TraefikServiceSensor(entry, "broken@file")
    assert mixed.native_value == "enabled"
    assert mixed.extra_state_attributes == {
        "type": "loadbalancer",
        "provider": "file",
        "servers_up": 1,
        "servers_total": 2,
        "used_by": [],
        "errors": [],
    }
    assert "mixed@file" in snapshot.service_problems
    assert broken.native_value == "error"
    assert broken.extra_state_attributes["errors"] == ["boom"]
    assert broken.extra_state_attributes["used_by"] == ["r@file"]


@pytest.mark.xfail(strict=True, reason="RED: TraefikServiceSensor not implemented yet")
def test_service_without_server_status_reads_zero_of_zero() -> None:
    """No serverStatus: 0/0 servers, empty lists, and no service problem (all servers up, adjacency)."""
    from custom_components.traefik_proxy.sensor import TraefikServiceSensor

    snapshot = make_snapshot(
        services=[
            {"name": "bare@file", "status": "enabled"},
            _lb_service("full@file", "enabled", {"http://192.0.2.1:80": "UP"}),
        ]
    )
    entry, _coord = _entry_with_snapshot(snapshot)
    attrs = TraefikServiceSensor(entry, "bare@file").extra_state_attributes
    assert (attrs["servers_up"], attrs["servers_total"]) == (0, 0)
    assert (attrs["used_by"], attrs["errors"]) == ([], [])
    assert snapshot.service_problems == ()


@pytest.mark.xfail(strict=True, reason="RED: TraefikServiceSensor not implemented yet")
@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_service_sensor_attributes_are_private(version: str) -> None:
    """On both captures no service attribute carries a backend URL or address."""
    from custom_components.traefik_proxy.sensor import TraefikServiceSensor

    snapshot = snapshot_from_fixture(version)
    entry, _coord = _entry_with_snapshot(snapshot)
    assert snapshot.services
    for name in snapshot.services:
        attrs = TraefikServiceSensor(entry, name).extra_state_attributes
        assert set(attrs) == SERVICE_ATTRIBUTES, name
        for value in attrs.values():
            assert "://" not in str(value), name
            assert "192.0.2." not in str(value), name
    mixed = TraefikServiceSensor(entry, "lb-mixed@file").extra_state_attributes
    assert (mixed["servers_up"], mixed["servers_total"]) == (1, 2)


@pytest.mark.xfail(strict=True, reason="RED: TraefikServiceSensor not implemented yet")
def test_service_sensor_missing_and_latest_snapshot() -> None:
    """A service absent from the snapshot reads missing with missing_since; a present one follows the snapshot."""
    from custom_components.traefik_proxy.sensor import TraefikServiceSensor

    entry, coord = _entry_with_snapshot(make_snapshot(services=[{"name": "svc@file", "status": "enabled"}]))
    entity = TraefikServiceSensor(entry, "svc@file")
    coord.data = make_snapshot(services=[{"name": "svc@file", "status": "warning"}])
    assert entity.native_value == "warning"

    coord.data = make_snapshot()
    entry.runtime_data.entity_manager.missing_since.return_value = MISSING_SINCE
    assert entity.native_value == STATE_MISSING
    assert entity.extra_state_attributes == {"missing_since": MISSING_SINCE.isoformat()}


@pytest.mark.xfail(strict=True, reason="RED: TraefikEntrypointSensor not implemented yet")
def test_entrypoint_sensor_shape() -> None:
    """Diagnostic, disabled by default, on the main device, unique_id kept, no explicit entity_id."""
    from custom_components.traefik_proxy.sensor import TraefikEntrypointSensor

    entry, _coord = _entry_with_snapshot(make_snapshot(entrypoints=[{"name": "websecure", "address": ":443"}]))
    entity = TraefikEntrypointSensor(entry, "websecure")
    assert entity.unique_id == "test-entry_http_entrypoint_websecure"
    assert entity.translation_key == "entrypoint"
    assert entity.entity_category is EntityCategory.DIAGNOSTIC
    assert entity.entity_registry_enabled_default is False
    assert entity.device_info == {"identifiers": {(DOMAIN, "test-entry")}}
    assert entity.entity_id is None


@pytest.mark.xfail(strict=True, reason="RED: TraefikEntrypointSensor not implemented yet")
@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_entrypoint_sensor_from_capture(version: str) -> None:
    """Every captured entrypoint reads its address with the single attribute protocol."""
    from custom_components.traefik_proxy.sensor import TraefikEntrypointSensor

    snapshot = snapshot_from_fixture(version)
    entry, _coord = _entry_with_snapshot(snapshot)
    states = {
        name: (
            TraefikEntrypointSensor(entry, name).native_value,
            TraefikEntrypointSensor(entry, name).extra_state_attributes,
        )
        for name in snapshot.entrypoints
    }
    assert states == {
        "traefik": (":8080", {"protocol": "tcp"}),
        "udp-ep": (":9999/udp", {"protocol": "udp"}),
        "web": (":80", {"protocol": "tcp"}),
        "websecure": (":443", {"protocol": "tcp"}),
    }


@pytest.mark.xfail(strict=True, reason="RED: TraefikEntrypointSensor not implemented yet")
def test_entrypoint_sensor_missing_and_latest_snapshot() -> None:
    """An entrypoint follows the snapshot and reads missing with missing_since once it is gone."""
    from custom_components.traefik_proxy.sensor import TraefikEntrypointSensor

    entry, coord = _entry_with_snapshot(make_snapshot(entrypoints=[{"name": "web", "address": ":80"}]))
    entity = TraefikEntrypointSensor(entry, "web")
    coord.data = make_snapshot(entrypoints=[{"name": "web", "address": ":8081"}])
    assert entity.native_value == ":8081"

    coord.data = make_snapshot()
    entry.runtime_data.entity_manager.missing_since.return_value = MISSING_SINCE
    assert entity.native_value == STATE_MISSING
    assert entity.extra_state_attributes == {"missing_since": MISSING_SINCE.isoformat()}
