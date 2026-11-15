"""Read the certificate a TLS server presents, without threads and without trusting it.

``async_probe_certificate`` performs one native asyncio handshake with a
shared ``CERT_NONE`` client context, so expired, self-signed and
private-CA certificates are read as well. The connect address and the SNI
name are separate: the probe connects to the Traefik host and asks for the
router hostname. Nothing is sent after the handshake; the connection is
closed right away.

The DER leaf is parsed with ``cryptography`` into a ``TraefikCertificate``.
Trust is decided offline: ``chain_verified`` validates the presented chain
against a ``cryptography`` trust store at a given time for the SNI host.

``match_certificate`` maps a hostname to the certificate covering it in a
list read from the Traefik API.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import ssl
import warnings
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from cryptography import x509
from cryptography.utils import CryptographyDeprecationWarning
from cryptography.x509.oid import NameOID
from cryptography.x509.verification import PolicyBuilder, Store, VerificationError

from .models import TraefikCertificate


class ProbeError(StrEnum):
    """Closed set of probe failure classes."""

    TIMEOUT = "timeout"
    SSL = "ssl"
    DNS = "dns"
    REFUSED = "refused"
    OSERROR = "oserror"
    PARSE = "parse"
    EMPTY = "empty"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ProbedCertificate:
    """The leaf a server presented.

    ``verified`` is True only when the presented chain validates against
    the trust store at the probe time for the SNI host. ``san_mismatch``
    is True when neither a SAN nor the CN covers the SNI host.
    """

    certificate: TraefikCertificate
    verified: bool
    san_mismatch: bool


@dataclass(frozen=True, slots=True)
class ProbeFailure:
    """A failed probe; ``detail`` is meant for debug logs only."""

    error: ProbeError
    detail: str


type ProbeResult = ProbedCertificate | ProbeFailure

# One client context for every probe: no certificate or CA is loaded into
# it, so building it does no disk I/O, and any certificate handshakes.
_PROBE_CONTEXT = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
_PROBE_CONTEXT.check_hostname = False
_PROBE_CONTEXT.verify_mode = ssl.CERT_NONE


def build_trust_store(ders: Iterable[bytes]) -> Store | None:
    """Build a ``cryptography`` trust store from DER root certificates.

    Roots that do not parse are skipped. Some real roots carry serial
    number 0, which ``cryptography`` reports with a deprecation warning;
    the warning is suppressed while loading. Returns None when no root
    parses (``cryptography`` refuses an empty store).
    """
    roots: list[x509.Certificate] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CryptographyDeprecationWarning)
        for der in ders:
            try:
                roots.append(x509.load_der_x509_certificate(der))
            except ValueError:
                continue
    return Store(roots) if roots else None


def _first_cn(name: x509.Name) -> str | None:
    for attribute in name.get_attributes_for_oid(NameOID.COMMON_NAME):
        value = attribute.value
        return value if isinstance(value, str) else value.decode("utf-8", "replace")
    return None


def certificate_from_der(der: bytes) -> TraefikCertificate:
    """Parse a DER certificate into a ``TraefikCertificate`` (``status`` None).

    ``sans`` holds the DNS names followed by the IP addresses of the SAN
    extension. Every parse problem raises ``ValueError``.
    """
    try:
        cert = x509.load_der_x509_certificate(der)
        try:
            san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        except x509.ExtensionNotFound:
            sans: tuple[str, ...] = ()
        else:
            sans = (
                *san.get_values_for_type(x509.DNSName),
                *(str(ip) for ip in san.get_values_for_type(x509.IPAddress)),
            )
        return TraefikCertificate(
            common_name=_first_cn(cert.subject) or "",
            sans=sans,
            not_after=cert.not_valid_after_utc,
            not_before=cert.not_valid_before_utc,
            issuer_cn=_first_cn(cert.issuer),
            status=None,
            serial_number=str(cert.serial_number),
        )
    except ValueError:
        raise
    except Exception as err:
        raise ValueError(f"certificate parse failed: {type(err).__name__}") from err


def _verification_subject(host: str) -> x509.DNSName | x509.IPAddress:
    """Return an IPAddress subject for an IP literal, else a DNSName."""
    try:
        return x509.IPAddress(ipaddress.ip_address(host))
    except ValueError:
        return x509.DNSName(host)


def chain_verified(chain: Sequence[bytes], host: str, store: Store | None, now: datetime) -> bool:
    """Return True when the DER ``chain`` (leaf first) validates for ``host`` at ``now``.

    Intermediates that do not parse are ignored. A missing store, an
    unparsable leaf or any verification error gives False.
    """
    if store is None or not chain:
        return False
    try:
        leaf = x509.load_der_x509_certificate(chain[0])
        intermediates: list[x509.Certificate] = []
        for der in chain[1:]:
            try:
                intermediates.append(x509.load_der_x509_certificate(der))
            except ValueError:
                continue
        verifier = PolicyBuilder().store(store).time(now).build_server_verifier(_verification_subject(host))
        verifier.verify(leaf, intermediates)
    except VerificationError, ValueError:
        return False
    return True


# Most specific first: TimeoutError, SSLError and gaierror are OSError
# subclasses, so each must be checked before the generic OSError.
_ERROR_CLASSES: Final[tuple[tuple[type[BaseException], ProbeError], ...]] = (
    (TimeoutError, ProbeError.TIMEOUT),
    (ssl.SSLError, ProbeError.SSL),
    (socket.gaierror, ProbeError.DNS),
    (ConnectionRefusedError, ProbeError.REFUSED),
    (OSError, ProbeError.OSERROR),
)


def _classify(err: Exception) -> ProbeFailure:
    """Map an exception to exactly one ``ProbeError`` class."""
    detail = f"{type(err).__name__}: {err}"
    for exc_type, error in _ERROR_CLASSES:
        if isinstance(err, exc_type):
            return ProbeFailure(error, detail)
    return ProbeFailure(ProbeError.UNKNOWN, detail)


def _read_presented(writer: asyncio.StreamWriter, sni: str, trust_store: Store | None, now: datetime) -> ProbeResult:
    """Read and judge the certificate of an established probe connection."""
    ssl_object = writer.get_extra_info("ssl_object")
    der = ssl_object.getpeercert(binary_form=True) if ssl_object is not None else None
    if not der:
        return ProbeFailure(ProbeError.EMPTY, "no peer certificate")
    try:
        certificate = certificate_from_der(der)
    except ValueError as err:
        return ProbeFailure(ProbeError.PARSE, f"{type(err).__name__}: {err}")
    chain = list(ssl_object.get_unverified_chain() or []) or [der]
    names = (*certificate.sans, certificate.common_name) if certificate.common_name else certificate.sans
    return ProbedCertificate(
        certificate=certificate,
        verified=chain_verified(chain, sni, trust_store, now),
        san_mismatch=not _hostname_matches_san(sni, names),
    )


async def _close_writer(writer: asyncio.StreamWriter, close_timeout: float) -> None:
    """Close the probe connection; abort it when the TLS shutdown does not finish in time."""
    writer.close()
    try:
        async with asyncio.timeout(close_timeout):
            await writer.wait_closed()
    except asyncio.CancelledError:
        writer.transport.abort()
        raise
    except Exception:  # TimeoutError, OSError or any other close error: never raise from the probe
        writer.transport.abort()


async def async_probe_certificate(
    connect_host: str,
    port: int,
    sni: str,
    *,
    handshake_timeout: float,
    trust_store: Store | None,
    now: datetime,
) -> ProbeResult:
    """Handshake with ``connect_host:port`` using SNI ``sni`` and read the presented leaf.

    Never sends application data. Returns ``ProbedCertificate`` for any
    certificate that handshakes (expired, self-signed and untrusted ones
    included) and ``ProbeFailure`` otherwise; the only exception that
    propagates is ``asyncio.CancelledError``. The connection is closed on
    every path, bounded by ``handshake_timeout``.
    """
    try:
        async with asyncio.timeout(handshake_timeout):
            _reader, writer = await asyncio.open_connection(connect_host, port, ssl=_PROBE_CONTEXT, server_hostname=sni)
    except Exception as err:
        return _classify(err)
    try:
        return _read_presented(writer, sni, trust_store, now)
    except Exception as err:
        return _classify(err)
    finally:
        await _close_writer(writer, handshake_timeout)


# Read-only translation table (no mutable module-level dict).
_ASCII_LOWER: Final = MappingProxyType(str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"))


def _normalize_name(name: str) -> str:
    """ASCII-lowercase ``name`` and drop one trailing dot (no Unicode normalization)."""
    return name.translate(_ASCII_LOWER).removesuffix(".")


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _hostname_matches_san(host: str, names: Iterable[str]) -> bool:
    """Return True when a certificate name in ``names`` covers ``host`` (RFC 6125 §6.4.3).

    Names compare ASCII-case-insensitively with one trailing dot removed;
    no Unicode normalization is applied, so a U-label never equals an
    A-label. A name ``*.<domain>`` covers exactly one label: the host's
    first label must be non-empty and the rest of the host must equal
    ``<domain>`` (so not ``a.b.<domain>``, not the bare ``<domain>``). Any
    other name, including a partial-label wildcard such as
    ``f*.example.com``, matches only by equality. An IP-literal host only
    matches an equal name.
    """
    wanted = _normalize_name(host)
    label, _, rest = wanted.partition(".")
    wildcard_ok = bool(label and rest) and not _is_ip_literal(wanted)
    for name in names:
        candidate = _normalize_name(name)
        if candidate == wanted:
            return True
        if wildcard_ok and candidate.startswith("*.") and rest == candidate[2:]:
            return True
    return False


def match_certificate(host: str, certificates: Sequence[TraefikCertificate]) -> TraefikCertificate | None:
    """Return the certificate that covers ``host``, or None.

    Candidate names are a certificate's SANs plus its CN. An exact name
    match beats a single-label wildcard match; among equal matches the
    latest ``not_after`` wins.
    """
    wanted = _normalize_name(host)
    best: TraefikCertificate | None = None
    best_rank = 0
    for certificate in certificates:
        names = (*certificate.sans, certificate.common_name) if certificate.common_name else certificate.sans
        if any(_normalize_name(name) == wanted for name in names):
            rank = 2
        elif _hostname_matches_san(host, names):
            rank = 1
        else:
            continue
        if best is None or rank > best_rank or (rank == best_rank and certificate.not_after > best.not_after):
            best, best_rank = certificate, rank
    return best
