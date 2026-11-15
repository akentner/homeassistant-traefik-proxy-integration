# Roadmap: Home Assistant Traefik Integration

## Overview

A HACS-distributable custom HA integration that polls the Traefik v2/v3 HTTP API
and surfaces reverse-proxy state (routers, services, entrypoints, TLS cert expiry)
as native HA entities. The journey walks a strict architectural dependency chain
(`const → api → coordinator → entity → config_flow → init → platforms`), proves
the polling loop with the Core Value (per-router binary_sensor) first, layers in
the remaining table-stakes surfaces (entrypoints, services, options, reauth,
reload), then attacks the killer differentiator (TLS cert expiry via out-of-band
stdlib TLS handshake), and finishes with quality polish, diagnostics redaction,
and HACS publication. After the 2026-11 marketplace research and code audit,
the remaining work was re-cut into Phases 4–8: fix the data layer against the
real Traefik API, rebuild the entity lifecycle, redo certificates, modernise
the flows on an HA 2026.11 baseline (2026.12-safe), then ship 1.0.0 through the Marketplace.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation** — Scaffold `custom_components/traefik/`, Config Flow (completed 2026-07-05)
      + YAML, Coordinator, first router binary_sensor, HACS manifest
- [x] **Phase 2: Core Entities + Options + Reauth + Reload** — Entrypoint / (completed 2026-07-05)
      Service / Overview sensors, Options Flow, reauth + reconfigure, reload
      service + button, stale entity cleanup
- [x] **Phase 3: TLS Certificate Expiry** — Spike → `tls.py` + `CertCoordinator` (completed 2026-07-06)
      → per-router cert timestamp sensor + expiring binary_sensor (6-hour cadence)
      → TEST-04 test surface (123 tests passing)

- [x] **Phase 4: Data layer (correct + lean)** — typed models, one `GET /api/rawdata` (completed 2026-11-14)
      per cycle, auth modes + error taxonomy in the client, real Traefik fixtures,
      `TraefikRuntimeData`, snapshot coordinator with precomputed aggregates
- [x] **Phase 5: Entity model + lifecycle** — entity manager (add / missing / 24 h (completed 2026-11-15)
      grace / re-add), main device + sub-devices, router/service ENUM sensors,
      problem aggregates on by default, "Refresh now" button, translations + icons
- [x] **Phase 6: Certificates** — `/api/certificates` on Traefik ≥ 3.7, async (completed 2026-11-15)
      threadless probe (CERT_NONE + DER parse) via the Traefik host with SNI,
      `rules.py`, live `days_left`, problem-on instead of unavailable
- [x] **Phase 7: Config flow, HA 2026.11 baseline, observability** — auth (completed 2026-11-15)
      selector + entry migration, minimum HA 2026.11.0 + 2026.11 APIs, grace-period option, `OptionsFlowWithReload`, reauth/reconfigure
      helpers, `host:port` unique_id, diagnostics, repairs, en/de translations
- [ ] **Phase 8: Marketplace + release readiness** — manifest categories, brand
      re-export, README/CHANGELOG, CI + tooling fixes, planning-reference sweep,
      version 1.0.0, local validation, Draft PR

