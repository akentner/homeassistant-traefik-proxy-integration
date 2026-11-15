"""Lifecycle of per-item entities through the entity manager (routers, services, entrypoints).

Full setups are served from the real captures; a router changes, appears or
vanishes between two coordinator cycles by re-serving a modified rawdata.
"""

from __future__ import annotations

import copy
import dataclasses
import logging
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import async_fire_time_changed

from custom_components.traefik_proxy.const import (
    CONF_PER_ITEM_ENTITIES,
    DOMAIN,
    ITEM_STATE_OPTIONS,
    UID_MIDDLEWARES_PROBLEM,
    UID_ROUTERS_PROBLEM,
    UID_SERVICES_PROBLEM,
)
from custom_components.traefik_proxy.entity_manager import (
    CERT_EXPIRING,
    CERT_EXPIRY,
    ENTRYPOINTS,
    ROUTERS,
    SERVICES,
    KindSpec,
    TraefikEntityManager,
)
from tests.conftest import (
    FIXTURE_VERSIONS,
    MOCK_URL,
    entity_id_for,
    frozen_v37_certificates,
    load_fixture,
    make_traefik_entry,
    rawdata_copy,
    restub_traefik,
    setup_traefik_entry,
    stub_traefik,
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
    """Minimal coordinator: one listener list, a success flag and the data of a finished cycle."""

    def __init__(self) -> None:
        self.last_update_success = True
        self.data: Any = {}
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


# ---------------------------------------------------------------------------
# Grace period: missing for 24 h (or the configured hours) on the wall clock, then removed
# ---------------------------------------------------------------------------

# The spec values, independent of the constants they are checked against.
GRACE = timedelta(hours=24)
CHECK_INTERVAL = timedelta(minutes=5)
GHOST = "ghost@file"
# Stored option key of the grace period (a persistence contract).
GRACE_OPTION = "missing_grace_hours"


def _store_key(entry_id: str) -> str:
    return f"{DOMAIN}.missing.{entry_id}"


def _router_keys(hass: HomeAssistant, entry: Any) -> list[str]:
    """Return the router keys of the entry's sensor registry entries."""
    return [
        key
        for reg_entry in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if reg_entry.domain == ROUTERS.domain
        and (key := ROUTERS.key_of(entry.entry_id, reg_entry.unique_id)) is not None
    ]


async def _run_deadline_check(hass: HomeAssistant) -> None:
    """Fire every timer due within one check interval; the wall clock stays where it is."""
    async_fire_time_changed(hass, dt_util.utcnow() + CHECK_INTERVAL)
    await hass.async_block_till_done()


async def _setup_with_ghost(hass: HomeAssistant, aioclient_mock: Any, entry: Any) -> str:
    """Register an orphan router sensor for ``entry`` (key absent from Traefik), then set the entry up."""
    stub_traefik(aioclient_mock)
    entry.add_to_hass(hass)
    unique_id = ROUTERS.unique_id(entry.entry_id, GHOST)
    reg_entry = er.async_get(hass).async_get_or_create(ROUTERS.domain, DOMAIN, unique_id, config_entry=entry)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return reg_entry.entity_id


async def test_vanished_router_removed_after_grace_period(hass, aioclient_mock, mock_tls_probe, freezer) -> None:  # type: ignore[no-untyped-def]
    """A vanished router keeps its registry entry until 24 h have passed; the next check removes it."""
    entry = await setup_traefik_entry(hass, aioclient_mock)
    registry = er.async_get(hass)
    entity_id = _router_entity_id(hass, entry)
    area = ar.async_get(hass).async_create("Rack")
    registry.async_update_entity(entity_id, name="My router", area_id=area.id)
    rawdata = rawdata_copy()
    del rawdata["routers"][ROUTER]
    await _refresh(hass, aioclient_mock, entry, rawdata, "v3.7")
    assert hass.states.get(entity_id).state == "missing"  # type: ignore[union-attr]

    freezer.tick(GRACE - timedelta(seconds=1))
    await _run_deadline_check(hass)
    reg_entry = registry.async_get(entity_id)
    assert reg_entry is not None
    assert (reg_entry.name, reg_entry.area_id) == ("My router", area.id)
    assert hass.states.get(entity_id).state == "missing"  # type: ignore[union-attr]

    freezer.tick(timedelta(seconds=2))
    await _run_deadline_check(hass)
    assert registry.async_get(entity_id) is None
    assert hass.states.get(entity_id) is None
    assert ROUTER not in _router_keys(hass, entry)
    assert entry.runtime_data.entity_manager.missing_since(ROUTERS, ROUTER) is None


async def test_grace_deadline_is_inclusive(hass, aioclient_mock, mock_tls_probe, freezer) -> None:  # type: ignore[no-untyped-def]
    """A router missing for exactly the grace period is removed by the next check."""
    entry = await setup_traefik_entry(hass, aioclient_mock)
    entity_id = _router_entity_id(hass, entry)
    rawdata = rawdata_copy()
    del rawdata["routers"][ROUTER]
    await _refresh(hass, aioclient_mock, entry, rawdata, "v3.7")

    freezer.tick(GRACE)
    await _run_deadline_check(hass)
    assert er.async_get(hass).async_get(entity_id) is None


async def test_reappearing_router_inside_grace_keeps_entity(hass, aioclient_mock, mock_tls_probe, freezer) -> None:  # type: ignore[no-untyped-def]
    """A router back inside the grace period keeps its entity; the original deadline removes nothing."""
    entry = await setup_traefik_entry(hass, aioclient_mock)
    entity_id = _router_entity_id(hass, entry)
    rawdata = rawdata_copy()
    removed = rawdata["routers"].pop(ROUTER)
    await _refresh(hass, aioclient_mock, entry, rawdata, "v3.7")

    freezer.tick(timedelta(hours=1))
    rawdata["routers"][ROUTER] = removed
    await _refresh(hass, aioclient_mock, entry, rawdata, "v3.7")
    freezer.tick(GRACE)
    await _run_deadline_check(hass)

    assert _router_entity_id(hass, entry) == entity_id
    assert _router_keys(hass, entry).count(ROUTER) == 1
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "enabled"
    assert "missing_since" not in state.attributes


async def test_grace_period_survives_entry_reload(hass, aioclient_mock, mock_tls_probe, freezer, hass_storage) -> None:  # type: ignore[no-untyped-def]
    """missing_since is persisted per entry: after a reload the router is missing since the original time."""
    entry = await setup_traefik_entry(hass, aioclient_mock)
    entity_id = _router_entity_id(hass, entry)
    rawdata = rawdata_copy()
    del rawdata["routers"][ROUTER]
    await _refresh(hass, aioclient_mock, entry, rawdata, "v3.7")
    vanished_at = dt_util.utcnow()
    assert hass_storage[_store_key(entry.entry_id)]["data"] == {"router": {ROUTER: vanished_at.isoformat()}}

    freezer.tick(GRACE / 2)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    assert _router_entity_id(hass, entry) == entity_id
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "missing"
    assert state.attributes["missing_since"] == vanished_at.isoformat()

    freezer.tick(GRACE / 2 - timedelta(seconds=1))
    await _run_deadline_check(hass)
    assert er.async_get(hass).async_get(entity_id) is not None

    freezer.tick(timedelta(seconds=2))
    await _run_deadline_check(hass)
    assert er.async_get(hass).async_get(entity_id) is None
    assert hass.states.get(entity_id) is None


async def _set_grace_hours_through_options(hass: HomeAssistant, entry: Any, hours: int) -> None:
    """Save the options form with its defaults and ``hours`` as grace period; wait for the reload."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    defaults = {str(marker): marker.default() for marker in result["data_schema"].schema}
    result = await hass.config_entries.options.async_configure(result["flow_id"], {**defaults, GRACE_OPTION: hours})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    # The reload is scheduled; the first cert cycle is an entry background task.
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.state is ConfigEntryState.LOADED
    assert entry.options[GRACE_OPTION] == hours


async def test_configured_grace_period_removes_vanished_router(hass, aioclient_mock, mock_tls_probe, freezer) -> None:  # type: ignore[no-untyped-def]
    """With a 2 h grace period a vanished router is still registered at 2 h - 1 s and removed at 2 h."""
    entry = await setup_traefik_entry(hass, aioclient_mock, make_traefik_entry(options={GRACE_OPTION: 2}))
    registry = er.async_get(hass)
    entity_id = _router_entity_id(hass, entry)
    rawdata = rawdata_copy()
    del rawdata["routers"][ROUTER]
    await _refresh(hass, aioclient_mock, entry, rawdata, "v3.7")

    freezer.tick(timedelta(hours=2) - timedelta(seconds=1))
    await _run_deadline_check(hass)
    assert registry.async_get(entity_id) is not None
    assert hass.states.get(entity_id).state == "missing"  # type: ignore[union-attr]

    freezer.tick(timedelta(seconds=1))
    await _run_deadline_check(hass)
    assert registry.async_get(entity_id) is None
    assert hass.states.get(entity_id) is None


@pytest.mark.parametrize(("hours", "removed"), [(2, True), (48, False)])
async def test_changed_grace_period_applies_after_options_reload(  # type: ignore[no-untyped-def]
    hass, aioclient_mock, mock_tls_probe, freezer, hass_storage, hours: int, removed: bool
) -> None:
    """A router missing for 3 h: a 2 h grace period removes it right after the reload, 48 h keeps it.

    The stored missing-since time is the original one after the reload.
    """
    entry = await setup_traefik_entry(hass, aioclient_mock)
    registry = er.async_get(hass)
    entity_id = _router_entity_id(hass, entry)
    rawdata = rawdata_copy()
    del rawdata["routers"][ROUTER]
    await _refresh(hass, aioclient_mock, entry, rawdata, "v3.7")
    vanished_at = dt_util.utcnow()
    freezer.tick(timedelta(hours=3))
    await _run_deadline_check(hass)
    assert registry.async_get(entity_id) is not None

    await _set_grace_hours_through_options(hass, entry, hours)
    freezer.tick(CHECK_INTERVAL)
    await _run_deadline_check(hass)

    if removed:
        assert registry.async_get(entity_id) is None
        assert hass.states.get(entity_id) is None
        assert hass_storage[_store_key(entry.entry_id)]["data"] == {}
    else:
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == "missing"
        assert state.attributes["missing_since"] == vanished_at.isoformat()
        assert hass_storage[_store_key(entry.entry_id)]["data"] == {"router": {ROUTER: vanished_at.isoformat()}}


async def test_orphan_registry_entry_adopted_and_removed_after_grace(  # type: ignore[no-untyped-def]
    hass, aioclient_mock, mock_tls_probe, freezer, hass_storage
) -> None:
    """A registry entry whose router is absent at setup becomes a missing entity and is removed 24 h later."""
    entry = make_traefik_entry(entry_id="orphan-entry")
    entity_id = await _setup_with_ghost(hass, aioclient_mock, entry)
    setup_at = dt_util.utcnow()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "missing"
    assert state.attributes["missing_since"] == setup_at.isoformat()
    assert hass_storage[_store_key("orphan-entry")]["data"] == {"router": {GHOST: setup_at.isoformat()}}
    assert sorted(_router_keys(hass, entry)) == sorted([*entry.runtime_data.coordinator.data.routers, GHOST])

    freezer.tick(GRACE - timedelta(seconds=1))
    await _run_deadline_check(hass)
    assert er.async_get(hass).async_get(entity_id) is not None

    freezer.tick(timedelta(seconds=2))
    await _run_deadline_check(hass)
    assert er.async_get(hass).async_get(entity_id) is None
    assert hass.states.get(entity_id) is None
    assert hass_storage[_store_key("orphan-entry")]["data"] == {}


async def test_expired_stored_orphan_removed_at_setup(hass, aioclient_mock, mock_tls_probe, hass_storage) -> None:  # type: ignore[no-untyped-def]
    """An orphan whose stored missing_since is older than 24 h is removed during setup and never gets a state."""
    key = _store_key("expired-entry")
    stored_since = dt_util.utcnow() - GRACE - timedelta(hours=1)
    hass_storage[key] = {
        "version": 1,
        "minor_version": 1,
        "key": key,
        "data": {"router": {GHOST: stored_since.isoformat(), "gone-long-ago@file": stored_since.isoformat()}},
    }
    entry = make_traefik_entry(entry_id="expired-entry")
    entity_id = await _setup_with_ghost(hass, aioclient_mock, entry)

    assert er.async_get(hass).async_get(entity_id) is None
    assert hass.states.get(entity_id) is None
    assert GHOST not in _router_keys(hass, entry)
    assert sorted(_router_keys(hass, entry)) == sorted(entry.runtime_data.coordinator.data.routers)
    assert hass_storage[key]["data"] == {}


async def test_empty_snapshot_marks_missing_and_deletes_nothing(hass, aioclient_mock, mock_tls_probe, freezer) -> None:  # type: ignore[no-untyped-def]
    """A successful snapshot without routers marks every router sensor missing and removes no registry entry."""
    entry = await setup_traefik_entry(hass, aioclient_mock)
    keys = sorted(_router_keys(hass, entry))
    assert keys == sorted(entry.runtime_data.coordinator.data.routers)
    rawdata = rawdata_copy()
    rawdata["routers"] = {}

    await _refresh(hass, aioclient_mock, entry, rawdata, "v3.7")
    freezer.tick(GRACE - timedelta(seconds=1))
    await _run_deadline_check(hass)

    assert sorted(_router_keys(hass, entry)) == keys
    for key in keys:
        state = hass.states.get(_router_entity_id(hass, entry, key))
        assert state is not None and state.state == "missing", key


async def test_failed_cycle_never_marks_missing(hass, aioclient_mock, mock_tls_probe, hass_storage) -> None:  # type: ignore[no-untyped-def]
    """A failed cycle makes router sensors unavailable without marking any key missing."""
    entry = await setup_traefik_entry(hass, aioclient_mock)
    keys = _router_keys(hass, entry)
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{MOCK_URL}/api/rawdata", status=500)
    stub_traefik(aioclient_mock)

    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert not entry.runtime_data.coordinator.last_update_success
    manager = entry.runtime_data.entity_manager
    for key in keys:
        state = hass.states.get(_router_entity_id(hass, entry, key))
        assert state is not None and state.state == "unavailable", key
        assert manager.missing_since(ROUTERS, key) is None, key
    assert _store_key(entry.entry_id) not in hass_storage


async def test_failed_cycle_keeps_stored_cert_missing_time(  # type: ignore[no-untyped-def]
    hass, aioclient_mock, mock_tls_probe, freezer, hass_storage
) -> None:
    """A failed first cert cycle keeps a restored host's stored missing time and stamps no other host."""
    stored_host, plain_host = "www.secure.example.com", "secure.example.com"
    key = _store_key("stored-cert-entry")
    stored_since = dt_util.utcnow() - timedelta(hours=2)
    hass_storage[key] = {
        "version": 1,
        "minor_version": 1,
        "key": key,
        "data": {CERT_EXPIRY.name: {stored_host: stored_since.isoformat()}},
    }
    entry = make_traefik_entry(entry_id="stored-cert-entry")
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    for host in (stored_host, plain_host):
        registry.async_get_or_create(
            CERT_EXPIRY.domain, DOMAIN, CERT_EXPIRY.unique_id(entry.entry_id, host), config_entry=entry
        )
    aioclient_mock.get(f"{MOCK_URL}/api/certificates", status=500)
    stub_traefik(aioclient_mock)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    assert not entry.runtime_data.cert_coordinator.last_update_success
    manager = entry.runtime_data.entity_manager
    assert manager.missing_since(CERT_EXPIRY, stored_host) == stored_since
    assert manager.missing_since(CERT_EXPIRY, plain_host) is None
    for host in (stored_host, plain_host):
        entity_id = entity_id_for(hass, CERT_EXPIRY.domain, CERT_EXPIRY.unique_id(entry.entry_id, host))
        state = hass.states.get(entity_id)
        assert state is not None and state.state == "unavailable", host
    assert hass_storage[key]["data"] == {CERT_EXPIRY.name: {stored_host: stored_since.isoformat()}}


async def test_remove_entry_deletes_missing_store(hass, aioclient_mock, mock_tls_probe, hass_storage) -> None:  # type: ignore[no-untyped-def]
    """Removing the config entry deletes its missing-since Store."""
    entry = await setup_traefik_entry(hass, aioclient_mock)
    rawdata = rawdata_copy()
    del rawdata["routers"][ROUTER]
    await _refresh(hass, aioclient_mock, entry, rawdata, "v3.7")
    key = _store_key(entry.entry_id)
    assert ROUTER in hass_storage[key]["data"]["router"]

    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert key not in hass_storage


# ---------------------------------------------------------------------------
# Services and entrypoints through the manager
# ---------------------------------------------------------------------------

SERVICE = "file-ok-svc@file"


def _service_entity_id(hass: HomeAssistant, entry: Any, key: str = SERVICE) -> str:
    return entity_id_for(hass, SERVICES.domain, SERVICES.unique_id(entry.entry_id, key))


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
async def test_service_server_down_reaches_sensor_next_cycle(
    hass, aioclient_mock, mock_tls_probe, version: str
) -> None:  # type: ignore[no-untyped-def]
    """A server going DOWN changes servers_up on the next cycle; disabled + error turns the state to error."""
    entry = await setup_traefik_entry(hass, aioclient_mock, version=version)
    entity_id = _service_entity_id(hass, entry)
    state = hass.states.get(entity_id)
    assert state is not None
    assert (state.state, state.attributes["servers_up"], state.attributes["servers_total"]) == ("enabled", 1, 1)

    rawdata = rawdata_copy(version)
    service = rawdata["services"][SERVICE]
    service["serverStatus"] = dict.fromkeys(service["serverStatus"], "DOWN")
    await _refresh(hass, aioclient_mock, entry, rawdata, version)

    state = hass.states.get(entity_id)
    assert state is not None
    assert (state.state, state.attributes["servers_up"], state.attributes["servers_total"]) == ("enabled", 0, 1)
    assert SERVICE in entry.runtime_data.coordinator.data.service_problems

    service["status"] = "disabled"
    service["error"] = ["boom"]
    await _refresh(hass, aioclient_mock, entry, rawdata, version)

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "error"
    assert state.attributes["errors"] == ["boom"]


async def test_new_service_appears_and_vanished_service_goes_missing(
    hass, aioclient_mock, mock_tls_probe, freezer
) -> None:  # type: ignore[no-untyped-def]
    """A new service gets its sensor without reload; a vanished one stays registered with state missing."""
    entry = await setup_traefik_entry(hass, aioclient_mock)
    entity_id = _service_entity_id(hass, entry)
    rawdata = rawdata_copy()
    rawdata["services"]["added-svc@file"] = copy.deepcopy(rawdata["services"].pop(SERVICE))

    await _refresh(hass, aioclient_mock, entry, rawdata, "v3.7")

    added = hass.states.get(_service_entity_id(hass, entry, "added-svc@file"))
    assert added is not None and added.state == "enabled"
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "missing"
    assert state.attributes["missing_since"] == dt_util.utcnow().isoformat()
    assert er.async_get(hass).async_get(entity_id) is not None


async def test_vanished_entrypoint_goes_missing(hass, aioclient_mock, mock_tls_probe, freezer) -> None:  # type: ignore[no-untyped-def]
    """An enabled entrypoint sensor whose entrypoint vanished reads missing with missing_since."""
    entry = make_traefik_entry()
    entry.add_to_hass(hass)
    unique_id = ENTRYPOINTS.unique_id(entry.entry_id, "web")
    entity_id = er.async_get(hass).async_get_or_create("sensor", DOMAIN, unique_id, config_entry=entry).entity_id
    await setup_traefik_entry(hass, aioclient_mock, entry)
    state = hass.states.get(entity_id)
    assert state is not None and state.state == ":80"

    coordinator = entry.runtime_data.coordinator
    entrypoints = {name: ep for name, ep in coordinator.data.entrypoints.items() if name != "web"}
    coordinator.async_set_updated_data(dataclasses.replace(coordinator.data, entrypoints=entrypoints))
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "missing"
    assert state.attributes["missing_since"] == dt_util.utcnow().isoformat()
    assert er.async_get(hass).async_get(entity_id) is not None


async def test_router_and_service_with_same_name_are_separate(hass, aioclient_mock, mock_tls_probe) -> None:  # type: ignore[no-untyped-def]
    """A router and a service both named dup@file are two sensors on the Routers and Services sub-devices."""
    rawdata = rawdata_copy()
    rawdata["routers"]["dup@file"] = copy.deepcopy(rawdata["routers"][ROUTER])
    rawdata["services"]["dup@file"] = copy.deepcopy(rawdata["services"][SERVICE])
    entry = await setup_traefik_entry(hass, aioclient_mock, rawdata=rawdata)
    registry = er.async_get(hass)
    devices = _entry_devices(hass, entry)

    router_entry = registry.async_get(_router_entity_id(hass, entry, "dup@file"))
    service_entry = registry.async_get(_service_entity_id(hass, entry, "dup@file"))
    assert router_entry is not None and service_entry is not None
    assert router_entry.entity_id != service_entry.entity_id
    assert router_entry.unique_id == f"{entry.entry_id}_http_router_dup@file"
    assert service_entry.unique_id == SERVICES.unique_id(entry.entry_id, "dup@file")
    assert service_entry.unique_id == f"{entry.entry_id}_http_service_dup@file"
    assert router_entry.device_id == devices[(DOMAIN, f"{entry.entry_id}_routers")].id
    assert service_entry.device_id == devices[(DOMAIN, f"{entry.entry_id}_services")].id


# ---------------------------------------------------------------------------
# Per-item option: no router or service entities when it is off
# ---------------------------------------------------------------------------

PER_ITEM_OFF = {CONF_PER_ITEM_ENTITIES: False}
SNAPSHOT_UID_SUFFIXES = ("overview_routers_count", "version", "start_time")
PROBLEM_UID_SUFFIXES = (UID_ROUTERS_PROBLEM, UID_SERVICES_PROBLEM, UID_MIDDLEWARES_PROBLEM)


def _kind_keys(hass: HomeAssistant, entry: Any, spec: KindSpec) -> list[str]:
    """Return the keys of the entry's registry entries of ``spec``."""
    return [
        key
        for reg_entry in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if reg_entry.domain == spec.domain and (key := spec.key_of(entry.entry_id, reg_entry.unique_id)) is not None
    ]


def _registered(hass: HomeAssistant, domain: str, unique_id: str) -> bool:
    return er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique_id) is not None


