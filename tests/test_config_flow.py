"""Tests for the Traefik integration config flow.

Covers:
- ``STEP_USER_DATA_SCHEMA`` accepts any URL string (the shape check runs in
  the step) and defaults the auth type to none.
- ``_validate_input`` maps ``InvalidUrlClientError`` (aiohttp URL parse failure)
  to ``InvalidUrl`` and ``async_step_user`` surfaces ``errors["base"] = "invalid_url"``
  instead of HA's generic "Unknown error occurred".
- ``TraefikProxyApiClient`` classifies ``InvalidUrlClientError`` as
  ``TraefikProxyInvalidUrlError`` so neither the flow nor the coordinator sees a
  raw aiohttp exception.
- ``_validate_input`` probes ``/api/version`` and maps every client error class
  to its flow error (auth, API disabled, invalid URL, cannot connect).
- Every ``AuthMode`` round-trips through the client to the exact
  Authorization header ``Auth.header()`` promises, also from stored entry data.
- The user step stores entry data 1.3 and reauth replaces the credentials.
- The error matrix: every probe failure maps to its own form error in the
  user, reauth and reconfigure steps; credentials in the URL, empty URLs,
  unexpected exceptions and the order in which errors are decided.

Hermetic via ``aioclient_mock`` (HA's HTTP mock layer) — no live Traefik needed.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import probatio as vol
import pytest
from homeassistant.config_entries import ConfigEntryDisabler
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.setup import async_setup_component

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
    ApiDisabled,
    CannotConnect,
    InvalidAuth,
    InvalidUrl,
    Redirect,
    UrlHasCredentials,
    _check_url_shape,
    _validate_input,
)
from custom_components.traefik_proxy.const import (
    CONF_URL,
    CONF_VERIFY_SSL,
    DOMAIN,
)
from custom_components.traefik_proxy.coordinator import auth_from_entry_data
from tests.conftest import AUTH_TYPE, MOCK_URL, load_fixture, make_traefik_entry, stub_traefik

GOOD_URL = "https://traefik.example.com:8080"
USERINFO_URL = "https://u:p@traefik.example.com:8080"
CONSTRUCTION_ERROR = "Cannot combine AUTHORIZATION header with AUTH argument or credentials encoded in URL"
# admin:s3cret, base64-encoded (RFC 7617)
BASIC_HEADER = "Basic YWRtaW46czNjcmV0"
BEARER_DATA = {CONF_URL: GOOD_URL, AUTH_TYPE: "bearer", CONF_TOKEN: "tok"}
NONE_DATA = {CONF_URL: GOOD_URL, AUTH_TYPE: "none"}


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


def test_user_schema_defaults_to_no_auth() -> None:
    """Without an auth type the form selects none and adds no credential."""
    out = STEP_USER_DATA_SCHEMA({CONF_URL: GOOD_URL})
    assert out == {CONF_URL: GOOD_URL, CONF_VERIFY_SSL: True, AUTH_TYPE: "none"}


def test_user_schema_serializes_for_config_flow_endpoint() -> None:
    """The schema serializer HA's frontend JSON-over-WS config flow endpoint
    calls before shipping the form to the browser: ``probatio.to_field_list``.

    v0.1.3 regression: ``vol.All(cv.string, cv.url)`` serialized as
    ``<function url at 0x…>`` and raised ``ValueError`` in the reconfigure
    flow. The fix is to use a ``TextSelector(type=URL)`` for UI schemas so
    the serializer can introspect a known type instead of a function ref.
    """
    from homeassistant.helpers import config_validation as cv
    from probatio import to_field_list as serialize_schema

    from custom_components.traefik_proxy.config_flow import STEP_USER_DATA_SCHEMA

    serialized = serialize_schema(STEP_USER_DATA_SCHEMA, custom_serializer=cv.custom_serializer)
    assert isinstance(serialized, list)
    # URL field becomes a selector block of type=text/url.
    by_name = {field["name"]: field for field in serialized}
    assert list(by_name) == [CONF_URL, CONF_VERIFY_SSL, AUTH_TYPE, CONF_USERNAME, CONF_PASSWORD, CONF_TOKEN]
    assert by_name["url"]["selector"] == {"text": {"type": "url", "multiple": False, "multiline": False}}
    assert by_name[CONF_TOKEN]["selector"]["text"]["type"] == "password"


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
    """A malformed URL raises InvalidUrl without arguments, so the URL never reaches exc.args (IN-09)."""
    with pytest.raises(InvalidUrl) as err:
        _check_url_shape(url)
    assert err.value.args == ()


def test_check_url_shape_accepts_http_and_https() -> None:
    _check_url_shape("http://traefik.example.com:8080")
    _check_url_shape("https://traefik.local")


@pytest.mark.parametrize(
    "url",
    [
        "https://u:p@traefik.example.com:8080",
        "https://u@traefik.example.com",
        "https://:p@traefik.example.com",
        "http://u:@traefik.example.com:8080",
        "https://@traefik.example.com",
    ],
)
def test_check_url_shape_rejects_userinfo(url: str) -> None:
    """Credentials embedded in a well-formed URL raise UrlHasCredentials, without the URL as argument."""
    with pytest.raises(UrlHasCredentials) as err:
        _check_url_shape(url)
    assert err.value.args == ()


@pytest.mark.parametrize(
    "url",
    ["ftp://u:p@traefik.example.com", "https://u:p@traefik.example.com:99999", "u:p@traefik.example.com"],
)
def test_check_url_shape_reports_shape_before_credentials(url: str) -> None:
    """A URL that is malformed and carries credentials is invalid_url: the shape is decided first."""
    with pytest.raises(InvalidUrl):
        _check_url_shape(url)


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
            {CONF_URL: "http;//foo.bar", AUTH_TYPE: "bearer", CONF_TOKEN: "tok", CONF_VERIFY_SSL: True},
        )


async def test_validate_input_uses_urlparse_shape_check(hass: object) -> None:
    """Pre-flight shape check runs BEFORE aiohttp — bad URLs never reach the network."""
    with pytest.raises(InvalidUrl):
        await _validate_input(hass, {CONF_URL: "://broken", AUTH_TYPE: "bearer", CONF_TOKEN: "tok"})


async def test_validate_input_passes_on_good_url(hass: object, aioclient_mock: Any) -> None:
    """Happy-path probe succeeds against the captured /api/version and sends the bearer token."""
    aioclient_mock.get(f"{GOOD_URL}/api/version", json=load_fixture("v3.7", "version.json"))

    await _validate_input(hass, BEARER_DATA)

    assert aioclient_mock.mock_calls[0][3] == {"Authorization": "Bearer tok"}


async def test_validate_input_no_auth_does_not_send_authorization_header(hass: object, aioclient_mock: Any) -> None:
    """Auth type none -> no Authorization header sent -> Traefik with api.insecure works."""
    aioclient_mock.get(f"{GOOD_URL}/api/version", json=load_fixture("v3.7", "version.json"))

    await _validate_input(hass, NONE_DATA)

    assert "Authorization" not in aioclient_mock.mock_calls[0][3]


async def test_validate_input_rejects_token_with_control_characters(hass: object, aioclient_mock: Any) -> None:
    """A token the client refuses to send surfaces as invalid_auth without a request."""
    with pytest.raises(InvalidAuth):
        await _validate_input(hass, {**BEARER_DATA, CONF_TOKEN: "tok\r\nX-Injected: 1"})
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
        await _validate_input(hass, {**BEARER_DATA, CONF_VERIFY_SSL: True})


async def test_validate_input_maps_real_404_to_api_disabled(hass: object, aioclient_mock: Any) -> None:
    """A real 404 on the probe reaches the api_disabled branch end to end."""
    aioclient_mock.get(f"{GOOD_URL}/api/version", status=404)

    with pytest.raises(ApiDisabled):
        await _validate_input(hass, NONE_DATA)


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


ENTRY_DATA_BY_MODE = {
    "none": {AUTH_TYPE: "none"},
    "basic": {AUTH_TYPE: "basic", CONF_USERNAME: "admin", CONF_PASSWORD: "s3cret"},
    "bearer": {AUTH_TYPE: "bearer", CONF_TOKEN: "s3cret-token"},
}


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        pytest.param(ENTRY_DATA_BY_MODE["none"], Auth(), id="none"),
        pytest.param(
            ENTRY_DATA_BY_MODE["basic"], Auth(mode=AuthMode.basic, username="admin", password="s3cret"), id="basic"
        ),
        pytest.param(ENTRY_DATA_BY_MODE["bearer"], Auth(mode=AuthMode.bearer, token="s3cret-token"), id="bearer"),
        pytest.param({}, Auth(), id="missing-auth-type"),
    ],
)
def test_auth_from_entry_data(data: dict[str, Any], expected: Auth) -> None:
    """Entry data 1.3 maps its auth_type and the mode's credentials to Auth."""
    assert auth_from_entry_data({CONF_URL: GOOD_URL, CONF_VERIFY_SSL: True, **data}) == expected


