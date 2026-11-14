"""Lifecycle of the per-item entities of one config entry.

Platforms register a "kind" (routers, services, ...) with the entry's
``TraefikEntityManager``: a key source, an entity factory and the platform's
``async_add_entities``. From then on the manager is the only code that adds
per-item entities. On every successful coordinator cycle it

- adds an entity for every key that is new (each key is added once per load);
- marks known keys that vanished from the snapshot as missing, with the time
  they were first seen missing;
- clears the missing mark of keys that came back (the entity was never
  removed, so its entity_id, name and area are unchanged).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from .data import TraefikProxyConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class KindSpec:
    """One kind of per-item entity and its unique_id scheme.

    ``name`` identifies the kind, ``domain`` is the entity platform and
    ``prefix`` the unique_id part after ``"<entry_id>_"``.
    """

    name: str
    domain: str
    prefix: str

    def unique_id(self, entry_id: str, key: str) -> str:
        """Return the unique_id of the entity for ``key``."""
        return f"{entry_id}_{self.prefix}{key}"

    def key_of(self, entry_id: str, unique_id: str) -> str | None:
        """Return the key encoded in ``unique_id``, or None when it is not of this kind."""
        head = f"{entry_id}_{self.prefix}"
        if not unique_id.startswith(head):
            return None
        return unique_id[len(head) :] or None


ROUTERS = KindSpec("router", "sensor", "http_router_")
SERVICES = KindSpec("service", "sensor", "http_service_")
ENTRYPOINTS = KindSpec("entrypoint", "sensor", "http_entrypoint_")
CERT_EXPIRY = KindSpec("certificate_expiry", "sensor", "tls_cert_")
CERT_EXPIRING = KindSpec("certificate_expiring", "binary_sensor", "tls_expiring_")


@dataclass(slots=True)
class _Kind:
    """Registration and bookkeeping of one kind."""

    spec: KindSpec
    coordinator: DataUpdateCoordinator[Any]
    keys: Callable[[], Iterable[str]]
    factory: Callable[[str], Entity]
    async_add_entities: AddConfigEntryEntitiesCallback
    known: set[str] = field(default_factory=set)
    missing: dict[str, datetime] = field(default_factory=dict)


class TraefikEntityManager:
    """Add, mark missing and re-bind the per-item entities of one config entry."""

    def __init__(self, hass: HomeAssistant, entry: TraefikProxyConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._kinds: dict[str, _Kind] = {}

    @callback
    def async_add_kind(
        self,
        spec: KindSpec,
        *,
        coordinator: DataUpdateCoordinator[Any],
        keys: Callable[[], Iterable[str]],
        factory: Callable[[str], Entity],
        async_add_entities: AddConfigEntryEntitiesCallback,
    ) -> None:
        """Register a kind and add the entities for its current keys.

        The kind listener is registered before any entity exists, so on every
        coordinator notification it runs before the entities' own listeners
        and they already see the updated missing marks.
        """
        kind = _Kind(spec, coordinator, keys, factory, async_add_entities)
        self._kinds[spec.name] = kind
        self._entry.async_on_unload(coordinator.async_add_listener(partial(self._async_kind_updated, spec.name)))
        initial = sorted(set(keys()))
        kind.known.update(initial)
        async_add_entities([factory(key) for key in initial])
        _LOGGER.debug("Added %d %s entities", len(initial), spec.name)

    @callback
    def missing_since(self, spec: KindSpec, key: str) -> datetime | None:
        """Return when ``key`` was first seen missing, or None while it is present."""
        kind = self._kinds.get(spec.name)
        return kind.missing.get(key) if kind is not None else None

    @callback
    def _async_kind_updated(self, name: str) -> None:
        """Reconcile one kind with the latest coordinator data."""
        kind = self._kinds[name]
        # A failed cycle carries no information about which items exist.
        if not kind.coordinator.last_update_success:
            return
        present = set(kind.keys())

        new = sorted(present - kind.known)
        if new:
            kind.known.update(new)
            kind.async_add_entities([kind.factory(key) for key in new])
            _LOGGER.debug("Added %s entities: %s", name, new)

        vanished = sorted(kind.known - present - kind.missing.keys())
        if vanished:
            now = dt_util.utcnow()
            for key in vanished:
                kind.missing[key] = now
            _LOGGER.debug("Marked %s entities missing: %s", name, vanished)

        returned = sorted(present & kind.missing.keys())
        for key in returned:
            del kind.missing[key]
        if returned:
            _LOGGER.debug("Re-bound %s entities: %s", name, returned)
