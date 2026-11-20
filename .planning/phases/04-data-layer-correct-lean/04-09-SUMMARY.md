---
phase: 04-data-layer-correct-lean
plan: 09
subsystem: api
tags: [traefik, rawdata, pagination, fallback, request-budget, coordinator, gap-closure, home-assistant]

requires:
  - phase: 04-06
    provides: "rawdata read with paginated fallback on 404, hourly version re-check, test_request_budget_matrix"
  - phase: 04-08
    provides: "api.py state after the request-construction ValueError mapping (built on, no overlap)"
provides:
  - "api.py: TraefikProxyApiClient.request_rawdata_probe() and _probe_rawdata(); a one-shot rawdata probe while paginated, cleared before the await"
  - "coordinator.py: _recheck_interval_elapsed() shared by _version_due(); probe armed only by the regular hourly version re-check"
  - "tests: matrix rows (6)-(13) incl. (10a)/(10b), 7 probe unit tests (11 cases), switch-back invariant test"
  - "04-CONTEXT.md: D-07 amendment (M27)"
affects: [phase-05-entity-model, phase-08-changelog]

actuals:
  tokens: 5364
  tasks: 2
  commits: 3
plan_head_before: e136a7862452ef5348b8cc882be24e98fb09d0b4
plan_head_after: a93762a35d2632f003c67e10b53ddee29218b145

tech-stack:
  added: []
  patterns:
    - "Coordinator owns cadence (dt_util.utcnow, freezer-testable); the client only consumes a one-shot flag the coordinator arms"
    - "One-shot flag cleared synchronously before the first await, so overlapping callers consume one arming once"
    - "Opportunistic probe: auth errors propagate, every other failure falls back to the known-good path in the same call"

key-files:
  created: []
  modified:
    - custom_components/traefik_proxy/api.py
    - custom_components/traefik_proxy/coordinator.py
    - tests/test_api.py
    - tests/test_coordinator.py
    - .planning/phases/04-data-layer-correct-lean/04-CONTEXT.md

key-decisions:
  - "Paginated fallback is revocable (M27, amends D-07): the hourly version re-check retries /api/rawdata once while paginated; at most one extra rawdata request per hour"
  - "The probe is armed only when the re-check interval has elapsed, never by a post-failure re-check inside it"
  - "Probe auth errors propagate at once; any other probe failure keeps the pages and serves the same cycle from them"

patterns-established:
  - "Coordinator-armed, client-consumed one-shot probes; no background task or timer in the client"

requirements-completed: []

coverage:
  - id: D1
    description: "Paginated client returns to one GET /api/rawdata per cycle after the hourly re-check (rows 6, 7, 11, 12, 13 of the request budget matrix)"
    requirement: DATA-02
    verification:
      - kind: integration
        ref: "tests/test_coordinator.py#test_request_budget_matrix"
        status: pass
    human_judgment: false
  - id: D2
    description: "Request budget boundaries: no probe at 1 h - 1 s, probe at exactly 1 h (404 costs one extra request), no probe on a post-failure re-check inside the interval (rows 8, 9, 10, 10a, 10b)"
    requirement: DATA-02
    verification:
      - kind: integration
        ref: "tests/test_coordinator.py#test_request_budget_matrix"
        status: pass
    human_judgment: false
  - id: D3
    description: "Probe outcomes: success switches back, 404 stays paginated once, empty payload switches back, no-op in rawdata mode, 401/403 propagate with no page request, 500/connection/shape/invalid JSON read the pages"
    requirement: DATA-02
    verification:
      - kind: unit
        ref: "tests/test_api.py#test_rawdata_probe_success_switches_back"
        status: pass
      - kind: unit
        ref: "tests/test_api.py#test_rawdata_probe_404_stays_paginated_once"
        status: pass
      - kind: unit
        ref: "tests/test_api.py#test_rawdata_probe_empty_payload_switches_back"
        status: pass
      - kind: unit
        ref: "tests/test_api.py#test_request_rawdata_probe_is_noop_in_rawdata_mode"
        status: pass
      - kind: unit
        ref: "tests/test_api.py#test_rawdata_probe_auth_error_propagates"
        status: pass
      - kind: unit
        ref: "tests/test_api.py#test_rawdata_probe_other_failures_read_pages"
        status: pass
    human_judgment: false
  - id: D4
    description: "One probe per arming under two overlapping async_get_state calls (flag cleared before the await)"
    requirement: DATA-02
    verification:
      - kind: unit
        ref: "tests/test_api.py#test_one_probe_per_arming_under_overlapping_calls"
        status: pass
    human_judgment: false
  - id: D5
    description: "Switching back to rawdata with an unchanged Traefik state publishes an equal snapshot and notifies no listener"
    requirement: DATA-02
    verification:
      - kind: integration
        ref: "tests/test_coordinator.py#test_switch_back_to_rawdata_publishes_no_change"
        status: pass
    human_judgment: false
  - id: D6
    description: "D-07 carries the M27 amendment; DATA-02 and ROADMAP SC3 wording needed no change"
    verification:
      - kind: other
        ref: "grep -n 'Amended (M27' .planning/phases/04-data-layer-correct-lean/04-CONTEXT.md; grep -c lifetime .planning/REQUIREMENTS.md"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-11-14
