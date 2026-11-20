"""Certificate state over time: the day-boundary timer of the cert coordinator.

Days until expiry are computed from the clock at read time, so a certificate
crosses the warning threshold, expires and counts down one day without any
new probe. The cert coordinator keeps one timer at the earliest moment a
host's whole-day count changes; when it fires the listeners re-evaluate and
write only the entities whose state changed.

A failed cert cycle is reported as it is: the first one does not block the
setup, leaves the cert entities unavailable instead of faking an empty
success, never marks registry-restored hosts missing and is retried after
5 minutes.

The timer setups run on the v2.11 capture (``/api/certificates`` answers
404, so certificates come from the probe) with the probe replaced by a stub
that returns a certificate per SNI name, and the clock frozen at ``T0``.
Clock moves stay below the 6 h cert interval after setup, so only the
day-boundary timer can explain a state change. The failure setups run on
the v3.7 capture with ``/api/certificates`` failing.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.traefik_proxy.cert_coordinator import CertCoordinator
from custom_components.traefik_proxy.const import DEFAULT_TLS_CERT_COOLDOWN, DOMAIN, UID_CERTIFICATES_PROBLEM
from custom_components.traefik_proxy.entity_manager import CERT_EXPIRING, CERT_EXPIRY
from custom_components.traefik_proxy.models import TraefikCertificate
from custom_components.traefik_proxy.tls import ProbedCertificate, ProbeError, ProbeFailure
from tests.conftest import (
    MOCK_URL,
    entity_id_for,
    make_cert_state,
    make_traefik_entry,
    rawdata_copy,
    restub_traefik,
    setup_traefik_entry,
    stub_traefik,
)

# TLS hosts of the v2.11 capture.
HOST = "secure.example.com"
OTHER_HOST = "www.secure.example.com"
T0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
SECOND = timedelta(seconds=1)
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
PROBE_TARGET = "custom_components.traefik_proxy.cert_coordinator.async_probe_certificate"
TRACK_TARGET = "custom_components.traefik_proxy.cert_coordinator.async_track_point_in_utc_time"
# The spec value, independent of the constant it is checked against.
RETRY = timedelta(seconds=300)


@dataclass
class CertStub:
    """Probe stub: ``not_after`` per SNI name; a name without an entry fails its probe."""

    probe: AsyncMock
    not_after: dict[str, datetime] = field(default_factory=dict)


@pytest.fixture
def certs(freezer: Any) -> Iterator[CertStub]:
    """Freeze the clock at ``T0`` and answer probes from ``CertStub.not_after``."""
    freezer.move_to(T0)
    stub = CertStub(probe=AsyncMock())

    async def _probe(_connect_host: str, _port: int, sni: str, **_kwargs: Any) -> ProbedCertificate | ProbeFailure:
        if sni not in stub.not_after:
            return ProbeFailure(ProbeError.UNKNOWN, "no certificate in this test")
        return ProbedCertificate(
            certificate=TraefikCertificate(
                common_name=sni,
                sans=(sni,),
                not_after=stub.not_after[sni],
                not_before=T0 - timedelta(days=60),
                issuer_cn="Test CA",
                status=None,
                serial_number="1",
            ),
            verified=True,
            san_mismatch=False,
        )

    stub.probe.side_effect = _probe
    with patch(PROBE_TARGET, stub.probe):
        yield stub


async def _setup(hass: HomeAssistant, aioclient_mock: Any) -> MockConfigEntry:
    """Set up one entry on the v2.11 capture (probe source) and return it loaded."""
    return await setup_traefik_entry(hass, aioclient_mock, version="v2.11")


async def _move_to(hass: HomeAssistant, freezer: Any, instant: datetime) -> None:
    """Move the frozen clock to ``instant`` and run every timer that is due."""
    freezer.move_to(instant)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


def _expiring(hass: HomeAssistant, entry: MockConfigEntry, host: str = HOST) -> Any:
    state = hass.states.get(entity_id_for(hass, CERT_EXPIRING.domain, CERT_EXPIRING.unique_id(entry.entry_id, host)))
    assert state is not None
    return state


def _expiry(hass: HomeAssistant, entry: MockConfigEntry, host: str = HOST) -> Any:
    state = hass.states.get(entity_id_for(hass, CERT_EXPIRY.domain, CERT_EXPIRY.unique_id(entry.entry_id, host)))
    assert state is not None
    return state


def _certificates_requests(aioclient_mock: Any) -> int:
    """Return how often /api/certificates was requested."""
    return sum(1 for call in aioclient_mock.mock_calls if call[1].path == "/api/certificates")


def _timer_pending(coordinator: CertCoordinator) -> bool:
    """Return whether the cert coordinator holds a pending day-boundary timer."""
    return getattr(coordinator, "_unsub_day_boundary", None) is not None


@pytest.mark.parametrize(
    ("not_after", "expected"),
    [
        (T0 + timedelta(days=10) + HOUR, T0 + HOUR + SECOND),
        (T0 + timedelta(days=10), T0 + SECOND),
        (T0 - 2 * HOUR, T0 + timedelta(hours=22) + SECOND),
    ],
    ids=["mid_day", "exact_day", "expired"],
)
def test_next_day_change(not_after: datetime, expected: datetime) -> None:
    """The next whole-day change is one second after the floor-day count drops; None without a certificate."""
    state = make_cert_state(HOST, days=0, now=T0)
    assert state.certificate is not None
    state = replace(state, certificate=replace(state.certificate, not_after=not_after))
    assert state.next_day_change(T0) == expected
    assert make_cert_state(HOST, now=T0).next_day_change(T0) is None


async def test_threshold_crossing_without_probe(
    hass: HomeAssistant, aioclient_mock: Any, certs: CertStub, freezer: Any
) -> None:
    """15 d + 1 h left: off at T0 and at N - 15 d, on (expiring, 14) one second later; no probe, no API call."""
    expires = T0 + timedelta(days=15) + HOUR
    certs.not_after = {HOST: expires, OTHER_HOST: T0 + timedelta(days=100, hours=3)}
    entry = await _setup(hass, aioclient_mock)
    probes, requests = certs.probe.call_count, _certificates_requests(aioclient_mock)

    state = _expiring(hass, entry)
    assert state.state == "off"
    assert state.attributes["days_until_expiry"] == 15

    await _move_to(hass, freezer, expires - timedelta(days=15))
    state = _expiring(hass, entry)
    assert state.state == "off"
    assert state.attributes["days_until_expiry"] == 15

    await _move_to(hass, freezer, expires - timedelta(days=15) + SECOND)
    state = _expiring(hass, entry)
    assert state.state == "on"
    assert state.attributes["reason"] == "expiring"
    assert state.attributes["days_until_expiry"] == 14
    assert certs.probe.call_count == probes
    assert _certificates_requests(aioclient_mock) == requests


async def test_expired_at_not_after_without_probe(
    hass: HomeAssistant, aioclient_mock: Any, certs: CertStub, freezer: Any
) -> None:
    """1 h left: on (expiring, 0) at T0 and at N, on (expired, -1) one second after N; no probe."""
    expires = T0 + HOUR
    certs.not_after = {HOST: expires, OTHER_HOST: T0 + timedelta(days=100, hours=3)}
    entry = await _setup(hass, aioclient_mock)
    probes, requests = certs.probe.call_count, _certificates_requests(aioclient_mock)

    for instant in (T0, expires):
        await _move_to(hass, freezer, instant)
        state = _expiring(hass, entry)
        assert state.state == "on"
        assert state.attributes["reason"] == "expiring"
        assert state.attributes["days_until_expiry"] == 0

    await _move_to(hass, freezer, expires + SECOND)
    state = _expiring(hass, entry)
    assert state.state == "on"
    assert state.attributes["reason"] == "expired"
    assert state.attributes["days_until_expiry"] == -1
    assert _expiry(hass, entry).attributes["days_until_expiry"] == -1
    assert certs.probe.call_count == probes
    assert _certificates_requests(aioclient_mock) == requests


async def test_daily_countdown_written_once_at_the_boundary(
    hass: HomeAssistant, aioclient_mock: Any, certs: CertStub, freezer: Any
) -> None:
    """30 d + 1 h left: days 30 until N - 30 d, 29 after it, written exactly at the boundary."""
    expires = T0 + timedelta(days=30) + HOUR
    certs.not_after = {HOST: expires, OTHER_HOST: T0 + timedelta(days=100, hours=3)}
    entry = await _setup(hass, aioclient_mock)
    probes = certs.probe.call_count
    before = _expiry(hass, entry)
    assert before.attributes["days_until_expiry"] == 30

    await _move_to(hass, freezer, expires - timedelta(days=30))
    unchanged = _expiry(hass, entry)
    assert unchanged.attributes["days_until_expiry"] == 30
    assert unchanged.last_reported == before.last_reported

    boundary = expires - timedelta(days=30) + SECOND
    await _move_to(hass, freezer, boundary)
    after = _expiry(hass, entry)
    assert after.attributes["days_until_expiry"] == 29
    assert after.last_updated == boundary
    assert after.last_reported == boundary
    assert dt_util.parse_datetime(after.state) == expires
    assert certs.probe.call_count == probes


async def test_boundary_writes_only_the_host_that_changed(
    hass: HomeAssistant, aioclient_mock: Any, certs: CertStub, freezer: Any
) -> None:
    """Boundaries one hour apart: the first fire writes host A only, the second host B."""
    certs.not_after = {HOST: T0 + timedelta(days=20) + HOUR, OTHER_HOST: T0 + timedelta(days=20) + 2 * HOUR}
    entry = await _setup(hass, aioclient_mock)
    other_before = {
        state.entity_id: state.last_reported
        for state in (_expiry(hass, entry, OTHER_HOST), _expiring(hass, entry, OTHER_HOST))
    }

    await _move_to(hass, freezer, T0 + HOUR + SECOND)
    assert _expiry(hass, entry).attributes["days_until_expiry"] == 19
    assert _expiring(hass, entry).attributes["days_until_expiry"] == 19
    for state in (_expiry(hass, entry, OTHER_HOST), _expiring(hass, entry, OTHER_HOST)):
        assert state.attributes["days_until_expiry"] == 20
        assert state.last_reported == other_before[state.entity_id], state.entity_id

    await _move_to(hass, freezer, T0 + 2 * HOUR + SECOND)
    assert _expiry(hass, entry, OTHER_HOST).attributes["days_until_expiry"] == 19
    assert _expiry(hass, entry, OTHER_HOST).last_reported == T0 + 2 * HOUR + SECOND


async def test_boundary_timer_is_replaced_on_every_cycle(
    hass: HomeAssistant, aioclient_mock: Any, certs: CertStub
) -> None:
    """Each successful cycle cancels the previous day-boundary timer before scheduling one."""
    certs.not_after = {HOST: T0 + timedelta(days=20) + HOUR, OTHER_HOST: T0 + timedelta(days=20) + 2 * HOUR}
    entry = await _setup(hass, aioclient_mock)
    cert_coordinator = entry.runtime_data.cert_coordinator
    unsubs: list[MagicMock] = []
    whens: list[datetime] = []

    def _track(hass: HomeAssistant, action: Any, when: datetime) -> MagicMock:
        unsub = MagicMock(wraps=async_track_point_in_utc_time(hass, action, when))
        unsubs.append(unsub)
        whens.append(when)
        return unsub

    with patch(TRACK_TARGET, side_effect=_track):
        for _ in range(2):
            await cert_coordinator.async_refresh()
            await hass.async_block_till_done()

    assert whens == [T0 + HOUR + SECOND] * 2
    unsubs[0].assert_called_once_with()
    unsubs[1].assert_not_called()
    assert _timer_pending(cert_coordinator)


async def test_no_timer_without_a_certificate(hass: HomeAssistant, aioclient_mock: Any, certs: CertStub) -> None:
    """Every probe fails, so no host has a certificate: no day-boundary timer is pending."""
    entry = await _setup(hass, aioclient_mock)
    cert_coordinator = entry.runtime_data.cert_coordinator
    assert cert_coordinator.last_update_success
    assert all(state.certificate is None for state in cert_coordinator.data.values())
    assert not _timer_pending(cert_coordinator)


async def test_unload_cancels_the_boundary_timer(hass: HomeAssistant, aioclient_mock: Any, certs: CertStub) -> None:
    """A pending day-boundary timer is cancelled when the entry unloads."""
    certs.not_after = {HOST: T0 + timedelta(days=20) + HOUR}
    entry = await _setup(hass, aioclient_mock)
    cert_coordinator = entry.runtime_data.cert_coordinator
    assert _timer_pending(cert_coordinator)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert not _timer_pending(cert_coordinator)


async def test_stopping_flag_blocks_the_boundary_timer_after_unload(
    hass: HomeAssistant, aioclient_mock: Any, certs: CertStub
) -> None:
    """The coordinator's own stop flag is set by unload; scheduling afterwards arms no timer."""
    certs.not_after = {HOST: T0 + timedelta(days=20) + HOUR}
    entry = await _setup(hass, aioclient_mock)
    cert_coordinator = entry.runtime_data.cert_coordinator
    assert getattr(cert_coordinator, "_stopping", None) is False
    states = dict(cert_coordinator.data)
    assert any(state.certificate is not None for state in states.values())

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert getattr(cert_coordinator, "_stopping", None) is True

    cert_coordinator._async_schedule_day_boundary(states)
    assert not _timer_pending(cert_coordinator)


