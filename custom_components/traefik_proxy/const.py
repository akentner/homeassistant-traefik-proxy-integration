"""Constants for the Traefik integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "traefik_proxy"

# Configuration keys (entry.data)
CONF_URL: Final = "url"
CONF_API_KEY: Final = "api_key"
CONF_VERIFY_SSL: Final = "verify_ssl"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_TLS_WARN_DAYS: Final = "tls_warn_days"

# Options key: create one entity per router and per service. Large installs
# turn it off and keep only aggregate, diagnostic and certificate entities.
CONF_PER_ITEM_ENTITIES: Final = "per_item_entities"
DEFAULT_PER_ITEM_ENTITIES: Final = True

# Defaults
DEFAULT_VERIFY_SSL: Final = True
DEFAULT_SCAN_INTERVAL: Final = 15  # seconds (CONTEXT.md D-12)
DEFAULT_NAME: Final = "Traefik Proxy"

# Per-item entity states: the Traefik item status plus ``missing`` for an item
# that vanished from the last successful snapshot. Order is the ENUM options order.
STATE_MISSING: Final = "missing"
ITEM_STATE_OPTIONS: Final = ("enabled", "warning", "error", "disabled", STATE_MISSING)

# A missing item's entity is removed once it has been missing this long (wall
# clock, survives restarts). The check runs every MISSING_CHECK_INTERVAL, so
# removal lands at most one interval after the deadline.
MISSING_GRACE_PERIOD: Final = timedelta(hours=24)
MISSING_CHECK_INTERVAL: Final = timedelta(minutes=5)

# Problem aggregates list at most this many names; problem_count carries the full number.
MAX_PROBLEM_NAMES: Final = 50

# Unique_id suffixes (after "<entry_id>_") of the problem aggregates. They keep
# the historical "any_*_failing" form so existing entity_ids survive.
UID_ROUTERS_PROBLEM: Final = "diagnostics_any_router_failing"
UID_SERVICES_PROBLEM: Final = "diagnostics_any_service_failing"
UID_MIDDLEWARES_PROBLEM: Final = "diagnostics_any_middleware_failing"

# Clamps for Options Flow (Phase 2 — Plan 02-02 fills these in).
# MIN_SCAN_INTERVAL/MAX_SCAN_INTERVAL bound the scan-interval knob
# (CONTEXT.md D-09 — 15s lower bound keeps the API polite; 300s upper bound
# keeps entity states fresh enough to be useful). MIN_TLS_WARN_DAYS /
# MAX_TLS_WARN_DAYS bound the cert-expiry warning threshold placeholder
# (CONTEXT.md D-09 — Phase 3 picks the value up).
MIN_SCAN_INTERVAL: Final = 15
MAX_SCAN_INTERVAL: Final = 300
MIN_TLS_WARN_DAYS: Final = 1
MAX_TLS_WARN_DAYS: Final = 90
DEFAULT_TLS_WARN_DAYS: Final = 14

# Phase 3 cert-cycle knobs (CONTEXT.md D-05). ``TLS_HANDSHAKE_TIMEOUT`` caps
# the per-host TLS handshake at 5s — a hanging host cannot stall the cycle
# indefinitely. ``TLS_SEMAPHORE`` bounds concurrent handshakes to 4 (a
# hostile config with 10k routers would otherwise fan out a thundering
# herd). ``DEFAULT_TLS_CERT_COOLDOWN`` is the 6h cadence (21600s) — the
# spike's 6h default; a 14d warning threshold with 6h probes means a
# user is alerted within ±6h of a cert entering the warning window.
TLS_HANDSHAKE_TIMEOUT: Final = 5.0
TLS_SEMAPHORE: Final = 4
DEFAULT_TLS_CERT_COOLDOWN: Final = 21600
# Seconds until the next cert cycle after a failed one (instead of the 6h cadence).
CERT_RETRY_INTERVAL: Final = 300
# Upper bound of hosts probed per cert cycle (a constant, not an option).
MAX_CERT_HOSTS: Final = 200

# Version - bumped manually; CI in Plan 04 enforces match with git tag
VERSION: Final = "1.0.0"

# Platforms forwarded in async_setup_entry.
# Phase 2 adds sensor (entrypoint/service/aggregate) and button (refresh).
PLATFORMS: Final = ["binary_sensor", "sensor", "button"]
