"""HA-state propagation and lifecycle of the TLS certificate entities after a full setup.

The cert entities must follow the cert coordinator: a cert cycle, a
threshold change and a ``tls_warn_days`` options change reach
``hass.states`` without any change of the main Traefik snapshot. The main
coordinator keeps ``always_update=False``, so these tests fail whenever a
cert entity only listens to the main coordinator.

The entry's entity manager adds each certificate host once, keeps a host
that leaves the cert data registered (unavailable) for the grace period and
the entities write their state only when it changed.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.traefik_proxy.const import (
    CONF_API_KEY,
    CONF_TLS_WARN_DAYS,
    CONF_URL,
    CONF_VERIFY_SSL,
    DOMAIN,
)
from custom_components.traefik_proxy.entity_manager import CERT_EXPIRING, CERT_EXPIRY, ROUTERS
from custom_components.traefik_proxy.tls import CertError, CertInfo
from tests.conftest import MOCK_URL, entity_id_for, load_fixture, rawdata_copy, restub_traefik, stub_traefik

# TLS hosts of the v3.7 capture (tls.domains and Host(...) rules).
HOST = "secure.example.com"
OTHER_HOST = "www.secure.example.com"

# Fixed reference instant so not_after values are deterministic.
REFERENCE = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)

DUPLICATE_ID_MESSAGE = "does not generate unique IDs"
# The spec values, independent of the constants they are checked against.
GRACE = timedelta(hours=24)
CHECK_INTERVAL = timedelta(minutes=5)


def _cert(host: str, days: int, *, port: int = 443) -> CertInfo:
    """Return a successful probe result for ``host`` with ``days`` left."""
    return CertInfo(
        host=host,
        port=port,
        not_after=REFERENCE + timedelta(days=days),
        days_until_expiry=days,
        subject=f"CN={host}",
        issuer="CN=Test CA",
        san=(host,),
        fetched_at=REFERENCE,
    )


@pytest.fixture
def cert_probe_ok() -> Iterator[AsyncMock]:
    """Answer every TLS probe with a certificate that expires in 30 days."""

    async def _ok(host: str, port: int, **_kwargs: Any) -> CertInfo:
        return _cert(host, 30, port=port)

    with patch(
        "custom_components.traefik_proxy.cert_coordinator.fetch_cert_info_async",
        AsyncMock(side_effect=_ok),
    ) as probe:
        yield probe


async def _setup(hass: HomeAssistant, aioclient_mock: Any) -> MockConfigEntry:
    """Set up one entry served by the v3.7 capture and return it loaded."""
    stub_traefik(aioclient_mock, version="v3.7")
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
    return entry


def _expiring(hass: HomeAssistant, entry: MockConfigEntry, host: str = HOST) -> str:
    """Return the entity_id of the expiring binary sensor of ``host``."""
    return entity_id_for(hass, CERT_EXPIRING.domain, CERT_EXPIRING.unique_id(entry.entry_id, host))


def _expiry(hass: HomeAssistant, entry: MockConfigEntry, host: str = HOST) -> str:
    """Return the entity_id of the expiry timestamp sensor of ``host``."""
    return entity_id_for(hass, CERT_EXPIRY.domain, CERT_EXPIRY.unique_id(entry.entry_id, host))


def _all_cert_ids(hass: HomeAssistant, entry: MockConfigEntry) -> tuple[str, ...]:
    """Return the four cert entity_ids of the v3.7 capture."""
    return (
        _expiring(hass, entry),
        _expiry(hass, entry),
        _expiring(hass, entry, OTHER_HOST),
        _expiry(hass, entry, OTHER_HOST),
    )


def _state(hass: HomeAssistant, entity_id: str) -> Any:
    """Return the state object of ``entity_id``; fail when it does not exist."""
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    return state


async def test_cert_cycle_updates_expiring_binary_sensor_state(
    hass: HomeAssistant, aioclient_mock: Any, cert_probe_ok: AsyncMock
) -> None:
    """A cert cycle inside the warning window turns only that host's alarm on."""
    entry = await _setup(hass, aioclient_mock)
    cert_coordinator = entry.runtime_data.cert_coordinator
    expiring = _expiring(hass, entry)
    other_expiring = _expiring(hass, entry, OTHER_HOST)

    state = _state(hass, expiring)
    assert state.state == "off"
    assert state.attributes["days_until_expiry"] == 30

    cert_coordinator.async_set_updated_data({HOST: _cert(HOST, 3), OTHER_HOST: _cert(OTHER_HOST, 30)})
    await hass.async_block_till_done()

    state = _state(hass, expiring)
    assert state.state == "on"
    assert state.attributes["days_until_expiry"] == 3
    other = _state(hass, other_expiring)
    assert other.state == "off"
    assert other.attributes["days_until_expiry"] == 30

    # An unchanged main cycle must not bring the old value back.
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    state = _state(hass, expiring)
    assert state.state == "on"
    assert state.attributes["days_until_expiry"] == 3


