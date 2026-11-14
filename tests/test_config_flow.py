"""Tests for the Traefik integration config flow.

Covers:
- ``STEP_USER_DATA_SCHEMA`` rejects malformed URLs via ``cv.url``.
- ``_validate_input`` maps ``InvalidUrlClientError`` (aiohttp URL parse failure)
  to ``InvalidUrl`` and ``async_step_user`` surfaces ``errors["base"] = "invalid_url"``
  instead of HA's generic "Unknown error occurred".
- ``STEP_USER_DATA_SCHEMA`` accepts an empty ``api_key`` (``TextSelector``
  with URL type used to mask the field; ``cv.url`` rejects bad schemes).
- ``TraefikProxyApiClient`` classifies ``InvalidUrlClientError`` as
  ``TraefikProxyInvalidUrlError`` so neither the flow nor the coordinator sees a
  raw aiohttp exception.
- ``_validate_input`` probes ``/api/version`` and maps every client error class
  to its flow error (auth, API disabled, invalid URL, cannot connect).
- Every ``AuthMode`` round-trips through the client to the exact
  Authorization header ``Auth.header()`` promises.

Hermetic via ``aioclient_mock`` (HA's HTTP mock layer) — no live Traefik needed.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.traefik_proxy.api import (
    Auth,
    AuthMode,
    TraefikProxyApiClient,
    TraefikProxyApiError,
    TraefikProxyAuthError,
    TraefikProxyConnectionError,
    TraefikProxyInvalidUrlError,
    TraefikProxyNotFoundError,
    TraefikProxyPayloadError,
)
from custom_components.traefik_proxy.config_flow import (
    STEP_USER_DATA_SCHEMA,
    STEP_YAML_DATA_SCHEMA,
    ApiDisabled,
    CannotConnect,
    InvalidAuth,
    InvalidUrl,
    _check_url_shape,
    _validate_input,
)
from custom_components.traefik_proxy.const import (
    CONF_API_KEY,
    CONF_URL,
    CONF_VERIFY_SSL,
)
from custom_components.traefik_proxy.coordinator import auth_from_entry_data
from tests.conftest import load_fixture

GOOD_URL = "https://traefik.example.com:8080"


# ----------------------- schema validation -----------------------


@pytest.mark.parametrize(
    "url",
    [
        "http;//192.168.178.3:8080",  # user's bug: semicolon instead of colon
        "htp://traefik.local:8080",  # missing letter in scheme
        "traefik.example.com:8080",  # no scheme at all
        "ftp://traefik.example.com:8080",  # disallowed scheme
        "",  # empty
    ],
)
def test_user_schema_accepts_any_url_string(url: str) -> None:
    """``STEP_USER_DATA_SCHEMA`` accepts arbitrary URL strings as plain text.

    v0.1.3 note: ``vol.All(cv.string, cv.url)`` (used in v0.1.0..v0.1.2)
    breaks ``voluptuous_serialize.convert`` — HA's frontend JSON-over-WS
    config-flow endpoint raises ``ValueError: Unable to convert schema:
    <function url at 0x…>`` (see PR-28788275285). The schema now uses
    ``TextSelector(type=URL)`` which serialises as a selector block; the
    browser additionally rejects malformed URLs via HA's URL input
    handler, and server-side ``_check_url_shape`` provides the final
    defence with ``errors["base"] = "invalid_url"``.
    """
    out = STEP_USER_DATA_SCHEMA({CONF_URL: url})
    assert out[CONF_URL] == url


@pytest.mark.parametrize(
    "url",
    [
        "http://traefik.example.com:8080",
        "https://traefik.local",
        "https://192.168.178.3:8080",
        "http;//malformed-on-purpose",
    ],
)
def test_user_schema_accepts_http_and_https(url: str) -> None:
    """Plain ``http://`` and ``https://`` URLs (with or without explicit port) pass."""
    out = STEP_USER_DATA_SCHEMA({CONF_URL: url})
    assert out[CONF_URL] == url


def test_user_schema_accepts_empty_api_key() -> None:
    """Bearer is optional — empty string must pass schema validation."""
    out = STEP_USER_DATA_SCHEMA({CONF_URL: GOOD_URL, CONF_API_KEY: ""})
    assert out[CONF_API_KEY] == ""


def test_user_schema_omitted_api_key_defaults_to_empty() -> None:
    """Omitting ``api_key`` entirely (e.g. UI form with blank field) → default ``""``."""
    out = STEP_USER_DATA_SCHEMA({CONF_URL: GOOD_URL})
    assert out[CONF_API_KEY] == ""


