---
phase: 04-data-layer-correct-lean
reviewed: 2026-11-14T03:04:27Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - custom_components/traefik_proxy/api.py
  - custom_components/traefik_proxy/coordinator.py
  - tests/test_api.py
  - tests/test_coordinator.py
findings:
  critical: 0
  warning: 0
  info: 7
  total: 7
  necessity: 0
status: issues_found
---

# Phase 4: Code Review Report (re-review of the WR-09 / WR-10 fixes)

**Reviewed:** 2026-11-14T03:04:27Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Scope: `git diff cc26dfc..HEAD` on the four listed files (commits `59b301e`, `293ba84`, `afb3650`, `1c35145`), plus the code they call:
- `TraefikProxyApiClient.async_get_state`, `_probe_rawdata` and `request_rawdata_probe`
- `__init__.py` setup and options listener
- HA's `DataUpdateCoordinator` (`_async_setup` runs only from `async_config_entry_first_refresh`, `update_coordinator.py:365`)

I read every changed file in full. The gates pass:
- `pytest tests/test_api.py tests/test_coordinator.py tests/test_api_pagination.py`: 117 passed
- `ruff check`: clean
- `mypy --strict`: 13 files, no issues

I also ran a scratch test on an isolated copy of the suite (since deleted) for three schedules that the matrix does not cover:

| Case | Schedule | Requests in the next cycle(s) |
|---|---|---|
| A | Switch to the pages at minute 59 | Probe at minute 60, one cycle after the switch: `/api/version`, `/api/rawdata`, pages |
| B | Probe and version both due, `/api/version` answers 500 | Failing cycle: `["/api/version"]`, probe flag stays `False`. Recovery cycle: `/api/version`, `/api/rawdata`, pages (probe not lost) |
| C | Probe due, page fails | Probe consumed in the failing cycle: `/api/version`, `/api/rawdata`, `/api/http/routers` |

**Status of the targeted findings:**

| Finding | Status | Evidence |
|---|---|---|
| **WR-09** probe starved by post-failure version re-checks | **Resolved** | `coordinator.py:169-175` arms the probe from its own clock `_probe_armed_at`. Only the setup (`:127`) and the arming cycle (`:175`) move that clock. `_async_refresh_version` (`:163`) moves only `_version_checked_at`. The arming runs after the version re-check, so a failed re-check raises before arming and the clock stays put (case B). Matrix row (15) shows probes at minutes 60, 120, 180 and 240 while a page fails every 50 minutes. Row (16) shows the switch-back with a version check that is only 50 minutes old. |
| **WR-10** pagination committed although the pages failed | **Resolved** | `api.py:315-321` sets `self._paginated = True` only after `_get_state_paginated()` returns. Any exception from the pages leaves the client in rawdata mode. That includes cancellation, because no state is written before the await. `test_failed_fallback_keeps_rawdata_mode` covers 404, 500 and connection errors. Matrix rows (18) to (20) show the restart window recovering to `["/api/version", "/api/rawdata"]`. |

**The fixer's declared trade-offs:**

1. **The probe clock is separate and can fire in a cycle without a version re-check. Probes stay at most one per hour: correct.**
   - The clock is armed only when `utcnow() - _probe_armed_at >= 1h`, and every arming moves it. So arming happens at most once per hour.
   - `request_rawdata_probe()` sets the client flag only while paginated (`api.py:268`).
   - `async_get_state` is awaited with no `await` in between and consumes the flag on its first line (`api.py:305-307`). The flag cannot leak into a later cycle.
   - Request budget: rawdata mode is unchanged (rows 1 to 13 are byte-identical; arming is a no-op there). In paginated mode, a diverged clock adds no requests. The probe and the hourly version request simply land in different cycles, which is still 1 + 1 per hour.
   - Two consequences are not stated precisely in the fix report:
     - The first probe after a switch comes anywhere from one cycle to one hour later (case A), not "an hour after the switch". See IN-12.
     - A successful probe can now switch back without a fresh `/api/version`. The version and entrypoints can therefore stay stale until the next version re-check (at most 1 h). That only matters when rawdata comes back because of a Traefik restart that no failed cycle observed, which is the existing IN-03. Acceptable.