@pytest.mark.parametrize(
    "data",
    [
        pytest.param({AUTH_TYPE: "digest"}, id="unknown-auth-type"),
        pytest.param({AUTH_TYPE: "basic", CONF_USERNAME: "admin"}, id="basic-without-password"),
        pytest.param({AUTH_TYPE: "bearer"}, id="bearer-without-token"),
    ],
)
def test_auth_from_entry_data_rejects_unusable_data(data: dict[str, Any]) -> None:
    """An unknown auth type or a mode without its credentials raises ValueError."""
    with pytest.raises(ValueError):
        auth_from_entry_data({CONF_URL: GOOD_URL, **data})


@pytest.mark.parametrize("mode", list(ENTRY_DATA_BY_MODE))
async def test_entry_data_round_trips_to_probe_header(hass: object, aioclient_mock: Any, mode: str) -> None:
    """Entry data 1.3 -> auth_from_entry_data -> the probe request carries exactly Auth.header()."""
    assert set(ENTRY_DATA_BY_MODE) == {m.value for m in AuthMode}
    aioclient_mock.get(f"{GOOD_URL}/api/version", json=load_fixture("v3.7", "version.json"))
    data = {CONF_URL: GOOD_URL, CONF_VERIFY_SSL: True, **ENTRY_DATA_BY_MODE[mode]}

    await _validate_input(hass, data)

    expected = auth_from_entry_data(data).header()
    assert aioclient_mock.mock_calls[0][3] == expected
    if mode == "none":
        assert expected == {}
    else:
        assert expected.get("Authorization", "").startswith("Basic " if mode == "basic" else "Bearer ")


