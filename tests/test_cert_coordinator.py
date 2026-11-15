"""CertCoordinator tests: per-host certificate state, probe cycle and host collection.

Covers ``custom_components.traefik_proxy.cert_coordinator``:

- ``HostCertState``: live floor-day arithmetic and the problem precedence.
- The probe cycle: one probe per host under the semaphore, connecting to the
  Traefik host with the router host as SNI; results become ``HostCertState``.
- ``async_set_threshold`` mutates ``threshold_days`` and notifies listeners.
- ``_collect_hosts``: union of ``tls.domains[].main`` + ``sans[]`` + literal
  ``Host()`` names, sorted, normalized and capped.

``MagicMock`` powers the entry / main-coordinator state. The probe is mocked
at the ``async_probe_certificate`` boundary except in the trust-store test,
which runs the real probe against a local TLS server; the probe itself is
covered by ``tests/test_tls.py``.
"""

from __future__ import annotations

import asyncio
import copy
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.verification import Store
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util

from custom_components.traefik_proxy import cert_coordinator as cert_coordinator_module
from custom_components.traefik_proxy import tls
from custom_components.traefik_proxy.api import (
    TraefikProxyApiError,
    TraefikProxyAuthError,
    TraefikProxyConnectionError,
    TraefikProxyNotFoundError,
    TraefikProxyPayloadError,
)
from custom_components.traefik_proxy.cert_coordinator import (
    CERT_FAILURES_FOR_PROBLEM,
    NOT_FOUND,
    CertCoordinator,
    CertProblem,
    CertSource,
    HostCertState,
)
from custom_components.traefik_proxy.const import (
    CONF_API_KEY,
    CONF_URL,
    CONF_VERIFY_SSL,
    DEFAULT_TLS_CERT_COOLDOWN,
    DEFAULT_TLS_WARN_DAYS,
    MAX_CERT_HOSTS,
    TLS_HANDSHAKE_TIMEOUT,
    TLS_SEMAPHORE,
)
from custom_components.traefik_proxy.entity_manager import CERT_EXPIRING, CERT_EXPIRY
from custom_components.traefik_proxy.models import TraefikCertificate, parse_certificates
from custom_components.traefik_proxy.tls import ProbedCertificate, ProbeError, ProbeFailure
from tests.certgen import make_ca, make_intermediate, make_leaf, make_self_signed, write_pem
from tests.conftest import (
    TlsServerStarter,
    entity_id_for,
    frozen_v37_certificates,
    load_fixture,
    make_cert_state,
    make_snapshot,
    make_traefik_entry,
    rawdata_copy,
    setup_traefik_entry,
    stub_traefik,
)

PROBE_TARGET = "custom_components.traefik_proxy.cert_coordinator.async_probe_certificate"
CONNECT_HOST = "traefik.example.com"
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
_CERT_LOGGER = "custom_components.traefik_proxy.cert_coordinator"
# HA's pre-built client context; the cert coordinator reads its roots through it.
HA_CLIENT_CONTEXT = "homeassistant.util.ssl.client_context"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    *,
    tls_warn_days: int | None = DEFAULT_TLS_WARN_DAYS,
    title: str = "Traefik",
    url: str = f"https://{CONNECT_HOST}:8080",
) -> MagicMock:
    """Build a ``MagicMock`` entry suitable for ``CertCoordinator.__init__``.

    Mirrors ``tests/test_coordinator.py:_make_entry`` so the cert
    coordinator tests reuse the same fixture-building idiom as the main
    coordinator lifecycle tests.
    """
    entry: MagicMock = MagicMock()
    entry.entry_id = "test-entry"
    entry.title = title
    entry.data = {CONF_URL: url}
    options: dict[str, Any] = {}
    if tls_warn_days is not None:
        options["tls_warn_days"] = tls_warn_days
    entry.options = options
    entry.runtime_data = MagicMock()
    # ``coordinator.data`` is the snapshot the main coordinator publishes;
    # tests override this per scenario.
    entry.runtime_data.coordinator = MagicMock()
    entry.runtime_data.coordinator.data = make_snapshot()
    # Probe mode by default: Traefik < 3.7 answers 404 on /api/certificates.
    entry.runtime_data.client.async_get_certificates = AsyncMock(
        side_effect=TraefikProxyNotFoundError("/api/certificates", "HTTP 404", status=404)
    )
    return entry


def _entry_with_tls_hosts(*hosts: str, url: str = f"https://{CONNECT_HOST}:8080") -> MagicMock:
    """Entry whose snapshot has one TLS router per host."""
    entry = _make_entry(url=url)
    entry.runtime_data.coordinator.data = make_snapshot(
        routers=[{"name": f"r{i}", "tls": {}, "rule": f"Host(`{host}`)"} for i, host in enumerate(hosts)],
    )
    return entry


def _certificate(host: str, days: int, *, now: datetime = NOW) -> TraefikCertificate:
    return TraefikCertificate(
        common_name=host,
        sans=(host,),
        not_after=now + timedelta(days=days),
        not_before=now - timedelta(days=1),
        issuer_cn="Test CA",
        status=None,
        serial_number="1",
    )


def _probed(host: str, days: int = 30, *, verified: bool = True, san_mismatch: bool = False) -> ProbedCertificate:
    return ProbedCertificate(certificate=_certificate(host, days), verified=verified, san_mismatch=san_mismatch)


def _state(
    *,
    days: int | None = None,
    not_after: datetime | None = None,
    error: str | None = None,
    failures: int = 0,
    san_mismatch: bool | None = None,
) -> HostCertState:
    """Build a ``HostCertState`` with an exact ``not_after`` or ``days`` from ``NOW``."""
    certificate = None
    if not_after is not None:
        certificate = TraefikCertificate("h", ("h",), not_after, not_after - timedelta(days=90), None, None, "1")
    elif days is not None:
        certificate = _certificate("h", days)
    return HostCertState(
        host="h",
        source=CertSource.PROBE,
        certificate=certificate,
        verified=None,
        san_mismatch=san_mismatch,
        port=443,
        error=error,
        failures=failures,
        fetched_at=None,
    )


# ---------------------------------------------------------------------------
# HostCertState
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("not_after", "expected"),
    [
        (NOW + timedelta(days=10), 10),
        (NOW + timedelta(days=10) - timedelta(microseconds=1), 9),
        (NOW, 0),
        (NOW - timedelta(microseconds=1), -1),
        (NOW - timedelta(days=1), -1),
        (NOW - timedelta(days=1, microseconds=1), -2),
    ],
)
def test_days_left_is_signed_floor_days(not_after: datetime, expected: int) -> None:
    """Integer timedelta floor division, never rounded."""
    assert _state(not_after=not_after).days_left(NOW) == expected


def test_days_left_without_certificate_is_none() -> None:
    assert _state(error="timeout", failures=1).days_left(NOW) is None


