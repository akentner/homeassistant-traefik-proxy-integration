"""Sensor entities for the Traefik integration.

Entity count per config entry (after `async_setup_entry` returns):
- 1 `TraefikProxyEntrypointSensor` per Traefik entrypoint (HTTP Entrypoints device)
- 1 `TraefikProxyServiceSensor` per Traefik HTTP service (HTTP Services device;
  Traefik-internal ``@internal`` services are not part of the snapshot)
- 1 each of `TraefikProxyRoutersCountSensor`, `TraefikProxyServicesCountSensor`,
  `TraefikProxyMiddlewaresCountSensor` on the Overview device
- 1 `TraefikProxyCertTimestampSensor` per probed TLS hostname
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, cast

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

from .entity import TraefikProxyCertEntity, TraefikProxyEntity
from .models import Entrypoint, Service, StatusCounts
from .tls import CertError, CertInfo, is_error

if TYPE_CHECKING:
    from .cert_coordinator import CertCoordinator
    from .coordinator import TraefikProxyCoordinator
    from .data import TraefikProxyConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: Any,
    entry: TraefikProxyConfigEntry,
    async_add_entities: Any,
) -> None:
    """Set up Traefik sensor entities for a config entry.

    Entities are created from the coordinator's current snapshot and read
    their state from the latest snapshot on every access.
    """
    coordinator: TraefikProxyCoordinator = entry.runtime_data.coordinator
    snapshot = coordinator.data

    entrypoint_entities = [TraefikProxyEntrypointSensor(entry, coordinator, ep) for ep in snapshot.entrypoints.values()]
    service_entities = [TraefikProxyServiceSensor(entry, coordinator, svc) for svc in snapshot.services.values()]

    # Aggregate counters on the Overview device read the snapshot counts.
    aggregate_entities = [
        TraefikProxyRoutersCountSensor(entry),
        TraefikProxyServicesCountSensor(entry),
        TraefikProxyMiddlewaresCountSensor(entry),
    ]

    async_add_entities(entrypoint_entities + service_entities + aggregate_entities)

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

    # Stale entity cleanup: entrypoints and services that disappear from the
    # snapshot are removed from the entity registry on the next refresh cycle.
    # Aggregate counters on the Overview device are never deleted — their
    # unique_id prefix is ``_overview_`` and is skipped below.
    registry = er.async_get(hass)

    def _remove_stale_entrypoints() -> None:
        if not coordinator.last_update_success:
            return
        current = set(coordinator.data.entrypoints)
        prefix = f"{entry.entry_id}_http_entrypoint_"
        for reg_entry in list(registry.entities.values()):
            unique_id = reg_entry.unique_id or ""
            if not unique_id.startswith(prefix):
                continue
            ep_name = unique_id.removeprefix(prefix)
            if ep_name and ep_name not in current:
                _LOGGER.debug("Removing stale entrypoint entity: %s", reg_entry.entity_id)
                registry.async_remove(reg_entry.entity_id)

    def _remove_stale_services() -> None:
        if not coordinator.last_update_success:
            return
        current = set(coordinator.data.services)
        prefix = f"{entry.entry_id}_http_service_"
        for reg_entry in list(registry.entities.values()):
            unique_id = reg_entry.unique_id or ""
            if not unique_id.startswith(prefix):
                continue
            svc_name = unique_id.removeprefix(prefix)
            if svc_name and svc_name not in current:
                _LOGGER.debug("Removing stale service entity: %s", reg_entry.entity_id)
                registry.async_remove(reg_entry.entity_id)

    entry.async_on_unload(coordinator.async_add_listener(_remove_stale_entrypoints))
    entry.async_on_unload(coordinator.async_add_listener(_remove_stale_services))


class TraefikProxyEntrypointSensor(TraefikProxyEntity, SensorEntity):
    """One sensor per Traefik entrypoint.

    State = the entrypoint's listening address (e.g. ``":443"``); attributes
    expose the raw ``name`` and the ``transport`` protocol (``tcp`` or
    ``udp``) so dashboards can group by protocol. The model is looked up by
    name in the latest snapshot on every read.
    """

    def __init__(
        self,
        entry: TraefikProxyConfigEntry,
        coordinator: TraefikProxyCoordinator,
        entrypoint: Entrypoint,
    ) -> None:
        entrypoint_name = entrypoint.name
        super().__init__(entry, category="http_entrypoints", description_key=entrypoint_name)
        self._item_name = entrypoint_name
        self._initial_entrypoint = entrypoint
        self._attr_unique_id = f"{entry.entry_id}_http_entrypoint_{entrypoint_name}"
        self.entity_id = f"sensor.traefik_http_entrypoint_{slugify(entrypoint_name)}"
        self._attr_name = entrypoint_name

    @property
    def _entrypoint(self) -> Entrypoint:
        """Return the current model, or the last known one when it is not in the snapshot."""
        return self.coordinator.data.entrypoints.get(self._item_name, self._initial_entrypoint)

    @property
    def native_value(self) -> str:
        """Return the listening address (e.g., ``":443"``).

        Kept raw including the leading ``:`` — this matches Traefik's own
        display format and avoids ambiguity when the bind host is included
        (``"0.0.0.0:443"`` vs ``":443"``).
        """
        return self._entrypoint.address

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        ep = self._entrypoint
        return {
            "name": ep.name,
            "address": ep.address,
            "transport": ep.protocol,
            # ``entrypoint_name`` mirrors ``name`` for consistency with the
            # ``router_name`` alias on TraefikProxyRouterBinarySensor.
            "entrypoint_name": ep.name,
        }

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success


class TraefikProxyServiceSensor(TraefikProxyEntity, SensorEntity):
    """One sensor per Traefik HTTP service.

    State = the service status (``enabled``, ``warning``, ``error`` or
    ``disabled``). Attributes expose the service ``type`` and the backend
    server counts from Traefik's health status (``server_count`` = all
    servers, ``servers_up`` = servers reported ``UP``). The model is looked
    up by name in the latest snapshot on every read.
    """

    def __init__(
        self,
        entry: TraefikProxyConfigEntry,
        coordinator: TraefikProxyCoordinator,
        service: Service,
    ) -> None:
        service_name = service.name
        super().__init__(entry, category="http_services", description_key=service_name)
        self._item_name = service_name
        self._initial_service = service
        self._attr_unique_id = f"{entry.entry_id}_http_service_{service_name}"
        self.entity_id = f"sensor.traefik_http_service_{slugify(service_name)}"
        self._attr_name = service_name

    @property
    def _service(self) -> Service:
        """Return the current model, or the last known one when it is not in the snapshot."""
        return self.coordinator.data.services.get(self._item_name, self._initial_service)

    @property
    def native_value(self) -> str:
        """Return the service status."""
        return str(self._service.status)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        svc = self._service
        return {
            "name": svc.name,
            "status": str(svc.status),
            "type": svc.type,
            "server_count": svc.servers_total,
            "servers_up": svc.servers_up,
            "service_name": svc.name,
        }

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success


class _TraefikProxyAggregateCountSensor(TraefikProxyEntity, SensorEntity):
    """Shared base for the three Overview device aggregate counters.

    State and attributes are properties that read the status counts the
    coordinator precomputes once per snapshot, so the displayed value
    always reflects the latest Traefik roster.

    ``state_class=MEASUREMENT`` so HA can graph trends over time — users
    may want to chart how many routers / services / middlewares are
    configured across deploys.

    Subclasses implement ``_counts`` (which snapshot counts to show) and
    set ``_HAS_HTTP_COUNT`` when the ``http_count`` attribute applies.
    """

    _attr_state_class = SensorStateClass.MEASUREMENT

    _HAS_HTTP_COUNT: ClassVar[bool] = True

    def __init__(
        self,
        entry: TraefikProxyConfigEntry,
        *,
        unique_id: str,
        entity_id: str,
        name: str,
    ) -> None:
        super().__init__(entry, category="overview", description_key=unique_id)
        self._attr_unique_id = unique_id
        self.entity_id = entity_id
        self._attr_name = name

    def _counts(self) -> StatusCounts:
        """Return the status counts this sensor shows."""
        raise NotImplementedError

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def native_value(self) -> int:
        """Total number of items of this kind in the latest snapshot."""
        return self._counts().total

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Per-status counts, their breakdown and the success percentage.

        ``success_pct`` = success / (success + warning + error) * 100,
        excluding disabled items (turned off on purpose, not a quality
        signal), clamped to [0.0, 100.0] and 100.0 when no such item exists.
        """
        counts = self._counts()
        breakdown = {
            "success": counts.enabled,
            "warning": counts.warning,
            "error": counts.error,
            "disabled": counts.disabled,
        }
        attrs: dict[str, Any] = {"filtered_count": counts.total}
        attrs.update({f"{bucket}_count": count for bucket, count in breakdown.items()})
        attrs["status_breakdown"] = breakdown
        non_disabled = counts.enabled + counts.warning + counts.error
        pct = counts.enabled / non_disabled * 100.0 if non_disabled > 0 else 100.0
        attrs["success_pct"] = max(0.0, min(100.0, pct))
        if self._HAS_HTTP_COUNT:
            attrs["http_count"] = counts.total
        return attrs


