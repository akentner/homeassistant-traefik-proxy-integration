"""Base entities and device topology of the Traefik integration."""

from __future__ import annotations

import logging
from abc import abstractmethod
from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar, Final
from urllib.parse import urlsplit

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .cert_coordinator import CertCoordinator, HostCertState
from .const import CONF_URL, DOMAIN
from .coordinator import TraefikProxyCoordinator
from .data import TraefikProxyConfigEntry
from .entity_manager import KindSpec

_LOGGER = logging.getLogger(__name__)


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
def _async_remove_device_if_unreferenced(
    device_registry: dr.DeviceRegistry, entity_registry: er.EntityRegistry, device: dr.DeviceEntry
) -> bool:
    """Remove ``device`` unless a registry entry still references it; return whether it was removed.

    Removing a device removes this entry's entities on it and unlinks every
    other entity, so a device any registry entry references (disabled entries
    and other integrations' entries included) is kept.
    """
    if er.async_entries_for_device(entity_registry, device.id, include_disabled_entities=True):
        _LOGGER.debug("Keeping Traefik device %s: entities still reference it", device.id)
        return False
    device_registry.async_remove_device(device.id)
    return True


@callback
def async_setup_devices(
    hass: HomeAssistant, entry: TraefikProxyConfigEntry, *, per_item: bool = True
) -> dr.DeviceEntry:
    """Register the main device and its sub-devices; return the main device.

    Runs before the platforms are set up, so entities attach to named devices.
    Sub-devices are linked to the main device through the registry, the one
    linking API available on every supported Home Assistant version. With
    ``per_item`` off the Routers and Services sub-devices are not registered,
    and existing ones of this entry are removed unless a registry entry still
    references them.
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
    per_item_devices = (TraefikDevice.ROUTERS, TraefikDevice.SERVICES)
    if not per_item:
        entity_registry = er.async_get(hass)
        unwanted = {device_identifier(entry.entry_id, device) for device in per_item_devices}
        for device_entry in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
            if device_entry.identifiers & unwanted:
                _async_remove_device_if_unreferenced(device_registry, entity_registry, device_entry)
    wanted = (*per_item_devices, TraefikDevice.CERTIFICATES) if per_item else (TraefikDevice.CERTIFICATES,)
    for device in wanted:
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


# Identifier suffixes of the 0.3.0 per-category devices, replaced by the
# main device and its sub-devices.
LEGACY_DEVICE_SUFFIXES: Final = (
    "http_routers",
    "http_routers_tls",
    "http_services",
    "http_entrypoints",
    "overview",
    "diagnostics",
)


@callback
def async_legacy_devices(hass: HomeAssistant, entry: TraefikProxyConfigEntry) -> list[dr.DeviceEntry]:
    """Return this entry's 0.3.0 per-category devices.

    Only devices of this entry are considered, and only those carrying exactly
    one legacy identifier and none of the current device identifiers.
    """
    legacy = {(DOMAIN, f"{entry.entry_id}_{suffix}") for suffix in LEGACY_DEVICE_SUFFIXES}
    current = {device_identifier(entry.entry_id, device) for device in TraefikDevice}
    return [
        device
        for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
        if len(device.identifiers & legacy) == 1 and not device.identifiers & current
    ]


@callback
def async_remove_legacy_devices(hass: HomeAssistant, entry: TraefikProxyConfigEntry) -> None:
    """Remove this entry's 0.3.0 per-category devices that no entity uses any more.

    Runs after the platforms are set up, so every entity they add has been
    re-pointed to its new device. A legacy device is removed only while no
    registry entry references it; otherwise it is kept.
    """
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    for device in async_legacy_devices(hass, entry):
        _async_remove_device_if_unreferenced(device_registry, entity_registry, device)


@callback
def async_track_sw_version(hass: HomeAssistant, entry: TraefikProxyConfigEntry, main_device_id: str) -> CALLBACK_TYPE:
    """Keep the main device's ``sw_version`` equal to the Traefik version.

    One device registry update per version change; snapshot changes that keep
    the version update nothing. Returns the unsubscribe callable.
    """
    coordinator = entry.runtime_data.coordinator
    device_registry = dr.async_get(hass)
    last_version = coordinator.data.version.version

    @callback
    def _async_check_version() -> None:
        nonlocal last_version
        version = coordinator.data.version.version
        if version == last_version:
            return
        last_version = version
        device_registry.async_update_device(main_device_id, sw_version=version)

    return coordinator.async_add_listener(_async_check_version)


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


def cert_hosts(coordinator: CertCoordinator) -> set[str]:
    """Return the lowercase hosts of the cert data, with and without a certificate."""
    return {host.lower() for host in coordinator.data or {}}


class TraefikCertCoordinatorEntity(_TraefikEntityBase[CertCoordinator]):
    """Entity that listens to the cert coordinator; on the main device by default.

    Cert cycles, threshold changes and day-boundary fires notify only the
    cert coordinator's listeners. Available while the last cert cycle
    succeeded.
    """

    def __init__(self, entry: TraefikProxyConfigEntry, unique_id: str) -> None:
        super().__init__(entry.runtime_data.cert_coordinator, entry, unique_id)


class TraefikCertEntity(TraefikCertCoordinatorEntity):
    """Entity for the certificate of one TLS host; holds only the host.

    On the Certificates device. Available while the last cert cycle
    succeeded and the host is in the cert data, also when its probe failed;
    a host absent from the cert data (missing) is unavailable. Days until
    expiry are computed from the clock at read time.
    ``homeassistant.update_entity`` requests a cert refresh.
    """

    _traefik_device = TraefikDevice.CERTIFICATES
    _spec: ClassVar[KindSpec]

    def __init__(self, entry: TraefikProxyConfigEntry, host: str) -> None:
        host = host.lower()
        super().__init__(entry, self._spec.unique_id(entry.entry_id, host))
        self._host = host
        self._attr_translation_placeholders = {"host": host}

    def _state(self) -> HostCertState | None:
        """Return the host's state in the latest cert data, or None when the host is absent."""
        return (self.coordinator.data or {}).get(self._host)

    def _days_left(self) -> int | None:
        """Return the signed days until the certificate expires, or None without one."""
        state = self._state()
        return None if state is None else state.days_left(dt_util.utcnow())

    @property
    def available(self) -> bool:
        return super().available and self._state() is not None

    def _state_token(self) -> object:
        return (self._state(), self._days_left())