async def _setup_failing_certificates(
    hass: HomeAssistant,
    aioclient_mock: Any,
    *,
    restored: tuple[str, ...] = (HOST, OTHER_HOST),
    exc: Exception | None = None,
) -> MockConfigEntry:
    """Set up a v3.7 entry whose /api/certificates fails (500, or ``exc``); assert it loaded.

    Registry entries of both cert kinds are created for every host in
    ``restored`` before the setup, as after a restart.
    """
    entry = make_traefik_entry()
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    for host in restored:
        for spec in (CERT_EXPIRY, CERT_EXPIRING):
            registry.async_get_or_create(spec.domain, DOMAIN, spec.unique_id(entry.entry_id, host), config_entry=entry)
    if exc is not None:
        aioclient_mock.get(f"{MOCK_URL}/api/certificates", exc=exc)
    else:
        aioclient_mock.get(f"{MOCK_URL}/api/certificates", status=500)
    stub_traefik(aioclient_mock, version="v3.7")
    assert await hass.config_entries.async_setup(entry.entry_id)
    # The first cert cycle runs as a background task of the entry.
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.state is ConfigEntryState.LOADED
    return entry


async def test_failed_first_cycle_keeps_restored_hosts_unavailable_not_missing(
    hass: HomeAssistant, aioclient_mock: Any, certs: CertStub
) -> None:
    """A failed first cert cycle stays failed; restored hosts are unavailable and not missing."""
    entry = await _setup_failing_certificates(hass, aioclient_mock)
    cert_coordinator = entry.runtime_data.cert_coordinator
    manager = entry.runtime_data.entity_manager

    assert not cert_coordinator.last_update_success
    for host in (HOST, OTHER_HOST):
        assert _expiry(hass, entry, host).state == "unavailable", host
        assert _expiring(hass, entry, host).state == "unavailable", host
        assert manager.missing_since(CERT_EXPIRY, host) is None, host
        assert manager.missing_since(CERT_EXPIRING, host) is None, host
    assert certs.probe.call_count == 0


