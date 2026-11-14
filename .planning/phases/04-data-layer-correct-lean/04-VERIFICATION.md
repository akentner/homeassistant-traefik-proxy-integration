---
phase: 04-data-layer-correct-lean
verified: 2026-11-14T01:35:00Z
status: gaps_found
score: 7/11 must-haves verified
covered_files:
  - ".planning/phases/04-data-layer-correct-lean/04-01-PLAN.md"
  - ".planning/phases/04-data-layer-correct-lean/04-01-SUMMARY.md"
  - ".planning/phases/04-data-layer-correct-lean/04-02-PLAN.md"
  - ".planning/phases/04-data-layer-correct-lean/04-02-SUMMARY.md"
  - ".planning/phases/04-data-layer-correct-lean/04-03-PLAN.md"
  - ".planning/phases/04-data-layer-correct-lean/04-03-SUMMARY.md"
  - ".planning/phases/04-data-layer-correct-lean/04-04-PLAN.md"
  - ".planning/phases/04-data-layer-correct-lean/04-04-SUMMARY.md"
  - ".planning/phases/04-data-layer-correct-lean/04-05-PLAN.md"
  - ".planning/phases/04-data-layer-correct-lean/04-05-SUMMARY.md"
  - ".planning/phases/04-data-layer-correct-lean/04-06-PLAN.md"
  - ".planning/phases/04-data-layer-correct-lean/04-06-SUMMARY.md"
  - "custom_components/traefik_proxy/__init__.py"
  - "custom_components/traefik_proxy/api.py"
  - "custom_components/traefik_proxy/binary_sensor.py"
  - "custom_components/traefik_proxy/button.py"
  - "custom_components/traefik_proxy/cert_coordinator.py"
  - "custom_components/traefik_proxy/config_flow.py"
  - "custom_components/traefik_proxy/coordinator.py"
  - "custom_components/traefik_proxy/data.py"
  - "custom_components/traefik_proxy/entity.py"
  - "custom_components/traefik_proxy/models.py"
  - "custom_components/traefik_proxy/sensor.py"
  - "tests/conftest.py"
  - "tests/fixtures/v2.11/pages/index.json"
  - "tests/fixtures/v2.11/rawdata.json"
  - "tests/fixtures/v3.7/pages/index.json"
  - "tests/fixtures/v3.7/rawdata.json"
  - "tests/test_api.py"
  - "tests/test_api_pagination.py"
  - "tests/test_coordinator.py"
  - "tests/test_fixture_redaction.py"
  - "tests/test_models.py"
  - "tests/test_platforms_real_fixtures.py"
  - "tests/traefik/capture.py"
  - "tests/traefik/compose.yaml"
  - "tests/traefik/dynamic/scenario.yml"
