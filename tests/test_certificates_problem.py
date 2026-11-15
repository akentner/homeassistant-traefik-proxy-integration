"""The ``certificates_problem`` aggregate binary sensor (D-17).

Contract pins:

- One per entry on the main device, enabled by default, device class
  ``problem``, bound to the cert coordinator.
- On while at least one host of the cert data has a problem by
  ``HostCertState.problem`` (the method the per-host ``certificate_expiring``
  sensor uses, so both always agree). Off with empty attributes otherwise;
  unavailable when the last cert cycle failed.
- ``problems`` lists the first ``MAX_PROBLEM_NAMES`` problem hosts in sorted
  order, ``reasons`` maps exactly those hosts to their problem, and
  ``problem_count`` counts every problem host.

Full setups use the v2.11 capture (certificates come from a probe stub) with
the clock frozen at ``T0``; no test here reads the v3.7 certificates capture.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.traefik_proxy import binary_sensor
from custom_components.traefik_proxy.binary_sensor import TraefikCertExpiringBinarySensor
from custom_components.traefik_proxy.cert_coordinator import NOT_FOUND, CertSource, HostCertState
from custom_components.traefik_proxy.const import DOMAIN
from custom_components.traefik_proxy.models import TraefikCertificate
from custom_components.traefik_proxy.tls import ProbedCertificate, ProbeError, ProbeFailure
from tests.conftest import (
    MOCK_URL,
    entity_id_for,
    make_cert_state,
    restub_traefik,
    setup_traefik_entry,
    stub_traefik,
)

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
ENTRY_ID = "test-entry"
# The spec values, independent of the constants they are checked against.
UNIQUE_ID_SUFFIX = "certificates_problem"
NAME_CAP = 50

# TLS hosts of the v2.11 capture.
HOST = "secure.example.com"
OTHER_HOST = "www.secure.example.com"
T0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
PROBE_TARGET = "custom_components.traefik_proxy.cert_coordinator.async_probe_certificate"


# ---------------------------------------------------------------------------
# Unit (mock entry)
# ---------------------------------------------------------------------------


def _row(host: str, days: int | None = 40, **kwargs: Any) -> HostCertState:
    return make_cert_state(host, days=days, now=NOW, **kwargs)


def _not_found(host: str) -> HostCertState:
    return _row(host, None, source=CertSource.API, error=NOT_FOUND, port=None)


def _entity(
    rows: list[HostCertState] | None, *, threshold_days: int = 14, last_update_success: bool = True
) -> binary_sensor.TraefikCertificatesProblemBinarySensor:
    coord: MagicMock = MagicMock()
    coord.data = None if rows is None else {row.host: row for row in rows}
    coord.threshold_days = threshold_days
    coord.last_update_success = last_update_success
    entry: MagicMock = MagicMock()
    entry.entry_id = ENTRY_ID
    entry.data = {"url": "https://traefik.example.com:8080"}
    entry.runtime_data.cert_coordinator = coord
    return binary_sensor.TraefikCertificatesProblemBinarySensor(entry)


@pytest.fixture
def frozen(freezer: Any) -> None:
    freezer.move_to(NOW)


@pytest.mark.usefixtures("frozen")
def test_problem_hosts_listed_with_reasons() -> None:
    entity = _entity(
        [
            _row("a.example.com", error="timeout", failures=2),
            _row("b.example.com"),
            _not_found("c.example.com"),
        ]
    )
    assert entity.is_on is True
    assert entity.extra_state_attributes == {
        "problems": ["a.example.com", "c.example.com"],
        "problem_count": 2,
        "reasons": {"a.example.com": "probe_failed", "c.example.com": "not_found"},
    }


@pytest.mark.usefixtures("frozen")
def test_all_healthy_is_off_with_empty_attributes() -> None:
    entity = _entity([_row("a.example.com"), _row("b.example.com", 15)])
    assert entity.is_on is False
    assert entity.extra_state_attributes == {"problems": [], "problem_count": 0, "reasons": {}}


@pytest.mark.usefixtures("frozen")
def test_names_capped_count_complete() -> None:
    rows = [_row(f"h{index:02d}.example.com", 3) for index in range(60)]
    entity = _entity(list(reversed(rows)))
    attributes = entity.extra_state_attributes
    expected = sorted(row.host for row in rows)[:NAME_CAP]
    assert attributes["problems"] == expected
    assert list(attributes["reasons"]) == expected
    assert set(attributes["reasons"].values()) == {"expiring"}
    assert attributes["problem_count"] == 60


@pytest.mark.usefixtures("frozen")
def test_reason_follows_per_host_precedence() -> None:
    entity = _entity([_row("a.example.com", -1, error="timeout", failures=2), _row("b.example.com", 5)])
    assert entity.extra_state_attributes["reasons"] == {"a.example.com": "expired", "b.example.com": "expiring"}


@pytest.mark.usefixtures("frozen")
def test_threshold_read_live_from_cert_coordinator() -> None:
    assert _entity([_row("a.example.com", 20)], threshold_days=14).is_on is False
    assert _entity([_row("a.example.com", 20)], threshold_days=30).is_on is True


@pytest.mark.usefixtures("frozen")
def test_unavailable_when_cert_cycle_failed() -> None:
    assert _entity(None, last_update_success=False).available is False
    assert _entity([_row("a.example.com")], last_update_success=False).available is False
    assert _entity([_row("a.example.com")]).available is True


@pytest.mark.usefixtures("frozen")
def test_no_cert_data_is_off() -> None:
    entity = _entity(None)
    assert entity.is_on is False
    assert entity.extra_state_attributes == {"problems": [], "problem_count": 0, "reasons": {}}


@pytest.mark.usefixtures("frozen")
def test_identity_device_and_coordinator() -> None:
    entity = _entity([])
    assert entity.unique_id == f"{ENTRY_ID}_{UNIQUE_ID_SUFFIX}"
    assert entity.translation_key == "certificates_problem"
    assert entity.device_class is BinarySensorDeviceClass.PROBLEM
    assert entity.entity_registry_enabled_default is True
    assert entity.device_info is not None
    assert entity.device_info["identifiers"] == {(DOMAIN, ENTRY_ID)}
    assert entity.coordinator is entity._entry.runtime_data.cert_coordinator


ROW_SETS = [
    [_row("a.example.com")],
    [_row("a.example.com", 14)],
    [_row("a.example.com", -1)],
    [_row("a.example.com", None)],
    [_row("a.example.com", None, error="timeout", failures=1)],
    [_row("a.example.com", None, error="timeout", failures=2)],
    [_not_found("a.example.com"), _row("b.example.com")],
]


@pytest.mark.usefixtures("frozen")
@pytest.mark.parametrize("rows", ROW_SETS)
def test_aggregate_agrees_with_per_host_sensors(rows: list[HostCertState]) -> None:
    """The aggregate is on exactly when at least one per-host certificate_expiring sensor is on."""
    aggregate = _entity(rows)
    coord = aggregate.coordinator
    per_host = [TraefikCertExpiringBinarySensor(aggregate._entry, row.host) for row in rows]
    assert all(sensor.coordinator is coord for sensor in per_host)
    assert aggregate.is_on is any(sensor.is_on is True for sensor in per_host)
    on_hosts = sorted(row.host for row, sensor in zip(rows, per_host, strict=True) if sensor.is_on)
    assert aggregate.extra_state_attributes["problems"] == on_hosts
    for row, sensor in zip(rows, per_host, strict=True):
        if sensor.is_on:
            assert aggregate.extra_state_attributes["reasons"][row.host] == sensor.extra_state_attributes["reason"]


# ---------------------------------------------------------------------------
# Full setup (v2.11 capture, probe stub)
# ---------------------------------------------------------------------------


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
            return ProbeFailure(ProbeError.TIMEOUT, "TimeoutError: ")
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


def _aggregate(hass: HomeAssistant, entry: MockConfigEntry) -> Any:
    state = hass.states.get(entity_id_for(hass, "binary_sensor", f"{entry.entry_id}_{UNIQUE_ID_SUFFIX}"))
    assert state is not None
    return state


def _assert_off(state: Any) -> None:
    assert state.state == "off"
    assert state.attributes["problems"] == []
    assert state.attributes["problem_count"] == 0
    assert state.attributes["reasons"] == {}


async def test_two_failed_probes_turn_the_aggregate_on(
    hass: HomeAssistant, aioclient_mock: Any, certs: CertStub
) -> None:
    """Probe ok at setup: off; two failed probes of one host: on with probe_failed; one success: off again."""
    healthy = {HOST: T0 + timedelta(days=40), OTHER_HOST: T0 + timedelta(days=40)}
    certs.not_after = dict(healthy)
    entry = await setup_traefik_entry(hass, aioclient_mock, version="v2.11")
    cert_coordinator = entry.runtime_data.cert_coordinator
    _assert_off(_aggregate(hass, entry))

    certs.not_after = {OTHER_HOST: healthy[OTHER_HOST]}
    await cert_coordinator.async_refresh()
    await hass.async_block_till_done()
    _assert_off(_aggregate(hass, entry))

    await cert_coordinator.async_refresh()
    await hass.async_block_till_done()
    state = _aggregate(hass, entry)
    assert state.state == "on"
    assert state.attributes["problems"] == [HOST]
    assert state.attributes["problem_count"] == 1
    assert state.attributes["reasons"] == {HOST: "probe_failed"}

    certs.not_after = dict(healthy)
    await cert_coordinator.async_refresh()
    await hass.async_block_till_done()
    _assert_off(_aggregate(hass, entry))


async def test_expiry_reaches_the_aggregate_without_a_probe(
    hass: HomeAssistant, aioclient_mock: Any, certs: CertStub, freezer: Any
) -> None:
    """1 h left: on with expiring at T0; one second after not_after on with expired, no probe call."""
    expires = T0 + timedelta(hours=1)
    certs.not_after = {HOST: expires, OTHER_HOST: T0 + timedelta(days=100, hours=3)}
    entry = await setup_traefik_entry(hass, aioclient_mock, version="v2.11")
    probes = certs.probe.call_count
    state = _aggregate(hass, entry)
    assert state.state == "on"
    assert state.attributes["reasons"] == {HOST: "expiring"}

    freezer.move_to(expires + timedelta(seconds=1))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()

    state = _aggregate(hass, entry)
    assert state.state == "on"
    assert state.attributes["problems"] == [HOST]
    assert state.attributes["problem_count"] == 1
    assert state.attributes["reasons"] == {HOST: "expired"}
    assert certs.probe.call_count == probes


async def test_aggregate_unavailable_after_a_failed_cert_cycle(
    hass: HomeAssistant, aioclient_mock: Any, certs: CertStub
) -> None:
    """A failed cert cycle makes the aggregate unavailable; the next success restores it."""
    certs.not_after = {HOST: T0 + timedelta(days=40), OTHER_HOST: T0 + timedelta(days=40)}
    entry = await setup_traefik_entry(hass, aioclient_mock, version="v2.11")
    cert_coordinator = entry.runtime_data.cert_coordinator

    # The first matching mock wins: /api/certificates answers 500, which fails the cycle.
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{MOCK_URL}/api/certificates", status=500)
    stub_traefik(aioclient_mock, version="v2.11")
    await cert_coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _aggregate(hass, entry).state == "unavailable"

    restub_traefik(aioclient_mock, version="v2.11")
    await cert_coordinator.async_refresh()
    await hass.async_block_till_done()
    _assert_off(_aggregate(hass, entry))
