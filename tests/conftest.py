"""Pytest fixtures for Traefik integration tests."""

from __future__ import annotations

import asyncio
import contextlib
import copy
import json
import socket
import ssl
import subprocess
import sys
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Ensure custom_components is importable from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

# Pre-import the project's custom_components so the production
# ``tls`` module is bound in this conftest's frame BEFORE the
# pytest-homeassistant-custom-component namespace hijack of the
# ``custom_components`` name takes effect. Later in-fixture
# ``from custom_components.traefik_proxy import tls`` references then resolve
# to the real production module rather than the testing_config stub
# that ships with ``pytest_homeassistant_custom_component``.
from custom_components.traefik_proxy import tls as _tls_module  # pre-import for in-fixture patching
from custom_components.traefik_proxy.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL, DOMAIN
from custom_components.traefik_proxy.models import (
    TraefikSnapshot,
    TraefikState,
    parse_entrypoints,
    parse_middlewares,
    parse_rawdata,
    parse_routers,
    parse_services,
    parse_version,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Base URL of the Traefik API in config entries built by the tests.
MOCK_URL = "https://traefik.example.com:8080"

# Real Traefik captures (tests/traefik/capture.py), one directory per generation.
FIXTURE_VERSIONS = ("v2.11", "v3.7")

# 88 days before the notAfter (2027-02-12T00:17:40Z) of the v3.7 certificates capture.
CERT_FIXTURE_NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
# Validity of the certificates the default stubs serve, counted from the clock.
STUB_CERT_VALIDITY = timedelta(days=3650)

_CERT_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def load_fixture(version: str, name: str) -> Any:
    """Return the parsed JSON of a captured fixture file."""
    return json.loads((FIXTURES_DIR / version / name).read_text(encoding="utf-8"))


def load_paginated(version: str, kind: str) -> tuple[list[Any], list[str | None]]:
    """Concatenate the captured list pages of ``kind`` in page order.

    Returns the items of all pages and the recorded ``X-Next-Page`` header
    value of each page (``None`` when the header was absent).
    """
    index = load_fixture(version, "pages/index.json")
    pages = sorted(index[kind], key=lambda page: page["page"])
    items: list[Any] = []
    next_pages: list[str | None] = []
    for page in pages:
        items.extend(load_fixture(version, f"pages/{page['file']}"))
        next_pages.append(page.get("x_next_page"))
    return items, next_pages


def _rebased_certificates(version: str) -> list[dict[str, Any]] | None:
    """Return a copy of the capture's certificates with dates relative to the clock.

    ``notBefore`` becomes now - 1 day and ``notAfter`` now + ``STUB_CERT_VALIDITY``;
    every other field is unchanged. None when the capture has no
    certificates.json (Traefik < 3.7).
    """
    if not (FIXTURES_DIR / version / "certificates.json").exists():
        return None
    now = dt_util.utcnow()
    certificates: list[dict[str, Any]] = copy.deepcopy(load_fixture(version, "certificates.json"))
    for certificate in certificates:
        certificate["notBefore"] = (now - timedelta(days=1)).strftime(_CERT_TIMESTAMP_FORMAT)
        certificate["notAfter"] = (now + STUB_CERT_VALIDITY).strftime(_CERT_TIMESTAMP_FORMAT)
    return certificates


def _stub_certificates(aioclient_mock: Any, base_url: str, version: str, certificates: Any) -> None:
    """Serve ``/api/certificates``: ``certificates`` when given, else the re-based capture, else 404."""
    payload = certificates if certificates is not None else _rebased_certificates(version)
    if payload is None:
        aioclient_mock.get(f"{base_url}/api/certificates", status=404)
    else:
        aioclient_mock.get(f"{base_url}/api/certificates", json=payload)


def frozen_v37_certificates(freezer: Any) -> list[dict[str, Any]]:
    """Move the clock to ``CERT_FIXTURE_NOW`` and return the unmodified v3.7 certificates capture.

    The only way an integration test gets the capture's fixed dates: the
    default stubs serve them re-based on the clock.
    """
    freezer.move_to(CERT_FIXTURE_NOW)
    certificates: list[dict[str, Any]] = load_fixture("v3.7", "certificates.json")
    return certificates


def make_snapshot(
    *,
    routers: Iterable[dict[str, Any]] = (),
    services: Iterable[dict[str, Any]] = (),
    middlewares: Iterable[dict[str, Any]] = (),
    entrypoints: Iterable[dict[str, Any]] = (),
    version: dict[str, Any] | None = None,
) -> TraefikSnapshot:
    """Build a snapshot from raw list-form items (each with ``name``) via the real parsers.

    ``version`` is a raw ``/api/version`` payload; it defaults to the v3.7 capture.
    """
    state = TraefikState(
        routers=parse_routers(list(routers)),
        services=parse_services(list(services)),
        middlewares=parse_middlewares(list(middlewares)),
    )
    return TraefikSnapshot.build(
        version=parse_version(version if version is not None else load_fixture("v3.7", "version.json")),
        entrypoints=parse_entrypoints(list(entrypoints)),
        state=state,
    )


def snapshot_from_fixture(version: str) -> TraefikSnapshot:
    """Build the snapshot of a whole capture (rawdata, version, entrypoints)."""
    return TraefikSnapshot.build(
        version=parse_version(load_fixture(version, "version.json")),
        entrypoints=parse_entrypoints(load_fixture(version, "entrypoints.json")),
        state=parse_rawdata(load_fixture(version, "rawdata.json")),
    )


def stub_traefik(
    aioclient_mock: Any,
    *,
    version: str = "v3.7",
    base_url: str = MOCK_URL,
    rawdata: Any = None,
    version_payload: Any = None,
    entrypoints: Any = None,
    certificates: Any = None,
) -> None:
    """Serve a Traefik through ``/api/version``, ``/api/entrypoints``, ``/api/rawdata`` and ``/api/certificates``.

    Each payload defaults to the capture of ``version``; an explicit value
    replaces it (``rawdata={}`` is an empty Traefik). ``/api/certificates``
    serves the capture's certificates re-based on the clock at registration
    time (see ``_rebased_certificates``), so no default setup depends on the
    wall clock; a capture without certificates.json (v2.11) answers 404.
    The first matching mock wins, so a test overrides an endpoint by
    registering its own mock before calling this helper.
    """
    payloads = {
        "version": version_payload if version_payload is not None else load_fixture(version, "version.json"),
        "entrypoints": entrypoints if entrypoints is not None else load_fixture(version, "entrypoints.json"),
        "rawdata": rawdata if rawdata is not None else load_fixture(version, "rawdata.json"),
    }
    for name, payload in payloads.items():
        aioclient_mock.get(f"{base_url}/api/{name}", json=payload)
    _stub_certificates(aioclient_mock, base_url, version, certificates)


def stub_traefik_paginated(aioclient_mock: Any, *, version: str = "v3.7", base_url: str = MOCK_URL) -> None:
    """Serve a capture through the version, entrypoints and paginated list endpoints.

    ``/api/rawdata`` answers 404, so every scenario exercises the client's
    paginated fallback. Every list page is registered with its recorded
    ``per_page``/``page`` query and ``X-Next-Page`` header, so the client's
    page size must equal the index ``per_page`` (tests monkeypatch
    ``api.DEFAULT_PAGE_SIZE``). ``/api/certificates`` (one page, registered
    without query) serves the re-based capture or 404, as in ``stub_traefik``.
    """
    aioclient_mock.get(f"{base_url}/api/rawdata", status=404)
    aioclient_mock.get(f"{base_url}/api/version", json=load_fixture(version, "version.json"))
    aioclient_mock.get(f"{base_url}/api/entrypoints", json=load_fixture(version, "entrypoints.json"))
    _stub_certificates(aioclient_mock, base_url, version, None)
    index = load_fixture(version, "pages/index.json")
    per_page = index["per_page"]
    for kind in ("routers", "services", "middlewares"):
        for page in index[kind]:
            next_page = page.get("x_next_page")
            aioclient_mock.get(
                f"{base_url}/api/http/{kind}",
                params={"per_page": per_page, "page": page["page"]},
                json=load_fixture(version, f"pages/{page['file']}"),
                headers={"X-Next-Page": next_page} if next_page is not None else None,
            )


def rawdata_copy(version: str = "v3.7") -> dict[str, Any]:
    """Return a deep copy of the capture's rawdata, safe to mutate."""
    return copy.deepcopy(load_fixture(version, "rawdata.json"))


def restub_traefik(aioclient_mock: Any, **kwargs: Any) -> None:
    """Drop every registered mock and serve a Traefik again through ``stub_traefik``."""
    aioclient_mock.clear_requests()
    stub_traefik(aioclient_mock, **kwargs)


def make_traefik_entry(*, options: dict[str, Any] | None = None, **kwargs: Any) -> MockConfigEntry:
    """Build a Traefik config entry for ``MOCK_URL``; ``kwargs`` override MockConfigEntry fields."""
    params: dict[str, Any] = {
        "domain": DOMAIN,
        "title": "Traefik",
        "data": {CONF_URL: MOCK_URL, CONF_API_KEY: "k", CONF_VERIFY_SSL: True},
        "unique_id": "traefik.example.com",
        "options": options or {},
    }
    params.update(kwargs)
    return MockConfigEntry(**params)


async def setup_traefik_entry(
    hass: HomeAssistant,
    aioclient_mock: Any,
    entry: MockConfigEntry | None = None,
    *,
    version: str = "v3.7",
    rawdata: Any = None,
) -> MockConfigEntry:
    """Serve a capture, set up ``entry`` (a fresh one by default) and assert it loaded."""
    stub_traefik(aioclient_mock, version=version, rawdata=rawdata)
    if entry is None:
        entry = make_traefik_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


def entity_id_for(hass: HomeAssistant, domain: str, unique_id: str) -> str:
    """Return the entity_id registered for ``unique_id`` in ``domain``; fail when there is none."""
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique_id)
    assert entity_id is not None, f"no {domain} entity with unique_id {unique_id}"
    return entity_id


