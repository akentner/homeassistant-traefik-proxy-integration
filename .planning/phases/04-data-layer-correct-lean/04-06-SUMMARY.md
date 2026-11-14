---
phase: 04-data-layer-correct-lean
plan: 06
subsystem: data-layer
tags: [traefik, rawdata, coordinator, restart-detection, request-budget, fixtures, home-assistant]

requires:
  - phase: 04-01
    provides: "Real v2.11/v3.7 captures (rawdata, version, entrypoints, pages + X-Next-Page)"
  - phase: 04-04
    provides: "Snapshot coordinator, _get_paginated with MAX_PAGES guard, snapshot_from_fixture"
  - phase: 04-05
    provides: "Error taxonomy incl. TraefikProxyNotFoundError, _request core, Auth"
provides:
  - "api.py: async_get_state reads GET /api/rawdata; a 404 there flips the client to the paginated list endpoints for its lifetime (_paginated)"
  - "coordinator.py: VERSION_RECHECK_INTERVAL (1 h), _version_due / _async_refresh_version; entrypoints re-read only when version or start date changed"
  - "tests/conftest.py: stub_traefik (version, entrypoints, rawdata from a capture or overrides); stub_traefik_paginated answers /api/rawdata 404 first"
  - "tests: request budget matrix, fallback request test, cycle error-mapping tests, real-fixture entity proof on v2.11 and v3.7"
affects: [phase-05-entity-lifecycle, phase-06-certificates, phase-07-flows, phase-08-changelog]

actuals:
  tokens: 13700
  tasks: 3
  commits: 3
plan_head_before: a7d6366216e466aae219e52bbf743bca6f7d05d5
plan_head_after: a26e3c27c6add0a9d80e97df686caf65568ea3b4

tech-stack:
  added: []
  patterns:
    - "Request-path assertions: exact list of call[1].path per cycle, aioclient_mock.mock_calls.clear() between cycles"
    - "Endpoint override in tests: register the special mock first, then stub_traefik (first match wins)"
    - "Cycle time driven by the freezer fixture + coordinator.async_refresh()"

key-files:
  created:
    - tests/test_platforms_real_fixtures.py
  modified:
    - custom_components/traefik_proxy/api.py
    - custom_components/traefik_proxy/coordinator.py
    - tests/conftest.py
    - tests/test_api.py
    - tests/test_api_pagination.py
    - tests/test_coordinator.py
    - tests/test_init.py
    - tests/test_verify_ssl.py
    - tests/test_reconfigure.py

key-decisions:
  - "04-06: The stored version and its check time are replaced only after a needed entrypoint fetch succeeded, so a restart whose entrypoint fetch failed is detected again on the next cycle"
  - "04-06: A failing version re-check fails the whole cycle (D-16 mapping); the previous snapshot stays published"
  - "04-06: Only a 404 on /api/rawdata triggers the fallback; a rawdata payload of the wrong shape is a TraefikProxyPayloadError, not a fallback"

requirements-completed: [DATA-02, DATA-07]

coverage:
  - id: D1
    description: "One GET /api/rawdata per steady cycle; setup requests exactly version, entrypoints, rawdata"
    requirement: DATA-02
    verification:
      - kind: integration
        ref: "tests/test_coordinator.py#test_rawdata_snapshot_reaches_entities, test_request_budget_matrix"
        status: pass
      - kind: unit
        ref: "tests/test_api.py#test_rawdata_parses_like_the_model_parser"
        status: pass
    human_judgment: false
  - id: D2
    description: "Version re-check hourly and after a failed cycle; entrypoints only on a changed version/start date; equal pair never requests entrypoints"
    requirement: DATA-02
    verification:
      - kind: integration
        ref: "tests/test_coordinator.py#test_request_budget_matrix, test_failed_entrypoint_refetch_is_retried"
        status: pass
    human_judgment: false
  - id: D3
    description: "rawdata 404 switches to the pages once and for the client's lifetime; 401/500 do not fall back; list 404 in paginated mode is NotFound"
    requirement: DATA-02
    verification:
      - kind: integration
        ref: "tests/test_coordinator.py#test_rawdata_404_switches_to_pages_once"
        status: pass
      - kind: unit
        ref: "tests/test_api.py#test_rawdata_404_falls_back_to_pages_and_is_remembered, test_rawdata_other_errors_do_not_fall_back, test_list_endpoint_404_in_paginated_mode_raises_not_found, test_rawdata_unexpected_shape_raises_payload_error; tests/test_api_pagination.py (all cases via the fallback)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Auth errors in any cycle step (state, version re-check, entrypoint re-fetch) start reauth; other API errors keep the entry LOADED on the previous snapshot object"
    requirement: DATA-02
    verification:
      - kind: integration
        ref: "tests/test_coordinator.py#test_cycle_auth_error_starts_reauth[state|version|entrypoints], test_cycle_server_error_keeps_previous_snapshot[state|version|entrypoints]"
        status: pass
    human_judgment: false
  - id: D5
    description: "Existing entity set reports correct states on the v2.11 and v3.7 captures (routers, entrypoints, services incl. lb-mixed 2/1, counts, disabled any-*-failing entities)"
    requirement: DATA-07
    verification:
      - kind: integration
        ref: "tests/test_platforms_real_fixtures.py (5 tests x [v2.11, v3.7])"
        status: pass
    human_judgment: false
  - id: D6
    description: "All full-setup tests use stub_traefik / stub_traefik_paginated; phase-wide gates green on the dev venv and HA 2026.3.0"
    verification:
      - kind: other
        ref: "grep _stub_all_endpoints tests -> none; pytest --collect-only tests/traefik -> exit 5; AST asserts 0; no getattr(..., None); no fetch_all|get_overview|/api/overview; 0 synthetic fixtures"
        status: pass
      - kind: unit
        ref: "uv run pytest -q (481 passed); ha2603-venv python -m pytest -q -o addopts='' tests (481 passed); ruff check, ruff format --check, mypy --strict clean"
        status: pass
    human_judgment: false

