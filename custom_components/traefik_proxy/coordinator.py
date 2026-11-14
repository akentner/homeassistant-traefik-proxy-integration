"""DataUpdateCoordinator for the Traefik integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import TraefikProxyApiClient, TraefikProxyApiError, TraefikProxyAuthError
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


def effective_verify_ssl(entry: ConfigEntry[Any]) -> bool:
    """Return the verify_ssl value the user set last.

    Precedence: ``entry.options`` -> ``entry.data`` -> ``DEFAULT_VERIFY_SSL``.
    The options flow writes options only; the reconfigure flow writes both.
    """
    if CONF_VERIFY_SSL in entry.options:
        return bool(entry.options[CONF_VERIFY_SSL])
    return bool(entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL))


def build_api_client(hass: HomeAssistant, entry: ConfigEntry[Any]) -> TraefikProxyApiClient:
    """Build the runtime API client from the entry and the shared HA session."""
    return TraefikProxyApiClient(
        session=aiohttp_client.async_get_clientsession(hass),
        base_url=entry.data[CONF_URL],
        api_key=entry.data[CONF_API_KEY],
        verify_ssl=effective_verify_ssl(entry),
    )


class TraefikProxyCoordinator(DataUpdateCoordinator[TraefikSnapshot]):
    """Single polling point for Traefik state.

    The coordinator does not own an API client. It reads the entry's one
    client from ``entry.runtime_data`` (see :class:`TraefikRuntimeData`), so
    the runtime data must be assigned before the first refresh.

    Version and entrypoints are fetched once during setup; every cycle then
    fetches routers, services and middlewares and publishes them as one
    immutable :class:`TraefikSnapshot`. Listeners are only notified when the
    snapshot differs from the previous one.
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
        self._entrypoints: dict[str, Entrypoint] = {}

    @property
    def client(self) -> TraefikProxyApiClient:
        """Return the entry's API client (owned by the runtime data)."""
        return self.config_entry.runtime_data.client

    async def _async_setup(self) -> None:
        """Fetch the Traefik version and entrypoints once per setup."""
        try:
            self._version = await self.client.async_get_version()
            self._entrypoints = await self.client.async_get_entrypoints()
        except TraefikProxyAuthError as err:
            raise ConfigEntryAuthFailed from err
        except TraefikProxyApiError as err:
            raise UpdateFailed(str(err)) from err

    async def _async_update_data(self) -> TraefikSnapshot:
        """Fetch the HTTP state and build the snapshot for this cycle."""
        try:
            state = await self.client.async_get_state()
        except TraefikProxyAuthError as err:
            raise ConfigEntryAuthFailed from err
        except TraefikProxyApiError as err:
            raise UpdateFailed(str(err)) from err
        if self._version is None:
            raise UpdateFailed("Traefik version not available")
        return TraefikSnapshot.build(version=self._version, entrypoints=self._entrypoints, state=state)