2. **One extra `/api/rawdata` request per failing cycle while the pages keep failing after a rawdata 404: correct and bounded.**
   - It applies only before the first successful switch. Once the client is paginated, failing pages do not request rawdata again (`api.py:326`).
   - During a full restart window the cost actually drops. After the first cycle (`/api/rawdata`, `/api/http/routers`), every following failed cycle stops at the post-failure `/api/version` and never reaches the state fetch.
   - Recovery costs 2 requests instead of `version + 4 pages`.
   - The case that stays +1 per cycle needs rawdata to answer 404 *permanently* while the pages fail *permanently*. In that case the entities are unavailable anyway.

No request-budget regression found.

**Carried info findings:**
- IN-08 and IN-09 are carried into **Phase 7** through ROADMAP (`.planning/ROADMAP.md:403`, commit `440ab67`). They are listed below so the disposition ledger keeps them.
- IN-09, IN-10 and IN-11 live in `config_flow.py`, `sensor.py` and `binary_sensor.py`. Those files are outside this scope but unchanged since `cc26dfc` (`git diff --stat` is empty). I re-checked the cited lines: all four findings are still present.

Earlier findings that are still open or deferred (WR-03 to WR-08, IN-01 to IN-07) are untouched by these commits. They are not re-raised; their disposition rows stay as they are.

Necessity review: I read the rubric from `~/.claude/gsd-core/references/necessity-review.md`. `_interval_elapsed(None)` returns False, and `_probe_armed_at` cannot be `None` at update time in production. That branch narrows `datetime | None`, so it is a type requirement, not an impossible-state guard. No necessity findings.

## Narrative Findings (AI reviewer)

## Info

### IN-08: Request-construction errors on a stored entry retry setup forever with an unactionable reason (carried into Phase 7)

**File:** `custom_components/traefik_proxy/api.py:206-209`, `custom_components/traefik_proxy/coordinator.py:129-132`
**Issue:** Unchanged since the previous review. `TraefikProxyInvalidUrlError` is a `TraefikProxyConnectionError`. A stored entry with URL userinfo plus a token therefore ends in `UpdateFailed`, then `ConfigEntryNotReady`, and setup retries forever. The only reason shown is `/api/version: ValueError`. **Carried into Phase 7 via ROADMAP (`.planning/ROADMAP.md:403`).**
**Fix:** In `_async_setup`, map `TraefikProxyInvalidUrlError` to `ConfigEntryError` with a `url_has_credentials` translation key, or migrate URL userinfo into the Phase 7 basic-auth fields.

### IN-09: `InvalidUrl` carries a credential-bearing URL in its exception args (carried into Phase 7)

**File:** `custom_components/traefik_proxy/config_flow.py:156,158,193`
**Issue:** Unchanged (the file has no diff since `cc26dfc`). `raise InvalidUrl(url)` and `raise InvalidUrl(data[CONF_URL])` keep the `user:pass@` password in `exc.args[0]`. It does not leak today, because every caller catches the exception without logging it. **Carried into Phase 7 via ROADMAP (`.planning/ROADMAP.md:403`).**
**Fix:** `raise InvalidUrl from None`; no caller reads the argument.

### IN-10: `_check_url_shape` lets `urlparse`'s `ValueError` escape

**File:** `custom_components/traefik_proxy/config_flow.py:154,423`
**Issue:** Unchanged. `urlparse("http://[::1")` raises `ValueError: Invalid IPv6 URL`. That aborts the user step with "Unknown error" and a traceback. The reconfigure step hits it even earlier, through `urlparse(...).hostname` at `:423`, before `_validate_input` runs.
**Fix:** Wrap the `urlparse` call in `try/except ValueError: raise InvalidUrl from None`, and run `_check_url_shape` before computing `host` in `async_step_reconfigure`.

### IN-11: Cert entities keep a redundant `_coordinator` alias of `self.coordinator`

