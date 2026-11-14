"""Lifecycle of the per-item entities of one config entry.

Platforms register a "kind" (routers, services, ...) with the entry's
``TraefikEntityManager``: a key source, an entity factory and the platform's
``async_add_entities``. From then on the manager is the only code that adds
or removes per-item entities. On every successful coordinator cycle it

- adds an entity for every key that is new (each key is added once per load);
- marks known keys that vanished from the snapshot as missing, with the time
  they were first seen missing;
- clears the missing mark of keys that came back (the entity was never
  removed, so its entity_id, name and area are unchanged).

A key that stays missing for ``MISSING_GRACE_PERIOD`` (wall clock) loses its
registry entry. The missing-since times are kept in a per-entry Store, so the
grace period survives reloads and restarts, and a timer of its own removes
expired keys even when the snapshot never changes. Registry entries of the
entry whose key is absent from the first snapshot are adopted as missing
entities at setup, so orphans expire the same way.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import DOMAIN, MISSING_CHECK_INTERVAL, MISSING_GRACE_PERIOD

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

MISSING_STORE_VERSION = 1

# Store data: {kind name: {key: missing since, ISO-8601 UTC}}.
type MissingData = dict[str, dict[str, str]]


def missing_store_key(entry_id: str) -> str:
    """Return the storage key of the missing-since map of one config entry."""
    return f"{DOMAIN}.missing.{entry_id}"


def _missing_store(hass: HomeAssistant, entry_id: str) -> Store[MissingData]:
    return Store[MissingData](hass, MISSING_STORE_VERSION, missing_store_key(entry_id))


async def async_remove_missing_store(hass: HomeAssistant, entry_id: str) -> None:
    """Delete the missing-since map of a removed config entry."""
    await _missing_store(hass, entry_id).async_remove()


def _parse_missing(raw: object, now: datetime) -> dict[str, dict[str, datetime]]:
    """Parse stored missing-since data; drop malformed, unparsable and naive values.

    A time in the future (clock moved back) counts as now, so it can never
    postpone a removal without bound.
    """
    if not isinstance(raw, dict):
        return {}
    result: dict[str, dict[str, datetime]] = {}
    for name, keys in raw.items():
        if not isinstance(name, str) or not isinstance(keys, dict):
            continue
        parsed: dict[str, datetime] = {}
        for key, value in keys.items():
            since = dt_util.parse_datetime(value) if isinstance(value, str) else None
            if not isinstance(key, str) or since is None or since.tzinfo is None:
                continue
            parsed[key] = min(dt_util.as_utc(since), now)
        if parsed:
            result[name] = parsed
    return result


def _serialize_missing(missing: dict[str, dict[str, datetime]]) -> MissingData:
    return {
        name: {key: since.isoformat() for key, since in sorted(keys.items())}
        for name, keys in sorted(missing.items())
        if keys
    }


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
    """Add, mark missing, re-bind and expire the per-item entities of one config entry.

    Every state change runs in an event-loop callback without an await, so
    platform setups and coordinator notifications never interleave inside
    one update. Store writes run as config-entry tasks, which entry unload
    awaits.
    """

    def __init__(self, hass: HomeAssistant, entry: TraefikProxyConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._kinds: dict[str, _Kind] = {}
        self._store: Store[MissingData] | None = None
        # Stored missing-since times of kinds that are not registered yet.
        self._stored: dict[str, dict[str, datetime]] = {}
        # (domain, unique_id) of the entry's registry entries at load time.
        self._registered: list[tuple[str, str]] = []
        self._saved: MissingData = {}

    async def async_load(self) -> None:
        """Load the stored missing-since times, read the entry's registry entries and start the deadline timer.

        Must run before any platform registers a kind.
        """
        store = _missing_store(self._hass, self._entry.entry_id)
        self._store = store
        self._stored = _parse_missing(await store.async_load(), dt_util.utcnow())
        self._saved = _serialize_missing(self._stored)
        registry = er.async_get(self._hass)
        self._registered = [
            (reg_entry.domain, reg_entry.unique_id)
            for reg_entry in er.async_entries_for_config_entry(registry, self._entry.entry_id)
        ]
        self._entry.async_on_unload(
            async_track_time_interval(
                self._hass,
                self._async_check_deadlines,
                MISSING_CHECK_INTERVAL,
                name="traefik_proxy missing entity check",
                cancel_on_shutdown=True,
            )
        )

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

        Registry entries of this kind whose key is absent from the current
        keys are adopted as missing entities, missing since their stored time
        (or since now when none is stored); an entry whose grace period
        already ran out is removed instead. Stored times of keys that are
        present again or no longer registered are dropped.

        The kind listener is registered before any entity exists, so on every
        coordinator notification it runs before the entities' own listeners
        and they already see the updated missing marks.
        """
        kind = _Kind(spec, coordinator, keys, factory, async_add_entities)
        self._kinds[spec.name] = kind
        self._entry.async_on_unload(coordinator.async_add_listener(partial(self._async_kind_updated, spec.name)))

        present = set(keys())
        stored = self._stored.pop(spec.name, {})
        entry_id = self._entry.entry_id
        orphans = {
            key
            for domain, unique_id in self._registered
            if domain == spec.domain and (key := spec.key_of(entry_id, unique_id)) is not None
        } - present
        now = dt_util.utcnow()
        for key in sorted(orphans):
            since = stored.get(key, now)
            if now - since >= MISSING_GRACE_PERIOD:
                self._async_remove_registry_entry(spec, key)
            else:
                kind.missing[key] = since

        initial = sorted(present | kind.missing.keys())
        kind.known.update(initial)
        async_add_entities([factory(key) for key in initial])
        _LOGGER.debug("Added %d %s entities (%d missing)", len(initial), spec.name, len(kind.missing))
        self._async_schedule_save()

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

        if vanished or returned:
            self._async_schedule_save()

    @callback
    def _async_check_deadlines(self, _now: datetime) -> None:
        """Remove the registry entries of keys missing for at least the grace period."""
        now = dt_util.utcnow()
        removed = False
        for kind in self._kinds.values():
            expired = sorted(key for key, since in kind.missing.items() if now - since >= MISSING_GRACE_PERIOD)
            for key in expired:
                self._async_remove_registry_entry(kind.spec, key)
                del kind.missing[key]
                kind.known.discard(key)
                removed = True
        if removed:
            self._async_schedule_save()

    @callback
    def _async_remove_registry_entry(self, spec: KindSpec, key: str) -> None:
        """Remove the registry entry of ``key``; HA then removes its entity."""
        registry = er.async_get(self._hass)
        entity_id = registry.async_get_entity_id(spec.domain, DOMAIN, spec.unique_id(self._entry.entry_id, key))
        if entity_id is None:
            return
        _LOGGER.debug("Removing %s, missing for longer than %s", entity_id, MISSING_GRACE_PERIOD)
        registry.async_remove(entity_id)

    @callback
    def _async_schedule_save(self) -> None:
        """Persist the missing-since times when they differ from the last write."""
        if self._store is None:
            return
        data = _serialize_missing(
            {**self._stored, **{name: kind.missing for name, kind in self._kinds.items()}},
        )
        if data == self._saved:
            return
        self._saved = data
        self._entry.async_create_task(self._hass, self._store.async_save(data), "traefik_proxy missing-since save")
