---
gsd_state_version: "1.0"
milestone: v1.0
current_phase: 05
current_phase_name: Entity model + lifecycle
status: verifying
stopped_at: Completed 05-08-PLAN.md
last_updated: "2026-11-14T22:57:35.417Z"
last_activity: 2026-11-14
last_activity_desc: 05-08 gap closure executed
state_head: 19cbb4272c9089e5036803bfcffea0f747432e31
progress:
  total_phases: 8
  completed_phases: 4
  total_plans: 28
  completed_plans: 28
milestone_name: milestone
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-05)

**Core value:** If nothing else works, the user must be able to see — at a
glance inside Home Assistant — which Traefik routers are enabled, which are
failing, and which TLS certificates are expiring soon.
**Current focus:** Phase 05 — Entity model + lifecycle

## Current Position

Phase: 05 (Entity model + lifecycle) — EXECUTED, READY FOR VERIFICATION
Plan: 8 of 8
Status: Phase complete — ready for verification
Last activity: 2026-11-14 — 05-08 gap closure executed (CR-01, WR-01, WR-02)

Progress: [█████░░░░░] 50% (3 of 8 phases)

## Performance Metrics

**Velocity:**

- Total plans completed: 18
- Average duration: 13m
- Total execution time: 1.7 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Foundation | 4 | 4 | 12m |
| 2. Core Entities + Options + Reauth + Reload | 2 | 4 | 11m |
| 3. TLS Certificate Expiry | 3 | 3 | 16m |
| 4. Data layer (correct + lean) | 0 | — | — |
| 04 | 9 | - | - |

**Recent Trend:**

- Last 5 plans: Phase 3 P01 (25m) + Phase 3 P02 (14m) + Phase 3 P03 (25m) — Phase 3 done in 64m cumulative
- Trend: stable

*Updated after each plan completion*
| Phase 01 P01 | 10 | 2 tasks | 9 files |
| Phase 01 P02 | 7 | 3 tasks | 4 files |
| Phase 01 P03 | 9 | 2 tasks | 6 files |
| Phase 01 P04 | 25 | 2 tasks | 18 files |
| Phase 02-core-entities-options-reauth-reload P01 | 17m | 3 tasks | 12 files |
| Phase 02-core-entities-options-reauth-reload P03 | 4m | 3 tasks | 3 files |
| Phase 02 P02 | 9m | 3 tasks | 4 files |
| Phase 02-core-entities-options-reauth-reload P04 | 627s | 3 tasks | 9 files |
| Phase 3 P01 | 25min | 3 tasks | 7 files |
| Phase 3 P02 | 14min | 2 tasks | 2 files |
| Phase 3 P03 | 25min | 4 tasks | 5 files |
**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 04 P01 | 8min | 2 tasks | 23 files |
| Phase 04 P02 | 8min | 3 tasks | 15 files |
| Phase 04 P03 | 7 min | 2 tasks | 3 files |
| Phase 04 P04 | 9min | 3 tasks | 14 files |
| Phase 04 P05 | 8min | 2 tasks | 14 files |
| Phase 04 P06 | 7 min | 3 tasks | 10 files |
| Phase 04 P07 | 6 min | 2 tasks | 6 files |
| Phase 04 P08 | 7min | 2 tasks | 6 files |
| Phase 04 P09 | 6min | 2 tasks | 5 files |
| Phase 05 P01 | 12min | 2 tasks | 11 files |
| Phase 05 P02 | 261min | 2 tasks | 10 files |
| Phase 05 P04 | 5min | 1 tasks | 6 files |
| Phase 05 P05 | 7min | 1 tasks | 9 files |
| Phase 05 P06 | 13min | 1 tasks | 9 files |
| Phase 05 P07 | 14min | 3 tasks | 11 files |
| Phase 05 P08 | 8min | 3 tasks | 6 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Phase 1 — pending]: Polling, not WebSocket; v2/v3 Traefik API only;
  HACS-distributable; Config Flow + YAML; per-router/per-cert entities;
  `aiohttp` over `requests`. (All listed in PROJECT.md — to be moved to
  Validated after Phase 1 ships.)

- [Phase 3 — pending]: TLS handshake uses stdlib `ssl` (no `cryptography`
  import), `asyncio.to_thread` wrapper, separate `CertCoordinator` with
  6-hour cadence. Spike to validate against 3+ real Traefik deployments
  before Phase 3 planning.