status: complete
---

# Phase 4 Plan 09: Revocable paginated fallback (WR-01, M27) Summary

**A client that fell back to the paginated list endpoints after a rawdata 404 now retries `GET /api/rawdata` once on the hourly version re-check and returns to one request per cycle on success, with at most one extra rawdata request per hour.**

## Performance

- **Duration:** about 6 min
- **Started:** 2026-11-14T02:22:11Z
- **Completed:** 2026-11-14T02:28Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- `TraefikProxyApiClient.request_rawdata_probe()` arms a one-shot rawdata probe while paginated (no-op in rawdata mode). `async_get_state` clears the flag before the probe request is awaited. A parsed payload clears `_paginated`. A 401/403 raises `TraefikProxyAuthError`. Any other failure falls back to `_get_state_paginated()` in the same call.
- `TraefikProxyCoordinator._recheck_interval_elapsed()` is shared by `_version_due()` with unchanged semantics. `_async_update_data` computes it before the re-check and arms the probe only after a successful re-check whose interval had elapsed, so a post-failure re-check inside the interval never probes.
- The request budget matrix now covers the whole cycle 404 -> pages -> hourly probe 404 (one extra request) -> pages -> failed page -> post-failure re-check without probe -> rawdata back but before the hour (no probe) -> hourly probe 200 -> one rawdata request per cycle. Rows (1)-(5) and the final rawdata hourly row are unchanged.
- The 04-06 must-have truth "never requests /api/rawdata again for its lifetime" is **superseded by M27**. D-07 in 04-CONTEXT.md carries the amendment. REQUIREMENTS.md DATA-02 and ROADMAP Phase 4 SC3 never said "lifetime", so they are unchanged (the only ROADMAP match is the Phase 5 goal line).

## Measured request counts (for the Phase 8 CHANGELOG)

v3.7 capture, per_page 100 (routers 2 pages, services 1, middlewares 1):

| Scenario | Requests per cycle | Paths |
|---|---|---|
| Steady rawdata (rows 2, 13) | 1 | `/api/rawdata` |
| Steady paginated (rows 7, 8, 10, 11) | 4 | routers x2, services, middlewares |
| Rawdata 404 fallback (row 6) | 5 | `/api/rawdata` + 4 pages |
| Hourly re-check, probe 404 (row 9) | 6 | `/api/version`, `/api/rawdata`, 4 pages |
| Hourly re-check, probe 200 (row 12) | 2 | `/api/version`, `/api/rawdata` |
| Post-failure re-check inside the interval (row 10b) | 5 | `/api/version` + 4 pages (no probe) |

## Task Commits