def _sub_device_ids(entry: Any) -> dict[str, tuple[str, str]]:
    return {sub: (DOMAIN, f"{entry.entry_id}_{sub}") for sub in SUB_DEVICES}


def _assert_per_item_off(hass: HomeAssistant, entry: Any) -> None:
    """No router/service entity or sub-device; everything else is still there."""
    entry_id = entry.entry_id
    assert _kind_keys(hass, entry, ROUTERS) == []
    assert _kind_keys(hass, entry, SERVICES) == []
    assert _kind_keys(hass, entry, ENTRYPOINTS)
    # The test probe fails for every host; both cert kinds still exist for a
    # host without a certificate and are unaffected by the per-item option.
    assert _kind_keys(hass, entry, CERT_EXPIRING)
    assert sorted(_kind_keys(hass, entry, CERT_EXPIRY)) == sorted(_kind_keys(hass, entry, CERT_EXPIRING))
    for suffix in SNAPSHOT_UID_SUFFIXES:
        assert _registered(hass, "sensor", f"{entry_id}_{suffix}"), suffix
    for suffix in PROBLEM_UID_SUFFIXES:
        assert _registered(hass, "binary_sensor", f"{entry_id}_{suffix}"), suffix

    devices = _entry_devices(hass, entry)
    subs = _sub_device_ids(entry)
    assert (DOMAIN, entry_id) in devices
    assert subs["certificates"] in devices
    assert subs["routers"] not in devices
    assert subs["services"] not in devices


