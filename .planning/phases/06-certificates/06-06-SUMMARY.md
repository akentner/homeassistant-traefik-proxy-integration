---
phase: 06-certificates
plan: 06
subsystem: certificates
tags: [cert-coordinator, day-boundary-timer, write-on-change, first-refresh, retry-interval, entity-manager]

requires:
  - phase: 06-04
    provides: "HostCertState.days_left (floor), entity _state_token with live days (write-on-change)"
  - phase: 06-05
    provides: "API-first cert cycle, 404 probe fallback, UpdateFailed on other API errors"
provides:
  - "HostCertState.next_day_change(now): not_after - days_left*DAY + 1 s, None without a certificate"
  - "CertCoordinator day-boundary timer: _unsub_day_boundary, _async_schedule_day_boundary(states), _async_handle_day_boundary(now), async_shutdown override"
  - "CertCoordinator retry interval: any failed cycle sets update_interval to CERT_RETRY_INTERVAL (300 s), a successful one restores the constructor interval"
  - "const.CERT_RETRY_INTERVAL: Final = 300"
  - "Setup awaits cert_coordinator.async_refresh(); no fake-success seeding"
  - "TraefikEntityManager.async_add_kind: after a failed cycle, orphans without a stored missing time are adopted as present"
affects: [06-07]

actuals:
  tokens: 8650
  tasks: 2
  commits: 4
plan_head_before: a4efa714704477d53208dc5f4f1802fd9fa25ccf
plan_head_after: 87a0ad3926d777bf956a520a39583c766519d3a7

tech-stack:
  added: []
  patterns:
    - "One coordinator-level async_track_point_in_utc_time timer at the earliest floor-day change + 1 s; fire = async_update_listeners() + reschedule from data"
    - "Timer scheduled from the end of a successful _async_update_data; cancelled before every reschedule and in async_shutdown"
    - "Retry interval via one try/except around the cycle body that sets update_interval before re-raising"

key-files:
  created:
    - tests/test_cert_lifecycle.py
  modified:
    - custom_components/traefik_proxy/cert_coordinator.py
    - custom_components/traefik_proxy/__init__.py
    - custom_components/traefik_proxy/entity_manager.py
    - custom_components/traefik_proxy/const.py
    - tests/test_cert_coordinator.py
    - tests/test_entity_manager.py

key-decisions:
  - "Planner worker decisions adopted as listed in 06-06-PLAN.md (one coordinator timer at floor-day change + 1 s, scheduled from a successful _async_update_data, 300 s retry, failed-cycle orphans adopted as present)"
  - "The retry wrapper catches Exception (not only UpdateFailed), so an unexpected error also retries in 5 minutes; CancelledError is not caught and changes neither interval nor timer"
  - "Standalone CertCoordinator tests with a mock entry call async_shutdown themselves: no unload cancels their timer, and phcc fails a lingering one"
  - "CERT-05 left open: the certificates_problem aggregate belongs to 06-07"

requirements-completed: []

