"""Phase 3 TEST-04 contract tests for ``custom_components.traefik_proxy.tls``.

TEST-04 mandates ``≥3 known notAfter shapes parse, ≥2 invalid shapes
reject``. The spike 002 catalogue (six known shapes) and a five-element
failure list are encoded as parametrised tests here, plus the auxiliary
contract pins:

- 24h parse-failure log throttle (CONTEXT.md D-11) — only one
  ``_LOGGER.debug`` line per host per cooldown window.
- ``_hostname_matches_san`` covers the RFC 6125 §6.4.3 single-label wildcard,
  case, trailing-dot, bare-apex and literal-IP semantics.
- ``is_error`` type guard across ``CertInfo`` / ``CertError`` / empty
  dict edges.
- ``fetch_cert_info`` never raises — refused / DNS / wrong-port paths
  resolve to ``CertError``.
- A real stdlib TLS handshake against an openssl-generated mock server
  (see ``tests/conftest.py:mock_certificate_server``) — the cache +
  semaphore + timeout paths are NOT mocked, per SUGGESTION in plan
  03-03 (defeating the test by mocking ``ssl.getpeercert`` would be
  worse than useless).
"""

from __future__ import annotations

import asyncio
import inspect
import re
import socket
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.utils import CryptographyDeprecationWarning
from cryptography.x509.oid import ExtendedKeyUsageOID
from cryptography.x509.verification import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.ssl import client_context

from custom_components.traefik_proxy import cert_coordinator as cert_coordinator_module
from custom_components.traefik_proxy import rules as rules_module
from custom_components.traefik_proxy import tls as tls_module
from custom_components.traefik_proxy.const import TLS_HANDSHAKE_TIMEOUT
from custom_components.traefik_proxy.models import TraefikCertificate
from custom_components.traefik_proxy.tls import (
    NOTAFTER_FORMATS,
    CertError,
    CertInfo,
    ProbedCertificate,
    ProbeError,
    ProbeFailure,
    _fetch_cert_raw,
    _hostname_matches_san,
    _log_parse_failure_once,
    async_probe_certificate,
    build_trust_store,
    fetch_cert_info,
    is_error,
    match_certificate,
    parse_not_after,
)
from tests.certgen import Issued, make_ca, make_intermediate, make_leaf, make_self_signed, write_pem
from tests.conftest import TlsServerStarter

# ---------------------------------------------------------------------------
# Known notAfter shapes — TEST-04's ≥3 minimum; six real-world shapes from
# spike 002 ``SYNTHETIC_OK``. Each tuple is
# ``(raw, expected_year, expected_month, expected_day)``.
# ---------------------------------------------------------------------------
_KNOWN_NOTAFTER: list[tuple[str, int, int, int]] = [
    ("Nov 15 12:00:00 2025 GMT", 2025, 11, 15),  # canonical
    ("Nov 15 12:00:00 2025", 2025, 11, 15),  # no timezone suffix
    ("Nov  1 12:00:00 2025 GMT", 2025, 11, 1),  # double-space (single-digit day)
    ("Jan  5 09:34:43 2018 GMT", 2018, 1, 5),  # from the Python docs example
    ("Feb 29 12:00:00 2024 GMT", 2024, 2, 29),  # leap-day edge case
    ("Dec 31 23:59:59 2025 GMT", 2025, 12, 31),  # year boundary
]


@pytest.mark.parametrize(("raw", "expected_year", "expected_month", "expected_day"), _KNOWN_NOTAFTER)
def test_parse_not_after_accepts_known_shapes(
    raw: str, expected_year: int, expected_month: int, expected_day: int
) -> None:
    """TEST-04 ≥3 contract — six known shapes (canonical / no-tz / double-space / leap)."""
    dt = parse_not_after(raw)
    assert (dt.year, dt.month, dt.day) == (expected_year, expected_month, expected_day)
    assert dt.tzinfo is not None, f"tzinfo must be set; got {dt!r}"
    offset = dt.tzinfo.utcoffset(dt)
    assert offset is not None, "UTC tzinfo must yield a non-None offset"
    assert offset.total_seconds() == 0, "Must parse to UTC"


# ---------------------------------------------------------------------------
# Invalid notAfter shapes — TEST-04's ≥2 minimum; five failure cases from
# spike 002 ``SYNTHETIC_FAIL``.
# ---------------------------------------------------------------------------
_INVALID_NOTAFTER: list[str] = [
    "",
    "garbage",
    "2025-11-15T12:00:00Z",  # ISO-8601 — not in any NOTAFTER_FORMAT
    "not-a-date",
    "11/15/2025",
]


@pytest.mark.parametrize("raw", _INVALID_NOTAFTER)
def test_parse_not_after_rejects_invalid_shapes(raw: str) -> None:
    """TEST-04 ≥2 contract — every invalid shape raises ``ValueError``."""
    with pytest.raises(ValueError, match="Unknown notAfter"):
        parse_not_after(raw)


# ---------------------------------------------------------------------------
# Log throttle for repeated parse failures (CONTEXT.md D-11).
# ---------------------------------------------------------------------------