def test_cert_failures_for_problem_is_2() -> None:
    assert CERT_FAILURES_FOR_PROBLEM == 2
    assert NOT_FOUND == "not_found"


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (_state(days=-1, error="timeout", failures=2), CertProblem.EXPIRED),
        (_state(days=40, error="ssl", failures=2), CertProblem.PROBE_FAILED),
        (_state(error="timeout", failures=2), CertProblem.PROBE_FAILED),
        (_state(error=NOT_FOUND), CertProblem.NOT_FOUND),
        (_state(days=5, error=NOT_FOUND), CertProblem.NOT_FOUND),
        # Probe mode: a certificate that does not cover the host (Traefik's default certificate).
        (_state(days=365, san_mismatch=True), CertProblem.NOT_FOUND),
        (_state(days=5, san_mismatch=True), CertProblem.NOT_FOUND),
        (_state(days=-1, san_mismatch=True), CertProblem.EXPIRED),
        (_state(days=365, san_mismatch=True, error="timeout", failures=2), CertProblem.PROBE_FAILED),
        (_state(days=365, san_mismatch=True, error="timeout", failures=1), CertProblem.NOT_FOUND),
        (_state(days=365, san_mismatch=False), None),
        (_state(days=14), CertProblem.EXPIRING),
        (_state(days=14, error="timeout", failures=1), CertProblem.EXPIRING),
        (_state(days=15), None),
        (_state(days=40, error="timeout", failures=1), None),
        (_state(error="timeout", failures=1), None),
    ],
)
def test_problem_precedence(state: HostCertState, expected: CertProblem | None) -> None:
    """expired > probe_failed > not_found > expiring; threshold 14."""
    assert state.problem(14, NOW) is expected


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (_state(error="timeout", failures=1), None),
        (_state(), None),
        (_state(days=15), False),
        (_state(days=14), True),
        (_state(error="timeout", failures=2), True),
        (_state(error=NOT_FOUND), True),
        (_state(days=365, san_mismatch=True), True),
    ],
)
def test_is_problem(state: HostCertState, expected: bool | None) -> None:
    """Unknown only without a certificate and below the failure limit."""
    assert state.is_problem(14, NOW) is expected


def test_make_cert_state_helper() -> None:
    """The conftest builder yields a probe state with a certificate ``days`` ahead."""
    state = make_cert_state("a.example.com", days=30, now=NOW)
    assert state.source is CertSource.PROBE
    assert state.certificate is not None
    assert state.days_left(NOW) == 30
    assert state.failures == 0
    assert state.error is None
    empty = make_cert_state("a.example.com", now=NOW, error="timeout", failures=1)
    assert empty.certificate is None
    assert empty.fetched_at is None


# ---------------------------------------------------------------------------
# Defaults & construction
# ---------------------------------------------------------------------------


def test_default_update_interval_is_6_hours() -> None:
    """CONTEXT.md D-05 spike-validated cycle = 21_600 seconds."""
    c = CertCoordinator(MagicMock(), _make_entry())
    assert c.update_interval == timedelta(seconds=21600)
    assert c.threshold_days == DEFAULT_TLS_WARN_DAYS


def test_threshold_sourced_from_options() -> None:
    """``threshold_days`` falls back to ``DEFAULT_TLS_WARN_DAYS`` when options omit it."""
    c_default = CertCoordinator(MagicMock(), _make_entry(tls_warn_days=None))
    assert c_default.threshold_days == DEFAULT_TLS_WARN_DAYS

    c7 = CertCoordinator(MagicMock(), _make_entry(tls_warn_days=7))
    assert c7.threshold_days == 7

    c90 = CertCoordinator(MagicMock(), _make_entry(tls_warn_days=90))
    assert c90.threshold_days == 90


def test_default_cooldown_constant_matches() -> None:
    """Sanity pin: the const value must match the ``update_interval`` above."""
    assert DEFAULT_TLS_CERT_COOLDOWN == 21600
    assert timedelta(seconds=DEFAULT_TLS_CERT_COOLDOWN) == timedelta(hours=6)


def test_semaphore_default_is_4() -> None:
    """``Semaphore(4)`` per CONTEXT.md D-05 (bounded concurrent handshakes)."""
    c = CertCoordinator(MagicMock(), _make_entry())
    assert isinstance(c._sem, asyncio.Semaphore)
    # ``_value`` is the remaining capacity (private but stable in CPython
    # 3.10+); pin the spike-validated bound.
    assert c._sem._value == 4
    assert TLS_SEMAPHORE == 4


def test_timeout_default_is_5_seconds() -> None:
    """Per-host timeout = 5.0 (CONTEXT.md D-05 spike-validated)."""
    c = CertCoordinator(MagicMock(), _make_entry())
    assert c._timeout == 5.0
    assert TLS_HANDSHAKE_TIMEOUT == 5.0


def test_config_entry_wired_via_super_init() -> None:
    """BLOCKER #1 fix pin: ``super().__init__(config_entry=entry)`` wires the entry.

    Without this, ``self.config_entry.runtime_data.coordinator.data`` access in
    ``_collect_hosts`` raises ``AttributeError``.
    """
    entry = _make_entry()
    c = CertCoordinator(MagicMock(), entry)
    assert c.config_entry is entry


# ---------------------------------------------------------------------------
# Probe cycle
# ---------------------------------------------------------------------------


async def test_probe_connects_to_traefik_host_with_router_host_as_sni(freezer: Any) -> None:
    """One probe per host: connect host = entry URL host, port 443, SNI = router host."""
    freezer.move_to(NOW)
    c = CertCoordinator(MagicMock(), _entry_with_tls_hosts("a.example.com", "b.example.com"))
    probe = AsyncMock(side_effect=lambda _connect, _port, sni, **_kw: _probed(sni))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, probe)
        await c._async_update_data()

    assert probe.await_count == 2
    assert [call.args for call in probe.await_args_list] == [
        (CONNECT_HOST, 443, "a.example.com"),
        (CONNECT_HOST, 443, "b.example.com"),
    ]
    for call in probe.await_args_list:
        assert call.kwargs["handshake_timeout"] == TLS_HANDSHAKE_TIMEOUT
        assert call.kwargs["now"] == NOW
        # Without a trust_store kwarg the probe verifies against HA's roots.
        assert isinstance(call.kwargs["trust_store"], Store)


async def test_probed_certificate_becomes_probe_state(freezer: Any) -> None:
    """A probed certificate is published with its trust flags, port 443 and the cycle time."""
    freezer.move_to(NOW)
    c = CertCoordinator(MagicMock(), _entry_with_tls_hosts("a.example.com"))
    probed = _probed("a.example.com", 30, verified=False, san_mismatch=True)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, AsyncMock(return_value=probed))
        data = await c._async_update_data()

    assert data == {
        "a.example.com": HostCertState(
            host="a.example.com",
            source=CertSource.PROBE,
            certificate=probed.certificate,
            verified=False,
            san_mismatch=True,
            port=443,
            error=None,
            failures=0,
            fetched_at=NOW,
        )
    }