# ----------------------- URL userinfo (credentials embedded in the URL) -----------------------


async def test_validate_input_rejects_userinfo_url_without_request(hass: object, aioclient_mock: Any) -> None:
    """A userinfo URL is refused by the shape check before any request is sent."""
    with pytest.raises(UrlHasCredentials):
        await _validate_input(hass, {**BEARER_DATA, CONF_URL: USERINFO_URL, CONF_VERIFY_SSL: True})

    assert aioclient_mock.call_count == 0


async def test_validate_input_maps_request_construction_error_to_invalid_url(hass: object, aioclient_mock: Any) -> None:
    """aiohttp refusing to build the probe request surfaces as invalid_url, never 'unknown'."""
    aioclient_mock.get(f"{GOOD_URL}/api/version", exc=ValueError(CONSTRUCTION_ERROR))

    with pytest.raises(InvalidUrl) as err:
        await _validate_input(hass, {**BEARER_DATA, CONF_VERIFY_SSL: True})
    assert err.value.args == ()


async def test_user_step_url_has_credentials(hass: Any, aioclient_mock: Any) -> None:
    """The user step answers a userinfo URL with url_has_credentials and sends no request."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_URL: USERINFO_URL, AUTH_TYPE: "bearer", CONF_TOKEN: "tok", CONF_VERIFY_SSL: True},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "url_has_credentials"}
    assert aioclient_mock.call_count == 0


# ----------------------- user step and reauth store entry data 1.3 -----------------------


async def test_user_step_basic_auth_reaches_traefik(hass: Any, aioclient_mock: Any) -> None:
    """Basic auth from the user step is stored as 1.3 data and sent on every /api/version request."""
    stub_traefik(aioclient_mock, base_url=MOCK_URL, rawdata={})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_URL: MOCK_URL,
            CONF_VERIFY_SSL: True,
            AUTH_TYPE: "basic",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "s3cret",
        },
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert (entry.version, entry.minor_version) == (1, 3)
    assert dict(entry.data) == {
        CONF_URL: MOCK_URL,
        CONF_VERIFY_SSL: True,
        AUTH_TYPE: "basic",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "s3cret",
    }
    versions = _version_requests(aioclient_mock)
    # The probe plus the setup of the new entry.
    assert len(versions) >= 2
    assert all((call[3] or {}).get("Authorization") == BASIC_HEADER for call in versions)


async def test_reauth_bearer_replaces_token_with_complete_data(hass: Any, aioclient_mock: Any) -> None:
    """Reauth stores complete 1.3 data and aborts with the central reauth_successful reason."""
    stub_traefik(aioclient_mock, base_url=MOCK_URL, rawdata={})
    entry = make_traefik_entry()
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {AUTH_TYPE: "bearer", CONF_TOKEN: "new"})
    await hass.async_block_till_done(wait_background_tasks=True)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert result["translation_domain"] == "homeassistant"
    assert dict(entry.data) == {CONF_URL: MOCK_URL, CONF_VERIFY_SSL: True, AUTH_TYPE: "bearer", CONF_TOKEN: "new"}
    assert _probe_auth(aioclient_mock) == "Bearer new"


def _version_requests(aioclient_mock: Any) -> list[Any]:
    return [call for call in aioclient_mock.mock_calls if str(call[1]).endswith("/api/version")]


def _probe_auth(aioclient_mock: Any) -> str | None:
    """Authorization header of the first /api/version request (the flow probe for entries not set up)."""
    versions = _version_requests(aioclient_mock)
    assert versions, "no /api/version request recorded"
    headers: dict[str, str] = versions[0][3] or {}
    return headers.get("Authorization")


# ----------------------- conditional credential fields -----------------------

BASIC_VISIBLE = {"field": AUTH_TYPE, "value": "basic"}
BEARER_VISIBLE = {"field": AUTH_TYPE, "value": "bearer"}
BASIC_INPUT = {AUTH_TYPE: "basic", CONF_USERNAME: "admin", CONF_PASSWORD: "s3cret"}


def _markers(result: Any) -> dict[str, Any]:
    """Return {field name: schema marker} of a form result."""
    return {str(marker): marker for marker in result["data_schema"].schema}


def _assert_auth_markers(markers: dict[str, Any], default_auth: str) -> None:
    """The auth selector defaults to ``default_auth``; credentials are visible only for their type."""
    assert markers[AUTH_TYPE].default() == default_auth
    assert markers[CONF_USERNAME].visible == BASIC_VISIBLE
    assert markers[CONF_PASSWORD].visible == BASIC_VISIBLE
    assert markers[CONF_TOKEN].visible == BEARER_VISIBLE
    for key in (CONF_USERNAME, CONF_PASSWORD, CONF_TOKEN):
        # Never a stored value as default or suggested value.
        assert markers[key].default is vol.UNDEFINED, key
        assert markers[key].description is None, key


def _basic_entry(hass: Any) -> Any:
    entry = make_traefik_entry(data={CONF_URL: MOCK_URL, CONF_VERIFY_SSL: True, **BASIC_INPUT})
    entry.add_to_hass(hass)
    return entry


async def test_user_form_credential_fields_are_visible_per_auth_type(hass: Any) -> None:
    """The user form defaults to no auth; username/password show for basic, token for bearer."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})

    _assert_auth_markers(_markers(result), "none")


