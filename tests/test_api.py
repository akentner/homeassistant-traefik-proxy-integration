"""Contract tests for TraefikProxyApiClient.

The client runs on Home Assistant's shared aiohttp session, which the
``aioclient_mock`` fixture replaces; every request is recorded as
``(method, url, data, headers)``. Payloads come from the real v3.7 capture
through the conftest helper.

Covered: the three auth modes and their per-request header, the error
taxonomy for HTTP statuses, network exceptions and payload errors,
credential secrecy in logs / exception text / reprs, TLS verification on
every request and request host pinning.
"""

from __future__ import annotations

import ast
import asyncio
import base64
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import aiohttp
import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMockResponse

from custom_components.traefik_proxy import api
from custom_components.traefik_proxy.api import TraefikProxyApiClient, TraefikProxyApiError, TraefikProxyAuthError
from custom_components.traefik_proxy.models import parse_certificates, parse_entrypoints, parse_rawdata, parse_version
from tests.conftest import (
    CERT_FIXTURE_NOW,
    MOCK_URL,
    STUB_CERT_VALIDITY,
    frozen_v37_certificates,
    load_fixture,
    stub_traefik,
    stub_traefik_paginated,
)

API_PATH = Path(__file__).parent.parent / "custom_components" / "traefik_proxy" / "api.py"
VERSION_PATH = "/api/version"

TOKEN = "s3cret-token"
USERNAME = "capture"
PASSWORD = "pw-s3cret"
URL_USER = "harness-user"
URL_PASSWORD = "harness-pw"
USERINFO_URL = f"https://{URL_USER}:{URL_PASSWORD}@traefik.example.com:8080"


def _basic_token(username: str, password: str) -> str:
    return base64.b64encode(f"{username}:{password}".encode()).decode()


def _auth(mode: str) -> Any:
    """Build an Auth value for ``mode`` with the module's test credentials."""
    if mode == "basic":
        return api.Auth(mode=api.AuthMode.basic, username=USERNAME, password=PASSWORD)
    if mode == "bearer":
        return api.Auth(mode=api.AuthMode.bearer, token=TOKEN)
    return api.Auth()


def _client(hass, auth: Any = None, *, base_url: str = MOCK_URL, **kwargs: Any) -> TraefikProxyApiClient:  # type: ignore[no-untyped-def]
    """Build the client under test on HA's shared (mocked) session."""
    return TraefikProxyApiClient(
        async_get_clientsession(hass), base_url, auth if auth is not None else api.Auth(), **kwargs
    )


def _secret_forms() -> list[str]:
    """Every textual form a credential could leak in."""
    return [
        TOKEN,
        PASSWORD,
        f"{USERNAME}:{PASSWORD}",
        _basic_token(USERNAME, PASSWORD),
        URL_PASSWORD,
        f"{URL_USER}:{URL_PASSWORD}",
        _basic_token(URL_USER, URL_PASSWORD),
        USERINFO_URL,
    ]


# --- Auth value object -------------------------------------------------------


def test_auth_header_per_mode() -> None:
    """Each mode builds exactly its Authorization header."""
    assert api.Auth(mode=api.AuthMode.none).header() == {}
    assert api.Auth().header() == {}
    assert _auth("bearer").header() == {"Authorization": f"Bearer {TOKEN}"}
    assert _auth("basic").header() == {"Authorization": f"Basic {_basic_token(USERNAME, PASSWORD)}"}


def test_basic_header_encodes_utf8_credentials() -> None:
    """Non-ASCII basic credentials are encoded as UTF-8 (RFC 7617)."""
    auth = api.Auth(mode=api.AuthMode.basic, username="jürgen", password="pässwort")
    assert auth.header() == {"Authorization": f"Basic {_basic_token('jürgen', 'pässwort')}"}


def test_auth_mode_members() -> None:
    """AuthMode is a StrEnum with exactly none, basic and bearer."""
    assert [member.value for member in api.AuthMode] == ["none", "basic", "bearer"]
    assert api.AuthMode("bearer") is api.AuthMode.bearer


@pytest.mark.parametrize(
    ("kwargs", "field", "secret"),
    [
        pytest.param(
            {"mode": "basic", "username": "leaky:user", "password": "leaky-pw"}, "username", "leaky", id="colon"
        ),
        pytest.param({"mode": "basic", "username": "", "password": "leaky-pw"}, "username", "leaky-pw", id="no-user"),
        pytest.param({"mode": "basic", "username": "leaky-user", "password": ""}, "password", "leaky-user", id="no-pw"),
        pytest.param({"mode": "bearer"}, "token", None, id="bearer-no-token"),
        pytest.param({"mode": "bearer", "token": ""}, "token", None, id="bearer-empty"),
        pytest.param({"mode": "none", "token": "leaky-token-value"}, "token", "leaky-token-value", id="none-token"),
        pytest.param({"mode": "none", "username": "leaky-user"}, "username", "leaky-user", id="none-user"),
        pytest.param({"mode": "bearer", "token": "leaky\r\ninjected"}, "token", "injected", id="bearer-control-char"),
    ],
)
def test_auth_rejects_invalid_credentials(kwargs: dict[str, Any], field: str, secret: str | None) -> None:
    """Invalid combinations raise ValueError naming the field, never the secret."""
    kwargs = {**kwargs, "mode": api.AuthMode(kwargs["mode"])}
    with pytest.raises(ValueError, match=field) as err:
        api.Auth(**kwargs)
    if secret is not None:
        assert secret not in str(err.value)