async def test_per_item_off_creates_no_router_or_service_entities(hass, aioclient_mock, mock_tls_probe) -> None:  # type: ignore[no-untyped-def]
    """A fresh entry with the option off gets no router/service entity and no Routers/Services sub-device."""
    entry = await setup_traefik_entry(hass, aioclient_mock, make_traefik_entry(options=PER_ITEM_OFF))
    _assert_per_item_off(hass, entry)
    assert entry.runtime_data.entity_manager.missing_since(ROUTERS, ROUTER) is None


async def test_per_item_off_on_reload_removes_existing_entities(  # type: ignore[no-untyped-def]
    hass, aioclient_mock, mock_tls_probe, freezer, hass_storage
) -> None:
    """Turning the option off removes router/service entities and sub-devices right at the reload."""
    entry = await setup_traefik_entry(hass, aioclient_mock)
    router_entity_id = _router_entity_id(hass, entry)
    service_entity_id = _service_entity_id(hass, entry)
    # A router missing at the reload must not survive as a missing entity either.
    rawdata = rawdata_copy()
    del rawdata["routers"][ROUTER]
    await _refresh(hass, aioclient_mock, entry, rawdata, "v3.7")
    assert hass_storage[_store_key(entry.entry_id)]["data"] == {"router": {ROUTER: dt_util.utcnow().isoformat()}}

    hass.config_entries.async_update_entry(entry, options=PER_ITEM_OFF)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    _assert_per_item_off(hass, entry)
    assert er.async_get(hass).async_get(router_entity_id) is None
    assert er.async_get(hass).async_get(service_entity_id) is None
    assert hass.states.get(router_entity_id) is None
    assert hass.states.get(service_entity_id) is None
    assert hass_storage[_store_key(entry.entry_id)]["data"] == {}


