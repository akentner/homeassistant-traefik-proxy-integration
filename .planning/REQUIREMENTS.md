# Requirements: Home Assistant Traefik Integration

**Defined:** 2026-07-05
**Core Value:** If nothing else works, the user must be able to see — at a glance inside Home Assistant — which Traefik routers are enabled, which are failing, and which TLS certificates are expiring soon.

## v1 Requirements

Requirements for initial release. Each maps to a roadmap phase.

### Configuration & Setup (CFG)

- [x] **CFG-01**: User can configure the integration via the Home Assistant UI
      config flow by providing the Traefik API URL and a bearer token.
- [~] ~~**CFG-02**~~ _(dropped — the YAML path never worked and is removed in FLOW-07 (audit A-18, U-14))_: User can alternatively configure the integration via
      `configuration.yaml` for users who prefer YAML / pinned releases.
- [x] **CFG-03**: User can reconfigure the Traefik URL without deleting and
      re-adding the integration entry.
- [x] **CFG-04**: When the API token becomes invalid (401), the integration
      triggers Home Assistant's reauth flow automatically.
- [x] **CFG-05**: User can configure integration options after setup (TLS
      verification, scan interval, certificate warning threshold).
- [x] **CFG-06**: User is shielded from "Updating Traefik failed" spam
      during transient API outages by surfacing `ConfigEntryNotReady` and
      retrying with backoff.

### API Client (API)

- [x] **API-01**: The integration connects to Traefik over HTTP using the
      shared HA `aiohttp.ClientSession` (never creates its own).
- [~] ~~**API-02**~~ _(superseded by DATA-02 (one `/api/rawdata` call per cycle))_: The integration calls `/api/version`, `/api/entrypoints`,
      `/api/http/routers`, `/api/http/services`, `/api/http/middlewares`,
      and `/api/overview` in parallel via `asyncio.gather`.
- [x] **API-03**: All API requests carry the bearer token in an
      `Authorization` header built per-request — never as a default header
      on a long-lived session.
- [x] **API-04**: The API client raises `TraefikAuthError` on HTTP 401 and
      `TraefikApiError` on other non-2xx responses — never logs the token.
- [~] ~~**API-05**~~ _(superseded by ENT-07 — Traefik has no refresh endpoint (audit A-04, M12))_: The API client can trigger `traefik.reload_routers` via
      `POST /api/http/routers/refresh` and report whether the refresh
      actually completed (Traefik returns 200 before reload finishes).
- [x] **API-06**: The API client supports HTTP and HTTPS targets, with
      optional TLS verification configurable per-entry.

### Coordinator (COORD)

- [x] **COORD-01**: Polling cycle completes in `≤10s` per fetch and runs on
      the HA event loop without blocking.
- [x] **COORD-02**: All parallel fetches wrapped in `asyncio.timeout(10)` so
      one slow endpoint does not stall the cycle.
- [x] **COORD-03**: Coordinator raises `ConfigEntryAuthFailed` on 401 and
      `UpdateFailed` on transient errors — the right exception determines
      whether the user sees reauth or retry.
- [x] **COORD-04**: First refresh awaited via
      `coordinator.async_config_entry_first_refresh()` in
      `async_setup_entry`, so initial state appears immediately on restart.

### Entities — Routers (CORE-04)

- [~] ~~**ROUTER-01**~~ _(superseded by ENT-04 (router ENUM sensor, M13))_: A `binary_sensor` exists for each Traefik router,
      with state `on` when the router is `enabled` and `off` when
      `disabled` or errored — `BinarySensorDeviceClass.RUNNING`.
- [x] **ROUTER-02**: Each router entity exposes the Traefik router `name`,
      friendly rule (first `Host(...)` match), and full `rule` as
      extra-state-attributes for dashboards and automations.
- [x] **ROUTER-03**: Traefik router names containing `@` are filtered at
      coordinator level (HA entity-ID regex rejects `@`).
- [x] **ROUTER-04**: Every router entity has a stable `unique_id` so
      re-setup does not duplicate entries.

