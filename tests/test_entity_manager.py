"""Lifecycle of per-item entities through the entity manager (router kind).

Full setups are served from the real captures; a router changes, appears or
vanishes between two coordinator cycles by re-serving a modified rawdata.
"""

from __future__ import annotations

import copy
import logging
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.traefik_proxy.const import DOMAIN, ITEM_STATE_OPTIONS
from custom_components.traefik_proxy.entity_manager import ROUTERS, KindSpec, TraefikEntityManager
from tests.conftest import (
    FIXTURE_VERSIONS,
    entity_id_for,
    rawdata_copy,
    restub_traefik,
    setup_traefik_entry,
)

ROUTER = "file-ok@file"
ROUTER_ATTRIBUTES = {"rule", "service", "provider", "entry_points", "middlewares", "tls", "errors"}
DUPLICATE_ID_MESSAGE = "does not generate unique IDs"
SUB_DEVICES = ("routers", "services", "certificates")


def _router_entity_id(hass: HomeAssistant, entry: Any, key: str = ROUTER) -> str:
    return entity_id_for(hass, ROUTERS.domain, ROUTERS.unique_id(entry.entry_id, key))


async def _refresh(hass: HomeAssistant, aioclient_mock: Any, entry: Any, rawdata: dict[str, Any], version: str) -> None:
    """Serve ``rawdata`` and run one coordinator cycle."""
    restub_traefik(aioclient_mock, version=version, rawdata=rawdata)
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert entry.runtime_data.coordinator.last_update_success


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
async def test_router_state_follows_status_change(hass, aioclient_mock, mock_tls_probe, version: str) -> None:  # type: ignore[no-untyped-def]
    """The router sensor shows the router status and follows a change on the next cycle."""
    entry = await setup_traefik_entry(hass, aioclient_mock, version=version)
    entity_id = _router_entity_id(hass, entry)
    router = entry.runtime_data.coordinator.data.routers[ROUTER]

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "enabled"
    assert state.attributes["options"] == list(ITEM_STATE_OPTIONS)
    assert set(state.attributes) & ROUTER_ATTRIBUTES == ROUTER_ATTRIBUTES
    assert state.attributes["entry_points"] == list(router.entry_points)
    assert state.attributes["middlewares"] == list(router.middlewares)
    assert state.attributes["errors"] == list(router.errors)
    assert state.attributes["rule"] == router.rule
    assert state.attributes["service"] == router.service
    assert state.attributes["provider"] == router.provider
    assert state.attributes["tls"] is router.tls
    assert "missing_since" not in state.attributes

    reg_entry = er.async_get(hass).async_get(entity_id)
    assert reg_entry is not None
    routers_device = [
        device
        for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
        if (DOMAIN, f"{entry.entry_id}_routers") in device.identifiers
    ]
    assert len(routers_device) == 1
    assert reg_entry.device_id == routers_device[0].id

    rawdata = rawdata_copy(version)
    rawdata["routers"][ROUTER]["status"] = "disabled"
    rawdata["routers"][ROUTER]["error"] = ["boom"]
    await _refresh(hass, aioclient_mock, entry, rawdata, version)

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "error"
    assert state.attributes["errors"] == ["boom"]


async def test_new_router_appears_without_reload(hass, aioclient_mock, mock_tls_probe) -> None:  # type: ignore[no-untyped-def]
    """A router added to Traefik gets its sensor on the next cycle; the entry is not reloaded."""
    entry = await setup_traefik_entry(hass, aioclient_mock)
    runtime_data = entry.runtime_data
    rawdata = rawdata_copy()
    rawdata["routers"]["added@file"] = copy.deepcopy(rawdata["routers"][ROUTER])

    await _refresh(hass, aioclient_mock, entry, rawdata, "v3.7")

    state = hass.states.get(_router_entity_id(hass, entry, "added@file"))
    assert state is not None
    assert state.state == "enabled"
    assert entry.state.name == "LOADED"
    assert entry.runtime_data is runtime_data