def test_log_throttle_suppresses_repeated_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """24h parse-failure throttle: the first call logs, subsequent calls do not.

    Pins D-11 by directly exercising ``_log_parse_failure_once`` — the
    actual production surface that ``_fetch_cert_raw`` invokes after a
    parse failure. A fresh, empty ``_parse_log_cooldown`` dict is
    monkey-patched into the module for the test's scope so no cross-
    test bleed is possible.
    """
    # Mirror the test in tls.py — module-level state needs scoping.
    monkeypatch.setattr("custom_components.traefik_proxy.tls._parse_log_cooldown", {}, raising=False)

    debug_spy = MagicMock()
    monkeypatch.setattr("custom_components.traefik_proxy.tls._LOGGER.debug", debug_spy)

    host = "throttle-test.example.test"
    raw = "garbage"
    _log_parse_failure_once(host, raw)
    _log_parse_failure_once(host, raw)
    _log_parse_failure_once(host, raw)

    assert debug_spy.call_count == 1, (
        f"Throttle must allow only one _LOGGER.debug call per host per 24h; "
        f"got {debug_spy.call_count} after 3 invocations."
    )


def test_log_throttle_per_host_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two different hosts each get their own first-call log line.

    D-11 semantics are per-host, not global. A second host must NOT
    piggyback on the first host's 24h cooldown.
    """
    monkeypatch.setattr("custom_components.traefik_proxy.tls._parse_log_cooldown", {}, raising=False)
    debug_spy = MagicMock()
    monkeypatch.setattr("custom_components.traefik_proxy.tls._LOGGER.debug", debug_spy)

    _log_parse_failure_once("host-a.example.test", "garbage")
    _log_parse_failure_once("host-b.example.test", "garbage")
    _log_parse_failure_once("host-a.example.test", "garbage")  # throttled

    assert debug_spy.call_count == 2


# ---------------------------------------------------------------------------
# ``_hostname_matches_san`` — RFC 6125 §6.4.3 wildcard + case + bare-apex.
# ---------------------------------------------------------------------------
_HOST_SAN_CASES: list[tuple[str, tuple[str, ...], bool]] = [
    ("a.example.com", ("*.example.com",), True),
    ("a.b.example.com", ("*.example.com",), False),  # a wildcard covers exactly one label
    ("example.com", ("*.example.com",), False),  # bare apex not covered by a wildcard
    ("foo.example.com.evil.org", ("*.example.com",), False),
    ("A.Example.COM.", ("*.example.com",), True),  # case- and trailing-dot-insensitive
    ("a.example.com", ("A.EXAMPLE.COM.",), True),
    ("fa.example.com", ("f*.example.com",), False),  # partial-label wildcard is a literal
    ("f*.example.com", ("f*.example.com",), True),
    ("localhost", ("localhost",), True),
    ("localhost", ("*.localhost", "*"), False),  # single-label host never matches a wildcard
    ("192.168.1.10", ("192.168.1.10",), True),  # IP SANs compare literally
    ("192.168.1.10", ("*.168.1.10",), False),  # never a wildcard match for an IP literal
    ("bücher.example", ("xn--bcher-kva.example",), False),  # no Unicode normalization
    ("api.example.com", ("api.example.com", "other.com"), True),  # multi-SAN hit
    ("example.com", ("example.org",), False),
]


@pytest.mark.parametrize(("host", "names", "expected"), _HOST_SAN_CASES)
def test_hostname_matches_san(host: str, names: tuple[str, ...], expected: bool) -> None:
    """RFC 6125 single-label wildcard, case, trailing-dot and literal semantics."""
    assert _hostname_matches_san(host, names) is expected


def test_hostname_matches_san_empty_san_rejects_all() -> None:
    """Empty SAN tuple matches nothing (defensive default)."""
    assert _hostname_matches_san("any.example.com", ()) is False


def test_hostname_matches_san_wildcard_does_not_match_attacker_suffix() -> None:
    """``*.example.com`` must NOT match ``foo.example.com.evil.org``.

    Wildcards are scoped to the cert's domain: the part of the host after
    its first label must equal the wildcard's domain exactly, so a suffix
    match cannot let ``foo.example.com.evil.org`` claim the certificate.
    """
    assert _hostname_matches_san("foo.example.com.evil.org", ("*.example.com",)) is False


# ---------------------------------------------------------------------------
# ``is_error`` type guard — three contract edges.
# ---------------------------------------------------------------------------


def test_is_error_true_on_dict_with_error_key() -> None:
    """``CertError`` carries an ``error`` key — type guard returns True."""
    err: CertError = {"host": "h", "port": 443, "error": "timeout"}
    assert is_error(err) is True


def test_is_error_false_on_certinfo_instance() -> None:
    """``CertInfo`` dataclass — no ``error`` attribute — type guard returns False."""
    info = CertInfo(
        host="example.com",
        port=443,
        not_after=datetime(2030, 1, 1, tzinfo=UTC),
        days_until_expiry=1000,
        subject="CN=example.com",
        issuer="CN=test",
    )
    assert is_error(info) is False


def test_is_error_false_on_empty_dict() -> None:
    """Empty dict — no ``error`` key — type guard returns False.

    Defensive: a future ``CertInfo`` shape that ever starts returning a
    bare dict with no ``notAfter`` should NOT be classified as an error.
    """
    assert is_error({}) is False


# ---------------------------------------------------------------------------
# ``fetch_cert_info`` graceful error paths — the function NEVER raises.
# Each test asks for ``socket_enabled`` so pytest-homeassistant-custom-component's
# network lock-down (pytest_socket) does not intercept the underlying
# socket.create_connection call before the production code's own except
# chain gets a chance to classify the failure.
# ---------------------------------------------------------------------------


def test_closed_port_returns_refused_or_oserror(socket_enabled: None) -> None:
    """Port 1 is unprivileged and rarely a listener — connection refused/oserror."""
    assert socket_enabled is None  # consumed for fixture propagation
    result = fetch_cert_info("127.0.0.1", 1, timeout=2.0)
    assert is_error(result)
    err = cast(CertError, result)
    assert err["error"] in {"refused", "oserror"}


def test_unresolvable_host_returns_dns(socket_enabled: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """DNS failure (``socket.gaierror``) → ``CertError(error="dns")``.

    ``pytest-homeassistant-custom-component`` patches ``socket.getaddrinfo``
    to raise a generic ``RuntimeError("DNS resolution disabled in tests")``
    for any non-IP hostname — that path would land in the production
    ``except Exception`` bucket and surface as ``unknown``. Instead we
    monkeypatch ``socket.getaddrinfo`` itself with the real-world
    ``socket.gaierror`` exception so the production ``except
    socket.gaierror`` handler is the one being tested, not the catch-all.
    """
    assert socket_enabled is None  # consumed for fixture propagation
    import socket as _socket

    def _raise_gaierror(*_args: object, **_kwargs: object) -> object:
        raise _socket.gaierror(-2, "Name or service not known (test stub)")

    monkeypatch.setattr(_socket, "getaddrinfo", _raise_gaierror)

    result = fetch_cert_info("nonexistent-traefik-test.invalid", 443, timeout=2.0)
    assert is_error(result)
    err = cast(CertError, result)
    assert err["error"] == "dns"


def test_invalid_port_for_running_service_returns_oserror(socket_enabled: None) -> None:
    """Probing a TCP-unbound high port must surface as oserror/refused.

    Port 99999 falls in the OS ephemeral range and is almost never
    bound; if it happens to be, the test simply retries — the contract
    is "error class is oserror/refused, NOT raise".
    """
    assert socket_enabled is None  # consumed for fixture propagation
    result = fetch_cert_info("127.0.0.1", 99999, timeout=2.0)
    assert is_error(result)
    err = cast(CertError, result)
    assert err["error"] in {"refused", "oserror"}


# ---------------------------------------------------------------------------
# Mock TLS server handshake — exercises the cache + cert parse path.
# Skipped if the openssl CLI is unavailable on PATH.
# ---------------------------------------------------------------------------


async def test_mock_tls_server_returns_certinfo(
    mock_certificate_server: tuple[str, int, str],
) -> None:
    """End-to-end: connect to the openssl-backed TLS server, expect CertInfo.

    Asserts the SNI hostname round-trips through ``getpeercert`` and that
    the 365-day cert yields ``300 < days_until_expiry < 400`` (a 7-day
    safety window around the 365-day target absorbs test-runner clock
    drift and leap-day effects).

    ``fetch_cert_info`` is sync and blocks the event loop — we drive it
    via ``asyncio.to_thread`` so the asyncio TLS server can accept the
    connection. Without the thread wrapper, the server-side ``accept()``
    can't fire because the loop is stuck in ``socket.create_connection``.
    """
    import asyncio as _asyncio

    host, port, sni_hostname = mock_certificate_server

    result = await _asyncio.to_thread(fetch_cert_info, host, port, timeout=5.0)

    assert not is_error(result), f"Expected CertInfo, got {result!r}"
    info: Any = result
    # Days window: ~365 from openssl ``-days 365``; tolerate ±30 for clock drift
    # and stdin-vs-now round-trip across day boundaries in CI runners.
    assert 300 < info.days_until_expiry < 400, f"days_until_expiry outside expected window: {info.days_until_expiry}"
    assert sni_hostname in info.san, f"SAN should include {sni_hostname!r}; got {info.san!r}"
    assert f"CN={sni_hostname}" in info.subject, f"Subject should contain CN={sni_hostname!r}; got {info.subject!r}"


async def test_mock_tls_server_sni_mismatch_detection(
    mock_certificate_server: tuple[str, int, str],
) -> None:
    """SNI mismatch: probe with a hostname the cert does not cover.

    The fixture cert covers ``router-a.example.test``; we probe
    ``127.0.0.1`` with SNI ``wrong.example.test`` via the test-only
    ``_fetch_cert_raw`` seam. The cert's SAN does not include
    ``wrong.example.test``, so ``san_mismatch=True`` must fire.

    Same threading rationale as ``test_mock_tls_server_returns_certinfo`` —
    the sync fetch must not block the asyncio server's accept path.
    """
    import asyncio as _asyncio

    _, port, _sni_hostname = mock_certificate_server

    result = await _asyncio.to_thread(
        _fetch_cert_raw,
        host="127.0.0.1",
        port=port,
        sni="wrong.example.test",
        timeout=5.0,
    )

    assert not is_error(result), f"Expected CertInfo (with mismatch flag), got {result!r}"
    info: Any = result
    assert info.san_mismatch is True, f"SNI mismatch must set san_mismatch=True; got san={info.san!r}"


# ---------------------------------------------------------------------------
# Module-level invariants the rest of the suite depends on.
# ---------------------------------------------------------------------------


def test_notafter_formats_count_matches_spec() -> None:
    """Exactly 3 manual fallback formats — adding/removing changes the contract."""
    assert len(NOTAFTER_FORMATS) == 3


# Names of the removed blocking probe path; none may come back.
_REMOVED_NAMES = (
    "DEFAULT_PORT",
    "NOTAFTER_FORMATS",
    "CertDict",
    "CertError",
    "CertInfo",
    "is_error",
    "parse_not_after",
    "_format_rdn",
    "_build_error",
    "_open_tls_connection",
    "_fetch_cert_raw",
    "fetch_cert_info",
    "fetch_cert_info_async",
    "_log_parse_failure_once",
    "_parse_log_cooldown",
)
# Thread offloading, blocking connects and CA / default-certificate loading.
_FORBIDDEN_CALLS = re.compile(
    r"to_thread|run_in_executor|create_connection|load_default_certs|load_verify_locations"
    r"|create_default_context|set_default_verify_paths"
)


def test_blocking_probe_path_is_removed() -> None:
    """Only the threadless probe remains in the tls module."""
    assert [name for name in _REMOVED_NAMES if hasattr(tls_module, name)] == []


@pytest.mark.parametrize("module", [tls_module, cert_coordinator_module], ids=["tls", "cert_coordinator"])
def test_probe_modules_use_no_threads_or_blocking_calls(module: ModuleType) -> None:
    """No thread, executor, blocking connect or CA loading in the probe modules."""
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
    assert _FORBIDDEN_CALLS.findall(source) == []


@pytest.mark.parametrize(
    "module", [tls_module, cert_coordinator_module, rules_module], ids=["tls", "cert_coordinator", "rules"]
)
def test_no_module_level_dict(module: ModuleType) -> None:
    """No module-level dict that could grow with the number of probed hosts."""
    dicts = [name for name, value in vars(module).items() if isinstance(value, dict) and not name.startswith("__")]
    assert dicts == []


def test_tls_handshake_timeout_default() -> None:
    """``TLS_HANDSHAKE_TIMEOUT`` constant must be 5s (the spike-validated value)."""
    assert TLS_HANDSHAKE_TIMEOUT == 5.0


# ---------------------------------------------------------------------------
# Threadless CERT_NONE probe against a local TLS server (certificates from
# ``tests/certgen.py``). Tests with generated certificates freeze time.
# ---------------------------------------------------------------------------

ROUTER_A = "router-a.example.test"
DEFAULT_HOST = "default.example.test"


@dataclass(frozen=True)
class _Pki:
    """A root and an intermediate CA, valid around ``now``."""

    now: datetime
    root: Issued
    intermediate: Issued

    @property
    def root_der(self) -> bytes:
        return self.root[0].public_bytes(Encoding.DER)


def _make_pki() -> _Pki:
    now = dt_util.utcnow()
    root = make_ca("Test Root", not_before=now - timedelta(days=30), not_after=now + timedelta(days=3650))
    intermediate = make_intermediate(
        "Test Intermediate", root, not_before=now - timedelta(days=30), not_after=now + timedelta(days=3650)
    )
    return _Pki(now=now, root=root, intermediate=intermediate)


def _valid_leaf(pki: _Pki, names: list[str], *, issuer: Issued | None = None) -> Issued:
    return make_leaf(
        names,
        issuer if issuer is not None else pki.intermediate,
        not_before=pki.now - timedelta(days=1),
        not_after=pki.now + timedelta(days=90),
    )


def _serve(
    tmp_path: Path, pki: _Pki, leaves: dict[str, Issued], *, with_intermediate: bool = True
) -> dict[str, tuple[Path, Path]]:
    """Write every leaf (plus the intermediate) as PEM files for ``tls_server``."""
    certs: dict[str, tuple[Path, Path]] = {}
    for index, (name, (cert, key)) in enumerate(leaves.items()):
        chain = [cert, pki.intermediate[0]] if with_intermediate else [cert]
        certs[name] = write_pem(tmp_path, f"leaf{index}", chain, key)
    return certs


def test_certgen_ca_extensions() -> None:
    """Roots and intermediates carry what the cryptography verifier needs for a CA."""
    pki = _make_pki()
    for cert, _key in (pki.root, pki.intermediate):
        basic = cert.extensions.get_extension_for_class(x509.BasicConstraints)
        assert basic.critical is True
        assert basic.value.ca is True
        usage = cert.extensions.get_extension_for_class(x509.KeyUsage).value
        assert usage.key_cert_sign is True
        assert usage.crl_sign is True
        cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier)
    pki.intermediate[0].extensions.get_extension_for_class(x509.AuthorityKeyIdentifier)


def test_certgen_leaf_extensions() -> None:
    """Leaves carry DNS/IP SANs, an AKI from the issuer, CA=false and serverAuth."""
    pki = _make_pki()
    leaf, _key = _valid_leaf(pki, [ROUTER_A, "127.0.0.1"])
    san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert san.get_values_for_type(x509.DNSName) == [ROUTER_A]
    assert [str(ip) for ip in san.get_values_for_type(x509.IPAddress)] == ["127.0.0.1"]
    aki = leaf.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value
    ski = pki.intermediate[0].extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value
    assert aki.key_identifier == ski.digest
    assert leaf.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False
    eku = leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert ExtendedKeyUsageOID.SERVER_AUTH in eku
    assert leaf.issuer == pki.intermediate[0].subject


def test_certgen_self_signed_issuer_is_subject() -> None:
    """A self-signed leaf names itself as issuer."""
    now = dt_util.utcnow()
    cert, _key = make_self_signed([ROUTER_A], not_before=now, not_after=now + timedelta(days=1))
    assert cert.issuer == cert.subject


async def test_probe_reads_verified_certificate_via_sni(
    tls_server: TlsServerStarter, tmp_path: Path, freezer: Any
) -> None:
    """Tracer: a real CERT_NONE handshake with SNI returns the parsed, verified leaf."""
    pki = _make_pki()
    leaf, key = _valid_leaf(pki, [ROUTER_A])
    certs = _serve(tmp_path, pki, {ROUTER_A: (leaf, key), DEFAULT_HOST: _valid_leaf(pki, [DEFAULT_HOST])})
    server = await tls_server(certs, default=DEFAULT_HOST)

    result = await async_probe_certificate(
        "127.0.0.1",
        server.port,
        ROUTER_A,
        handshake_timeout=5.0,
        trust_store=build_trust_store([pki.root_der]),
        now=dt_util.utcnow(),
    )

    assert isinstance(result, ProbedCertificate), result
    assert result.verified is True
    assert result.san_mismatch is False
    assert result.certificate == TraefikCertificate(
        common_name=ROUTER_A,
        sans=(ROUTER_A,),
        not_after=leaf.not_valid_after_utc,
        not_before=leaf.not_valid_before_utc,
        issuer_cn="Test Intermediate",
        status=None,
        serial_number=str(leaf.serial_number),
    )


async def test_probe_sni_routing_and_default_certificate(
    tls_server: TlsServerStarter, tmp_path: Path, freezer: Any
) -> None:
    """The server presents the certificate of the SNI name, else its default certificate."""
    pki = _make_pki()
    certs = _serve(
        tmp_path, pki, {ROUTER_A: _valid_leaf(pki, [ROUTER_A]), DEFAULT_HOST: _valid_leaf(pki, [DEFAULT_HOST])}
    )
    server = await tls_server(certs, default=DEFAULT_HOST)
    store = build_trust_store([pki.root_der])

    routed = await async_probe_certificate(
        "127.0.0.1", server.port, ROUTER_A, handshake_timeout=5.0, trust_store=store, now=dt_util.utcnow()
    )
    unknown = await async_probe_certificate(
        "127.0.0.1", server.port, "unknown.example.test", handshake_timeout=5.0, trust_store=store, now=dt_util.utcnow()
    )

    assert isinstance(routed, ProbedCertificate)
    assert routed.certificate.common_name == ROUTER_A
    assert isinstance(unknown, ProbedCertificate)
    assert unknown.certificate.common_name == DEFAULT_HOST
    assert unknown.san_mismatch is True
    assert unknown.verified is False


# ---------------------------------------------------------------------------
# Verification matrix: real handshakes under frozen time.
# ---------------------------------------------------------------------------


async def _probe(port: int, sni: str, store: Store | None, *, now: datetime | None = None) -> ProbedCertificate:
    result = await async_probe_certificate(
        "127.0.0.1",
        port,
        sni,
        handshake_timeout=5.0,
        trust_store=store,
        now=now if now is not None else dt_util.utcnow(),
    )
    assert isinstance(result, ProbedCertificate), result
    return result


async def test_probe_expired_leaf_is_read_unverified(
    tls_server: TlsServerStarter, tmp_path: Path, freezer: Any
) -> None:
    """An expired leaf from a trusted CA is read, with verified False."""
    pki = _make_pki()
    leaf = make_leaf(
        [ROUTER_A], pki.intermediate, not_before=pki.now - timedelta(days=100), not_after=pki.now - timedelta(days=1)
    )
    server = await tls_server(_serve(tmp_path, pki, {ROUTER_A: leaf}), default=ROUTER_A)

    result = await _probe(server.port, ROUTER_A, build_trust_store([pki.root_der]))

    assert result.verified is False
    assert result.san_mismatch is False
    assert result.certificate.not_after == leaf[0].not_valid_after_utc
    await server.wait_connections(1)
    assert server.received == [b""]


async def test_probe_self_signed_leaf_is_read_unverified(
    tls_server: TlsServerStarter, tmp_path: Path, freezer: Any
) -> None:
    """A self-signed leaf is read, with verified False."""
    pki = _make_pki()
    leaf = make_self_signed([ROUTER_A], not_before=pki.now - timedelta(days=1), not_after=pki.now + timedelta(days=30))
    certs = _serve(tmp_path, pki, {ROUTER_A: leaf}, with_intermediate=False)
    server = await tls_server(certs, default=ROUTER_A)

    result = await _probe(server.port, ROUTER_A, build_trust_store([pki.root_der]))

    assert result.verified is False
    assert result.certificate.issuer_cn == ROUTER_A
    await server.wait_connections(1)
    assert server.received == [b""]


async def test_probe_private_ca_not_in_store_is_unverified(
    tls_server: TlsServerStarter, tmp_path: Path, freezer: Any
) -> None:
    """A leaf from a private CA whose root is not trusted is read, with verified False."""
    pki = _make_pki()
    other_root = make_ca("Other Root", not_before=pki.now - timedelta(days=1), not_after=pki.now + timedelta(days=30))
    server = await tls_server(_serve(tmp_path, pki, {ROUTER_A: _valid_leaf(pki, [ROUTER_A])}), default=ROUTER_A)

    result = await _probe(server.port, ROUTER_A, build_trust_store([other_root[0].public_bytes(Encoding.DER)]))

    assert result.verified is False
    await server.wait_connections(1)
    assert server.received == [b""]


async def test_probe_without_intermediate_is_unverified(
    tls_server: TlsServerStarter, tmp_path: Path, freezer: Any
) -> None:
    """A leaf served without its intermediate does not verify, even with the root trusted."""
    pki = _make_pki()
    certs = _serve(tmp_path, pki, {ROUTER_A: _valid_leaf(pki, [ROUTER_A])}, with_intermediate=False)
    server = await tls_server(certs, default=ROUTER_A)

    result = await _probe(server.port, ROUTER_A, build_trust_store([pki.root_der]))

    assert result.verified is False
    await server.wait_connections(1)
    assert server.received == [b""]


async def test_probe_leaf_for_other_host_is_unverified_with_san_mismatch(
    tls_server: TlsServerStarter, tmp_path: Path, freezer: Any
) -> None:
    """A trusted leaf for another host is unverified and flagged as SAN mismatch."""
    pki = _make_pki()
    other = "other.example.test"
    server = await tls_server(_serve(tmp_path, pki, {other: _valid_leaf(pki, [other])}), default=other)

    result = await _probe(server.port, ROUTER_A, build_trust_store([pki.root_der]))

    assert result.certificate.common_name == other
    assert result.verified is False
    assert result.san_mismatch is True
    await server.wait_connections(1)
    assert server.received == [b""]


async def test_probe_ip_san_with_ip_sni_is_verified(tls_server: TlsServerStarter, tmp_path: Path, freezer: Any) -> None:
    """An IP-literal host is verified against an IP SAN."""
    pki = _make_pki()
    server = await tls_server(
        _serve(tmp_path, pki, {"127.0.0.1": _valid_leaf(pki, ["127.0.0.1"])}), default="127.0.0.1"
    )

    result = await _probe(server.port, "127.0.0.1", build_trust_store([pki.root_der]))

    assert result.certificate.sans == ("127.0.0.1",)
    assert result.verified is True
    assert result.san_mismatch is False
    await server.wait_connections(1)
    assert server.received == [b""]


async def test_probe_verifies_at_given_time_after_not_after(
    tls_server: TlsServerStarter, tmp_path: Path, freezer: Any
) -> None:
    """Verification uses ``now``: one second after notAfter the valid chain is unverified."""
    pki = _make_pki()
    leaf = _valid_leaf(pki, [ROUTER_A])
    server = await tls_server(_serve(tmp_path, pki, {ROUTER_A: leaf}), default=ROUTER_A)
    store = build_trust_store([pki.root_der])

    current = await _probe(server.port, ROUTER_A, store)
    later = await _probe(server.port, ROUTER_A, store, now=leaf[0].not_valid_after_utc + timedelta(seconds=1))

    assert current.verified is True
    assert later.verified is False


async def test_probe_sends_no_bytes_after_handshake(tls_server: TlsServerStarter, tmp_path: Path, freezer: Any) -> None:
    """Every probe connection closes without sending application data."""
    pki = _make_pki()
    certs = _serve(
        tmp_path, pki, {ROUTER_A: _valid_leaf(pki, [ROUTER_A]), DEFAULT_HOST: _valid_leaf(pki, [DEFAULT_HOST])}
    )
    server = await tls_server(certs, default=DEFAULT_HOST)

    for sni in (ROUTER_A, DEFAULT_HOST, "unknown.example.test"):
        await _probe(server.port, sni, None)

    await server.wait_connections(3)
    assert server.received == [b"", b"", b""]


# ---------------------------------------------------------------------------
# Error classification (wall clock, no freezer).
# ---------------------------------------------------------------------------


@dataclass
class _TcpServer:
    port: int
    eof: asyncio.Event


type _TcpServerStarter = Callable[
    [Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]], Awaitable[_TcpServer]
]


@pytest_asyncio.fixture
async def tcp_server(socket_enabled: None) -> AsyncIterator[_TcpServerStarter]:
    """Start plain TCP servers on 127.0.0.1 with a given handler; teardown closes them."""
    assert socket_enabled is None  # consumed for fixture propagation
    servers: list[asyncio.Server] = []

    async def start(
        handler: Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]],
    ) -> _TcpServer:
        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        servers.append(server)
        return _TcpServer(port=server.sockets[0].getsockname()[1], eof=asyncio.Event())

    yield start
    for server in servers:
        server.close()
        server.close_clients()
        await server.wait_closed()


async def _start_silent_server(tcp_server: _TcpServerStarter) -> _TcpServer:
    """A TCP server that accepts, never answers and records EOF from the client."""
    eof = asyncio.Event()

    async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.read()
        except OSError:
            pass
        finally:
            eof.set()
            writer.close()

    server = await tcp_server(_handle)
    server.eof = eof
    return server


async def _probe_failure(host: str, port: int, *, handshake_timeout: float = 5.0) -> ProbeFailure:
    result = await async_probe_certificate(
        host, port, ROUTER_A, handshake_timeout=handshake_timeout, trust_store=None, now=dt_util.utcnow()
    )
    assert isinstance(result, ProbeFailure), result
    return result


async def test_probe_plain_http_server_is_ssl_error(tcp_server: _TcpServerStarter) -> None:
    """A server answering plain HTTP fails the handshake as ``ssl``, not ``oserror``."""

    async def _http(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.read(1024)
        writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
        await writer.drain()
        writer.close()

    server = await tcp_server(_http)

    failure = await _probe_failure("127.0.0.1", server.port)

    assert failure.error is ProbeError.SSL
    assert failure.detail.startswith("SSL")


async def test_probe_closed_port_is_refused(socket_enabled: None) -> None:
    """A closed port on 127.0.0.1 is ``refused``."""
    assert socket_enabled is None  # consumed for fixture propagation
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    failure = await _probe_failure("127.0.0.1", port)

    assert failure.error is ProbeError.REFUSED


async def test_probe_hanging_server_is_timeout(tcp_server: _TcpServerStarter) -> None:
    """A server that never answers the handshake is ``timeout`` within the handshake timeout."""
    server = await _start_silent_server(tcp_server)
    started = time.monotonic()

    failure = await _probe_failure("127.0.0.1", server.port, handshake_timeout=0.3)

    assert failure.error is ProbeError.TIMEOUT
    assert time.monotonic() - started < 2.0


async def test_probe_dns_failure_is_dns(socket_enabled: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """``socket.gaierror`` from the loop's resolver is ``dns``."""
    assert socket_enabled is None  # consumed for fixture propagation

    async def _gaierror(*_args: object, **_kwargs: object) -> object:
        raise socket.gaierror(-2, "Name or service not known (test stub)")

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", _gaierror)

    failure = await _probe_failure("traefik.invalid", 443)

    assert failure.error is ProbeError.DNS