### Entities — Entrypoints, Services, Overview (CORE-05, CORE-06, DIAG-01)

- [x] **ENTRY-01**: A `sensor` per Traefik entrypoint reports the
      listening address and current request count.
- [x] **ENTRY-02**: A `sensor` per Traefik service reports load-balancer
      status and backend server health (when healthcheck is configured).
- [x] **ENTRY-03**: An aggregate `sensor.traefik` reports the total
      number of routers, services, and middlewares.

### Entities — Diagnostics & Reload (DIAG-02, DIAG-03)

- [x] **DIAG-01**: A top-level `binary_sensor` becomes `on` when any
      router is reporting a non-`enabled` status — `BinarySensorDeviceClass.PROBLEM`.
- [~] ~~**DIAG-02**~~ _(superseded by ENT-07 ("Refresh now" button, M12))_: A `button` entity triggers the `Reload` button device
      class and posts a refresh to Traefik when pressed.
- [~] ~~**DIAG-03**~~ _(superseded by ENT-07 (service removed, M12))_: A `traefik.reload_routers` service is registered
      during `async_setup` (not `async_setup_entry`) and verifies reload
      completion via polling.

### Entities — TLS Certificate Expiry (TLS-01, TLS-02)

- [x] **TLS-01**: For every router terminating TLS, a `sensor` exposes
      the certificate's `notAfter` timestamp (with `device_class:
      timestamp`) and a `days_until_expiry` attribute.
- [x] **TLS-02**: For every TLS-enabled router, a `binary_sensor` turns
      `on` when the certificate is within the user-configurable warning
      threshold (default 14 days) — `BinarySensorDeviceClass.PROBLEM`.
- [ ] **TLS-03**: TLS fetches use a separate `CertCoordinator` with a
      6-hour cadence (not the 30s state cycle).
- [~] ~~**TLS-04**~~ _(superseded by CERT-02 (async probe without threads; problem-on instead of unavailable))_: TLS handshakes run via stdlib `ssl` inside
      `asyncio.to_thread`; failures mark the entity as `unavailable`
      rather than crashing the integration.
- [ ] **TLS-05**: TLS state caches per cycle to avoid hammering ports on
      large router counts; cadence is bounded by semaphore.

### Platform & UX (UX)

- [x] **UX-01**: Entities grouped under a single "Traefik" device with
      `sw_version` set from `/api/version`.
- [x] **UX-02**: Entities use HA's modern `_attr_has_entity_name=True`
      convention so the UI displays `<Device> <Entity Name>`.
- [x] **UX-03**: Stale entities (e.g. a router removed in Traefik) are
      pruned via `coordinator.async_add_listener` cleanup hook.
- [x] **UX-04**: All entities expose additional state attributes
      (Traefik IDs, rule excerpts, raw timestamps) so dashboards and
      automations can drill in.

### Distribution & Quality (DIST)

- [x] **DIST-01**: Integration ships with `manifest.json` registered for
      domain `traefik`, `hacs.json` ready for HACS, and `brand/` icon
      assets (`icon.png` 256×256, `icon@2x.png` 512×512).
- [x] **DIST-02**: `manifest.json` declares `homeassistant: "2025.4.0"`
      minimum and `"requirements": []` (HA Core bundles everything).
- [x] **DIST-03**: `manifest.json` deliberately omits `quality_scale`
      (hassfest blocks it for custom integrations).
- [x] **DIST-04**: GitHub Actions include `hassfest`, HACS Action, and
      pytest workflows; a release workflow fails when the tag does not equal
      the manifest `version` (Phase 8).
- [~] ~~**DIST-05**~~ _(dropped — hassfest ignores quality scale for custom integrations; IQS rules are a checklist only (M10))_: The integration targets **Bronze** quality scale for
      v1.0 and **Silver** as a stretch goal for v1.2.

### Documentation (DOCS-01)

- [x] **DOCS-01**: A `README.md` documents HACS install, manual install,
      every configuration option, and example dashboards / automations
      (including a "notify when a router goes down" pattern and a
      "warn me N days before TLS expiry" pattern).
- [x] **DOCS-02**: A `CHANGELOG.md` is added for the first release and
      updated on every release tag.
- [~] ~~**DOCS-03**~~ _(dropped — `info.md` is not used by the Marketplace; README is the information file (research §6 Q8))_: A `info.md` (HACS store card) summarizes the
      integration for the HACS browse view.
- [x] **DOCS-04**: An FAQ addresses the locked-out anti-features
      (config-file edits, ACME in HA, v1 Traefik, etc.) so users do not
      file duplicate issues.

### Testing (TEST-01)

- [x] **TEST-01**: Unit tests cover the API client (parsing, error paths,
      redaction safety) and the coordinator (poll cycle, exception
      mapping).
- [x] **TEST-02**: Integration tests using
      `pytest-homeassistant-custom-component` cover Config Flow
      (success, invalid auth, unreachable host), all entity platforms,
      options flow, reload service, and reauth flow.
- [x] **TEST-03**: A test fixture captures a realistic Traefik `/api/...`
      payload so integration tests stay hermetic.
- [x] **TEST-04**: TLS parsing tests cover ≥3 known `notAfter` format
      strings and ≥2 invalid format strings (graceful unavailable state).
      Satisfied by `tests/test_tls.py` (33 tests) + `tests/test_cert_coordinator.py` (19)
      + `tests/test_sensor_tls.py` (13) + `tests/test_binary_sensor_tls_expiring.py` (18)
      — Phase 3 plan 03-03 closed out the full TEST-04 surface with 83 new tests,
      suite 40 → 123 passing. Covered: 6 known + 5 invalid format strings, 24h
      log throttle, RFC 6125 wildcard SAN matching, graceful error paths (refused /
      dns / wrong-port), real mock-TLS handshake via openssl-driven asyncio server
      fixture.

### Diagnostics (DIAG-04)

- [x] **DIAG-04**: A `diagnostics.py` exports config-entry diagnostics
      (entry data, options, current snapshot) with `async_redact_data`
      stripping token, username, password and any other credential-shaped
      keys (Phase 7; audit U-16).

### Data layer (DATA) — Phase 4

- [x] **DATA-01**: API responses are parsed once, in the client, into frozen
      dataclasses in `models.py` (`Router`, `Service`, `Middleware`,
      `Entrypoint`, `TraefikVersion`, `TraefikSnapshot`) with a `Status`
      `StrEnum`; platforms never inspect raw API dicts. (A-10)
- [x] **DATA-02**: One scan cycle issues one request, `GET /api/rawdata`
      (unpaginated; routers, services incl. `serverStatus`, middlewares);
      `/api/version` and `/api/entrypoints` are fetched at setup; the version is
      re-checked at most hourly and after a failed cycle recovers, and
      entrypoints are re-fetched only when `version.StartDate` changed; if
      `/api/rawdata` is unavailable the
      client falls back to the paginated list endpoints and follows
      `X-Next-Page`. HTTP objects only; TCP/UDP data is ignored. (A-06, P-01)
- [x] **DATA-03**: The client supports auth modes none / basic (username +
      password) / bearer; the `Authorization` header is built per request and
      credentials never appear in logs or exception messages.
- [x] **DATA-04**: The client raises only subclasses of `TraefikProxyApiError`:
      `TraefikProxyAuthError` (401/403), `TraefikProxyNotFoundError` (404),
      `TraefikProxyConnectionError` (any `aiohttp.ClientError`, timeout,
      `OSError`) or `TraefikProxyPayloadError` (invalid JSON or shape);
      production code contains no `assert`.
      (A-15 client part, A-16)
- [x] **DATA-05**: `entry.runtime_data` is a typed `TraefikRuntimeData`
      dataclass holding client, coordinator and cert coordinator. (A-11)
- [x] **DATA-06**: The main coordinator returns a `TraefikSnapshot` with
      `dict[name, Model]` per kind and aggregates (counts per status, problem
      lists) computed once per cycle; `always_update=False`. (P-02)
- [x] **DATA-07**: Test fixtures are captured from local Docker Traefik v2.11
      and v3.x, redacted, and regenerable from a committed script; they cover
      providers, `error[]`, `serverStatus`, TLS domains and >100 items on the
      paginated path. (A-05, H-11)

### Entity model + lifecycle (ENT) — Phase 5

- [x] **ENT-01**: One entity manager per entry adds entities for new items on
      each coordinator update, marks vanished items `missing`, removes them from
      the registry after a 24 h grace period and re-binds items that reappear;
      it reads only `er.async_entries_for_config_entry`, never the whole
      registry. Used for routers, services and (Phase 6) certificates; cert
      entities are never re-added for known hosts. (A-02, A-03, A-08, A-14, P-04)
- [x] **ENT-02**: Per-item entities store only their key and read the current
      model from the snapshot on every update; state is written only when the
      entity's model changed; redundant `available` overrides are removed.
      (A-01, A-20, P-03)
- [x] **ENT-03**: Entity bases `TraefikEntity` and `TraefikCertEntity`
      (subscribed to the cert coordinator) share one `DeviceInfo` factory: main
      device `Traefik (<host>)` with `entry_type=SERVICE`,
      `configuration_url=<url>/dashboard/` and `sw_version` kept current;
      sub-devices Routers / Services / Certificates linked to it via the
      registry `via_device_id` (no deprecated `DeviceInfo.via_device`). (A-07,
      A-21, U-04)
- [x] **ENT-04**: Routers and services are `sensor` entities with
      `device_class=enum` (`enabled`, `warning`, `error`, `disabled`,
      `missing`); services expose `servers_up`/`servers_total` (no URLs/IPs);
      each attribute has one canonical key. (U-07, U-08, S-06, P-09)
- [x] **ENT-05**: Problem aggregates `routers_problem`, `services_problem`,
      `middlewares_problem` (binary_sensor, `problem`) are enabled by default
      and implemented as one class plus entity descriptions. (U-01, A-13)
- [x] **ENT-06**: Counts, version, Traefik start time, entrypoints and an
      optional healthy-ratio sensor carry `EntityCategory.DIAGNOSTIC`;
      entrypoints and healthy ratio are disabled by default. (U-05, U-06, U-15)
- [x] **ENT-07**: The reload button, the `reload_routers` service,
      `services.yaml` and the client refresh method are removed; a "Refresh
      now" button refreshes both coordinators of its own entry and needs no
      admin bypass. (A-04, A-09, S-08)
- [x] **ENT-08**: Static entity names use `translation_key` with entity
      strings in `en.json` and `de.json`; `icons.json` provides default and
      state icons; every platform sets `PARALLEL_UPDATES`. (U-02)
- [x] **ENT-09**: Upgrading from 0.3.0 removes the old router/service
      `binary_sensor` and reload-button registry entries in a config-entry
      migration and shows a non-fixable, persistent repair notice (HA 2026.11
      issue API bound to the entry via `config_entry_id=entry.entry_id`) that
      the user dismisses and that Home Assistant deletes when the entry is
      removed (amended by M34: not deleted on unload).
- [x] **ENT-10**: The option "create per-router/per-service entities"
      (default on) is honoured; when off, no per-router or per-service entity
      exists (aggregate, diagnostic and certificate entities remain) and
      existing per-router/per-service entities are removed.

### Certificates (CERT) — Phase 6

- [x] **CERT-01**: On Traefik ≥ 3.7 certificate data comes from
      `GET /api/certificates` (`source=api`, no probing); a 404 or older version
      falls back to probing. (T-01)
- [x] **CERT-02**: The fallback probe is native async
      (`asyncio.open_connection`, no threads), uses one shared `SSLContext` with
      `CERT_NONE`, parses the DER certificate with `cryptography`, connects to
      the Traefik host from the entry URL on the TLS entrypoint port with
      SNI = router host, reports `verified`, and classifies `ssl` vs `oserror`
      correctly. (T-01, T-02, P-05, P-06, S-05)
- [x] **CERT-03**: `rules.py` `extract_hosts()` handles v2 multi-argument
      `Host()` and v3 `||` rules and skips regex and wildcard hosts; at most 200
      hosts are probed; no module-level cache grows without bound. (A-12, P-07,
      P-08, S-07)
- [x] **CERT-04**: Wildcard SAN matching accepts exactly one label
      (RFC 6125 §6.4.3). (S-04)
- [x] **CERT-05**: `days_left` is computed from `not_after` at read time; an
      expired or repeatedly unprobeable certificate turns `certificate_expiring`
      and the `certificates_problem` aggregate (enabled by default) on with a
      `reason`, while the timestamp sensor keeps its last value. (U-09, U-10)

### Config flow, HA 2026.11 baseline, observability (FLOW) — Phase 7

- [x] **FLOW-01**: User, reauth and reconfigure steps offer an auth selector
      (none / basic / bearer) with `PASSWORD` selectors and per-field
      `data_description`; a minor-version config-entry migration converts 0.3.0
      data (token → bearer, empty → none); choosing "none" clears credentials.
      (U-03, U-11, S-03)
- [x] **FLOW-02**: No update listener remains; the options flow is an
      `OptionsFlowWithReload` with `NumberSelector`s (units, box mode), the
      per-item-entities toggle and the missing-entity grace period (1–168 h,
      default 24 h; I7). (A-17, S-01, U-12, W36)
- [x] **FLOW-03**: Reauth and reconfigure finish through
      `async_update_reload_and_abort`; the config-entry unique_id is
      `host:port` (migrated) and follows a reconfigure; the title is the host.
      (A-22, S-02)
- [x] **FLOW-04**: A 404 maps to `api_disabled`; every flow error path is
      tested (config_flow.py 100 % line coverage). (A-15 flow part)
- [x] **FLOW-05**: `ConfigEntryAuthFailed`, `ConfigEntryNotReady` and
      `UpdateFailed` use `translation_domain`/`translation_key` with an
      `exceptions` section in the translations. (research §4.2)
- [x] **FLOW-06**: A repair issue is raised for an `http://` URL combined with
      credentials and is deleted when resolved or when the entry unloads, using
      the HA 2026.11 issue-registry API with `config_entry_id` (I1 supersedes
      M4). (research §4.6)