async def test_vanished_router_goes_missing_and_rebinds(hass, aioclient_mock, mock_tls_probe, freezer, caplog) -> None:  # type: ignore[no-untyped-def]
    """A vanished router stays registered with state missing and comes back under the same entity_id."""
    caplog.set_level(logging.ERROR)
    entry = await setup_traefik_entry(hass, aioclient_mock)
    registry = er.async_get(hass)
    entity_id = _router_entity_id(hass, entry)
    area = ar.async_get(hass).async_create("Rack")
    registry.async_update_entity(entity_id, name="My router", area_id=area.id)
    await hass.async_block_till_done()

    rawdata = rawdata_copy()
    removed = rawdata["routers"].pop(ROUTER)
    await _refresh(hass, aioclient_mock, entry, rawdata, "v3.7")

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "missing"
    assert state.attributes["missing_since"] == dt_util.utcnow().isoformat()
    assert not set(state.attributes) & ROUTER_ATTRIBUTES
    reg_entry = registry.async_get(entity_id)
    assert reg_entry is not None
    assert (reg_entry.name, reg_entry.area_id) == ("My router", area.id)

    freezer.tick(timedelta(minutes=5))
    rawdata["routers"][ROUTER] = removed
    await _refresh(hass, aioclient_mock, entry, rawdata, "v3.7")

    assert _router_entity_id(hass, entry) == entity_id
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "enabled"
    assert "missing_since" not in state.attributes
    reg_entry = registry.async_get(entity_id)
    assert reg_entry is not None
    assert (reg_entry.name, reg_entry.area_id) == ("My router", area.id)
    assert DUPLICATE_ID_MESSAGE not in caplog.text


async def test_router_change_writes_only_that_router(hass, aioclient_mock, mock_tls_probe, freezer) -> None:  # type: ignore[no-untyped-def]
    """A cycle that changes one router writes that sensor only; the others keep last_reported."""
    entry = await setup_traefik_entry(hass, aioclient_mock)
    entity_ids = {
        reg_entry.entity_id
        for reg_entry in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if reg_entry.domain == ROUTERS.domain and ROUTERS.key_of(entry.entry_id, reg_entry.unique_id) is not None
    }
    assert len(entity_ids) == len(entry.runtime_data.coordinator.data.routers)
    changed = _router_entity_id(hass, entry)
    before = {}
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        assert state is not None
        before[entity_id] = state.last_reported

    freezer.tick(timedelta(seconds=1))
    rawdata = rawdata_copy()
    rawdata["routers"][ROUTER]["status"] = "warning"
    await _refresh(hass, aioclient_mock, entry, rawdata, "v3.7")

    changed_state = hass.states.get(changed)
    assert changed_state is not None
    assert changed_state.state == "warning"
    assert changed_state.last_reported > before[changed]
    for entity_id in entity_ids - {changed}:
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.last_reported == before[entity_id], entity_id


def _entry_devices(hass: HomeAssistant, entry: Any) -> dict[tuple[str, str], dr.DeviceEntry]:
    """Return the entry's devices keyed by their Traefik identifier."""
    return {
        identifier: device
        for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
        for identifier in device.identifiers
        if identifier[0] == DOMAIN
    }


@pytest.mark.xfail(strict=True, reason="RED: device registration not implemented yet")
async def test_router_sensor_on_routers_sub_device(hass, aioclient_mock, mock_tls_probe, caplog) -> None:  # type: ignore[no-untyped-def]
    """Main device and sub-devices are registered, named and linked; router sensors sit on Routers."""
    caplog.set_level(logging.WARNING)
    entry = await setup_traefik_entry(hass, aioclient_mock)
    devices = _entry_devices(hass, entry)
    assert {(DOMAIN, entry.entry_id), *((DOMAIN, f"{entry.entry_id}_{sub}") for sub in SUB_DEVICES)} <= set(devices)
    main = devices[(DOMAIN, entry.entry_id)]
    routers = devices[(DOMAIN, f"{entry.entry_id}_routers")]
    services = devices[(DOMAIN, f"{entry.entry_id}_services")]
    certificates = devices[(DOMAIN, f"{entry.entry_id}_certificates")]

    reg_entry = er.async_get(hass).async_get(_router_entity_id(hass, entry))
    assert reg_entry is not None
    assert reg_entry.device_id == routers.id
    for sub in (routers, services, certificates):
        assert sub.via_device_id == main.id
    assert main.via_device_id is None
    assert main.entry_type is dr.DeviceEntryType.SERVICE
    assert main.manufacturer == "Traefik"
    assert main.name == "Traefik (traefik.example.com)"
    assert main.configuration_url == "https://traefik.example.com:8080/dashboard/"
    assert main.sw_version == entry.runtime_data.coordinator.data.version.version
    assert main.sw_version
    assert routers.name == "Traefik routers (traefik.example.com)"
    assert services.name == "Traefik services (traefik.example.com)"
    assert certificates.name == "Traefik certificates (traefik.example.com)"
    assert "via_device" not in caplog.text
    assert "Detected that custom integration 'traefik_proxy'" not in caplog.text