**File:** `custom_components/traefik_proxy/sensor.py:466`, `custom_components/traefik_proxy/binary_sensor.py:417`
**Issue:** Unchanged. There are two names for one `CertCoordinator` binding. A refactor that rebinds only one of them brings back the CR-01 class of bug, where entities listen to one coordinator and read from another.
**Fix:** Drop `self._coordinator`, read `self.coordinator` everywhere, and adjust `tests/test_sensor_tls.py:347-348`.

### IN-12: Matrix row (15) and the fix report over-claim the probe timing; three probe-clock edges are untested

**File:** `tests/test_coordinator.py:444-447,457-474`
**Issue:** The row comment says the probe runs "the first one an hour after the switch, and never in a failing or recovering cycle". Both statements describe this test's schedule, not the code:
- **First probe one hour after the switch.** Row (14) switches at the same frozen instant as the arming in row (12), so the switch sits exactly on the probe grid. With a switch off the grid, the first probe comes one cycle later (scratch case A: switch at minute 59, probe at minute 60). That is correct behaviour; the fixer's decision table says "at most one hour later". But the row comment and `04-REVIEW-FIX.md` ("The first one is an hour after the switch") state something the code does not guarantee.
- **Never in a failing or recovering cycle.** The failure minutes (multiples of 50) never coincide with the probe minutes (multiples of 60) below 300. A probe that is due in a failing cycle is consumed there (scratch case C).

None of the three edges that the WR-09 fix relies on is pinned by a test:
- (a) a switch off the probe grid
- (b) a probe-due cycle whose version re-check fails, which must not move `_probe_armed_at` (the fixer's stated invariant; it holds per scratch case B)
- (c) a probe consumed by a cycle whose pages then fail

If someone later moves the arming above `_async_refresh_version`, the clock would advance in a cycle that raises. No test would catch that.

**Fix:**
- Reword the comment to "probes stay at least one hour apart and are not postponed by failures".
- Add matrix rows for (a) and (b). For example:
  - tick 30 min, then switch, then tick 30 min: assert `["/api/rawdata", *pages]`.
  - tick to the probe-due point with `/api/version` returning 500: assert `["/api/version"]` and `client._rawdata_probe_due is False`; the recovery cycle then asserts `["/api/version", "/api/rawdata", *pages]`.

### IN-13: The probe interval is hard-wired to `VERSION_RECHECK_INTERVAL`, and `_probe_armed_at` is moved when nothing was armed

**File:** `custom_components/traefik_proxy/coordinator.py:75-77,113-115,169-175`
**Issue:** `_interval_elapsed` serves both clocks with `VERSION_RECHECK_INTERVAL`. The probe budget ("≤ 1 probe per hour") is therefore tied to the version cadence. The natural fix for the open IN-03 (restart detected up to 1 h late) is to shorten `VERSION_RECHECK_INTERVAL`. That would silently multiply the paginated-mode probe requests. The matrix's `assert timedelta(hours=1) == VERSION_RECHECK_INTERVAL` would fail, but it would not explain why.

Separately, the name `_probe_armed_at` and its comment ("Last cycle that reached the rawdata probe arming") hide that the clock also moves in rawdata mode, where `request_rawdata_probe()` is a no-op. Part of the time it records a grid tick, not an arming.
**Fix:** Add `RAWDATA_PROBE_INTERVAL = timedelta(hours=1)`, give `_interval_elapsed(since, interval)` an interval parameter, and rename the field to `_probe_clock` (or document it as "last probe grid tick, moved in rawdata mode as well").

### IN-14: The committed switch to the pages is no longer logged

**File:** `custom_components/traefik_proxy/api.py:316-321`
**Issue:** The fix moved the debug line in front of the fallback read and reworded it to "trying the paginated list endpoints". Nothing is logged when `self._paginated = True` is actually committed. The same "trying" line now also appears in every failing cycle that never switches.

The switch back is logged ("probe succeeded, switching back to rawdata", `:291`); the switch to the pages is not. Debug logs therefore cannot show whether a client is in paginated mode, and the toggling of that mode is what WR-01, WR-09 and WR-10 were about.
**Fix:** After `self._paginated = True`, add `_LOGGER.debug("path=%s not found and the list endpoints answered, switched to the paginated list endpoints", _RAWDATA_PATH)`.

---

_Reviewed: 2026-11-14T03:04:27Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
