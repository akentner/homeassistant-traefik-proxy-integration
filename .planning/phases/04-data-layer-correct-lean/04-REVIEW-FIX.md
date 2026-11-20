---
phase: 04-data-layer-correct-lean
fixed_at: 2026-11-14T02:58:06Z
review_path: .planning/phases/04-data-layer-correct-lean/04-REVIEW.md
iteration: 1
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 4: Code Review Fix Report

**Fixed at:** 2026-11-14T02:58:06Z
**Source review:** .planning/phases/04-data-layer-correct-lean/04-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 2 (WR-09, WR-10; fix_scope `critical_warning`, binding decision M29)
- Fixed: 2
- Skipped: 0
- Out of scope, untouched: IN-08, IN-09 (Phase 7 per M31), IN-10, IN-11

Both fixes followed TDD: a failing test commit came first, then the fix commit.

## Fixed Issues

### WR-09: The rawdata probe can be starved indefinitely: every post-failure version re-check resets its clock

**Status:** fixed: requires human verification (state-handling logic; covered by the regression rows below)
**Files modified:** `custom_components/traefik_proxy/coordinator.py`, `tests/test_coordinator.py`
**Commits:** `59b301e` (RED test), `293ba84` (fix)
**Applied fix:**
- New coordinator state `_probe_armed_at`. It is set in `_async_setup` together with `_version_checked_at`. After that, only the cycle that arms the probe moves it.
- `_async_update_data` arms the probe when `VERSION_RECHECK_INTERVAL` has passed since `_probe_armed_at`. This check is separate from `_version_due()`. A post-failure version re-check therefore neither arms the probe nor postpones it.
- The arming comes after the version re-check. If that re-check fails, the cycle raises before arming and the clock does not move.
- `_recheck_interval_elapsed()` was replaced by a module-level `_interval_elapsed(since)`, which the version check and the probe check share. Semantics are unchanged.
- The class docstring now describes the probe's own clock.

**Regression rows in `test_request_budget_matrix`:**
- (14) Another rawdata 404 switches the client to the pages again.
- (15) For almost five hours, a page fails every 50 minutes. Each failure is followed by a recovery cycle that re-checks the version. Every cycle is asserted exactly. Probes run at minutes 60, 120, 180 and 240, one per hour. The first one is an hour after the switch, despite the failure at minute 50. No probe runs in a failing or recovering cycle.
  - RED on the old code: `AssertionError: 60`, because the old code read the pages instead of `["/api/rawdata", *pages]`.
- (16) Rawdata is back. The next hourly probe switches back, although the last version check is only 50 minutes old.
- (17) One rawdata request per cycle.

### WR-10: The switch to pagination is committed even when the page reads fail in the same cycle (outage-wide 404)

**Status:** fixed: requires human verification (state-handling logic; covered by the regression tests below)
**Files modified:** `custom_components/traefik_proxy/api.py`, `tests/test_api.py`, `tests/test_coordinator.py`
**Commits:** `afb3650` (RED tests), `1c35145` (fix)
**Applied fix:**
- In `async_get_state`, a rawdata 404 now reads the pages first and sets `self._paginated = True` only after `_get_state_paginated()` returned.
- If the pages fail as well, the error propagates and the client stays in rawdata mode.
- The `_paginated` comment and the `async_get_state` docstring were updated.
- The docstring of `test_list_endpoint_404_in_paginated_mode_raises_not_found` said "Once paginated". It now says "During the fallback". The assertions are unchanged.

**Regression tests:**
- `tests/test_api.py::test_failed_fallback_keeps_rawdata_mode` checks a rawdata 404 together with a routers page failure, in three cases: 404, 500 and a connection error. In each case `client._paginated` stays `False`, and the next call requests `/api/rawdata` only. RED on the old code: `assert True is False` for all three cases.
- New matrix rows:
  - (18) Restart window: rawdata and routers both answer 404. Paths are `["/api/rawdata", "/api/http/routers"]` and the cycle fails.
  - (19) Traefik is back. The post-failure re-check requests `["/api/version", "/api/rawdata"]`. RED on the old code: it requested `["/api/version", *pages]`.
  - (20) Steady state is `["/api/rawdata"]`.

## Request budget matrix

Rows (1) to (13) and the hourly row after (5) are byte-identical and still pass, so no existing path list changed.