coverage:
  - id: D1
    description: "next_day_change: mid-day, exact day, expired, no certificate"
    requirement: "CERT-05"
    verification:
      - kind: unit
        ref: "tests/test_cert_lifecycle.py#test_next_day_change"
        status: pass
    human_judgment: false
  - id: D2
    description: "Threshold crossing (off at N-15 d, on/expiring/14 one second later), expiry (expiring/0 at N, expired/-1 at N+1 s), daily countdown 30->29 written once at the boundary; no probe, no /api/certificates request"
    requirement: "CERT-05"
    verification:
      - kind: integration
        ref: "tests/test_cert_lifecycle.py#test_threshold_crossing_without_probe, test_expired_at_not_after_without_probe, test_daily_countdown_written_once_at_the_boundary"
        status: pass
    human_judgment: false
  - id: D3
    description: "Write-on-change across two hosts; timer replaced on every cycle (old one cancelled); no timer without a certificate; unload cancels the timer"
    requirement: "CERT-05"
    verification:
      - kind: integration
        ref: "tests/test_cert_lifecycle.py#test_boundary_writes_only_the_host_that_changed, test_boundary_timer_is_replaced_on_every_cycle, test_no_timer_without_a_certificate, test_unload_cancels_the_boundary_timer"
        status: pass
    human_judgment: false
  - id: D4
    description: "Failed first cert cycle: entry LOADED, cert coordinator failed, restored hosts unavailable with missing_since None; next success reconciles (present available/api, absent missing); stored missing time kept"
    requirement: "CERT-05"
    verification:
      - kind: integration
        ref: "tests/test_cert_lifecycle.py#test_failed_first_cycle_keeps_restored_hosts_unavailable_not_missing, test_restored_hosts_reconciled_by_the_next_successful_cycle; tests/test_entity_manager.py#test_failed_cycle_keeps_stored_cert_missing_time"
        status: pass
    human_judgment: false
  - id: D5
    description: "300 s retry after a failed cycle, 6 h after success; no ConfigEntryNotReady on 500 or connection error"
    requirement: "CERT-05"
    verification:
      - kind: integration
        ref: "tests/test_cert_lifecycle.py#test_retry_five_minutes_after_a_failed_cycle, test_certificate_failure_never_raises_not_ready"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-11-15
status: complete
---

# Phase 6 Plan 06: Day-Boundary Timer and Honest First Cert Cycle Summary

**Certificate state now changes when the clock says so. One timer on the cert coordinator fires one second after the earliest whole-day boundary of any host and lets the entities re-evaluate. Threshold crossings, expiry and the daily `days_until_expiry` countdown therefore reach Home Assistant at the boundary, with no probe and no API call, instead of up to 6 h later. A failing certificate source at startup is no longer faked into an empty success. The cert entities show unavailable, restored hosts are not marked missing, and the cycle is retried after 5 minutes.**

## Performance

- **Duration:** about 8 min (2026-11-15T09:02Z to 09:10Z)
- **Tasks:** 2, both TDD (a RED commit, then a GREEN commit)
- **Files:** 1 created, 6 modified

## Accomplishments

- **Day-boundary timer (Task 1, tracer):** `HostCertState.next_day_change(now)` returns `not_after - days_left*DAY + 1 s`, or None when the host has no certificate. `_async_update_data` now wraps the cycle body (`_async_cycle`). After a successful cycle it calls `_async_schedule_day_boundary(states)`, which cancels any pending timer and schedules `async_track_point_in_utc_time` at the earliest change. If no host has a certificate, no timer is scheduled. `_async_handle_day_boundary` clears the handle, calls `async_update_listeners()` and reschedules from `data`. The `async_shutdown` override cancels the timer before the base shutdown, which HA registers on entry unload. Entities needed no change: since 06-04 their write-on-change token already holds the live day count, so a fire writes only the hosts whose state changed.
- **Honest first cycle (Task 2):** `async_setup_entry` now awaits `cert_coordinator.async_refresh()`. This call never raises, so a failure keeps `last_update_success` False. The catch-all and the `async_set_updated_data({})` seeding are gone. `TraefikEntityManager.async_add_kind` checks `coordinator.last_update_success` and adopts registry orphans that have no stored missing time as present: they are added and get no missing stamp. Orphans with a stored time keep it, or are removed once it ran out. The next successful cycle reconciles them through `_async_kind_updated`.
- **Retry interval (Task 2):** `CERT_RETRY_INTERVAL: Final = 300`. Any exception from the cycle body sets `update_interval` to 300 s before it is re-raised. A successful cycle restores the constructor interval (default 6 h). HA schedules the next refresh from `update_interval` after `_async_update_data` returns.

## Task Commits

1. **Task 1 (tracer): day-boundary timer**
   - RED `4bc4b15` test(06-06): add failing tests for the day-boundary timer of the cert coordinator
   - GREEN `68b69b5` feat(06-06): write certificate day changes at the boundary with one coordinator timer
   - Tracer gate (auto mode): every `<verify>` command was re-run and passed: 10 targeted, 806 full with no lingering timer, ruff, format and mypy clean, 806 on HA 2026.3. Then the work moved on to Task 2.