def test_auth_repr_hides_credentials() -> None:
    """repr() of an Auth never shows the username, password or token."""
    basic = repr(api.Auth(mode=api.AuthMode.basic, username="harness-user", password="harness-pw"))
    bearer = repr(_auth("bearer"))
    assert "harness-user" not in basic
    assert "harness-pw" not in basic
    assert TOKEN not in bearer
    assert "bearer" in bearer


def test_auth_is_frozen() -> None:
    """Auth cannot be mutated after construction."""
    auth = _auth("bearer")
    with pytest.raises(AttributeError):
        auth.token = "other"  # type: ignore[misc]


# --- Per-request header and the shared session -------------------------------


@pytest.mark.parametrize("mode", ["none", "basic", "bearer"])
async def test_each_mode_sends_exactly_its_header(hass, aioclient_mock, mode: str) -> None:
    """The recorded request carries the mode's header; the shared session gets no default header."""
    aioclient_mock.get(f"{MOCK_URL}{VERSION_PATH}", json=load_fixture("v3.7", "version.json"))
    auth = _auth(mode)

    await _client(hass, auth).async_get_version()

    headers = aioclient_mock.mock_calls[0][3]
    assert headers == auth.header()
    if mode == "none":
        assert "Authorization" not in headers
    assert "Authorization" not in async_get_clientsession(hass).headers


# --- Error taxonomy ----------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "error_name"),
    [
        (401, "TraefikProxyAuthError"),
        (403, "TraefikProxyAuthError"),
        (404, "TraefikProxyNotFoundError"),
    ],
)
async def test_status_maps_to_specific_error(hass, aioclient_mock, status: int, error_name: str) -> None:
    """401/403 raise the auth error and 404 the not-found error, carrying path and status."""
    aioclient_mock.get(f"{MOCK_URL}{VERSION_PATH}", status=status)

    with pytest.raises(TraefikProxyApiError) as err:
        await _client(hass, _auth("bearer")).async_get_version()

    assert type(err.value) is getattr(api, error_name)
    assert err.value.path == VERSION_PATH
    assert err.value.status == status
    assert str(err.value) == f"{VERSION_PATH}: HTTP {status}"


@pytest.mark.parametrize("status", [400, 500, 502, 503])
async def test_other_non_2xx_raise_base_error_with_status(hass, aioclient_mock, status: int) -> None:
    """Any other non-2xx status raises the base error, none of its subclasses."""
    aioclient_mock.get(f"{MOCK_URL}{VERSION_PATH}", status=status)

    with pytest.raises(TraefikProxyApiError) as err:
        await _client(hass).async_get_version()

    assert type(err.value) is TraefikProxyApiError
    assert err.value.status == status
    assert str(err.value) == f"{VERSION_PATH}: HTTP {status}"


REDIRECT_LOCATION = "https://intruder:hunter2@other.example.org/api"


async def test_redirect_is_not_followed_and_hides_location(hass, aioclient_mock) -> None:
    """A 302 raises the redirect error; the Location target is never contacted or named."""
    aioclient_mock.get(f"{MOCK_URL}{VERSION_PATH}", status=302, headers={"Location": REDIRECT_LOCATION})

    with pytest.raises(api.TraefikProxyRedirectError) as err:
        await _client(hass, _auth("bearer")).async_get_version()

    assert isinstance(err.value, api.TraefikProxyConnectionError)
    assert str(err.value) == f"{VERSION_PATH}: HTTP 302"
    assert err.value.status == 302
    assert err.value.detail == "HTTP 302"
    for text in (str(err.value), repr(err.value)):
        for secret in ("other.example.org", "intruder", "hunter2"):
            assert secret not in text
    assert len(aioclient_mock.mock_calls) == 1


@pytest.mark.parametrize(
    ("status", "redirect"),
    [(300, True), (302, True), (307, True), (399, True), (400, False)],
)
async def test_redirect_status_classification(hass, aioclient_mock, status: int, redirect: bool) -> None:
    """300-399 raise the redirect error; 400 raises the plain base error."""
    aioclient_mock.get(f"{MOCK_URL}{VERSION_PATH}", status=status)

    with pytest.raises(TraefikProxyApiError) as err:
        await _client(hass).async_get_version()

    assert isinstance(err.value, api.TraefikProxyRedirectError) is redirect
    if not redirect:
        assert type(err.value) is TraefikProxyApiError
    assert err.value.status == status
    assert err.value.detail == f"HTTP {status}"