@pytest.fixture
def mock_tls_probe() -> Iterator[AsyncMock]:
    """Replace the cert coordinator's TLS probe so no DNS lookup or socket is opened."""

    async def _unreachable(host: str, port: int, **_kwargs: Any) -> dict[str, Any]:
        return {"host": host, "port": port, "error": "unreachable", "detail": "probe disabled in tests"}

    with patch(
        "custom_components.traefik_proxy.cert_coordinator.fetch_cert_info_async",
        AsyncMock(side_effect=_unreachable),
    ) as probe:
        yield probe


pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def enable_custom_integrations(hass):  # type: ignore[no-untyped-def]
    """Force-reload the custom_components cache so our integration gets registered."""
    hass.data.pop("custom_components", None)
    return hass


@pytest.fixture
def mock_traefik_config_entry() -> MockConfigEntry:
    """A config entry for the Traefik integration, valid for happy-path tests."""
    return MockConfigEntry(
        domain="traefik_proxy",
        title="Traefik Proxy",
        data={
            "url": "https://traefik.example.com:8080",
            "api_key": "test-secret",
            "verify_ssl": True,
        },
        unique_id="traefik.example.com",
    )


@pytest_asyncio.fixture
async def mock_certificate_server(
    socket_enabled: None,  # NO default — required fixture, enables real socket access
    monkeypatch: pytest.MonkeyPatch,
    sni_hostname: str = "router-a.example.test",
) -> AsyncIterator[tuple[str, int, str]]:
    """Spin up a stdlib TLS server on 127.0.0.1 with a CA-signed cert.

    Yields ``(host, port, sni_hostname)`` so tests can probe
    ``fetch_cert_info("127.0.0.1", port, timeout=5.0)`` and
    ``_fetch_cert_raw(host="127.0.0.1", port=port, sni=<other-host>,
    timeout=...)`` (the latter for SNI-mismatch scenarios per spike 003).

    The cert is CA-signed in the per-test ``TemporaryDirectory``: the
    fixture generates a throwaway CA, signs the server leaf with it,
    and chains them into a single PEM for ``load_cert_chain``. The
    CA path is then monkey-patched into the production SSLContext via
    ``ssl.SSLContext.load_verify_locations`` so ``fetch_cert_info`` —
    which uses ``PROTOCOL_TLS_CLIENT`` + ``load_default_certs()`` —
    can complete the handshake against the test cert chain. Without
    this injection, the verifier rejects the self-signed CA root and
    the test surfaces ``oserror`` instead of a successful handshake.

    Requires the ``openssl`` CLI on PATH (the standard on every
    supported CI runner). Cleanup is automatic: ``tempfile.TemporaryDirectory``
    removes the cert + key at fixture exit, ``server.close()`` +
    ``wait_closed()`` shuts down the asyncio server, and
    ``monkeypatch.undo()`` cleans up the SSL context monkey-patch.
    """
    with tempfile.TemporaryDirectory() as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        ca_key = tmpdir / "ca.key"
        ca_cert = tmpdir / "ca.crt"
        server_key = tmpdir / "server.key"
        server_csr = tmpdir / "server.csr"
        server_ext = tmpdir / "server.ext"
        server_cert = tmpdir / "server.crt"
        chain_pem = tmpdir / "chain.pem"

        server_ext.write_text(f"subjectAltName=DNS:{sni_hostname}\n")

        # Run openssl in a worker thread so the blocking subprocess doesn't
        # stall the event loop (ASYNC221 — async functions should not
        # invoke blocking OS calls). All openssl calls happen sequentially
        # in the same thread so the cert chain references resolve.
        await asyncio.to_thread(
            _generate_ca_signed_cert,
            ca_key,
            ca_cert,
            server_key,
            server_csr,
            server_cert,
            server_ext,
            chain_pem,
            sni_hostname,
        )

        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(str(chain_pem), str(server_key))

        # Inject the test CA into the trust store the production SSLContext
        # uses. The production ``_open_tls_connection`` calls
        # ``ctx.load_default_certs()`` which pulls from the system CA
        # bundle — that bundle does NOT include our throwaway CA. We
        # patch the production entry point to ALSO load the test CA via
        # ``load_verify_locations`` so the handshake succeeds.
        _original_open = _tls_module._open_tls_connection

        def _patched_open_tls_connection(
            host: str, port: int, *, server_hostname: str, timeout: float
        ) -> ssl.SSLSocket:
            """Wrap the production context-creation with our test CA in the trust store."""
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.load_default_certs()
            ctx.load_verify_locations(cafile=str(ca_cert))
            raw_sock = socket.create_connection((host, port), timeout=timeout)
            return ctx.wrap_socket(raw_sock, server_hostname=server_hostname)

        monkeypatch.setattr(_tls_module, "_open_tls_connection", _patched_open_tls_connection)

        server = await asyncio.start_server(
            _silence_client,
            "127.0.0.1",
            0,
            ssl=ssl_ctx,
        )
        try:
            # ``sockets`` is non-None because we explicitly bound ``127.0.0.1``.
            sockets = server.sockets or ()
            sock = sockets[0]
            port = sock.getsockname()[1]
            yield ("127.0.0.1", port, sni_hostname)
        finally:
            server.close()
            await server.wait_closed()


