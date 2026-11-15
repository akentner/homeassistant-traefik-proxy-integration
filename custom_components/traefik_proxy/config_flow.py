"""Config flow for the Traefik integration.

- :meth:`TraefikProxyConfigFlow.async_step_user` sets up an entry: the Traefik
  API URL, TLS verification and how the API is protected (no authentication,
  basic auth or a bearer token). The credential fields are shown only for the
  auth type that uses them; Home Assistant drops hidden fields from the
  submitted data.
- :meth:`TraefikProxyConfigFlow.async_step_reauth_confirm` asks for new
  credentials for the stored URL when Traefik rejected the stored ones.
- :meth:`TraefikProxyConfigFlow.async_step_reconfigure` changes URL, TLS
  verification and credentials of an existing entry. Secrets are never sent to
  the form; with an unchanged auth type an empty secret keeps the stored one.
- :class:`TraefikProxyOptionsFlow` holds the polling and certificate options;
  saving changed options reloads the entry.

Every step probes ``/api/version`` before it stores anything, and stores the
complete entry data (``_entry_data``), so no credential of an auth type the
entry no longer uses is kept.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import probatio as vol
from homeassistant import data_entry_flow
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    Auth,
    AuthMode,
    TraefikProxyApiClient,
    TraefikProxyApiError,
    TraefikProxyAuthError,
    TraefikProxyInvalidUrlError,
    TraefikProxyNotFoundError,
)
from .const import (
    CONF_AUTH_TYPE,
    CONF_SCAN_INTERVAL,
    CONF_TLS_WARN_DAYS,
    CONF_URL,
    CONF_VERIFY_SSL,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TLS_WARN_DAYS,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MAX_TLS_WARN_DAYS,
    MIN_SCAN_INTERVAL,
    MIN_TLS_WARN_DAYS,
)
from .coordinator import auth_from_entry_data, effective_verify_ssl, url_host, url_unique_id

_LOGGER = logging.getLogger(__name__)

# UI schemas use Home Assistant's typed selectors so the frontend renders the
# right input widget and the schema serializes for the config flow API (a raw
# ``cv.url`` function cannot be serialized). URL shape is enforced
# server-side by :func:`_check_url_shape` (``errors["base"] = "invalid_url"``).
_URL_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.URL))
_SECRET_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
_AUTH_TYPE_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=[mode.value for mode in AuthMode],
        translation_key=CONF_AUTH_TYPE,
        mode=SelectSelectorMode.LIST,
    )
)

# Credential fields each auth type needs, in the order they are checked.
_CREDENTIAL_KEYS: dict[AuthMode, tuple[str, ...]] = {
    AuthMode.none: (),
    AuthMode.basic: (CONF_USERNAME, CONF_PASSWORD),
    AuthMode.bearer: (CONF_TOKEN,),
}


def _auth_fields(default_auth: str) -> dict[Any, Any]:
    """Return the auth type selector and the credential fields shown for it.

    The credential fields are optional at schema level and visible only for
    their auth type; the step enforces the credentials of the chosen type.
    Secrets never carry a default or suggested value.
    """
    return {
        vol.Required(CONF_AUTH_TYPE, default=default_auth): _AUTH_TYPE_SELECTOR,
        data_entry_flow.Optional(
            CONF_USERNAME, visible={"field": CONF_AUTH_TYPE, "value": AuthMode.basic.value}
        ): TextSelector(),
        data_entry_flow.Optional(
            CONF_PASSWORD, visible={"field": CONF_AUTH_TYPE, "value": AuthMode.basic.value}
        ): _SECRET_SELECTOR,
        data_entry_flow.Optional(
            CONF_TOKEN, visible={"field": CONF_AUTH_TYPE, "value": AuthMode.bearer.value}
        ): _SECRET_SELECTOR,
    }


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): _URL_SELECTOR,
        vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): BooleanSelector(),
        **_auth_fields(AuthMode.none.value),
    }
)


# Sentinel exceptions for the probe flow
class CannotConnect(Exception):
    """Network or Traefik unreachable."""


class InvalidAuth(Exception):
    """Traefik returned 401/403."""


class ApiDisabled(Exception):
    """Traefik's API is not enabled (404 on the /api/version probe)."""


class InvalidUrl(Exception):
    """The provided URL is malformed or carries credentials (userinfo)."""


_ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