async def test_probe_failure_becomes_state_without_certificate(freezer: Any, caplog: pytest.LogCaptureFixture) -> None:
    """A failed first probe: no certificate, the closed-set code, one failure, debug log."""
    freezer.move_to(NOW)
    caplog.set_level(logging.DEBUG, logger=_CERT_LOGGER)
    c = CertCoordinator(MagicMock(), _entry_with_tls_hosts("a.example.com"))
    failure = ProbeFailure(ProbeError.TIMEOUT, "TimeoutError: ")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, AsyncMock(return_value=failure))
        data = await c._async_update_data()

    state = data["a.example.com"]
    assert state.certificate is None
    assert state.verified is None
    assert state.san_mismatch is None
    assert state.error == "timeout"
    assert state.failures == 1
    assert state.fetched_at is None
    assert state.source is CertSource.PROBE
    assert state.port == 443
    debug = [r.getMessage() for r in caplog.records if r.name == _CERT_LOGGER and r.levelno == logging.DEBUG]
    assert any("a.example.com" in message and "timeout" in message for message in debug)


async def test_entry_url_without_host_fails_the_cycle() -> None:
    """Without a Traefik host there is nothing to connect to: the cycle fails."""
    c = CertCoordinator(MagicMock(), _entry_with_tls_hosts("a.example.com", url="traefik"))
    probe = AsyncMock(return_value=_probed("a.example.com"))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, probe)
        with pytest.raises(UpdateFailed):
            await c._async_update_data()
    probe.assert_not_awaited()


async def test_trust_store_reaches_the_probe() -> None:
    """The coordinator passes its trust store object to every probe unchanged."""
    store = MagicMock(spec=Store)
    c = CertCoordinator(MagicMock(), _entry_with_tls_hosts("a.example.com"), trust_store=store)
    probe = AsyncMock(return_value=_probed("a.example.com"))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, probe)
        await c._async_update_data()
    assert probe.await_args is not None
    assert probe.await_args.kwargs["trust_store"] is store


async def test_trust_store_verifies_chain_through_real_probe(
    tls_server: TlsServerStarter, tmp_path: Path, freezer: Any
) -> None:
    """A coordinator store holding the test root makes a real probe report verified True."""
    now = dt_util.utcnow()
    root = make_ca("Coordinator Root", not_before=now - timedelta(days=30), not_after=now + timedelta(days=3650))
    leaf, key = make_leaf(
        ["a.example.com"], root, not_before=now - timedelta(days=1), not_after=now + timedelta(days=90)
    )
    server = await tls_server({"a.example.com": write_pem(tmp_path, "leaf", [leaf], key)}, default="a.example.com")
    store = tls.build_trust_store([root[0].public_bytes(Encoding.DER)])
    assert store is not None
    c = CertCoordinator(
        MagicMock(), _entry_with_tls_hosts("a.example.com", url="https://127.0.0.1:8080"), trust_store=store
    )
    real_probe = tls.async_probe_certificate

    async def _to_local_server(connect_host: str, port: int, sni: str, **kwargs: Any) -> tls.ProbeResult:
        assert (connect_host, port) == ("127.0.0.1", 443)
        assert kwargs["trust_store"] is store
        return await real_probe(connect_host, server.port, sni, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, _to_local_server)
        data = await c._async_update_data()

    state = data["a.example.com"]
    assert state.verified is True
    assert state.san_mismatch is False
    assert state.certificate is not None
    assert state.certificate.not_after == leaf.not_valid_after_utc


async def test_probe_of_default_certificate_is_not_found_problem(
    tls_server: TlsServerStarter, tmp_path: Path, freezer: Any
) -> None:
    """Probe mode: Traefik answers an unknown SNI host with its default certificate.

    The default certificate is valid for about a year, but it does not cover
    the host, so the host is a ``not_found`` problem, as in API mode.
    """
    now = dt_util.utcnow()
    default_cert, key = make_self_signed(
        ["0a1b2c3d.traefik.default"], not_before=now - timedelta(days=1), not_after=now + timedelta(days=365)
    )
    server = await tls_server(
        {"0a1b2c3d.traefik.default": write_pem(tmp_path, "default", [default_cert], key)},
        default="0a1b2c3d.traefik.default",
    )
    c = CertCoordinator(MagicMock(), _entry_with_tls_hosts("a.example.com", url="https://127.0.0.1:8080"))
    real_probe = tls.async_probe_certificate

    async def _to_local_server(connect_host: str, _port: int, sni: str, **kwargs: Any) -> tls.ProbeResult:
        return await real_probe(connect_host, server.port, sni, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, _to_local_server)
        data = await c._async_update_data()

    state = data["a.example.com"]
    assert state.source is CertSource.PROBE
    assert state.certificate is not None
    assert state.san_mismatch is True
    # About a year left: no expiry problem would hide the missing coverage.
    assert state.days_left(dt_util.utcnow()) > DEFAULT_TLS_WARN_DAYS
    assert state.problem(DEFAULT_TLS_WARN_DAYS, dt_util.utcnow()) is CertProblem.NOT_FOUND
    assert state.is_problem(DEFAULT_TLS_WARN_DAYS, dt_util.utcnow()) is True


# ---------------------------------------------------------------------------
# API source (Traefik >= 3.7)
# ---------------------------------------------------------------------------

API_HOSTS = ("secure.example.com", "www.secure.example.com")


def _api_entry(*hosts: str, certificates: Any) -> MagicMock:
    """Entry with one TLS router per host whose client serves ``certificates`` (a value or an exception)."""
    entry = _entry_with_tls_hosts(*hosts)
    if isinstance(certificates, BaseException):
        entry.runtime_data.client.async_get_certificates = AsyncMock(side_effect=certificates)
    else:
        entry.runtime_data.client.async_get_certificates = AsyncMock(return_value=certificates)
    return entry


async def test_api_certificates_become_api_states(freezer: Any) -> None:
    """Traefik >= 3.7: every host maps to its API certificate; no probe runs."""
    certificates = parse_certificates(frozen_v37_certificates(freezer))
    now = dt_util.utcnow()
    c = CertCoordinator(MagicMock(), _api_entry(*API_HOSTS, certificates=certificates))
    probe = AsyncMock(return_value=_probed("unused"))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, probe)
        data = await c._async_update_data()

    probe.assert_not_awaited()
    assert data == {
        host: HostCertState(
            host=host,
            source=CertSource.API,
            certificate=certificates[0],
            verified=None,
            san_mismatch=False,
            port=None,
            error=None,
            failures=0,
            fetched_at=now,
        )
        for host in API_HOSTS
    }


async def test_api_uncovered_host_is_not_found_and_not_probed(freezer: Any) -> None:
    """A host no API certificate covers is not_found right away and never probed."""
    certificates = parse_certificates(frozen_v37_certificates(freezer))
    c = CertCoordinator(MagicMock(), _api_entry("extra.example.com", *API_HOSTS, certificates=certificates))
    probe = AsyncMock(return_value=_probed("extra.example.com"))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, probe)
        data = await c._async_update_data()

    probe.assert_not_awaited()
    assert data["extra.example.com"] == HostCertState(
        host="extra.example.com",
        source=CertSource.API,
        certificate=None,
        verified=None,
        san_mismatch=None,
        port=None,
        error=NOT_FOUND,
        failures=0,
        fetched_at=None,
    )
    assert data["secure.example.com"].certificate == certificates[0]


