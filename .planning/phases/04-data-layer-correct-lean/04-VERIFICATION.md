---
phase: 04-data-layer-correct-lean
verified: 2026-11-14T02:48:58Z
status: human_needed
score: 15/16 must-haves verified
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
  - ".planning/phases/04-data-layer-correct-lean/04-07-PLAN.md"
  - ".planning/phases/04-data-layer-correct-lean/04-07-SUMMARY.md"
  - ".planning/phases/04-data-layer-correct-lean/04-08-PLAN.md"
  - ".planning/phases/04-data-layer-correct-lean/04-08-SUMMARY.md"
  - ".planning/phases/04-data-layer-correct-lean/04-09-PLAN.md"
  - ".planning/phases/04-data-layer-correct-lean/04-09-SUMMARY.md"
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
  - "tests/test_binary_sensor_tls_expiring.py"
  - "tests/test_cert_entity_state.py"
  - "tests/test_config_flow.py"
  - "tests/test_coordinator.py"
  - "tests/test_fixture_redaction.py"
  - "tests/test_models.py"
  - "tests/test_platforms_real_fixtures.py"
  - "tests/test_reconfigure.py"
  - "tests/test_sensor_tls.py"
  - "tests/traefik/capture.py"
  - "tests/traefik/compose.yaml"
  - "tests/traefik/dynamic/scenario.yml"
covered_digest: "v4:sha256:516a04c345e1bd3d28f0eaf7d82f7deb211b13d284f6f7ced72ab04e82c7514f"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 7/11
  gaps_closed:
    - "User-visible entities keep working unchanged on top of the new data layer (CR-01, plan 04-07)"
    - "The client raises only subclasses of TraefikProxyApiError (WR-02, DATA-04, plan 04-08)"
  gaps_remaining: []
  regressions: []
advisory:
  - finding: "WR-09: the rawdata probe shares its clock with the post-failure version re-check; failed cycles recurring at intervals under one hour starve the probe, and the client stays paginated indefinitely"
    category: other
    reason: "Reproduced, but judged non-blocking: the M27 target (one 404 during a Traefik restart) is revoked within about 1 h, and starvation needs a spurious switch plus sustained sub-hourly failures. The cost is request volume only (pages plus 1 instead of 1), not data correctness. No later phase carries it; resolve by giving the probe its own clock (fix in 04-REVIEW.md WR-09)"
    evidence_status: "reproduced by verifier scratch test: failures every 50 min -> 0 probes in 6 h, still paginated; every 55 or 70 min (500) -> switched back at 60 min"
  - finding: "WR-10: the switch to pagination is committed before the page reads succeed; an all-404 restart window leaves the client paginated even though that cycle failed"
    category: other
    reason: "Reproduced, non-blocking: bounded at about 1 h of paginated reads per restart window, because the next hourly re-check probes rawdata and switches back. Fix: set _paginated only after _get_state_paginated() returns"
    evidence_status: "reproduced by verifier scratch test: one all-404 cycle -> _paginated True; healthy afterwards -> back to rawdata after 65 min (5-min cycles)"
  - finding: "IN-09: config_flow raises InvalidUrl(url) / InvalidUrl(data[CONF_URL]), so a rejected userinfo URL, password included, sits in exc.args"
    category: security
    reason: "Every caller catches InvalidUrl without logging, so nothing leaks today. Literal tension with the 04-08 prohibition about the error raised for a request-construction failure (the client error itself is clean). One-line fix: raise InvalidUrl without the URL"
    evidence_status: "code reading (config_flow.py:156,158,193); all four except-InvalidUrl sites checked, no logging"
  - finding: "IN-08: a stored userinfo URL plus token retries setup forever with reason '/api/version: ValueError'"
    category: other
    reason: "Intended quiet retry per 04-08 decisions; actionable error belongs with the Phase 7 auth selector (with IN-04)"
    evidence_status: "code reading"
  - finding: "IN-10: _check_url_shape lets urlparse's ValueError ('Invalid IPv6 URL') escape into 'unknown'"
    category: other
    reason: "Pre-existing config-flow path, not the client (the DATA-04 contract covers the client and still holds); Phase 7 config-flow work is the natural home"
    evidence_status: "reviewer-verified on Python 3.14; not re-run"
  - finding: "IN-11: cert entities keep a redundant self._coordinator alias of self.coordinator"
    category: other
    reason: "Both names point to the same CertCoordinator today (asserted by tests); refactor hazard only"
    evidence_status: "code reading (sensor.py:466, binary_sensor.py:417)"