@dataclass
class TlsServer:
    """A running ``tls_server`` instance.

    ``received`` holds, per finished connection, every byte the client
    sent after the handshake (``b""`` when it sent nothing).
    """

    port: int = 0
    received: list[bytes] = field(default_factory=list)

    async def wait_connections(self, count: int) -> None:
        """Yield to the loop until ``count`` connections have finished.

        Uses ``asyncio.sleep(0)`` only, so it also works under ``freezer``
        (the loop clock is frozen there and timed sleeps never return).
        """
        for _ in range(10_000):
            if len(self.received) >= count:
                return
            await asyncio.sleep(0)
        raise AssertionError(f"expected {count} finished connections, got {len(self.received)}")


type TlsServerStarter = Callable[..., Awaitable[TlsServer]]


@pytest_asyncio.fixture
async def tls_server(socket_enabled: None) -> AsyncIterator[TlsServerStarter]:
    """Start asyncio TLS servers on 127.0.0.1 that pick the certificate by SNI.

    Yields ``start(certs, *, default)``: ``certs`` maps an SNI name to the
    ``(chain_pem, key_pem)`` pair of ``tests.certgen.write_pem``; a handshake
    with an unknown or missing SNI name gets ``certs[default]``. One server
    context is built per entry up front and the SNI callback only assigns
    ``sslobj.context`` (never load a chain inside the callback). Every
    connection is read until EOF and its bytes appended to ``received``.
    Teardown closes every started server.
    """
    assert socket_enabled is None  # consumed for fixture propagation
    servers: list[asyncio.Server] = []

    async def start(certs: Mapping[str, tuple[Path, Path]], *, default: str) -> TlsServer:
        contexts: dict[str, ssl.SSLContext] = {}
        for name, (chain_pem, key_pem) in certs.items():
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(chain_pem, key_pem)
            contexts[name] = context
        default_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        default_context.load_cert_chain(*certs[default])

        def _select(sslobj: ssl.SSLObject, server_name: str | None, _context: ssl.SSLContext) -> None:
            if server_name is not None and server_name in contexts:
                sslobj.context = contexts[server_name]

        default_context.sni_callback = _select
        record = TlsServer()

        async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            data = b""
            try:
                data = await reader.read()
            except OSError:
                pass
            finally:
                record.received.append(data)
                writer.close()
                with contextlib.suppress(OSError):
                    await writer.wait_closed()

        server = await asyncio.start_server(_handle, "127.0.0.1", 0, ssl=default_context)
        servers.append(server)
        record.port = server.sockets[0].getsockname()[1]
        return record

    yield start
    for server in servers:
        server.close()
        server.close_clients()
        await server.wait_closed()


