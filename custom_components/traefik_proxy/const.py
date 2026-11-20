"""Constants for the Traefik integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "traefik_proxy"

# Configuration keys (entry.data). The credentials of the chosen auth type use
# Home Assistant's CONF_USERNAME / CONF_PASSWORD / CONF_TOKEN.
CONF_URL: Final = "url"
CONF_VERIFY_SSL: Final = "verify_ssl"
# Auth type of the entry; the values are those of ``api.AuthMode``.
CONF_AUTH_TYPE: Final = "auth_type"
# Bearer token of entries before 1.3. Only the 1.2 -> 1.3 migration reads it;
# diagnostics redact it.
CONF_API_KEY: Final = "api_key"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_TLS_WARN_DAYS: Final = "tls_warn_days"

# Options key: create one entity per router and per service. Large installs
# turn it off and keep only aggregate, diagnostic and certificate entities.
CONF_PER_ITEM_ENTITIES: Final = "per_item_entities"
DEFAULT_PER_ITEM_ENTITIES: Final = True

# Options key: hours a router, service or certificate that vanished from
# Traefik stays as "missing" before its entity is removed (wall clock,
# survives restarts and reloads).
CONF_MISSING_GRACE_HOURS: Final = "missing_grace_hours"
DEFAULT_MISSING_GRACE_HOURS: Final = 24
MIN_MISSING_GRACE_HOURS: Final = 1
MAX_MISSING_GRACE_HOURS: Final = 168

# Defaults
DEFAULT_VERIFY_SSL: Final = True
DEFAULT_SCAN_INTERVAL: Final = 15  # seconds
DEFAULT_NAME: Final = "Traefik Proxy"

# Per-item entity states: the Traefik item status plus ``missing`` for an item
# that vanished from the last successful snapshot. Order is the ENUM options order.
STATE_MISSING: Final = "missing"
ITEM_STATE_OPTIONS: Final = ("enabled", "warning", "error", "disabled", STATE_MISSING)

# Missing items are checked against the configured grace period every
# MISSING_CHECK_INTERVAL, so removal lands at most one interval after it.
MISSING_CHECK_INTERVAL: Final = timedelta(minutes=5)

# Problem aggregates list at most this many names; problem_count carries the full number.
MAX_PROBLEM_NAMES: Final = 50

# Unique_id suffixes (after "<entry_id>_") of the problem aggregates. They keep
# the historical "any_*_failing" form so existing entity_ids survive.
UID_ROUTERS_PROBLEM: Final = "diagnostics_any_router_failing"
UID_SERVICES_PROBLEM: Final = "diagnostics_any_service_failing"
UID_MIDDLEWARES_PROBLEM: Final = "diagnostics_any_middleware_failing"
# Unique_id suffix of the certificate problem aggregate (new in 1.0, no historical form).
UID_CERTIFICATES_PROBLEM: Final = "certificates_problem"

# Bounds of the options form. MIN_SCAN_INTERVAL / MAX_SCAN_INTERVAL bound the
# scan interval: the 15 s lower bound keeps the API polite, the 300 s upper
# bound keeps entity states fresh enough to be useful. MIN_TLS_WARN_DAYS /
# MAX_TLS_WARN_DAYS bound the certificate expiry warning threshold.
MIN_SCAN_INTERVAL: Final = 15
MAX_SCAN_INTERVAL: Final = 300
MIN_TLS_WARN_DAYS: Final = 1
MAX_TLS_WARN_DAYS: Final = 90
DEFAULT_TLS_WARN_DAYS: Final = 14

# Cert-cycle knobs. ``TLS_HANDSHAKE_TIMEOUT`` caps the per-host TLS handshake
# at 5 s, so a hanging host cannot stall the cycle indefinitely.
# ``TLS_SEMAPHORE`` bounds concurrent handshakes to 4 (a config with thousands
# of routers would otherwise fan out a thundering herd).
# ``DEFAULT_TLS_CERT_COOLDOWN`` is the 6 h cadence (21600 s): with a 14-day
# warning threshold, a user is alerted within about 6 h of a certificate
# entering the warning window.
TLS_HANDSHAKE_TIMEOUT: Final = 5.0
TLS_SEMAPHORE: Final = 4
DEFAULT_TLS_CERT_COOLDOWN: Final = 21600
# Seconds until the next cert cycle after a failed one (instead of the 6h cadence).
CERT_RETRY_INTERVAL: Final = 300
# Upper bound of hosts probed per cert cycle (a constant, not an option).
MAX_CERT_HOSTS: Final = 200

# Platforms forwarded in async_setup_entry: binary_sensor (problem aggregates,
# certificate expiring), sensor (per-item, snapshot and certificate expiry
# sensors) and button (refresh).
PLATFORMS: Final = ["binary_sensor", "sensor", "button"]
