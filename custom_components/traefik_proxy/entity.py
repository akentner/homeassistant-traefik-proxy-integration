"""Base entities and device topology of the Traefik integration."""

from __future__ import annotations

from abc import abstractmethod
from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar, Final
from urllib.parse import urlsplit

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .cert_coordinator import CertCoordinator
from .const import CONF_URL, DEFAULT_NAME, DOMAIN
from .coordinator import TraefikProxyCoordinator
from .data import TraefikProxyConfigEntry
from .entity_manager import KindSpec
from .models import TraefikSnapshot


class TraefikDevice(StrEnum):
    """Devices of one config entry; the values are the device translation keys."""

    MAIN = "main"
    ROUTERS = "routers"
    SERVICES = "services"
    CERTIFICATES = "certificates"


def device_identifier(entry_id: str, device: TraefikDevice) -> tuple[str, str]:
    """Return the device registry identifier of ``device`` for an entry."""
    if device is TraefikDevice.MAIN:
        return (DOMAIN, entry_id)
    return (DOMAIN, f"{entry_id}_{device}")


def traefik_device_info(entry: TraefikProxyConfigEntry, device: TraefikDevice) -> DeviceInfo:
    """Return the DeviceInfo that attaches an entity to ``device``.

    Identifiers only: the devices are registered (names, entry type, link to
    the main device) before the platforms are set up.
    """
    return DeviceInfo(identifiers={device_identifier(entry.entry_id, device)})


def entry_host(entry: TraefikProxyConfigEntry) -> str:
    """Return the host of the entry URL for device names, or the entry title without one."""
    try:
        host = urlsplit(entry.data[CONF_URL]).hostname
    except ValueError:
        host = None
    return host or entry.title


def dashboard_url(url: str) -> str | None:
    """Return the Traefik dashboard URL for an API base URL.

    Keeps scheme, host, port and path prefix; drops userinfo, query and
    fragment. None for non-http(s) URLs, URLs without a host and invalid ports.
    """
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    host = parts.hostname
    if parts.scheme not in ("http", "https") or not host:
        return None
    if ":" in host:
        host = f"[{host}]"
    netloc = host if port is None else f"{host}:{port}"
    return f"{parts.scheme}://{netloc}{parts.path.rstrip('/')}/dashboard/"


@callback
def async_setup_devices(hass: HomeAssistant, entry: TraefikProxyConfigEntry) -> dr.DeviceEntry:
    """Register the main device and its sub-devices; return the main device.

    Runs before the platforms are set up, so entities attach to named devices.
    Sub-devices are linked to the main device through the registry, the one
    linking API available on every supported Home Assistant version.
    """
    device_registry = dr.async_get(hass)
    placeholders = {"host": entry_host(entry)}
    main = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={device_identifier(entry.entry_id, TraefikDevice.MAIN)},
        translation_key=TraefikDevice.MAIN.value,
        translation_placeholders=placeholders,
        manufacturer="Traefik",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url=dashboard_url(entry.data[CONF_URL]),
        sw_version=entry.runtime_data.coordinator.data.version.version,
    )
    for device in (TraefikDevice.ROUTERS, TraefikDevice.SERVICES, TraefikDevice.CERTIFICATES):
        sub = device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={device_identifier(entry.entry_id, device)},
            translation_key=device.value,
            translation_placeholders=placeholders,
            manufacturer="Traefik",
            entry_type=DeviceEntryType.SERVICE,
        )
        if sub.via_device_id != main.id:
            device_registry.async_update_device(sub.id, via_device_id=main.id)
    return main


_UNWRITTEN: Final = object()