2. **Task 2: honest first cycle, restored hosts, 5-minute retry**
   - RED `c3a2b91` test(06-06): add failing tests for an honest first cert cycle and the 5-minute retry
   - GREEN `87a0ad3` feat(06-06): keep a failed first cert cycle failed and retry it after 5 minutes

## TDD Gate Compliance

| Task | RED evidence | Verdict | Semantic assessment |
|------|--------------|---------|---------------------|
| 1 | `uv run pytest tests/test_cert_lifecycle.py -q` with `--junitxml`, exit 1, 9 failed / 1 passed; target `test_threshold_crossing_without_probe` | `RED_EVIDENCE_OK` (target_test_failed) | The target failed on `assert 'off' == 'on'` one second after N − 15 d, because nothing re-evaluated the entity. The expiry, countdown and two-host tests failed on the same missing re-evaluation (`'expiring' == 'expired'`, `30 == 29`, `20 == 19`). The unload test failed on "timer pending after setup". `next_day_change` failed with AttributeError (method missing). The replace test failed because the patch target does not exist yet. `test_no_timer_without_a_certificate` passed in RED by design: it guards against scheduling a timer when no host has a certificate. There were no collection or fixture errors. |
| 2 | `uv run pytest tests/test_cert_lifecycle.py tests/test_entity_manager.py -q` with `--junitxml`, exit 1, 5 failed / 47 passed; target `test_failed_first_cycle_keeps_restored_hosts_unavailable_not_missing` | `RED_EVIDENCE_OK` (target_test_failed) | The target failed on `assert not True` for `last_update_success`: setup seeded an empty successful state. The retry test, both no-NotReady cases and the stored-time test failed on the same assertion. `test_restored_hosts_reconciled_by_the_next_successful_cycle` passed in RED as a guard: under the old seeding the absent host was stamped at setup, which equals "now" on the frozen clock. It pins the post-success outcome the new path must keep. |

Each RED commit contains tests only, and each GREEN commit leaves the tree green. This follows the same D-19 precedent as 06-01..06-05.

## Verification

- `uv run pytest -q`: **812 passed** (796 before this plan; +16). There was no "Lingering timer" output.
- `~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`: **812 passed on HA 2026.3.0**
- `uv run ruff check custom_components tests`: all checks passed. `ruff format --check`: 42 files already formatted. `mypy --strict custom_components/traefik_proxy`: no issues in 15 source files.
- Acceptance Task 1: `async_track_point_in_utc_time(` and `async def async_shutdown(self) -> None:` are in cert_coordinator. `-k "threshold or expired or daily or boundary or unload or no_timer"`: 8 passed (at least 6 required).
- Acceptance Task 2: `async_set_updated_data` no longer appears in `__init__.py`. `await cert_coordinator.async_refresh()` and `^CERT_RETRY_INTERVAL: Final = 300` are present. `-k "first_cycle or restored or retry or not_ready"`: 5 passed (at least 4 required). test_entity_manager `-k failed_cycle`: 2 passed (at least 2 required).

## Worker decisions