coincidental_reliance_items:
  - truth: "The paginated fallback is revocable: while paginated, the hourly version re-check retries /api/rawdata once and switches back on success (04-09, M27)"
    reason: undeclared-precondition
    harden: "Revocation relies on no failed cycle inside each hour after the last successful version check (WR-09) and on the switch being committed only on a real page success (WR-10). Give the probe its own clock and set _paginated only after the pages succeed"
human_verification:
  - test: "With Docker available, run `uv run python tests/traefik/capture.py` twice, then `git diff --stat tests/fixtures tests/traefik/dynamic/bulk.yml`"
    expected: "Only time-varying fields (startDate and similar) differ; bulk.yml is unchanged"
    why_human: "04-01 backstop truth (non-inferable). It needs live containers, and the verifier must not start services"
---

# Phase 4: Data layer (correct + lean) Verification Report

**Phase Goal:** The integration reads the **real** Traefik v2.11 / v3.x API shape correctly and cheaply: one `GET /api/rawdata` per scan cycle is parsed once at the client boundary into frozen, typed models, and the coordinator hands every consumer a `TraefikSnapshot` with per-name lookups and precomputed aggregates, proven against fixtures captured from real Traefik containers, not hand-written JSON. User-visible entities keep working unchanged on top of the new data layer (the entity rework is Phase 5).
**Verified:** 2026-11-14T02:48:58Z
**Status:** human_needed
**Re-verification:** Yes, after gap closure (plans 04-07, 04-08, 04-09)

## Goal Achievement

Both previous gaps are closed, with code and behavioral evidence:
- **CR-01:** cert entities now listen to the cert coordinator. A full-setup HA-state test proves propagation.
- **WR-02:** aiohttp's request-construction `ValueError` is mapped into the taxonomy. A real-session reproduction now yields `TraefikProxyInvalidUrlError` on every client method.

The M27 extra (revocable fallback) works for the condition it targets. It has two reproduced, non-blocking weaknesses (WR-09, WR-10).

The only item left is the Docker-dependent fixture re-capture determinism check from 04-01. A human has to run it.

### Previous gaps: closure status

| Previous gap | Status | Evidence |
|---|---|---|
| 1. CR-01: cert entities no longer update (phase goal, SC5) | **CLOSED** | See the bullets below this table |
| 2. WR-02: bare `ValueError` escapes the client (DATA-04, SC4) | **CLOSED** | See the bullets below this table |
| Advisory WR-01: a single rawdata 404 makes pagination permanent | **Closed as scoped (M27)** | Revocable. Residuals WR-09 and WR-10, see below |

**CR-01 evidence:**
- `entity.py:41-136` adds the generic `_TraefikProxyBaseEntity[CoordinatorT]`. `TraefikProxyCertEntity` passes the `CertCoordinator` to `CoordinatorEntity.__init__`.
- Both cert classes now derive from it. The diff against b05c9e5 is limited to the base class and the `super().__init__` argument, so unique_id, entity_id and name are unchanged.
- `always_update=False` is still set (`coordinator.py:103`).
- `tests/test_cert_entity_state.py` has 8 full-setup tests that cover:
  - a cert cycle, followed by an unchanged main cycle
  - the threshold boundary at 30/29/31
  - the `tls_warn_days` option
  - availability following only the cert coordinator, including a `CertError` row
  - main cycles never probing
  - the listener count staying stable
  - `sw_version`

  These are the same assertions as the previous verifier's failing scratch test, and they pass.

