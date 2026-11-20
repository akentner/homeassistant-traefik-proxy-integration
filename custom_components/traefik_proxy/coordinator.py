"""DataUpdateCoordinator for the Traefik integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlsplit

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError, HomeAssistantError
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .api import (
    Auth,
    AuthMode,
    TraefikProxyApiClient,
    TraefikProxyApiError,
    TraefikProxyAuthError,
    TraefikProxyInvalidUrlError,
    TraefikProxyRedirectError,
)
from .const import (
    CONF_AUTH_TYPE,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)
from .models import Entrypoint, TraefikSnapshot, TraefikVersion

if TYPE_CHECKING:
    from .data import TraefikProxyConfigEntry

_LOGGER = logging.getLogger(__name__)

# Port of a URL without an explicit one, by scheme.
_DEFAULT_PORTS = {"http": 80, "https": 443}

# How often a healthy coordinator re-reads /api/version to detect a Traefik
# restart or upgrade (/api/rawdata carries no start date).
VERSION_RECHECK_INTERVAL = timedelta(hours=1)

# How often a client on the paginated list endpoints retries /api/rawdata.
RAWDATA_PROBE_INTERVAL = timedelta(hours=1)


def effective_verify_ssl(entry: ConfigEntry[Any]) -> bool:
    """Return the verify_ssl value the user set last.

    Precedence: ``entry.options`` -> ``entry.data`` -> ``DEFAULT_VERIFY_SSL``.
    The options flow writes options only; the reconfigure flow writes both.
    """
    if CONF_VERIFY_SSL in entry.options:
        return bool(entry.options[CONF_VERIFY_SSL])
    return bool(entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL))


def auth_from_entry_data(data: Mapping[str, Any]) -> Auth:
    """Map entry data to the client's Auth value; the single mapping point.

    Entry data names its auth type (``none`` when absent) plus the credentials
    of that type: username and password for basic, a token for bearer. Raises
    ``ValueError`` for an unknown auth type or credentials ``Auth`` rejects.
    """
    return Auth(
        mode=AuthMode(data.get(CONF_AUTH_TYPE, AuthMode.none)),
        username=data.get(CONF_USERNAME),
        password=data.get(CONF_PASSWORD),
        token=data.get(CONF_TOKEN),
    )


def split_url_userinfo(url: str) -> tuple[str, str | None, str | None]:
    """Return ``url`` without userinfo plus the percent-decoded username and password.

    Only the userinfo is cut from the URL; scheme, host spelling, IPv6
    brackets, port, path, query and fragment stay as given. An absent or
    empty username or password is ``None``. Raises ``ValueError`` for a URL
    ``urlsplit`` cannot parse.
    """
    netloc = urlsplit(url).netloc
    if "@" not in netloc:
        return url, None, None
    userinfo, _, hostport = netloc.rpartition("@")
    username, _, password = userinfo.partition(":")
    return url.replace(netloc, hostport, 1), unquote(username) or None, unquote(password) or None


def url_host(url: str) -> str | None:
    """Return the lowercased host of ``url``, or None when it has none or cannot be parsed."""
    try:
        return urlsplit(url).hostname
    except ValueError:
        return None


def url_unique_id(url: str) -> str:
    """Return the config entry unique_id of a Traefik API URL: ``host:port``.

    The host is lowercased, an IPv6 address is wrapped in brackets and a
    missing port is the scheme's default (80 for http, 443 for https). Raises
    ``ValueError`` for a URL without a usable host or port.
    """
    parts = urlsplit(url)
    host = parts.hostname
    port = parts.port if parts.port is not None else _DEFAULT_PORTS.get(parts.scheme)
    if not host or port is None:
        raise ValueError("URL has no usable host and port")
    if ":" in host:
        host = f"[{host}]"
    return f"{host}:{port}"


def build_api_client(hass: HomeAssistant, entry: ConfigEntry[Any]) -> TraefikProxyApiClient:
    """Build the runtime API client from the entry and the shared HA session.

    Stored credentials ``Auth`` rejects can never be sent, so retrying is
    pointless: the entry asks for new credentials through reauth instead.
    """
    try:
        auth = auth_from_entry_data(entry.data)
    except ValueError:
        # The ValueError names a field, never its value; the chain is dropped
        # anyway so no credential detail reaches a traceback.
        raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="invalid_credentials") from None
    return TraefikProxyApiClient(
        session=aiohttp_client.async_get_clientsession(hass),
        base_url=entry.data[CONF_URL],
        auth=auth,
        verify_ssl=effective_verify_ssl(entry),
    )


def _translated_update_error(err: TraefikProxyApiError) -> HomeAssistantError:
    """Map a client error to the translated Home Assistant exception to raise.

    Placeholders carry only the request path, the HTTP status and the
    client's non-secret detail, never ``str(err)``. Subclasses are checked
    before their bases: an invalid URL and a redirect are also connection
    errors. A stored URL aiohttp refuses can never work, so it stops the
    setup instead of retrying.
    """
    if isinstance(err, TraefikProxyInvalidUrlError):
        return ConfigEntryError(translation_domain=DOMAIN, translation_key="invalid_url")
    if isinstance(err, TraefikProxyAuthError):
        return ConfigEntryAuthFailed(
            translation_domain=DOMAIN,
            translation_key="auth_failed",
            translation_placeholders={"path": err.path},
        )
    if isinstance(err, TraefikProxyRedirectError):
        return UpdateFailed(
            translation_domain=DOMAIN,
            translation_key="redirect",
            translation_placeholders={"path": err.path, "status": str(err.status)},
        )
    return UpdateFailed(
        translation_domain=DOMAIN,
        translation_key="api_error",
        translation_placeholders={"path": err.path, "detail": err.detail},
    )


def _logged_cause(err: TraefikProxyApiError) -> TraefikProxyApiError | None:
    """Return the cause to chain to the translated exception of ``err``.

    Home Assistant logs a ``ConfigEntryError`` from setup with its full
    traceback at ERROR. Below an invalid-URL error sits aiohttp's error,
    whose text can be the URL including userinfo, so that chain is dropped.
    """
    return None if isinstance(err, TraefikProxyInvalidUrlError) else err


def _interval_elapsed(since: datetime | None, interval: timedelta) -> bool:
    """Return whether ``interval`` has passed since ``since`` (False when unset)."""
    return since is not None and dt_util.utcnow() - since >= interval


class TraefikProxyCoordinator(DataUpdateCoordinator[TraefikSnapshot]):
    """Single polling point for Traefik state.

    The coordinator does not own an API client. It reads the entry's one
    client from ``entry.runtime_data`` (see :class:`TraefikRuntimeData`), so
    the runtime data must be assigned before the first refresh.

    Version and entrypoints are fetched during setup; every cycle then
    fetches routers, services and middlewares and publishes them as one
    immutable :class:`TraefikSnapshot`. The version is re-read at most once
    per ``VERSION_RECHECK_INTERVAL`` and on the first cycle after a failed
    one; the entrypoints are re-read only when the version or start date
    changed (Traefik restarted or was upgraded). While the client is
    paginated, /api/rawdata is retried once per ``RAWDATA_PROBE_INTERVAL``
    on a clock of its own, so failed cycles cannot postpone it. Listeners
    are only notified when the snapshot differs from the previous one.
    """

    config_entry: TraefikProxyConfigEntry

    def __init__(self, hass: HomeAssistant, entry: TraefikProxyConfigEntry) -> None:
        """Construct coordinator from a config entry's data + options."""
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=entry.title or "Traefik",
            update_interval=timedelta(seconds=scan_interval),
            always_update=False,
        )
        self._version: TraefikVersion | None = None
        self._version_checked_at: datetime | None = None
        # Last tick of the rawdata probe grid. It moves in rawdata mode as
        # well, where arming the probe is a no-op; a cycle that fails before
        # the arming does not move it.
        self._probe_clock: datetime | None = None
        self._entrypoints: dict[str, Entrypoint] = {}

    @property
    def client(self) -> TraefikProxyApiClient:
        """Return the entry's API client (owned by the runtime data)."""
        return self.config_entry.runtime_data.client

    async def _async_setup(self) -> None:
        """Fetch the Traefik version and entrypoints once per setup."""
        try:
            self._version = await self.client.async_get_version()
            self._version_checked_at = self._probe_clock = dt_util.utcnow()
            self._entrypoints = await self.client.async_get_entrypoints()
        except TraefikProxyApiError as err:
            raise _translated_update_error(err) from _logged_cause(err)

    def _version_due(self) -> bool:
        """Return whether this cycle re-reads /api/version.

        ``last_update_success`` still describes the previous cycle here:
        Home Assistant updates it only after ``_async_update_data`` returns.
        """
        if self._version is None or self._version_checked_at is None or not self.last_update_success:
            return True
        return _interval_elapsed(self._version_checked_at, VERSION_RECHECK_INTERVAL)

    async def _async_refresh_version(self) -> None:
        """Re-read the version; re-read the entrypoints when Traefik restarted.

        The stored version is replaced only after a needed entrypoint fetch
        succeeded, so a failure there is retried on the next cycle.
        """
        try:
            version = await self.client.async_get_version()
            previous = self._version
            if previous is None or (version.version, version.start_date) != (
                previous.version,
                previous.start_date,
            ):
                self._entrypoints = await self.client.async_get_entrypoints()
        except TraefikProxyApiError as err:
            raise _translated_update_error(err) from _logged_cause(err)
        self._version = version
        self._version_checked_at = dt_util.utcnow()

    async def _async_update_data(self) -> TraefikSnapshot:
        """Fetch the HTTP state and build the snapshot for this cycle."""
        if self._version_due():
            await self._async_refresh_version()
        if _interval_elapsed(self._probe_clock, RAWDATA_PROBE_INTERVAL):
            # The probe has its own clock: a post-failure version re-check
            # neither arms it nor postpones it, so probes stay at least
            # RAWDATA_PROBE_INTERVAL apart and recurring failures cannot
            # starve them. In rawdata mode the arming is a no-op.
            self.client.request_rawdata_probe()
            self._probe_clock = dt_util.utcnow()
        try:
            state = await self.client.async_get_state()
        except TraefikProxyApiError as err:
            raise _translated_update_error(err) from _logged_cause(err)
        if self._version is None:
            raise UpdateFailed(translation_domain=DOMAIN, translation_key="version_unavailable")
        return TraefikSnapshot.build(version=self._version, entrypoints=self._entrypoints, state=state)