async def test_certificates_404_falls_back_to_probe(freezer: Any) -> None:
    """Traefik < 3.7 answers 404: every host is probed and published as a probe state."""
    freezer.move_to(NOW)
    error = TraefikProxyNotFoundError("/api/certificates", "HTTP 404", status=404)
    c = CertCoordinator(MagicMock(), _api_entry(*API_HOSTS, certificates=error))
    probe = AsyncMock(side_effect=lambda _connect, _port, sni, **_kw: _probed(sni))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, probe)
        data = await c._async_update_data()

    assert probe.await_count == 2
    assert {state.source for state in data.values()} == {CertSource.PROBE}
    assert list(data) == list(API_HOSTS)


@pytest.mark.parametrize(
    "error",
    [
        TraefikProxyApiError("/api/certificates", "HTTP 500", status=500),
        TraefikProxyConnectionError("/api/certificates", "ClientConnectorError"),
        TraefikProxyPayloadError("/api/certificates", "unexpected payload shape"),
        TraefikProxyAuthError("/api/certificates", "HTTP 401", status=401),
    ],
    ids=["status_500", "connection", "payload", "auth_401"],
)
async def test_certificates_error_fails_the_cycle_without_probe(error: TraefikProxyApiError) -> None:
    """Any non-404 API error fails the cert cycle (no reauth, no probe fallback)."""
    c = CertCoordinator(MagicMock(), _api_entry(*API_HOSTS, certificates=error))
    probe = AsyncMock(return_value=_probed("secure.example.com"))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, probe)
        with pytest.raises(UpdateFailed) as excinfo:
            await c._async_update_data()
    probe.assert_not_awaited()
    assert "/api/certificates" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Trust anchors (Home Assistant's client context)
# ---------------------------------------------------------------------------


def _root_der() -> bytes:
    now = dt_util.utcnow()
    root, _key = make_ca("HA Test Root", not_before=now - timedelta(days=1), not_after=now + timedelta(days=3650))
    return root.public_bytes(Encoding.DER)


def _ha_context(*ders: bytes) -> MagicMock:
    """A stand-in for HA's client context whose ``get_ca_certs`` returns ``ders``."""
    context = MagicMock()
    context.get_ca_certs.return_value = list(ders)
    return context


async def test_trust_store_defaults_to_ha_roots_built_once() -> None:
    """Without the kwarg the first probe-mode cycle builds the store from HA's roots, once."""
    context = _ha_context(_root_der())
    c = CertCoordinator(MagicMock(), _entry_with_tls_hosts("a.example.com"))
    probe = AsyncMock(return_value=_probed("a.example.com"))
    with patch(HA_CLIENT_CONTEXT, return_value=context), pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, probe)
        await c._async_update_data()
        await c._async_update_data()

    context.get_ca_certs.assert_called_once_with(binary_form=True)
    stores = [call.kwargs["trust_store"] for call in probe.await_args_list]
    assert len(stores) == 2
    assert isinstance(stores[0], Store)
    assert stores[1] is stores[0]


async def test_trust_store_kwarg_replaces_ha_roots() -> None:
    """A given trust store is used as is; HA's roots are never read."""
    now = dt_util.utcnow()
    root = make_ca("Kwarg Root", not_before=now - timedelta(days=1), not_after=now + timedelta(days=3650))
    store = Store([root[0]])
    context = _ha_context(_root_der())
    c = CertCoordinator(MagicMock(), _entry_with_tls_hosts("a.example.com"), trust_store=store)
    probe = AsyncMock(return_value=_probed("a.example.com"))
    with patch(HA_CLIENT_CONTEXT, return_value=context) as client_context, pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, probe)
        await c._async_update_data()

    client_context.assert_not_called()
    context.get_ca_certs.assert_not_called()
    assert probe.await_args is not None
    assert probe.await_args.kwargs["trust_store"] is store


async def test_trust_store_never_built_in_api_mode(freezer: Any) -> None:
    """API-mode cycles never read HA's roots."""
    certificates = parse_certificates(frozen_v37_certificates(freezer))
    c = CertCoordinator(MagicMock(), _api_entry(*API_HOSTS, certificates=certificates))
    with patch(HA_CLIENT_CONTEXT, return_value=_ha_context(_root_der())) as client_context:
        await c._async_update_data()
        await c._async_update_data()
    client_context.assert_not_called()


# ---------------------------------------------------------------------------
# Probe port: the router's TLS entrypoint
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        (":443", 443),
        ("0.0.0.0:443", 443),
        ("[::]:8443", 8443),
        ("[::]:443", 443),
        (":8443/tcp", 8443),
        (":9999/udp", None),
        (":http", None),
        (":0", None),
        (":70000", None),
        ("", None),
    ],
)
def test_entrypoint_port(address: str, expected: int | None) -> None:
    """Digits-only ports in 1..65535; UDP and anything else -> None."""
    assert cert_coordinator_module.entrypoint_port(address) == expected


PORT_ENTRYPOINTS = [
    {"name": "websecure", "address": ":443"},
    {"name": "alt", "address": ":8443"},
    {"name": "alt2", "address": "0.0.0.0:9443/tcp"},
    {"name": "udp-ep", "address": ":9999/udp"},
]


def _router(name: str, *entry_points: str, host: str = "h.example.com") -> dict[str, Any]:
    return {"name": name, "tls": {}, "rule": f"Host(`{host}`)", "entryPoints": list(entry_points)}


def _entry_with_routers(*routers: dict[str, Any]) -> MagicMock:
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot(routers=list(routers), entrypoints=PORT_ENTRYPOINTS)
    return entry


@pytest.mark.parametrize(
    ("routers", "expected"),
    [
        ([_router("a", "websecure"), _router("b", "alt")], 443),
        ([_router("b", "alt")], 8443),
        ([_router("b", "alt"), _router("c", "alt2")], 8443),
        ([_router("c", "alt2")], 9443),
        ([_router("d", "unknown")], 443),
        ([_router("e", "udp-ep")], 443),
        ([_router("f")], 443),
    ],
    ids=["443_wins", "only_8443", "lowest", "tcp_suffix", "unknown_entrypoint", "udp_entrypoint", "no_entrypoint"],
)
def test_probe_ports(routers: list[dict[str, Any]], expected: int) -> None:
    """Per host: 443 when any router offers it, else the lowest TLS port, else 443."""
    c = CertCoordinator(MagicMock(), _entry_with_routers(*routers))
    snapshot = c.config_entry.runtime_data.coordinator.data
    assert c._probe_ports(("h.example.com",), snapshot) == {"h.example.com": expected}