async def test_reauth_form_credential_fields_are_visible_per_auth_type(hass: Any) -> None:
    """The reauth form defaults to the stored auth type and pre-fills no credential."""
    entry = _basic_entry(hass)

    result = await entry.start_reauth_flow(hass)

    markers = _markers(result)
    assert set(markers) == {AUTH_TYPE, CONF_USERNAME, CONF_PASSWORD, CONF_TOKEN}
    _assert_auth_markers(markers, "basic")


async def test_reconfigure_form_credential_fields_are_visible_per_auth_type(hass: Any) -> None:
    """The reconfigure form defaults to the stored auth type and pre-fills no credential."""
    entry = _basic_entry(hass)

    result = await entry.start_reconfigure_flow(hass)

    _assert_auth_markers(_markers(result), "basic")


def test_user_schema_serializes_auth_selector_and_secrets() -> None:
    """The serialized form carries the translated auth selector and password inputs for both secrets."""
    from homeassistant.helpers import config_validation as cv
    from probatio import to_field_list as serialize_schema

    by_name = {
        field["name"]: field
        for field in serialize_schema(STEP_USER_DATA_SCHEMA, custom_serializer=cv.custom_serializer)
    }

    assert set(by_name) == {CONF_URL, CONF_VERIFY_SSL, AUTH_TYPE, CONF_USERNAME, CONF_PASSWORD, CONF_TOKEN}
    select = by_name[AUTH_TYPE]["selector"]["select"]
    assert select["translation_key"] == "auth_type"
    assert select["options"] == ["none", "basic", "bearer"]
    assert by_name[CONF_PASSWORD]["selector"]["text"]["type"] == "password"
    assert by_name[CONF_TOKEN]["selector"]["text"]["type"] == "password"


async def test_flow_api_sends_visible_conditions(hass: Any, hass_client: Any) -> None:
    """The config flow HTTP API ships the visible condition of each credential field to the frontend."""
    assert await async_setup_component(hass, "config", {})
    client = await hass_client()

    response = await client.post("/api/config/config_entries/flow", json={"handler": DOMAIN})

    assert response.status == 200
    fields = {field["name"]: field for field in (await response.json())["data_schema"]}
    assert fields[CONF_TOKEN]["visible"] == BEARER_VISIBLE
    assert fields[CONF_USERNAME]["visible"] == BASIC_VISIBLE
    assert fields[CONF_PASSWORD]["visible"] == BASIC_VISIBLE
    assert "visible" not in fields[CONF_URL]


async def _submit_user(hass: Any, user_input: dict[str, Any]) -> Any:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: MOCK_URL, CONF_VERIFY_SSL: True, **user_input}
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    return result


@pytest.mark.parametrize(
    ("submitted", "expected"),
    [
        pytest.param({AUTH_TYPE: "none", CONF_TOKEN: "stale", CONF_USERNAME: "stale"}, {AUTH_TYPE: "none"}, id="none"),
        pytest.param({**BASIC_INPUT, CONF_TOKEN: "stale"}, BASIC_INPUT, id="basic"),
        pytest.param(
            {AUTH_TYPE: "bearer", CONF_TOKEN: "tok", CONF_PASSWORD: "stale"},
            {AUTH_TYPE: "bearer", CONF_TOKEN: "tok"},
            id="bearer",
        ),
    ],
)
async def test_user_step_strips_hidden_credentials(
    hass: Any, aioclient_mock: Any, submitted: dict[str, Any], expected: dict[str, Any]
) -> None:
    """Credentials of another auth type in the submitted form are never stored."""
    stub_traefik(aioclient_mock, base_url=MOCK_URL, rawdata={})

    result = await _submit_user(hass, submitted)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert dict(result["result"].data) == {CONF_URL: MOCK_URL, CONF_VERIFY_SSL: True, **expected}