def test_user_schema_serializes_for_config_flow_endpoint() -> None:
    """The schema serializer HA's frontend JSON-over-WS config flow endpoint
    calls before shipping the form to the browser: ``probatio.to_field_list``
    on HA 2026.10+, ``voluptuous_serialize.convert`` on HA 2026.3.

    v0.1.3 regression: ``vol.All(cv.string, cv.url)`` serialized as
    ``<function url at 0x…>`` and raised ``ValueError`` in the reconfigure
    flow. The fix is to use a ``TextSelector(type=URL)`` for UI schemas so
    the serializer can introspect a known type instead of a function ref.
    """
    try:
        from probatio import to_field_list as serialize_schema
    except ImportError:
        from voluptuous_serialize import convert as serialize_schema
    from homeassistant.helpers import config_validation as cv

    from custom_components.traefik_proxy.config_flow import STEP_USER_DATA_SCHEMA

    serialized = serialize_schema(STEP_USER_DATA_SCHEMA, custom_serializer=cv.custom_serializer)
    assert isinstance(serialized, list)
    assert len(serialized) == 3
    # URL field becomes a selector block of type=text/url.
    by_name = {field["name"]: field for field in serialized}
    assert by_name["url"]["selector"] == {"text": {"type": "url", "multiple": False, "multiline": False}}
    assert by_name["api_key"]["selector"]["text"]["type"] == "password"


def test_yaml_schema_accepts_arbitrary_url_string() -> None:
    """YAML schema is plain string validation; URL shape is checked by
    ``_check_url_shape`` after submission (see v0.1.3 release notes)."""
    out = STEP_YAML_DATA_SCHEMA({CONF_URL: "http;//foo.bar"})
    assert out[CONF_URL] == "http;//foo.bar"


# ----------------------- _check_url_shape -----------------------


@pytest.mark.parametrize(
    "url",
    [
        "http;//192.168.178.3:8080",
        "htp://traefik.example.com",
        "ftp://traefik.example.com",
        "traefik.example.com:8080",
        "",
    ],
)
def test_check_url_shape_raises_on_bad_urls(url: str) -> None:
    with pytest.raises(InvalidUrl):
        _check_url_shape(url)


def test_check_url_shape_accepts_http_and_https() -> None:
    _check_url_shape("http://traefik.example.com:8080")
    _check_url_shape("https://traefik.local")


# ----------------------- _validate_input + aiohttp url-parse failure -----------------------


async def test_validate_input_maps_invalid_url_client_error_to_invalid_url(
    hass: object, aioclient_mock: object
) -> None:
    """If a bad URL slips past the schema (e.g. raised inside the client), the
    config flow surfaces ``invalid_url`` rather than HA's 'Unknown error'."""
    # Bad URL goes through urlparse-clean check first.
    with pytest.raises(InvalidUrl):
        await _validate_input(
            hass,
            {CONF_URL: "http;//foo.bar", CONF_API_KEY: "tok", CONF_VERIFY_SSL: True},
        )


async def test_validate_input_uses_urlparse_shape_check(hass: object) -> None:
    """Pre-flight shape check runs BEFORE aiohttp — bad URLs never reach the network."""
    with pytest.raises(InvalidUrl):
        await _validate_input(hass, {CONF_URL: "://broken", CONF_API_KEY: "tok"})


async def test_validate_input_passes_on_good_url(hass: object, aioclient_mock: Any) -> None:
    """Happy-path probe succeeds against the captured /api/version and sends the bearer token."""
    aioclient_mock.get(f"{GOOD_URL}/api/version", json=load_fixture("v3.7", "version.json"))

    await _validate_input(hass, {CONF_URL: GOOD_URL, CONF_API_KEY: "tok"})

    assert aioclient_mock.mock_calls[0][3] == {"Authorization": "Bearer tok"}


async def test_validate_input_empty_bearer_does_not_send_authorization_header(
    hass: object, aioclient_mock: Any
) -> None:
    """Empty bearer -> no Authorization header sent -> Traefik with api.insecure works."""
    aioclient_mock.get(f"{GOOD_URL}/api/version", json=load_fixture("v3.7", "version.json"))

    await _validate_input(hass, {CONF_URL: GOOD_URL, CONF_API_KEY: ""})

    assert "Authorization" not in aioclient_mock.mock_calls[0][3]


