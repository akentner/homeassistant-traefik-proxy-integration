"""Sensor entities for the Traefik integration.

Entity count per config entry (after `async_setup_entry` returns):
- 1 `TraefikRouterSensor` per Traefik HTTP router (Routers device), managed by
  the entry's entity manager
- 1 `TraefikServiceSensor` per Traefik HTTP service (Services device), managed
  by the entity manager; Traefik-internal ``@internal`` services are not part
  of the snapshot
- 1 `TraefikEntrypointSensor` per Traefik entrypoint (main device, diagnostic,
  disabled by default), managed by the entity manager
- 1 `TraefikSnapshotSensor` per `SNAPSHOT_SENSORS` description on the main
  device: router/service/middleware counts, Traefik version, start time and
  healthy router ratio (all diagnostic; the ratio is disabled by default)
- 1 `TraefikProxyCertTimestampSensor` per probed TLS hostname
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import slugify

from .const import ITEM_STATE_OPTIONS, STATE_MISSING
from .entity import TraefikDevice, TraefikEntity, TraefikItemEntity, TraefikProxyCertEntity
from .entity_manager import ENTRYPOINTS, ROUTERS, SERVICES
from .models import Entrypoint, Router, Service, StatusCounts, TraefikSnapshot
from .tls import CertError, CertInfo, is_error

if TYPE_CHECKING:
    from .cert_coordinator import CertCoordinator
    from .coordinator import TraefikProxyCoordinator
    from .data import TraefikProxyConfigEntry

_LOGGER = logging.getLogger(__name__)

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

    # --- Cert timestamp sensors (TLS-01) ---
    # The cert coordinator lives next to the main coordinator on the entry's
    # runtime data; setup always creates it before forwarding platforms.
    cert_coordinator: CertCoordinator = entry.runtime_data.cert_coordinator
    registry = er.async_get(hass)

    def _create_pending_cert_sensor_entities() -> None:
        """Materialise one timestamp sensor per cached ``CertInfo`` row.

        BLOCKER #2 fix — entity creation must fire on EVERY cert cycle
        (not just on initial setup) so hosts discovered after the
        cold-start empty-cache fallback in plan 03-01 Task 3 step
        3d(iii) still get their entities registered. The cert cache is
        populated asynchronously, so the first ``async_setup_entry``
        call may see an empty cache (zero entities registered — correct)
        and the next 6h cycle will fill the cache and re-trigger this
        closure to add the missing entities.

        v0.2.1 fix: removed the ``if host in existing: continue`` check
        that skipped already-registered hosts. ``async_add_entities``
        deduplicates by ``unique_id`` itself — for a registered
        entity whose live ``CoordinatorEntity`` instance has been
        garbage-collected (HA restart with restored entities),
        ``async_add_entities`` REPLACES the defunct instance with
        the new one and wires it to the coordinator. The redundant
        check was preventing exactly that re-bind, leaving restored
        entities stuck at ``state="unavailable"`` + ``restored: true``
        until the next 6h cert cycle.
        """
        cache = cert_coordinator.data
        if not isinstance(cache, dict) or not cache:
            return
        new_entities: list[TraefikProxyCertTimestampSensor] = []
        for host, cache_value in cache.items():
            host = host.lower()
            # Only timestamp sensors go on ``CertInfo`` rows. Error
            # hosts get a ``binary_sensor`` only (per D-03 — the
            # timestamp sensor makes no sense without a ``not_after``).
            if is_error(cache_value):
                continue
            # Type narrowing: ``is_error`` returned False so
            # ``cache_value`` is a ``CertInfo`` dataclass.
            info: CertInfo = cache_value  # type: ignore[assignment]
            new_entities.append(TraefikProxyCertTimestampSensor(entry, cert_coordinator, host, info))
        if new_entities:
            async_add_entities(new_entities)

    def _remove_stale_cert_hosts() -> None:
        """Drop timestamp-sensor entities whose host is no longer probed.

        WARNING #1 fix — this listener is registered ONLY in
        ``sensor.py``; the matching ``_remove_stale_cert_expiring``
        for the ``tls_expiring_`` prefix lives in ``binary_sensor.py``.
        No duplicate registration. Gate on
        ``cert_coordinator.last_update_success`` (Phase 2 D-18 pattern
        replicated verbatim) so a transient cert-cycle failure cannot
        mass-delete every TLS host entity.
        """
        if not cert_coordinator.last_update_success:
            return
        cache = cert_coordinator.data
        current: set[str] = {h.lower() for h in cache} if isinstance(cache, dict) else set()
        prefix = f"{entry.entry_id}_tls_cert_"
        for reg_entry in list(registry.entities.values()):
            unique_id = reg_entry.unique_id or ""
            if not unique_id.startswith(prefix):
                continue
            host = unique_id.removeprefix(prefix)
            if host and host not in current:
                _LOGGER.debug("Removing stale cert timestamp entity: %s", reg_entry.entity_id)
                registry.async_remove(reg_entry.entity_id)

    def _cert_update_listener() -> None:
        """Combined cert-cycle listener — creation + cleanup in one tick.

        A single ``async_add_listener`` registration drives both the
        BLOCKER #2 entity-creation closure (for newly-discovered hosts)
        AND the WARNING #1 stale-cleanup callback. Folding both into
        one function keeps the listener registration count to a minimum
        and ensures both paths fire on every cert cycle (every 6h).
        """
        _create_pending_cert_sensor_entities()
        _remove_stale_cert_hosts()

    # Materialise any entities for hosts already in the cache at setup time.
    _create_pending_cert_sensor_entities()
    # Register the combined listener for future cycles.
    entry.async_on_unload(cert_coordinator.async_add_listener(_cert_update_listener))


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


class TraefikProxyCertTimestampSensor(TraefikProxyCertEntity, SensorEntity):
    """One timestamp sensor per TLS-probed hostname (TLS-01).

    Surfaces the leaf cert's ``notAfter`` datetime via HA's standard
    ``SensorDeviceClass.TIMESTAMP`` device class — the timestamp renders
    as a human-readable date in the States panel and is exposed as a
    ``datetime`` to automations so they can compare against
    ``now() + timedelta(days=14)`` without parsing strings.

    The entity reads from the sibling ``CertCoordinator`` cache (NOT the
    main coordinator — Phase 3's sibling coordinator pattern keeps the
    6h TLS-handshake cadence decoupled from the 15s main coordinator).
    Hosts are deduplicated by the cert coordinator's
    ``_collect_hosts_from_main_coordinator`` (union of
    ``tls.domains[].main`` + ``tls.domains[].sans[]`` + ``Host(...)`` rule
    matches); each unique hostname gets exactly one timestamp sensor on
    the new "HTTP Routers TLS" device (CONTEXT.md D-02).

    CONTEXT.md D-04 / D-08: ``days_until_expiry`` is ALWAYS exposed on
    the entity's ``extra_state_attributes`` — even when the cert probe
    failed and the entity is unavailable — so dashboards consistently
    show the countdown attribute. The same field is mirrored on the
    paired ``TraefikProxyCertExpiryBinarySensor`` for the ``is_on`` threshold
    comparison; both entities read from the SAME cache row so they
    never disagree about the underlying cert state.

    The ``san_mismatch`` attribute (spike 006) is surfaced verbatim so
    dashboards can flag a router whose probe hostname is not strictly
    covered by the cert's SAN entries (Traefik may be serving a default
    or wildcard cert — useful diagnostic, not a failure).
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    # TIMESTAMP device class uses state_class=None by convention — HA
    # doesn't accumulate statistics on a future datetime. MEASUREMENT
    # would force every renderer to treat the cert as a gauge.
    _attr_state_class = None
    # ``mdi:certificate`` matches the TLS-certificate semantic of the
    # entity cluster. Distinct from the ``mdi:lock-alert`` used by the
    # paired binary_sensor — the timestamp sensor is informational, the
    # binary_sensor is the alarm.
    _attr_icon = "mdi:certificate"

    def __init__(
        self,
        entry: TraefikProxyConfigEntry,
        coordinator: CertCoordinator,
        host: str,
        info: CertInfo,
    ) -> None:
        # Defensive lowercase normalisation (the cert coordinator
        # already lowercases, but a cache row populated from a test
        # harness could carry mixed casing — see threat model).
        host = host.lower()
        super().__init__(entry, coordinator, category="http_routers_tls", description_key=host)
        self._host = host
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_tls_cert_{host}"
        # Explicit entity_id prefix per CONTEXT.md D-09 — the
        # ``traefik_<slug>_cert`` shape is the user-facing identity.
        self.entity_id = f"sensor.traefik_{slugify(host)}_cert"
        self._attr_name = f"{host} certificate"

    @property
    def native_value(self) -> datetime | None:
        """Return ``not_after`` UTC datetime (or ``None`` when probe failed).

        ``None`` rather than a sentinel so HA renders "unknown" instead
        of a misleading past date — the ``available`` property below
        drives the unavailable/unknown distinction; ``native_value`` is
        the authoritative timestamp render.
        """
        cache = self._coordinator.data.get(self._host) if isinstance(self._coordinator.data, dict) else None
        if cache is None or is_error(cache):
            return None
        # Type narrowing: ``is_error`` returned False so ``cache`` is a
        # ``CertInfo`` dataclass. The cast documents the post-check state
        # for mypy --strict (the ``is_error`` predicate isn't a
        # TypeGuard-aware assignment target here because the dict.get
        # path widened the union).
        info = cast("CertInfo", cache)
        return info.not_after

    @property
    def available(self) -> bool:
        """Delegate to the shared ``_cert_cache_availability`` helper.

        SUGGESTION #1 fix — the helper is the single source of truth for
        cache availability so the timestamp sensor can never show
        "unavailable" while the paired ``TraefikProxyCertExpiryBinarySensor``
        for the same host still shows a stale "ON". Both platforms
        consult this same function; the alternative — a duplicate
        per-platform helper — would inevitably drift out of sync.
        """
        return _cert_cache_availability(self._coordinator, self._host)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Diagnostic attrs (CONTEXT.md D-04 — always present, even on error)."""
        cache = self._coordinator.data.get(self._host) if isinstance(self._coordinator.data, dict) else None
        if cache is None or is_error(cache):
            # Error path: surface the cached error verbatim; ``days_until_expiry``
            # stays None so dashboards consistently see the attribute.
            err: CertError | None = cast("CertError", cache) if cache is not None and is_error(cache) else None
            return {
                "days_until_expiry": None,
                "subject": None,
                "issuer": None,
                "san": None,
                "san_mismatch": None,
                "host": self._host,
                "port": err.get("port") if err else None,
                "fetched_at": None,
                "last_error": err.get("error") if err else None,
            }
        # CertInfo path — full attribute surface. Cast documents the
        # post-is_error narrowing for mypy --strict.
        info = cast("CertInfo", cache)
        san_sorted: tuple[str, ...] = tuple(sorted(info.san))
        return {
            "days_until_expiry": info.days_until_expiry,
            "subject": info.subject,
            "issuer": info.issuer,
            "san": san_sorted,
            "san_mismatch": info.san_mismatch,
            "host": self._host,
            "port": info.port,
            "fetched_at": info.fetched_at.isoformat(),
            "last_error": None,
        }


def _cert_cache_availability(coordinator: CertCoordinator, host: str) -> bool:
    """Single-source-of-truth helper: is the cert cache row for ``host`` usable?

    SUGGESTION #1 fix — this helper is defined in ``sensor.py`` and
    imported by ``binary_sensor.py`` so both platforms consult the
    EXACT same availability semantics. Returns ``False`` when:

    1. The coordinator's last cycle failed (``last_update_success`` is
       ``False``) — the cache is stale and we don't trust it.
    2. The cache is missing/empty (defensive — the brief window before
       the first cycle completes).
    3. The cache row for ``host`` is absent.
    4. The cache row is a ``CertError`` (probe failed) — the cert data
       is not present, the entity should be unavailable so the user
       sees "unavailable" instead of a stale timestamp.

    The paired ``TraefikProxyCertExpiryBinarySensor`` imports this helper
    directly (``from .sensor import _cert_cache_availability``) — NO
    duplicate helper exists in ``binary_sensor.py``.
    """
    if not coordinator.last_update_success:
        return False
    cache = coordinator.data
    if not isinstance(cache, dict):
        return False
    row = cache.get(host)
    if row is None:
        return False
    return not is_error(row)


# Public alias for the shared helper (SUGGESTION #1 — keep the underscore
# form canonical for the per-platform imports, but expose a public name
# for tests / future cross-module callers that prefer the non-prefixed
# import). The two names point at the SAME function object; this is
# deliberately NOT a re-export from ``__all__`` — the alias is for
# consumers that want a non-private name without renaming the
# implementation.
cert_cache_availability = _cert_cache_availability
