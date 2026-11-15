"""Sensor entities for the Traefik integration.

Entity count per config entry (after `async_setup_entry` returns):
- 1 `TraefikRouterSensor` per Traefik HTTP router (Routers device), managed by
  the entry's entity manager; router and service sensors only exist while the
  per-item option is on
- 1 `TraefikServiceSensor` per Traefik HTTP service (Services device), managed
  by the entity manager; Traefik-internal ``@internal`` services are not part
  of the snapshot
- 1 `TraefikEntrypointSensor` per Traefik entrypoint (main device, diagnostic,
  disabled by default), managed by the entity manager
- 1 `TraefikSnapshotSensor` per `SNAPSHOT_SENSORS` description on the main
  device: router/service/middleware counts, Traefik version, start time and
  healthy router ratio (all diagnostic; the ratio is disabled by default)
- 1 `TraefikCertExpirySensor` per host of the cert data (Certificates device),
  managed by the entity manager, also for hosts whose probe failed
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import ITEM_STATE_OPTIONS, STATE_MISSING
from .entity import TraefikCertEntity, TraefikDevice, TraefikEntity, TraefikItemEntity, cert_hosts
from .entity_manager import CERT_EXPIRY, ENTRYPOINTS, ROUTERS, SERVICES, per_item_entities_enabled
from .models import Entrypoint, Router, Service, StatusCounts, TraefikSnapshot

if TYPE_CHECKING:
    from .coordinator import TraefikProxyCoordinator
    from .data import TraefikProxyConfigEntry

# Entities read the coordinator snapshot; no per-entity polling.
PARALLEL_UPDATES = 0


def healthy_ratio(counts: StatusCounts) -> float:
    """Return enabled / (enabled + warning + error) in percent, one decimal.

    Disabled routers are switched off on purpose and do not count; without
    any other router the ratio is 100.0.
    """
    judged = counts.enabled + counts.warning + counts.error
    if judged == 0:
        return 100.0
    return round(counts.enabled / judged * 100, 1)


def _count_attributes(counts: StatusCounts) -> dict[str, Any]:
    return {"enabled": counts.enabled, "warning": counts.warning, "error": counts.error, "disabled": counts.disabled}


@dataclass(frozen=True, kw_only=True)
class TraefikSensorEntityDescription(SensorEntityDescription):
    """A sensor computed from the whole snapshot."""

    unique_id_suffix: str
    value_fn: Callable[[TraefikSnapshot], StateType | datetime]
    attrs_fn: Callable[[TraefikSnapshot], dict[str, Any]] | None = None


SNAPSHOT_SENSORS: tuple[TraefikSensorEntityDescription, ...] = (
    TraefikSensorEntityDescription(
        key="routers_count",
        translation_key="routers_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        unique_id_suffix="overview_routers_count",
        value_fn=lambda snapshot: snapshot.router_counts.total,
        attrs_fn=lambda snapshot: _count_attributes(snapshot.router_counts),
    ),
    TraefikSensorEntityDescription(
        key="services_count",
        translation_key="services_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        unique_id_suffix="overview_services_count",
        value_fn=lambda snapshot: snapshot.service_counts.total,
        attrs_fn=lambda snapshot: _count_attributes(snapshot.service_counts),
    ),
    TraefikSensorEntityDescription(
        key="middlewares_count",
        translation_key="middlewares_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        unique_id_suffix="overview_middlewares_count",
        value_fn=lambda snapshot: snapshot.middleware_counts.total,
        attrs_fn=lambda snapshot: _count_attributes(snapshot.middleware_counts),
    ),
    TraefikSensorEntityDescription(
        key="version",
        translation_key="version",
        entity_category=EntityCategory.DIAGNOSTIC,
        unique_id_suffix="version",
        value_fn=lambda snapshot: snapshot.version.version,
        attrs_fn=lambda snapshot: {"codename": snapshot.version.codename},
    ),
    TraefikSensorEntityDescription(
        key="start_time",
        translation_key="start_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        unique_id_suffix="start_time",
        value_fn=lambda snapshot: snapshot.version.start_date,
    ),
    TraefikSensorEntityDescription(
        key="healthy_ratio",
        translation_key="healthy_ratio",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        unique_id_suffix="healthy_ratio",
        value_fn=lambda snapshot: healthy_ratio(snapshot.router_counts),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TraefikProxyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Traefik sensor entities for a config entry.

    Entities are created from the coordinator's current snapshot and read
    their state from the latest snapshot on every access.
    """
    coordinator: TraefikProxyCoordinator = entry.runtime_data.coordinator
    manager = entry.runtime_data.entity_manager

    if per_item_entities_enabled(entry):
        manager.async_add_kind(
            ROUTERS,
            coordinator=coordinator,
            keys=lambda: coordinator.data.routers,
            factory=lambda key: TraefikRouterSensor(entry, key),
            async_add_entities=async_add_entities,
        )
        manager.async_add_kind(
            SERVICES,
            coordinator=coordinator,
            keys=lambda: coordinator.data.services,
            factory=lambda key: TraefikServiceSensor(entry, key),
            async_add_entities=async_add_entities,
        )
    manager.async_add_kind(
        ENTRYPOINTS,
        coordinator=coordinator,
        keys=lambda: coordinator.data.entrypoints,
        factory=lambda key: TraefikEntrypointSensor(entry, key),
        async_add_entities=async_add_entities,
    )

    async_add_entities([TraefikSnapshotSensor(entry, description) for description in SNAPSHOT_SENSORS])

    # Certificate entities exist for every host of the cert data, independent
    # of the per-item option.
    cert_coordinator = entry.runtime_data.cert_coordinator
    manager.async_add_kind(
        CERT_EXPIRY,
        coordinator=cert_coordinator,
        keys=lambda: cert_hosts(cert_coordinator),
        factory=lambda host: TraefikCertExpirySensor(entry, host),
        async_add_entities=async_add_entities,
    )