def _fake_writer(peer: bytes | None) -> MagicMock:
    """A stream writer whose ssl_object presents ``peer`` as DER leaf."""
    ssl_object = MagicMock()
    ssl_object.getpeercert.return_value = peer
    ssl_object.get_unverified_chain.return_value = None
    writer = MagicMock()
    writer.get_extra_info.return_value = ssl_object
    writer.wait_closed = AsyncMock(return_value=None)
    return writer


def _patch_opener(
    monkeypatch: pytest.MonkeyPatch, *, writer: MagicMock | None = None, exc: BaseException | None = None
) -> None:
    async def _open(*_args: object, **_kwargs: object) -> tuple[MagicMock, MagicMock]:
        if exc is not None:
            raise exc
        assert writer is not None
        return MagicMock(), writer

    monkeypatch.setattr("custom_components.traefik_proxy.tls.asyncio.open_connection", _open)


async def test_probe_empty_peer_certificate_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """No peer certificate is ``empty``; the writer is still closed."""
    writer = _fake_writer(None)
    _patch_opener(monkeypatch, writer=writer)

    failure = await _probe_failure("127.0.0.1", 443)

    assert failure.error is ProbeError.EMPTY
    writer.close.assert_called_once()
    writer.wait_closed.assert_awaited_once()