covered_digest: "v4:sha256:cc827736bb6bd1ed3cee907e7c6e3b98627f46f0ca6ca476441aebd48886b890"
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "User-visible entities keep working unchanged on top of the new data layer (phase goal; ROADMAP SC5 'existing entity set still reports correct states')"
    status: failed
    reason: "Regression CR-01 confirmed. Phase 4 set always_update=False on the main coordinator (coordinator.py:102), but TraefikProxyCertTimestampSensor and TraefikProxyCertExpiryBinarySensor still subscribe to the MAIN coordinator through TraefikProxyEntity.__init__ (entity.py:62 super().__init__(entry.runtime_data.coordinator)). They read the cert coordinator only inside their properties. Cert-coordinator listeners (sensor.py:146, binary_sensor.py:186) only re-add entities (rejected as duplicate unique_ids) and clean up the registry; they never write entity state. Before Phase 4 (1d41e87) the main coordinator used the default always_update=True, so every 15 s cycle re-wrote cert entity state as a side effect. Verifier scratch test (full setup via stub_traefik, probe patched to CertInfo days=30, then cert_coordinator.async_set_updated_data(days=3), then an unchanged main refresh, then async_set_threshold(60)): binary_sensor stayed 'off' with days_until_expiry=30 and threshold_days=14 throughout; setting coordinator.always_update=True and refreshing immediately flipped it to 'on' with days=3. Cert-expiry alerts and tls_warn_days option changes do not reach HA state until the Traefik snapshot changes, which breaks the project's core value ('which TLS certificates are expiring soon')."
    artifacts:
      - path: "custom_components/traefik_proxy/entity.py"
        issue: "TraefikProxyEntity always binds CoordinatorEntity to entry.runtime_data.coordinator; no way to bind to the cert coordinator"
      - path: "custom_components/traefik_proxy/sensor.py"
        issue: "TraefikProxyCertTimestampSensor (line ~464) listens to the main coordinator, reads self._coordinator (cert) only in properties"
      - path: "custom_components/traefik_proxy/binary_sensor.py"
        issue: "TraefikProxyCertExpiryBinarySensor (line ~415) same; async_set_threshold -> async_update_listeners reaches no entity"
      - path: "custom_components/traefik_proxy/coordinator.py"
        issue: "always_update=False (line 102) removed the incidental 15 s re-render the cert entities depended on"
    missing:
      - "Bind both cert entity classes to the cert coordinator (e.g. optional coordinator= kwarg on TraefikProxyEntity, _sw_version read from entry.runtime_data.coordinator.data), or subscribe them in async_added_to_hass via self.async_on_remove(self._coordinator.async_add_listener(self.async_write_ha_state))"
      - "Integration test: full setup, then cert_coordinator.async_set_updated_data(...) changes the HA state of binary_sensor.traefik_<host>_expiring and sensor.traefik_<host>_cert; async_set_threshold(...) changes is_on/threshold_days in HA state"
  - truth: "The client raises only subclasses of TraefikProxyApiError (DATA-04, ROADMAP SC4, 04-05 truth 3)"
    status: partial
    reason: "Reproduced WR-02: TraefikProxyApiClient(session, 'https://u:p@192.0.2.1:1', Auth(mode=bearer, token='t')).async_get_version() raises a bare ValueError('Cannot combine AUTHORIZATION header with AUTH argument or credentials encoded in URL') from aiohttp request construction. api.py _request (lines 200-203) and reload_routers (310-313) catch only InvalidUrlClientError, ClientError, TimeoutError, OSError. config_flow._check_url_shape (line 149-151) accepts userinfo URLs and _validate_input does not catch ValueError, so the flow ends in 'unknown' with a traceback; at runtime _async_setup leaks a bare ValueError (HA wraps it as ConfigEntryNotReady and retries with a traceback). Until Phase 7 adds basic auth, a userinfo URL is the only way to reach a basicAuth-protected Traefik, so a token plus userinfo URL is a plausible input. All other taxonomy branches are verified by tests."
    artifacts:
      - path: "custom_components/traefik_proxy/api.py"
        issue: "aiohttp request-construction ValueError not mapped into the taxonomy (_request, reload_routers)"
      - path: "custom_components/traefik_proxy/config_flow.py"
        issue: "_check_url_shape accepts URLs with username/password"
    missing:
      - "Map aiohttp's request-construction ValueError inside the network block to TraefikProxyInvalidUrlError (JSON decode stays outside, as now)"
      - "Reject userinfo in _check_url_shape (parsed.username or parsed.password -> InvalidUrl)"
      - "Client test: userinfo URL + bearer auth raises a TraefikProxyApiError subclass, never a bare ValueError"
advisory:
  - finding: "WR-01: a single 404 on /api/rawdata (e.g. during a Traefik restart while the API router is not yet loaded) flips the client to paginated mode for its whole lifetime, tripling requests per cycle"
    category: other
    reason: "Behaviour matches D-07 and SC3 wording ('remembers the choice for the client's lifetime'), so not a goal failure; consider probing /api/version before flipping and making the switch revocable"
    evidence_status: "code reading only (api.py:264-269)"
  - finding: "WR-03 (pre-existing): update listener remover is discarded (__init__.py:260), so listeners accumulate across reloads; reconfigure plus update listener is slated to break in HA 2026.12.0"
    category: other
    reason: "Predates Phase 4 and is scheduled in Phase 7 SC2 (no add_update_listener, OptionsFlowWithReload)"
    evidence_status: "code reading; reviewer measured 1 -> 2 listeners after one reload"
  - finding: "WR-05 (pre-existing): every cert-coordinator notification re-adds all cert entities and HA logs ERROR 'does not generate unique IDs' per host and platform"
    category: other
    reason: "Observed in the verifier's scratch run (4 ERROR lines per notification for 2 hosts); interacts with the CR-01 fix; Phase 5/6 entity manager is the natural home"
    evidence_status: "observed in scratch test log output"