**Milestone v1.0 restructure (2026-11-14):** the original Phase 4 ("Quality +
Diagnostics + Polish + HACS", never started) was replaced by Phases 4–8 after
the marketplace research and the code audit
(`.planning/research/MARKETPLACE-BEST-PRACTICES.md`,
`.planning/research/AUDIT-ARCH-PERF-UX.md`). Every audit/research item is mapped
to exactly one phase in REQUIREMENTS.md → "Audit traceability". Cross-phase
gates for Phases 4–8: `pytest`, `ruff check`, `ruff format --check` and
`mypy --strict custom_components/traefik_proxy` stay green after every plan,
and the minimum Home Assistant stays **2026.3.0** (no 2026.11-only APIs) up to
Phase 6; Phase 7 raises it to **2026.11.0** (user decision I1) and from then on
the gate runs against HA 2026.11.x.

## Phase Details

### Phase 1: Foundation

**Goal**: Users can install the integration from HACS (or by copying
`custom_components/traefik/`), complete the config flow, and see one
`binary_sensor` per Traefik router under a single "Traefik" device.
**Depends on**: Nothing (first phase)
**Requirements**: CFG-01, CFG-02, CFG-06, API-01, API-02, API-03, API-04, API-06,
COORD-01, COORD-02, COORD-03, COORD-04, ROUTER-01, ROUTER-04, UX-01, UX-02,
DIST-01, DIST-02, DIST-03, DOCS-01, TEST-01, TEST-03 (22 requirements)
**Success Criteria** (what must be TRUE):

  1. User can install the integration via HACS (or manually), restart HA, and
     complete the UI config flow by entering the Traefik base URL, bearer token,
     and `verify_ssl` option; alternatively place a YAML entry in
     `configuration.yaml`. The integration registers under a single "Traefik"
     device in HA's device registry.

  2. The integration exposes one `binary_sensor.<router_name>` per Traefik
     router with `_attr_has_entity_name=True` so the UI displays
     `Traefik <Router Name>`; state is `on` when the router is `enabled` and
     `off` when `disabled` or errored; `unique_id` is stable so re-setup does
     not duplicate entries.

  3. Initial router state appears immediately after HA restart because
     `coordinator.async_config_entry_first_refresh()` is awaited inside
     `async_setup_entry`; polling completes inside one event-loop tick without
     blocking, with a configured scan interval (default 30s) and
     `asyncio.timeout(10)` wrapping every cycle.

  4. Transient API outages surface as `ConfigEntryNotReady` with backoff (no
     log spam); an invalid bearer token (HTTP 401) raises
     `ConfigEntryAuthFailed` so HA marks the entry for reauth instead of
     showing endless "Updating Traefik failed" messages.

  5. The package ships with `manifest.json` (no `quality_scale` key —
     hassfest blocks it for custom integrations), `hacs.json`, brand icons
     (`brand/icon.png` + `icon@2x.png`), a `pyproject.toml`, and a `README.md`
     documenting the HACS install path; `hassfest` validation passes.
**Plans**: 4 plans (scaffold → coordinator+entity+__init__ → config_flow+router entity+docs → tests+CI)

Plans:

- [x] 01-01: Project scaffold (manifest.json, hacs.json, const.py, brand/, pyproject.toml, .gitignore, LICENSE, ruff config)
- [x] 01-02: api.py + coordinator.py + entity.py + __init__.py (DataUpdateCoordinator, runtime_data, async_setup_entry, first_refresh)
- [x] 01-03: config_flow.py (UI config + YAML step) + binary_sensor platform for first router entity + README skeleton
- [x] 01-04: Unit tests (TraefikApiClient parsing + error paths), fixture capture, hassfest validation in CI

### Phase 2: Core Entities + Options + Reauth + Reload

**Goal**: Users can configure integration options without re-adding the entry,
reauthenticate when the bearer token changes, and see per-entrypoint,
per-service, aggregate-overview, any-router-failing, and reload entities in
addition to the per-router binary_sensor from Phase 1.
**Depends on**: Phase 1
**Requirements**: CFG-03, CFG-04, CFG-05, API-05, ROUTER-02, ROUTER-03,
ENTRY-01, ENTRY-02, ENTRY-03, DIAG-01, DIAG-02, DIAG-03, UX-03, UX-04,
TEST-02 (15 requirements)
**Success Criteria** (what must be TRUE):

  1. User can open integration Options after setup to change scan interval
     (clamped 15s–5min), TLS verification, certificate warning threshold, and
     the Traefik base URL — without removing and re-adding the entry; the
     coordinator restarts on option change via `entry.add_update_listener`.

  2. When the bearer token rotates, HA presents the reauth flow automatically;
     when the user needs to point the integration at a new Traefik host, the
     reconfigure flow updates the entry in place (no delete+re-add).

  3. The integration exposes one `sensor` per Traefik entrypoint (reporting
     listening address + current request count), one `sensor` per Traefik
     service (load-balancer status + backend server health when a healthcheck
     is configured), and an aggregate `sensor.traefik` reporting the total
     counts of routers, services, and middlewares.

  4. The integration exposes a "Reload" `button` entity and a
     `traefik.reload_routers` HA service that posts
     `/api/http/routers/refresh` and waits for the reload to actually complete
     (Traefik returns 200 before providers finish reloading, so the service
     polls `/api/http/routers` to verify before returning).

  5. Each router binary_sensor exposes the Traefik router `name`, the first
     `Host(...)` match as a friendly rule hint, and the full `rule` as
     extra-state attributes; Traefik names containing `@<provider>` (e.g.
     `api@internal`, `strip@docker`) are filtered out at coordinator level
     (HA's entity-ID regex rejects `@`); routers removed in Traefik are
     pruned from HA via `coordinator.async_add_listener` cleanup hook.
**Plans**: 4 plans in 3 waves

Plans:

- [x] 02-01: Foundation — TraefikEntity multi-device refactor + new api.py endpoints + filter_internal_items + TraefikData TypedDict + const.py extension
- [x] 02-02: Config Flow — OptionsFlow + Reauth + Reconfigure + entry.add_update_listener + translation bundle updates
- [x] 02-03: Entities — sensor.py (entrypoint + service + 3 aggregates) + button.py (reload) + binary_sensor.py (any-router-failing)
- [x] 02-04: Service + Stale Cleanup + Tests — module-level async_setup + reload handler with polling verification + stale entity cleanup listeners + integration tests
- [ ] 02-04: Stale entity cleanup via coordinator.async_add_listener + @<provider> filtering + integration tests with pytest-homeassistant-custom-component

### Phase 3: TLS Certificate Expiry

**Goal**: Users can see — for every Traefik router terminating TLS — a Home
Assistant timestamp sensor for the certificate's `notAfter` and a
`binary_sensor` that turns `on` when the cert is within the configured warning
threshold (default 14 days).
**Depends on**: Phase 2
**Pre-phase activity**: Run `gsd-spike` against 3+ real Traefik v2/v3
deployments before planning Phase 3 — validate stdlib `ssl` handshake handles
SNI routing, multi-cert chains, wildcard certs, and that the format-string
loop covers all observed `notAfter` shapes. Spike deliverable: spike document

+ `tls.py` prototype with tests. (Strongly flagged in

`research/SUMMARY.md`.)
**Requirements**: TLS-01, TLS-02, TLS-03, TLS-04, TLS-05, TEST-04
(6 requirements)
**Success Criteria** (what must be TRUE):

  1. For every Traefik router with `tls` set, the integration exposes a
     `sensor.<host>` reporting the certificate's `notAfter` timestamp
     (`device_class: timestamp`) and a `days_until_expiry` attribute that
     decreases monotonically as the cert approaches expiry.

  2. For every TLS-enabled router, the integration exposes a
     `binary_sensor.<host>_expiring` that turns `on` when
     `days_until_expiry ≤ user-configurable warning threshold (default 14)`
     with `BinarySensorDeviceClass.PROBLEM`; turning the threshold in
     integration options immediately re-evaluates the entities.

  3. TLS handshakes run on a separate `CertCoordinator` (not the main
     state coordinator) with a 6-hour cadence, bounded by a semaphore so
     large router counts do not hammer the host network all at once;
     results are cached per cycle so a slow router does not stall others.

  4. Any TLS error — unreachable host, timeout, format-string mismatch,
     SNI mismatch, IPv6 failure — marks the corresponding entity
     `unavailable` and lets the rest of the integration keep working; the
     integration never crashes from a TLS failure. The actual TLS socket
     work runs via `asyncio.to_thread` so the HA event loop stays
     responsive.

  5. Unit tests cover ≥3 known `notAfter` format strings (e.g.
     `Nov 15 12:00:00 2025 GMT`, `Nov 15 12:00:00 2025+00:00`, ISO-style)
     and ≥2 invalid format strings (graceful `unavailable` mapping); a mock
     TLS handshake exercises the cache + semaphore + timeout paths.
**Plans**: 3 plans in 3 waves

Plans:
**Wave 1**

- [x] 03-01: tls.py + cert_coordinator.py + integration wiring (sibling attach on entry.runtime_data, threshold live re-eval) — TLS-03/04/05

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 03-02: TraefikCertTimestampSensor + TraefikCertExpiryBinarySensor + stale-cleanup listeners wired to cert_coordinator — TLS-01/02

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 03-03: TEST-04 tests — test_tls.py (format-string parse + graceful error + log throttle), test_cert_coordinator.py (semaphore + timeout + threshold + hostname union), test_sensor_tls.py + test_binary_sensor_tls_expiring.py (entity state derivation + D-04 contract pin) — completed 2026-07-06 (83 new tests, suite 40 → 123 passing, ruff+mypy+pytest clean)

### Phase 4: Data layer (correct + lean)

**Goal**: The integration reads the **real** Traefik v2.11 / v3.x API shape
correctly and cheaply: one `GET /api/rawdata` per scan cycle is parsed once at
the client boundary into frozen, typed models, and the coordinator hands every
consumer a `TraefikSnapshot` with per-name lookups and precomputed aggregates —
proven against fixtures captured from real Traefik containers, not hand-written
JSON. User-visible entities keep working unchanged on top of the new data layer
(the entity rework is Phase 5).
**Depends on**: Phase 3
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06, DATA-07
**Audit items**: A-05, A-06, A-10, A-11, A-15 client part, A-16, P-01, P-02, H-11
**Success Criteria** (what must be TRUE):

  1. `tests/fixtures/` contains redacted responses captured from local Docker
     Traefik **v2.11** and **v3.x** (`/api/rawdata`, `/api/version`,
     `/api/entrypoints`, paginated list pages with `X-Next-Page`), including
     `@docker`/`@file`/`@internal` providers, a router with `error[]`, a
     service with `serverStatus` UP and DOWN, a TLS router with `tls.domains`,
     and more than 100 routers on the paginated path; the capture script and
     compose file are committed so fixtures can be regenerated; no private
     hostname, IP or credential appears in any fixture.
  2. `custom_components/traefik_proxy/models.py` defines frozen dataclasses
     (`Router`, `Service`, `Middleware`, `Entrypoint`, `TraefikVersion`,
     `TraefikSnapshot`) and a `Status` `StrEnum`; parsing both fixture
     generations yields identical model semantics (e.g. `Service.servers_up` /
     `servers_total` from `serverStatus`, overview counts from objects), and
     no platform module performs `isinstance` shape checks on raw API dicts.
  3. With default options, one scan cycle issues exactly **one** HTTP request
     (`GET /api/rawdata`); `/api/version` and `/api/entrypoints` are fetched at
     setup; `/api/version` is re-checked at most once per hour and after a
     failed cycle recovers, and `/api/entrypoints` is re-fetched only when
     `version.StartDate` changed (Traefik restart); when
     `/api/rawdata` is unavailable the client falls back to the paginated list
     endpoints and follows `X-Next-Page` until exhaustion (no truncation at
     100) — all asserted by request-counting tests.
  4. The client supports auth modes **none / basic / bearer** (header built per
     request, credentials never logged or included in exception text) and
     raises only subclasses of `TraefikProxyApiError`: `TraefikProxyAuthError`
     (401/403), `TraefikProxyNotFoundError` (404), `TraefikProxyConnectionError`
     (any `aiohttp.ClientError`, timeout, OS error) or `TraefikProxyPayloadError`
     (invalid JSON / unexpected shape); the package
     contains no `assert` statements in production code; the coordinator maps
     these to `ConfigEntryAuthFailed` / `UpdateFailed`.
  5. `entry.runtime_data` is a typed `TraefikRuntimeData` dataclass
     (`client`, `coordinator`, `cert_coordinator`) with no `getattr(..., None)`
     lookups left; the main coordinator uses `always_update=False` and listeners
     do not fire when two consecutive snapshots are equal; the full test suite,
     `ruff` and `mypy --strict` are green and the existing entity set still
     reports correct states on both fixture generations.
**Plans**: 9/9 plans complete (6 executed in 5 waves; 3 gap-closure plans in 2 waves)

Plans:
**Wave 1**
- [x] 04-01-PLAN.md — Docker capture harness + redacted, digest-pinned v2.11/v3.7 fixtures with privacy and scenario guards (DATA-07)
- [x] 04-02-PLAN.md — Typed `TraefikRuntimeData` (client, coordinator, cert_coordinator), single client owner (DATA-05)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 04-03-PLAN.md — Frozen typed models parsed from both payload shapes, proven equal on both real generations; single fixture loader (DATA-01)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 04-04-PLAN.md — Tracer: real pages -> models -> client -> `TraefikSnapshot` coordinator (`always_update=False`) -> all consumers; paginated reads (DATA-01, DATA-06, DATA-02)

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 04-05-PLAN.md — Client contract: auth none/basic/bearer, error taxonomy, no asserts, config-flow D-11 mapping, synthetic fixtures deleted (DATA-03, DATA-04, DATA-07)

**Wave 5** *(blocked on Wave 4 completion)*
- [x] 04-06-PLAN.md — One `GET /api/rawdata` per cycle + paginated fallback, restart detection, request-budget matrix, real-fixture entity proof (DATA-02, DATA-07)

**Gap closure** (04-VERIFICATION.md; M26, M27)

**Gap wave 1**
- [x] 04-07-PLAN.md — CR-01: cert entities bound to the cert coordinator; full-setup HA-state tests for cert cycle, threshold, options and availability (DATA-06, SC5)
- [x] 04-08-PLAN.md — WR-02: aiohttp request-construction `ValueError` mapped to `TraefikProxyInvalidUrlError`; userinfo URLs rejected in the config flows (DATA-04)

**Gap wave 2** *(blocked on 04-08: shares `api.py`)*
- [x] 04-09-PLAN.md — WR-01 / M27: paginated fallback revocable on the hourly version re-check, at most one extra rawdata request per hour; D-07 amended (DATA-02)

### Phase 5: Entity model + lifecycle

**Goal**: Router, service and problem entities reflect live Traefik state for
the lifetime of the config entry: new items appear without a reload, vanished
items go `missing` and are removed only after a 24 h grace period, states update
on every change (and only on change), and the entity/device model is readable,
translated (en/de) and categorised — with the never-working reload feature
replaced by a "Refresh now" button and existing installs migrated cleanly.
**Depends on**: Phase 4
**Requirements**: ENT-01, ENT-02, ENT-03, ENT-04, ENT-05, ENT-06, ENT-07, ENT-08, ENT-09, ENT-10
**Audit items**: A-01..A-04, A-07..A-09, A-13, A-14, A-20, A-21, P-03, P-04, P-09, U-01, U-02, U-04..U-08, U-15, S-06, S-08
**Carry-over (Phase 4 review, `04-REVIEW.md`)**: WR-04 (a paginated read can silently drop items that move between pages; the stale-entity cleanup must then not delete their registry entries, so the 24 h grace period has to cover "missing because of a short read"); WR-05 (every cert-coordinator notification re-adds all cert entities and HA logs ERROR "does not generate unique IDs" per host and platform; the entity manager must add only new unique_ids). The CR-01 gap fix in Phase 4 binds the cert entities to the cert coordinator but leaves the re-add listeners in place.
**Success Criteria** (what must be TRUE):

  1. In an integration test, changing a router's status `enabled → error`
     (and a service's `serverStatus` to DOWN) between two refreshes changes the
     corresponding entity state on the next cycle; adding a router creates its
     entity without reload; removing a router sets it to `missing` and keeps its
     registry entry (user renames/areas survive) until 24 h have passed
     (freezer), after which it is removed; a router that reappears inside the
     grace period is re-bound to the same entity.
  2. Routers and services are `sensor` entities with `device_class=enum` and
     options `enabled/warning/error/disabled/missing` (translated); service
     attributes expose `servers_up`/`servers_total` but never backend URLs or
     IPs; every attribute has one canonical key (no duplicate
     `name`/`router_name`/`status_breakdown` copies).
  3. `routers_problem`, `services_problem` and `middlewares_problem`
     (`binary_sensor`, `device_class=problem`) are **enabled by default**,
     implemented by one class plus entity descriptions; counts, version,
     entrypoints and the refresh button carry `EntityCategory.DIAGNOSTIC`,
     entrypoints are disabled by default; a no-change refresh writes zero
     states (write-on-change) and no listener scans the whole entity registry.
  4. One main device `Traefik (<host>)` (`entry_type=SERVICE`,
     `configuration_url=<url>/dashboard/`, `sw_version` updated when Traefik is
     upgraded) with sub-devices Routers / Services / Certificates linked via
     the registry `via_device_id` (no deprecated `DeviceInfo.via_device`); all static entity names come from `translation_key` with
     `en.json` + `de.json` entity strings and `icons.json` (state icons);
     every platform declares `PARALLEL_UPDATES`.
  5. The reload button, the `traefik_proxy.reload_routers` service,
     `services.yaml` and the client refresh method are gone; a "Refresh now"
     button refreshes both coordinators of **its own** entry; upgrading an
     install from 0.3.0 removes the old router/service `binary_sensor` and
     reload-button registry entries via a config-entry migration and raises a
     non-fixable repair notice explaining the new entity IDs; with the option
     "create per-router/per-service entities" set to off, no per-router or
     per-service entity exists (aggregate, diagnostic and certificate entities
     remain). Cert entities subclass a `TraefikCertEntity` subscribed to
     the cert coordinator and are no longer re-added every cycle (no
     "does not generate unique IDs" errors). Tests, `ruff`, `mypy --strict` green.
**Plans**: 8/8 plans complete (7 sequential waves; 1 gap-closure plan)

Plans:
**Wave 1**
- [x] 05-01-PLAN.md — Tracer: router ENUM sensor through the entity manager on the Routers sub-device (add / missing / re-bind, write-on-change); main + sub-devices with registry link, device and router-state translations (ENT-01, ENT-02, ENT-03, ENT-04)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 05-02-PLAN.md — Router binary_sensor removed and router tests moved to the ENUM sensor; persisted 24 h wall-clock grace period with deadline timer and orphan adoption (ENT-01, ENT-02, ENT-04)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 05-03-PLAN.md — Services and entrypoints as manager kinds; problem aggregates as one enabled-by-default class; diagnostic counts/version/start time/healthy ratio; PARALLEL_UPDATES for sensor/binary_sensor (ENT-01, ENT-02, ENT-04, ENT-05, ENT-06, ENT-08)

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 05-04-PLAN.md — Per-item option: no router/service entities and no Routers/Services sub-devices when off, immediate purge on reload (ENT-10)

**Wave 5** *(blocked on Wave 4 completion)*
- [x] 05-05-PLAN.md — Certificate entities on TraefikCertEntity through the manager (WR-05): no re-adding known hosts, grace period, write-on-change, translated {host} names (ENT-01, ENT-02, ENT-03, ENT-08)

**Wave 6** *(blocked on Wave 5 completion)*
- [x] 05-06-PLAN.md — Reload feature removed (button, service, services.yaml, client refresh method); "Refresh now" button for its own entry (ENT-07, ENT-08)

**Wave 7** *(blocked on Wave 6 completion)*
- [x] 05-07-PLAN.md — de.json + icons.json; 0.3.0 migration with persistent repair notice; legacy device cleanup, live sw_version, old bases removed, zero-write invariant (ENT-02, ENT-03, ENT-08, ENT-09)
- [x] 05-08-PLAN.md — Gap closure: migration keeps user-disabled routers disabled (CR-01/G6); update listener released on unload (WR-01); sub-device removal only when unreferenced (WR-02) (ENT-03, ENT-09, ENT-10)

**Cross-cutting constraints:** <!-- gsd:generated -->
- pytest, ruff check, ruff format --check, mypy --strict and the HA 2026.3.0 venv suite are green after every task of this plan; no HA 2026.11-only API is used (D-20)
- pytest, ruff check, ruff format --check, mypy --strict and the HA 2026.3.0 venv suite are green after every task (D-20)

### Phase 6: Certificates

**Goal**: Users see correct expiry data for the certificates Traefik actually
serves — including expired, self-signed and private-CA certificates — sourced
from `GET /api/certificates` on Traefik ≥ 3.7 and otherwise from a threadless
async probe against the Traefik host with SNI; an expired or unprobeable
certificate is reported as a problem, never as "unavailable".
**Depends on**: Phase 5
**Requirements**: CERT-01, CERT-02, CERT-03, CERT-04, CERT-05
**Audit items**: A-12, P-05..P-08, U-09, U-10, S-04, S-05, S-07, T-01, T-02
**Success Criteria** (what must be TRUE):

  1. Against a Traefik ≥ 3.7 fixture the cert coordinator reads
     `/api/certificates` (no probing, `source=api`); against v2.11 / older v3
     (404) it probes; certificate entities are subscribed to the cert
     coordinator and managed by the Phase 5 entity manager.
  2. The probe uses `asyncio.open_connection` (no `to_thread`, no executor),
     one shared `SSLContext` with `CERT_NONE`, `getpeercert(binary_form=True)`
     and DER parsing via `cryptography` (bundled with HA); it connects to the
     Traefik host from the entry URL on the TLS entrypoint port with
     `server_hostname=<router host>`; tests show an **expired** and a
     **self-signed** certificate are both read successfully, with
     `verified=false` where the chain does not validate.
  3. `rules.py` `extract_hosts()` handles the v2 multi-argument form
     ``Host(`a`,`b`)``, the v3 `||` form, and skips `HostRegexp`/`HostSNI` and
     wildcard names; the probe set is capped at 200 hosts; wildcard SAN matching
     accepts exactly one label (RFC 6125 §6.4.3); TLS error classification
     distinguishes `ssl` from `oserror`; no module-level dict grows without bound.
  4. `days_left` is computed from `not_after` at read time (a threshold
     crossing is visible on the next state write, not 6 h later); an expired or
     repeatedly unprobeable certificate turns `certificate_expiring` and the
     `certificates_problem` aggregate (enabled by default) **on** with a
     `reason` attribute, while the timestamp sensor keeps its last known value
     and stays available. Tests, `ruff`, `mypy --strict` green.
**Plans**: 7/7 plans complete in 6 waves

Plans:
**Wave 1**
- [x] 06-01-PLAN.md — `rules.py` `extract_hosts`/`normalize_host` (v2 multi-argument, v3 `||`, no regex/SNI/wildcard/negated names) for the cert host set; cap at 200 hosts with one warning (CERT-03)
- [x] 06-02-PLAN.md — `/api/certificates` client + `TraefikCertificate` model + strict parser; test stubs serve the endpoint (clock-rebased v3.7 capture, v2.11 404); fixed capture dates only under frozen time (CERT-01)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 06-03-PLAN.md — Threadless CERT_NONE probe (`asyncio.open_connection`, SNI, DER via cryptography), offline `verified`, closed error set, single-label wildcard + API host mapping (CERT-02, CERT-04)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 06-04-PLAN.md — Atomic switch: per-host `HostCertState` from the threadless probe (connect host = Traefik host, SNI = router host), problem-on instead of unavailable with `reason`/`verified`/`source`, failure history, live days (CERT-02, CERT-05)

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 06-05-PLAN.md — API-first cert cycle (`/api/certificates`, `not_found`, 404 probe fallback), HA trust anchors, TLS entrypoint port per host, real-handshake end-to-end, cancellation/overlap safety; blocking probe path and throttle dict deleted with grep gates (CERT-01, CERT-02, CERT-03)

**Wave 5** *(blocked on Wave 4 completion)*
- [x] 06-06-PLAN.md — Day-boundary timer (threshold/expiry/daily change without a probe); honest failed first cert cycle, restored hosts not stamped missing, 5-minute retry (CERT-05)

**Wave 6** *(blocked on Wave 5 completion)*
- [x] 06-07-PLAN.md — `certificates_problem` aggregate (enabled by default, hosts + reasons) and en/de `reason` texts (CERT-05)

**Cross-cutting constraints:** <!-- gsd:generated -->
- pytest, ruff check, ruff format --check, mypy --strict and the HA 2026.3.0 venv suite are green after every task (D-19)

### Phase 7: Config flow, HA 2026.11 baseline, observability

**Goal**: Users can set up, re-authenticate and reconfigure the integration with
the authentication Traefik deployments actually use (none / basic / bearer),
options changes reload the entry without any update listener (HA 2026.12-safe),
errors are translated and actionable, and support data is available as a
redacted diagnostics download — fully in English and German, on HA 2026.11.0+
(raised from 2026.3.0 by user decision I1, using the 2026.11 APIs instead of
the 2026.3 workarounds).
**Depends on**: Phase 6
**Requirements**: FLOW-01, FLOW-02, FLOW-03, FLOW-04, FLOW-05, FLOW-06, FLOW-07, FLOW-08, DIAG-04
**Audit items**: A-15 flow part, A-17, A-18, A-22, U-03, U-11..U-14, U-16, S-01..S-03; research §4.1, §4.2 translated `UpdateFailed`, §4.5, §4.6 (§4.4 moot: services removed in Phase 5)
**Carry-over (Phase 4 review, `04-REVIEW.md`)**: IN-01 (an http-to-https redirect drops the Authorization header and surfaces as `invalid_auth` / reauth instead of a clear "use https" error); IN-04 (a stored token the new `Auth` rejects fails setup instead of starting reauth); IN-08 (a stored entry with credentials in the URL plus a token retries setup forever and only shows "/api/version: ValueError"; the basic-auth selector and migration must move URL userinfo into the credential fields or raise a repair telling the user what to fix); IN-09 (`InvalidUrl(url)` in `config_flow.py` keeps the URL including its userinfo password in the exception args; raise it without the URL). WR-03 (update-listener leak) is already covered by SC2.
**Carry-over (Phase 4 re-review, `04-REVIEW.md` @ 9ef58b3, M33)**: IN-10 (`_check_url_shape` lets `urlparse`'s `ValueError` escape: `http://[::1` aborts the user step with "Unknown error" and a traceback, and the reconfigure step hits it even earlier through `urlparse(...).hostname`; wrap the parse in `try/except ValueError: raise InvalidUrl from None` and run the shape check before computing the host in reconfigure).
**Carry-over (user interview 2026-11-14)**: I1 (minimum HA 2026.11.0: `hacs.json`, `pyproject`/`uv.lock`, CI minimum job 2026.11.x, `ChildDeviceInfo` instead of the `via_device_id` registry workaround W33, repairs with `config_entry_id`, `async_unload_platforms_or_raise`, other 2026.11 APIs where sensible); I7 (missing-entity grace period becomes an option, 1 h – 7 days, default 24 h) together with the per-item field (W36); config entry `MINOR_VERSION` 2 → 3 (W44).
**Carry-over (Phase 5 review, `05-REVIEW.md`)**: IN-02 (`de.json` lacks config/options/exceptions strings); IN-04 (per-item option has no options-form field).
**Carry-over (Phase 6 review/verification, `06-REVIEW.md`, STATE)**: IN-01 (`CertCoordinator.get_threshold()` dead); IN-02 (literal `"tls_warn_days"` instead of `CONF_TLS_WARN_DAYS`); the WR-02 fix reads the private `DataUpdateCoordinator._shutdown_requested` — replace it with a public/own mechanism at the 2026.11 bump. Phase 4 deferred item W28 (`invalid_url` text does not mention URL credentials).
**Success Criteria** (what must be TRUE):

  1. The user step offers an auth selector (none / basic username+password /
     bearer) with `PASSWORD` selectors for secrets and a `data_description` per
     field; existing 0.3.0 entries migrate (minor version bump) to the new data
     shape (token → bearer, empty → none) and to unique_id `host:port` with
     title = host; switching to "none" clears stored credentials.
  2. `entry.add_update_listener` is no longer used anywhere; the options flow
     is an `OptionsFlowWithReload` with `NumberSelector`s (unit `s` / `d`,
     box mode) and the per-item-entities toggle; reauth and reconfigure finish
     via `async_update_reload_and_abort`, and reconfigure to a new host:port
     updates the entry unique_id; no HA `report_usage` warning is logged in
     tests on HA 2026.11+; the options form also offers the missing-entity grace
     period (1–168 h, default 24 h), applied after the reload.
  3. Every config-flow error path (`invalid_auth`, `cannot_connect`,
     `api_disabled` on 404, `unknown`, `already_configured`) is covered by tests
     (config_flow.py 100 % line coverage); `ConfigEntryAuthFailed`,
     `ConfigEntryNotReady` and `UpdateFailed` carry `translation_key`s resolved
     from `translations/*.json` `exceptions`.
  4. Downloading diagnostics returns the entry data, options and current
     snapshot with password, token and username redacted (asserted by a test
     that searches the dump for the secret values); an `http://` URL combined
     with credentials raises a repair issue that disappears when fixed or when
     the entry is unloaded/removed, using the HA 2026.11 issue-registry API
     (`config_entry_id`).
  5. `hacs.json` and the test floor require HA 2026.11.0, CI runs a test job
     pinned to HA 2026.11.0, sub-devices link via the 2026.11 device API, every
     repair carries `config_entry_id`, unload uses
     `async_unload_platforms_or_raise`, and no private HA attribute is read.
  6. `strings.json`, the YAML import step and its strings, and the dead code
     listed in audit A-18 are removed; `translations/en.json` is the single
     source and `translations/de.json` covers every key in it (key-parity test);
     hassfest translation validation passes. Tests, `ruff`, `mypy --strict` green.
**Plans**: 9/9 plans complete in 8 waves (07-02 and 07-03 run in parallel)

Plans:
**Wave 1**
- [x] 07-01-PLAN.md — Tracer: toolchain on HA 2026.11 — `pytest-homeassistant` switch with the mechanical test-import rename, 2026.3 import shims removed, `ha2611-venv`; `hacs.json` 2026.11.0 and CI `test-min-ha` (FLOW-08)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 07-02-PLAN.md — Tracer: 2026.11 APIs — sub-devices via `via_device_id=`, entry-bound migration repair, `async_unload_platforms_or_raise`, `-> None` setup/unload, own `_stopping` flag (FLOW-08)
- [x] 07-03-PLAN.md — Tracer: baseline cleanup — `strings.json` gone (test + hassfest script), `const.VERSION` gone, `api.py` comment, REQUIREMENTS/ROADMAP 2026.11 leftovers after verifying d18f96a (FLOW-07, FLOW-08)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 07-04-PLAN.md — Tracer: redirect never followed and translated; every coordinator/cert/setup exception translated; invalid stored URL stops, rejected credentials start reauth (FLOW-05, FLOW-04)

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 07-05-PLAN.md — Tracer: entry data 1.3 with auth selector (none/basic/bearer, conditional fields) in user/reauth/reconfigure; 1.2 → 1.3 migration incl. URL userinfo; unique_id `host:port`, title = host (FLOW-01, FLOW-03)

**Wave 5** *(blocked on Wave 4 completion)*
- [x] 07-06-PLAN.md — Tracer: `OptionsFlowWithReload` without update listener; NumberSelectors for interval and TLS threshold; listener-only threshold setter/getter removed (FLOW-02)

**Wave 6** *(blocked on Wave 5 completion)*
- [x] 07-07-PLAN.md — Tracer: missing-entity grace period (1–168 h) honoured by the entity manager; per-item toggle in the options form; all options texts en + de (FLOW-02)

**Wave 7** *(blocked on Wave 6 completion)*
- [x] 07-08-PLAN.md — Tracer: `redirect` flow error; `url_has_credentials`, `unknown`, full error matrix, `config_flow.py` 100 % line coverage, final en/de error texts (FLOW-04, FLOW-07)

**Wave 8** *(blocked on Wave 7 completion)*
- [x] 07-09-PLAN.md — Tracer: redacted diagnostics download; `insecure_credentials` repair with `config_entry_id` and whole-file en ↔ de parity test; read-only phase checks incl. no new planning references in shipped code (DIAG-04, FLOW-06, FLOW-07)

**Cross-cutting constraints:** <!-- gsd:generated -->
- pytest (dev env), ruff check, ruff format --check, mypy --strict and the HA 2026.11.0 venv suite are green after every task (D-02)

- pytest (dev env 2026.11.x), ruff check, ruff format --check, mypy --strict and the HA 2026.11.0 venv suite are green after every task (D-02); a failure confined to `tests/test_cert_entity_state.py` is rerun once before it counts (D-33)

### Phase 8: Marketplace + release readiness

**Goal**: The repository is ready for a 1.0.0 release and a `hacs/default`
catalog submission: metadata, brand, documentation, CI and tooling meet the
Marketplace/HACS requirements, shipped code is free of planning references, both
validators pass locally, and the branch is pushed with a Draft PR — the release,
tag and catalog PR themselves remain the user's action.
**Depends on**: Phase 7
**Requirements**: REL-01, REL-02, REL-03, REL-04, REL-05, REL-06, REL-07, REL-08, DIST-04, DOCS-02, DOCS-04
**Audit items**: A-19, B-01..B-06, H-01..H-10, H-12; research §2, §3, §6 Q1/Q7/Q8
**Carry-over (Phase 4 review)**: `pyproject.toml` `addopts` measures `--cov=custom_components.traefik`, a package that no longer exists; switch to `--cov=custom_components.traefik_proxy` and gate CI on it. Clear `.planning/phases/04-data-layer-correct-lean/deferred-items.md` (SyntaxWarning from the non-raw docstring in `tests/test_binary_sensor.py:35`) as part of the docstring sweep.
**Carry-over (Phase 4 re-review, `04-REVIEW.md` @ 9ef58b3, M33)**: IN-11 (cert entities keep a redundant `_coordinator` alias of `self.coordinator`; drop it and read `self.coordinator` everywhere — close as already resolved if the Phase 5 cert-entity rewrite removed it); IN-12 (the probe-clock matrix row and `04-REVIEW-FIX.md` over-claim the timing "first probe one hour after the switch, never in a failing cycle"; correct the comment and add tests for an off-grid switch, a probe due in a failing cycle and a probe due in a recovering cycle); IN-13 (add `RAWDATA_PROBE_INTERVAL = timedelta(hours=1)`, give `_interval_elapsed(since, interval)` an interval parameter, rename `_probe_armed_at` to `_probe_clock` or document it as the probe grid tick that also moves in rawdata mode); IN-14 (log at debug level when the switch to the paginated list endpoints is committed, not only "trying"); fixture determinism (document in the capture harness that re-captured fixtures are byte-stable only while the committed throwaway certificate is kept; a regenerated certificate changes the certificate fixtures).
**Success Criteria** (what must be TRUE):

  1. `manifest.json` declares `"categories": ["computers_network.monitoring"]`
     (keys sorted as hassfest requires) and `"version": "1.0.0"`; `brand/`
     contains re-exported, trimmed and centred `icon.png` (256²) /
     `icon@2x.png` (512²) plus `logo.png` / `logo@2x.png`, and `icon.svg`
     lives in `docs/`; local brand serving is confirmed for HA 2026.11.0.
  2. `README.md` is rewritten (Marketplace / My-link badge, prerequisites incl.
     how to protect the Traefik API with basicAuth, install/removal, options,
     entity table matching the code, example automations, troubleshooting, FAQ
     on out-of-scope features, Traefik trademark note) and contains no private
     hostnames or aliases; `CHANGELOG.md` (Keep a Changelog) covers 0.1.x–1.0.0
     with the breaking changes and required user actions at the top.
  3. pre-commit hooks target `custom_components/traefik_proxy` on Python 3.14
     and actually run; `pyproject.toml` coverage points at
     `custom_components.traefik_proxy` with a `fail_under` gate; the Makefile
     matches CI; CI runs on push, PR, nightly `schedule` and
     `workflow_dispatch`, keeps the test job pinned to HA 2026.11.x added in
     Phase 7, pins every
     action by tag or SHA, and a release workflow fails when the tag does not
     equal the manifest version; the suite has no `SyntaxWarning` and no real
     multi-second sleeps.
  4. A grep for planning references (`CONTEXT.md`, `PITFALLS`, `D-[0-9]`,
     `BLOCKER`, `Phase [0-9]`, `.planning/`, `.claude/`, `spike`) in
     `custom_components/` returns nothing; CLAUDE.md describes
     `custom_components/traefik_proxy` / domain `traefik_proxy` and routes to
     the renamed `spike-findings-homeassistant-traefik-proxy-integration` skill.
  5. Local `hassfest` and `hacs/action` (category integration, no `ignore`)
     both pass; release notes and the `hacs/default` PR text are drafted in
     `.planning/`; `feat/marketplace-polish` is pushed and a **Draft PR** to
     `main` is open — no tag, release or `hacs/default` PR is created by the
     assistant (U1, M8). Tests, `ruff`, `mypy --strict` green.
**Plans**: TBD

Plans:

- [ ] TBD (run /gsd-plan-phase 8 to break down)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 4/4 | Complete    | 2026-07-05 |
| 2. Core Entities + Options + Reauth + Reload | 4/4 | Complete   | 2026-07-05 |
| 3. TLS Certificate Expiry | 3/3 | Complete   | 2026-07-06 |
| 4. Data layer (correct + lean) | 9/9 | Complete    | 2026-11-14 |
| 5. Entity model + lifecycle | 8/8 | Complete    | 2026-11-15 |
| 6. Certificates | 7/7 | Complete    | 2026-11-15 |
| 7. Config flow, HA 2026.11 baseline, observability | 9/9 | Complete    | 2026-11-15 |
| 8. Marketplace + release readiness | 0/TBD | Not started | - |

**Coverage:**

| Phase | Requirements | Count |
|-------|--------------|-------|
| 1 | CFG-01,02,06 / API-01,02,03,04,06 / COORD-01..04 / ROUTER-01,04 / UX-01,02 / DIST-01,02,03 / DOCS-01 / TEST-01,03 | 22 |
| 2 | CFG-03,04,05 / API-05 / ROUTER-02,03 / ENTRY-01,02,03 / DIAG-01,02,03 / UX-03,04 / TEST-02 | 15 |
| 3 | TLS-01..05 / TEST-04 | 6 |
| 4 | DATA-01..07 | 7 |
| 5 | ENT-01..10 | 10 |
| 6 | CERT-01..05 | 5 |
| 7 | FLOW-01..08 / DIAG-04 | 9 |
| 8 | REL-01..08 / DIST-04 / DOCS-02,04 | 11 |
| Superseded | API-02, API-05, ROUTER-01, DIAG-02, DIAG-03, CFG-02, TLS-04, DIST-05, DOCS-03 (see REQUIREMENTS.md) | 9 |
| **Total active** | 36 complete (Phases 1–3) + 42 (Phases 4–8) | **78 / 78** ✓ |
