"""Entity states on both real capture generations (v2.11 and v3.7).

A full setup is served from the committed captures through ``stub_traefik``.
Expected values come from the snapshot built from the same capture, so the
test proves the path capture -> client -> coordinator -> entities, not the
parser itself.
"""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.traefik_proxy.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL, DOMAIN
from custom_components.traefik_proxy.models import Status, TraefikSnapshot
from tests.conftest import FIXTURE_VERSIONS, MOCK_URL, snapshot_from_fixture, stub_traefik

FAILING_ENTITIES = (
    "binary_sensor.traefik_any_router_failing",
    "binary_sensor.traefik_any_service_failing",
    "binary_sensor.traefik_any_middleware_failing",
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


async def test_router_binary_sensors(hass, loaded: TraefikSnapshot) -> None:
    """One binary_sensor per non-internal router, on iff the router is enabled."""
    assert loaded.routers
    for name, router in loaded.routers.items():
        state = hass.states.get(f"binary_sensor.traefik_http_router_{slugify(name)}")
        assert state is not None, name
        assert state.state == ("on" if router.status is Status.enabled else "off"), name
        assert state.attributes["status"] == str(router.status)
    assert not any(name.endswith("@internal") for name in loaded.routers)
    router_entities = hass.states.async_entity_ids("binary_sensor")
    assert sum(eid.startswith("binary_sensor.traefik_http_router_") for eid in router_entities) == len(loaded.routers)


async def test_entrypoint_sensors(hass, loaded: TraefikSnapshot) -> None:
    """Each entrypoint sensor shows its address; ``transport`` is the protocol."""
    assert loaded.entrypoints
    for name, entrypoint in loaded.entrypoints.items():
        state = hass.states.get(f"sensor.traefik_http_entrypoint_{slugify(name)}")
        assert state is not None, name
        assert state.state == entrypoint.address
        assert state.attributes["transport"] == entrypoint.protocol
    assert {ep.protocol for ep in loaded.entrypoints.values()} == {"tcp", "udp"}


async def test_service_sensors(hass, loaded: TraefikSnapshot) -> None:
    """Each service sensor shows its status and the server counts from serverStatus."""
    assert loaded.services
    for name, service in loaded.services.items():
        state = hass.states.get(f"sensor.traefik_http_service_{slugify(name)}")
        assert state is not None, name
        assert state.state == str(service.status)
        assert state.attributes["server_count"] == service.servers_total
        assert state.attributes["servers_up"] == service.servers_up
    mixed = hass.states.get(f"sensor.traefik_http_service_{slugify('lb-mixed@file')}")
    assert mixed is not None
    assert (mixed.attributes["server_count"], mixed.attributes["servers_up"]) == (2, 1)


async def test_count_sensors(hass, loaded: TraefikSnapshot) -> None:
    """The count sensors equal the snapshot totals."""
    for entity_id, counts in (
        ("sensor.traefik_routers", loaded.router_counts),
        ("sensor.traefik_services", loaded.service_counts),
        ("sensor.traefik_middlewares", loaded.middleware_counts),
    ):
        state = hass.states.get(entity_id)
        assert state is not None, entity_id
        assert int(state.state) == counts.total, entity_id


async def test_failing_aggregates_registered_and_problems_present(hass, loaded: TraefikSnapshot) -> None:
    """The any-*-failing entities are registered but disabled; the captures carry real problems."""
    registry = er.async_get(hass)
    for entity_id in FAILING_ENTITIES:
        reg_entry = registry.async_get(entity_id)
        assert reg_entry is not None, entity_id
        assert reg_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert "broken-missing-service@file" in loaded.router_problems
    assert loaded.routers["broken-missing-service@file"].status is Status.error
    assert "lb-mixed@file" in loaded.service_problems