@pytest.mark.parametrize(
    ("submitted", "errors"),
    [
        pytest.param({AUTH_TYPE: "basic", CONF_PASSWORD: "s3cret"}, {CONF_USERNAME: "required"}, id="no-username"),
        pytest.param({AUTH_TYPE: "basic", CONF_USERNAME: "admin"}, {CONF_PASSWORD: "required"}, id="no-password"),
        pytest.param(
            {AUTH_TYPE: "basic", CONF_USERNAME: "", CONF_PASSWORD: ""},
            {CONF_USERNAME: "required", CONF_PASSWORD: "required"},
            id="neither",
        ),
        pytest.param({AUTH_TYPE: "bearer"}, {CONF_TOKEN: "required"}, id="no-token"),
        pytest.param({AUTH_TYPE: "bearer", CONF_TOKEN: ""}, {CONF_TOKEN: "required"}, id="empty-token"),
    ],
)
async def test_user_step_requires_credentials_of_auth_type(
    hass: Any, aioclient_mock: Any, submitted: dict[str, Any], errors: dict[str, str]
) -> None:
    """Missing credentials of the chosen type are field errors; Traefik is not contacted."""
    result = await _submit_user(hass, submitted)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == errors
    assert aioclient_mock.call_count == 0


@pytest.mark.parametrize(
    ("submitted", "errors"),
    [
        pytest.param({**BASIC_INPUT, CONF_USERNAME: "ad:min"}, {CONF_USERNAME: "invalid_auth"}, id="colon-username"),
        pytest.param({**BASIC_INPUT, CONF_USERNAME: "ad\tmin"}, {CONF_USERNAME: "invalid_auth"}, id="control-username"),
        pytest.param({**BASIC_INPUT, CONF_PASSWORD: "s3\x00cret"}, {CONF_PASSWORD: "invalid_auth"}, id="password"),
        pytest.param({AUTH_TYPE: "bearer", CONF_TOKEN: "to\nken"}, {CONF_TOKEN: "invalid_auth"}, id="token"),
    ],
)
async def test_user_step_rejected_credentials_mark_their_field(
    hass: Any, aioclient_mock: Any, submitted: dict[str, Any], errors: dict[str, str]
) -> None:
    """A credential the client cannot send marks its field invalid_auth; Traefik is not contacted."""
    result = await _submit_user(hass, submitted)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == errors
    assert aioclient_mock.call_count == 0


