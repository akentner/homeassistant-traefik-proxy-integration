"""HA-state propagation and lifecycle of the TLS certificate entities after a full setup.

The cert entities must follow the cert coordinator: a cert cycle, a
threshold change and a ``tls_warn_days`` options change reach
``hass.states`` without any change of the main Traefik snapshot. The main
coordinator keeps ``always_update=False``, so these tests fail whenever a
cert entity only listens to the main coordinator.

The entry's entity manager adds each certificate host once, keeps a host
that leaves the cert data registered (unavailable) for the grace period and
the entities write their state only when it changed. A failed probe never
makes a cert entity unavailable.

Most setups use the v2.11 capture (certificates come from the probe) with
the clock frozen at ``REFERENCE``. The API-source tests use the v3.7
capture: the fixed capture dates only through ``frozen_v37_certificates``,
otherwise the clock-rebased default stub.
"""

from __future__ import annotations

import copy
import dataclasses
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.x509.verification import Store
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.traefik_proxy.cert_coordinator import HostCertState
from custom_components.traefik_proxy.const import (
    CONF_API_KEY,
    CONF_TLS_WARN_DAYS,
    CONF_URL,
    CONF_VERIFY_SSL,
    DOMAIN,
    TLS_HANDSHAKE_TIMEOUT,
)
from custom_components.traefik_proxy.entity_manager import CERT_EXPIRING, CERT_EXPIRY, ROUTERS
from custom_components.traefik_proxy.models import TraefikCertificate
from custom_components.traefik_proxy.tls import ProbedCertificate, ProbeError, ProbeFailure
from tests.conftest import (
    CERT_FIXTURE_NOW,
    MOCK_URL,
    entity_id_for,
    frozen_v37_certificates,
    load_fixture,
    make_cert_state,
    rawdata_copy,
    restub_traefik,
    stub_traefik,
)

# The probe-driven capture: Traefik < 3.7 has no /api/certificates.
VERSION = "v2.11"
# TLS hosts of the capture (tls.domains and Host(...) rules).
HOST = "secure.example.com"
OTHER_HOST = "www.secure.example.com"
CONNECT_HOST = "traefik.example.com"

# Fixed reference instant so not_after values are deterministic.
REFERENCE = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
PROBE_TARGET = "custom_components.traefik_proxy.cert_coordinator.async_probe_certificate"
SECRET_TOKEN = "secret-token-6f1e"

DUPLICATE_ID_MESSAGE = "does not generate unique IDs"
# The spec values, independent of the constants they are checked against.
GRACE = timedelta(hours=24)
CHECK_INTERVAL = timedelta(minutes=5)


def _cert(host: str, days: int) -> HostCertState:
    """Return a probe state for ``host`` whose certificate has ``days`` left at ``REFERENCE``."""
    return make_cert_state(host, days=days, now=REFERENCE, verified=True)


def _probed(sni: str, days: float = 30) -> ProbedCertificate:
    """Return a verified probe result for ``sni`` expiring ``days`` after ``REFERENCE``."""
    return ProbedCertificate(
        certificate=TraefikCertificate(
            common_name=sni,
            sans=(sni,),
            not_after=REFERENCE + timedelta(days=days),
            not_before=REFERENCE - timedelta(days=60),
            issuer_cn="Test CA",
            status=None,
            serial_number="1",
        ),
        verified=True,
        san_mismatch=False,
    )


@pytest.fixture
def cert_probe_ok(freezer: Any) -> Iterator[AsyncMock]:
    """Freeze the clock at ``REFERENCE`` and answer every probe with a certificate for 30 days."""
    freezer.move_to(REFERENCE)

    async def _ok(_connect_host: str, _port: int, sni: str, **_kwargs: Any) -> ProbedCertificate:
        return _probed(sni)

    with patch(PROBE_TARGET, AsyncMock(side_effect=_ok)) as probe:
        yield probe


async def _setup(hass: HomeAssistant, aioclient_mock: Any, *, api_key: str = "k") -> MockConfigEntry:
    """Set up one entry served by the v2.11 capture and return it loaded."""
    stub_traefik(aioclient_mock, version=VERSION)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Traefik",
        data={CONF_URL: MOCK_URL, CONF_API_KEY: api_key, CONF_VERIFY_SSL: True},
        unique_id="traefik.example.com",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    # The first cert cycle runs as a background task of the entry.
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.state is ConfigEntryState.LOADED
    return entry