---

# Phase 4: Data layer (correct + lean) Verification Report

**Phase Goal:** The integration reads the **real** Traefik v2.11 / v3.x API shape correctly and cheaply: one `GET /api/rawdata` per scan cycle is parsed once at the client boundary into frozen, typed models, and the coordinator hands every consumer a `TraefikSnapshot` with per-name lookups and precomputed aggregates, proven against fixtures captured from real Traefik containers, not hand-written JSON. User-visible entities keep working unchanged on top of the new data layer (the entity rework is Phase 5).
**Verified:** 2026-11-14T01:35:00Z
**Status:** gaps_found
**Re-verification:** No (initial verification)

## Goal Achievement

The data layer itself is real and well tested: captured fixtures, frozen models, rawdata-first client with a paginated fallback, typed runtime data, and a snapshot coordinator. The goal's last clause fails, though: the `always_update=False` switch breaks state propagation for the two TLS certificate entities. In addition, the "only TraefikProxyApiError subclasses" contract has a reproducible hole.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1 / DATA-07: redacted real v2.11 + v3.x captures (rawdata, version, entrypoints, paginated pages with X-Next-Page) cover @docker/@file/@internal, error[], serverStatus UP+DOWN, tls.domains, >100 routers on the paginated path; harness committed; no private host/IP/credential | ✓ VERIFIED | jq: both generations have 129 routers, providers docker,file,internal, error[] router, UP+DOWN service, tls.domains router; router pages 1 and 2 (X-Next-Page "2" then "1", per_page 100); v3.7 certificates.json present. compose.yaml pins traefik:v2.11.63, v3.7.19 and whoami v1.12.0 by sha256 and binds only to 127.0.0.1. tests/traefik/certs is git-ignored. test_fixture_redaction.py (11 tests: IP/hostname/credential scan, scenario coverage, redactor, harness isolation) passes. `pytest --collect-only tests/traefik` exits 5 |
| 2 | SC2 / DATA-01: models.py defines frozen dataclasses Router, Service, Middleware, Entrypoint, TraefikVersion, TraefikSnapshot and a Status StrEnum; both generations give identical semantics; no platform runs isinstance shape checks on raw API dicts | ✓ VERIFIED | models.py: `@dataclass(frozen=True, slots=True)` on every model, no HA import. test_models.py covers map form vs list form and v2.11 vs v3.7 projection equality, servers_up/servers_total, frozen-ness, @internal drop. The remaining isinstance calls in the platforms check only the cert-cache dict (cert coordinator data) and `TraefikSnapshot` in entity.py, never raw API payloads |
| 3 | SC3 / DATA-02: one steady cycle = one `GET /api/rawdata`; version + entrypoints fetched at setup; version re-checked hourly and after a failed cycle; entrypoints refetched only on start-date change; 404 on rawdata falls back to pagination following X-Next-Page with no truncation; all asserted by request-counting tests | ✓ VERIFIED | coordinator.py `_async_setup`, `_version_due`, `_async_refresh_version`; api.py `async_get_state` / `_get_paginated` (continue only while header > page, MAX_PAGES raises). Checked by test_request_budget_matrix (setup, steady, hourly, post-failure, restart), test_rawdata_404_switches_to_pages_once, test_page_cap_raises_instead_of_truncating, test_real_router_pages_followed_to_the_end. The termination rule matches the captured headers (last page repeats "1"). Matrix and listener tests also pass on the HA 2026.3.0 venv (aiohttp 3.13.3) |
| 4 | SC4 / DATA-03: auth none/basic/bearer, header built per request, never on the session, credentials never logged or in exception text | ✓ VERIFIED | api.py `Auth` (frozen, secrets `repr=False`), `header()` per request. test_each_mode_sends_exactly_its_header asserts the shared session gets no Authorization header. test_credentials_never_leak scans caplog, str/repr of exceptions and repr(client). No assert statements in the package (AST count 0) |
| 5 | SC4 / DATA-04: the client raises **only** TraefikProxyApiError subclasses (Auth 401/403, NotFound 404, Connection, Payload); coordinator maps to ConfigEntryAuthFailed / UpdateFailed | ✗ FAILED (partial) | The mapping is correct and tested for every enumerated case (test_status_maps_to_specific_error, test_network_errors_raise_connection_error, test_cycle_auth_error_starts_reauth, test_cycle_server_error_keeps_previous_snapshot). But a scratch run with a userinfo URL plus a bearer token raised a bare `ValueError` from aiohttp (WR-02 reproduced). See gaps |
| 6 | SC5 / DATA-05: entry.runtime_data is a typed TraefikRuntimeData(client, coordinator, cert_coordinator); no getattr(..., None); runtime_data assigned before the first refreshes; single client owner | ✓ VERIFIED | data.py dataclass plus PEP-695 alias. grep finds no `getattr(..., None)` and no monkey-attached cert_coordinator. `__init__.py` assigns runtime_data before both first refreshes. Coordinator `client` property reads runtime_data.client. Tested by test_runtime_data_set_before_cert_first_refresh and test_single_client_owner |
| 7 | SC5 / DATA-06: coordinator returns TraefikSnapshot with per-name dicts and aggregates computed once; always_update=False; listeners do not fire on equal snapshots | ✓ VERIFIED | `TraefikSnapshot.build` computes StatusCounts and sorted problem tuples. coordinator.py:102 sets `always_update=False`. test_equal_snapshots_do_not_notify_listeners covers both the negative case and the positive control |
| 8 | Phase goal / SC5: user-visible entities keep working unchanged on top of the new data layer | ✗ FAILED | CR-01 confirmed by a verifier scratch test (deleted afterwards). Cert timestamp sensor and cert-expiring binary sensor listen to the main coordinator. With always_update=False, cert-cycle results and tls_warn_days changes never reach HA state (state stayed `off`/30 days after the cache said 3 days; flipped to `on` only after forcing always_update=True). Router, entrypoint, service, count and any-*-failing entities are fine on both generations (test_platforms_real_fixtures.py) |
| 9 | Entity classes, unique_ids, entity_ids, names, platforms and entity set unchanged; service attributes carry counts only, no backend URL/IP | ✓ VERIFIED | Diff of unique_id/entity_id/class patterns in sensor.py, binary_sensor.py and button.py between 1d41e87 and HEAD: identical. Service attributes are name/status/type/server_count/servers_up/service_name. Tested by test_service_sensor_attributes_expose_no_backend_url and test_services_store_no_backend_url_or_ip |
| 10 | (backstop, 04-01) Re-running the capture produces byte-identical fixtures except time-varying fields | ⚠️ insufficient_spec | Non-inferable. It needs Docker and a live capture run, and the verifier must not start services. Sorted-key writing and the deterministic redactor are present, but presence does not count for a backstop truth. Routed to human |
| 11 | (backstop, 04-05) Replacing the client through the options listener during an in-flight refresh never mixes credentials | ⚠️ insufficient_spec | Non-inferable. Each request takes its header from its own frozen `Auth` (api.py:187, 305), but no concurrency test exercises this. Routed to human |