async def test_unknown_auth_type_is_rejected_without_request(hass: Any, aioclient_mock: Any) -> None:
    """An auth type the integration does not know (bypassing the selector) is refused without a request."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data={CONF_URL: MOCK_URL, AUTH_TYPE: "digest"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {AUTH_TYPE: "invalid_auth"}
    assert aioclient_mock.call_count == 0


# ----------------------- reauth switches the auth type -----------------------


async def _reauth(hass: Any, entry: Any, user_input: dict[str, Any]) -> Any:
    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)
    await hass.async_block_till_done(wait_background_tasks=True)
    return result


async def test_reauth_basic_to_bearer_drops_username_and_password(hass: Any, aioclient_mock: Any) -> None:
    """Switching a basic entry to bearer in reauth leaves no username or password."""
    stub_traefik(aioclient_mock, base_url=MOCK_URL, rawdata={})
    entry = _basic_entry(hass)

    result = await _reauth(hass, entry, {AUTH_TYPE: "bearer", CONF_TOKEN: "new"})

    assert result["reason"] == "reauth_successful"
    assert dict(entry.data) == {CONF_URL: MOCK_URL, CONF_VERIFY_SSL: True, AUTH_TYPE: "bearer", CONF_TOKEN: "new"}


async def test_reauth_bearer_to_none_drops_token(hass: Any, aioclient_mock: Any) -> None:
    """Switching a bearer entry to none in reauth leaves no token and sends no header."""
    stub_traefik(aioclient_mock, base_url=MOCK_URL, rawdata={})
    entry = make_traefik_entry()
    entry.add_to_hass(hass)

    result = await _reauth(hass, entry, {AUTH_TYPE: "none"})

    assert result["reason"] == "reauth_successful"
    assert dict(entry.data) == {CONF_URL: MOCK_URL, CONF_VERIFY_SSL: True, AUTH_TYPE: "none"}
    assert _probe_auth(aioclient_mock) is None


async def test_reauth_to_basic_probes_and_stores_both(hass: Any, aioclient_mock: Any) -> None:
    """Switching a bearer entry to basic in reauth probes with the Basic header and stores both credentials."""
    stub_traefik(aioclient_mock, base_url=MOCK_URL, rawdata={})
    entry = make_traefik_entry()
    entry.add_to_hass(hass)

    result = await _reauth(hass, entry, BASIC_INPUT)

    assert result["reason"] == "reauth_successful"
    assert _probe_auth(aioclient_mock) == BASIC_HEADER
    assert dict(entry.data) == {CONF_URL: MOCK_URL, CONF_VERIFY_SSL: True, **BASIC_INPUT}


@pytest.mark.parametrize(
    ("submitted", "errors"),
    [
        pytest.param({AUTH_TYPE: "bearer", CONF_TOKEN: ""}, {CONF_TOKEN: "required"}, id="token"),
        pytest.param({**BASIC_INPUT, CONF_PASSWORD: ""}, {CONF_PASSWORD: "required"}, id="password"),
    ],
)
async def test_reauth_requires_every_credential(
    hass: Any, aioclient_mock: Any, submitted: dict[str, Any], errors: dict[str, str]
) -> None:
    """Reauth never falls back to a stored secret: an empty one is required, nothing is sent or stored."""
    entry = _basic_entry(hass)
    before = dict(entry.data)

    result = await _reauth(hass, entry, submitted)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == errors
    assert dict(entry.data) == before
    assert aioclient_mock.call_count == 0


# ----------------------- unique_id host:port and title -----------------------


async def test_user_step_unique_id_is_host_port_and_title_is_host(hass: Any, aioclient_mock: Any) -> None:
    """A new entry is identified by host:port and named after its host."""
    stub_traefik(aioclient_mock, base_url=MOCK_URL, rawdata={})

    result = await _submit_user(hass, {AUTH_TYPE: "none"})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "traefik.example.com:8080"
    assert result["title"] == "traefik.example.com"


@pytest.mark.parametrize(
    ("existing_url", "existing_unique_id", "new_url"),
    [
        pytest.param(
            MOCK_URL, "traefik.example.com:8080", "https://TRAEFIK.example.com:8080/", id="host-case-trailing-slash"
        ),
        pytest.param(
            "https://traefik.example.com",
            "traefik.example.com:443",
            "https://traefik.example.com:443",
            id="default-port",
        ),
    ],
)
async def test_user_step_same_host_port_aborts_without_request(
    hass: Any, aioclient_mock: Any, existing_url: str, existing_unique_id: str, new_url: str
) -> None:
    """The same Traefik (same host:port) cannot be added twice; it is not contacted."""
    make_traefik_entry(data={CONF_URL: existing_url, AUTH_TYPE: "none"}, unique_id=existing_unique_id).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: new_url, AUTH_TYPE: "none"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert aioclient_mock.call_count == 0


async def test_user_step_other_port_on_same_host_is_a_new_entry(hass: Any, aioclient_mock: Any) -> None:
    """A second Traefik on the same host but another port is a separate entry."""
    make_traefik_entry().add_to_hass(hass)
    other_url = "https://traefik.example.com:8443"
    stub_traefik(aioclient_mock, base_url=other_url, rawdata={})

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: other_url, AUTH_TYPE: "none"})
    await hass.async_block_till_done(wait_background_tasks=True)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "traefik.example.com:8443"


def _legacy_entry(**kwargs: Any) -> Any:
    """A 1.2 entry that was never migrated: it still carries the bare-host unique_id (disabled during the upgrade)."""
    return make_traefik_entry(minor_version=2, disabled_by=ConfigEntryDisabler.USER, **kwargs)


@pytest.mark.parametrize(
    "new_url",
    [
        pytest.param(MOCK_URL, id="same-url"),
        pytest.param("https://TRAEFIK.example.com:8080/", id="host-case-trailing-slash"),
    ],
)
async def test_user_step_legacy_unique_id_owner_aborts_without_request(
    hass: Any, aioclient_mock: Any, new_url: str
) -> None:
    """An entry still on the legacy bare-host unique_id owns its host:port; adding it again aborts (WR-02)."""
    _legacy_entry().add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: new_url, AUTH_TYPE: "none"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert aioclient_mock.call_count == 0


@pytest.mark.parametrize(
    "legacy_url",
    [
        pytest.param("https://traefik.example.com:8443", id="other-port"),
        pytest.param("https://traefik.example.com:99999", id="unusable-port"),
    ],
)
async def test_user_step_legacy_entry_on_other_port_is_no_owner(
    hass: Any, aioclient_mock: Any, legacy_url: str
) -> None:
    """A legacy bare-host entry owns only the host:port of its own URL, not every port of the host."""
    _legacy_entry(data={CONF_URL: legacy_url, CONF_VERIFY_SSL: True}).add_to_hass(hass)
    stub_traefik(aioclient_mock, base_url=MOCK_URL, rawdata={})

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: MOCK_URL, AUTH_TYPE: "none"})
    await hass.async_block_till_done(wait_background_tasks=True)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "traefik.example.com:8080"


# ----------------------- redirects (IN-01) -----------------------

INTRUDER = "https://intruder.example.org/api/version"


def _stub_redirect(aioclient_mock: Any, status: int = 302) -> None:
    """/api/version answers with a redirect to another host."""
    aioclient_mock.get(f"{MOCK_URL}/api/version", status=status, headers={"Location": INTRUDER})


def _assert_single_probe_without_location(aioclient_mock: Any) -> None:
    """Exactly one request was sent; the Location target was never contacted."""
    assert aioclient_mock.call_count == 1
    assert not [call for call in aioclient_mock.mock_calls if "intruder.example.org" in str(call[1])]


async def test_user_step_redirect_shows_redirect_error(hass: Any, aioclient_mock: Any) -> None:
    """A 3xx answer to the user step's probe is the 'redirect' form error; the redirect is not followed."""
    _stub_redirect(aioclient_mock)

    result = await _submit_user(hass, {AUTH_TYPE: "bearer", CONF_TOKEN: "tok"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "redirect"}
    _assert_single_probe_without_location(aioclient_mock)


async def test_reauth_redirect_shows_redirect_error(hass: Any, aioclient_mock: Any) -> None:
    """A 3xx answer to the reauth probe is the 'redirect' form error; the entry is unchanged."""
    _stub_redirect(aioclient_mock)
    entry = make_traefik_entry()
    entry.add_to_hass(hass)
    before = dict(entry.data)

    result = await _reauth(hass, entry, {AUTH_TYPE: "bearer", CONF_TOKEN: "new"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "redirect"}
    assert dict(entry.data) == before
    _assert_single_probe_without_location(aioclient_mock)


@pytest.mark.parametrize("status", [301, 307, 308])
async def test_validate_input_maps_redirect_status_to_redirect(hass: Any, aioclient_mock: Any, status: int) -> None:
    """Every redirect status of the probe raises the flow's Redirect sentinel."""
    _stub_redirect(aioclient_mock, status)

    with pytest.raises(Redirect):
        await _validate_input(hass, {**BEARER_DATA, CONF_URL: MOCK_URL, CONF_VERIFY_SSL: True})
    _assert_single_probe_without_location(aioclient_mock)


@pytest.mark.parametrize("status", [400, 500])
async def test_validate_input_maps_other_error_status_to_cannot_connect(
    hass: Any, aioclient_mock: Any, status: int
) -> None:
    """A non-redirect error status keeps mapping to cannot_connect (the redirect branch is not a catch-all)."""
    aioclient_mock.get(f"{MOCK_URL}/api/version", status=status)

    with pytest.raises(CannotConnect):
        await _validate_input(hass, {**BEARER_DATA, CONF_URL: MOCK_URL, CONF_VERIFY_SSL: True})


# ----------------------- error matrix: every probe failure in every step -----------------------

STEPS = ("user", "reauth", "reconfigure")
SECRET_TOKEN = "s3cret-matrix-token"


async def _run_step(hass: Any, step: str, user_input: dict[str, Any]) -> Any:
    """Submit ``user_input`` (merged over a valid bearer input) to ``step`` and return the result.

    reauth and reconfigure run against a bearer entry for ``MOCK_URL``; the
    user step gets the URL in its input. reauth has no URL field.
    """
    submitted = {AUTH_TYPE: "bearer", CONF_TOKEN: SECRET_TOKEN, **user_input}
    if step == "user":
        return await _submit_user(hass, submitted)
    entry = make_traefik_entry()
    entry.add_to_hass(hass)
    if step == "reauth":
        submitted.pop(CONF_URL, None)
        return await _reauth(hass, entry, submitted)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: MOCK_URL, CONF_VERIFY_SSL: True, **submitted}
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    return result


@pytest.mark.parametrize("step", STEPS)
@pytest.mark.parametrize(
    ("answer", "error"),
    [
        pytest.param({"status": 401}, "invalid_auth", id="401"),
        pytest.param({"status": 403}, "invalid_auth", id="403"),
        pytest.param({"status": 404}, "api_disabled", id="404"),
        pytest.param({"status": 500}, "cannot_connect", id="500"),
        pytest.param({"exc": aiohttp.ClientError()}, "cannot_connect", id="client-error"),
        pytest.param({"exc": TimeoutError()}, "cannot_connect", id="timeout"),
        pytest.param({"status": 302, "headers": {"Location": INTRUDER}}, "redirect", id="302"),
    ],
)
async def test_error_matrix_probe_failure_maps_to_its_key(
    hass: Any, aioclient_mock: Any, step: str, answer: dict[str, Any], error: str
) -> None:
    """Each probe failure shows its own base error in each step; one request, nothing stored."""
    aioclient_mock.get(f"{MOCK_URL}/api/version", **answer)

    result = await _run_step(hass, step, {})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
    assert aioclient_mock.call_count == 1
    assert not [call for call in aioclient_mock.mock_calls if "intruder.example.org" in str(call[1])]
    entries = hass.config_entries.async_entries(DOMAIN)
    if step == "user":
        assert entries == []
    else:
        assert dict(entries[0].data) == dict(make_traefik_entry().data)


@pytest.mark.parametrize("step", STEPS)
async def test_error_matrix_request_construction_error_is_invalid_url(
    hass: Any, aioclient_mock: Any, step: str
) -> None:
    """aiohttp refusing to build the probe request is invalid_url in every step, never 'unknown'."""
    aioclient_mock.get(f"{MOCK_URL}/api/version", exc=ValueError(CONSTRUCTION_ERROR))

    result = await _run_step(hass, step, {})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_url"}


async def test_reauth_stored_url_has_credentials(hass: Any, aioclient_mock: Any) -> None:
    """A stored URL that still carries credentials is url_has_credentials in reauth; nothing is sent."""
    entry = make_traefik_entry(data={CONF_URL: USERINFO_URL, CONF_VERIFY_SSL: True, AUTH_TYPE: "none"})
    entry.add_to_hass(hass)
    before = dict(entry.data)

    result = await _reauth(hass, entry, {AUTH_TYPE: "bearer", CONF_TOKEN: "new"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "url_has_credentials"}
    assert dict(entry.data) == before
    assert aioclient_mock.call_count == 0


@pytest.mark.parametrize("step", STEPS)
async def test_unknown_error_is_logged_once_without_input(
    hass: Any, aioclient_mock: Any, caplog: pytest.LogCaptureFixture, step: str
) -> None:
    """An unexpected exception during validation is 'unknown', logged once with a traceback and no input."""
    caplog.set_level(logging.DEBUG)
    with patch.object(TraefikProxyApiClient, "async_get_version", AsyncMock(side_effect=RuntimeError("boom"))):
        result = await _run_step(hass, step, {})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}
    records = [
        record
        for record in caplog.records
        if record.name == "custom_components.traefik_proxy.config_flow" and record.levelno >= logging.ERROR
    ]
    assert len(records) == 1
    assert records[0].exc_info is not None
    assert "traefik.example.com" not in caplog.text
    assert SECRET_TOKEN not in caplog.text


async def test_unknown_error_log_has_no_basic_credentials(
    hass: Any, aioclient_mock: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """With basic auth neither the username nor the password reaches the 'unknown' log record."""
    caplog.set_level(logging.DEBUG)
    with patch.object(TraefikProxyApiClient, "async_get_version", AsyncMock(side_effect=RuntimeError("boom"))):
        result = await _submit_user(
            hass, {AUTH_TYPE: "basic", CONF_USERNAME: "matrix-user", CONF_PASSWORD: "matrix-pw"}
        )

    assert result["errors"] == {"base": "unknown"}
    assert "matrix-user" not in caplog.text
    assert "matrix-pw" not in caplog.text


@pytest.mark.parametrize("url", ["", "   "])
async def test_user_step_empty_url_is_invalid_url(hass: Any, aioclient_mock: Any, url: str) -> None:
    """An empty or blank URL is invalid_url; Traefik is not contacted."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: url, AUTH_TYPE: "none"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_url"}
    assert aioclient_mock.call_count == 0


@pytest.mark.parametrize(
    ("url", "user_input", "existing", "expected"),
    [
        pytest.param(
            "ftp://u:p@traefik.example.com", {AUTH_TYPE: "none"}, False, {"base": "invalid_url"}, id="shape-first"
        ),
        pytest.param(
            "https://u:p@traefik.example.com:8080",
            {AUTH_TYPE: "basic", CONF_USERNAME: "admin"},
            False,
            {"base": "url_has_credentials"},
            id="url-credentials-before-fields",
        ),
        pytest.param(
            "https://u:p@traefik.example.com:8080",
            {AUTH_TYPE: "none"},
            True,
            {"base": "url_has_credentials"},
            id="url-credentials-before-duplicate",
        ),
        pytest.param(
            MOCK_URL,
            {AUTH_TYPE: "basic", CONF_USERNAME: "admin"},
            True,
            "already_configured",
            id="duplicate-before-fields",
        ),
    ],
)
async def test_user_step_error_order(
    hass: Any, aioclient_mock: Any, url: str, user_input: dict[str, Any], existing: bool, expected: Any
) -> None:
    """Only the first failing stage is reported: URL shape, URL credentials, duplicate, fields, probe."""
    if existing:
        make_traefik_entry().add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: url, **user_input})

    if expected == "already_configured":
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == expected
    else:
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == expected
    assert aioclient_mock.call_count == 0


FLOW_ERROR_KEYS = {
    "invalid_url",
    "url_has_credentials",
    "invalid_auth",
    "cannot_connect",
    "api_disabled",
    "redirect",
    "required",
    "unknown",
}


@pytest.mark.parametrize("language", ["en", "de"])
def test_flow_error_keys_have_texts(language: str) -> None:
    """Every form error and the already_configured abort have a text in en and de, without a URL literal."""
    import json
    from pathlib import Path

    import custom_components.traefik_proxy as integration

    path = Path(integration.__file__).parent / "translations" / f"{language}.json"
    config = json.loads(path.read_text(encoding="utf-8"))["config"]

    assert set(config["error"]) == FLOW_ERROR_KEYS
    assert config["abort"]["already_configured"]
    for text in [*config["error"].values(), config["abort"]["already_configured"]]:
        assert text.strip()
        assert "://" not in text
        assert "{" not in text