async def test_probe_ports_host_of_several_routers_probed_once(freezer: Any) -> None:
    """A host reached by several routers is probed once per cycle, on its chosen port."""
    freezer.move_to(NOW)
    entry = _entry_with_routers(
        _router("a", "alt", "websecure"),
        _router("b", "alt"),
        _router("c", "alt2", host="other.example.com"),
    )
    c = CertCoordinator(MagicMock(), entry, trust_store=MagicMock(spec=Store))
    probe = AsyncMock(side_effect=lambda _connect, _port, sni, **_kw: _probed(sni))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, probe)
        data = await c._async_update_data()

    assert sorted(call.args for call in probe.await_args_list) == [
        (CONNECT_HOST, 443, "h.example.com"),
        (CONNECT_HOST, 9443, "other.example.com"),
    ]
    assert data["h.example.com"].port == 443
    assert data["other.example.com"].port == 9443


# ---------------------------------------------------------------------------
# End to end: full setup, real handshake on the TLS entrypoint port
# ---------------------------------------------------------------------------

E2E_URL = "https://127.0.0.1:8080"
E2E_HOSTS = ("secure.example.com", "www.secure.example.com")


@pytest.mark.parametrize("trusted", [True, False], ids=["test_root_as_ha_roots", "real_ha_roots"])
async def test_end_to_end_probe_reaches_tls_entrypoint_port(
    hass: Any,
    aioclient_mock: Any,
    tls_server: TlsServerStarter,
    tmp_path: Path,
    freezer: Any,
    trusted: bool,
) -> None:
    """v2.11 (404) setup: the probe connects to 127.0.0.1 on the websecure port with each router host as SNI."""
    now = dt_util.utcnow()
    root = make_ca("E2E Root", not_before=now - timedelta(days=30), not_after=now + timedelta(days=3650))
    intermediate = make_intermediate(
        "E2E Intermediate", root, not_before=now - timedelta(days=30), not_after=now + timedelta(days=1825)
    )
    leaf, key = make_leaf(
        list(E2E_HOSTS), intermediate, not_before=now - timedelta(days=1), not_after=now + timedelta(days=45)
    )
    fallback, fallback_key = make_leaf(
        ["fallback.invalid"], intermediate, not_before=now - timedelta(days=1), not_after=now + timedelta(days=300)
    )
    served = write_pem(tmp_path, "leaf", [leaf, intermediate[0]], key)
    server = await tls_server(
        {
            E2E_HOSTS[0]: served,
            E2E_HOSTS[1]: served,
            "fallback.invalid": write_pem(tmp_path, "fallback", [fallback, intermediate[0]], fallback_key),
        },
        default="fallback.invalid",
    )
    entrypoints = copy.deepcopy(load_fixture("v2.11", "entrypoints.json"))
    for entrypoint in entrypoints:
        if entrypoint["name"] == "websecure":
            entrypoint["address"] = f":{server.port}"
    stub_traefik(aioclient_mock, version="v2.11", base_url=E2E_URL, entrypoints=entrypoints)
    entry = make_traefik_entry(
        data={CONF_URL: E2E_URL, CONF_API_KEY: "k", CONF_VERIFY_SSL: True}, unique_id="127.0.0.1"
    )
    entry.add_to_hass(hass)
    real_probe = tls.async_probe_certificate
    connects: list[tuple[str, int, str]] = []

    async def _recording_probe(connect_host: str, port: int, sni: str, **kwargs: Any) -> tls.ProbeResult:
        connects.append((connect_host, port, sni))
        return await real_probe(connect_host, port, sni, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, _recording_probe)
        if trusted:
            mp.setattr(HA_CLIENT_CONTEXT, lambda *_a, **_kw: _ha_context(root[0].public_bytes(Encoding.DER)))
        assert await hass.config_entries.async_setup(entry.entry_id)
        # The first cert cycle runs as a background task of the entry.
        await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.state is ConfigEntryState.LOADED

    assert sorted(connects) == [("127.0.0.1", server.port, host) for host in E2E_HOSTS]
    for host in E2E_HOSTS:
        state = hass.states.get(entity_id_for(hass, CERT_EXPIRY.domain, CERT_EXPIRY.unique_id(entry.entry_id, host)))
        assert state is not None
        assert dt_util.parse_datetime(state.state) == leaf.not_valid_after_utc
        assert state.attributes["source"] == "probe"
        assert state.attributes["port"] == server.port
        assert state.attributes["verified"] is trusted


# ---------------------------------------------------------------------------
# Cancellation, overlap and the concurrency bound (wall clock, no freezer)
# ---------------------------------------------------------------------------


def _probe_mode_entry(hosts: Sequence[str], *, port: int = 443) -> MagicMock:
    """Probe-mode entry (404) whose routers sit on a websecure entrypoint at ``port`` of 127.0.0.1."""
    entry = _make_entry(url="https://127.0.0.1:8080")
    entry.runtime_data.coordinator.data = make_snapshot(
        routers=[
            {"name": f"r{i}", "tls": {}, "rule": f"Host(`{host}`)", "entryPoints": ["websecure"]}
            for i, host in enumerate(hosts)
        ],
        entrypoints=[{"name": "websecure", "address": f":{port}"}],
    )
    return entry


async def test_cancelled_refresh_closes_connection_and_keeps_data(hass: Any, socket_enabled: None) -> None:
    """Cancelling a refresh in a hanging handshake: CancelledError, data untouched, connection closed."""
    eof = asyncio.Event()

    async def _silent(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.read()
        except OSError:
            pass
        finally:
            eof.set()
            writer.close()

    server = await asyncio.start_server(_silent, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        hosts = ("a.example.com", "b.example.com")
        c = CertCoordinator(hass, _probe_mode_entry(hosts, port=port), trust_store=MagicMock(spec=Store))
        ok = AsyncMock(side_effect=lambda _connect, _port, sni, **_kw: _probed(sni))
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(PROBE_TARGET, ok)
            await c.async_refresh()
        before = c.data
        assert set(before) == set(hosts)

        task = asyncio.create_task(c.async_refresh())
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert c.data is before
        async with asyncio.timeout(1.0):
            await eof.wait()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(PROBE_TARGET, ok)
            await c.async_refresh()
        assert c.last_update_success is True
        assert set(c.data) == set(hosts)
        assert c.data is not before
    finally:
        # The entry is a mock, so no unload cancels the day-boundary timer.
        await c.async_shutdown()
        server.close()
        server.close_clients()
        await server.wait_closed()


async def test_cycle_finishing_after_shutdown_schedules_no_day_boundary(hass: Any) -> None:
    """A cycle still running at unload must not arm the day-boundary timer on the dead coordinator."""
    c = CertCoordinator(hass, _probe_mode_entry(("a.example.com",)), trust_store=MagicMock(spec=Store))
    started = asyncio.Event()
    release = asyncio.Event()

    async def _gated(_connect: str, _port: int, sni: str, **_kw: Any) -> ProbedCertificate:
        started.set()
        await release.wait()
        return _probed(sni)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, AsyncMock(side_effect=_gated))
        task = asyncio.create_task(c.async_refresh())
        async with asyncio.timeout(5):
            await started.wait()
        await c.async_shutdown()
        release.set()
        async with asyncio.timeout(5):
            await task

    assert c._unsub_day_boundary is None
    # A day-boundary callback that was already due when shutdown ran does not re-arm either.
    c._async_handle_day_boundary(dt_util.utcnow())
    assert c._unsub_day_boundary is None


async def test_probe_cycle_never_reads_runtime_data_after_the_api_call() -> None:
    """The 404 answer may arrive after unload deleted ``runtime_data``: the ports come from the snapshot read before."""
    entry = _probe_mode_entry(("a.example.com",), port=8443)

    async def _unloaded_then_404() -> None:
        del entry.runtime_data
        raise TraefikProxyNotFoundError("/api/certificates", "HTTP 404", status=404)

    entry.runtime_data.client.async_get_certificates = AsyncMock(side_effect=_unloaded_then_404)
    c = CertCoordinator(MagicMock(), entry, trust_store=MagicMock(spec=Store))
    probe = AsyncMock(side_effect=lambda _connect, _port, sni, **_kw: _probed(sni))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, probe)
        data = await c._async_cycle()

    assert [call.args for call in probe.await_args_list] == [("127.0.0.1", 8443, "a.example.com")]
    assert data["a.example.com"].port == 8443