def _expiring(hass: HomeAssistant, entry: MockConfigEntry, host: str = HOST) -> str:
    """Return the entity_id of the expiring binary sensor of ``host``."""
    return entity_id_for(hass, CERT_EXPIRING.domain, CERT_EXPIRING.unique_id(entry.entry_id, host))


def _expiry(hass: HomeAssistant, entry: MockConfigEntry, host: str = HOST) -> str:
    """Return the entity_id of the expiry timestamp sensor of ``host``."""
    return entity_id_for(hass, CERT_EXPIRY.domain, CERT_EXPIRY.unique_id(entry.entry_id, host))


def _all_cert_ids(hass: HomeAssistant, entry: MockConfigEntry) -> tuple[str, ...]:
    """Return the four cert entity_ids of the capture."""
    return (
        _expiring(hass, entry),
        _expiry(hass, entry),
        _expiring(hass, entry, OTHER_HOST),
        _expiry(hass, entry, OTHER_HOST),
    )


def _certificates_problem(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    """Return the entity_id of the certificates_problem aggregate."""
    return entity_id_for(hass, "binary_sensor", f"{entry.entry_id}_certificates_problem")


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
    assert renewed.certificate is not None
    assert dt_util.parse_datetime(state.state) == renewed.certificate.not_after
    # Days are computed from the frozen clock at read time.
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
    """A Traefik API failure or a failed probe never blanks a cert entity; a failed cert cycle does."""
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
    stub_traefik(aioclient_mock, version=VERSION)
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

    # A failed probe without a certificate keeps that host's entities available (unknown).
    failed = make_cert_state(HOST, now=REFERENCE, error="timeout", failures=1)
    cert_coordinator.async_set_updated_data({HOST: failed, OTHER_HOST: _cert(OTHER_HOST, 30)})
    await hass.async_block_till_done()
    assert _state(hass, expiring).state == "unknown"
    assert _state(hass, expiry).state == "unknown"
    assert _state(hass, expiry).attributes["last_error"] == "timeout"
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
    rawdata = copy.deepcopy(load_fixture(VERSION, "rawdata.json"))
    extra = copy.deepcopy(rawdata["routers"]["secure@file"])
    extra["rule"] = "Host(`extra.example.com`)"
    extra["tls"] = {}
    rawdata["routers"]["extra@file"] = extra
    aioclient_mock.clear_requests()
    stub_traefik(aioclient_mock, version=VERSION, rawdata=rawdata)
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
    # 2 kind listeners + 4 certificate entities (two hosts, two classes) + the aggregate.
    listeners_after_setup = len(cert_coordinator._listeners)
    assert listeners_after_setup == 7

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
    # 2 kind listeners + 4 certificate entities + the aggregate.
    assert len(cert_coordinator._listeners) == 7

    for days in (20, 10, 5):
        cert_coordinator.async_set_updated_data({HOST: _cert(HOST, days), OTHER_HOST: _cert(OTHER_HOST, days)})
        await hass.async_block_till_done()
    await cert_coordinator.async_set_threshold(7)
    await hass.async_block_till_done()
    hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_TLS_WARN_DAYS: 30})
    await hass.async_block_till_done()

    assert DUPLICATE_ID_MESSAGE not in caplog.text
    assert len(cert_coordinator._listeners) == 7
    assert _state(hass, _expiring(hass, entry)).state == "on"


async def test_vanished_cert_host_unavailable_then_removed_after_grace(
    hass: HomeAssistant, aioclient_mock: Any, cert_probe_ok: AsyncMock, freezer: Any
) -> None:
    """A host that leaves the cert data is unavailable but registered until the grace period ends."""
    entry = await _setup(hass, aioclient_mock)
    registry = er.async_get(hass)
    other_expiring = _expiring(hass, entry, OTHER_HOST)
    other_expiry = _expiry(hass, entry, OTHER_HOST)

    rawdata = rawdata_copy(VERSION)
    rawdata["routers"]["secure@file"]["tls"]["domains"][0]["sans"] = []
    restub_traefik(aioclient_mock, version=VERSION, rawdata=rawdata)
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
    """A cert notification with unchanged data keeps last_reported of every cert entity, the aggregate included."""
    entry = await _setup(hass, aioclient_mock)
    cert_coordinator = entry.runtime_data.cert_coordinator
    entity_ids = (*_all_cert_ids(hass, entry), _certificates_problem(hass, entry))
    # Certificates half a day off the day boundary, so one second changes no day count.
    half_day = {
        host: dataclasses.replace(_cert(host, 30), certificate=_probed(host, 30.5).certificate)
        for host in (HOST, OTHER_HOST)
    }
    cert_coordinator.async_set_updated_data(half_day)
    await hass.async_block_till_done()
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
    # Look devices up by config entry and index them by identifier.
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