- [x] **FLOW-07**: `strings.json`, the YAML step and its strings, and the dead
      code from audit A-18 are removed; `translations/en.json` is the single
      source and `translations/de.json` has full key parity (tested). (A-18,
      U-13, U-14, M7)

- [x] **FLOW-08**: The minimum Home Assistant is 2026.11.0 (`hacs.json`,
      test floor, CI job pinned to 2026.11.0); sub-devices link through the
      2026.11 device API instead of the registry workaround, repairs carry
      `config_entry_id`, unload uses `async_unload_platforms_or_raise`, and no
      private HA attribute is read. (I1, research §4.2/§4.6/§5)

### Marketplace + release readiness (REL) — Phase 8

- [x] **REL-01**: `manifest.json` has `categories:
      ["computers_network.monitoring"]` (sorted keys) and version `1.0.0`;
      `hacs.json` keeps `homeassistant: 2026.11.0`. (research §2)
- [x] **REL-02**: Brand icons are re-exported trimmed and centred, `logo.png`
      / `logo@2x.png` are added, `icon.svg` moves to `docs/`, local brand
      serving is confirmed for HA 2026.11.0, and the README carries the Traefik
      trademark note. (B-01..B-06, research §3)
- [x] **REL-03**: README is rewritten (Marketplace/My-link badge,
      prerequisites incl. protecting the Traefik API, install/removal, options,
      entity table matching the code, automations, troubleshooting, data update
      cadence, known limitations) with no private hostnames. (H-01, H-02)
