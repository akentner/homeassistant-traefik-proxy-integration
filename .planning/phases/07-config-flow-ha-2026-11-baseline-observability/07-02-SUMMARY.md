---
phase: 07-config-flow-ha-2026-11-baseline-observability
plan: 02
subsystem: integration-lifecycle
tags: [home-assistant-2026.11, device-registry, issue-registry, config-entries, data-update-coordinator]

requires:
  - phase: 07-01
    provides: "Dev env on HA 2026.11.1 (pytest-homeassistant) and ha2611-venv pinned to HA 2026.11.0"
provides:
  - "Sub-devices linked at creation via async_get_or_create(..., via_device_id=main.id); no async_update_device link"
  - "entities_migrated repair issue bound to its entry (config_entry_id), still persistent; HA deletes it on entry removal"
  - "async_setup_entry / async_unload_entry -> None; unload via async_unload_platforms_or_raise"
  - "CertCoordinator._stopping (own flag) replaces the read of DataUpdateCoordinator._shutdown_requested"
affects: [07-03, 07-05, 07-06, phase-08]

actuals:
  tokens: 4150
  tasks: 2
  commits: 4
plan_head_before: e0ef12964f9e5a7a24c5b91803d08b7ca04ffd16
plan_head_after: 238f952d198b4177a6c53a8294f70b6dd4be71f5

tech-stack:
  added: []
  patterns:
    - "Sub-device link at creation: device_registry.async_get_or_create(..., via_device_id=main.id)"
    - "Repair issues pass config_entry_id=entry.entry_id; async_remove_entry does not delete them"
    - "Lifecycle methods return None and raise on failure (async_unload_platforms_or_raise)"
    - "Coordinator subclasses keep their own stop flag instead of reading base-class private state"

key-files:
  created: []
  modified:
    - custom_components/traefik_proxy/entity.py
    - custom_components/traefik_proxy/__init__.py
    - custom_components/traefik_proxy/cert_coordinator.py
    - tests/test_devices.py
    - tests/test_binary_sensor_tls_expiring.py
    - tests/test_certificates_problem.py
    - tests/test_sensor_tls.py
    - tests/test_migration.py
    - tests/test_init.py
    - tests/test_cert_lifecycle.py

key-decisions:
  - "Phase 07: sub-devices link via the 2026.11 via_device_id keyword of async_get_or_create (not ChildDeviceInfo, M37); the async_update_device workaround is gone"
  - "Phase 07: migration repair issue carries config_entry_id and stays is_persistent=True; async_remove_entry only deletes the missing-since Store"
  - "Phase 07: setup/unload return None, unload uses async_unload_platforms_or_raise; async_migrate_entry keeps bool (False on downgrade, direct-call test)"
  - "Phase 07: CertCoordinator._stopping set first in async_shutdown; no private DataUpdateCoordinator attribute is read"

patterns-established:
  - "Spy on DeviceRegistry.async_update_device (public) to prove no post-creation link; HA's own get_or_create uses the private _async_update_device"

requirements-completed: [FLOW-08]

coverage:
  - id: D1
    description: "Sub-devices Routers/Services/Certificates carry via_device_id == main.id right after setup, without any async_update_device call carrying via_device_id; no deprecation / report_usage / 'Detected that custom integration' log"
    requirement: FLOW-08
    verification:
      - kind: integration
        ref: "tests/test_devices.py#test_sub_devices_linked_without_deprecation"
        status: pass
    human_judgment: false
  - id: D2
    description: "Tests read DeviceInfo.identifiers by attribute; D-09 grep (UNDEFINED, ATTR_*, device.config_entries) empty in custom_components"
    requirement: FLOW-08
    verification:
      - kind: unit
        ref: "tests/test_sensor_tls.py, tests/test_certificates_problem.py, tests/test_binary_sensor_tls_expiring.py (identity tests)"
        status: pass
      - kind: other
        ref: "! grep -rnE '\\bUNDEFINED\\b|\\bATTR_[A-Z_]+|device[a-z_]*\\.config_entries\\b' custom_components/traefik_proxy (empty)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Migration repair issue bound to the entry (config_entry_id, is_persistent=True), survives reload and unload, gone after entry removal (HA cleanup) together with the missing-since Store"
    requirement: FLOW-08
    verification:
      - kind: integration
        ref: "tests/test_migration.py#test_issue_survives_reload_and_is_deleted_on_remove"
        status: pass
    human_judgment: false
  - id: D4
    description: "async_setup_entry/async_unload_entry typed and returning None; unload via async_unload_platforms_or_raise; unload/reload work without usage report; direct downgrade migration returns False"
    requirement: FLOW-08
    verification:
      - kind: integration
        ref: "tests/test_init.py#test_setup_and_unload_return_none"
        status: pass
      - kind: unit
        ref: "tests/test_migration.py#test_downgrade_direct_call_returns_false"
        status: pass
    human_judgment: false
  - id: D5
    description: "CertCoordinator uses its own _stopping flag; a cycle completing after shutdown arms no day-boundary timer; existing shutdown/timer tests unchanged"
    requirement: FLOW-08
    verification:
      - kind: integration
        ref: "tests/test_cert_lifecycle.py#test_stopping_flag_blocks_the_boundary_timer_after_unload"
        status: pass
      - kind: unit
        ref: "tests/test_cert_coordinator.py#test_cycle_finishing_after_shutdown_schedules_no_day_boundary (unchanged)"
        status: pass
    human_judgment: false