async def test_restored_hosts_reconciled_by_the_next_successful_cycle(
    hass: HomeAssistant, aioclient_mock: Any, certs: CertStub
) -> None:
    """After the failed first cycle, the next success makes present hosts available and marks absent ones missing."""
    entry = await _setup_failing_certificates(hass, aioclient_mock)
    cert_coordinator = entry.runtime_data.cert_coordinator
    manager = entry.runtime_data.entity_manager

    rawdata = rawdata_copy("v3.7")
    rawdata["routers"]["secure@file"]["tls"]["domains"][0]["sans"] = []
    restub_traefik(aioclient_mock, version="v3.7", rawdata=rawdata)
    await entry.runtime_data.coordinator.async_refresh()
    await cert_coordinator.async_refresh()
    await hass.async_block_till_done()

    assert cert_coordinator.last_update_success
    expiry = _expiry(hass, entry)
    assert expiry.state not in ("unavailable", "unknown")
    assert expiry.attributes["source"] == "api"
    assert _expiring(hass, entry).state == "off"
    assert manager.missing_since(CERT_EXPIRY, HOST) is None
    assert manager.missing_since(CERT_EXPIRY, OTHER_HOST) == dt_util.utcnow()
    assert manager.missing_since(CERT_EXPIRING, OTHER_HOST) == dt_util.utcnow()
    assert _expiry(hass, entry, OTHER_HOST).state == "unavailable"