def _connector_error() -> aiohttp.ClientConnectorError:
    key = MagicMock(host="traefik.example.com", port=8080, ssl=True)
    return aiohttp.ClientConnectorError(key, OSError(111, "Connection refused"))


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(_connector_error(), id="ClientConnectorError"),
        pytest.param(aiohttp.ServerDisconnectedError(), id="ServerDisconnectedError"),
        pytest.param(aiohttp.ClientOSError(104, "Connection reset"), id="ClientOSError"),
        pytest.param(aiohttp.ClientPayloadError("truncated"), id="ClientPayloadError"),
        pytest.param(TimeoutError(), id="TimeoutError"),
        pytest.param(OSError(113, "No route to host"), id="OSError"),
    ],
)
async def test_network_errors_raise_connection_error(hass, aioclient_mock, exc: BaseException) -> None:
    """Network-level failures raise the connection error named by exception type only."""
    aioclient_mock.get(f"{MOCK_URL}{VERSION_PATH}", exc=exc)

    with pytest.raises(TraefikProxyApiError) as err:
        await _client(hass).async_get_version()

    assert type(err.value) is api.TraefikProxyConnectionError
    assert err.value.status is None
    assert str(err.value) == f"{VERSION_PATH}: {type(exc).__name__}"
    assert err.value.__cause__ is exc


async def test_invalid_url_raises_invalid_url_error(hass, aioclient_mock) -> None:
    """aiohttp's invalid-URL error raises the invalid-URL error, a connection error subclass."""
    aioclient_mock.get(f"{MOCK_URL}{VERSION_PATH}", exc=aiohttp.InvalidUrlClientError(USERINFO_URL))

    with pytest.raises(api.TraefikProxyInvalidUrlError) as err:
        await _client(hass).async_get_version()

    assert isinstance(err.value, api.TraefikProxyConnectionError)
    assert str(err.value) == f"{VERSION_PATH}: InvalidUrlClientError"


async def test_userinfo_url_with_bearer_token_raises_invalid_url_error() -> None:
    """URL credentials plus a bearer header make aiohttp refuse the request; the client maps it.

    Runs on a real aiohttp session because ``aioclient_mock`` replaces the
    request method and so never builds a request. aiohttp raises before any
    socket is opened, so no network access happens.
    """
    async with aiohttp.ClientSession() as session:
        client = TraefikProxyApiClient(
            session,
            "https://u:p@192.0.2.1:1",
            api.Auth(mode=api.AuthMode.bearer, token="t"),
            request_timeout=1.0,
        )
        calls = [
            (client.async_get_version, "/api/version"),
            (client.async_get_state, "/api/rawdata"),
        ]
        for call, path in calls:
            with pytest.raises(api.TraefikProxyInvalidUrlError) as err:
                await call()

            assert str(err.value) == f"{path}: ValueError"
            assert isinstance(err.value.__cause__, ValueError)
            assert "u:p" not in str(err.value)
            assert "192.0.2.1" not in str(err.value)


CONSTRUCTION_ERROR = "Cannot combine AUTHORIZATION header with AUTH argument or credentials encoded in URL"


async def test_request_construction_value_error_maps_to_invalid_url(hass, aioclient_mock) -> None:
    """A ValueError raised while aiohttp builds the request maps to the invalid-URL error."""
    aioclient_mock.get(f"{MOCK_URL}{VERSION_PATH}", exc=ValueError(CONSTRUCTION_ERROR))

    with pytest.raises(api.TraefikProxyInvalidUrlError) as err:
        await _client(hass, _auth("bearer")).async_get_version()

    assert isinstance(err.value, api.TraefikProxyConnectionError)
    assert isinstance(err.value, TraefikProxyApiError)
    assert str(err.value) == f"{VERSION_PATH}: ValueError"


def test_taxonomy_hierarchy() -> None:
    """Every client error is a TraefikProxyApiError; invalid URL is a connection error."""
    for name in (
        "TraefikProxyAuthError",
        "TraefikProxyNotFoundError",
        "TraefikProxyConnectionError",
        "TraefikProxyPayloadError",
    ):
        assert issubclass(getattr(api, name), TraefikProxyApiError)
    assert issubclass(api.TraefikProxyInvalidUrlError, api.TraefikProxyConnectionError)
    assert issubclass(api.TraefikProxyRedirectError, api.TraefikProxyConnectionError)
    assert not issubclass(api.TraefikProxyNotFoundError, TraefikProxyAuthError)


async def test_invalid_json_raises_payload_error(hass, aioclient_mock) -> None:
    """A body that is not JSON raises the payload error, not an invalid-URL error."""
    aioclient_mock.get(f"{MOCK_URL}{VERSION_PATH}", text="not json")

    with pytest.raises(api.TraefikProxyPayloadError) as err:
        await _client(hass).async_get_version()

    assert not isinstance(err.value, api.TraefikProxyConnectionError)
    assert err.value.path == VERSION_PATH
    assert "not json" not in str(err.value)


