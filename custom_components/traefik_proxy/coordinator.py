"""DataUpdateCoordinator for the Traefik integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .api import Auth, AuthMode, TraefikProxyApiClient, TraefikProxyApiError, TraefikProxyAuthError
from .const import (
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VERIFY_SSL,
)
from .models import Entrypoint, TraefikSnapshot, TraefikVersion

if TYPE_CHECKING:
    from .data import TraefikProxyConfigEntry

_LOGGER = logging.getLogger(__name__)

# How often a healthy coordinator re-reads /api/version to detect a Traefik
# restart or upgrade (/api/rawdata carries no start date).
VERSION_RECHECK_INTERVAL = timedelta(hours=1)


def effective_verify_ssl(entry: ConfigEntry[Any]) -> bool:
    """Return the verify_ssl value the user set last.

    Precedence: ``entry.options`` -> ``entry.data`` -> ``DEFAULT_VERIFY_SSL``.
    The options flow writes options only; the reconfigure flow writes both.
    """
    if CONF_VERIFY_SSL in entry.options:
        return bool(entry.options[CONF_VERIFY_SSL])
    return bool(entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL))


def auth_from_entry_data(data: Mapping[str, Any]) -> Auth:
    """Map stored entry data to the client's Auth value.

    Entries store a single optional bearer token: a non-empty token selects
    bearer auth, an empty or missing one selects no auth. Basic auth is not
    reachable from entry data yet.
    """
    token = data.get(CONF_API_KEY)
    if isinstance(token, str) and token:
        return Auth(mode=AuthMode.bearer, token=token)
    return Auth()


def build_api_client(hass: HomeAssistant, entry: ConfigEntry[Any]) -> TraefikProxyApiClient:
    """Build the runtime API client from the entry and the shared HA session."""
    return TraefikProxyApiClient(
        session=aiohttp_client.async_get_clientsession(hass),
        base_url=entry.data[CONF_URL],
        auth=auth_from_entry_data(entry.data),
        verify_ssl=effective_verify_ssl(entry),
    )


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
    paginated, the hourly re-check also retries /api/rawdata once. Listeners
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
        self._entrypoints: dict[str, Entrypoint] = {}

    @property
    def client(self) -> TraefikProxyApiClient:
        """Return the entry's API client (owned by the runtime data)."""
        return self.config_entry.runtime_data.client

    async def _async_setup(self) -> None:
        """Fetch the Traefik version and entrypoints once per setup."""
        try:
            self._version = await self.client.async_get_version()
            self._version_checked_at = dt_util.utcnow()
            self._entrypoints = await self.client.async_get_entrypoints()
        except TraefikProxyAuthError as err:
            raise ConfigEntryAuthFailed from err
        except TraefikProxyApiError as err:
            raise UpdateFailed(str(err)) from err

    def _version_due(self) -> bool:
        """Return whether this cycle re-reads /api/version.

        ``last_update_success`` still describes the previous cycle here:
        Home Assistant updates it only after ``_async_update_data`` returns.
        """
        if self._version is None or self._version_checked_at is None or not self.last_update_success:
            return True
        return self._recheck_interval_elapsed()

    def _recheck_interval_elapsed(self) -> bool:
        """Return whether ``VERSION_RECHECK_INTERVAL`` has passed since the last successful version check."""
        if self._version_checked_at is None:
            return False
        return dt_util.utcnow() - self._version_checked_at >= VERSION_RECHECK_INTERVAL

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
        except TraefikProxyAuthError as err:
            raise ConfigEntryAuthFailed from err
        except TraefikProxyApiError as err:
            raise UpdateFailed(str(err)) from err
        self._version = version
        self._version_checked_at = dt_util.utcnow()

    async def _async_update_data(self) -> TraefikSnapshot:
        """Fetch the HTTP state and build the snapshot for this cycle."""
        if self._version_due():
            # Only the regular hourly re-check arms the rawdata probe; a
            # post-failure re-check inside the interval does not, so probes
            # stay at least VERSION_RECHECK_INTERVAL apart.
            probe_rawdata = self._recheck_interval_elapsed()
            await self._async_refresh_version()
            if probe_rawdata:
                self.client.request_rawdata_probe()
        try:
            state = await self.client.async_get_state()
        except TraefikProxyAuthError as err:
            raise ConfigEntryAuthFailed from err
        except TraefikProxyApiError as err:
            raise UpdateFailed(str(err)) from err
        if self._version is None:
            raise UpdateFailed("Traefik version not available")
        return TraefikSnapshot.build(version=self._version, entrypoints=self._entrypoints, state=state)
