# Home Assistant Traefik Proxy Integration

## What This Is

A custom Home Assistant integration that connects to a Traefik reverse proxy
and surfaces its operational state inside Home Assistant — routers, services,
entrypoints, middleware, and TLS certificate health are exposed as entities
the user can monitor, automate against, and visualize in dashboards.

Built for self-hosters running Traefik in front of their Home Assistant
and other homelab services who want a single pane of glass for reverse-proxy
health instead of having to log into the Traefik dashboard separately.

## Core Value

If nothing else works, the user must be able to see — at a glance inside
Home Assistant — which Traefik routers are enabled, which are failing,
and which TLS certificates are expiring soon.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- [x] **CORE-04**: The integration exposes each discovered Traefik router as a
      binary sensor named after its `@router` rule identifier, with state
      derived from the router's `status` field. _(Validated in Phase 1,
      re-validated by Phase 2 per-category device migration.)_
- [x] **CORE-05**: The integration exposes each Traefik entrypoint as a sensor
      reporting the listening address and current request count. _(Validated
      in Phase 2 — `TraefikEntrypointSensor`.)_
- [x] **CORE-06**: The integration exposes each Traefik service as a sensor
      reporting its load-balancer status and backend server health. _(Validated
      in Phase 2 — `TraefikServiceSensor`.)_
- [x] **DIAG-01**: The integration aggregates a top-level `sensor.traefik`
      reporting the total number of routers, services, and middlewares.
      _(Validated in Phase 2 — 3 aggregate count sensors on the Overview
      device.)_
- [x] **DIAG-02**: The integration creates a `binary_sensor` that becomes `on`
      when any router is reporting a non-`enabled` status. _(Validated in
      Phase 2 — `TraefikAnyRouterFailingBinarySensor` on the Diagnostics
      device.)_
- [x] **DIAG-03**: ~~The integration supports a "reload" service that triggers
      a Traefik router refresh.~~ _(Superseded in Phase 5: the reload service
      and reload button were removed; the "Refresh now" button, which polls
      Traefik again on demand, replaces them.)_

- [x] **TLS-01**: For every router terminating TLS, the integration exposes
      a sensor with the certificate's `notAfter` date and a calculated
      "days until expiry" attribute. _(Validated in Phase 3; refined in
      Phase 6 by CERT-01/05 — `/api/certificates` on Traefik ≥ 3.7, threadless
      probe otherwise, live `days_until_expiry`.)_
- [x] **TLS-02**: The integration creates a dedicated `binary_sensor` per
      certificate that turns `on` when the certificate is within a
      user-configurable expiry threshold (default: 14 days). _(Validated in
      Phase 3; refined in Phase 6 by CERT-05 — on with a `reason` for
      expiring / expired / probe_failed / not_found, plus the
      `certificates_problem` aggregate.)_

- [x] **CORE-01**: User can configure the integration via the Home Assistant
      config flow by providing the Traefik API URL and an API key (or bearer
      token). _(Validated in Phase 1; refined in Phase 7 — auth selector
      none / basic / bearer, reauth and reconfigure flows.)_
- [x] **CORE-03**: The integration connects to the Traefik API over HTTP.
      _(Validated in Phase 1; refined in Phase 4 — one `/api/rawdata` request
      per cycle, paginated `/api/http/*` endpoints only as the 404 fallback.)_
- [x] **CFG-01**: User can override the API base URL, TLS verification, scan
      interval, and certificate warning threshold from integration options.
      _(Validated in Phase 1; refined in Phase 7 — `OptionsFlowWithReload`,
      configurable entity grace period.)_
- [x] **DOCS-01**: A `README.md` documents install via HACS and manual,
      configuration options, and example dashboards / automations.
      _(Validated in Phase 1; rewritten for the Marketplace in Phase 8,
      REL-03.)_
- [x] **TEST-01**: Unit tests cover the Traefik API client (parsing, error
      paths) and the entity state derivation logic. _(Validated in Phase 1;
      Phase 8: 1180 tests, coverage gate 99 % on the minimum HA 2026.11.0
      stack too.)_
- [x] **REL-01..08**: Marketplace and release readiness — manifest category,
      brand, README/CHANGELOG, CI and tooling, no planning references, local
      hassfest plus hacs/action 10/10 in the first PR CI run, branch pushed
      with Draft PR #2. _(Validated in Phase 8.)_

### Active