duration: 10min
completed: 2026-11-15
status: complete
---

# Phase 7 Plan 02: HA 2026.11 lifecycle and device APIs Summary

**Sub-devices link to the Traefik device at creation through `async_get_or_create(..., via_device_id=main.id)`, the migration repair is bound to its config entry, setup/unload return `None` with `async_unload_platforms_or_raise`, and `CertCoordinator` uses its own `_stopping` flag instead of a private `DataUpdateCoordinator` attribute**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-11-15T13:22:00Z
- **Completed:** 2026-11-15T13:32:00Z
- **Tasks:** 2 (TDD: RED + GREEN each)
- **Files modified:** 10

## Accomplishments

- `entity.py`: sub-device `async_get_or_create` passes `via_device_id=main.id`; the follow-up `async_update_device(sub.id, via_device_id=…)` workaround is removed; docstring describes the keyword link.
- `__init__.py`: `entities_migrated` issue passes `config_entry_id=entry.entry_id` (keeps `is_persistent=True`); `async_remove_entry` only deletes the missing-since Store; `async_setup_entry` / `async_unload_entry` are `-> None`; unload awaits `hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)`; `async_migrate_entry` keeps `-> bool`.
- `cert_coordinator.py`: `self._stopping = False` in `__init__`, set to `True` as the first statement of `async_shutdown`; `_async_schedule_day_boundary` returns early on it.
- Tests: spy-based "no post-creation link" assertion, attribute access on `DeviceInfo`, entry-bound issue assertions, direct downgrade test, `None` return hints + unload/reload test, `_stopping` test; the last HA 2026.3 comment (`tests/test_init.py`) is reworded.

## Task Commits

1. **Task 1: Tracer — sub-devices link at creation via `via_device_id`**
   - RED `084bea7` (test) — `test_sub_devices_linked_without_deprecation` failed on the spy assertion (3 `async_update_device` calls with `via_device_id`)
   - GREEN `fbc2dfc` (feat)
2. **Task 2: Entry-bound repair, unload helper, None returns, own stop flag**
   - RED `7372fac` (test) — three targets failed on their planned assertions
   - GREEN `238f952` (feat)

No REFACTOR commits (nothing to clean up).

## TDD Gate Compliance

RED evidence was captured as pytest JUnit XML (`--junitxml`) in the git-ignored `.pytest_cache/gsd-red/` and classified with `gsd-tools check tdd-red-evidence`:

| Target | Verdict | Semantic assessment |
|---|---|---|
| `tests/test_devices.py::test_sub_devices_linked_without_deprecation` | RED_EVIDENCE_OK | Failed on `assert not [kwargs … if "via_device_id" in kwargs]` with three recorded link calls: exactly the workaround the plan removes |
| `tests/test_migration.py::test_issue_survives_reload_and_is_deleted_on_remove` | RED_EVIDENCE_OK | Failed on `issue.config_entry_id == ENTRY_ID` (`None`) |
| `tests/test_init.py::test_setup_and_unload_return_none` | RED_EVIDENCE_OK | Failed on the return hint (`bool` is not `NoneType`) |
| `tests/test_cert_lifecycle.py::test_stopping_flag_blocks_the_boundary_timer_after_unload` | RED_EVIDENCE_OK | Failed on `getattr(cc, "_stopping", None) is False` (attribute absent) |

`test_downgrade_direct_call_returns_false` passed in RED as expected: it characterises unchanged behaviour (the downgrade branch keeps `return False`, D-06). Each `feat(07-02)` commit descends from its `test(07-02)` commit.

## Gate results