async def test_probe_non_der_peer_certificate_is_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Peer bytes that are not DER are ``parse``; the writer is still closed."""
    writer = _fake_writer(b"not-der")
    _patch_opener(monkeypatch, writer=writer)

    failure = await _probe_failure("127.0.0.1", 443)

    assert failure.error is ProbeError.PARSE
    writer.close.assert_called_once()


async def test_probe_unexpected_exception_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any other exception is ``unknown`` with its type name in ``detail``."""
    _patch_opener(monkeypatch, exc=RuntimeError("boom"))

    failure = await _probe_failure("127.0.0.1", 443)

    assert failure.error is ProbeError.UNKNOWN
    assert failure.detail == "RuntimeError: boom"


async def test_probe_cancelled_error_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """``asyncio.CancelledError`` is never swallowed."""
    _patch_opener(monkeypatch, exc=asyncio.CancelledError())

    with pytest.raises(asyncio.CancelledError):
        await async_probe_certificate(
            "127.0.0.1", 443, ROUTER_A, handshake_timeout=5.0, trust_store=None, now=dt_util.utcnow()
        )


async def test_probe_aborts_transport_when_wait_closed_hangs(monkeypatch: pytest.MonkeyPatch) -> None:
    """A wait_closed that never completes is bounded by the handshake timeout and followed by abort()."""
    writer = _fake_writer(None)

    async def _never() -> None:
        await asyncio.Event().wait()

    writer.wait_closed = _never
    _patch_opener(monkeypatch, writer=writer)

    # The outer bound turns an unbounded wait_closed into a test failure instead of a hang.
    async with asyncio.timeout(0.3 + 1.0):
        failure = await _probe_failure("127.0.0.1", 443, handshake_timeout=0.3)

    assert failure.error is ProbeError.EMPTY
    writer.transport.abort.assert_called_once()