@pytest.mark.xfail(strict=True, reason="RED: device registration not implemented yet")
@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://user:pw@traefik.example.com:8080/", "https://traefik.example.com:8080/dashboard/"),
        ("http://[::1]:8080", "http://[::1]:8080/dashboard/"),
        ("https://h.example.com/traefik/?x=1#f", "https://h.example.com/traefik/dashboard/"),
        ("HTTPS://H.example.com", "https://h.example.com/dashboard/"),
        ("ftp://h.example.com", None),
        ("https:///path", None),
        ("https://h.example.com:99999", None),
        ("not a url", None),
    ],
)
def test_dashboard_url_variants(url: str, expected: str | None) -> None:
    """The dashboard URL keeps scheme, host, port and path prefix; drops userinfo, query and fragment."""
    from custom_components.traefik_proxy.entity import dashboard_url

    assert dashboard_url(url) == expected


@pytest.mark.xfail(strict=True, reason="RED: device registration not implemented yet")
def test_entry_host_falls_back_to_title() -> None:
    """The device host is the URL hostname, or the entry title when the URL has none."""
    from custom_components.traefik_proxy.entity import entry_host

    entry = MagicMock(title="Traefik", data={"url": "https://user:pw@traefik.example.com:8080"})
    assert entry_host(entry) == "traefik.example.com"
    entry.data = {"url": "http://[::1"}
    assert entry_host(entry) == "Traefik"
    entry.data = {"url": "no host"}
    assert entry_host(entry) == "Traefik"


class _FakeCoordinator:
    """Minimal coordinator: one listener list and a success flag."""

    def __init__(self) -> None:
        self.last_update_success = True
        self.listeners: list[Any] = []

    def async_add_listener(self, update_callback: Any) -> Any:
        self.listeners.append(update_callback)
        return lambda: None

    def notify(self) -> None:
        for listener in list(self.listeners):
            listener()


def test_manager_adds_each_key_once_in_sorted_order(freezer) -> None:  # type: ignore[no-untyped-def]
    """New keys are added sorted in one call; known keys are never added again; failed cycles change nothing."""
    entry = MagicMock()
    manager = TraefikEntityManager(MagicMock(), entry)
    spec = KindSpec("thing", "sensor", "thing_")
    coordinator = _FakeCoordinator()
    keys = {"b", "a"}
    calls: list[list[str]] = []

    manager.async_add_kind(
        spec,
        coordinator=coordinator,  # type: ignore[arg-type]
        keys=lambda: keys,
        factory=lambda key: key,  # type: ignore[arg-type,return-value]
        async_add_entities=lambda entities: calls.append(list(entities)),  # type: ignore[arg-type]
    )
    assert calls == [["a", "b"]]
    assert entry.async_on_unload.call_count == 1

    keys = {"d", "a", "c"}
    coordinator.notify()
    assert calls == [["a", "b"], ["c", "d"]]
    assert manager.missing_since(spec, "b") == dt_util.utcnow()
    assert manager.missing_since(spec, "a") is None

    freezer.tick(timedelta(minutes=1))
    coordinator.last_update_success = False
    keys = set()
    coordinator.notify()
    assert len(calls) == 2
    assert manager.missing_since(spec, "a") is None

    coordinator.last_update_success = True
    keys = {"a", "b", "c", "d"}
    coordinator.notify()
    coordinator.notify()
    assert len(calls) == 2
    assert manager.missing_since(spec, "b") is None
    assert manager.missing_since(KindSpec("other", "sensor", "other_"), "a") is None


def test_kind_spec_unique_id_round_trip() -> None:
    """``key_of`` inverts ``unique_id`` and rejects other kinds, other entries and empty keys."""
    unique_id = ROUTERS.unique_id("entry1", "file-ok@file")
    assert unique_id == "entry1_http_router_file-ok@file"
    assert ROUTERS.key_of("entry1", unique_id) == "file-ok@file"
    assert ROUTERS.key_of("entry2", unique_id) is None
    assert ROUTERS.key_of("entry1", "entry1_http_service_file-ok@file") is None
    assert ROUTERS.key_of("entry1", "entry1_http_router_") is None
