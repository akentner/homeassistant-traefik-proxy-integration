"""Entity states on both real capture generations (v2.11 and v3.7).

A full setup is served from the committed captures through ``stub_traefik``.
Expected values come from the snapshot built from the same capture, so the
test proves the path capture -> client -> coordinator -> entities, not the
parser itself.
"""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EntityCategory
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.traefik_proxy.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL, DOMAIN, ITEM_STATE_OPTIONS
from custom_components.traefik_proxy.entity_manager import ENTRYPOINTS, ROUTERS, SERVICES
from custom_components.traefik_proxy.models import Status, TraefikSnapshot
from tests.conftest import (
    FIXTURE_VERSIONS,
    MOCK_URL,
    entity_id_for,
    make_traefik_entry,
    snapshot_from_fixture,
    stub_traefik,
)


@pytest.fixture(params=FIXTURE_VERSIONS)
async def loaded(request, hass, aioclient_mock, mock_tls_probe) -> TraefikSnapshot:  # type: ignore[no-untyped-def]
    """Set up an entry served by the capture of one generation; return the expected snapshot."""
    version = request.param
    stub_traefik(aioclient_mock, version=version)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Traefik",
        data={CONF_URL: MOCK_URL, CONF_API_KEY: "k", CONF_VERIFY_SSL: True},
        unique_id="traefik.example.com",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    expected = snapshot_from_fixture(version)
    assert entry.runtime_data.coordinator.data == expected
    return expected


async def test_router_sensors(hass, loaded: TraefikSnapshot) -> None:
    """Exactly one ENUM sensor per non-internal router, its state is the router status; no router binary_sensor."""
    assert loaded.routers
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    for name, router in loaded.routers.items():
        state = hass.states.get(entity_id_for(hass, "sensor", ROUTERS.unique_id(entry.entry_id, name)))
        assert state is not None, name
        assert state.state == str(router.status), name
    assert not any(name.endswith("@internal") for name in loaded.routers)
    broken = hass.states.get(
        entity_id_for(hass, "sensor", ROUTERS.unique_id(entry.entry_id, "broken-missing-service@file"))
    )
    assert broken is not None and broken.state == "error"

    reg_entries = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    router_keys = [
        (reg_entry.domain, key)
        for reg_entry in reg_entries
        if (key := ROUTERS.key_of(entry.entry_id, reg_entry.unique_id)) is not None
    ]
    assert sorted(key for domain, key in router_keys if domain == "sensor") == sorted(loaded.routers)
    assert not [key for domain, key in router_keys if domain == "binary_sensor"]


SERVICE_ATTRIBUTES = {"type", "provider", "servers_up", "servers_total", "used_by", "errors"}
HA_ATTRIBUTES = {"options", "device_class", "friendly_name"}


def _device_id(hass, entry_id: str, identifier: str) -> str:  # type: ignore[no-untyped-def]
    """Return the id of the entry's device with Traefik identifier ``identifier``."""
    matches = [
        device.id
        for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry_id)
        if (DOMAIN, identifier) in device.identifiers
    ]
    assert len(matches) == 1, identifier
    return matches[0]


async def test_service_enum_sensors(hass, loaded: TraefikSnapshot) -> None:
    """Each service is an ENUM sensor on the Services sub-device with the canonical, private attributes."""
    assert loaded.services
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    registry = er.async_get(hass)
    services_device = _device_id(hass, entry.entry_id, f"{entry.entry_id}_services")
    for name, service in loaded.services.items():
        entity_id = entity_id_for(hass, "sensor", SERVICES.unique_id(entry.entry_id, name))
        state = hass.states.get(entity_id)
        assert state is not None, name
        assert state.state == str(service.status), name
        assert state.attributes["options"] == list(ITEM_STATE_OPTIONS)
        assert set(state.attributes) - HA_ATTRIBUTES == SERVICE_ATTRIBUTES, name
        assert (state.attributes["servers_up"], state.attributes["servers_total"]) == (
            service.servers_up,
            service.servers_total,
        )
        for key in SERVICE_ATTRIBUTES:
            assert "://" not in str(state.attributes[key]), name
            assert "192.0.2." not in str(state.attributes[key]), name
        reg_entry = registry.async_get(entity_id)
        assert reg_entry is not None and reg_entry.device_id == services_device, name
    mixed = hass.states.get(entity_id_for(hass, "sensor", SERVICES.unique_id(entry.entry_id, "lb-mixed@file")))
    assert mixed is not None
    assert (mixed.attributes["servers_total"], mixed.attributes["servers_up"]) == (2, 1)