Why rows (3), (5), (9) and (12) are unchanged: in a healthy run the probe clock and the version clock both start at setup. Both advance in the same hourly cycle, so the probe still lands in the version re-check cycle. Rows (10a) and (10b) run at a frozen time, so the probe clock does not elapse there either.

New request counts (v3.7 capture, per_page 100):

| Scenario | Requests | Paths |
|---|---|---|
| Probe in a cycle without a version re-check, 404 (row 15, minutes 60/120/180/240) | 5 | `/api/rawdata` + 4 pages |
| Probe without a version re-check, 200 (row 16) | 1 | `/api/rawdata` |
| Failing page cycle (row 15) | 1 | `/api/http/routers` |
| Post-failure recovery while paginated (row 15) | 5 | `/api/version` + 4 pages |
| All-404 restart cycle (row 18) | 2 | `/api/rawdata`, `/api/http/routers` |
| Recovery after the all-404 cycle (row 19) | 2 | `/api/version`, `/api/rawdata` |

## Decisions not covered by the review or the decisions file

| Decision | Reason | Alternative |
|---|---|---|
| Fixes were made directly in the existing worktree on `feat/marketplace-polish`, without a nested `.claude/worktrees/rf-*` worktree. | The user's CLAUDE.md allows worktrees only under `~/Projekte/_worktrees/…` and removal only on request. The manager required the gates to run from the project root with `.venv`, which a nested worktree lacks. This is the same path as `workflow.use_worktrees=false`. | A nested worktree with a fast-forward merge. That conflicts with the user's worktree rules and has no venv. |
| The probe clock ticks every hour in rawdata mode too, where the arming is a no-op. | This keeps rows (1) to (13) exact and keeps the probe cadence a fixed hourly grid from setup. Probes stay at least one hour apart, and the first probe after a switch comes at most one hour later. | Move the clock only when the client really armed, which needs a return value from `request_rawdata_probe`. A switch long after the last probe would then probe in the very next cycle. That changes rows (7) and (8), and inside a restart window it would most likely just cost another 404. |
| A probe can now run in a cycle without a version re-check: after a post-failure re-check, the two clocks diverge. | M29 and the brief require the probe's own clock. W24 limits the budget to at most 1 extra request per hour, and that still holds. Only W24's wording, "only on the regular hourly version check", is literally narrower. | Force a version re-check whenever the probe is due. That adds a `/api/version` request without any benefit. |
| `_recheck_interval_elapsed()` was removed in favour of a module function `_interval_elapsed(since)`. | One helper for two clocks; no test referenced the old method. | Keep the method and add a second `_probe_due()` method. |
| While the pages keep failing after a rawdata 404, each failing cycle requests `/api/rawdata` again: 1 extra request in a cycle that fails anyway. | This follows directly from WR-10: the mode switches only after the pages worked. | Remember the 404 separately and skip rawdata. That would bring back the sticky state WR-10 removes. |
| The client still switches to the pages when rawdata answers 404 and the pages answer 200. | This is unchanged behaviour (D-07, M27). The probe now reverts it within one hour, even under recurring failures. | Gate the first switch on a version probe. Plan 04-09 rejected this. |

## Verification

All gates ran in the main checkout (`feat/marketplace-polish` worktree root), not in an isolated worktree, so the numbers can be reproduced from this tree:

- `.venv/bin/pytest -q`: 523 passed (520 before: +3 cases of `test_failed_fallback_keeps_rawdata_mode`; the matrix stays one test)
- `.venv/bin/ruff check custom_components tests`: all checks passed
- `.venv/bin/ruff format --check custom_components tests`: 33 files already formatted
- `.venv/bin/mypy --strict custom_components`: no issues in 13 source files
- HA 2026.3 venv `~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`: 523 passed
- Guards:
  - `create_task|call_later|async_track_time` does not occur in `api.py` or `coordinator.py`.
  - Shipped code contains no planning references (WR-/D-/M-/phase).

I did not touch `tests/fixtures`, `tests/traefik`, REQUIREMENTS.md, ROADMAP.md or STATE.md. The working tree also contains changes to `.planning/config.json` and `.planning/phases/04-data-layer-correct-lean/04-UAT.md` and an untracked `.planning/state.json`. None of them came from this fixer, and none were committed.

---

_Fixed: 2026-11-14T02:58:06Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