- [x] **REL-04**: Dev tooling is consistent: pre-commit on Python 3.14 and
      `traefik_proxy` paths, pyproject project name + coverage target +
      `fail_under`, Makefile aligned with CI, no test `SyntaxWarning`, no real
      multi-second sleeps in tests. (H-03, H-04, H-09, H-10, H-12)
- [x] **REL-05**: CI runs on push, PR, nightly schedule and manual dispatch,
      includes the test job against HA 2026.11.x added in Phase 7, and pins all actions by tag or
      SHA. (H-05, M9, M24)
- [x] **REL-06**: Shipped code contains no planning references (CONTEXT.md,
      PITFALLS, D-xx, BLOCKER, phase/plan numbers, `.planning/`, `.claude/`
      paths); CLAUDE.md stack section and skill routing match the
      `traefik_proxy` domain and the renamed skill; developer-doc links point
      at contributors.home-assistant.io. (A-19, H-07, H-08, research §6 Q7)
- [ ] **REL-07**: Local hassfest and `hacs/action` (no `ignore`) pass;
      release notes and the `hacs/default` PR text are drafted in `.planning/`.
      (research §2, M8)
- [ ] **REL-08**: `feat/marketplace-polish` is pushed and a Draft PR to `main`
      is open; no tag, release or `hacs/default` PR is created by the assistant.
      (U1)

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Routing