class TraefikProxyRoutersCountSensor(_TraefikProxyAggregateCountSensor):
    """Number of HTTP routers in the latest snapshot."""

    def __init__(self, entry: TraefikProxyConfigEntry) -> None:
        super().__init__(
            entry,
            unique_id=f"{entry.entry_id}_overview_routers_count",
            entity_id="sensor.traefik_routers",
            name="Routers",
        )

    def _counts(self) -> StatusCounts:
        return self.coordinator.data.router_counts


class TraefikProxyServicesCountSensor(_TraefikProxyAggregateCountSensor):
    """Number of HTTP services in the latest snapshot."""

    def __init__(self, entry: TraefikProxyConfigEntry) -> None:
        super().__init__(
            entry,
            unique_id=f"{entry.entry_id}_overview_services_count",
            entity_id="sensor.traefik_services",
            name="Services",
        )

    def _counts(self) -> StatusCounts:
        return self.coordinator.data.service_counts


class TraefikProxyMiddlewaresCountSensor(_TraefikProxyAggregateCountSensor):
    """Number of HTTP middlewares in the latest snapshot."""

    _HAS_HTTP_COUNT = False

    def __init__(self, entry: TraefikProxyConfigEntry) -> None:
        super().__init__(
            entry,
            unique_id=f"{entry.entry_id}_overview_middlewares_count",
            entity_id="sensor.traefik_middlewares",
            name="Middlewares",
        )

    def _counts(self) -> StatusCounts:
        return self.coordinator.data.middleware_counts


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