async def test_validate_input_rejects_token_with_control_characters(hass: object, aioclient_mock: Any) -> None:
    """A token the client refuses to send surfaces as invalid_auth without a request."""
    with pytest.raises(InvalidAuth):
        await _validate_input(hass, {CONF_URL: GOOD_URL, CONF_API_KEY: "tok\r\nX-Injected: 1"})
    assert aioclient_mock.mock_calls == []


@pytest.mark.parametrize(
    ("side_effect", "expected"),
    [
        pytest.param(TraefikProxyAuthError("/api/version", "HTTP 401", status=401), InvalidAuth, id="auth-401"),
        pytest.param(TraefikProxyAuthError("/api/version", "HTTP 403", status=403), InvalidAuth, id="auth-403"),
        pytest.param(
            TraefikProxyNotFoundError("/api/version", "HTTP 404", status=404), ApiDisabled, id="not-found-404"
        ),
        pytest.param(
            TraefikProxyInvalidUrlError("/api/version", "InvalidUrlClientError"), InvalidUrl, id="invalid-url"
        ),
        pytest.param(TraefikProxyConnectionError("/api/version", "ClientOSError"), CannotConnect, id="connection"),
        pytest.param(TraefikProxyPayloadError("/api/version", "invalid JSON"), CannotConnect, id="payload"),
        pytest.param(TraefikProxyApiError("/api/version", "HTTP 500", status=500), CannotConnect, id="api-500"),
        pytest.param(TimeoutError(), CannotConnect, id="timeout"),
    ],
)
async def test_validate_input_maps_client_errors(
    hass: object, side_effect: BaseException, expected: type[Exception]
) -> None:
    """Each client error class maps to exactly one flow error, most specific first."""
    with (
        patch.object(TraefikProxyApiClient, "async_get_version", AsyncMock(side_effect=side_effect)),
        pytest.raises(expected),
    ):
        await _validate_input(hass, {CONF_URL: GOOD_URL, CONF_API_KEY: "tok", CONF_VERIFY_SSL: True})


async def test_validate_input_maps_real_404_to_api_disabled(hass: object, aioclient_mock: Any) -> None:
    """A real 404 on the probe reaches the api_disabled branch end to end."""
    aioclient_mock.get(f"{GOOD_URL}/api/version", status=404)

    with pytest.raises(ApiDisabled):
        await _validate_input(hass, {CONF_URL: GOOD_URL, CONF_API_KEY: ""})


# ----------------------- api.py: InvalidUrlClientError is classified -----------------------


async def test_api_classifies_invalid_url_client_error() -> None:
    """The client turns ``InvalidUrlClientError`` into ``TraefikProxyInvalidUrlError``."""
    bad_session = MagicMock()
    bad_session.get.side_effect = aiohttp.InvalidUrlClientError("http;//bad")
    client = TraefikProxyApiClient(session=bad_session, base_url="http;//bad", auth=Auth())

    with pytest.raises(TraefikProxyInvalidUrlError):
        await client.async_get_version()


# ----------------------- Auth invariant -----------------------


@pytest.mark.parametrize(
    "auth",
    [
        pytest.param(Auth(), id="none"),
        pytest.param(Auth(mode=AuthMode.basic, username="capture", password="pw"), id="basic"),
        pytest.param(Auth(mode=AuthMode.bearer, token="s3cret-token"), id="bearer"),
    ],
)
async def test_every_auth_mode_round_trips_to_its_header(hass: object, aioclient_mock: Any, auth: Auth) -> None:
    """A real request records exactly the Authorization header the Auth promises (no bearer-only shortcut)."""
    # A new AuthMode must be added to the parametrization above.
    assert set(AuthMode) == {AuthMode.none, AuthMode.basic, AuthMode.bearer}
    aioclient_mock.get(f"{GOOD_URL}/api/version", json=load_fixture("v3.7", "version.json"))

    await TraefikProxyApiClient(async_get_clientsession(hass), GOOD_URL, auth).async_get_version()

    headers = aioclient_mock.mock_calls[0][3]
    assert headers.get("Authorization") == auth.header().get("Authorization")
    assert headers == auth.header()


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        pytest.param({CONF_API_KEY: "tok"}, Auth(mode=AuthMode.bearer, token="tok"), id="token"),
        pytest.param({CONF_API_KEY: ""}, Auth(), id="empty"),
        pytest.param({}, Auth(), id="missing"),
        pytest.param({CONF_API_KEY: None}, Auth(), id="none"),
    ],
)
def test_auth_from_entry_data(data: dict[str, Any], expected: Auth) -> None:
    """Entry data maps to bearer for a non-empty token and to no auth otherwise."""
    assert auth_from_entry_data({CONF_URL: GOOD_URL, **data}) == expected