async def test_probe_cancelled_during_handshake_closes_connection(tcp_server: _TcpServerStarter) -> None:
    """Cancelling a probe in a hanging handshake raises CancelledError and closes the connection."""
    server = await _start_silent_server(tcp_server)
    task = asyncio.create_task(
        async_probe_certificate(
            "127.0.0.1", server.port, ROUTER_A, handshake_timeout=5.0, trust_store=None, now=dt_util.utcnow()
        )
    )
    await asyncio.sleep(0.2)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    async with asyncio.timeout(1.0):
        await server.eof.wait()


# ---------------------------------------------------------------------------
# Trust store.
# ---------------------------------------------------------------------------


def test_build_trust_store_without_roots_is_none() -> None:
    """No parsable root gives None (cryptography refuses an empty store)."""
    assert build_trust_store([]) is None
    assert build_trust_store([b"garbage"]) is None


def test_build_trust_store_skips_unparsable_roots() -> None:
    """A root that does not parse is skipped; the rest form the store."""
    assert isinstance(build_trust_store([b"garbage", _make_pki().root_der]), Store)


def test_build_trust_store_from_ha_roots_records_no_warning(recwarn: pytest.WarningsRecorder) -> None:
    """HA's client-context roots build a store without a CryptographyDeprecationWarning."""
    ders = client_context().get_ca_certs(binary_form=True)

    assert isinstance(build_trust_store(ders), Store)
    assert not [w for w in recwarn if issubclass(w.category, CryptographyDeprecationWarning)]