1. **Task 1 (tracer): rawdata 404 -> paginated -> hourly probe -> rawdata 200 -> one request per cycle**
   - RED `87061f6` test(04-09): add failing rawdata re-probe rows to the request budget matrix
   - GREEN `ad01b8a` fix(04-09): retry /api/rawdata on the hourly re-check while paginated
   - Tracer gate (auto mode, `auto_advance: true`): `<verify>` re-run after the commit passed (2 tests; mypy --strict clean). Continued with expansion.
2. **Task 2: boundary rows, probe outcome tests, overlap test, switch invariant, D-07 amendment, gates**
   - `a93762a` test(04-09): cover rawdata re-probe outcomes, budget boundaries and the D-07 amendment

## TDD Gate Compliance

- **RED** (`87061f6`): `test_request_budget_matrix` ran with `--junitxml` and the record went through `gsd-tools check tdd-red-evidence`, which returned `RED_EVIDENCE_OK` (format junit, target test failed, exit 1). Semantic assessment: rows (6), (7) and (11) passed. The target failed on the row (12) assertion: `At index 1 diff: '/api/http/routers' != '/api/rawdata'` (the hourly cycle read the pages instead of retrying rawdata). That is the planned WR-01 reproduction, not a setup or collection fault.
- **GREEN** (`ad01b8a`): the matrix and `test_rawdata_404_switches_to_pages_once` pass. The commit type is `fix(04-09):` as the plan prescribes for a gap-closure fix.
- **Task 2** adds coverage on top of the Task 1 behaviour, so its tests pass when written, as the plan intends: "no further production behaviour beyond Task 1". Negative control for the overlap test: with the flag cleared *after* the await (temporary mutation of api.py, then restored), `test_one_probe_per_arming_under_overlapping_calls` failed. With the shipped code it passes.
- No REFACTOR commit was needed.

## Files Created/Modified

- `custom_components/traefik_proxy/api.py`: `_rawdata_probe_due`, rewritten `_paginated` comment (no "lifetime"), `request_rawdata_probe()`, `_probe_rawdata()`, probe branch and docstring in `async_get_state`
- `custom_components/traefik_proxy/coordinator.py`: `_recheck_interval_elapsed()`, probe arming in `_async_update_data`, one sentence in the class docstring
- `tests/test_coordinator.py`: matrix rows (6)-(13) incl. (10a)/(10b), `monkeypatch` fixture and page path list in the matrix, `test_switch_back_to_rawdata_publishes_no_change`, docstring of `test_rawdata_404_switches_to_pages_once`
- `tests/test_api.py`: helpers `_page_paths`, `_paginated_client`, `_restub_rawdata`, 7 probe tests (11 cases), imports `asyncio` and `AiohttpClientMockResponse`
- `.planning/phases/04-data-layer-correct-lean/04-CONTEXT.md`: D-07 amendment line (M27)

## Gate Results

- `.venv/bin/pytest -q`: 520 passed (508 before the plan)
- `.venv/bin/ruff check custom_components tests`: all checks passed
- `.venv/bin/ruff format --check custom_components tests`: 33 files already formatted
- `.venv/bin/mypy --strict custom_components`: no issues in 13 source files
- HA 2026.3.0 venv `~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`: 520 passed
- Acceptance greps: `def request_rawdata_probe` 1 line; `request_rawdata_probe()` in coordinator.py 1 line; `def _recheck_interval_elapsed` 1 line; `lifetime` in api.py 0; `create_task|call_later|async_track_time` in api.py/coordinator.py 0; `_refresh_paths(hass, aioclient_mock, coordinator)` 18 (>= 17); `def test_switch_back_to_rawdata_publishes_no_change` 1; probe test defs 7; `Amended (M27` 1 line; `lifetime` in REQUIREMENTS.md 0; ROADMAP `lifetime` only on the Phase 5 goal line (302); `test(04-09)` commit before `fix(04-09)`.

## Decisions Made

- The plan's decisions table was implemented as written: the coordinator arms the probe, the client consumes it; probes are armed only on an elapsed interval; non-auth probe failures keep the pages; auth failures propagate; no arming on restart detection; no version probe before the first flip; COVERAGE.md unchanged. W24 and W25 are honoured.