async def test_retry_five_minutes_after_a_failed_cycle(
    hass: HomeAssistant, aioclient_mock: Any, certs: CertStub, freezer: Any
) -> None:
    """A failed cycle retries after 300 s; a successful one goes back to the 6 h interval."""
    entry = await _setup_failing_certificates(hass, aioclient_mock, restored=())
    cert_coordinator = entry.runtime_data.cert_coordinator
    assert not cert_coordinator.last_update_success
    assert cert_coordinator.update_interval == RETRY
    requests = _certificates_requests(aioclient_mock)
    assert requests == 1

    freezer.tick(RETRY + SECOND)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert _certificates_requests(aioclient_mock) == requests + 1
    assert not cert_coordinator.last_update_success
    assert cert_coordinator.update_interval == RETRY

    restub_traefik(aioclient_mock, version="v3.7")
    freezer.tick(RETRY + SECOND)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert _certificates_requests(aioclient_mock) == 1
    assert cert_coordinator.last_update_success
    assert cert_coordinator.update_interval == timedelta(seconds=DEFAULT_TLS_CERT_COOLDOWN)


@pytest.mark.parametrize(
    "exc", [None, aiohttp.ClientConnectionError("connection refused")], ids=["status_500", "connection_error"]
)
async def test_certificate_failure_never_raises_not_ready(
    hass: HomeAssistant, aioclient_mock: Any, certs: CertStub, exc: Exception | None
) -> None:
    """A failing certificate source at setup never blocks the entry (no ConfigEntryNotReady)."""
    entry = await _setup_failing_certificates(hass, aioclient_mock, restored=(), exc=exc)
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.coordinator.last_update_success
    assert not entry.runtime_data.cert_coordinator.last_update_success