async def test_cert_cycle_updates_timestamp_sensor_state(
    hass: HomeAssistant, aioclient_mock: Any, cert_probe_ok: AsyncMock
) -> None:
    """A cert cycle with a new notAfter reaches the timestamp sensor's state."""
    entry = await _setup(hass, aioclient_mock)
    expiry = _expiry(hass, entry)
    other_expiry = _expiry(hass, entry, OTHER_HOST)
    assert dt_util.parse_datetime(_state(hass, expiry).state) == REFERENCE + timedelta(days=30)

    renewed = _cert(HOST, 3)
    entry.runtime_data.cert_coordinator.async_set_updated_data({HOST: renewed, OTHER_HOST: _cert(OTHER_HOST, 30)})
    await hass.async_block_till_done()

    state = _state(hass, expiry)
    assert dt_util.parse_datetime(state.state) == renewed.not_after
    # The entity layer adds no rounding: the attribute is the cache integer.
    assert state.attributes["days_until_expiry"] == 3
    other = _state(hass, other_expiry)
    assert dt_util.parse_datetime(other.state) == REFERENCE + timedelta(days=30)


async def test_threshold_change_reaches_state_at_the_boundary(
    hass: HomeAssistant, aioclient_mock: Any, cert_probe_ok: AsyncMock
) -> None:
    """Signed ``<=``: on at days == threshold, off one below, on one above."""
    entry = await _setup(hass, aioclient_mock)
    cert_coordinator = entry.runtime_data.cert_coordinator
    expiring = _expiring(hass, entry)
    state = _state(hass, expiring)
    assert state.state == "off"
    assert state.attributes["threshold_days"] == 14

    for threshold, expected in ((30, "on"), (29, "off"), (31, "on")):
        await cert_coordinator.async_set_threshold(threshold)
        await hass.async_block_till_done()
        state = _state(hass, expiring)
        assert state.state == expected, threshold
        assert state.attributes["threshold_days"] == threshold
        assert state.attributes["days_until_expiry"] == 30


async def test_tls_warn_days_option_reaches_state(
    hass: HomeAssistant, aioclient_mock: Any, cert_probe_ok: AsyncMock
) -> None:
    """Changing ``tls_warn_days`` in the options turns the alarm on."""
    entry = await _setup(hass, aioclient_mock)
    expiring = _expiring(hass, entry)
    assert _state(hass, expiring).state == "off"

    hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_TLS_WARN_DAYS: 30})
    await hass.async_block_till_done()

    state = _state(hass, expiring)
    assert state.state == "on"
    assert state.attributes["threshold_days"] == 30