duration: 7min
completed: 2026-11-14
status: complete
---

# Phase 4 Plan 06: rawdata request budget and real-fixture proof Summary

**Each steady coordinator cycle is now one `GET /api/rawdata`. The paginated list endpoints serve as a fallback that the client remembers after a rawdata 404. `/api/version` is re-read hourly and after a failed cycle, and `/api/entrypoints` only after a detected Traefik restart. Request-path tests prove this step by step, and the existing entities report correct states on both real capture generations (v2.11, v3.7).**

## Performance

- **Duration:** 7 min (start 2026-11-14T01:08:52Z, end 2026-11-14T01:15:30Z)
- **Tasks:** 3 of 3 (Task 1 tracer, Tasks 2-3 auto)
- **Files:** 10 (1 created, 9 modified)

## Measured request counts (for the Phase 8 CHANGELOG)

Measured by exact path-list assertions in `tests/test_coordinator.py` (v3.7 capture, default options):

| Scenario | Requests | Paths |
|---|---|---|
| Setup | 3 | `/api/version`, `/api/entrypoints`, `/api/rawdata` |
| Steady cycle | 1 | `/api/rawdata` |
| Hourly re-check (no restart) | 2 | `/api/version`, `/api/rawdata` |
| Failed cycle (rawdata 500) | 1 | `/api/rawdata` |
| First cycle after a failure | 2 | `/api/version`, `/api/rawdata` |
| Restart detected (start date changed) | 3 | `/api/version`, `/api/entrypoints`, `/api/rawdata` |
| Fallback setup (rawdata 404, capture pages at per_page 100) | 7 | version, entrypoints, rawdata (404), routers p1+p2, services p1, middlewares p1 |
| Fallback steady cycle (per_page 100) | 4 | routers p1+p2, services p1, middlewares p1; never `/api/rawdata` again |

With the default 15 s interval that is 5 760 cycle requests plus 24 hourly version checks, about 5 784 requests per day per instance. Before Phase 4 it was 34 560 (6 per cycle). In the fallback the production page size is 500, so the v3.7 capture would need 3 requests per cycle.

## Accomplishments