- **ROUTER-V2-01**: Per-router transport security / TLS version attributes
- **ROUTER-V2-02**: Per-router `using` array (chain of middlewares)
  visualized in the UI
- **ROUTER-V2-03**: Per-backend server health attributes (only valuable
  when Traefik server-side `healthcheck` is configured)

### TLS

- **TLS-V2-01**: TLS chain validation (intermediates, SAN match)
- **TLS-V2-02**: Show chain trust path per certificate
- **TLS-V2-03**: TLS subject/issuer attributes in addition to expiry

### Operations

- **OPS-V2-01**: Switch entities to toggle per-router status (requires
  Traefik to add an enable/disable endpoint)
- **OPS-V2-02**: Per-middleware entities (middlewares are config-time
  constructs with no runtime state — value is dubious)
- **OPS-V2-03**: WebSocket streaming for live updates (sub-second state;
  adds reconnect/diff complexity)
- **OPS-V2-04**: TCP/UDP router+service entities (PROJECT.md HTTP-only)
- **OPS-V2-05**: Traefik v1 compatibility (EOL since 2021)
- **OPS-V2-06**: Auto-discovery via zeroconf / DHCP (Traefik does not
  advertise)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Mutating Traefik dynamic-config files on disk | Traefik dashboard already exists; race conditions between provider and file writes; dangerous default |