<!-- Current scope. Building toward these. Hypotheses until shipped. -->

None — milestone v1.0 scope is shipped on `feat/marketplace-polish`. The
release itself (merge, CHANGELOG date, tag `v1.0.0`, GitHub release,
`hacs/default` PR) is the user's action.

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- **CORE-02: YAML configuration (`configuration.yaml`)** — dropped (CFG-02):
  the YAML path never worked and was removed in Phase 7 (FLOW-07); setup is
  UI-only.
- **Mutating Traefik configuration files on disk** — Traefik's dynamic
  configuration is intentionally external; this integration only reads
  state, it does not write files.
- **Auto-provisioning TLS certificates (Let's Encrypt / ACME flow)** —
  Traefik already handles this; duplicating it in HA would fight the
  source of truth.
- **A built-in web UI for editing Traefik routes** — out of scope; the
  Traefik dashboard already exists.
- **Traefik v1 support** — only Traefik v2.x and v3.x are targeted
  (only one API shape to maintain).
- **Cloud-managed Traefik / Traefik Enterprise** — only the OSS proxy
  is targeted.
- **Streaming WebSocket (`/api/websocket`) integration for live updates**
  — polling at the user-configurable interval is sufficient for v1 and
  dramatically simpler to implement.

## Context

The user already runs multiple Home Assistant instances reachable over
Tailscale, maintains several custom HA integrations (chargefinder, gatus,
kroki, etc.), and uses Traefik as the fronting reverse proxy in their
homelab. This integration slots into that existing ecosystem as another
self-hosted component — a HACS-distributable custom component that other
self-hosters can adopt.

Home Assistant integrations follow a well-documented convention:
`custom_components/<domain>/` with `__init__.py`, `manifest.json`,
`config_flow.py`, `const.py`, and one coordinator/entity file per
concern. The HA Core `DataUpdateCoordinator` pattern is the standard way
to poll an external API and fan updates out to entities.

The Traefik HTTP API (`/api/...`, optionally behind basic auth or a
`Bearer` token) provides read-only access to operational state. The
integration only reads it. All endpoints return JSON.

## Constraints

- **Tech stack**: Python >= 3.14.2, Home Assistant Core (minimum version
  2026.11.0), `aiohttp` for HTTP, HACS-compatible.
- **Distribution**: HACS default repository structure (`hacs.json`,
  `README.md` as the information file — no `info.md`, version tags via
  releases).
- **Compatibility**: Must work against Traefik v2.11+ and v3.x.
- **Performance**: API polling must not exceed one call-set per scan
  interval (default 15 s) per integration instance; multiple endpoints
  fetched in parallel via `asyncio.gather`.
- **Security**: API tokens never logged; integration must support
  self-signed certificates via user option.
- **No external service dependencies**: integration talks only to the
  Traefik API the user points it at — no SaaS, no telemetry.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Polling, not WebSocket | Simpler, fewer failure modes, scan interval is fine for v1 | — Pending |
| v2/v3 Traefik API only | One API shape to maintain; v1 is EOL | — Pending |
| HACS-distributable, not core | Matches pattern of user's other custom integrations | — Pending |
| Config flow + YAML | Config flow is the modern HA path, YAML still needed for power users | — Pending |
| Per-router / per-cert entities | Maps cleanly to HA entity model; users can build dashboards on top | — Pending |
| `aiohttp` over `requests` | Async, matches HA Core's loop, no thread-pool | — Pending |
| Certificate not covering its host = problem (`not_found`) in both sources | Traefik serves its ~1-year default certificate to uncovered hosts; reporting it as healthy would hide the failure (D-03/R-1, review CR-01) | ✓ Phase 6 |
| Keep the Traefik Proxy logo lockup (`logo.png` / `dark_logo.png`) | User decision 2026-11-16 (A3/A8); README and `docs/BRAND.md` state that the Traefik Labs trademark guidelines were not reviewed and no permission is claimed | ✓ Phase 8 |
| Prove hacs/action in the PR CI run, not locally | The validators need a GitHub token; agents never run `make hacs-action` (M43) | ✓ Phase 8 — run 43769962201, All (10) checks passed |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-11-16 after Phase 8 completion — milestone v1.0 scope shipped on `feat/marketplace-polish` (Draft PR #2, CI green incl. hacs/action 10/10); logo lockup kept (A3/A8); release steps remain the user's.*
