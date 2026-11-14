"""Typed runtime data stored on the Traefik config entry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

if TYPE_CHECKING:
    from .api import TraefikProxyApiClient
    from .cert_coordinator import CertCoordinator
    from .coordinator import TraefikProxyCoordinator
    from .entity_manager import TraefikEntityManager


@dataclass
class TraefikRuntimeData:
    """Objects owned by one loaded Traefik config entry.

    ``client`` is the single API client of the entry: the coordinator reads it
    from here, so replacing it (options change) reaches every caller at once.
    The dataclass is mutable on purpose for exactly that replacement.
    ``entity_manager`` owns the lifecycle of the per-item entities.
    """

    client: TraefikProxyApiClient
    coordinator: TraefikProxyCoordinator
    cert_coordinator: CertCoordinator
    entity_manager: TraefikEntityManager


type TraefikProxyConfigEntry = ConfigEntry[TraefikRuntimeData]