- [Phase 2 — pending]: HA quality-scale rule "Polling intervals are NOT
  user-configurable" — scan-interval override is opt-in via Options Flow
  but quality-scale Bronze is targeted without it (decide during Phase 2
  discuss).

- [Phase 02-core-entities-options-reauth-reload]: Per-category multi-device model: TraefikEntity takes (entry, category, *, description_key=None); device identifier is (DOMAIN, f'{entry_id}_{category}') instead of Phase 1's single-device (DOMAIN, entry_id). Existing HA device-registry rows become orphans; new per-category devices appear on first restart after upgrade.
- [Phase 02-core-entities-options-reauth-reload]: TraefikData is now a TypedDict (PEP-589, total=False) with version/entrypoints/http_routers/http_services/http_middlewares/overview keys. fetch_all drops entire payload on non-auth error (CONTEXT.md D-07) so entities see a stale cycle rather than mixed fresh+stale data.
- [Phase 02-core-entities-options-reauth-reload]: filter_internal_items lifted from binary_sensor to api.py — canonical helper for @<provider> filtering across all Phase 2 platforms (routers/services/middlewares/entrypoints). Local _filter_user_routers / _PROVIDER_SUFFIX_RE removed from binary_sensor.
- [Phase 02-core-entities-options-reauth-reload]: reload_routers POSTs /api/http/routers/refresh with explicit Content-Length: 0 header (aiohttp requires it for empty-body POSTs). Does not poll — verification lives in the reload service handler (plan 02-04). Traefik returns 202 before reload completes (PITFALLS #15).
- [Phase 02-core-entities-options-reauth-reload]: TypedDict(total=False) safe access via _dict_or_empty / _list_or_empty helpers in sensor.py — keeps mypy --strict clean when reading partial coordinator payloads; pattern reusable across Phase 2+ platforms (Phase 3 TLS sensors).
- [Phase 03]: Combined cert-cycle listener per platform (single cert_coordinator.async_add_listener registration covers both BLOCKER #2 entity-creation AND WARNING #1 stale-cleanup). Folding into one callback keeps listener count minimal and ensures both paths fire atomically on every cert cycle.
- [Phase 03]: Shared _cert_cache_availability helper in sensor.py imported by binary_sensor.py — single source of truth for cache availability across both platforms (SUGGESTION #1 fix; eliminates the per-platform-helper-drift bug class). Public cert_cache_availability alias added for tests / future cross-module callers.
- [Phase 03]: TraefikCertExpiryBinarySensor._attr_entity_registry_enabled_default = True (D-03 explicit divergence from Phase 2 M-12 on TraefikAnyRouterFailingBinarySensor) — cert expiry is a security-impacting alarm that warrants always-on visibility. Phase 2 router-failure aggregate keeps the default-off behavior because router failures often reflect deployment churn rather than outages.
- [Phase 03]: Host normalised to lowercase at __init__ top of both TraefikCertTimestampSensor AND TraefikCertExpiryBinarySensor — defensive against cache rows populated with mixed casing (cert coordinator already lowercases in production but test harness could inject mixed casing; threat-model hardening).
- [Phase 03]: mock_certificate_server test fixture generates a CA-signed cert per test (not self-signed) and monkey-patches production _open_tls_connection to also load_verify_locations(cafile=<test CA>) — production SSLContext rejects self-signed chains under PROTOCOL_TLS_CLIENT+load_default_certs, so the throwaway CA must be in the trust store for the handshake to complete.
- [Phase 03]: conftest.py pre-imports `custom_components.traefik.tls` at module level — pytest-homeassistant-custom-component ships a namespace package at testing_config/custom_components/ that would otherwise shadow the production module for in-fixture imports; module-level pre-import binds it to sys.modules before the namespace hijack takes effect.
- [Phase 03]: Mock-server handshake tests use `asyncio.to_thread` to drive the sync `fetch_cert_info` from async tests — passing through without the thread wrapper blocks the asyncio TLS server's accept path (event-loop starvation), causing the handshake to hang.
- [Phase 03]: HA's `CachedProperties` metaclass moves class-level `_attr_*` attributes to private `__attr_*` names and wraps them in `property`. Tests that pin entity default-state attributes (e.g. `_attr_entity_registry_enabled_default`) read `cls.__dict__.get("__attr_<name>")` to get the underlying boolean value.
- [Phase 04]: 04-01: Traefik v2.11.63 and v3.7.19 send X-Next-Page: 1 on the last page; client follows the header only while int(value) > current page (D-07 rule)
- [Phase 04]: 04-01: Observed status strings are only enabled/warning/disabled (no literal error); disabled + non-empty error[] is the D-02 error case; services stay enabled with a DOWN server
- [Phase 04]: 04-01: --ping on the traefik entrypoint provides the @internal router (ping@internal) because insecure API mode stays off
- [Phase 04]: 04-02: TraefikRuntimeData owns the only API client; TraefikProxyCoordinator.client is a read-only property over runtime_data.client, so an options change replaces the client in one statement
- [Phase 04]: 04-02: entry.runtime_data is assigned before both first refreshes; platforms read runtime_data.coordinator/.cert_coordinator directly (no getattr, cert block always runs)
- [Phase 04]: 04-03: ALLOWED_GENERATION_DIFFERENCES empty - v2.11.63 and v3.7.19 agree on every projected router/service/middleware field
- [Phase 04]: 04-03: Service/Middleware type = list-form type, else lowercased single non-meta rawdata key
- [Phase 04]: 04-03: parse_version uses startDate (StartDate accepted); missing -> KeyError, non-string -> TypeError, unparsable -> ValueError, naive -> UTC
- [Phase 04]: 04-03: TDD RED commits carry an interface stub of models.py so RED fails on assertions (tdd.md treats import faults as INVALID_RED)
- [Phase 04]: 04-04: X-Next-Page loop continues only while the header is an int greater than the current page; missing/non-integer header ends it; an announced page above MAX_PAGES raises TraefikProxyPayloadError
- [Phase 04]: 04-04: per-item entities store _item_name plus the construction-time model and resolve the current model from coordinator.data on every read (fallback: last known model)
- [Phase 04]: 04-04: cert host collection skips routers with Router.tls False; snapshot consumers never read raw API dicts
- [Phase 04]: 04-05: Basic Authorization header built in api.py (base64 of UTF-8 user:password); aiohttp 3.14 deprecates BasicAuth and HA 2026.3's aiohttp 3.13 lacks encode_basic_auth
- [Phase 04]: 04-05: Auth rejects credentials its mode does not use and control characters; config flow maps that ValueError to invalid_auth
- [Phase 04]: 04-05: TraefikProxyApiError(path, detail, *, status) — messages are '<path>: HTTP <status>' / '<path>: <ExceptionType>' / fixed description; reload_routers keeps 401/403 -> Auth, other non-2xx -> base error until Phase 5
- [Phase 04]: 04-06: One GET /api/rawdata per steady cycle; a rawdata 404 switches the client to the paginated list endpoints for its lifetime; 401/500/shape errors do not fall back
- [Phase 04]: 04-06: /api/version re-checked hourly and after a failed cycle; /api/entrypoints only when version or start date changed; stored version replaced only after the entrypoint fetch succeeded
- [Phase 04]: 04-06: A failing version re-check fails the whole cycle with the D-16 mapping (auth -> reauth, else UpdateFailed keeping the previous snapshot)
- [Phase 04]: 04-07: cert entities bind to the cert coordinator via TraefikProxyCertEntity(_TraefikProxyBaseEntity[CertCoordinator]); availability depends only on the cert cycle; sw_version from the main snapshot
- [Phase 04]: 04-08: aiohttp request-construction ValueError maps to TraefikProxyInvalidUrlError (setup retries, no traceback)
- [Phase 04]: 04-08: URL userinfo rejected in user/reconfigure via strict allow_userinfo=False default; reauth_confirm and YAML import opt out (W19)
- [Phase 04]: 04-09: Paginated fallback revocable (M27, amends D-07): hourly version re-check retries /api/rawdata once while paginated; at most one extra rawdata request per hour
- [Phase 04]: 04-09: Rawdata probe armed only when the re-check interval elapsed, never by a post-failure re-check inside it
- [Phase 04]: 04-09: Probe auth errors propagate; other probe failures keep the pages and serve the same cycle
- [Phase 05]: 05-01: RED commit of a tdd task carries xfail(strict=True) markers so every commit stays green (D-20/W42); GREEN removes them
- [Phase 05]: 05-01: TraefikEntityManager on runtime_data; kind listener registered before entities; new keys added once in sorted order; vanished keys stamped missing; registry link via async_update_device(via_device_id)
- [Phase 05]: 05-02: missing_since persisted per entry in a helpers.storage.Store (traefik_proxy.missing.<entry_id>); stored times of kinds not registered yet are carried through every write
- [Phase 05]: 05-02: deadline check by async_track_time_interval every 5 min (cancel_on_shutdown); deadline inclusive (>= 24 h); removal lands within one interval
- [Phase 05]: 05-02: future stored missing_since values are clamped to now at load; the Store is created in async_load
- [Phase 05]: 05-04: per-item option read once per setup; off purges router/service registry entries and Routers/Services sub-devices without grace (change applies on next reload until Phase 7)
- [Phase 05]: 05-05: Both cert kinds key on every host in the cert data (CertInfo and CertError rows); a failing host keeps a stable registry entry
- [Phase 05]: 05-05: Cert entity names via translation_key + {host} placeholder ('{host} expiry' / '{host} expiring'); IN-11 closed
- [Phase 05]: 05-06: Refresh button PARALLEL_UPDATES = 1 (serializes presses on top of the request-refresh debouncers)
- [Phase 05]: 05-06: Refresh button keeps inherited CoordinatorEntity availability (unavailable while the main coordinator's last update failed)
- [Phase 05]: 05-07: async_remove_legacy_devices removes only devices with exactly one legacy identifier and no current identifier, and only while no registry entry (disabled included) references them
- [Phase 05]: 05-07: cross-entry tests use a user-disabled second entry, because setting up the integration sets up every enabled entry of the domain
- [Phase 05]: 05-07: zero-write tests snapshot State.last_reported values; HA updates last_reported in place
- [Phase 05]: 05-08: Disabled 0.3.0 router binary sensors are replaced by disabled router sensors (USER->USER, DEVICE->USER, INTEGRATION->INTEGRATION) seeded with the old object id; name/area/icon not carried over
- [Phase 05]: 05-08: Update listener registered via entry.async_on_unload(entry.add_update_listener(...))
- [Phase 05]: 05-08: _async_remove_device_if_unreferenced is the single device-removal path in entity.py (per-item off and legacy cleanup)

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 3 is strongly flagged in `research/SUMMARY.md` for a `gsd-spike`
  before planning: TLS handshake has subtle edge cases (SNI, multi-cert
  chains, wildcard certs, IPv6). Spike should validate 3+ real Traefik
  deployments and confirm format-string loop covers observed `notAfter`
  shapes.

- `requirementS.md` footer says `46 total` but the traceability table
  contains 49 rows (CFG:6 + API:6 + COORD:4 + ROUTER:4 + ENTRY:3 +
  DIAG:4 + TLS:5 + UX:4 + DIST:5 + DOCS:4 + TEST:4 = 49). Table itself
  is correct — only the footer is stale. Cosmetic; not a coverage gap.
  Phase 03 closed out TEST-04 — only DIAG-04 + DIST-04/05 + DOCS-02/03/04
  remain pending in Phase 4.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 261113-viw | Security fixes: verify_ssl single source, admin-only reload service, no token prefill in reconfigure, HA 2026.3.0 minimum + HA 2026.10 compat | 2026-11-13 | 1a07f14 | [261113-viw-security-fixes-verify-ssl-single-source-](./quick/261113-viw-security-fixes-verify-ssl-single-source-/) |

- `custom_components/traefik/config_flow.py` ruff-format diff is pre-existing
  from Phase 2-02 (verified via `git stash` before-plan baseline). Out of
  scope for 03-03 — per deviation rules, only directly-caused reformatting
  is in scope.

### Roadmap Evolution

- Phase 4 added: Data layer (correct + lean) — replaces old Phase 4 (Quality + Diagnostics + Polish + HACS) after marketplace research + code audit (M11)
- Phase 5 added: Entity model + lifecycle — replaces old Phase 4 (Quality + Diagnostics + Polish + HACS) after marketplace research + code audit (M11)
- Phase 6 added: Certificates — replaces old Phase 4 (Quality + Diagnostics + Polish + HACS) after marketplace research + code audit (M11)
- Phase 7 added: Config flow, HA 2026.12 compatibility, observability — replaces old Phase 4 (Quality + Diagnostics + Polish + HACS) after marketplace research + code audit (M11)
- Phase 8 added: Marketplace + release readiness — replaces old Phase 4 (Quality + Diagnostics + Polish + HACS) after marketplace research + code audit (M11)

## Session Continuity

Last session: 2026-11-14T22:57:35.327Z
Stopped at: Completed 05-08-PLAN.md
Resume file: None
Next: /gsd-execute-phase 4 (plan 04-02)