class _TraefikEntityBase[CoordinatorT: DataUpdateCoordinator[Any]](CoordinatorEntity[CoordinatorT]):
    """Common base: device attachment and write-on-change.

    A coordinator update writes the state only when availability or the
    entity's state token changed since the last write.
    """

    _attr_has_entity_name = True
    _traefik_device: ClassVar[TraefikDevice] = TraefikDevice.MAIN

    def __init__(self, coordinator: CoordinatorT, entry: TraefikProxyConfigEntry, unique_id: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = unique_id
        self._attr_device_info = traefik_device_info(entry, self._traefik_device)
        self._written_token: object = _UNWRITTEN

    def _state_token(self) -> object:
        """Return a value that changes whenever the written state would change."""
        return (self.state, self.extra_state_attributes)

    def _write_token(self) -> object:
        return (self.available, self._state_token())

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._written_token = self._write_token()

    @callback
    def _handle_coordinator_update(self) -> None:
        token = self._write_token()
        if token == self._written_token:
            return
        self._written_token = token
        self.async_write_ha_state()


class TraefikEntity(_TraefikEntityBase[TraefikProxyCoordinator]):
    """Entity that listens to the main Traefik coordinator."""

    def __init__(self, entry: TraefikProxyConfigEntry, unique_id: str) -> None:
        super().__init__(entry.runtime_data.coordinator, entry, unique_id)


class TraefikItemEntity[ModelT](TraefikEntity):
    """Entity for one Traefik item; holds only the item key.

    The model is looked up in the latest snapshot on every update. An item
    absent from the snapshot is missing since the time the entry's entity
    manager recorded.
    """

    _spec: ClassVar[KindSpec]

    def __init__(self, entry: TraefikProxyConfigEntry, key: str) -> None:
        super().__init__(entry, self._spec.unique_id(entry.entry_id, key))
        self._key = key
        self._attr_name = key

    @abstractmethod
    def _model(self) -> ModelT | None:
        """Return the current model of the item, or None when it is missing."""

    def _missing_since(self) -> datetime | None:
        return self._entry.runtime_data.entity_manager.missing_since(self._spec, self._key)

    def _state_token(self) -> object:
        return (self._model(), self._missing_since())

    def _missing_attributes(self) -> dict[str, Any]:
        since = self._missing_since()
        return {"missing_since": since.isoformat() if since is not None else None}


# Per-category model labels for the multi-device model (CONTEXT.md D-01).
# Each Traefik category becomes its own HA device; the Traefik integration is
# the manufacturer and the category is the model.
_CATEGORY_TO_MODEL: Final[dict[str, str]] = {
    "http_routers": "HTTP Routers",
    "http_routers_tls": "HTTP Routers TLS",  # Phase 3 — TLS probe results live on their own device
    "http_services": "HTTP Services",
    "http_entrypoints": "HTTP Entrypoints",
    "overview": "Overview",
    "diagnostics": "Diagnostics",
}


def _category_to_model(category: str) -> str:
    """Return the human-readable model label for a category.

    Falls back to the raw category string so a typo in a new platform's
    category still produces a usable device model rather than crashing.
    """
    return _CATEGORY_TO_MODEL.get(category, category)


class _TraefikProxyBaseEntity[CoordinatorT: DataUpdateCoordinator[Any]](CoordinatorEntity[CoordinatorT]):
    """Common base for all Traefik entities (binary_sensor, sensor, button).

    Generic over the coordinator the entity listens to: most entities follow
    the main coordinator (``TraefikProxyEntity``), the TLS certificate
    entities follow the cert coordinator (``TraefikProxyCertEntity``).

    Each entity registers under a per-category HA device — the integration
    identifier is ``(DOMAIN, f"{entry.entry_id}_{category}")``. The legacy
    Phase 1 single-device identifier ``(DOMAIN, entry.entry_id)`` is gone;
    existing HA installations will see a new device row in the registry on
    first restart after this migration (device-registry IDs are opaque so
    this is unavoidable when the shape of the identifier changes). See
    SUMMARY 02-01 for the regression-risk note.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CoordinatorT,
        entry: TraefikProxyConfigEntry,
        category: str,
        *,
        description_key: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._category = category
        # Back-compat alias: the Phase 1 binary_sensor code reads
        # ``self._router_name`` for the router label. New platforms can ignore
        # the attribute — it's a thin alias for ``description_key`` (or "" when
        # the entity is single-instance, e.g. aggregates on the Overview device).
        self._router_name = description_key or ""

    @property
    def device_info(self) -> DeviceInfo:
        url_host = self._url_host()
        model = _category_to_model(self._category)
        name = f"{url_host} Traefik Proxy \u2014 {model}" if url_host else f"{DEFAULT_NAME} \u2014 {model}"
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_{self._category}")},
            manufacturer="Traefik",
            model=model,
            name=name,
            sw_version=self._sw_version(),
            entry_type=DeviceEntryType.SERVICE,
        )

    def _url_host(self) -> str | None:
        from urllib.parse import urlparse

        url = self._entry.data.get("url", "")
        try:
            return str(urlparse(url).hostname)
        except Exception:
            return None

    def _sw_version(self) -> str | None:
        # Always the main snapshot, also for entities bound to the cert coordinator.
        # Cert-entity unit tests build entities on mocked entries without a snapshot.
        data = self._entry.runtime_data.coordinator.data
        return data.version.version if isinstance(data, TraefikSnapshot) else None


class TraefikProxyEntity(_TraefikProxyBaseEntity[TraefikProxyCoordinator]):
    """Entity that listens to the main Traefik coordinator."""

    def __init__(
        self,
        entry: TraefikProxyConfigEntry,
        category: str,
        *,
        description_key: str | None = None,
    ) -> None:
        super().__init__(entry.runtime_data.coordinator, entry, category, description_key=description_key)


class TraefikProxyCertEntity(_TraefikProxyBaseEntity[CertCoordinator]):
    """Entity that listens to the cert coordinator (TLS certificate state).

    Cert cycles and threshold changes notify only the cert coordinator's
    listeners, so the certificate entities subscribe there and not to the
    main coordinator (which skips unchanged snapshots).
    """

    def __init__(
        self,
        entry: TraefikProxyConfigEntry,
        coordinator: CertCoordinator,
        category: str,
        *,
        description_key: str,
    ) -> None:
        super().__init__(coordinator, entry, category, description_key=description_key)
