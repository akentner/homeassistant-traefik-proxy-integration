"""The Traefik integration."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

try:
    import probatio as vol
except ImportError:  # HA releases before 2026.9 ship voluptuous only
    import voluptuous as vol  # type: ignore[no-redef]
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service

from .cert_coordinator import CertCoordinator
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_TLS_WARN_DAYS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TLS_WARN_DAYS,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import TraefikProxyCoordinator, build_api_client
from .data import TraefikProxyConfigEntry, TraefikRuntimeData
from .entity_manager import TraefikEntityManager

_LOGGER = logging.getLogger(__name__)


# CONFIG_SCHEMA is required by hassfest whenever ``async_setup`` is implemented.
# The integration is config-flow only — YAML setup is intentionally unsupported —
# so this is the canonical empty-marker. See:
# https://developers.home-assistant.io/docs/config_entries_config_flow_handler/#config_flow-only
CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


# CONTEXT.md D-12: reload_routers takes no parameters — the service is
# fire-and-forget with a structured return dict. ``vol.Schema({})`` declares an
# explicit empty schema so HA's service UI shows "no fields" rather than
# prompting for anything.
RELOAD_ROUTERS_SCHEMA = vol.Schema({})


async def _async_handle_reload_routers(call: ServiceCall) -> dict[str, Any]:
    """Reload Traefik dynamic config and verify completion via router-set polling.

    CONTEXT.md D-12 / PITFALLS #15: Traefik returns 200/202 from
    ``/api/http/routers/refresh`` BEFORE providers finish reloading, so we
    capture the pre-POST router-name set, POST the refresh, then poll
    the router names of the coordinator snapshot with exponential backoff
    (``200ms -> 5s``, max 10 attempts, <= 5s budget) and exit early when the
    name set changes from the snapshot.

    Returns: ``{verified: bool, elapsed_ms: int, attempts: int, name_diff:
    {"added": [...], "removed": [...]}}``.

    Non-2xx POSTs raise ``TraefikProxyApiError`` -> HA surfaces the service-call
    failure to the caller. When no Traefik config entry is loaded (shouldn't
    happen for a sane HA install), we raise ``HomeAssistantError`` so HA's
    service UI shows a clear error rather than silently no-op'ing.
    """
    hass = call.hass
    t0 = time.monotonic()

    # Find the first loaded Traefik entry. The integration is `service`
    # type (one Traefik per config entry), so there should be exactly one
    # loaded entry in normal use.
    runtimes: list[TraefikRuntimeData] = [
        entry.runtime_data
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    if not runtimes:
        raise HomeAssistantError("No loaded Traefik config entry to reload against")
    runtime = runtimes[0]
    coordinator = runtime.coordinator

    def _current_router_names() -> set[str]:
        """Router names from the latest coordinator snapshot."""
        return set(coordinator.data.routers)

    before = _current_router_names()

    # Trigger the refresh. Raises TraefikProxyApiError -> HA surfaces as
    # service-call failure (the caller sees the error in the trace log).
    await runtime.client.reload_routers()

    # Poll the coordinator for an observable change. ``async_request_refresh``
    # is itself an awaitable that returns once the refresh cycle completes
    # (it internally calls ``_debounced_refresh.async_call()``), so awaiting
    # it gives us a clean "refresh finished, check the data" handoff.
    attempts = 0
    verified = False
    backoff_ms = 200
    max_attempts = 10
    max_budget_ms = 5000
    current = before
    while attempts < max_attempts and (time.monotonic() - t0) * 1000 < max_budget_ms:
        attempts += 1
        await coordinator.async_request_refresh()
        current = _current_router_names()
        if current != before:
            verified = True
            break
        await asyncio.sleep(backoff_ms / 1000)
        backoff_ms = min(backoff_ms * 2, 5000)

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    name_diff = {
        "added": sorted(current - before) if verified else [],
        "removed": sorted(before - current) if verified else [],
    }
    _LOGGER.debug(
        "traefik.reload_routers: verified=%s elapsed_ms=%d attempts=%d name_diff=%s",
        verified,
        elapsed_ms,
        attempts,
        name_diff,
    )
    return {
        "verified": verified,
        "elapsed_ms": elapsed_ms,
        "attempts": attempts,
        "name_diff": name_diff,
    }


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register integration-level services (PITFALLS M5: NOT async_setup_entry).

    The Traefik integration exposes one domain-level service:
    ``traefik.reload_routers``. Service registration lives in the module-level
    ``async_setup`` (HA's startup hook) rather than per-entry in
    ``async_setup_entry`` for two reasons:

    1. Per-entry registration causes duplicate registrations and stale
       handlers after unload (PITFALLS M5).
    2. The service is conceptually integration-scoped (one Traefik per
       config entry, but the service is callable regardless of which entry
       is loaded) — module-level registration makes that contract explicit.

    The service is admin-only: calls carrying a non-admin user context raise
    ``Unauthorized``. Calls without a user context (automations, the Reload
    button) are not subject to the check.

    The ``config`` argument is HA's YAML config (always empty for us — the
    integration is config-flow only). HA's setup machinery calls this with
    ``(hass, config)``; we ignore the second arg.
    """
    del config  # YAML setup not supported — ConfigFlow handles all configuration
    async_register_admin_service(
        hass,
        DOMAIN,
        "reload_routers",
        _async_handle_reload_routers,
        schema=RELOAD_ROUTERS_SCHEMA,
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
    4. Forward platforms (sensor, binary_sensor, button).
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