def _check_url_shape(url: str) -> None:
    """Pre-flight URL shape check before handing it to aiohttp.

    Catches the common class of malformed-input bugs that the
    ``TextSelector(type=URL)`` field cannot block (e.g. ``http;//`` from
    autocomplete / paste mistakes). Raises :class:`InvalidUrl` if the URL
    cannot be parsed, is missing a scheme, has a non-HTTP scheme, has no
    host or an invalid port, or carries credentials (``user:pass@host``):
    credentials belong in the authentication fields. A URL that passes has
    a :func:`url_unique_id`.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in _ALLOWED_URL_SCHEMES or not parsed.hostname:
            raise InvalidUrl(url)
        if parsed.username or parsed.password:
            raise InvalidUrl(url)
        # Raises ValueError for a port out of range or not a number.
        _ = parsed.port
    except ValueError:
        raise InvalidUrl(url) from None


async def _validate_input(hass: HomeAssistant, data: Mapping[str, Any]) -> None:
    """Probe /api/version with entry data and map client errors to flow errors.

    401/403 -> InvalidAuth, 404 -> ApiDisabled, invalid URL -> InvalidUrl,
    everything else -> CannotConnect. Should aiohttp refuse to build the
    request for the URL, the client error maps to InvalidUrl.
    """
    _check_url_shape(data[CONF_URL])
    try:
        auth = auth_from_entry_data(data)
    except ValueError:
        # A credential the client refuses to send (e.g. a control character).
        raise InvalidAuth from None
    client = TraefikProxyApiClient(
        session=async_get_clientsession(hass),
        base_url=data[CONF_URL],
        auth=auth,
        verify_ssl=data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
    )
    try:
        async with asyncio.timeout(10):
            await client.async_get_version()
    except TraefikProxyAuthError:
        raise InvalidAuth from None
    except TraefikProxyNotFoundError:
        raise ApiDisabled from None
    except TraefikProxyInvalidUrlError:
        raise InvalidUrl(data[CONF_URL]) from None
    except TraefikProxyApiError, TimeoutError:
        raise CannotConnect from None


async def _async_probe_errors(hass: HomeAssistant, data: Mapping[str, Any]) -> dict[str, str]:
    """Probe Traefik with entry data; return the form errors (empty on success)."""
    try:
        await _validate_input(hass, data)
    except InvalidUrl:
        return {"base": "invalid_url"}
    except InvalidAuth:
        return {"base": "invalid_auth"}
    except ApiDisabled:
        return {"base": "api_disabled"}
    except CannotConnect:
        return {"base": "cannot_connect"}
    return {}


def _rejected_field(mode: AuthMode, credentials: Mapping[str, str]) -> str:
    """Return the credential field ``Auth`` rejected for complete credentials."""
    if mode is AuthMode.basic:
        try:
            Auth(mode=AuthMode.basic, username=credentials[CONF_USERNAME], password="-")
        except ValueError:
            return CONF_USERNAME
        return CONF_PASSWORD
    return CONF_TOKEN


def _collect_credentials(
    user_input: Mapping[str, Any], auth_type: str, stored: Mapping[str, Any] | None = None
) -> tuple[dict[str, str], dict[str, str]]:
    """Return the credentials of ``auth_type`` from the form and the field errors.

    A missing or empty field falls back to ``stored`` when given (reconfigure
    with an unchanged auth type) and is otherwise ``required``. Complete
    credentials ``Auth`` rejects (a ':' or control character in the username,
    a control character in a secret) mark that field ``invalid_auth``.
    """
    try:
        mode = AuthMode(auth_type)
    except ValueError:
        return {}, {CONF_AUTH_TYPE: "invalid_auth"}
    credentials: dict[str, str] = {}
    errors: dict[str, str] = {}
    for key in _CREDENTIAL_KEYS[mode]:
        value = user_input.get(key) or (stored or {}).get(key)
        if isinstance(value, str) and value:
            credentials[key] = value
        else:
            errors[key] = "required"
    if errors:
        return credentials, errors
    try:
        Auth(mode=mode, **credentials)
    except ValueError:
        errors[_rejected_field(mode, credentials)] = "invalid_auth"
    return credentials, errors


def _entry_data(url: str, verify_ssl: bool, auth_type: str, credentials: Mapping[str, str]) -> dict[str, Any]:
    """Build complete entry data: URL, TLS verification, auth type and its credentials."""
    return {CONF_URL: url, CONF_VERIFY_SSL: verify_ssl, CONF_AUTH_TYPE: auth_type, **credentials}


def _stored_auth_type(data: Mapping[str, Any]) -> str:
    """Return the entry's auth type as a selector value (none for an unknown type)."""
    stored = data.get(CONF_AUTH_TYPE)
    return stored if stored in {mode.value for mode in AuthMode} else AuthMode.none.value


def _number_selector(minimum: int, maximum: int, unit: str) -> NumberSelector:
    """Return a whole-number input box from ``minimum`` to ``maximum`` in ``unit``."""
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=1,
            unit_of_measurement=unit,
            mode=NumberSelectorMode.BOX,
        )
    )