**WR-02 evidence:**
- `api.py:206-209` and `api.py:361-364` add `except ValueError` inside the network block and map it to `TraefikProxyInvalidUrlError`. JSON decoding stays outside the block.
- `config_flow.py:141-158` rejects userinfo by default. The user step (285) and reconfigure (435) use the strict default. Reauth (372) and YAML import (318) opt out and get the mapped InvalidUrl.
- Verifier re-run on a real aiohttp session with `https://u:p@`, `http://u@` and `https://:p@` plus a bearer token:
  - All 4 client methods raise `TraefikProxyInvalidUrlError` with the message `<path>: ValueError`.
  - Nothing escapes, and the message contains no credential or host.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1 / DATA-07: redacted real v2.11 + v3.x captures with full scenario coverage; harness committed; no private host/IP/credential | ✓ VERIFIED (regression check) | `git diff b05c9e5..HEAD -- tests/fixtures` is empty. verify.artifacts for 04-01 is 8/8 and key-links 3/3. test_fixture_redaction.py is in the green suite |
| 2 | SC2 / DATA-01: frozen models, identical semantics on both generations, no raw-dict isinstance checks in platforms | ✓ VERIFIED (regression check) | models.py is unchanged since the previous verification (9 `frozen=True`). Platform changes only touch the cert base class |
| 3 | SC3 / DATA-02: one steady cycle = one `GET /api/rawdata`; version/entrypoints at setup; hourly + post-failure version re-check; entrypoints only on start-date change; 404 fallback follows X-Next-Page without truncation | ✓ VERIFIED | test_request_budget_matrix rows (1)-(5) are unchanged and pass. Rows (6)-(13) add the fallback and re-probe. It also passes on HA 2026.3.0 / aiohttp 3.13.3 |
| 4 | SC4 / DATA-03: auth none/basic/bearer, per-request header, no credential leaks | ✓ VERIFIED (regression check) | `Auth` is unchanged. test_credentials_never_leak gains a request-construction scenario |
| 5 | SC4 / DATA-04: the client raises only TraefikProxyApiError subclasses; coordinator maps to ConfigEntryAuthFailed / UpdateFailed; no asserts | ✓ VERIFIED (gap closed) | See the WR-02 evidence above. AST assert count in the package is 0. test_request_construction_error_retries_setup_without_traceback covers SETUP_RETRY with no traceback |
| 6 | SC5 / DATA-05: typed TraefikRuntimeData; no `getattr(..., None)`; runtime_data before first refreshes; single client owner | ✓ VERIFIED (regression check) | data.py and `__init__.py` are unchanged. grep finds no `getattr(..., None)` |
| 7 | SC5 / DATA-06: snapshot with aggregates, `always_update=False`, no notifications on equal snapshots | ✓ VERIFIED | `coordinator.py:103`. test_equal_snapshots_do_not_notify_listeners and test_switch_back_to_rawdata_publishes_no_change pass |
| 8 | Phase goal / SC5: user-visible entities keep working unchanged, including the cert entities | ✓ VERIFIED (gap closed) | test_cert_entity_state.py (8 tests) plus test_platforms_real_fixtures.py on both generations |
| 9 | Entity classes, unique_ids, entity_ids, names, entity set unchanged; no backend URL/IP in attributes | ✓ VERIFIED | The 04-07 diff of sensor.py and binary_sensor.py touches only the base class and the super() call |
| 10 | (backstop 04-01) Re-running the capture is byte-identical except time-varying fields | ⚠️ insufficient_spec | Needs Docker and a live capture. Routed to human |
| 11 | (backstop 04-05) Replacing the client through the options listener during an in-flight refresh never mixes credentials | ✓ VERIFIED (directly observed) | Verifier scratch test, paginated, token `k`. In the first page response the test changed the entry data to `NEWTOKEN`, which made the listener swap the client. Results: all 4 in-flight requests sent `Bearer k`, all 5 next-cycle requests sent `Bearer NEWTOKEN`, and `runtime_data.client` was replaced |
| 12 | (04-07) Cert entities are cert-coordinator listeners; availability depends only on the cert coordinator; a main cycle never triggers a TLS probe | ✓ VERIFIED | test_cert_availability_follows_cert_coordinator_only, test_main_cycles_never_probe_certificates, test_cert_notifications_do_not_grow_listeners (6 listeners stable) |
| 13 | (04-08) User and reconfigure steps reject userinfo URLs without a request; reauth and YAML map the construction error to `invalid_url` | ✓ VERIFIED | test_user_step_rejects_userinfo_url, test_reconfigure_rejects_userinfo_url, test_reauth_confirm_userinfo_url_with_token_maps_construction_error, test_reauth_confirm_userinfo_url_without_token_succeeds, test_yaml_step_userinfo_url_with_token_maps_construction_error |
| 14 | (04-09, M27) The paginated fallback is revocable: the hourly re-check retries `/api/rawdata` once, success switches back, at most one extra rawdata request per hour, no timer | ✓ VERIFIED (coincidental-reliance) | Matrix rows (8)-(13) cover the boundary at 1 h - 1 s / 1 h, the probe 404, the post-failure re-check that arms no probe, and the switch back. Probe unit tests cover success, 404, empty, auth, other failures, no-op and overlap. The targeted condition was reproduced by the verifier (see the WR-09/WR-10 assessment) |
| 15 | (backstop 04-07) Cert entity state after one notification does not depend on listener order | ✓ VERIFIED (directly observed) | Verifier scratch test: reversing `cert_coordinator._listeners` and replaying the same rows gave HA states and attributes identical to forward order |
| 16 | (backstop 04-08) Concurrent requests on one client cannot mix credentials when a request-construction error occurs | ✓ VERIFIED (directly observed) | Verifier scratch test: 20 interleaved `async_get_version` calls on two clients (`AAA` / `BBB`), with every other request raising aiohttp's construction ValueError. Sent headers were exactly `[AAA, BBB] * 10`, all errors were `TraefikProxyInvalidUrlError`, no token appeared in any message, and the Auth objects were untouched |

