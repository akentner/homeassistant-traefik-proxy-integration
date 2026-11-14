---
gsd_state_version: "1.0"
milestone: v1.0
current_phase: 3
current_phase_name: Data layer (correct + lean)
status: executing
stopped_at: Completed 04-01-PLAN.md
last_updated: "2026-11-14T00:21:32.960Z"
last_activity: 2026-11-14
last_activity_desc: "Restructured milestone v1.0: old Phase 4 replaced by Phases 4-8 (data layer, entity lifecycle, certificates, flows/2026.12/observability, marketplace release)"
state_head: 668b62001815f62abed97ebd678dd3876d780a4d
progress:
  total_phases: 8
  completed_phases: 3
  total_plans: 17
  completed_plans: 12
milestone_name: milestone
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-05)

**Core value:** If nothing else works, the user must be able to see — at a
glance inside Home Assistant — which Traefik routers are enabled, which are
failing, and which TLS certificates are expiring soon.
**Current focus:** Phase 4 — Data layer (correct + lean). Branch `feat/marketplace-polish`; Phases 4–8 replace the old Phase 4 (see ROADMAP.md).

## Current Position

Phase: 4 (Data layer (correct + lean)) — READY TO EXECUTE
Plan: 2 of 6
Status: Executing Phase 4 (04-01 complete)
Last activity: 2026-11-14 - 04-01 complete: real redacted Traefik v2.11/v3.7 fixtures + capture harness

Progress: [████░░░░░░] 38% (3 of 8 phases)

## Performance Metrics

**Velocity:**

- Total plans completed: 8
- Average duration: 13m
- Total execution time: 1.7 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Foundation | 4 | 4 | 12m |
| 2. Core Entities + Options + Reauth + Reload | 2 | 4 | 11m |
| 3. TLS Certificate Expiry | 3 | 3 | 16m |
| 4. Data layer (correct + lean) | 0 | — | — |

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

Last session: 2026-11-14T00:21:32.909Z
Stopped at: Completed 04-01-PLAN.md
Resume file: None
Next: /gsd-execute-phase 4 (plan 04-02)