| Gate | After Task 1 | After Task 2 |
|---|---|---|
| `uv run pytest -q` (dev, HA 2026.11.1) | 851 passed | 854 passed |
| `ruff check custom_components tests` | clean | clean |
| `ruff format --check custom_components tests` (43 files) | clean | clean |
| `uv run mypy --strict custom_components/traefik_proxy` (15 files) | no issues | no issues |
| ha2611-venv suite (HA 2026.11.0) | 851 passed | 854 passed |
| "Lingering" in output | none | none |

No failure occurred in any run, so no rerun was needed (M39: reruns void anyway).

Acceptance criteria: all Task 1 and Task 2 greps pass; `-k linked` 1 passed; `-k "issue or downgrade or unload or stopping"` 7 passed.

**D-09 grep record:** `grep -rnE "\bUNDEFINED\b|\bATTR_[A-Z_]+|device[a-z_]*\.config_entries\b" custom_components/traefik_proxy` → empty (no other 2026.11 API adopted).

**Private-attribute grep:** `grep -rnE "self\._(shutdown_requested|listeners|unsub_refresh|unsub_shutdown|update_interval|debounced_refresh|request_refresh_task|retry_after|last_listener_id|microsecond)\b" custom_components/` → empty.

**2026.3 sweep:** `grep -rn "2026\.3" custom_components tests` → empty.

Local hassfest: not part of this plan (deferred to Phase 8, Docker unavailable; CI's hassfest job remains the backstop).

## Files Created/Modified

- `custom_components/traefik_proxy/entity.py` - keyword link at creation, workaround removed
- `custom_components/traefik_proxy/__init__.py` - entry-bound issue, `-> None`, `async_unload_platforms_or_raise`, no manual issue delete on removal
- `custom_components/traefik_proxy/cert_coordinator.py` - own `_stopping` flag
- `tests/test_devices.py` - `async_update_device` spy, link asserted right after setup
- `tests/test_binary_sensor_tls_expiring.py`, `tests/test_certificates_problem.py`, `tests/test_sensor_tls.py` - `device_info.identifiers`
- `tests/test_migration.py` - `config_entry_id` / `is_persistent` assertions, direct downgrade test
- `tests/test_init.py` - `None` return / unload-reload test, 2026.3 comment reworded
- `tests/test_cert_lifecycle.py` - `_stopping` test

## Decisions Made

Planner decisions (applied as written): 2026.11 API adoption as its own wave-2 plan; downgrade branch keeps `return False` with a direct-call test (D-06); `_stopping` lands with the lifecycle changes.

Worker decisions:

| Decision | Reason | Alternative |
|---|---|---|
| Spy patches the public `DeviceRegistry.async_update_device` only | HA's `async_get_or_create` uses the private `_async_update_device`, so the spy sees only integration-side link calls | Patch `_async_update_device` (would also catch HA's internal creation path and could never pass) |
| `_stopping` RED/GREEN assertions use `getattr(cc, "_stopping", None)` | Makes the RED fail on the assertion, not on an `AttributeError` | Direct attribute access |
| Unload/reload test also asserts the `NOT_LOADED` / `LOADED` states and waits for background tasks after the reload | Reload starts the first cert cycle as an entry background task (M39 rule) | Plain `async_block_till_done()` |
| Removed the "(M34)" planning reference while rewriting the `async_remove_entry` docstring | The docstring was rewritten anyway; no planning references in shipped code (M22) | Keep the reference |
| RED evidence stored under git-ignored `.pytest_cache/gsd-red/` | Classifier requires a path inside the project; nothing untracked is left behind | Commit evidence files |
| FLOW-08 stays `Complete` in REQUIREMENTS.md | 07-01 delivered the toolchain half, this plan the API half; the remaining 07-03 work for FLOW-08 is planning-document housekeeping only | Reset to Pending until 07-03 |

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User-visible changes (for the Phase 8 CHANGELOG)

- None beyond the Home Assistant 2026.11.0 requirement: device links and repair cleanup behave as before.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- FLOW-08 code work complete; 07-03 (parallel wave 2) owns the remaining REQUIREMENTS/ROADMAP 2026.11 leftovers.
- 07-05/07-06 can add the FLOW-06 issue with `config_entry_id` following the same pattern; the update listener is still in place for 07-06.

---
*Phase: 07-config-flow-ha-2026-11-baseline-observability*
*Completed: 2026-11-15*

## Self-Check: PASSED

- Commits `084bea7`, `fbc2dfc`, `7372fac`, `238f952` are ancestors of HEAD; all modified files exist; acceptance greps and plan-level verification re-run green.