**Score:** 15/16 truths verified (0 present-but-behavior-unverified; 1 insufficient_spec routed to human; 0 failed)

### WR-09 / WR-10 assessment (M27 must-have "the paginated fallback is revocable")

I ran a verifier scratch test on an isolated copy of the suite, with real `TraefikProxyCoordinator` cycles, freezer time and 5-minute cycles.

| Scenario | Result |
|---|---|
| Rawdata mode, one restart-window cycle where every `/api/*` path answers 404, then healthy | That cycle fails, and `_paginated` becomes **True** although the pages failed too (WR-10 confirmed). It switches back to rawdata after **65 min** of healthy cycles: the post-failure re-check resets the clock, and the next hourly re-check probes successfully |
| Paginated, rawdata healthy again, a failing cycle (404 or 500) every **50 min** for 6 h | **0 probes, still paginated** (WR-09 confirmed) |
| Same, every **55 min** or **70 min** with 500 | Switched back at 60 min and stayed in rawdata |
| Same, every 55 or 70 min with all-404 | Switched back at 60 min, then re-flipped by each all-404 cycle (WR-10) and recovered again an hour later |

**Judgement: the must-have is achieved; WR-09 and WR-10 are non-blocking warnings, not gaps.**

**Why it is achieved:**
- M27 targets one specific case: "a 404 during a Traefik restart would otherwise cost 3× requests **permanently**". That case is now bounded at about one hour after recovery, and the same mechanism keeps working on later restarts.
- Every literal 04-09 must-have holds. Notably, probes stay at least `VERSION_RECHECK_INTERVAL` apart, and a post-failure re-check arms no probe (W24 chose this deliberately).
- ROADMAP SC3 and DATA-02 do not require revocability at all.