async def test_cert_availability_follows_cert_coordinator_only(
    hass: HomeAssistant, aioclient_mock: Any, cert_probe_ok: AsyncMock
) -> None:
    """A Traefik API failure never blanks a cert entity; a cert failure does."""
    entry = await _setup(hass, aioclient_mock)
    cert_coordinator = entry.runtime_data.cert_coordinator
    expiring, expiry, other_expiring, other_expiry = _all_cert_ids(hass, entry)
    before = {eid: _state(hass, eid).state for eid in (expiring, expiry, other_expiring, other_expiry)}
    assert "unavailable" not in before.values()
    router = entity_id_for(hass, "sensor", ROUTERS.unique_id(entry.entry_id, "secure@file"))
    assert _state(hass, router).state == "enabled"

    # Main cycle fails: router entity goes unavailable, cert entities stay as they were.
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{MOCK_URL}/api/rawdata", status=500)
    stub_traefik(aioclient_mock)
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert not entry.runtime_data.coordinator.last_update_success
    assert _state(hass, router).state == "unavailable"
    assert {eid: _state(hass, eid).state for eid in before} == before

    # Cert cycle fails: every cert entity goes unavailable.
    cert_coordinator.async_set_update_error(UpdateFailed("cert cycle failed"))
    await hass.async_block_till_done()
    for eid in before:
        assert _state(hass, eid).state == "unavailable", eid

    # Next successful cert cycle brings them back.
    cert_coordinator.async_set_updated_data({HOST: _cert(HOST, 30), OTHER_HOST: _cert(OTHER_HOST, 30)})
    await hass.async_block_till_done()
    assert {eid: _state(hass, eid).state for eid in before} == before

    # A CertError row makes only that host's entities unavailable.
    error: CertError = {"host": HOST, "port": 443, "error": "timeout", "detail": "test stub"}
    cert_coordinator.async_set_updated_data({HOST: error, OTHER_HOST: _cert(OTHER_HOST, 30)})
    await hass.async_block_till_done()
    assert _state(hass, expiring).state == "unavailable"
    assert _state(hass, expiry).state == "unavailable"
    assert _state(hass, other_expiring).state == before[other_expiring]
    assert _state(hass, other_expiry).state == before[other_expiry]


async def test_main_cycles_never_probe_certificates(
    hass: HomeAssistant, aioclient_mock: Any, cert_probe_ok: AsyncMock
) -> None:
    """Main cycles, also with a changed snapshot and a new TLS host, never probe."""
    entry = await _setup(hass, aioclient_mock)
    coordinator = entry.runtime_data.coordinator
    probes_after_setup = cert_probe_ok.call_count
    assert probes_after_setup == 2

    await coordinator.async_refresh()
    await coordinator.async_refresh()
    rawdata = copy.deepcopy(load_fixture("v3.7", "rawdata.json"))
    extra = copy.deepcopy(rawdata["routers"]["secure@file"])
    extra["rule"] = "Host(`extra.example.com`)"
    extra["tls"] = {}
    rawdata["routers"]["extra@file"] = extra
    aioclient_mock.clear_requests()
    stub_traefik(aioclient_mock, rawdata=rawdata)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert "extra@file" in coordinator.data.routers
    assert cert_probe_ok.call_count == probes_after_setup


async def test_cert_notifications_do_not_grow_listeners(
    hass: HomeAssistant, aioclient_mock: Any, cert_probe_ok: AsyncMock
) -> None:
    """Rejected duplicate cert entities never subscribe to the cert coordinator."""
    entry = await _setup(hass, aioclient_mock)
    cert_coordinator = entry.runtime_data.cert_coordinator
    # Two kind listeners plus one per cert entity (two hosts, two classes).
    listeners_after_setup = len(cert_coordinator._listeners)
    assert listeners_after_setup == 6

    for days in (20, 10, 5):
        cert_coordinator.async_set_updated_data({HOST: _cert(HOST, days), OTHER_HOST: _cert(OTHER_HOST, days)})
        await hass.async_block_till_done()
    await cert_coordinator.async_set_threshold(7)
    await hass.async_block_till_done()

    assert len(cert_coordinator._listeners) == listeners_after_setup


async def test_known_cert_hosts_are_never_added_again(
    hass: HomeAssistant, aioclient_mock: Any, cert_probe_ok: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    """Cert cycles, a threshold change and an options change add no entity a second time."""
    entry = await _setup(hass, aioclient_mock)
    cert_coordinator = entry.runtime_data.cert_coordinator
    assert len(cert_coordinator._listeners) == 6

    for days in (20, 10, 5):
        cert_coordinator.async_set_updated_data({HOST: _cert(HOST, days), OTHER_HOST: _cert(OTHER_HOST, days)})
        await hass.async_block_till_done()
    await cert_coordinator.async_set_threshold(7)
    await hass.async_block_till_done()
    hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_TLS_WARN_DAYS: 30})
    await hass.async_block_till_done()

    assert DUPLICATE_ID_MESSAGE not in caplog.text
    assert len(cert_coordinator._listeners) == 6
    assert _state(hass, _expiring(hass, entry)).state == "on"


