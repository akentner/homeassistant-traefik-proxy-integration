"""Certificate state over time: the day-boundary timer of the cert coordinator.

Days until expiry are computed from the clock at read time, so a certificate
crosses the warning threshold, expires and counts down one day without any
new probe. The cert coordinator keeps one timer at the earliest moment a
host's whole-day count changes; when it fires the listeners re-evaluate and
write only the entities whose state changed.

Every setup runs on the v2.11 capture (``/api/certificates`` answers 404,
so certificates come from the probe) with the probe replaced by a stub that
returns a certificate per SNI name, and the clock frozen at ``T0``. Clock
moves stay below the 6 h cert interval after setup, so only the day-boundary
timer can explain a state change.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.traefik_proxy.cert_coordinator import CertCoordinator
from custom_components.traefik_proxy.entity_manager import CERT_EXPIRING, CERT_EXPIRY
from custom_components.traefik_proxy.models import TraefikCertificate
from custom_components.traefik_proxy.tls import ProbedCertificate, ProbeError, ProbeFailure
from tests.conftest import entity_id_for, make_cert_state, setup_traefik_entry

# TLS hosts of the v2.11 capture.
HOST = "secure.example.com"
OTHER_HOST = "www.secure.example.com"
T0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
SECOND = timedelta(seconds=1)
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
PROBE_TARGET = "custom_components.traefik_proxy.cert_coordinator.async_probe_certificate"
TRACK_TARGET = "custom_components.traefik_proxy.cert_coordinator.async_track_point_in_utc_time"


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