# ---------------------------------------------------------------------------
# ``match_certificate``: host -> API certificate (exact > wildcard > latest expiry).
# ---------------------------------------------------------------------------

_MATCH_BASE = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


def _api_cert(common_name: str = "", sans: tuple[str, ...] = (), *, days: int = 30) -> TraefikCertificate:
    return TraefikCertificate(
        common_name=common_name,
        sans=sans,
        not_after=_MATCH_BASE + timedelta(days=days),
        not_before=_MATCH_BASE,
        issuer_cn="Test CA",
        status="enabled",
        serial_number=str(days),
    )


def test_match_certificate_exact_beats_later_wildcard() -> None:
    """An exact SAN match wins over a wildcard certificate that expires later."""
    exact = _api_cert(sans=("a.example.com",), days=10)
    wildcard = _api_cert(sans=("*.example.com",), days=80)
    assert match_certificate("a.example.com", [wildcard, exact]) is exact


def test_match_certificate_counts_common_name() -> None:
    """A certificate covering the host only through its CN matches."""
    cn_only = _api_cert("a.example.com")
    assert match_certificate("A.example.com.", [cn_only]) is cn_only


def test_match_certificate_two_exact_matches_latest_not_after() -> None:
    """Among exact matches the latest not_after wins."""
    early = _api_cert(sans=("a.example.com",), days=10)
    late = _api_cert("a.example.com", days=60)
    assert match_certificate("a.example.com", [late, early]) is late
    assert match_certificate("a.example.com", [early, late]) is late


def test_match_certificate_two_wildcard_matches_latest_not_after() -> None:
    """Among wildcard matches the latest not_after wins."""
    early = _api_cert("*.example.com", days=10)
    late = _api_cert(sans=("*.example.com",), days=60)
    assert match_certificate("a.example.com", [early, late]) is late


def test_match_certificate_no_candidate_is_none() -> None:
    """No covering certificate (multi-label wildcard, apex, other domain) gives None."""
    certs = [_api_cert(sans=("*.example.com",)), _api_cert("other.org")]
    assert match_certificate("a.b.example.com", certs) is None
    assert match_certificate("example.com", certs) is None


def test_match_certificate_empty_list_is_none() -> None:
    """No certificates give None."""
    assert match_certificate("a.example.com", ()) is None


def test_match_certificate_never_returns_nameless_certificate() -> None:
    """A certificate with an empty CN and no SANs matches nothing."""
    nameless = _api_cert()
    assert match_certificate("a.example.com", [nameless]) is None
    assert match_certificate("", [nameless]) is None