async def test_overlapping_refreshes_both_complete(hass: Any) -> None:
    """Two refreshes started together both finish with a full per-host dict."""
    hosts = ("a.example.com", "b.example.com", "c.example.com")
    c = CertCoordinator(hass, _probe_mode_entry(hosts), trust_store=MagicMock(spec=Store))

    async def _yielding(_connect: str, _port: int, sni: str, **_kw: Any) -> ProbedCertificate:
        await asyncio.sleep(0)
        return _probed(sni)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, AsyncMock(side_effect=_yielding))
        await asyncio.gather(c.async_refresh(), c.async_refresh())
    assert c.last_update_success is True
    assert set(c.data) == set(hosts)
    await c.async_shutdown()


async def test_probe_concurrency_is_bounded_by_semaphore(hass: Any) -> None:
    """With 10 hosts at most TLS_SEMAPHORE probes run at the same time; all 10 complete."""
    hosts = tuple(f"h{i:02d}.example.com" for i in range(10))
    c = CertCoordinator(hass, _probe_mode_entry(hosts), trust_store=MagicMock(spec=Store))
    release = asyncio.Event()
    running = 0
    peak = 0

    async def _gated(_connect: str, _port: int, sni: str, **_kw: Any) -> ProbedCertificate:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        try:
            await release.wait()
        finally:
            running -= 1
        return _probed(sni)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, AsyncMock(side_effect=_gated))
        task = asyncio.create_task(c.async_refresh())
        for _ in range(50):
            await asyncio.sleep(0)
        assert running == TLS_SEMAPHORE
        release.set()
        await task
    assert peak == TLS_SEMAPHORE == 4
    assert c.last_update_success is True
    assert set(c.data) == set(hosts)
    await c.async_shutdown()


# ---------------------------------------------------------------------------
# Probe history
# ---------------------------------------------------------------------------


