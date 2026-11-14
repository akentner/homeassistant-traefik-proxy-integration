"""DataUpdateCoordinator for the Traefik integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any, TypedDict

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

if TYPE_CHECKING:
    from .data import TraefikProxyConfigEntry

_LOGGER = logging.getLogger(__name__)


class TraefikProxyData(TypedDict, total=False):
    """Shape of the coordinator's `data` attribute (Phase 2, CONTEXT.md D-04).

    All keys are optional at runtime (DataUpdateCoordinator stores a dict via
    its generic). ``total=False`` mirrors the Phase 1 behavior where any
    individual key may be missing transiently. Partial-failure policy lives
    in ``TraefikProxyApiClient.fetch_all`` (CONTEXT.md D-07): on a non-auth error,
    the entire payload is dropped so callers see a stale cycle rather than
    mixed fresh+stale data.

    NOTE: Phase 1 used a PEP-695 ``type TraefikProxyData = dict[str, Any]`` alias.
    The class form (TypedDict) is the canonical Phase 2 type — every
    ``from .coordinator import TraefikProxyData`` continues to resolve to a valid
    type identifier (the TypedDict class itself). The PLAN.md 02-01 snippet
    ``type TraefikProxyData = TraefikProxyData`` is a self-referential alias that ruff
    + mypy both flag as a no-op redefinition; we keep the class form alone
    and surface this in SUMMARY 02-01 as a deviation.
    """

    version: dict[str, Any]
    entrypoints: list[dict[str, Any]]
    http_routers: list[dict[str, Any]]
    http_services: list[dict[str, Any]]
    http_middlewares: list[dict[str, Any]]
    overview: dict[str, Any]


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


class TraefikProxyCoordinator(DataUpdateCoordinator[TraefikProxyData]):
    """Single polling point for Traefik state.

    The coordinator does not own an API client. It reads the entry's one
    client from ``entry.runtime_data`` (see :class:`TraefikRuntimeData`), so
    the runtime data must be assigned before the first refresh.
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
        )

    @property
    def client(self) -> TraefikProxyApiClient:
        """Return the entry's API client (owned by the runtime data)."""
        return self.config_entry.runtime_data.client

    async def _async_update_data(self) -> TraefikProxyData:
        """Fetch the six Traefik endpoints in parallel; map errors per CONTEXT.md D-07.

        Partial-failure policy is enforced inside ``TraefikProxyApiClient.fetch_all``
        (CONTEXT.md D-07): any non-auth error drops the entire payload so
        callers see a stale cycle rather than mixed fresh+stale data. Auth
        errors propagate unchanged so this method only needs to translate
        them to ``ConfigEntryAuthFailed``.
        """
        try:
            result = await self.client.fetch_all()
        except TraefikProxyAuthError as err:
            raise ConfigEntryAuthFailed from err
        except TraefikProxyApiError as err:
            raise UpdateFailed(str(err)) from err
        # ``fetch_all`` returns a plain dict that matches the TypedDict shape;
        # cast at the boundary so the static type stays TraefikProxyData (TypedDict
        # instances ARE dicts at runtime).
        return result  # type: ignore[return-value]
