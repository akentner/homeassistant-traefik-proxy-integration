"""Contract tests for TraefikProxyApiClient.

The client runs on Home Assistant's shared aiohttp session, which the
``aioclient_mock`` fixture replaces; every request is recorded as
``(method, url, data, headers)``. Payloads come from the real v3.7 capture
through the conftest helper.

Covered: the three auth modes and their per-request header, the error
taxonomy for HTTP statuses, network exceptions and payload errors,
credential secrecy in logs / exception text / reprs, TLS verification on
every request, request host pinning and the router refresh POST.
"""

from __future__ import annotations

import ast
import base64
import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import aiohttp
import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.traefik_proxy import api
from custom_components.traefik_proxy.api import TraefikProxyApiClient, TraefikProxyApiError, TraefikProxyAuthError
from custom_components.traefik_proxy.models import parse_entrypoints, parse_version
from tests.conftest import MOCK_URL, load_fixture, stub_traefik_paginated

API_PATH = Path(__file__).parent.parent / "custom_components" / "traefik_proxy" / "api.py"
VERSION_PATH = "/api/version"
REFRESH_PATH = "/api/http/routers/refresh"

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
    assert _auth("basic").header() == {"Authorization": aiohttp.BasicAuth(USERNAME, PASSWORD).encode()}


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


@pytest.mark.parametrize("status", [400, 302, 500, 502, 503])
async def test_other_non_2xx_raise_base_error_with_status(hass, aioclient_mock, status: int) -> None:
    """Any other non-2xx status raises the base error, none of its subclasses."""
    aioclient_mock.get(f"{MOCK_URL}{VERSION_PATH}", status=status)

    with pytest.raises(TraefikProxyApiError) as err:
        await _client(hass).async_get_version()

    assert type(err.value) is TraefikProxyApiError
    assert err.value.status == status
    assert str(err.value) == f"{VERSION_PATH}: HTTP {status}"


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
    pytest.param({"exc": aiohttp.ServerDisconnectedError()}, id="connection"),
    pytest.param({"exc": aiohttp.InvalidUrlClientError(USERINFO_URL)}, id="invalid-url"),
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


# --- Router refresh POST -----------------------------------------------------


async def test_reload_routers_success_sends_auth_and_empty_body(hass, aioclient_mock) -> None:
    """A 202 returns None; the POST carries the Auth header and Content-Length 0."""
    aioclient_mock.post(f"{MOCK_URL}{REFRESH_PATH}", status=202)

    assert await _client(hass, _auth("basic")).reload_routers() is None

    method, url, _data, headers = aioclient_mock.mock_calls[0]
    assert method == "post"
    assert str(url) == f"{MOCK_URL}{REFRESH_PATH}"
    assert headers == {**_auth("basic").header(), "Content-Length": "0"}


@pytest.mark.parametrize(
    ("status", "error_name"),
    [(401, "TraefikProxyAuthError"), (403, "TraefikProxyAuthError"), (500, "TraefikProxyApiError")],
)
async def test_reload_routers_status_errors(hass, aioclient_mock, status: int, error_name: str) -> None:
    """Refresh failures map to the auth error or the base error with path and status."""
    aioclient_mock.post(f"{MOCK_URL}{REFRESH_PATH}", status=status)

    with pytest.raises(TraefikProxyApiError) as err:
        await _client(hass, _auth("bearer")).reload_routers()

    assert type(err.value) is getattr(api, error_name)
    assert str(err.value) == f"{REFRESH_PATH}: HTTP {status}"


async def test_reload_routers_network_error(hass, aioclient_mock) -> None:
    """A network failure on the refresh POST raises the connection error."""
    aioclient_mock.post(f"{MOCK_URL}{REFRESH_PATH}", exc=aiohttp.ServerDisconnectedError())

    with pytest.raises(api.TraefikProxyConnectionError, match=r"^/api/http/routers/refresh: ServerDisconnectedError$"):
        await _client(hass).reload_routers()


async def test_reload_routers_verify_ssl(hass, aioclient_mock) -> None:
    """The refresh POST honours verify_ssl as well."""
    aioclient_mock.post(f"{MOCK_URL}{REFRESH_PATH}", status=202)
    session = MagicMock(wraps=async_get_clientsession(hass))

    await TraefikProxyApiClient(session, MOCK_URL, api.Auth(), verify_ssl=False).reload_routers()

    assert session.post.call_args.kwargs["ssl"] is False


# --- Module hygiene ----------------------------------------------------------


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