async def test_per_item_off_reload_is_idempotent(hass, aioclient_mock, mock_tls_probe, caplog) -> None:  # type: ignore[no-untyped-def]
    """A second reload with the option still off removes nothing more and raises nothing."""
    entry = await setup_traefik_entry(hass, aioclient_mock)
    hass.config_entries.async_update_entry(entry, options=PER_ITEM_OFF)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    before_entities = {reg.entity_id for reg in er.async_entries_for_config_entry(registry, entry.entry_id)}
    before_devices = set(_entry_devices(hass, entry))

    # Only the second reload is under test; the options update itself still logs
    # the cert closures' duplicate unique_id errors until the cert entities move
    # onto the manager.
    caplog.clear()
    caplog.set_level(logging.WARNING)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    _assert_per_item_off(hass, entry)
    assert {reg.entity_id for reg in er.async_entries_for_config_entry(registry, entry.entry_id)} == before_entities
    assert set(_entry_devices(hass, entry)) == before_devices
    assert "Traceback" not in caplog.text
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


async def test_per_item_default_keeps_router_and_service_entities(hass, aioclient_mock, mock_tls_probe) -> None:  # type: ignore[no-untyped-def]
    """Without the option key router and service entities and all sub-devices exist as before."""
    entry = await setup_traefik_entry(hass, aioclient_mock)
    assert CONF_PER_ITEM_ENTITIES not in entry.options
    assert ROUTER in _kind_keys(hass, entry, ROUTERS)
    assert SERVICE in _kind_keys(hass, entry, SERVICES)
    devices = _entry_devices(hass, entry)
    assert set(_sub_device_ids(entry).values()) <= set(devices)
    reg_entry = er.async_get(hass).async_get(_service_entity_id(hass, entry))
    assert reg_entry is not None
    assert reg_entry.device_id == devices[(DOMAIN, f"{entry.entry_id}_services")].id