async def test_probe_driven_setup_publishes_probe_state(
    hass: HomeAssistant, aioclient_mock: Any, cert_probe_ok: AsyncMock
) -> None:
    """Each cert cycle probes both hosts at the Traefik host; the entities show the probed certificate."""
    entry = await _setup(hass, aioclient_mock)
    assert cert_probe_ok.await_count == 2
    expected_calls = {(CONNECT_HOST, 443, HOST), (CONNECT_HOST, 443, OTHER_HOST)}
    assert {call.args for call in cert_probe_ok.await_args_list} == expected_calls
    for call in cert_probe_ok.await_args_list:
        assert call.kwargs["handshake_timeout"] == TLS_HANDSHAKE_TIMEOUT
        assert call.kwargs["now"] == REFERENCE
        # The default trust store holds Home Assistant's roots.
        assert isinstance(call.kwargs["trust_store"], Store)

    expiry = _state(hass, _expiry(hass, entry))
    assert dt_util.parse_datetime(expiry.state) == REFERENCE + timedelta(days=30)
    assert expiry.attributes["source"] == "probe"
    assert expiry.attributes["verified"] is True
    assert expiry.attributes["subject"] == HOST
    assert expiry.attributes["issuer"] == "Test CA"
    assert expiry.attributes["port"] == 443
    assert expiry.attributes["fetched_at"] == REFERENCE.isoformat()
    assert expiry.attributes["last_error"] is None
    expiring = _state(hass, _expiring(hass, entry))
    assert expiring.state == "off"
    assert expiring.attributes["reason"] is None
    assert expiring.attributes["source"] == "probe"

    await entry.runtime_data.cert_coordinator.async_refresh()
    await hass.async_block_till_done()
    assert cert_probe_ok.await_count == 4
    assert {call.args for call in cert_probe_ok.await_args_list[2:]} == expected_calls


async def test_failing_probe_keeps_cert_entities_available(
    hass: HomeAssistant, aioclient_mock: Any, mock_tls_probe: AsyncMock
) -> None:
    """A probe that fails from the start shows unknown values on available entities."""
    entry = await _setup(hass, aioclient_mock)
    assert entry.runtime_data.cert_coordinator.last_update_success
    for host in (HOST, OTHER_HOST):
        expiry = _state(hass, _expiry(hass, entry, host))
        assert expiry.state == "unknown"
        assert expiry.attributes["last_error"] == "unknown"
        assert expiry.attributes["days_until_expiry"] is None
        expiring = _state(hass, _expiring(hass, entry, host))
        assert expiring.state == "unknown"
        assert expiring.attributes["reason"] is None
        assert expiring.attributes["last_error"] == "unknown"