**Why the weaknesses do not block:**
- Starvation (WR-09) needs a compound condition: a spurious switch to pagination plus failed cycles recurring at intervals under one hour.
- Even then the cost is request volume (3 list endpoints plus pages instead of 1 request), not wrong data.

**Why they still need a follow-up:**
- The revocation silently relies on an undeclared precondition, so it is recorded as coincidental-reliance.
- No later phase carries WR-09 or WR-10. The orchestrator should either fix them now (both fixes are a few lines; see 04-REVIEW.md) or add them to a ROADMAP carry-over block, for example Phase 5 (next to WR-04, which shares the paginated-mode exposure) or Phase 7.

### Advisory (new scope)

| # | Finding | Category | Why non-blocking |
|---|---------|----------|------------------|
| 1 | WR-09: probe starvation under sub-hourly failures | other | Reproduced. The targeted restart case is bounded, and the cost is request volume only |
| 2 | WR-10: pagination committed before the pages succeed | other | Reproduced. The cost is bounded at about 1 h per restart window |
| 3 | IN-09: `InvalidUrl(url)` carries the userinfo password in `exc.args` | security | Never logged. All 4 catch sites set `errors["base"]` only. The client error itself is clean |
| 4 | IN-08: a stored userinfo URL plus token retries setup forever | other | Intended. Phase 7 auth selector |
| 5 | IN-10: `urlparse` ValueError in `_check_url_shape` | other | Pre-existing config-flow path. The client contract is unaffected |
| 6 | IN-11: redundant `_coordinator` alias on cert entities | other | Refactor hazard only |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `custom_components/traefik_proxy/entity.py` | Generic base, `TraefikProxyEntity`, `TraefikProxyCertEntity` | ✓ VERIFIED | Wired from sensor.py and binary_sensor.py. Previous wiring defect fixed |
| `custom_components/traefik_proxy/sensor.py` / `binary_sensor.py` | Cert classes bound to the cert coordinator | ✓ VERIFIED | |
| `custom_components/traefik_proxy/api.py` | ValueError mapping; `request_rawdata_probe`, `_probe_rawdata` | ✓ VERIFIED | WR-10 noted |
| `custom_components/traefik_proxy/coordinator.py` | Probe armed on the hourly re-check only | ✓ VERIFIED | WR-09 noted |
| `custom_components/traefik_proxy/config_flow.py` | `allow_userinfo` strict default | ✓ VERIFIED | IN-09 / IN-10 noted |
| `tests/test_cert_entity_state.py` | Full-setup HA-state tests | ✓ VERIFIED | 8 tests |
| `.planning/phases/04-data-layer-correct-lean/04-CONTEXT.md` | D-07 amendment (M27) | ✓ VERIFIED | "Amended (M27, 2026-11-14, plan 04-09)" present |
| Plans 01-06 artifacts | (see previous report) | ✓ VERIFIED | Regression: verify.artifacts 01 8/8, 02 3/3, 03 3/3, 04 7/7, 05 4/4, 06 5/5 |

gsd-tools `verify.artifacts`: 07 4/4, 08 4/4, 09 5/5.

### Key Link Verification

