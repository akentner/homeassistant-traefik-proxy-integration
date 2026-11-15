"""Test certificate factory built on ``cryptography`` (bundled with Home Assistant).

Every certificate carries the extensions the ``cryptography`` path
verifier requires for a chain to validate: CA and intermediate
certificates have a critical ``BasicConstraints(ca=True)``, a critical
``KeyUsage(key_cert_sign, crl_sign)`` and a ``SubjectKeyIdentifier``;
leaves have a ``SubjectAlternativeName``, an ``AuthorityKeyIdentifier``,
``BasicConstraints(ca=False)`` and ``ExtendedKeyUsage(serverAuth)``.
Keys are EC P-256 (they generate in milliseconds).
"""

from __future__ import annotations

import ipaddress
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

type Issued = tuple[x509.Certificate, ec.EllipticCurvePrivateKey]

_CA_KEY_USAGE = x509.KeyUsage(
    digital_signature=False,
    content_commitment=False,
    key_encipherment=False,
    data_encipherment=False,
    key_agreement=False,
    key_cert_sign=True,
    crl_sign=True,
    encipher_only=False,
    decipher_only=False,
)


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _general_name(name: str) -> x509.GeneralName:
    """Return an IPAddress for an IP literal, else a DNSName."""
    try:
        return x509.IPAddress(ipaddress.ip_address(name))
    except ValueError:
        return x509.DNSName(name)


def _builder(
    subject: x509.Name,
    issuer: x509.Name,
    key: ec.EllipticCurvePrivateKey,
    *,
    not_before: datetime,
    not_after: datetime,
) -> x509.CertificateBuilder:
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
    )


def _authority_key_id(issuer_key: ec.EllipticCurvePrivateKey) -> x509.AuthorityKeyIdentifier:
    return x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key())


def make_ca(common_name: str, *, not_before: datetime, not_after: datetime) -> Issued:
    """Return a self-signed root CA."""
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (
        _builder(_name(common_name), _name(common_name), key, not_before=not_before, not_after=not_after)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(_CA_KEY_USAGE, critical=True)
        .sign(key, hashes.SHA256())
    )
    return cert, key


def make_intermediate(common_name: str, issuer: Issued, *, not_before: datetime, not_after: datetime) -> Issued:
    """Return an intermediate CA signed by ``issuer``."""
    issuer_cert, issuer_key = issuer
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (
        _builder(_name(common_name), issuer_cert.subject, key, not_before=not_before, not_after=not_after)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(_CA_KEY_USAGE, critical=True)
        .add_extension(_authority_key_id(issuer_key), critical=False)
        .sign(issuer_key, hashes.SHA256())
    )
    return cert, key


def _leaf(
    names: Sequence[str],
    subject: x509.Name,
    issuer_name: x509.Name,
    key: ec.EllipticCurvePrivateKey,
    signing_key: ec.EllipticCurvePrivateKey,
    *,
    not_before: datetime,
    not_after: datetime,
) -> x509.Certificate:
    return (
        _builder(subject, issuer_name, key, not_before=not_before, not_after=not_after)
        .add_extension(x509.SubjectAlternativeName([_general_name(name) for name in names]), critical=False)
        .add_extension(_authority_key_id(signing_key), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(signing_key, hashes.SHA256())
    )


def make_leaf(
    names: Sequence[str],
    issuer: Issued,
    *,
    not_before: datetime,
    not_after: datetime,
    common_name: str | None = None,
) -> Issued:
    """Return a server leaf for ``names`` (DNS or IP SANs) signed by ``issuer``.

    The subject CN is ``common_name``, else the first name.
    """
    issuer_cert, issuer_key = issuer
    key = ec.generate_private_key(ec.SECP256R1())
    subject = _name(common_name if common_name is not None else names[0])
    cert = _leaf(names, subject, issuer_cert.subject, key, issuer_key, not_before=not_before, not_after=not_after)
    return cert, key


def make_self_signed(names: Sequence[str], *, not_before: datetime, not_after: datetime) -> Issued:
    """Return a self-signed server leaf for ``names``."""
    key = ec.generate_private_key(ec.SECP256R1())
    subject = _name(names[0])
    cert = _leaf(names, subject, subject, key, key, not_before=not_before, not_after=not_after)
    return cert, key


def write_pem(
    directory: Path,
    stem: str,
    chain: Sequence[x509.Certificate],
    key: ec.EllipticCurvePrivateKey,
) -> tuple[Path, Path]:
    """Write ``chain`` (leaf first) and the unencrypted PKCS8 ``key`` as PEM files.

    Returns ``(chain_path, key_path)`` for ``ssl.SSLContext.load_cert_chain``.
    """
    chain_path = directory / f"{stem}-chain.pem"
    key_path = directory / f"{stem}-key.pem"
    chain_path.write_bytes(b"".join(cert.public_bytes(serialization.Encoding.PEM) for cert in chain))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return chain_path, key_path