async def _silence_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Tiny no-op connection handler for the stdlib TLS server.

    The handshake handler from ``tls._fetch_cert_raw`` only reads the
    handshake bytes; once the handshake completes the client closes.
    Send a minimal HTTP/1.0 200 response so a misbehaving client doesn't
    hang on a read.
    """
    try:
        writer.write(b"HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nOK")
        await writer.drain()
    except ConnectionResetError, BrokenPipeError, OSError:
        # Client hung up after the handshake — expected.
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except OSError, RuntimeError:
            # Already closed by the peer; safe to ignore.
            pass


# ``socket`` import retained: some proxy/type-checkers warn otherwise. The
# fixture intentionally binds via ``asyncio.start_server`` rather than the
# low-level ``socket`` module so the asyncio cancel / cleanup semantics stay
# in one place.
_ = socket


def _generate_ca_signed_cert(
    ca_key: Path,
    ca_cert: Path,
    server_key: Path,
    server_csr: Path,
    server_cert: Path,
    server_ext: Path,
    chain_pem: Path,
    sni_hostname: str,
) -> None:
    """Generate a CA + sign a per-server leaf cert (runs in a worker thread).

    Synchronous so ``subprocess.run`` is the natural fit — pulled out of
    the async fixture proper to satisfy ASYNC221. Creates:

    1. A self-signed CA root (365-day validity, CN=Test CA).
    2. A server leaf signed by the CA (365-day validity, CN=sni_hostname,
       SAN=DNS:sni_hostname via ``server_ext`` config).
    3. A chained PEM ``chain_pem`` (leaf + CA) for ``ssl.SSLContext.load_cert_chain``.

    The server leaf's ``notAfter`` falls ~365d ahead of the test run
    (used by ``test_mock_tls_server_returns_CertInfo`` to assert the
    days-until-expiry window in ``tests/test_tls.py``).
    """
    # 1. CA key + self-signed CA cert.
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(ca_key),
            "-out",
            str(ca_cert),
            "-days",
            "365",
            "-nodes",
            "-subj",
            "/CN=Test CA",
        ],
        check=True,
        capture_output=True,
    )

    # 2. Server key + CSR.
    subprocess.run(
        [
            "openssl",
            "req",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(server_key),
            "-out",
            str(server_csr),
            "-nodes",
            "-subj",
            f"/CN={sni_hostname}",
        ],
        check=True,
        capture_output=True,
    )

    # 3. Sign server leaf with the CA + apply the SAN extension.
    subprocess.run(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(server_csr),
            "-CA",
            str(ca_cert),
            "-CAkey",
            str(ca_key),
            "-CAcreateserial",
            "-out",
            str(server_cert),
            "-days",
            "365",
            "-extfile",
            str(server_ext),
        ],
        check=True,
        capture_output=True,
    )

    # 4. Build the chained PEM (leaf + CA) for ``ssl.SSLContext.load_cert_chain``.
    chain_pem.write_text(server_cert.read_text() + ca_cert.read_text())