async def _cycle(c: CertCoordinator, probe: AsyncMock) -> dict[str, HostCertState]:
    """Run one cycle and publish its data as the real refresh does."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, probe)
        data = await c._async_update_data()
    c.data = data
    return data


async def test_probe_history_keeps_last_known_certificate_and_counts_failures(freezer: Any) -> None:
    """Success, two failures (probe_failed), success: the certificate survives failures, a success resets them."""
    freezer.move_to(NOW)
    host = "a.example.com"
    c = CertCoordinator(MagicMock(), _entry_with_tls_hosts(host))
    cert_a = _probed(host, 30, verified=True, san_mismatch=True)

    first = (await _cycle(c, AsyncMock(return_value=cert_a)))[host]
    assert first.failures == 0
    assert first.certificate == cert_a.certificate

    freezer.tick(timedelta(hours=6))
    second = (await _cycle(c, AsyncMock(return_value=ProbeFailure(ProbeError.TIMEOUT, "t"))))[host]
    assert second.certificate == cert_a.certificate
    assert second.verified is True
    assert second.san_mismatch is True
    assert second.fetched_at == NOW
    assert second.error == "timeout"
    assert second.failures == 1
    # One failure is no probe_failed yet; the carried SAN mismatch keeps the host a not_found problem.
    assert second.problem(14, dt_util.utcnow()) is CertProblem.NOT_FOUND

    freezer.tick(timedelta(hours=6))
    third = (await _cycle(c, AsyncMock(return_value=ProbeFailure(ProbeError.SSL, "s"))))[host]
    assert third.certificate == cert_a.certificate
    assert third.error == "ssl"
    assert third.failures == 2
    assert third.problem(14, dt_util.utcnow()) is CertProblem.PROBE_FAILED

    freezer.tick(timedelta(hours=6))
    cert_b = ProbedCertificate(certificate=_certificate(host, 90), verified=False, san_mismatch=False)
    fourth = (await _cycle(c, AsyncMock(return_value=cert_b)))[host]
    assert fourth.certificate == cert_b.certificate
    assert fourth.verified is False
    assert fourth.san_mismatch is False
    assert fourth.error is None
    assert fourth.failures == 0
    assert fourth.fetched_at == NOW + timedelta(hours=18)


async def test_failed_probe_after_api_state_keeps_last_known_certificate(freezer: Any) -> None:
    """A failing probe after an API state keeps its certificate, starts counting at 1 and reports source probe."""
    freezer.move_to(NOW)
    host = "a.example.com"
    c = CertCoordinator(MagicMock(), _entry_with_tls_hosts(host))
    previous = make_cert_state(host, days=30, now=NOW, source=CertSource.API, port=None)
    c.data = {host: previous}

    state = (await _cycle(c, AsyncMock(return_value=ProbeFailure(ProbeError.REFUSED, "r"))))[host]
    assert state.certificate == previous.certificate
    assert state.fetched_at == previous.fetched_at
    assert state.failures == 1
    assert state.error == "refused"
    assert state.source is CertSource.PROBE
    assert state.port == 443


async def test_host_dropped_from_host_set_and_new_host_without_history() -> None:
    """A host that leaves the host set is gone in the same cycle; a new host starts fresh."""
    entry = _entry_with_tls_hosts("a.example.com", "b.example.com")
    c = CertCoordinator(MagicMock(), entry)
    failing = AsyncMock(return_value=ProbeFailure(ProbeError.TIMEOUT, "t"))
    await _cycle(c, failing)
    assert set(c.data) == {"a.example.com", "b.example.com"}

    entry.runtime_data.coordinator.data = make_snapshot(
        routers=[
            {"name": "r0", "tls": {}, "rule": "Host(`a.example.com`)"},
            {"name": "r2", "tls": {}, "rule": "Host(`c.example.com`)"},
        ],
    )
    data = await _cycle(c, failing)
    assert list(data) == ["a.example.com", "c.example.com"]
    assert data["a.example.com"].failures == 2
    assert data["c.example.com"].failures == 1


# ---------------------------------------------------------------------------
# Threshold — live re-eval per D-08
# ---------------------------------------------------------------------------


async def test_async_set_threshold_mutates_and_notifies_listeners() -> None:
    """``async_set_threshold`` mutates ``threshold_days`` AND fires listeners once.

    Note: ``DataUpdateCoordinator.async_update_listeners`` is a SYNC
    method (despite the ``async_`` prefix) that schedules callbacks
    via ``self._listeners`` — not a coroutine. The production code
    (``cert_coordinator.async_set_threshold``) calls it without
    ``await``, so we mock it with ``MagicMock()`` (not ``AsyncMock()``).
    """
    c = CertCoordinator(MagicMock(), _make_entry())
    c.async_update_listeners = MagicMock()  # type: ignore[method-assign]

    await c.async_set_threshold(7)

    assert c.threshold_days == 7
    assert c.async_update_listeners.call_count == 1


async def test_get_threshold_returns_current_value() -> None:
    """Read accessor mirrors the stored ``threshold_days``."""
    c = CertCoordinator(MagicMock(), _make_entry(tls_warn_days=21))
    assert c.get_threshold() == c.threshold_days
    assert c.get_threshold() == 21

    await c.async_set_threshold(5)
    assert c.get_threshold() == 5


# ---------------------------------------------------------------------------
# Data path — async update fans out via gather
# ---------------------------------------------------------------------------


async def test_async_update_data_fans_out_via_gather() -> None:
    """Every host of the host set gets one state; success and failure rows merge."""
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot(
        routers=[
            {
                "name": "r1",
                "tls": {
                    "domains": [
                        {"main": "h1.example.com", "sans": ["h1-alt.example.com"]},
                    ],
                },
                "rule": "Host(`h1.example.com`)",
            },
            {
                "name": "r2",
                "tls": {
                    "domains": [{"main": "h2.example.com"}],
                },
                "rule": "Host(`h2.example.com`)",
            },
        ],
    )
    c = CertCoordinator(MagicMock(), entry)

    async def fake_probe(_connect: str, _port: int, sni: str, **_kwargs: object) -> tls.ProbeResult:
        if sni == "h2.example.com":
            return ProbeFailure(ProbeError.REFUSED, "ConnectionRefusedError: ")
        return _probed(sni)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, AsyncMock(side_effect=fake_probe))
        data = await c._async_update_data()

    assert list(data) == ["h1-alt.example.com", "h1.example.com", "h2.example.com"]
    assert data["h1.example.com"].certificate is not None
    assert data["h1-alt.example.com"].certificate is not None
    assert data["h2.example.com"].certificate is None
    assert data["h2.example.com"].error == "refused"


async def test_async_update_data_returns_empty_when_no_routers() -> None:
    """Defensive: a snapshot with an empty router list returns an empty cache dict."""
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot(routers=[])
    c = CertCoordinator(MagicMock(), entry)

    data = await c._async_update_data()
    assert data == {}


async def test_async_update_data_handles_empty_snapshot() -> None:
    """A snapshot without any router → empty cache, never raises."""
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot()
    c = CertCoordinator(MagicMock(), entry)

    data = await c._async_update_data()
    assert data == {}


# ---------------------------------------------------------------------------
# Hostname extraction
# ---------------------------------------------------------------------------


def test_collect_hosts_extracts_union_of_domains_and_sans() -> None:
    """BLOCKER #1 fix pin: union of tls.domains[].main + sans[] + Host() matches.

    Routers config:
    - r1 — TLS with main + sans → must be in hosts
    - r2 — TLS with main → must be in hosts
    - r3 — no TLS → dropped
    - api@internal — TLS, but internal routers are not part of the snapshot

    Dedup collapses ``Host(`h1.example.com`)`` (rule) with
    ``domains[].main="h1.example.com"`` to a single host.
    """
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot(
        routers=[
            {
                "name": "r1",
                "tls": {
                    "domains": [
                        {"main": "h1.example.com", "sans": ["h1-alt.example.com"]},
                    ],
                },
                "rule": "Host(`h1.example.com`)",
            },
            {
                "name": "r2",
                "tls": {"domains": [{"main": "h2.example.com"}]},
                "rule": "Host(`h2.example.com`)",
            },
            {
                "name": "r3",
                "tls": None,
                "rule": "",
            },
            {
                "name": "api@internal",
                "tls": {"domains": [{"main": "internal.example.com"}]},
                "rule": "Host(`internal.example.com`)",
            },
        ],
    )
    c = CertCoordinator(MagicMock(), entry)
    assert c.config_entry is entry  # BLOCKER #1 fix pin

    hosts = c._collect_hosts()
    assert hosts == ("h1-alt.example.com", "h1.example.com", "h2.example.com")
    assert "internal.example.com" not in hosts  # internal router not in the snapshot
    assert "r3" not in hosts and "api@internal" not in hosts


def test_collect_hosts_lowercases_for_dedup() -> None:
    """Mixed casing in rule + domains → lowercased + deduped."""
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot(
        routers=[
            {
                "name": "r1",
                "tls": {"domains": [{"main": "EXAMPLE.com"}]},
                "rule": "Host(`Example.COM`)",
            },
            {
                "name": "r2",
                "tls": {"domains": [{"main": "example.com"}]},
                "rule": "Host(`example.com`)",
            },
        ],
    )
    c = CertCoordinator(MagicMock(), entry)
    hosts = c._collect_hosts()
    assert hosts == ("example.com",)


def test_collect_hosts_skips_routers_with_tls_but_no_host() -> None:
    """Routers with empty TLS, TLS without domains, malformed shapes — all skipped.

    The parser absorbs the malformed shapes (non-object tls, wrong keys),
    so they reach the cert coordinator as routers without a probe target.
    Traefik wildcard / default-cert setups leave no useful probe target either.
    """
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot(
        routers=[
            {"name": "r1", "tls": {}, "rule": ""},  # TLS set but empty
            {"name": "r2", "tls": {"domains": []}, "rule": ""},  # empty domains list
            {"name": "r3", "tls": {"not_domains": "x"}, "rule": ""},  # wrong key
            {"name": "r4", "rule": "Path(`/api`)"},  # no Host() in rule
            {"name": "not-a-dict"},  # malformed
            {"name": "r5", "tls": "should-be-dict", "rule": ""},  # wrong tls type
            {
                "name": "r6",
                "tls": {
                    "domains": [
                        {"main": "good.example.com"},
                    ],
                },
                "rule": "Host(`good.example.com`)",
            },  # valid — should appear
        ],
    )
    c = CertCoordinator(MagicMock(), entry)
    hosts = c._collect_hosts()
    assert hosts == ("good.example.com",)


def test_collect_hosts_handles_sans_as_string_or_list() -> None:
    """Sans can be a string OR a list (Traefik v3 spec)."""
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot(
        routers=[
            {
                "name": "r1",
                "tls": {"domains": [{"main": "h.example.com", "sans": "alt.example.com"}]},
                "rule": "",
            },
            {
                "name": "r2",
                "tls": {
                    "domains": [
                        {
                            "main": "h2.example.com",
                            "sans": ["a.example.com", "b.example.com"],
                        },
                    ],
                },
                "rule": "",
            },
            {
                "name": "r3",
                "tls": {"domains": [{"main": "h3.example.com", "sans": 42}]},
                "rule": "",
            },  # bad sans type → main still picked up
        ],
    )
    c = CertCoordinator(MagicMock(), entry)
    hosts = c._collect_hosts()
    assert hosts == tuple(sorted(hosts))
    assert {
        "h.example.com",
        "alt.example.com",
        "h2.example.com",
        "a.example.com",
        "b.example.com",
        "h3.example.com",
    }.issubset(hosts)


def test_collect_hosts_multi_host_rules_and_domains() -> None:
    """v2 multi-argument rules, normalized domains, skipped wildcards, non-TLS routers ignored."""
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot(
        routers=[
            {
                "name": "r1",
                "tls": {},
                "rule": "Host(`a.example.com`, `b.example.com`)",
            },
            {
                "name": "r2",
                "tls": {
                    "domains": [
                        {"main": "C.example.com", "sans": ["*.wild.example.com", "d.example.com"]},
                    ],
                },
                "rule": "",
            },
            {
                "name": "r3",
                "rule": "Host(`x.example.com`)",
            },
        ],
    )
    c = CertCoordinator(MagicMock(), entry)
    assert c._collect_hosts() == (
        "a.example.com",
        "b.example.com",
        "c.example.com",
        "d.example.com",
    )


def test_collect_hosts_skips_regex_sni_and_negated_names() -> None:
    """HostRegexp, HostSNI and negated Host() names never become probe targets."""
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot(
        routers=[
            {
                "name": "r1",
                "tls": {},
                "rule": "HostRegexp(`{sub:[a-z]+}.example.com`) || HostSNI(`sni.example.com`)",
            },
            {
                "name": "r2",
                "tls": {},
                "rule": "PathPrefix(`/x`) && !Host(`neg.example.com`) || Host(`Ok.Example.com.`)",
            },
        ],
    )
    c = CertCoordinator(MagicMock(), entry)
    assert c._collect_hosts() == ("ok.example.com",)


async def test_full_setup_registers_cert_entities_for_alt_host(
    hass: Any, aioclient_mock: Any, mock_tls_probe: AsyncMock
) -> None:
    """A v2 multi-argument rule yields cert entities for every host (probe mode, v2.11 capture)."""
    rawdata = rawdata_copy("v2.11")
    rawdata["routers"]["secure@file"]["rule"] = "Host(`secure.example.com`, `alt.example.com`)"
    entry = await setup_traefik_entry(hass, aioclient_mock, version="v2.11", rawdata=rawdata)

    probed = {call.args[2] for call in mock_tls_probe.call_args_list}
    assert {call.args[0] for call in mock_tls_probe.call_args_list} == {CONNECT_HOST}
    assert "alt.example.com" in probed
    entity_id_for(hass, CERT_EXPIRY.domain, CERT_EXPIRY.unique_id(entry.entry_id, "alt.example.com"))
    entity_id_for(hass, CERT_EXPIRING.domain, CERT_EXPIRING.unique_id(entry.entry_id, "alt.example.com"))


# ---------------------------------------------------------------------------
# Host limit (MAX_CERT_HOSTS)
# ---------------------------------------------------------------------------


def _entry_with_hosts(count: int) -> MagicMock:
    """Entry whose snapshot has ``count`` TLS routers, one distinct host each."""
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot(
        routers=[{"name": f"r{i:03d}", "tls": {}, "rule": f"Host(`h{i:03d}.example.com`)"} for i in range(count)],
    )
    return entry


def _cap_warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == _CERT_LOGGER and r.levelno >= logging.WARNING]


def test_max_cert_hosts_is_200() -> None:
    """The host limit is a fixed constant of 200."""
    assert MAX_CERT_HOSTS == 200


@pytest.mark.parametrize("count", [199, 200])
def test_collect_hosts_cap_not_reached(count: int, caplog: pytest.LogCaptureFixture) -> None:
    """Up to the limit every host is kept and nothing is logged."""
    caplog.set_level(logging.WARNING, logger=_CERT_LOGGER)
    c = CertCoordinator(MagicMock(), _entry_with_hosts(count))
    hosts = c._collect_hosts()
    assert len(hosts) == count
    assert hosts == tuple(sorted(hosts))
    assert _cap_warnings(caplog) == []


def test_collect_hosts_cap_201_drops_last_sorted(caplog: pytest.LogCaptureFixture) -> None:
    """201 hosts keep the first 200 in sorted order and log one WARNING naming 1 dropped host."""
    caplog.set_level(logging.WARNING, logger=_CERT_LOGGER)
    c = CertCoordinator(MagicMock(), _entry_with_hosts(201))
    hosts = c._collect_hosts()
    assert len(hosts) == 200
    assert hosts[0] == "h000.example.com"
    assert hosts[-1] == "h199.example.com"
    assert "h200.example.com" not in hosts
    warnings = _cap_warnings(caplog)
    assert len(warnings) == 1
    assert warnings[0].args == (200, 1)


async def test_cert_cycle_cap_250_probes_200(caplog: pytest.LogCaptureFixture) -> None:
    """250 hosts lead to exactly 200 probes and one WARNING naming 50, without host names."""
    caplog.set_level(logging.DEBUG, logger=_CERT_LOGGER)
    c = CertCoordinator(MagicMock(), _entry_with_hosts(250))

    async def fake_probe(_connect: str, _port: int, sni: str, **_kwargs: object) -> ProbedCertificate:
        return _probed(sni)

    probe = AsyncMock(side_effect=fake_probe)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, probe)
        data = await c._async_update_data()

    assert probe.call_count == 200
    assert len(data) == 200
    warnings = _cap_warnings(caplog)
    assert len(warnings) == 1
    assert warnings[0].args == (200, 50)
    assert "50" in warnings[0].getMessage()
    for record in caplog.records:
        assert ".example.com" not in record.getMessage()


async def test_cert_cycle_cap_warns_once_per_cycle(caplog: pytest.LogCaptureFixture) -> None:
    """Two cycles over 250 hosts log exactly two WARNINGs."""
    caplog.set_level(logging.WARNING, logger=_CERT_LOGGER)
    c = CertCoordinator(MagicMock(), _entry_with_hosts(250))

    async def fake_probe(_connect: str, _port: int, sni: str, **_kwargs: object) -> ProbedCertificate:
        return _probed(sni)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PROBE_TARGET, AsyncMock(side_effect=fake_probe))
        await c._async_update_data()
        await c._async_update_data()

    assert len(_cap_warnings(caplog)) == 2