async def test_version_list_payload_raises_payload_error(hass, aioclient_mock) -> None:
    """/api/version answering with a JSON list raises the payload error."""
    aioclient_mock.get(f"{MOCK_URL}{VERSION_PATH}", json=[{"Version": "3.7.19"}])

    with pytest.raises(api.TraefikProxyPayloadError, match=r"^/api/version: "):
        await _client(hass).async_get_version()


# --- Credential secrecy ------------------------------------------------------


_ERROR_SCENARIOS = [
    pytest.param({"status": 401}, id="401"),
    pytest.param({"status": 404}, id="404"),
    pytest.param({"status": 500}, id="500"),
    pytest.param({"status": 302, "headers": {"Location": USERINFO_URL}}, id="redirect"),
    pytest.param({"exc": aiohttp.ServerDisconnectedError()}, id="connection"),
    pytest.param({"exc": aiohttp.InvalidUrlClientError(USERINFO_URL)}, id="invalid-url"),
    pytest.param(
        {"exc": ValueError("Cannot combine AUTHORIZATION header with AUTH argument or credentials encoded in URL")},
        id="request-construction",
    ),
    pytest.param({"text": "not json"}, id="invalid-json"),
    pytest.param({"json": ["unexpected"]}, id="payload-shape"),
]


@pytest.mark.parametrize("mode", ["basic", "bearer"])
@pytest.mark.parametrize("scenario", _ERROR_SCENARIOS)
async def test_credentials_never_leak(hass, aioclient_mock, caplog, mode: str, scenario: dict[str, Any]) -> None:
    """No log record, str(exc) or repr(exc) contains any credential form or the userinfo URL."""
    caplog.set_level(logging.DEBUG)
    aioclient_mock.get(f"{MOCK_URL}{VERSION_PATH}", **scenario)
    client = _client(hass, _auth(mode), base_url=USERINFO_URL)

    with pytest.raises(TraefikProxyApiError) as err:
        await client.async_get_version()

    texts = [caplog.text, str(err.value), repr(err.value), repr(client)]
    texts.extend(record.getMessage() for record in caplog.records)
    for secret in _secret_forms():
        for text in texts:
            assert secret not in text


# --- TLS verification and host pinning ---------------------------------------


async def test_verify_ssl_false_reaches_every_request(hass, aioclient_mock) -> None:
    """verify_ssl=False is passed as ssl=False on every session.get call."""
    per_page = load_fixture("v3.7", "pages/index.json")["per_page"]
    stub_traefik_paginated(aioclient_mock, version="v3.7")
    session = MagicMock(wraps=async_get_clientsession(hass))
    client = TraefikProxyApiClient(session, MOCK_URL, api.Auth(), verify_ssl=False, page_size=per_page)

    await client.async_get_version()
    await client.async_get_entrypoints()
    await client.async_get_state()

    assert session.get.call_count == len(aioclient_mock.mock_calls) > 3
    for call in session.get.call_args_list:
        assert call.kwargs["ssl"] is False


async def test_every_request_disables_redirects(hass, aioclient_mock) -> None:
    """allow_redirects=False is passed on every session.get call (D-23)."""
    per_page = load_fixture("v3.7", "pages/index.json")["per_page"]
    stub_traefik_paginated(aioclient_mock, version="v3.7")
    session = MagicMock(wraps=async_get_clientsession(hass))
    client = TraefikProxyApiClient(session, MOCK_URL, api.Auth(), page_size=per_page)

    await client.async_get_version()
    await client.async_get_entrypoints()
    await client.async_get_state()

    assert session.get.call_count == len(aioclient_mock.mock_calls) > 3
    for call in session.get.call_args_list:
        assert call.kwargs["allow_redirects"] is False


async def test_verify_ssl_defaults_to_true(hass, aioclient_mock) -> None:
    """Without the option every request verifies TLS."""
    aioclient_mock.get(f"{MOCK_URL}{VERSION_PATH}", json=load_fixture("v3.7", "version.json"))
    session = MagicMock(wraps=async_get_clientsession(hass))

    await TraefikProxyApiClient(session, MOCK_URL, api.Auth()).async_get_version()

    assert session.get.call_args.kwargs["ssl"] is True


async def test_real_captures_parse_and_requests_stay_on_base_url(hass, aioclient_mock) -> None:
    """Version and entrypoints match the parsers on the v3.7 capture; every request targets the base URL."""
    per_page = load_fixture("v3.7", "pages/index.json")["per_page"]
    stub_traefik_paginated(aioclient_mock, version="v3.7")
    client = _client(hass, page_size=per_page)

    assert await client.async_get_version() == parse_version(load_fixture("v3.7", "version.json"))
    assert await client.async_get_entrypoints() == parse_entrypoints(load_fixture("v3.7", "entrypoints.json"))
    await client.async_get_state()

    assert aioclient_mock.mock_calls
    for _method, url, _data, _headers in aioclient_mock.mock_calls:
        assert str(url).startswith(f"{MOCK_URL}/api/")