**Score:** 7/11 truths verified (0 present-but-behavior-unverified; 2 insufficient_spec routed to human; 2 failed)

### Deferred Items

None applied. Phase 6 SC1 ("certificate entities are subscribed to the cert coordinator") would cover the CR-01 fix. CR-01 is still kept as a real gap for three reasons: Phase 4 explicitly promises unchanged user-visible entities, the regression was introduced by this phase, and it would persist through all of Phase 5. Deferring would need an explicit decision (see the override suggestion below).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/traefik/compose.yaml` | Digest-pinned v2.11/v3.7 + whoami, loopback only | ✓ VERIFIED | verify.artifacts 8/8 for plan 01 |
| `tests/traefik/capture.py` | Capture + Redactor | ✓ VERIFIED | `main()` behind guard; loaded by path in tests |
| `tests/fixtures/v2.11/*`, `tests/fixtures/v3.7/*` | Real redacted captures | ✓ VERIFIED | Scenario coverage confirmed with jq |
| `custom_components/traefik_proxy/models.py` | Frozen models, parsers, snapshot aggregates | ✓ VERIFIED | 399 lines, wired from api.py and coordinator.py |
| `custom_components/traefik_proxy/api.py` | Auth, taxonomy, rawdata + paginated fallback | ⚠️ VERIFIED with gap | Substantive and wired; ValueError hole (gap 2) |
| `custom_components/traefik_proxy/coordinator.py` | Snapshot coordinator, `_async_setup`, version re-check | ✓ VERIFIED | |
| `custom_components/traefik_proxy/data.py` | TraefikRuntimeData + alias | ✓ VERIFIED | |
| `custom_components/traefik_proxy/entity.py` | Base entity bound to runtime coordinator | ✗ wiring defect | Binds cert entities to the wrong coordinator (gap 1) |
| `tests/test_platforms_real_fixtures.py` | Entity-state proof on both generations | ✓ VERIFIED | Does not cover cert entities |

gsd-tools `verify.artifacts`: plan 01 8/8, plan 02 3/3, plan 03 3/3, plan 04 7/7, plan 05 4/4, plan 06 5/5.

### Key Link Verification

gsd-tools `verify.key-links`: 01 3/3, 02 3/3, 03 2/2, 04 4/4, 05 3/3, 06 3/3, all WIRED.

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| Cert entities (sensor.py / binary_sensor.py) | CertCoordinator | CoordinatorEntity subscription | ✗ NOT_WIRED | Subscribed to the main coordinator instead. No plan declared this link, which is why the tool checks pass while the behavior fails |
| api.py | models.py | parse_* at the client boundary | ✓ WIRED | |
| coordinator.py | models.py | TraefikSnapshot.build once per cycle | ✓ WIRED | |
| binary_sensor/sensor | coordinator.data | `data.routers.get` / `.services.get` / `.entrypoints.get` | ✓ WIRED | |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| Router binary_sensor | `coordinator.data.routers[name]` | `/api/rawdata` -> parse_rawdata -> TraefikSnapshot | Yes (captured fixtures) | ✓ FLOWING |
| Service / entrypoint / count sensors | snapshot services/entrypoints/counts | same | Yes | ✓ FLOWING |
| Cert expiring binary_sensor / cert timestamp sensor | `cert_coordinator.data[host]` | TLS probe cache | Read on render, but render never triggered by cert updates | ⚠️ STATIC after setup (CR-01) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full suite (run once) | `uv run pytest -q` | 481 passed | ✓ PASS |
| Lint/format/types | `ruff check`, `ruff format --check`, `mypy --strict custom_components/traefik_proxy` | clean | ✓ PASS |
| Harness not collected | `pytest --collect-only -q tests/traefik` | exit 5 | ✓ PASS |
| HA 2026.3.0 compatibility | `ha2603-venv python -m pytest test_request_budget_matrix test_equal_snapshots_do_not_notify_listeners` | 2 passed (HA 2026.3.0, aiohttp 3.13.3) | ✓ PASS |
| CR-01 cert state propagation | scratch test (deleted) | state stayed off/30 after cert cycle and threshold change; on/3 only after forcing always_update=True | ✗ FAIL |
| WR-02 taxonomy hole | scratch script with userinfo URL + bearer | `ESCAPED: ValueError Cannot combine AUTHORIZATION header ...` | ✗ FAIL |

### Probe Execution

Step 7c: not applicable. No `scripts/*/tests/probe-*.sh` exists, and the phase declares no probes. The capture harness is intentionally Docker-only and not run by the verifier.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DATA-01 | 04-03, 04-04 | Parse once into frozen models; platforms never inspect raw dicts | ✓ SATISFIED | Truth 2 |
| DATA-02 | 04-04, 04-06 | One rawdata request per cycle; setup/hourly/restart rules; paginated fallback | ✓ SATISFIED | Truth 3 (WR-01 advisory) |
| DATA-03 | 04-05 | Auth none/basic/bearer; per-request header; no credential leaks | ✓ SATISFIED | Truth 4 |
| DATA-04 | 04-05 | Only TraefikProxyApiError subclasses; no assert | ✗ PARTIAL | Truth 5; REQUIREMENTS.md marks it `[x] Complete`, which is not accurate |
| DATA-05 | 04-02 | Typed TraefikRuntimeData | ✓ SATISFIED | Truth 6 |
| DATA-06 | 04-04 | TraefikSnapshot with aggregates; always_update=False | ✓ SATISFIED | Truth 7. The requirement holds, but implementing it caused the CR-01 regression |
| DATA-07 | 04-01, 04-05, 04-06 | Real, redacted, regenerable fixtures with full coverage | ✓ SATISFIED | Truth 1 |

All 7 IDs are claimed by at least one plan, and none is orphaned (REQUIREMENTS.md maps exactly DATA-01..07 to Phase 4).

### Prohibitions

| Prohibition | Tier | Enforcement evidence | Disposition |
|-------------|------|----------------------|-------------|
| No non-documentation IP / real hostname / credential in fixtures (04-01) | test | test_fixture_redaction.py privacy tests | verified (wired, passing) |
| No test starts Docker or contacts a Traefik (04-01) | test | test_harness_is_not_collectable; collect exit 5; all HTTP via aioclient_mock | verified |
| No backend URL/IP in models or attributes (04-04) | test | test_services_store_no_backend_url_or_ip, test_service_sensor_attributes_expose_no_backend_url | verified |
| No credential in log/exception/repr (04-05) | test | test_credentials_never_leak (the escaped ValueError message also carries no credential) | verified |
| No Authorization default header on the shared session (04-05) | test | test_each_mode_sends_exactly_its_header | verified |
| No request to a host other than the base URL (04-05) | test | test_real_captures_parse_and_requests_stay_on_base_url | verified |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| custom_components/traefik_proxy/entity.py | 62 | Cert entities subscribed to the wrong coordinator | 🛑 Blocker | CR-01 |
| custom_components/traefik_proxy/api.py | 200-203, 310-313 | Unmapped aiohttp ValueError | ⚠️ Warning (gap 2) | DATA-04 contract hole |
| custom_components/traefik_proxy/entity.py | 15-16 | `if TYPE_CHECKING: pass` dead block | ℹ️ Info | none |
| custom_components/traefik_proxy/__init__.py | 260, 273-276 | Discarded update-listener remover; wrong docstring | ℹ️ Info (pre-existing, Phase 7) | listener leak |

No TBD/FIXME/XXX/TODO/HACK markers in the phase files.

### Human Verification Required

These do not change the status, which is already gaps_found. Recorded so they are not lost:

1. **Fixture re-capture determinism (04-01 backstop)**
   - **Test:** With Docker available, run `uv run python tests/traefik/capture.py` twice and `git diff --stat tests/fixtures tests/traefik/dynamic/bulk.yml`
   - **Expected:** only time-varying fields (startDate and similar) differ; bulk.yml unchanged
   - **Why human:** requires starting containers; non-inferable truth
2. **No credential mixing on client swap (04-05 backstop)**
   - **Test:** start a refresh, change options (new verify_ssl/token) mid-cycle, inspect the Authorization header per recorded request
   - **Expected:** every request carries the header of the client instance that issued it
   - **Why human:** concurrency invariant with no test exercising it

### Gaps Summary

1. **CR-01 (BLOCKER), cert entities no longer update.** This is the one real regression of Phase 4. It comes from combining the correct DATA-06 change (`always_update=False`) with a pre-existing wiring shortcut: the cert entities subscribe to the main coordinator. The fix is small. Bind the two cert entity classes to the cert coordinator, and add an integration test that asserts HA state changes after `cert_coordinator.async_set_updated_data(...)` and `async_set_threshold(...)`.

   **Deferral option.** If the team prefers to fix this together with Phase 6 SC1, accept it explicitly. Note that cert alerts stay broken until then:

   ```yaml
   overrides:
     - must_have: "User-visible entities keep working unchanged on top of the new data layer"
       reason: "Cert entity re-binding to the cert coordinator is Phase 6 SC1; regression accepted until then"
       accepted_by: "<name>"
       accepted_at: "<ISO timestamp>"
   ```

2. **WR-02 (partial), DATA-04 taxonomy hole.** A userinfo URL combined with a bearer token makes aiohttp raise a bare `ValueError`. It escapes the client and the config flow. Map it to `TraefikProxyInvalidUrlError` and reject userinfo URLs in `_check_url_shape`.

Everything else in the phase goal holds:
- real captured fixtures
- frozen models
- one rawdata request per cycle
- paginated fallback without truncation
- typed runtime data
- the snapshot coordinator with change-only notifications
- unchanged entity identifiers
- all gates green on the dev venv and HA 2026.3.0

---

_Verified: 2026-11-14T01:35:00Z_
_Verifier: Claude (gsd-verifier)_