async def test_vanished_cert_host_unavailable_then_removed_after_grace(
    hass: HomeAssistant, aioclient_mock: Any, cert_probe_ok: AsyncMock, freezer: Any
) -> None:
    """A host that leaves the cert data is unavailable but registered until the grace period ends."""
    entry = await _setup(hass, aioclient_mock)
    registry = er.async_get(hass)
    other_expiring = _expiring(hass, entry, OTHER_HOST)
    other_expiry = _expiry(hass, entry, OTHER_HOST)

    rawdata = rawdata_copy()
    rawdata["routers"]["secure@file"]["tls"]["domains"][0]["sans"] = []
    restub_traefik(aioclient_mock, rawdata=rawdata)
    await entry.runtime_data.coordinator.async_refresh()
    await entry.runtime_data.cert_coordinator.async_refresh()
    await hass.async_block_till_done()
    assert OTHER_HOST not in entry.runtime_data.cert_coordinator.data

    for entity_id in (other_expiring, other_expiry):
        assert _state(hass, entity_id).state == "unavailable", entity_id
        assert registry.async_get(entity_id) is not None, entity_id
    # The remaining host is untouched.
    assert _state(hass, _expiring(hass, entry)).state == "off"

    freezer.tick(GRACE - timedelta(seconds=1))
    async_fire_time_changed(hass, dt_util.utcnow() + CHECK_INTERVAL)
    await hass.async_block_till_done()
    for entity_id in (other_expiring, other_expiry):
        assert registry.async_get(entity_id) is not None, entity_id

    freezer.tick(timedelta(seconds=2))
    async_fire_time_changed(hass, dt_util.utcnow() + CHECK_INTERVAL)
    await hass.async_block_till_done()
    for entity_id in (other_expiring, other_expiry):
        assert registry.async_get(entity_id) is None, entity_id
        assert hass.states.get(entity_id) is None, entity_id
    assert registry.async_get(_expiring(hass, entry)) is not None


async def test_unchanged_cert_notification_writes_nothing(
    hass: HomeAssistant, aioclient_mock: Any, cert_probe_ok: AsyncMock, freezer: Any
) -> None:
    """A cert notification with unchanged data keeps last_reported of every cert entity."""
    entry = await _setup(hass, aioclient_mock)
    cert_coordinator = entry.runtime_data.cert_coordinator
    entity_ids = _all_cert_ids(hass, entry)
    before = {entity_id: _state(hass, entity_id).last_reported for entity_id in entity_ids}

    freezer.tick(timedelta(seconds=1))
    cert_coordinator.async_set_updated_data(dict(cert_coordinator.data))
    await hass.async_block_till_done()

    for entity_id in entity_ids:
        assert _state(hass, entity_id).last_reported == before[entity_id], entity_id


async def test_cert_entities_on_certificates_sub_device(
    hass: HomeAssistant, aioclient_mock: Any, cert_probe_ok: AsyncMock
) -> None:
    """Cert entities sit on the Certificates sub-device, linked to the main device with the Traefik version."""
    entry = await _setup(hass, aioclient_mock)
    # Lookup by config entry works on HA 2026.3 and on releases that deprecate async_get_device.
    devices = {
        identifier: device
        for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
        for identifier in device.identifiers
    }
    main = devices[(DOMAIN, entry.entry_id)]
    certificates = devices[(DOMAIN, f"{entry.entry_id}_certificates")]
    assert certificates.via_device_id == main.id
    assert main.sw_version == entry.runtime_data.coordinator.data.version.version
    assert main.sw_version

    registry = er.async_get(hass)
    for entity_id in _all_cert_ids(hass, entry):
        reg_entry = registry.async_get(entity_id)
        assert reg_entry is not None
        assert reg_entry.device_id == certificates.id, entity_id
    assert {registry.async_get(entity_id).unique_id for entity_id in _all_cert_ids(hass, entry)} == {  # type: ignore[union-attr]
        f"{entry.entry_id}_tls_expiring_{HOST}",
        f"{entry.entry_id}_tls_cert_{HOST}",
        f"{entry.entry_id}_tls_expiring_{OTHER_HOST}",
        f"{entry.entry_id}_tls_cert_{OTHER_HOST}",
    }