class TraefikProxyOptionsFlow(OptionsFlowWithReload):
    """Options of a Traefik entry; saving changed options reloads the entry.

    - ``scan_interval``: seconds between two polls of the Traefik API
      (15..300, default 15).
    - ``verify_ssl``: TLS verification of the Traefik API (default: the
      effective value of the entry).
    - ``tls_warn_days``: days before expiry at which a certificate counts as
      expiring (1..90, default 14).

    The selectors validate the ranges, so a value outside one never reaches
    the step. Home Assistant reloads the entry only when the saved options
    differ from the stored ones; the reloaded entry reads them at setup.
    """

    config_entry: ConfigEntry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the options form pre-filled with the active values, or store the submitted ones.

        The number selectors return floats; both numbers are stored as int.
        Options the form does not show are kept.
        """
        current = self.config_entry.options

        if user_input is not None:
            return self.async_create_entry(
                data={
                    **current,
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_VERIFY_SSL: bool(user_input[CONF_VERIFY_SSL]),
                    CONF_TLS_WARN_DAYS: int(user_input[CONF_TLS_WARN_DAYS]),
                }
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL, default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ): _number_selector(MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL, "s"),
                vol.Required(CONF_VERIFY_SSL, default=effective_verify_ssl(self.config_entry)): BooleanSelector(),
                vol.Required(
                    CONF_TLS_WARN_DAYS, default=current.get(CONF_TLS_WARN_DAYS, DEFAULT_TLS_WARN_DAYS)
                ): _number_selector(MIN_TLS_WARN_DAYS, MAX_TLS_WARN_DAYS, "d"),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


class TraefikProxyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Traefik."""

    VERSION = 1
    MINOR_VERSION = 3

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> TraefikProxyOptionsFlow:
        """Return the options flow; saving changed options reloads the entry."""
        return TraefikProxyOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Set up an entry: URL, TLS verification and authentication."""
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL]
            auth_type = user_input.get(CONF_AUTH_TYPE, AuthMode.none.value)
            try:
                _check_url_shape(url)
            except InvalidUrl:
                errors["base"] = "invalid_url"
            else:
                # One entry per Traefik (host:port); a configured one is not
                # contacted again.
                await self.async_set_unique_id(url_unique_id(url))
                self._abort_if_unique_id_configured()
                credentials, errors = _collect_credentials(user_input, auth_type)
            if not errors:
                data = _entry_data(url, user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL), auth_type, credentials)
                errors = await _async_probe_errors(self.hass, data)
            if not errors:
                return self.async_create_entry(title=url_host(url) or url, data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start reauthentication after Traefik rejected the stored credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for new credentials for the stored URL, probe them and store them.

        Every credential of the chosen auth type is required. The entry data
        is replaced as a whole, so credentials of another auth type are
        dropped; the entry reloads and the flow aborts with Home Assistant's
        central ``reauth_successful`` reason.
        """
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        stored_auth = _stored_auth_type(entry.data)

        if user_input is not None:
            auth_type = user_input.get(CONF_AUTH_TYPE, stored_auth)
            credentials, errors = _collect_credentials(user_input, auth_type)
            if not errors:
                new_data = _entry_data(
                    entry.data[CONF_URL],
                    entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
                    auth_type,
                    credentials,
                )
                errors = await _async_probe_errors(
                    self.hass, {**new_data, CONF_VERIFY_SSL: effective_verify_ssl(entry)}
                )
            if not errors:
                return self.async_update_reload_and_abort(entry, data=new_data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(_auth_fields(stored_auth)),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change URL, TLS verification and credentials of an existing entry.

        The URL and the effective TLS verification are pre-filled; secrets are
        not. With an unchanged auth type an empty or omitted credential keeps
        the stored one (for the probe and storage); a changed auth type needs
        its own credentials, and none removes them. A host:port owned by
        another entry aborts with ``already_configured`` before any request.
        The unique_id follows the new host:port; a title that is the old host
        or the default name follows the new host, a user-chosen title stays.
        The new TLS verification value is also written to the options, so it
        stays the effective one.
        """
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        stored_auth = _stored_auth_type(entry.data)

        if user_input is not None:
            url = user_input[CONF_URL]
            try:
                _check_url_shape(url)
            except InvalidUrl:
                errors["base"] = "invalid_url"
            else:
                # Checked before the probe so a Traefik owned by another
                # entry is never contacted.
                unique_id = url_unique_id(url)
                for other in self._async_current_entries(include_ignore=False):
                    if other.entry_id != entry.entry_id and other.unique_id == unique_id:
                        return self.async_abort(reason="already_configured")
                auth_type = user_input.get(CONF_AUTH_TYPE, stored_auth)
                stored = entry.data if auth_type == entry.data.get(CONF_AUTH_TYPE) else None
                credentials, errors = _collect_credentials(user_input, auth_type, stored)
            if not errors:
                verify_ssl = user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
                new_data = _entry_data(url, verify_ssl, auth_type, credentials)
                errors = await _async_probe_errors(self.hass, new_data)
            if not errors:
                title = entry.title
                if title in {url_host(entry.data.get(CONF_URL, "")), DEFAULT_NAME}:
                    title = url_host(url) or title
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=unique_id,
                    title=title,
                    data=new_data,
                    options={**entry.options, CONF_VERIFY_SSL: verify_ssl},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_URL, default=entry.data.get(CONF_URL, "")): _URL_SELECTOR,
                vol.Optional(CONF_VERIFY_SSL, default=effective_verify_ssl(entry)): BooleanSelector(),
                **_auth_fields(stored_auth),
            }
        )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
        )