| Auto-provisioning TLS certificates (ACME/LE) inside HA | Traefik owns the cert lifecycle; the integration only surfaces expiry |
| A built-in web UI for editing Traefik routes | Out of scope — Traefik dashboard exists; duplicating UI is wasted effort |
| Traefik v1 support | EOL since 2021; two API shapes would double the maintenance surface |
| Traefik Enterprise / cloud-managed Traefik | Only OSS reverse proxy is targeted |
| Visualising the `/api/rawdata` dependency graph | `/api/rawdata` is used as the data source (DATA-02), but drawing the router→middleware→service graph has unclear value; defer until user feedback |
| Reading `acme.json` from disk | Coupling to Traefik's internal file layout; TLS handshake works without it |
| Per-middleware entities | Middlewares are config-time constructs with no runtime state to expose |
| TCP/UDP router+service entities | PROJECT.md explicitly HTTP-only; TCP uses a different API surface |
| Integration service actions (reload or otherwise) | The Traefik API is read-only; the "Refresh now" button covers manual refresh (M12). Research §4.4 (action-setup, response data, action exceptions, service translations) is therefore moot |
| `quality_scale.yaml` / manifest `quality_scale` | hassfest skips it for custom integrations; IQS rules are used as a checklist only (M10) |
| Probatio migration (`import probatio`) | Done in Phase 7: `config_flow.py` imports `probatio as vol` (HA aliases `voluptuous` to Probatio since 2026.9, research §4.7); nothing further planned |
| Option "probe certificates via DNS" | Probing via the Traefik host with SNI is the only correct path behind CDNs/split DNS (M19); a DNS mode would re-introduce audit T-02 |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CFG-01 | Phase 1 | Complete |
| CFG-02 | Phase 1 | Superseded |
| CFG-03 | Phase 2 | Complete |
| CFG-04 | Phase 2 | Complete |
| CFG-05 | Phase 2 | Complete |
| CFG-06 | Phase 1 | Complete |
| API-01 | Phase 1 | Complete |
| API-02 | Phase 1 | Superseded |
| API-03 | Phase 1 | Complete |
| API-04 | Phase 1 | Complete |
| API-05 | Phase 2 | Superseded |
| API-06 | Phase 1 | Complete |
| COORD-01 | Phase 1 | Complete |
| COORD-02 | Phase 1 | Complete |
| COORD-03 | Phase 1 | Complete |
| COORD-04 | Phase 1 | Complete |
| ROUTER-01 | Phase 1 | Superseded |
| ROUTER-02 | Phase 2 | Complete (refined by ENT-04) |
| ROUTER-03 | Phase 2 | Complete |
| ROUTER-04 | Phase 1 | Complete |
| ENTRY-01 | Phase 2 | Complete (refined by ENT-06) |
| ENTRY-02 | Phase 2 | Complete (refined by ENT-04) |
| ENTRY-03 | Phase 2 | Complete (refined by ENT-05/06) |
| DIAG-01 | Phase 2 | Complete |
| DIAG-02 | Phase 2 | Superseded |
| DIAG-03 | Phase 2 | Superseded |
| DIAG-04 | Phase 7 | Complete |
| TLS-01 | Phase 3 | Complete (refined by CERT-01/05) |
| TLS-02 | Phase 3 | Complete (refined by CERT-05) |
| TLS-03 | Phase 3 | Complete |
| TLS-04 | Phase 3 | Superseded |
| TLS-05 | Phase 3 | Complete |
| UX-01 | Phase 1 | Complete (refined by ENT-03) |
| UX-02 | Phase 1 | Complete |
| UX-03 | Phase 2 | Complete (refined by ENT-01) |
| UX-04 | Phase 2 | Complete |
| DIST-01 | Phase 1 | Complete |
| DIST-02 | Phase 1 | Complete |
| DIST-03 | Phase 1 | Complete |
| DIST-04 | Phase 8 | Complete |
| DIST-05 | — | Superseded |
| DOCS-01 | Phase 1 | Complete |
| DOCS-02 | Phase 8 | Complete |
| DOCS-03 | — | Superseded |
| DOCS-04 | Phase 8 | Complete |
| TEST-01 | Phase 1 | Complete |
| TEST-02 | Phase 2 | Complete |
| TEST-03 | Phase 1 | Complete (refined by DATA-07) |
| TEST-04 | Phase 3 | Complete |
| DATA-01 | Phase 4 | Complete |
| DATA-02 | Phase 4 | Complete |
| DATA-03 | Phase 4 | Complete |
| DATA-04 | Phase 4 | Complete |
| DATA-05 | Phase 4 | Complete |
| DATA-06 | Phase 4 | Complete |
| DATA-07 | Phase 4 | Complete |
| ENT-01 | Phase 5 | Complete |
| ENT-02 | Phase 5 | Complete |
| ENT-03 | Phase 5 | Complete |
| ENT-04 | Phase 5 | Complete |
| ENT-05 | Phase 5 | Complete |
| ENT-06 | Phase 5 | Complete |
| ENT-07 | Phase 5 | Complete |
| ENT-08 | Phase 5 | Complete |
| ENT-09 | Phase 5 | Complete |
| ENT-10 | Phase 5 | Complete |
| CERT-01 | Phase 6 | Complete |
| CERT-02 | Phase 6 | Complete |
| CERT-03 | Phase 6 | Complete |
| CERT-04 | Phase 6 | Complete |
| CERT-05 | Phase 6 | Complete |
| FLOW-01 | Phase 7 | Complete |
| FLOW-02 | Phase 7 | Complete |
| FLOW-03 | Phase 7 | Complete |
| FLOW-04 | Phase 7 | Complete |
| FLOW-05 | Phase 7 | Complete |
| FLOW-06 | Phase 7 | Complete |
| FLOW-07 | Phase 7 | Complete |
| FLOW-08 | Phase 7 | Complete |
| REL-01 | Phase 8 | Complete |
| REL-02 | Phase 8 | Complete |
| REL-03 | Phase 8 | Complete |
| REL-04 | Phase 8 | Complete |
| REL-05 | Phase 8 | Complete |
| REL-06 | Phase 8 | Complete |
| REL-07 | Phase 8 | Pending (first PR CI run, M43) |
| REL-08 | Phase 8 | Pending |

