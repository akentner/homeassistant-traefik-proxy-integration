"""Binary sensor entities for the Traefik integration.

The platform provides the router, service and middleware problem aggregates on
the main device and one certificate-expiring binary sensor per host of the cert
data on the Certificates device.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription

try:
    from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
except ImportError:  # HA releases before 2026.10 define it in the package
    from homeassistant.components.binary_sensor import BinarySensorDeviceClass  # type: ignore[attr-defined]
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import MAX_PROBLEM_NAMES, UID_MIDDLEWARES_PROBLEM, UID_ROUTERS_PROBLEM, UID_SERVICES_PROBLEM
from .entity import TraefikCertEntity, TraefikEntity, cert_hosts
from .entity_manager import CERT_EXPIRING
from .models import TraefikSnapshot

if TYPE_CHECKING:
    from .data import TraefikProxyConfigEntry

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
    hass: HomeAssistant,
    entry: TraefikProxyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Traefik binary sensors of a config entry.

    Adds the three problem aggregates (one each per entry, enabled by default;
    they fall to off when nothing is wrong) and registers the
    certificate-expiring kind with the entity manager: one binary sensor per
    host of the cert data, independent of the per-item option.
    """
    async_add_entities([TraefikProblemBinarySensor(entry, description) for description in PROBLEM_SENSORS])

    cert_coordinator = entry.runtime_data.cert_coordinator
    entry.runtime_data.entity_manager.async_add_kind(
        CERT_EXPIRING,
        coordinator=cert_coordinator,
        keys=lambda: cert_hosts(cert_coordinator),
        factory=lambda host: TraefikCertExpiringBinarySensor(entry, host),
        async_add_entities=async_add_entities,
    )


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


class TraefikCertExpiringBinarySensor(TraefikCertEntity, BinarySensorEntity):
    """Problem binary sensor: on while one TLS host's certificate expires within the threshold.

    On when ``days_until_expiry <= threshold_days`` (signed, so an expired
    certificate is on); the threshold is read live from the cert coordinator,
    so an options change re-evaluates without a new probe. Enabled by
    default: certificate expiry is a security alarm.
    """

    _spec = CERT_EXPIRING
    _attr_translation_key = "certificate_expiring"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_registry_enabled_default = True

    @property
    def is_on(self) -> bool | None:
        """Return whether the certificate expires within the threshold, or None without a certificate."""
        info = self._info()
        return None if info is None else info.days_until_expiry <= self.coordinator.threshold_days

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        threshold = self.coordinator.threshold_days
        info = self._info()
        if info is None:
            err = self._error()
            return {
                "days_until_expiry": None,
                "threshold_days": threshold,
                "not_after": None,
                "last_error": err.get("error") if err else None,
                "san_mismatch": None,
                "host": self._host,
                "fetched_at": None,
            }
        return {
            "days_until_expiry": info.days_until_expiry,
            "threshold_days": threshold,
            "not_after": info.not_after.isoformat(),
            "last_error": None,
            "san_mismatch": info.san_mismatch,
            "host": self._host,
            "fetched_at": info.fetched_at.isoformat(),
        }

    def _state_token(self) -> object:
        return (self._row(), self.coordinator.threshold_days)