class TraefikRouterSensor(TraefikItemEntity[Router], SensorEntity):
    """One ENUM sensor per Traefik HTTP router.

    State = the router status, or ``missing`` while the router is absent
    from the snapshot (attribute ``missing_since``).
    """

    _spec = ROUTERS
    _traefik_device = TraefikDevice.ROUTERS
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = "router"

    def __init__(self, entry: TraefikProxyConfigEntry, key: str) -> None:
        super().__init__(entry, key)
        self._attr_options = list(ITEM_STATE_OPTIONS)

    def _model(self) -> Router | None:
        return self.coordinator.data.routers.get(self._key)

    @property
    def native_value(self) -> str:
        """Return the router status, or ``missing``."""
        router = self._model()
        return STATE_MISSING if router is None else str(router.status)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        router = self._model()
        if router is None:
            return self._missing_attributes()
        return {
            "rule": router.rule,
            "service": router.service,
            "provider": router.provider,
            "entry_points": list(router.entry_points),
            "middlewares": list(router.middlewares),
            "tls": router.tls,
            "errors": list(router.errors),
        }


class TraefikServiceSensor(TraefikItemEntity[Service], SensorEntity):
    """One ENUM sensor per Traefik HTTP service.

    State = the service status, or ``missing`` while the service is absent
    from the snapshot. A DOWN backend server shows in ``servers_up`` and in
    the services problem aggregate; backend URLs are never exposed.
    """

    _spec = SERVICES
    _traefik_device = TraefikDevice.SERVICES
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = "service"

    def __init__(self, entry: TraefikProxyConfigEntry, key: str) -> None:
        super().__init__(entry, key)
        self._attr_options = list(ITEM_STATE_OPTIONS)

    def _model(self) -> Service | None:
        return self.coordinator.data.services.get(self._key)

    @property
    def native_value(self) -> str:
        """Return the service status, or ``missing``."""
        service = self._model()
        return STATE_MISSING if service is None else str(service.status)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        service = self._model()
        if service is None:
            return self._missing_attributes()
        return {
            "type": service.type,
            "provider": service.provider,
            "servers_up": service.servers_up,
            "servers_total": service.servers_total,
            "used_by": list(service.used_by),
            "errors": list(service.errors),
        }


class TraefikEntrypointSensor(TraefikItemEntity[Entrypoint], SensorEntity):
    """One diagnostic sensor per Traefik entrypoint, disabled by default.

    State = the listening address as Traefik reports it (e.g. ``":443"``),
    or ``missing`` while the entrypoint is absent from the snapshot.
    """

    _spec = ENTRYPOINTS
    _attr_translation_key = "entrypoint"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def _model(self) -> Entrypoint | None:
        return self.coordinator.data.entrypoints.get(self._key)

    @property
    def native_value(self) -> str:
        """Return the listening address, or ``missing``."""
        entrypoint = self._model()
        return STATE_MISSING if entrypoint is None else entrypoint.address

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        entrypoint = self._model()
        if entrypoint is None:
            return self._missing_attributes()
        return {"protocol": entrypoint.protocol}


class TraefikSnapshotSensor(TraefikEntity, SensorEntity):
    """A main-device sensor whose value and attributes come from the snapshot."""

    entity_description: TraefikSensorEntityDescription

    def __init__(self, entry: TraefikProxyConfigEntry, description: TraefikSensorEntityDescription) -> None:
        super().__init__(entry, f"{entry.entry_id}_{description.unique_id_suffix}")
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attrs_fn = self.entity_description.attrs_fn
        return None if attrs_fn is None else attrs_fn(self.coordinator.data)


class TraefikCertExpirySensor(TraefikCertEntity, SensorEntity):
    """Timestamp sensor with the ``notAfter`` time of one TLS host's certificate.

    Available while the cert cycle succeeds and the host is in the cert
    data. A failing probe keeps the last known value; before the first
    certificate was read the value is unknown. The attributes are always
    present, with None values without a certificate.
    """

    _spec = CERT_EXPIRY
    _attr_translation_key = "certificate_expiry"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    # A future point in time; no statistics.
    _attr_state_class = None

    @property
    def native_value(self) -> datetime | None:
        """Return the last known certificate's ``notAfter`` (UTC), or None without a certificate."""
        state = self._state()
        if state is None or state.certificate is None:
            return None
        return state.certificate.not_after

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self._state()
        certificate = state.certificate if state is not None else None
        fetched_at = state.fetched_at if state is not None else None
        return {
            "days_until_expiry": self._days_left(),
            "subject": (certificate.common_name or None) if certificate is not None else None,
            "issuer": certificate.issuer_cn if certificate is not None else None,
            "san": tuple(sorted(certificate.sans)) if certificate is not None else None,
            "san_mismatch": state.san_mismatch if state is not None else None,
            "verified": state.verified if state is not None else None,
            "source": state.source.value if state is not None else None,
            "host": self._host,
            "port": state.port if state is not None else None,
            "fetched_at": fetched_at.isoformat() if fetched_at is not None else None,
            "last_error": state.error if state is not None else None,
        }