- **api.py (D-07):** `async_get_state()` first sends `GET /api/rawdata` and parses it with `parse_rawdata`. On `TraefikProxyNotFoundError` the client sets `_paginated = True` and logs the path once at debug level. It then reads the three list endpoints in the same call (moved into `_get_state_paginated`, MAX_PAGES guard unchanged). Every other error propagates without a fallback. A rawdata payload of the wrong shape raises `TraefikProxyPayloadError("/api/rawdata", ...)`.
- **coordinator.py (D-14, D-16):** `VERSION_RECHECK_INTERVAL = timedelta(hours=1)`. `_async_setup` records `_version_checked_at`. `_version_due()` returns true when the previous cycle failed (`not last_update_success`, still the previous cycle's value inside `_async_update_data`) or the interval has elapsed. `_async_refresh_version()` re-reads the version and, only when `(version, start_date)` changed, the entrypoints. It stores the new version and check time only after both succeeded. Each step maps `TraefikProxyAuthError` to `ConfigEntryAuthFailed` and any other `TraefikProxyApiError` to `UpdateFailed`. Only HA 2026.3 APIs are used (`dt_util.utcnow`, `_async_setup`).
- **conftest (D-22):** `stub_traefik(aioclient_mock, *, version, base_url, rawdata, version_payload, entrypoints)` serves the three endpoints from the capture or from overrides (`rawdata={}` is an empty Traefik). `stub_traefik_paginated` registers `/api/rawdata` → 404 first, so every paginated scenario goes through the fallback.
- **Tests (D-24):** `test_rawdata_snapshot_reaches_entities` (tracer), `test_rawdata_404_switches_to_pages_once`, `test_request_budget_matrix`, `test_cycle_auth_error_starts_reauth` and `test_cycle_server_error_keeps_previous_snapshot` (each over state / version / entrypoints), `test_failed_entrypoint_refetch_is_retried`, and 6 rawdata unit tests in test_api.py. The new `tests/test_platforms_real_fixtures.py` covers both generations (SC5). test_init, test_verify_ssl and test_reconfigure run on `stub_traefik`, and the leftover `/api/overview` mocks are gone.

## Task Commits

1. **Task 1 (tracer): rawdata-first client, conftest stubs, tracer + fallback + unit tests** - `1cea893` (feat)
2. **Task 2: restart detection, budget matrix, cycle mapping, real-fixture entity proof** - `2ebc823` (feat)
3. **Task 3: migrate test_init / test_verify_ssl / test_reconfigure to stub_traefik** - `a26e3c2` (test)

The tracer gate ran in auto mode: the Task 1 `<verify>` was re-run before expansion (88 passed).

## Verification

- `uv run pytest -q`: 481 passed (456 before the plan)
- HA 2026.3.0 venv (`~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`): 481 passed
- `uv run ruff check custom_components tests`: all checks passed; `uv run ruff format --check custom_components tests`: 32 files already formatted
- `uv run mypy --strict custom_components/traefik_proxy`: no issues in 13 source files
- `! grep -rn '_stub_all_endpoints' tests`: no output (baseline: 4 modules)
- `uv run pytest --collect-only -q tests/traefik`: exit 5
- AST assert count over the package: 0; `getattr(..., None)`: none; `fetch_all|get_overview|/api/overview` in the package: none; synthetic `traefik_*.json` fixtures: 0
- Task acceptance: `/api/rawdata` in api.py (line 37); one `def stub_traefik(`; `_stub_all_endpoints` count 0 in test_coordinator.py; `["/api/rawdata"]` asserted (test_coordinator.py:205); `VERSION_RECHECK_INTERVAL` 3 lines in coordinator.py; one `def test_request_budget_matrix`; 20 `v2.11|v3.7` result lines for the real-fixture module
- Mutation check (not committed): removing the post-failure condition, the hourly interval or the start-date equality each made at least one coordinator test fail
- Raw-dict reads in consumers: only the cert coordinator's host cache and `entry.data` remain (Phase 6 scope, not snapshot reads)
- No Docker containers, networks or volumes were started (the 7 existing containers predate this session, created 2026-11-01..08)

## Decisions Made

See key-decisions above and Worker Decisions below.

## Deviations from Plan

**1. [Ordering] Intermediate commits do not pass the full suite**
- **Found during:** Task 1
- **Issue:** After the rawdata switch, the private stubs in test_init.py, test_verify_ssl.py and test_reconfigure.py registered no `/api/rawdata`, so 11 of their tests failed until Task 3 migrated them. The plan's task split puts that migration in Task 3, and Task 1's `<verify>` covers only the three client/coordinator modules.
- **Fix:** Followed the plan's split. `1cea893` and `2ebc823` pass their own task verify; the full suite is green from `a26e3c2` on. A bisect across these two commits will show these 11 test failures.

**2. [Scope] Only one reload test swaps the payload**
- **Found during:** Task 3
- **Issue:** The plan describes "the two reload tests" that swap the router payload through `side_effect`. Only `test_reload_service_verified_true_when_routers_change` did; the verified-false test used a fixed router list.
- **Fix:** The verified-true test swaps the `/api/rawdata` payload through `side_effect` (registered before `stub_traefik`); the verified-false test uses `stub_traefik(rawdata=_rawdata("stable-router"))`.

**3. [Rule 2 - Correctness] Entrypoint re-fetch failure must not hide the restart**
- **Found during:** Task 2
- **Issue:** If the new version were stored before the entrypoint fetch, a failed fetch would make the next re-check see an equal pair, so the entrypoints would never be refreshed.
- **Fix:** Version and check time are stored only after the fetch succeeded; covered by `test_failed_entrypoint_refetch_is_retried`.
- **Commit:** 2ebc823

**Total deviations:** 3 (1 ordering note, 1 scope note, 1 correctness addition). **Impact:** no scope creep; behaviour matches D-07, D-14, D-16 and D-24.

## Worker Decisions

- The paginated read moved into a private `_get_state_paginated()`, and `async_get_state()` holds only the rawdata branch and the switch. Reason: keeps the try/except around the parsers apart from the fallback logic. Alternative: one inline method.
- A rawdata payload of the wrong shape raises `TraefikProxyPayloadError`; it does not fall back. Reason: D-07 names only the 404, and a shape error means a broken Traefik, not an old one. Alternative: fall back on any rawdata error.
- `_version_due()` is also true when no version or check time is stored. Reason: defensive; such a cycle fetches the version instead of failing with "version not available". Alternative: only the two planned conditions.
- A failing version re-check fails the whole cycle (`UpdateFailed`) instead of continuing with the stored version. Reason: D-16 says "every step uses the mapping", and an auth failure there must start reauth. Alternative: log it and still fetch the state.
- When the `(version, start_date)` pair is equal, the freshly read `TraefikVersion` still replaces the stored one (only a codename difference could change it). Reason: the snapshot always shows the latest version payload. Alternative: keep the old object.
- The cycle mapping tests are parametrized over all three steps (state, version re-check, entrypoint re-fetch) for 401 and 500, not only over a failing state request. Reason: the must-have truth says "any cycle step". Alternative: one 401 and one 500 test on rawdata.
- The matrix also asserts the failing cycle's own paths (`["/api/rawdata"]`) and adds a final hourly step after the restart (no entrypoints again). Reason: proves the stored pair was updated. Alternative: stop at step 5.
- `stub_traefik` has no `skip` parameter; tests override an endpoint by registering their own mock first. Reason: first-match-wins already covers it and keeps the planned signature. Alternative: a `skip=` argument.
- Empty-Traefik tests keep the capture's version and entrypoints (stub defaults), so `test_setup_creates_coordinator_in_runtime_data` now expects `3.7.19` instead of the old synthetic `3.1.4`. Reason: no synthetic payloads (D-22). Alternative: pass a synthetic `version_payload`.
- test_init, test_verify_ssl and test_reconfigure import `MOCK_URL` from conftest instead of their own copy of the same string. Reason: one source for the base URL the stub registers. Alternative: keep the local constants.
- The real-fixture module uses a parametrized async fixture `loaded`. It also asserts that the number of router entities equals the snapshot router count and that the any-*-failing entries are `disabled_by=INTEGRATION`. Reason: proves no extra and no missing router entity, and checks "disabled by default" precisely. Alternative: per-test setup without those checks.
- The rawdata no-fallback unit test is parametrized over 401 and 500 and also checks `client._paginated is False`. A separate rawdata shape-error test was added. Reason: T-04-16 says only a 404 flips the client. Alternative: the single 500 case from the plan.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or trust-boundary surface. T-04-15 is mitigated through `test_request_budget_matrix` with exact path lists. T-04-16 is mitigated because only a rawdata 404 flips the client (401/500 tested) and the paginated path keeps MAX_PAGES.

## Issues Encountered

- `test_reload_service_verified_false_when_no_change_within_budget` and `test_reload_button_async_press_calls_service` each take about 6 s because the reload handler waits out its real 5 s budget. This is pre-existing and goes away when Phase 5 removes the reload feature (ENT-07).
- The deferred `SyntaxWarning` item in deferred-items.md is still marked open, although 04-04 removed its cause. Left for the verifier, as 04-04 and 04-05 noted.
- The open question from 04-05 about redirect handling (`allow_redirects`) still stands for Phase 7/8.

## User Setup Required

None.

## Next Phase Readiness

- Phase 4 is complete: 6 of 6 plans. Phase 5 (entity lifecycle) can rely on the snapshot that is published per cycle and on `stub_traefik` for full-setup tests.
- Phase 6 can add `/api/certificates` (v3.7 capture present) next to the rawdata read without touching the request budget logic.

## Self-Check: PASSED

- FOUND: custom_components/traefik_proxy/api.py, custom_components/traefik_proxy/coordinator.py, tests/conftest.py, tests/test_platforms_real_fixtures.py, tests/test_coordinator.py, tests/test_api.py, tests/test_api_pagination.py, tests/test_init.py, tests/test_verify_ssl.py, tests/test_reconfigure.py
- FOUND commits: 1cea893, 2ebc823, a26e3c2 (ancestors of HEAD; 3 commits since plan_head_before a7d6366)
- All task acceptance criteria and plan-level verification commands re-run after Task 3 and passing