## Worker Decisions

- `_recheck_interval_elapsed()` returns False when no version check has succeeded yet. Reason: there is no last successful check to measure from, and `_version_due()` already handles that case first. Alternative: assert that the timestamp is set.
- `_probe_rawdata` re-raises `TraefikProxyAuthError` in its own `except` clause before the broader `TraefikProxyApiError` clause. Reason: makes the auth carve-out explicit and readable. Alternative: an `isinstance` check inside one `except` clause.
- Probe debug logs name only the path, the outcome and the exception type. Reason: no response body or credentials in logs. Alternative: log the HTTP status.
- `TraefikProxyInvalidUrlError` on the probe counts as a non-auth failure and falls back to the pages, as the plan's taxonomy implies. The pages then raise the same error. Reason: one rule for every non-auth error. Alternative: propagate URL errors directly.
- The overlap test uses an aioclient_mock `side_effect` that yields to the loop three times before it returns a 404 `AiohttpClientMockResponse`. Reason: without a real suspension the first call would finish before the second starts, and the test could not tell "clear before await" from "clear after await". A mutation check confirmed that it can now. Alternative: an `asyncio.Event` handshake.
- Test helpers `_paginated_client` and `_restub_rawdata` in test_api.py. Reason: 6 of the 7 probe tests share the same setup. Alternative: inline the setup in each test.
- Extra assertions beyond the behavior block: the success test checks that a further call requests rawdata only; the empty-payload test checks the path list; the switch-back test checks `last_update_success`. Reason: they pin the request budget at each step. Alternative: assert only the listed facts.
- RED evidence came from pytest `--junitxml` (JUnit adapter). The record was written into the project directory only for the classifier call, then moved to the session scratchpad and not committed. Reason: the classifier refuses paths outside the project, and the record is not a project artifact. Alternative: commit the record.
- The SUMMARY is committed on its own before the STATE/ROADMAP update commit. Reason: the orchestrator requires SUMMARY Write -> commit with no step in between, and `roadmap update-plan-progress` counts SUMMARY files on disk. Alternative: one combined docs commit as in 04-08.
- REQUIREMENTS.md is untouched (DATA-02 not marked complete) and `requirements-completed: []`. Reason: orchestrator rule; the phase is re-verified after all gap plans. Alternative: the executor protocol's mark-complete step.

## Deviations from Plan

None. The plan was executed as written. The plan's verify commands use `uv run`; the gates ran through the same project `.venv` binaries (`.venv/bin/pytest`, `.venv/bin/mypy`, `.venv/bin/ruff`), as the orchestrator's project rules prescribe.

## Issues Encountered

- A first full-suite run after the GREEN commit used `-p no:logging` to keep the output short and reported 18 errors. The cause was the missing `caplog` fixture, which that flag disables; no code was at fault. A re-run with the project defaults passed 508 tests at `ad01b8a`. No code change was needed.

## Known Stubs

None.

## User-visible changes (Phase 8 CHANGELOG)

- If Traefik briefly answers 404 on `/api/rawdata` (for example while it restarts), the integration falls back to the paginated list endpoints as before. It now switches back to the single `/api/rawdata` request at the next hourly version check instead of staying on the pages until Home Assistant restarts. Cost: at most one extra `/api/rawdata` request per hour while paginated (6 instead of 5 requests in that cycle on the v3.7 capture; 1 request per cycle after the switch back instead of 4).

## Next Phase Readiness

- All three gap plans (04-07, 04-08, 04-09) are summarized. Phase 4 is ready for re-verification (WR-01 closed).

## Self-Check: PASSED

- Files: all 5 modified files exist; SUMMARY at `.planning/phases/04-data-layer-correct-lean/04-09-SUMMARY.md`
- Commits: `87061f6`, `ad01b8a`, `a93762a` are ancestors of HEAD
- TDD gate: `test(04-09)` `87061f6` precedes `fix(04-09)` `ad01b8a`
