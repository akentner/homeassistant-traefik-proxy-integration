"""Binary sensor entities for the Traefik integration.

The platform provides the router, service and middleware problem aggregates on
the main device and one certificate-expiring binary sensor per probed TLS host.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription

try:
    from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
except ImportError:  # HA releases before 2026.10 define it in the package
    from homeassistant.components.binary_sensor import BinarySensorDeviceClass  # type: ignore[attr-defined]
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

from .const import MAX_PROBLEM_NAMES, UID_MIDDLEWARES_PROBLEM, UID_ROUTERS_PROBLEM, UID_SERVICES_PROBLEM
from .entity import TraefikEntity, TraefikProxyCertEntity
from .models import TraefikSnapshot
from .sensor import _cert_cache_availability
from .tls import CertError, CertInfo, is_error

if TYPE_CHECKING:
    from .cert_coordinator import CertCoordinator
    from .data import TraefikProxyConfigEntry

_LOGGER = logging.getLogger(__name__)

# Entities read the coordinator snapshot; no per-entity polling.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class TraefikProblemEntityDescription(BinarySensorEntityDescription):
    """A problem aggregate: unique_id suffix and the snapshot problem names it reads."""

    unique_id_suffix: str
    problems_fn: Callable[[TraefikSnapshot], tuple[str, ...]]


PROBLEM_SENSORS: tuple[TraefikProblemEntityDescription, ...] = (
    TraefikProblemEntityDescription(
        key="routers_problem",
        translation_key="routers_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        unique_id_suffix=UID_ROUTERS_PROBLEM,
        problems_fn=lambda snapshot: snapshot.router_problems,
    ),
    TraefikProblemEntityDescription(
        key="services_problem",
        translation_key="services_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        unique_id_suffix=UID_SERVICES_PROBLEM,
        problems_fn=lambda snapshot: snapshot.service_problems,
    ),
    TraefikProblemEntityDescription(
        key="middlewares_problem",
        translation_key="middlewares_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        unique_id_suffix=UID_MIDDLEWARES_PROBLEM,
        problems_fn=lambda snapshot: snapshot.middleware_problems,
    ),
)


async def async_setup_entry(
    hass: Any,
    entry: TraefikProxyConfigEntry,
    async_add_entities: Any,
) -> None:
    """Set up the Traefik binary sensors of a config entry.

    Adds the three problem aggregates (one each per entry, enabled by default;
    they fall to off when nothing is wrong) and one certificate-expiring
    binary sensor per host in the certificate cache.
    """
    async_add_entities([TraefikProblemBinarySensor(entry, description) for description in PROBLEM_SENSORS])

    # --- Cert expiry binary sensors (TLS-02) ---
    # The cert coordinator lives next to the main coordinator on the entry's
    # runtime data; setup always creates it before forwarding platforms.
    cert_coordinator: CertCoordinator = entry.runtime_data.cert_coordinator
    registry = er.async_get(hass)

    def _create_pending_cert_binary_sensor_entities() -> None:
        """Materialise one expiring binary sensor per cached cert row.

        BLOCKER #2 fix — entity creation must fire on EVERY cert cycle
        (not just on initial setup) so hosts discovered after the
        cold-start empty-cache fallback in plan 03-01 Task 3 step
        3d(iii) still get their entities registered. Mirrors the
        timestamp-sensor closure in ``sensor.py`` so the two
        platforms stay in sync — when the cert coordinator discovers
        a new host, BOTH the timestamp sensor AND the expiry binary
        sensor register on the same cycle.

        v0.2.1 fix: removed the ``if host in existing: continue`` check.
        ``async_add_entities`` deduplicates by ``unique_id`` — the
        check was redundant AND broke the HA-restart restore path
        (see ``sensor.py`` closure for the full explanation).
        """
        cache = cert_coordinator.data
        if not isinstance(cache, dict) or not cache:
            return
        new_entities: list[TraefikProxyCertExpiryBinarySensor] = [
            TraefikProxyCertExpiryBinarySensor(entry, cert_coordinator, host.lower(), cache_value)
            for host, cache_value in cache.items()
        ]
        if new_entities:
            async_add_entities(new_entities)

    def _remove_stale_cert_expiring() -> None:
        """Drop expiry-binary-sensor entities whose host is no longer probed.

        WARNING #1 fix — this listener is registered ONLY in
        ``binary_sensor.py``; the matching ``_remove_stale_cert_hosts``
        for the ``tls_cert_`` prefix lives in ``sensor.py``. No
        duplicate registration. Gate on
        ``cert_coordinator.last_update_success`` (Phase 2 D-18 pattern
        replicated verbatim) so a transient cert-cycle failure cannot
        mass-delete every TLS host entity.
        """
        if not cert_coordinator.last_update_success:
            return
        cache = cert_coordinator.data
        current: set[str] = {h.lower() for h in cache} if isinstance(cache, dict) else set()
        prefix = f"{entry.entry_id}_tls_expiring_"
        for reg_entry in list(registry.entities.values()):
            unique_id = reg_entry.unique_id or ""
            if not unique_id.startswith(prefix):
                continue
            host = unique_id.removeprefix(prefix)
            if host and host not in current:
                _LOGGER.debug("Removing stale cert expiring entity: %s", reg_entry.entity_id)
                registry.async_remove(reg_entry.entity_id)

    def _on_cert_update() -> None:
        """Combined cert-cycle listener — creation + cleanup in one tick.

        Single ``async_add_listener`` registration drives both the
        BLOCKER #2 entity-creation closure (for newly-discovered
        hosts) AND the WARNING #1 stale-cleanup callback. Folding
        both into one function keeps the listener registration count
        to a minimum and ensures both paths fire on every cert cycle
        (every 6h).
        """
        _create_pending_cert_binary_sensor_entities()
        _remove_stale_cert_expiring()

    # Materialise any entities for hosts already in the cache at setup time.
    _create_pending_cert_binary_sensor_entities()
    # Register the combined listener for future cycles.
    entry.async_on_unload(cert_coordinator.async_add_listener(_on_cert_update))


class TraefikProblemBinarySensor(TraefikEntity, BinarySensorEntity):
    """On while the snapshot lists at least one problem item of the description's kind.

    Attributes: ``problems`` (sorted names, at most ``MAX_PROBLEM_NAMES``) and
    ``problem_count`` (all of them).
    """

    entity_description: TraefikProblemEntityDescription

    def __init__(self, entry: TraefikProxyConfigEntry, description: TraefikProblemEntityDescription) -> None:
        super().__init__(entry, f"{entry.entry_id}_{description.unique_id_suffix}")
        self.entity_description = description

    def _problems(self) -> tuple[str, ...]:
        return self.entity_description.problems_fn(self.coordinator.data)

    @property
    def is_on(self) -> bool:
        return bool(self._problems())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        problems = self._problems()
        return {"problems": list(problems[:MAX_PROBLEM_NAMES]), "problem_count": len(problems)}


class TraefikProxyCertExpiryBinarySensor(TraefikProxyCertEntity, BinarySensorEntity):
    """One ``PROBLEM`` binary sensor per TLS-probed hostname (TLS-02).

    State is ``True`` when ``days_until_expiry <= threshold_days``
    (CONTEXT.md D-03 — signed-int semantics so already-expired certs
    surface as ``True``). The threshold is read live from
    ``cert_coordinator.threshold_days`` so a user Options change
    (``tls_warn_days``) flips the binary state within ~1s without
    requiring a re-handshake — the Options listener calls
    ``cert_coordinator.async_set_threshold`` which calls
    ``async_update_listeners`` (plan 03-01 Task 3 step 3e).

    CONTEXT.md D-03 explicitly diverges from Phase 2's M-12 default:
    ``_attr_entity_registry_enabled_default = True`` so the cert-expiry
    alarm is visible by default on a brand-new install. The user can
    still opt out per-entity via Settings → Devices & Services. The
    cert entity lives on the new "HTTP Routers TLS" device — the
    always-on default does NOT enable entities on any other device.

    ``available`` DELEGATES to the shared
    ``sensor.py._cert_cache_availability`` helper (SUGGESTION #1 fix —
    single source of truth for cache availability across both
    platforms; no per-platform drift). The cert-expiring entity and
    the paired ``TraefikProxyCertTimestampSensor`` for the same host will
    therefore flip to unavailable together, never out of sync.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    # D-03: ALWAYS ON by default — cert expiry is a security-impacting
    # alarm. See class docstring for the divergence rationale from M-12.
    _attr_entity_registry_enabled_default = True
    # ``mdi:lock-alert`` matches the cert-security semantic; distinct
    # from the timestamp sensor's ``mdi:certificate`` icon — the
    # binary_sensor is the alarm, the timestamp is informational.
    _attr_icon = "mdi:lock-alert"

    def __init__(
        self,
        entry: TraefikProxyConfigEntry,
        coordinator: CertCoordinator,
        host: str,
        info: CertInfo | CertError | None,
    ) -> None:
        # Defensive lowercase normalisation (the cert coordinator
        # already lowercases, but a cache row populated from a test
        # harness could carry mixed casing — see threat model).
        host = host.lower()
        # Distinct ``description_key`` from the timestamp sensor
        # (``<host>_expiring`` vs ``<host>``) so the binary_sensor's
        # name in the States panel is uniquely identifiable.
        super().__init__(entry, coordinator, category="http_routers_tls", description_key=f"{host}_expiring")
        self._host = host
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_tls_expiring_{host}"
        # Explicit entity_id prefix per CONTEXT.md D-09 — the
        # ``traefik_<slug>_expiring`` shape is the user-facing identity.
        self.entity_id = f"binary_sensor.traefik_{slugify(host)}_expiring"
        self._attr_name = f"{host} certificate expiring"

    @property
    def is_on(self) -> bool | None:
        """``True`` when ``days_until_expiry <= threshold_days`` (signed).

        CONTEXT.md D-03 — negative ``days_until_expiry`` (already-expired
        certs) is ``<= threshold`` for any reasonable threshold so the
        entity surfaces the breach as ``True``. ``None`` (unknown) is
        returned when the cache row is absent or a ``CertError`` — the
        ``available`` property drives the unavailable/unknown distinction.
        """
        cache = self._coordinator.data.get(self._host) if isinstance(self._coordinator.data, dict) else None
        if cache is None or is_error(cache):
            return None
        # Type narrowing: ``is_error`` returned False so ``cache`` is a
        # ``CertInfo`` dataclass.
        info = cast("CertInfo", cache)
        return info.days_until_expiry <= self._coordinator.threshold_days

    @property
    def available(self) -> bool:
        """Delegate to the shared ``sensor.py._cert_cache_availability`` helper.

        SUGGESTION #1 fix — both platforms consult this same function
        so the timestamp sensor and the paired expiry binary sensor can
        never disagree about whether a host's cache row is usable.
        """
        return _cert_cache_availability(self._coordinator, self._host)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Always-on diagnostic attrs (CONTEXT.md D-04 / D-08).

        ``days_until_expiry``, ``threshold_days``, ``not_after``,
        ``san_mismatch``, ``host``, ``fetched_at`` are always present
        (with ``None`` on the error path) so dashboards consistently
        show the comparison surface even when the cert probe failed.
        """
        cache = self._coordinator.data.get(self._host) if isinstance(self._coordinator.data, dict) else None
        threshold = self._coordinator.get_threshold()
        if cache is None or is_error(cache):
            # Error path — surface the cached error verbatim.
            err: CertError | None = cast("CertError", cache) if cache is not None and is_error(cache) else None
            return {
                "days_until_expiry": None,
                "threshold_days": threshold,
                "not_after": None,
                "last_error": err.get("error") if err else None,
                "san_mismatch": None,
                "host": self._host,
                "fetched_at": None,
            }
        # CertInfo path — full attribute surface. Cast documents the
        # post-is_error narrowing for mypy --strict.
        info = cast("CertInfo", cache)
        return {
            "days_until_expiry": info.days_until_expiry,
            "threshold_days": threshold,
            "not_after": info.not_after.isoformat(),
            "last_error": None,
            "san_mismatch": info.san_mismatch,
            "host": self._host,
            "fetched_at": info.fetched_at.isoformat(),
        }
