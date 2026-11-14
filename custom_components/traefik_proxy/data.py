"""Typed runtime data stored on the Traefik config entry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

if TYPE_CHECKING:
    from .api import TraefikProxyApiClient
    from .cert_coordinator import CertCoordinator
    from .coordinator import TraefikProxyCoordinator


@dataclass
class TraefikRuntimeData:
    """Objects owned by one loaded Traefik config entry.

    ``client`` is the single API client of the entry: the coordinator reads it
    from here, so replacing it (options change) reaches every caller at once.
    The dataclass is mutable on purpose for exactly that replacement.
    """

    client: TraefikProxyApiClient
    coordinator: TraefikProxyCoordinator
    cert_coordinator: CertCoordinator


type TraefikProxyConfigEntry = ConfigEntry[TraefikRuntimeData]