# --- State: /api/rawdata with the remembered paginated fallback --------------

RAWDATA_PATH = "/api/rawdata"
LIST_PATHS = ("/api/http/routers", "/api/http/services", "/api/http/middlewares")


def _paths(aioclient_mock) -> list[str]:  # type: ignore[no-untyped-def]
    return [call[1].path for call in aioclient_mock.mock_calls]


async def test_rawdata_parses_like_the_model_parser(hass, aioclient_mock) -> None:
    """The real v3.7 rawdata is read in one request and equals models.parse_rawdata."""
    payload = load_fixture("v3.7", "rawdata.json")
    aioclient_mock.get(f"{MOCK_URL}{RAWDATA_PATH}", json=payload)

    state = await _client(hass).async_get_state()

    assert state == parse_rawdata(payload)
    assert _paths(aioclient_mock) == [RAWDATA_PATH]


async def test_rawdata_404_falls_back_to_pages_and_is_remembered(hass, aioclient_mock) -> None:
    """A 404 on rawdata reads the list pages; the next call goes straight to the pages."""
    per_page = load_fixture("v3.7", "pages/index.json")["per_page"]
    stub_traefik_paginated(aioclient_mock, version="v3.7")
    client = _client(hass, page_size=per_page)

    first = await client.async_get_state()
    assert _paths(aioclient_mock)[0] == RAWDATA_PATH
    assert set(_paths(aioclient_mock)[1:]) == set(LIST_PATHS)

    aioclient_mock.mock_calls.clear()
    second = await client.async_get_state()

    assert second == first
    assert first == parse_rawdata(load_fixture("v3.7", "rawdata.json"))
    assert RAWDATA_PATH not in _paths(aioclient_mock)
    assert set(_paths(aioclient_mock)) == set(LIST_PATHS)


@pytest.mark.parametrize("status", [401, 500])
async def test_rawdata_other_errors_do_not_fall_back(hass, aioclient_mock, status: int) -> None:
    """Only a 404 switches to the pages; any other error propagates and no page is requested."""
    aioclient_mock.get(f"{MOCK_URL}{RAWDATA_PATH}", status=status)
    client = _client(hass)

    with pytest.raises(TraefikProxyApiError) as err:
        await client.async_get_state()

    assert err.value.status == status
    assert _paths(aioclient_mock) == [RAWDATA_PATH]
    assert client._paginated is False


async def test_rawdata_unexpected_shape_raises_payload_error(hass, aioclient_mock) -> None:
    """A rawdata list instead of an object is a payload error naming only the path."""
    aioclient_mock.get(f"{MOCK_URL}{RAWDATA_PATH}", json=[])

    with pytest.raises(api.TraefikProxyPayloadError, match=r"^/api/rawdata: unexpected payload shape$"):
        await _client(hass).async_get_state()


async def test_list_endpoint_404_in_paginated_mode_raises_not_found(hass, aioclient_mock) -> None:
    """During the fallback, a 404 on a list endpoint is a NotFound error, not another fallback."""
    aioclient_mock.get(f"{MOCK_URL}{RAWDATA_PATH}", status=404)
    aioclient_mock.get(f"{MOCK_URL}/api/http/routers", status=404)

    with pytest.raises(api.TraefikProxyNotFoundError) as err:
        await _client(hass).async_get_state()

    assert err.value.path == "/api/http/routers"
    assert _paths(aioclient_mock) == [RAWDATA_PATH, "/api/http/routers"]


@pytest.mark.parametrize(
    "page",
    [{"status": 404}, {"status": 500}, {"exc": aiohttp.ClientConnectionError()}],
    ids=["http-404", "http-500", "connection-error"],
)
async def test_failed_fallback_keeps_rawdata_mode(hass, aioclient_mock, page: dict[str, Any]) -> None:
    """A rawdata 404 whose page reads fail too leaves the mode unchanged; the next call tries rawdata first."""
    aioclient_mock.get(f"{MOCK_URL}{RAWDATA_PATH}", status=404)
    aioclient_mock.get(f"{MOCK_URL}/api/http/routers", **page)
    client = _client(hass)

    with pytest.raises(TraefikProxyApiError):
        await client.async_get_state()
    assert client._paginated is False

    payload = load_fixture("v3.7", "rawdata.json")
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{MOCK_URL}{RAWDATA_PATH}", json=payload)

    assert await client.async_get_state() == parse_rawdata(payload)
    assert _paths(aioclient_mock) == [RAWDATA_PATH]
    assert client._paginated is False


# --- Rawdata probe while paginated -------------------------------------------


def _page_paths() -> list[str]:
    """Paths of one paginated read of the v3.7 capture, one entry per page."""
    index = load_fixture("v3.7", "pages/index.json")
    return [f"/api/http/{kind}" for kind in ("routers", "services", "middlewares") for _page in index[kind]]


