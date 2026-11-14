"""Refresh button of the Traefik integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .data import TraefikProxyConfigEntry
from .entity import TraefikEntity

# Presses are serialized; the coordinators' request-refresh debouncers absorb bursts.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TraefikProxyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the entry's refresh button."""
    async_add_entities([TraefikRefreshButton(entry)])


class TraefikRefreshButton(TraefikEntity, ButtonEntity):
    """Refresh the Traefik data and the certificates of its own entry."""

    _attr_translation_key = "refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: TraefikProxyConfigEntry) -> None:
        super().__init__(entry, f"{entry.entry_id}_refresh")

    def _state_token(self) -> object:
        # Only a press changes the state; coordinator updates never do.
        return None

    async def async_press(self) -> None:
        """Request a refresh of the entry's main coordinator and cert coordinator."""
        runtime = self._entry.runtime_data
        await runtime.coordinator.async_request_refresh()
        await runtime.cert_coordinator.async_request_refresh()