gsd-tools `verify.key-links`: 07 3/3, 09 2/2, 08 2/4. The two 04-08 misses are tool parse failures: the `from:` field holds a path plus step names. I checked both by hand (rows marked "manual" below). Plans 01-06: all WIRED, unchanged.

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| Cert entities | CertCoordinator | `TraefikProxyCertEntity` → `CoordinatorEntity.__init__(coordinator)` | ✓ WIRED | Previously NOT_WIRED. Proven by HA-state tests |
| entity.py `_sw_version` | main snapshot | `entry.runtime_data.coordinator.data` | ✓ WIRED | test_cert_device_keeps_traefik_sw_version |
| config_flow user/reconfigure | `_check_url_shape` | `_validate_input` strict default (lines 285, 435) | ✓ WIRED (manual) | |
| config_flow reauth_confirm/yaml | api.py mapping | `_validate_input(..., allow_userinfo=True)` (lines 372, 318) | ✓ WIRED (manual) | |
| coordinator.py | api.py | `client.request_rawdata_probe()` after the hourly `_async_refresh_version` | ✓ WIRED | coordinator.py:164-171 |
| api.py | `/api/rawdata` | `_rawdata_probe_due` consumed once, cleared before the await | ✓ WIRED | test_one_probe_per_arming_under_overlapping_calls |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| Router / service / entrypoint / count entities | `coordinator.data.*` | `/api/rawdata` (or pages) → parse → `TraefikSnapshot` | Yes (captured fixtures) | ✓ FLOWING |
| Cert expiring binary_sensor / cert timestamp sensor | `cert_coordinator.data[host]`, `threshold_days` | TLS probe cache, options | Yes. State is rewritten on every cert-coordinator notification | ✓ FLOWING (was STATIC after setup) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full suite (run once) | `.venv/bin/pytest -q` | 520 passed | ✓ PASS |
| Lint / format / types | `ruff check`, `ruff format --check`, `mypy --strict custom_components` | clean, 33 formatted, 13 files no issues | ✓ PASS |
| HA 2026.3.0 compatibility (gap-closure modules) | ha2603-venv pytest on test_cert_entity_state, test_api, test_coordinator, test_config_flow, test_reconfigure | 171 passed (HA 2026.3.0, aiohttp 3.13.3) | ✓ PASS |
| WR-02 reproduction | scratch script, real aiohttp session, 3 userinfo URL forms × 4 methods | all `TraefikProxyInvalidUrlError "<path>: ValueError"` | ✓ PASS |
| Backstops 04-05 / 04-07 / 04-08 | scratch tests on an isolated suite copy | 3 passed (see truths 11, 15, 16) | ✓ PASS |
| WR-09 / WR-10 | scratch tests on an isolated suite copy | Behaviour as tabled above | ⚠️ confirmed (non-blocking) |

All scratch files live outside the repository, in the verifier scratchpad. No source file was modified.

### Probe Execution

Step 7c: not applicable. No `scripts/*/tests/probe-*.sh` exists, and the phase declares no probes.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DATA-01 | 04-03, 04-04 | Parse once into frozen models; platforms never inspect raw dicts | ✓ SATISFIED | Truth 2 |
| DATA-02 | 04-04, 04-06, 04-09 | One rawdata request per cycle; setup/hourly/restart rules; paginated fallback | ✓ SATISFIED | Truths 3, 14 (WR-09/WR-10 advisory) |
| DATA-03 | 04-05 | Auth none/basic/bearer; per-request header; no leaks | ✓ SATISFIED | Truths 4, 11 |
| DATA-04 | 04-05, 04-08 | Only TraefikProxyApiError subclasses; no assert | ✓ SATISFIED | Truth 5 (previously PARTIAL) |
| DATA-05 | 04-02 | Typed TraefikRuntimeData | ✓ SATISFIED | Truth 6 |
| DATA-06 | 04-04, 04-07 | TraefikSnapshot with aggregates; `always_update=False` | ✓ SATISFIED | Truths 7, 8 |
| DATA-07 | 04-01, 04-05, 04-06 | Real, redacted, regenerable fixtures | ✓ SATISFIED | Truth 1. Regeneration determinism is the open human item |

All 7 IDs are claimed by plans, and none is orphaned. REQUIREMENTS.md is out of sync with this report:
- DATA-06 is checked `[x]`, and its traceability row says "Complete".
- DATA-01..05 and DATA-07 are `[ ]`, and their rows say "Gaps Found".

