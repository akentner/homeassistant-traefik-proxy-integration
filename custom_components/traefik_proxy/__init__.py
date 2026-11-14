"""The Traefik integration: config entry migration, setup, unload and removal."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Final

from homeassistant.core import HomeAssistant, split_entity_id
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from .cert_coordinator import CertCoordinator
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_TLS_WARN_DAYS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TLS_WARN_DAYS,
    DOMAIN,
    PLATFORMS,
    UID_MIDDLEWARES_PROBLEM,
    UID_ROUTERS_PROBLEM,
    UID_SERVICES_PROBLEM,
)
from .coordinator import TraefikProxyCoordinator, build_api_client
from .data import TraefikProxyConfigEntry, TraefikRuntimeData
from .entity import async_remove_legacy_devices, async_setup_devices, async_track_sw_version
from .entity_manager import (
    ROUTERS,
    SERVICES,
    TraefikEntityManager,
    async_remove_missing_store,
    per_item_entities_enabled,
)

_LOGGER = logging.getLogger(__name__)

# Repair issue raised once when the 1.2 migration removed replaced entities (D-19).
ISSUE_ENTITIES_MIGRATED: Final = "entities_migrated"
# unique_id suffix of the 0.3.0 reload button, removed by the 1.2 migration.
_LEGACY_RELOAD_BUTTON_SUFFIX: Final = "diagnostics_reload"
# Maps the disabled_by of a removed 0.3.0 router binary sensor to the one its
# router sensor replacement is created with. Enabled router binary sensors get
# no entry here: the platform creates their replacement as usual.
_ROUTER_REPLACEMENT_DISABLED_BY: Final[dict[er.RegistryEntryDisabler, er.RegistryEntryDisabler]] = {
    er.RegistryEntryDisabler.USER: er.RegistryEntryDisabler.USER,
}


def _issue_id(entry_id: str) -> str:
    return f"{ISSUE_ENTITIES_MIGRATED}_{entry_id}"


async def async_migrate_entry(hass: HomeAssistant, entry: TraefikProxyConfigEntry) -> bool:
    """Migrate a config entry to the current version (D-18).

    1.1 -> 1.2: remove this entry's router binary sensors (replaced by router
    sensors with new entity IDs) and the reload button, and enable the three
    problem aggregates where only the old disabled-by-default disabled them.
    A disabled router binary sensor is replaced by a disabled router sensor
    with the same unique_id and the old object id. User-disabled entities
    stay disabled; no surviving entity is renamed or re-IDed. A persistent repair issue explains the change when anything was
    removed. An entry from a newer major version fails (downgrade).
    """
    if entry.version > 1:
        _LOGGER.debug(
            "Cannot migrate Traefik entry %s from version %s.%s (downgrade)",
            entry.entry_id,
            entry.version,
            entry.minor_version,
        )
        return False

    if entry.minor_version < 2:
        registry = er.async_get(hass)
        router_prefix = f"{entry.entry_id}_{ROUTERS.prefix}"
        reload_unique_id = f"{entry.entry_id}_{_LEGACY_RELOAD_BUTTON_SUFFIX}"
        aggregate_unique_ids = {
            f"{entry.entry_id}_{suffix}"
            for suffix in (UID_ROUTERS_PROBLEM, UID_SERVICES_PROBLEM, UID_MIDDLEWARES_PROBLEM)
        }
        removed = 0
        # (unique_id, disabled_by, object_id) of each disabled router to re-create
        replacements: list[tuple[str, er.RegistryEntryDisabler, str]] = []
        for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
            if reg_entry.domain == "binary_sensor" and reg_entry.unique_id.startswith(router_prefix):
                mapped = (
                    _ROUTER_REPLACEMENT_DISABLED_BY.get(reg_entry.disabled_by)
                    if reg_entry.disabled_by is not None
                    else None
                )
                if mapped is not None:
                    replacements.append((reg_entry.unique_id, mapped, split_entity_id(reg_entry.entity_id)[1]))
                registry.async_remove(reg_entry.entity_id)
                removed += 1
            elif reg_entry.domain == "button" and reg_entry.unique_id == reload_unique_id:
                registry.async_remove(reg_entry.entity_id)
                removed += 1
            elif (
                reg_entry.domain == "binary_sensor"
                and reg_entry.unique_id in aggregate_unique_ids
                and reg_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
            ):
                registry.async_update_entity(reg_entry.entity_id, disabled_by=None)
        # Only the disabled state and the object id carry over; the platform
        # attaches the replacement to its device when it adds the router.
        for unique_id, disabled_by, object_id in replacements:
            registry.async_get_or_create(
                ROUTERS.domain,
                DOMAIN,
                unique_id,
                config_entry=entry,
                disabled_by=disabled_by,
                suggested_object_id=object_id,
            )
        hass.config_entries.async_update_entry(entry, minor_version=2)
        if removed:
            ir.async_create_issue(
                hass,
                DOMAIN,
                _issue_id(entry.entry_id),
                is_fixable=False,
                is_persistent=True,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_ENTITIES_MIGRATED,
                translation_placeholders={"entry_title": entry.title, "removed_count": str(removed)},
            )
        _LOGGER.debug(
            "Migrated Traefik entry %s to 1.2: %d entities removed, %d disabled routers kept disabled",
            entry.entry_id,
            removed,
            len(replacements),
        )

    return True


async def _async_options_updated(hass: HomeAssistant, entry: TraefikProxyConfigEntry) -> None:
    """Apply Options changes to the running coordinator (CONTEXT.md D-08).

    Options Flow writes the new scan_interval / verify_ssl / tls_warn_days
    into ``entry.options`` and HA fires this listener. We mutate the
    coordinator's ``update_interval`` directly so a scan-interval change
    takes effect on the next scheduled cycle without a full reload, and
    rebuild the API client so a verify_ssl change reaches the running
    client immediately (cheap: shared session, no network call). URL
    changes (reconfigure flow) come through ``entry.data`` instead of
    ``entry.options`` — HA's standard entry-data-change reload handles those
    by re-running ``async_setup_entry`` with the new URL, which rebuilds
    the API client + coordinator from scratch.
    """
    runtime = entry.runtime_data
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    runtime.coordinator.update_interval = timedelta(seconds=scan_interval)
    # The runtime data owns the only client; the coordinator reads it from
    # there, so this one assignment switches every caller to the new client.
    runtime.client = build_api_client(hass, entry)
    _LOGGER.debug(
        "Traefik options updated: entry_id=%s scan_interval=%ss",
        entry.entry_id,
        scan_interval,
    )
    # CONTEXT.md D-08: push tls_warn_days into CertCoordinator and
    # immediately re-render all cert binary sensors (no re-handshake
    # needed — threshold change is a UX concern, cert data is unchanged).
    # Defensive try/except so an options-mutation race never blocks the
    # listener from completing.
    new_threshold = entry.options.get(CONF_TLS_WARN_DAYS, DEFAULT_TLS_WARN_DAYS)
    try:
        await runtime.cert_coordinator.async_set_threshold(new_threshold)
    except Exception as err:  # final-resort catch-all; listener must complete
        _LOGGER.debug(
            "CertCoordinator.async_set_threshold raised (listener continues): %s",
            err,
        )


async def async_setup_entry(hass: HomeAssistant, entry: TraefikProxyConfigEntry) -> bool:
    """Set up Traefik from a config entry.

    Order matters:

    1. Build the API client and both coordinators, then assign
       ``entry.runtime_data`` before any refresh: the main coordinator reads
       its client from the runtime data, and the cert coordinator reads the
       main coordinator's data through it.
    2. Await the main coordinator's first refresh. It raises
       ``ConfigEntryNotReady`` on transient failure (HA retries) or
       ``ConfigEntryAuthFailed`` on 401/403 (reauth flow).
    3. ``try/except``-guarded first refresh on the cert coordinator: a TLS
       failure on the first cycle must not also raise
       ``ConfigEntryNotReady``. On failure an empty cache is seeded via
       ``async_set_updated_data({})`` so the platforms see a defined state
       instead of awaiting an unfinished refresh.
    4. Load the entity manager: stored missing-since times, the entry's
       registry entries and the deadline timer. With the per-item option
       off, purge the router and service registry entries right away.
    5. Register the main device and the Certificates sub-device, plus the
       Routers / Services sub-devices when per-item entities are on.
    6. Forward platforms (sensor, binary_sensor, button).
    7. Remove the entry's 0.3.0 per-category devices that no entity
       references any more, and keep the main device's ``sw_version``
       following the Traefik version.
    """
    client = build_api_client(hass, entry)
    coordinator = TraefikProxyCoordinator(hass, entry)
    cert_coordinator = CertCoordinator(hass, entry)
    entry.runtime_data = TraefikRuntimeData(
        client=client,
        coordinator=coordinator,
        cert_coordinator=cert_coordinator,
        entity_manager=TraefikEntityManager(hass, entry),
    )

    await coordinator.async_config_entry_first_refresh()

    _LOGGER.debug(
        "cert coordinator initialised: update_interval=%ds threshold=%d",
        int(cert_coordinator.update_interval.total_seconds()) if cert_coordinator.update_interval else 0,
        cert_coordinator.threshold_days,
    )
    try:
        await cert_coordinator.async_config_entry_first_refresh()
    except Exception as err:  # final-resort catch-all; cert failure must not raise ConfigEntryNotReady
        _LOGGER.debug(
            "cert coordinator first refresh failed (TLS probes deferred to next 6h cycle): %s",
            err,
        )
        # Seed an empty cache so the platforms see a defined state
        # instead of awaiting an unfinished refresh.
        cert_coordinator.async_set_updated_data({})

    entity_manager = entry.runtime_data.entity_manager
    await entity_manager.async_load()
    # Read once per setup; a changed option applies on the next reload.
    per_item = per_item_entities_enabled(entry)
    if not per_item:
        entity_manager.async_purge(ROUTERS)
        entity_manager.async_purge(SERVICES)

    # Every device exists, named and linked, before the first entity attaches.
    main = async_setup_devices(hass, entry, per_item=per_item)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Safe order (D-15): the platforms have re-pointed every entity they add
    # to the new devices, so only legacy devices nothing references are removed.
    async_remove_legacy_devices(hass, entry)
    entry.async_on_unload(async_track_sw_version(hass, entry, main.id))

    # Bind the Options-update listener. HA fires it whenever entry.options
    # (Options Flow submit) OR entry.data (reconfigure flow / reauth flow)
    # changes. The listener mutates coordinator.update_interval live; HA's
    # standard data-change handling takes care of full reloads for URL
    # changes (see async_setup_entry being re-invoked).
    entry.add_update_listener(_async_options_updated)

    _LOGGER.debug(
        "Traefik integration ready: entry_id=%s, scan_interval=%ss",
        entry.entry_id,
        coordinator.update_interval.total_seconds() if coordinator.update_interval else 0.0,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TraefikProxyConfigEntry) -> bool:
    """Unload a Traefik config entry.

    HA removes the update listener automatically as part of entry unload,
    so we do not need explicit teardown here.
    """
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: TraefikProxyConfigEntry) -> None:
    """Delete the data the entry keeps outside the registries.

    That is its missing-since Store and its migration repair issue, which
    unload keeps (M34).
    """
    ir.async_delete_issue(hass, DOMAIN, _issue_id(entry.entry_id))
    await async_remove_missing_store(hass, entry.entry_id)