async def test_secret_token_never_in_cert_attributes_or_log(
    hass: HomeAssistant, aioclient_mock: Any, mock_tls_probe: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    """The API token appears in no cert attribute value and no DEBUG log line of setup plus two cert cycles."""
    caplog.set_level(logging.DEBUG)
    entry = await _setup(hass, aioclient_mock, api_key=SECRET_TOKEN)
    cert_coordinator = entry.runtime_data.cert_coordinator
    for _ in range(2):
        await cert_coordinator.async_refresh()
        await hass.async_block_till_done()
    # Setup plus two cert cycles, one probe per host each.
    assert mock_tls_probe.await_count == 3 * 2

    for entity_id in _all_cert_ids(hass, entry):
        state = _state(hass, entity_id)
        for value in state.attributes.values():
            assert SECRET_TOKEN not in str(value), entity_id
    assert "probe disabled in tests" in caplog.text
    assert SECRET_TOKEN not in caplog.text


async def test_update_entity_action_refreshes_cert_coordinator(
    hass: HomeAssistant, aioclient_mock: Any, cert_probe_ok: AsyncMock
) -> None:
    """``homeassistant.update_entity`` on a certificate_expiry entity requests one cert refresh."""
    assert await async_setup_component(hass, "homeassistant", {})
    entry = await _setup(hass, aioclient_mock)
    cert_coordinator = entry.runtime_data.cert_coordinator
    with patch.object(cert_coordinator, "async_request_refresh", AsyncMock()) as refresh:
        await hass.services.async_call(
            "homeassistant", "update_entity", {"entity_id": _expiry(hass, entry)}, blocking=True
        )
    refresh.assert_awaited_once()


async def test_probe_failed_after_two_failed_refreshes(
    hass: HomeAssistant, aioclient_mock: Any, cert_probe_ok: AsyncMock
) -> None:
    """One failed probe keeps the alarm off; the second turns it on with reason probe_failed."""
    entry = await _setup(hass, aioclient_mock)
    cert_coordinator = entry.runtime_data.cert_coordinator
    expiry = _expiry(hass, entry)
    expiring = _expiring(hass, entry)
    not_after = _state(hass, expiry).state
    assert dt_util.parse_datetime(not_after) == REFERENCE + timedelta(days=30)
    assert _state(hass, expiring).state == "off"

    cert_probe_ok.side_effect = None
    cert_probe_ok.return_value = ProbeFailure(ProbeError.TIMEOUT, "TimeoutError: ")
    await cert_coordinator.async_refresh()
    await hass.async_block_till_done()
    state = _state(hass, expiring)
    assert state.state == "off"
    assert state.attributes["reason"] is None
    assert state.attributes["last_error"] == "timeout"
    assert _state(hass, expiry).state == not_after

    cert_probe_ok.return_value = ProbeFailure(ProbeError.SSL, "SSLError: ")
    await cert_coordinator.async_refresh()
    await hass.async_block_till_done()
    state = _state(hass, expiring)
    assert state.state == "on"
    assert state.attributes["reason"] == "probe_failed"
    assert state.attributes["last_error"] == "ssl"
    timestamp = _state(hass, expiry)
    assert timestamp.state == not_after
    assert timestamp.attributes["last_error"] == "ssl"
    assert timestamp.attributes["days_until_expiry"] == 30


# ---------------------------------------------------------------------------
# API source (Traefik >= 3.7)
# ---------------------------------------------------------------------------

API_NOT_AFTER = datetime(2027, 2, 12, 0, 17, 40, tzinfo=UTC)


async def _setup_v37(hass: HomeAssistant, aioclient_mock: Any, **stub_kwargs: Any) -> MockConfigEntry:
    """Set up one entry served by the v3.7 capture (``stub_kwargs`` go to ``stub_traefik``)."""
    stub_traefik(aioclient_mock, version="v3.7", **stub_kwargs)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Traefik",
        data={CONF_URL: MOCK_URL, CONF_API_KEY: "k", CONF_VERIFY_SSL: True},
        unique_id="traefik.example.com",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    # The first cert cycle runs as a background task of the entry.
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.state is ConfigEntryState.LOADED
    return entry


def _certificates_requests(aioclient_mock: Any) -> int:
    """Return how often /api/certificates was requested."""
    return sum(1 for call in aioclient_mock.mock_calls if call[1].path == "/api/certificates")


async def test_v37_api_setup_publishes_api_state_without_probing(
    hass: HomeAssistant, aioclient_mock: Any, mock_tls_probe: AsyncMock, freezer: Any
) -> None:
    """Traefik 3.7: both hosts show the API certificate; no probe in setup and two further cycles."""
    entry = await _setup_v37(hass, aioclient_mock, certificates=frozen_v37_certificates(freezer))
    for host in (HOST, OTHER_HOST):
        expiry = _state(hass, _expiry(hass, entry, host))
        assert dt_util.parse_datetime(expiry.state) == API_NOT_AFTER
        assert expiry.attributes["source"] == "api"
        assert expiry.attributes["verified"] is None
        assert expiry.attributes["port"] is None
        assert expiry.attributes["days_until_expiry"] == 88
        expiring = _state(hass, _expiring(hass, entry, host))
        assert expiring.state == "off"
        assert expiring.attributes["reason"] is None
    cert_coordinator = entry.runtime_data.cert_coordinator
    for _ in range(2):
        await cert_coordinator.async_refresh()
        await hass.async_block_till_done()
    assert cert_coordinator.last_update_success
    assert mock_tls_probe.call_count == 0


async def test_v37_api_uncovered_host_is_not_found_right_away(
    hass: HomeAssistant, aioclient_mock: Any, mock_tls_probe: AsyncMock, freezer: Any
) -> None:
    """A TLS host without an API certificate: expiring on (not_found), timestamp unknown but available, no probe."""
    rawdata = rawdata_copy("v3.7")
    extra = copy.deepcopy(rawdata["routers"]["secure@file"])
    extra["rule"] = "Host(`extra.example.com`)"
    extra["tls"] = {}
    rawdata["routers"]["extra@file"] = extra
    entry = await _setup_v37(hass, aioclient_mock, rawdata=rawdata, certificates=frozen_v37_certificates(freezer))

    expiring = _state(hass, _expiring(hass, entry, "extra.example.com"))
    assert expiring.state == "on"
    assert expiring.attributes["reason"] == "not_found"
    assert expiring.attributes["source"] == "api"
    expiry = _state(hass, _expiry(hass, entry, "extra.example.com"))
    assert expiry.state == "unknown"
    assert expiry.attributes["last_error"] == "not_found"
    assert _state(hass, _expiring(hass, entry)).state == "off"
    assert mock_tls_probe.call_count == 0


async def test_v37_api_status_field_never_changes_the_state(
    hass: HomeAssistant, aioclient_mock: Any, mock_tls_probe: AsyncMock, freezer: Any
) -> None:
    """An API certificate with status 'expired' but 400 days left keeps the alarm off."""
    (certificate,) = copy.deepcopy(frozen_v37_certificates(freezer))
    certificate["status"] = "expired"
    certificate["notAfter"] = (CERT_FIXTURE_NOW + timedelta(days=400)).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = await _setup_v37(hass, aioclient_mock, certificates=[certificate])

    for host in (HOST, OTHER_HOST):
        expiring = _state(hass, _expiring(hass, entry, host))
        assert expiring.state == "off"
        assert expiring.attributes["reason"] is None
        assert expiring.attributes["days_until_expiry"] == 400


@pytest.mark.parametrize(
    "instant",
    [datetime(2027, 1, 30, 12, 0, tzinfo=UTC), datetime(2027, 2, 13, 12, 0, tzinfo=UTC)],
    ids=["after_threshold_crossing", "after_expiry"],
)
async def test_default_v37_setup_is_clock_independent(
    hass: HomeAssistant, aioclient_mock: Any, mock_tls_probe: AsyncMock, freezer: Any, instant: datetime
) -> None:
    """The default v3.7 stub re-bases the capture on the clock: no state depends on the real date."""
    freezer.move_to(instant)
    entry = await _setup_v37(hass, aioclient_mock)
    for host in (HOST, OTHER_HOST):
        expiry = _state(hass, _expiry(hass, entry, host))
        assert expiry.attributes["source"] == "api"
        assert expiry.attributes["days_until_expiry"] >= 3649
        expiring = _state(hass, _expiring(hass, entry, host))
        assert expiring.state == "off"
        assert expiring.attributes["reason"] is None
    aggregate = _state(hass, _certificates_problem(hass, entry))
    assert aggregate.state == "off"
    assert aggregate.attributes["problems"] == []
    assert aggregate.attributes["problem_count"] == 0
    assert aggregate.attributes["reasons"] == {}
    assert mock_tls_probe.call_count == 0


@pytest.mark.parametrize("status", [500, 401], ids=["non_404", "unauthorized"])
async def test_v37_certificates_error_fails_the_cert_cycle(
    hass: HomeAssistant, aioclient_mock: Any, mock_tls_probe: AsyncMock, status: int
) -> None:
    """A non-404 answer of /api/certificates fails a later cert cycle: entities unavailable, no probe, no reauth."""
    entry = await _setup_v37(hass, aioclient_mock)
    cert_coordinator = entry.runtime_data.cert_coordinator
    assert cert_coordinator.last_update_success

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{MOCK_URL}/api/certificates", status=status)
    stub_traefik(aioclient_mock, version="v3.7")
    await cert_coordinator.async_refresh()
    await hass.async_block_till_done()

    assert not cert_coordinator.last_update_success
    for entity_id in _all_cert_ids(hass, entry):
        assert _state(hass, entity_id).state == "unavailable", entity_id
    assert mock_tls_probe.call_count == 0
    assert not [flow for flow in hass.config_entries.flow.async_progress() if flow["context"]["source"] == "reauth"]
    assert entry.state is ConfigEntryState.LOADED


async def test_v211_certificates_404_probes_and_re_requests_each_cycle(
    hass: HomeAssistant, aioclient_mock: Any, mock_tls_probe: AsyncMock, freezer: Any
) -> None:
    """Traefik 2.11: /api/certificates answers 404, both hosts are probed; the next cycle asks the API again."""
    freezer.move_to(REFERENCE)
    entry = await _setup(hass, aioclient_mock)
    assert mock_tls_probe.call_count == 2
    assert _certificates_requests(aioclient_mock) == 1
    assert _state(hass, _expiry(hass, entry)).attributes["source"] == "probe"

    await entry.runtime_data.cert_coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _certificates_requests(aioclient_mock) == 2
    assert mock_tls_probe.call_count == 4