async def _paginated_client(hass, aioclient_mock) -> TraefikProxyApiClient:  # type: ignore[no-untyped-def]
    """A client that fell back to the pages on a rawdata 404; recorded calls are cleared."""
    per_page = load_fixture("v3.7", "pages/index.json")["per_page"]
    stub_traefik_paginated(aioclient_mock, version="v3.7")
    client = _client(hass, page_size=per_page)
    await client.async_get_state()
    assert client._paginated is True
    aioclient_mock.mock_calls.clear()
    return client


def _restub_rawdata(aioclient_mock, **rawdata: Any) -> None:  # type: ignore[no-untyped-def]
    """Answer /api/rawdata with ``rawdata``; the pages stay served (their 404 rawdata mock is shadowed)."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{MOCK_URL}{RAWDATA_PATH}", **rawdata)
    stub_traefik_paginated(aioclient_mock, version="v3.7")


async def test_rawdata_probe_success_switches_back(hass, aioclient_mock) -> None:
    """An armed probe that gets rawdata returns its state and the client stays in rawdata mode."""
    client = await _paginated_client(hass, aioclient_mock)
    payload = load_fixture("v3.7", "rawdata.json")
    _restub_rawdata(aioclient_mock, json=payload)

    client.request_rawdata_probe()
    state = await client.async_get_state()

    assert _paths(aioclient_mock) == [RAWDATA_PATH]
    assert client._paginated is False
    assert state == parse_rawdata(payload)

    aioclient_mock.mock_calls.clear()
    await client.async_get_state()
    assert _paths(aioclient_mock) == [RAWDATA_PATH]


async def test_rawdata_probe_404_stays_paginated_once(hass, aioclient_mock) -> None:
    """A probe answered 404 costs one extra request; the next call reads the pages only."""
    client = await _paginated_client(hass, aioclient_mock)

    client.request_rawdata_probe()
    await client.async_get_state()
    assert _paths(aioclient_mock) == [RAWDATA_PATH, *_page_paths()]

    aioclient_mock.mock_calls.clear()
    await client.async_get_state()
    assert _paths(aioclient_mock) == _page_paths()
    assert client._paginated is True


async def test_rawdata_probe_empty_payload_switches_back(hass, aioclient_mock) -> None:
    """An empty but valid rawdata payload is a successful probe: empty state, rawdata mode."""
    client = await _paginated_client(hass, aioclient_mock)
    _restub_rawdata(aioclient_mock, json={})

    client.request_rawdata_probe()
    state = await client.async_get_state()

    assert state.routers == {}
    assert state.services == {}
    assert state.middlewares == {}
    assert client._paginated is False
    assert _paths(aioclient_mock) == [RAWDATA_PATH]


async def test_request_rawdata_probe_is_noop_in_rawdata_mode(hass, aioclient_mock) -> None:
    """In rawdata mode arming changes nothing: one rawdata request, no pending probe."""
    aioclient_mock.get(f"{MOCK_URL}{RAWDATA_PATH}", json=load_fixture("v3.7", "rawdata.json"))
    client = _client(hass)

    client.request_rawdata_probe()
    await client.async_get_state()

    assert _paths(aioclient_mock) == [RAWDATA_PATH]
    assert client._rawdata_probe_due is False


@pytest.mark.parametrize("status", [401, 403])
async def test_rawdata_probe_auth_error_propagates(hass, aioclient_mock, status: int) -> None:
    """A rejected credential on the probe raises at once; no page is requested with it."""
    client = await _paginated_client(hass, aioclient_mock)
    _restub_rawdata(aioclient_mock, status=status)

    client.request_rawdata_probe()
    with pytest.raises(TraefikProxyAuthError):
        await client.async_get_state()

    assert _paths(aioclient_mock) == [RAWDATA_PATH]
    assert client._paginated is True


@pytest.mark.parametrize(
    "rawdata",
    [
        {"status": 500},
        {"exc": aiohttp.ClientConnectionError()},
        {"json": []},
        {"text": "not json"},
    ],
    ids=["http-500", "connection-error", "unexpected-shape", "invalid-json"],
)
async def test_rawdata_probe_other_failures_read_pages(hass, aioclient_mock, rawdata: dict[str, Any]) -> None:
    """Any other probe failure keeps the client paginated and serves the call from the pages."""
    client = await _paginated_client(hass, aioclient_mock)
    _restub_rawdata(aioclient_mock, **rawdata)

    client.request_rawdata_probe()
    state = await client.async_get_state()

    assert state == parse_rawdata(load_fixture("v3.7", "rawdata.json"))
    assert _paths(aioclient_mock) == [RAWDATA_PATH, *_page_paths()]
    assert client._paginated is True


async def test_one_probe_per_arming_under_overlapping_calls(hass, aioclient_mock) -> None:
    """Two overlapping calls after one arming request /api/rawdata exactly once."""
    client = await _paginated_client(hass, aioclient_mock)

    async def _slow_404(method: str, url: Any, _data: Any) -> AiohttpClientMockResponse:
        # Yield to the loop so the second call runs while the probe is in flight.
        for _ in range(3):
            await asyncio.sleep(0)
        return AiohttpClientMockResponse(method, url, status=404)

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{MOCK_URL}{RAWDATA_PATH}", side_effect=_slow_404)
    stub_traefik_paginated(aioclient_mock, version="v3.7")

    client.request_rawdata_probe()
    await asyncio.gather(client.async_get_state(), client.async_get_state())

    assert _paths(aioclient_mock).count(RAWDATA_PATH) == 1
    assert client._paginated is True


# --- Module hygiene ----------------------------------------------------------


# --- /api/certificates (Traefik >= 3.7) -----------------------------------------------

CERTIFICATES_PATH = "/api/certificates"


async def test_certificates_capture_flows_through_the_client(hass, aioclient_mock) -> None:
    """The v3.7 capture is read through the paginated path and parsed into certificates."""
    payload = load_fixture("v3.7", "certificates.json")
    aioclient_mock.get(f"{MOCK_URL}{CERTIFICATES_PATH}", json=payload)

    certificates = await _client(hass, page_size=7).async_get_certificates()

    assert certificates == parse_certificates(payload)
    assert certificates[0].common_name == "secure.example.com"
    assert len(aioclient_mock.mock_calls) == 1
    url = aioclient_mock.mock_calls[0][1]
    assert url.path == CERTIFICATES_PATH
    assert dict(url.query) == {"per_page": "7", "page": "1"}


def _certificate_item(common_name: str) -> dict[str, Any]:
    return {
        "commonName": common_name,
        "sans": [common_name],
        "notAfter": "2030-01-02T03:04:05Z",
        "notBefore": "2029-10-04T03:04:05Z",
        "serialNumber": "1",
        "status": "enabled",
    }


@pytest.mark.parametrize("mode", ["basic", "bearer"])
@pytest.mark.parametrize(
    ("status", "error"),
    [
        (404, api.TraefikProxyNotFoundError),
        (401, api.TraefikProxyAuthError),
        (403, api.TraefikProxyAuthError),
        (500, TraefikProxyApiError),
    ],
)
async def test_certificates_status_maps_to_taxonomy(
    hass, aioclient_mock, mode: str, status: int, error: type[Exception]
) -> None:
    """Non-2xx answers map to the existing taxonomy; the text names only path and status."""
    aioclient_mock.get(f"{MOCK_URL}{CERTIFICATES_PATH}", status=status)

    with pytest.raises(TraefikProxyApiError) as err:
        await _client(hass, _auth(mode)).async_get_certificates()

    assert type(err.value) is error
    assert err.value.status == status
    assert str(err.value) == f"{CERTIFICATES_PATH}: HTTP {status}"
    assert MOCK_URL not in str(err.value)
    for secret in _secret_forms():
        assert secret not in str(err.value)


@pytest.mark.parametrize("mode", ["basic", "bearer"])
async def test_certificates_connection_error(hass, aioclient_mock, mode: str) -> None:
    """A connection failure names only the path and the exception type."""
    aioclient_mock.get(f"{MOCK_URL}{CERTIFICATES_PATH}", exc=aiohttp.ClientConnectionError())

    with pytest.raises(api.TraefikProxyConnectionError) as err:
        await _client(hass, _auth(mode)).async_get_certificates()

    assert str(err.value) == f"{CERTIFICATES_PATH}: ClientConnectionError"
    assert MOCK_URL not in str(err.value)
    for secret in _secret_forms():
        assert secret not in str(err.value)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"0": _certificate_item("a.example.com")}, id="dict-payload"),
        pytest.param(["x"], id="string-item"),
        pytest.param([{**_certificate_item("a.example.com"), "notAfter": None}], id="notAfter-null"),
        pytest.param([{k: v for k, v in _certificate_item("a").items() if k != "notAfter"}], id="notAfter-missing"),
        pytest.param([{**_certificate_item("a.example.com"), "notAfter": 123}], id="notAfter-int"),
        pytest.param([{**_certificate_item("a.example.com"), "notAfter": "not-a-date"}], id="notAfter-unparsable"),
        pytest.param([{**_certificate_item("a.example.com"), "notAfter": "2027-02-12T00:17:40"}], id="notAfter-naive"),
        pytest.param([{k: v for k, v in _certificate_item("a").items() if k != "notBefore"}], id="notBefore-missing"),
        pytest.param([{**_certificate_item("a.example.com"), "notBefore": 123}], id="notBefore-int"),
        pytest.param([{**_certificate_item("a.example.com"), "notBefore": "x"}], id="notBefore-unparsable"),
        pytest.param(
            [{**_certificate_item("a.example.com"), "notBefore": "2026-11-13T00:17:40"}], id="notBefore-naive"
        ),
    ],
)
async def test_certificates_payload_errors(hass, aioclient_mock, payload: object) -> None:
    """Every shape violation is a payload error; no certificate with a guessed expiry is returned."""
    aioclient_mock.get(f"{MOCK_URL}{CERTIFICATES_PATH}", json=payload)

    with pytest.raises(api.TraefikProxyPayloadError) as err:
        await _client(hass).async_get_certificates()

    assert str(err.value) == f"{CERTIFICATES_PATH}: unexpected payload shape"


async def test_certificates_pagination_follows_x_next_page(hass, aioclient_mock) -> None:
    """Two pages of one certificate each yield two certificates in page order, in two requests."""
    for page, common_name in ((1, "a.example.com"), (2, "b.example.com")):
        aioclient_mock.get(
            f"{MOCK_URL}{CERTIFICATES_PATH}",
            params={"per_page": 1, "page": page},
            json=[_certificate_item(common_name)],
            headers={"X-Next-Page": "2"},
        )

    certificates = await _client(hass, page_size=1).async_get_certificates()

    assert [certificate.common_name for certificate in certificates] == ["a.example.com", "b.example.com"]
    assert len(aioclient_mock.mock_calls) == 2


STUB_NOW = datetime(2027, 2, 13, 12, 0, tzinfo=UTC)


async def test_certificates_stub_v37_is_rebased_on_the_clock(hass, aioclient_mock, freezer) -> None:
    """The default v3.7 stub serves the capture with dates relative to the clock at registration."""
    freezer.move_to(STUB_NOW)
    stub_traefik(aioclient_mock, version="v3.7")
    capture = load_fixture("v3.7", "certificates.json")[0]

    (certificate,) = await _client(hass).async_get_certificates()

    now = dt_util.utcnow().replace(microsecond=0)
    assert certificate.common_name == capture["commonName"]
    assert certificate.sans == tuple(capture["sans"])
    assert certificate.status == capture["status"]
    assert certificate.not_before == now - timedelta(days=1)
    assert certificate.not_after == now + STUB_CERT_VALIDITY


async def test_certificates_stub_paginated_v37_is_rebased_on_the_clock(hass, aioclient_mock, freezer) -> None:
    """The paginated stub serves the same re-based certificates."""
    freezer.move_to(STUB_NOW)
    stub_traefik_paginated(aioclient_mock, version="v3.7")

    (certificate,) = await _client(hass).async_get_certificates()

    assert certificate.not_after == STUB_NOW + STUB_CERT_VALIDITY


@pytest.mark.parametrize("stub", [stub_traefik, stub_traefik_paginated])
async def test_certificates_stub_v211_answers_404(hass, aioclient_mock, freezer, stub: Any) -> None:
    """A capture without certificates.json (Traefik < 3.7) answers 404."""
    freezer.move_to(STUB_NOW)
    stub(aioclient_mock, version="v2.11")

    with pytest.raises(api.TraefikProxyNotFoundError):
        await _client(hass).async_get_certificates()


async def test_certificates_stub_argument_replaces_payload(hass, aioclient_mock, freezer) -> None:
    """An explicit certificates= payload replaces the capture."""
    freezer.move_to(STUB_NOW)
    stub_traefik(aioclient_mock, version="v3.7", certificates=[])

    assert await _client(hass).async_get_certificates() == ()


def test_certificates_frozen_v37_helper_returns_the_capture_under_frozen_time(freezer) -> None:
    """The helper moves the clock to CERT_FIXTURE_NOW and returns the unmodified capture."""
    certificates = frozen_v37_certificates(freezer)

    assert dt_util.utcnow() == CERT_FIXTURE_NOW
    assert certificates == load_fixture("v3.7", "certificates.json")
    assert certificates[0]["notAfter"] == "2027-02-12T00:17:40Z"
    assert (parse_certificates(certificates)[0].not_after - CERT_FIXTURE_NOW).days == 88


def test_api_module_contains_no_assert_statements() -> None:
    """Shape checks raise TraefikProxyPayloadError; production code has no assert."""
    tree = ast.parse(API_PATH.read_text(encoding="utf-8"))
    asserts = [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Assert)]
    assert asserts == []


def test_legacy_read_surface_removed() -> None:
    """Only the typed read API remains on the client."""
    for name in (
        "fetch_all",
        "get_overview",
        "get_version",
        "get_entrypoints",
        "get_routers",
        "get_http_services",
        "get_http_middlewares",
        "_get",
        "_get_response",
    ):
        assert not hasattr(TraefikProxyApiClient, name), name
    assert not hasattr(api, "filter_internal_items")


def test_no_client_session_in_api_module() -> None:
    """Production code never instantiates its own aiohttp session."""
    for line in API_PATH.read_text(encoding="utf-8").splitlines():
        if "aiohttp.ClientSession(" in line:
            raise AssertionError(f"ClientSession instantiation found: {line!r}")