| Decision | Reason | Alternative not taken |
|---|---|---|
| Planner decisions adopted as listed in 06-06-PLAN.md "Worker decisions (planner)" | Recorded by the planner | — |
| The retry wrapper catches `Exception`, not only `UpdateFailed` | HA's `_async_refresh` also turns unexpected exceptions into a failed cycle. The plan asks for "one wrapper ... so every failure path is covered". `CancelledError` is a `BaseException`, so a cancelled cycle changes neither the interval nor the timer. | `except UpdateFailed` only, where an unexpected bug would wait 6 h |
| The cycle body moved to `_async_cycle`, and `_async_update_data` became the wrapper (interval, then timer) | One place for success and failure handling, and the existing early returns stay unchanged | Set the interval and timer at every return point |
| `DAY_CHANGE_DELAY: Final = timedelta(seconds=1)` module constant in cert_coordinator | Gives the +1 s a name next to `DAY` | Inline literal |
| Three standalone `CertCoordinator(hass, <mock entry>)` tests in test_cert_coordinator now `await c.async_shutdown()` | A mock entry has no unload, so the new timer lingered and phcc failed those tests. Production entries cancel it on unload, which `test_unload_cancels_the_boundary_timer` covers. | Turn the timer off in tests |
| The "at most one pending timer" truth is tested by wrapping `async_track_point_in_utc_time` (`test_boundary_timer_is_replaced_on_every_cycle`): the first unsub is called once and the second stays pending | This checks the cancel-before-reschedule rule directly, without scanning the loop's private timer list | Count `loop._scheduled` handles |
| The tests for a failed first cycle use the v3.7 capture with `/api/certificates` returning 500, or `aiohttp.ClientConnectionError` through `aioclient_mock`'s `exc=` | The API source is the first thing a cycle touches, and both failure classes map to `UpdateFailed` | Make the probe fail on v2.11 (a failed probe does not fail the cycle) |

## Deviations from Plan

None in production behaviour. The only change outside the plan's file list is in `tests/test_cert_coordinator.py`: three standalone tests now shut their coordinator down (Rule 3, blocking: the new timer lingered after these tests and phcc failed them). See Worker decisions.

## Requirement status

CERT-05 is **not** marked complete. This plan delivers the live-days and day-boundary part: SC4 "visible at the boundary, not 6 h later", D-13 and D-23. The `certificates_problem` aggregate named in the CERT-05 text belongs to 06-07.

## User-visible changes (for the Phase 8 CHANGELOG)

- Certificate expiry, threshold crossings (`certificate_expiring` turning on with reason `expiring`) and the daily `days_until_expiry` change now appear at the moment they happen, not at the next 6-hourly certificate check.
- If the certificate source fails at startup, the certificate entities show as unavailable. Before, this was an empty "everything fine". The check is retried after 5 minutes, and any failed certificate check is retried after 5 minutes instead of 6 hours. Home Assistant logs the failure once as an error ("Error fetching Traefik certs data").
- Existing certificate entities are no longer marked missing, and their 24 h removal clock no longer starts, just because the first certificate check after a restart failed.

## Known Stubs

None.

## Threat Flags

No new surface. T-06-17: there is one timer per coordinator. It is cancelled before every reschedule and in `async_shutdown`. `test_no_timer_without_a_certificate`, `test_unload_cancels_the_boundary_timer` and `test_boundary_timer_is_replaced_on_every_cycle` cover this, and the phcc lingering-timer check is green across the suite. T-06-18: there is no fake success. The `async_set_updated_data` grep gate passes, and the failed-first-cycle tests assert unavailable entities with no missing stamp.

## Assumptions carried (from the plan)

- Last known certificate values live in memory only (D-16). After an HA restart with a failed first cycle, the restored cert entities are unavailable until the first success. There is no RestoreSensor in this phase.

## Next Phase Readiness

- 06-07: the aggregate can listen to the cert coordinator. The day-boundary fire calls `async_update_listeners()`, so a time-only change (for example passing `not_after`) reaches the aggregate without a probe. When the last cycle failed, `last_update_success` is False, so "unavailable when the last cert cycle failed" follows from the base availability.

## Self-Check: PASSED

- FOUND: tests/test_cert_lifecycle.py, custom_components/traefik_proxy/cert_coordinator.py (`async_track_point_in_utc_time(`, `async def async_shutdown(self) -> None:`), custom_components/traefik_proxy/const.py (`CERT_RETRY_INTERVAL: Final = 300`), custom_components/traefik_proxy/__init__.py (`await cert_coordinator.async_refresh()`)
- FOUND commits (ancestors of HEAD): 4bc4b15, 68b69b5, c3a2b91, 87a0ad3
- Measured: `git rev-list --count a4efa71..HEAD` = 4
