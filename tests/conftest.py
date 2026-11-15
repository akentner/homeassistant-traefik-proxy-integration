"""Pytest fixtures for Traefik integration tests."""

from __future__ import annotations

import asyncio
import contextlib
import copy
import json
import ssl
import sys
import threading
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
from pytest_homeassistant.common import MockConfigEntry

# Ensure custom_components is importable from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from custom_components.traefik_proxy.cert_coordinator import CertSource, HostCertState
from custom_components.traefik_proxy.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL, DOMAIN
from custom_components.traefik_proxy.models import (
    TraefikCertificate,
    TraefikSnapshot,
    TraefikState,
    parse_entrypoints,
    parse_middlewares,
    parse_rawdata,
    parse_routers,
    parse_services,
    parse_version,
)
from custom_components.traefik_proxy.tls import ProbeError, ProbeFailure
from tests.certgen import warm_up_datetime_types

# Resolve cryptography's cached datetime class before any test freezes time.
warm_up_datetime_types()

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
    # The first cert cycle runs as a background task of the entry.
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.state is ConfigEntryState.LOADED
    return entry


def entity_id_for(hass: HomeAssistant, domain: str, unique_id: str) -> str:
    """Return the entity_id registered for ``unique_id`` in ``domain``; fail when there is none."""
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique_id)
    assert entity_id is not None, f"no {domain} entity with unique_id {unique_id}"
    return entity_id


@pytest.fixture
def mock_tls_probe() -> Iterator[AsyncMock]:
    """Replace the cert coordinator's TLS probe so no DNS lookup or socket is opened.

    Every probe fails with ``ProbeError.UNKNOWN``.
    """
    with patch(
        "custom_components.traefik_proxy.cert_coordinator.async_probe_certificate",
        AsyncMock(return_value=ProbeFailure(ProbeError.UNKNOWN, "probe disabled in tests")),
    ) as probe:
        yield probe


def make_cert_state(
    host: str,
    *,
    days: int | None = None,
    now: datetime,
    source: CertSource = CertSource.PROBE,
    error: str | None = None,
    failures: int = 0,
    verified: bool | None = None,
    port: int | None = 443,
) -> HostCertState:
    """Build a ``HostCertState`` for ``host``; with ``days`` it carries a certificate expiring ``days`` after ``now``.

    The certificate covers ``host`` (CN and SAN); ``fetched_at`` is ``now``
    with a certificate and None without one.
    """
    certificate = (
        None
        if days is None
        else TraefikCertificate(
            common_name=host,
            sans=(host,),
            not_after=now + timedelta(days=days),
            not_before=now - timedelta(days=1),
            issuer_cn="Test CA",
            status=None,
            serial_number="1",
        )
    )
    return HostCertState(
        host=host,
        source=source,
        certificate=certificate,
        verified=verified,
        san_mismatch=None if certificate is None else False,
        port=port,
        error=error,
        failures=failures,
        fetched_at=None if certificate is None else now,
    )


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


@dataclass
class TlsServer:
    """A running ``tls_server`` instance.

    ``received`` holds, per finished connection, every byte the client
    sent after the handshake (``b""`` when it sent nothing).
    """

    port: int = 0
    received: list[bytes] = field(default_factory=list)

    async def wait_connections(self, count: int, *, limit: float = 10.0) -> None:
        """Yield to the loop until ``count`` connections have finished, for at most ``limit`` seconds.

        Uses ``asyncio.sleep(0)`` only, so it also works under ``freezer``
        (the loop clock is frozen there and timed sleeps never return). The
        limit is wall-clock time measured by a thread timer, which the frozen
        clock does not affect.
        """
        deadline = threading.Event()
        timer = threading.Timer(limit, deadline.set)
        timer.daemon = True
        timer.start()
        try:
            while not deadline.is_set():
                if len(self.received) >= count:
                    return
                await asyncio.sleep(0)
        finally:
            timer.cancel()
        raise AssertionError(f"expected {count} finished connections, got {len(self.received)}")


type TlsServerStarter = Callable[..., Awaitable[TlsServer]]

# Wall-clock limit of one test that uses ``tls_server``.
TLS_TEST_WALL_CLOCK_LIMIT = 60.0


@contextlib.contextmanager
def wall_clock_watchdog(loop: asyncio.AbstractEventLoop, seconds: float) -> Iterator[threading.Event]:
    """Cancel every task of ``loop`` when the block runs longer than ``seconds`` of wall-clock time.

    Under ``freezer`` the loop clock stands still, so ``asyncio.timeout``
    never expires and a stalled handshake would hang the test for ever. A
    thread timer is not affected by the frozen clock; when it fires, every
    task of ``loop`` is cancelled from the loop thread and the yielded event
    is set, so the test fails instead of hanging.
    """
    fired = threading.Event()

    def _cancel_all() -> None:
        for task in asyncio.all_tasks(loop):
            task.cancel()

    def _fire() -> None:
        fired.set()
        loop.call_soon_threadsafe(_cancel_all)

    timer = threading.Timer(seconds, _fire)
    timer.daemon = True
    timer.start()
    try:
        yield fired
    finally:
        timer.cancel()


@pytest_asyncio.fixture
async def tls_server(socket_enabled: None) -> AsyncIterator[TlsServerStarter]:
    """Start asyncio TLS servers on 127.0.0.1 that pick the certificate by SNI.

    Yields ``start(certs, *, default)``: ``certs`` maps an SNI name to the
    ``(chain_pem, key_pem)`` pair of ``tests.certgen.write_pem``; a handshake
    with an unknown or missing SNI name gets ``certs[default]``. One server
    context is built per entry up front and the SNI callback only assigns
    ``sslobj.context`` (never load a chain inside the callback). Every
    connection is read until EOF and its bytes appended to ``received``.
    Teardown closes every started server. A test that runs longer than
    ``TLS_TEST_WALL_CLOCK_LIMIT`` seconds of wall-clock time is cancelled
    and failed (:func:`wall_clock_watchdog`), also under ``freezer``.
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

    with wall_clock_watchdog(asyncio.get_running_loop(), TLS_TEST_WALL_CLOCK_LIMIT) as fired:
        yield start
    for server in servers:
        server.close()
        server.close_clients()
    if fired.is_set():
        pytest.fail(f"test exceeded the tls_server wall-clock limit of {TLS_TEST_WALL_CLOCK_LIMIT} s")
        await server.wait_closed()