**Coverage:**
- v1 requirements: 87 rows — 78 active (76 complete, 2 pending) + 9 superseded/dropped
- Mapped to phases: 78 / 78 active
- Unmapped: 0 ✓

## Audit traceability

Every finding in `.planning/research/AUDIT-ARCH-PERF-UX.md` and every
actionable item in `.planning/research/MARKETPLACE-BEST-PRACTICES.md` maps to
exactly one phase (A-15 is split into its client and flow halves).

| Phase | Audit / research items | Requirements |
|-------|------------------------|--------------|
| 4 — Data layer | A-05, A-06, A-10, A-11, A-15 (client: `TraefikProxyNotFoundError` + flow re-wired to it), A-16, P-01, P-02, H-11; research §4.2 `always_update=False`, `_async_setup` | DATA-01..07 |
| 5 — Entity model + lifecycle | A-01, A-02, A-03, A-04, A-07, A-08, A-09, A-13, A-14, A-20, A-21, P-03, P-04, P-09, U-01, U-02, U-04, U-05, U-06, U-07, U-08, U-15, S-06, S-08; research §4.3 (has-entity-name, icon-translations, entity-category, parallel-updates, dynamic/stale devices, DeviceInfo kwargs only), §5 DeviceInfo dataclass / `DeviceEntry.config_entries` | ENT-01..10 |
| 6 — Certificates | A-12, P-05, P-06, P-07, P-08, U-09, U-10, S-04, S-05, S-07, T-01, T-02 | CERT-01..05 |
| 7 — Config flow / 2026.11 baseline / observability | A-15 (flow: full error-path test matrix + translated `api_disabled` text), A-17, A-18, A-22, U-03, U-11, U-12, U-13, U-14, U-16, S-01, S-02, S-03; research §4.1, §4.2 translated `UpdateFailed`, §4.5, §4.6 (diagnostics, repairs), §5 2026.6→2026.12 listener deprecation, research summary items 6–7 (listener leak), 9 | FLOW-01..08, DIAG-04 |
| 8 — Marketplace + release | A-19, B-01, B-02, B-03, B-04, B-05, B-06, H-01, H-02, H-03, H-04, H-05, H-06, H-07, H-08, H-09, H-10, H-12; research §2 (categories, CI triggers, release, catalog PR text, My-link badge), §3 brand, §4.6 `docs-*` rules + coverage gate, §6 Q1 (tag prefix), Q7 (doc URLs), Q8 (`info.md`) | REL-01..08, DIST-04, DOCS-02, DOCS-04 |
| Out of scope | research §4.4 service actions + research summary item 8 (`supports_response`) — moot, services removed in Phase 5; §4.7 Probatio — adopted in Phase 7 (`import probatio as vol`); §5 `UNDEFINED`, `ATTR_*` constants — not used (D-09) | — |

---
*Requirements defined: 2026-07-05*
*Last updated: 2026-11-15 — 08-12: ENT-09 names the 2026.11 `config_entry_id` repair API, Probatio row reflects Phase 7, coverage footer recounted*