async def test_unchanged_notifications_write_no_state(hass, aioclient_mock, freezer, mock_tls_probe) -> None:  # type: ignore[no-untyped-def]
    """With every entity enabled, forced and unchanged notifications write no state anywhere (ROADMAP SC3)."""
    # The capture's certificate dates (88.5 days left): one tick later the live day count is unchanged.
    aioclient_mock.get(f"{MOCK_URL}/api/certificates", json=frozen_v37_certificates(freezer))
    entry = make_traefik_entry()
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    # Pre-create the disabled-by-default entities enabled.
    for name in load_fixture("v3.7", "entrypoints.json"):
        registry.async_get_or_create(
            ENTRYPOINTS.domain, DOMAIN, ENTRYPOINTS.unique_id(entry.entry_id, name["name"]), config_entry=entry
        )
    registry.async_get_or_create("sensor", DOMAIN, f"{entry.entry_id}_healthy_ratio", config_entry=entry)

    await setup_traefik_entry(hass, aioclient_mock, entry)
    reg_entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert not [reg.entity_id for reg in reg_entries if reg.disabled_by is not None]
    states = {reg.entity_id: hass.states.get(reg.entity_id) for reg in reg_entries}
    assert all(state is not None for state in states.values()), states
    # HA updates last_reported in place on the same State object: keep the values.
    before = {entity_id: state.last_reported for entity_id, state in states.items() if state is not None}
    assert any(
        reg.domain == ENTRYPOINTS.domain and reg.unique_id.startswith(f"{entry.entry_id}_{ENTRYPOINTS.prefix}")
        for reg in reg_entries
    )
    runtime = entry.runtime_data

    freezer.tick(timedelta(seconds=1))
    runtime.coordinator.async_update_listeners()
    runtime.cert_coordinator.async_set_updated_data(dict(runtime.cert_coordinator.data))
    await runtime.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert runtime.coordinator.last_update_success
    for entity_id, last_reported in before.items():
        after = hass.states.get(entity_id)
        assert after is not None
        assert after.last_reported == last_reported, entity_id