async def test_entrypoint_sensors_diagnostic_and_disabled(hass, loaded: TraefikSnapshot) -> None:
    """Every entrypoint sensor is registered disabled by the integration, diagnostic, on the main device."""
    assert loaded.entrypoints
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    registry = er.async_get(hass)
    main_device = _device_id(hass, entry.entry_id, entry.entry_id)
    for name in loaded.entrypoints:
        reg_entry = registry.async_get(entity_id_for(hass, "sensor", ENTRYPOINTS.unique_id(entry.entry_id, name)))
        assert reg_entry is not None, name
        assert reg_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION, name
        assert reg_entry.entity_category is EntityCategory.DIAGNOSTIC, name
        assert reg_entry.device_id == main_device, name
        assert hass.states.get(reg_entry.entity_id) is None, name


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
async def test_enabled_entrypoint_sensors(hass, aioclient_mock, mock_tls_probe, version: str) -> None:  # type: ignore[no-untyped-def]
    """Entrypoint sensors enabled before setup show the address and the protocol."""
    expected = snapshot_from_fixture(version)
    entry = make_traefik_entry()
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    for name in expected.entrypoints:
        registry.async_get_or_create("sensor", DOMAIN, ENTRYPOINTS.unique_id(entry.entry_id, name), config_entry=entry)
    stub_traefik(aioclient_mock, version=version)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    for name, entrypoint in expected.entrypoints.items():
        state = hass.states.get(entity_id_for(hass, "sensor", ENTRYPOINTS.unique_id(entry.entry_id, name)))
        assert state is not None, name
        assert state.state == entrypoint.address, name
        assert state.attributes["protocol"] == entrypoint.protocol, name
        assert "transport" not in state.attributes
    udp = hass.states.get(entity_id_for(hass, "sensor", ENTRYPOINTS.unique_id(entry.entry_id, "udp-ep")))
    assert udp is not None and udp.attributes["protocol"] == "udp"


PROBLEM_UNIQUE_ID_SUFFIXES = {
    "diagnostics_any_router_failing": "router_problems",
    "diagnostics_any_service_failing": "service_problems",
    "diagnostics_any_middleware_failing": "middleware_problems",
}


async def test_problem_aggregates_enabled_and_on(hass, loaded: TraefikSnapshot) -> None:
    """The three problem aggregates are enabled, uncategorised, on the main device and on for both captures."""
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    registry = er.async_get(hass)
    main_device = _device_id(hass, entry.entry_id, entry.entry_id)
    for suffix, field in PROBLEM_UNIQUE_ID_SUFFIXES.items():
        entity_id = entity_id_for(hass, "binary_sensor", f"{entry.entry_id}_{suffix}")
        reg_entry = registry.async_get(entity_id)
        assert reg_entry is not None, suffix
        assert reg_entry.disabled_by is None, suffix
        assert reg_entry.entity_category is None, suffix
        assert reg_entry.device_id == main_device, suffix
        problems = getattr(loaded, field)
        state = hass.states.get(entity_id)
        assert state is not None, suffix
        assert state.state == "on", suffix
        assert state.attributes["problem_count"] == len(problems), suffix
        assert state.attributes["problems"] == list(problems), suffix
    assert "broken-missing-service@file" in loaded.router_problems
    assert loaded.routers["broken-missing-service@file"].status is Status.error
    assert "lb-mixed@file" in loaded.service_problems


COUNT_ATTRIBUTES = {"enabled", "warning", "error", "disabled"}


async def test_snapshot_sensors(hass, loaded: TraefikSnapshot) -> None:
    """Counts, version and start time are diagnostic and enabled; healthy_ratio is diagnostic and disabled."""
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    registry = er.async_get(hass)
    main_device = _device_id(hass, entry.entry_id, entry.entry_id)

    for suffix, counts in (
        ("overview_routers_count", loaded.router_counts),
        ("overview_services_count", loaded.service_counts),
        ("overview_middlewares_count", loaded.middleware_counts),
    ):
        state = hass.states.get(entity_id_for(hass, "sensor", f"{entry.entry_id}_{suffix}"))
        assert state is not None, suffix
        assert int(state.state) == counts.total, suffix
        assert set(state.attributes) - {"state_class", "friendly_name"} == COUNT_ATTRIBUTES, suffix
        assert state.attributes["enabled"] == counts.enabled, suffix
        assert state.attributes["error"] == counts.error, suffix

    version = hass.states.get(entity_id_for(hass, "sensor", f"{entry.entry_id}_version"))
    assert version is not None
    assert version.state == loaded.version.version
    assert version.attributes["codename"] == loaded.version.codename
    start = hass.states.get(entity_id_for(hass, "sensor", f"{entry.entry_id}_start_time"))
    assert start is not None
    # Home Assistant renders timestamp states at second precision.
    assert dt_util.parse_datetime(start.state) == loaded.version.start_date.replace(microsecond=0)

    for suffix in (
        "overview_routers_count",
        "overview_services_count",
        "overview_middlewares_count",
        "version",
        "start_time",
    ):
        reg_entry = registry.async_get(entity_id_for(hass, "sensor", f"{entry.entry_id}_{suffix}"))
        assert reg_entry is not None, suffix
        assert reg_entry.entity_category is EntityCategory.DIAGNOSTIC, suffix
        assert reg_entry.disabled_by is None, suffix
        assert reg_entry.device_id == main_device, suffix
    ratio = registry.async_get(entity_id_for(hass, "sensor", f"{entry.entry_id}_healthy_ratio"))
    assert ratio is not None
    assert ratio.entity_category is EntityCategory.DIAGNOSTIC
    assert ratio.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert ratio.device_id == main_device