async def test_setup_does_not_wait_for_the_first_cert_cycle(
    hass: HomeAssistant, aioclient_mock: Any, socket_enabled: None
) -> None:
    """The first cert cycle runs in the background; setup finishes while it runs.

    While it runs, restored hosts are unavailable and not missing, and the
    aggregate is unavailable (never a fake "off"). When it finishes, the cert
    entities follow. Wall clock (no freezer), so the setup timeout can fire.
    """
    started = asyncio.Event()
    release = asyncio.Event()
    not_after = (dt_util.utcnow() + timedelta(days=100)).replace(microsecond=0)

    async def _gated(_connect_host: str, _port: int, sni: str, **_kwargs: Any) -> ProbedCertificate:
        started.set()
        await release.wait()
        return ProbedCertificate(
            certificate=TraefikCertificate(sni, (sni,), not_after, not_after - timedelta(days=90), "CA", None, "1"),
            verified=True,
            san_mismatch=False,
        )

    entry = make_traefik_entry()
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    for spec in (CERT_EXPIRY, CERT_EXPIRING):
        registry.async_get_or_create(spec.domain, DOMAIN, spec.unique_id(entry.entry_id, HOST), config_entry=entry)
    stub_traefik(aioclient_mock, version="v2.11")
    aggregate_uid = f"{entry.entry_id}_{UID_CERTIFICATES_PROBLEM}"

    with patch(PROBE_TARGET, AsyncMock(side_effect=_gated)):
        async with asyncio.timeout(5):
            assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        assert started.is_set()
        cert_coordinator = entry.runtime_data.cert_coordinator
        manager = entry.runtime_data.entity_manager
        assert cert_coordinator.data is None
        assert _expiry(hass, entry).state == "unavailable"
        assert _expiring(hass, entry).state == "unavailable"
        assert manager.missing_since(CERT_EXPIRY, HOST) is None
        assert manager.missing_since(CERT_EXPIRING, HOST) is None
        aggregate = hass.states.get(entity_id_for(hass, "binary_sensor", aggregate_uid))
        assert aggregate is not None
        assert aggregate.state == "unavailable"

        release.set()
        await hass.async_block_till_done(wait_background_tasks=True)

    assert cert_coordinator.last_update_success
    assert dt_util.parse_datetime(_expiry(hass, entry).state) == not_after
    assert _expiring(hass, entry).state == "off"
    assert _expiry(hass, entry, OTHER_HOST).state not in ("unavailable", "unknown")
    aggregate = hass.states.get(entity_id_for(hass, "binary_sensor", aggregate_uid))
    assert aggregate is not None
    assert aggregate.state == "off"


async def test_unload_cancels_a_running_first_cert_cycle(
    hass: HomeAssistant, aioclient_mock: Any, socket_enabled: None
) -> None:
    """Unload while the first cert cycle hangs: the cycle is cancelled, no timer is left behind."""
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def _hanging(_connect_host: str, _port: int, _sni: str, **_kwargs: Any) -> ProbedCertificate:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        raise AssertionError("unreachable")

    entry = make_traefik_entry()
    entry.add_to_hass(hass)
    stub_traefik(aioclient_mock, version="v2.11")
    with patch(PROBE_TARGET, AsyncMock(side_effect=_hanging)):
        async with asyncio.timeout(5):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
            await started.wait()
        cert_coordinator = entry.runtime_data.cert_coordinator
        async with asyncio.timeout(5):
            assert await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()
            await cancelled.wait()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert cert_coordinator.data is None
    assert not _timer_pending(cert_coordinator)