The orchestrator should update all seven together. They are all satisfied, and DATA-07's regeneration check is still a pending human item. I did not edit REQUIREMENTS.md.

### Prohibitions

| Prohibition | Tier | Enforcement evidence | Disposition |
|-------------|------|----------------------|-------------|
| 04-01: no private IP/hostname/credential in fixtures; no test starts Docker | test | test_fixture_redaction.py; collect exit 5 | verified |
| 04-04 / 04-05: no backend URL/IP; no credential in log/exception/repr; no session default Authorization; no foreign host | test | as in the previous report; suite green | verified |
| 04-07: must not hide or freeze a cert alarm behind main-coordinator state | test | test_cert_availability_follows_cert_coordinator_only, test_cert_cycle_updates_expiring_binary_sensor_state (unchanged main cycle) | verified |
| 04-07: a main cycle must not trigger a TLS probe | test | test_main_cycles_never_probe_certificates | verified |
| 04-08: must not accept userinfo in newly entered URLs | test | test_user_step_rejects_userinfo_url, test_reconfigure_rejects_userinfo_url | verified |
| 04-08: no URL/userinfo/credential in the request-construction error message | test | test_credentials_never_leak (request-construction id), test_userinfo_url_with_bearer_token_raises_invalid_url_error | verified for the client error. The flow-level `InvalidUrl(url)` still carries the URL in its args but is never surfaced (IN-09, advisory) |
| 04-09: at most one extra rawdata request per hour; no background/timer probing | test | matrix rows (8)-(12); test_one_probe_per_arming_under_overlapping_calls; no task or timer in api.py | verified |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| custom_components/traefik_proxy/coordinator.py | 135-171 | Probe clock shared with the post-failure re-check (WR-09) | ⚠️ Warning | Probe starvation under sub-hourly failures |
| custom_components/traefik_proxy/api.py | 311-321 | `_paginated = True` before the pages succeed (WR-10) | ⚠️ Warning | About 1 h of paginated reads per restart window |
| custom_components/traefik_proxy/config_flow.py | 156, 158, 193 | `InvalidUrl(url)` carries credentials in args (IN-09) | ℹ️ Info | Latent leak, none today |
| custom_components/traefik_proxy/entity.py | 16-17 | `if TYPE_CHECKING: pass` dead block (IN-07) | ℹ️ Info | none |
| custom_components/traefik_proxy/__init__.py | 260 | Discarded update-listener remover (WR-03) | ℹ️ Info (pre-existing; Phase 7 SC2) | listener leak |

No TBD/FIXME/XXX/TODO/HACK markers in the package or the new test module.

### Human Verification Required

#### 1. Fixture re-capture determinism (04-01 backstop)

**Test:** With Docker available, run `uv run python tests/traefik/capture.py` twice, then `git diff --stat tests/fixtures tests/traefik/dynamic/bulk.yml`.
**Expected:** Only time-varying fields (startDate and similar) differ, and bulk.yml is unchanged.
**Why human:** This is a non-inferable backstop truth. It needs live containers, and the verifier must not start services.

The previous report's second human item (04-05 client swap) is now closed by direct observation (truth 11).

### Gaps Summary

There are no remaining gaps. Both blockers from the previous verification are closed in code and proven at HA-state level. No regression was found in the previously verified truths.

The phase goal is achieved:
- real captured fixtures
- frozen models
- one rawdata request per cycle
- a paginated fallback without truncation, now revocable
- the typed runtime data
- a snapshot coordinator with change-only notifications
- unchanged user-visible entities, cert entities included
- the client error taxonomy without holes

Two items need a decision. Neither one blocks:
1. Run the Docker re-capture check, or accept it.
2. Fix WR-09 and WR-10 now, or add them to a ROADMAP carry-over. They are currently untracked by any later phase.

---

_Verified: 2026-11-14T02:48:58Z_
_Verifier: Claude (gsd-verifier)_
