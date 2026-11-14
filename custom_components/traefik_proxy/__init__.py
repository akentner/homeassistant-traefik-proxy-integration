"""The Traefik integration: config entry setup, unload and removal."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant

from .cert_coordinator import CertCoordinator
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_TLS_WARN_DAYS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TLS_WARN_DAYS,
    PLATFORMS,
)
from .coordinator import TraefikProxyCoordinator, build_api_client
from .data import TraefikProxyConfigEntry, TraefikRuntimeData
from .entity import async_setup_devices
from .entity_manager import (
    ROUTERS,
    SERVICES,
    TraefikEntityManager,
    async_remove_missing_store,
    per_item_entities_enabled,
)

_LOGGER = logging.getLogger(__name__)


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
    async_setup_devices(hass, entry, per_item=per_item)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

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
    """Delete the data the entry keeps outside the registries (its missing-since Store)."""
    await async_remove_missing_store(hass, entry.entry_id)
