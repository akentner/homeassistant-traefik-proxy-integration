---
phase: 07-config-flow-ha-2026-11-baseline-observability
plan: 06
subsystem: options-flow
tags: [options-flow, OptionsFlowWithReload, update-listener, NumberSelector, cert-coordinator, home-assistant-2026.11]
status: complete

requires:
  - phase: 07-05
    provides: "entry data 1.3, reauth/reconfigure finish via async_update_reload_and_abort (so no listener is needed for data changes)"
provides:
  - "TraefikProxyOptionsFlow(OptionsFlowWithReload): scan_interval / tls_warn_days box NumberSelectors (s / d), verify_ssl BooleanSelector, int storage, extra options kept"
  - "No config-entry update listener anywhere; options apply through the reload"
  - "TraefikRuntimeData frozen"
  - "CertCoordinator reads CONF_TLS_WARN_DAYS once at construction; no threshold setter/getter"
  - "tests/test_options_flow.py"
affects: [07-07, 07-08, phase-08]

actuals:
  tokens: 11700
  tasks: 2
  commits: 4
plan_head_before: bf0b25fa1a5974c7e652d8e3cd2fa9ce04c0be01
plan_head_after: f8e0a674639a4506a68cb54ba2760c0dd48eed10

tech-stack:
  added: []
  patterns:
    - "Options flow subclasses OptionsFlowWithReload; HA reloads only when async_update_entry(options=...) changed something"
    - "NumberSelector values coerced with int() in the step, never vol.Coerce around the selector"
    - "Tests that save options wait with hass.async_block_till_done(wait_background_tasks=True) (scheduled reload + first cert cycle)"
    - "Request-level ssl assertion: patch.object(ClientSession, 'get', autospec=True, side_effect=ClientSession.get)"

key-files:
  created:
    - tests/test_options_flow.py
  modified:
    - custom_components/traefik_proxy/config_flow.py
    - custom_components/traefik_proxy/__init__.py
    - custom_components/traefik_proxy/data.py
    - custom_components/traefik_proxy/cert_coordinator.py
    - custom_components/traefik_proxy/binary_sensor.py
    - custom_components/traefik_proxy/entity.py
    - tests/test_init.py
    - tests/test_verify_ssl.py
    - tests/test_cert_entity_state.py
    - tests/test_cert_coordinator.py

key-decisions:
  - "Phase 07: options apply only through the reload of OptionsFlowWithReload; the integration registers no update listener"
  - "Phase 07: the options flow merges the submitted fields into the stored options, so options the form does not show survive a save"

requirements-completed: []  # FLOW-02 partially delivered; 07-07 adds the per-item toggle and grace period and completes it

coverage:
  - id: D1
    description: "No update listener after setup or reload; a bare options update does not reload; no listener usage report"
    requirement: FLOW-02
    verification:
      - kind: integration
        ref: "tests/test_init.py#test_no_update_listener_options_flow_reloads; tests/test_options_flow.py#test_changed_options_reload_with_new_values"
        status: pass
    human_judgment: false
  - id: D2
    description: "Changed options reload the entry: new runtime_data, coordinator interval, request ssl=False, cert threshold; unchanged values (45.0 for 45) do not reload"
    requirement: FLOW-02
    verification:
      - kind: integration
        ref: "tests/test_options_flow.py#test_changed_options_reload_with_new_values, test_unchanged_options_do_not_reload; tests/test_verify_ssl.py#test_options_change_reloads_with_new_client; tests/test_cert_entity_state.py#test_tls_warn_days_option_reaches_state, test_known_cert_hosts_are_never_added_again"
        status: pass
    human_judgment: false
  - id: D3
    description: "Selectors (box, units s/d, bounds), defaults, int storage, InvalidData outside the ranges, bounds accepted"
    requirement: FLOW-02
    verification:
      - kind: integration
        ref: "tests/test_options_flow.py#test_options_form_selectors, test_options_form_defaults_without_options, test_values_outside_a_range_raise_invalid_data, test_range_bounds_are_accepted"
        status: pass
    human_judgment: true
    rationale: "Rendering of the input boxes with units in the frontend is the Phase 8 visual check (M35)"
  - id: D4
    description: "CertCoordinator threshold only from construction; no accessor"
    requirement: FLOW-02
    verification:
      - kind: unit
        ref: "tests/test_cert_coordinator.py#test_threshold_is_set_at_construction"
        status: pass
    human_judgment: false

duration: 7min
completed: 2026-11-15
---

# Phase 7 Plan 06: Options flow with reload, no update listener Summary

**Saving the options form now reloads the Traefik entry through `OptionsFlowWithReload` (only when a value changed); polling interval and certificate warning threshold are whole-number input boxes with units, and every listener-only code path (options callback, live client swap, threshold setter/getter) is gone.**

## Performance

- **Duration:** ~7 min (14:13Z - 14:20Z)
- **Tasks:** 2 (Task 1 tracer; both TDD RED + GREEN)
- **Files modified:** 11 (1 created)

## Accomplishments

- **Options flow (D-16, D-17, D-32):** `TraefikProxyOptionsFlow(OptionsFlowWithReload)`. `scan_interval` is a `NumberSelector` min 15 / max 300 / step 1 / unit `s` / box; `tls_warn_days` min 1 / max 90 / step 1 / unit `d` / box; `verify_ssl` a `BooleanSelector` defaulting to the effective value. Both numbers are stored via `int(...)`, `verify_ssl` via `bool(...)`. `STEP_OPTIONS_SCHEMA`, the `vol.Invalid` branch, the `scan_interval_out_of_range` error path and the `cv` import are gone; out-of-range input raises `InvalidData` from the schema.
- **No listener (D-16, WR-03):** `_async_options_updated`, its `add_update_listener` registration and the now-unused imports (`timedelta`, `CONF_SCAN_INTERVAL`, `CONF_TLS_WARN_DAYS`, `DEFAULT_SCAN_INTERVAL`, `DEFAULT_TLS_WARN_DAYS`) are removed from `__init__.py`. Reauth and reconfigure already finish via `async_update_reload_and_abort` (07-05), so no data-change path needed the listener.
- **Frozen runtime data:** `TraefikRuntimeData` is `@dataclass(frozen=True)`.
- **Cert coordinator (Phase 6 IN-01/IN-02):** threshold setter and getter deleted; the constructor reads `entry.options.get(CONF_TLS_WARN_DAYS, DEFAULT_TLS_WARN_DAYS)`.
- **Tests:** new `tests/test_options_flow.py` (13 tests); `test_init` listener test replaced by `test_no_update_listener_options_flow_reloads`; the two option tests in `test_verify_ssl` and `test_cert_entity_state` drive the options flow and assert on the reloaded runtime; threshold boundary/listener tests set `threshold_days` and call `async_update_listeners()`.

## Task Commits

1. **Task 1 (tracer): options change reloads the entry, no update listener**
   - RED `d4b625f` (test)
   - GREEN `bc523eb` (feat)
   - Tracer gate (auto mode): full verify re-run green (946 dev / 946 HA 2026.11.0) -> expanded to Task 2
2. **Task 2: listener-only threshold paths removed**
   - RED `45b4c7b` (test)
   - GREEN `f8e0a67` (refactor)

## TDD Gate Compliance

RED evidence as pytest JUnit XML in the git-ignored `.pytest_cache/gsd-red/`, classified with `gsd-tools check tdd-red-evidence`. The records were produced after the GREEN commits by temporarily restoring the pre-GREEN source files of the RED commit (`git checkout <red-commit> -- <source files>`, run, `git checkout HEAD -- <source files>`); the RED commits themselves were verified failing at the time (8 failed in Task 1, 3 failed in Task 2).

| Target | Verdict | Semantic assessment |
|---|---|---|
| `tests/test_options_flow.py::test_changed_options_reload_with_new_values` (`07-06-t1.json`, source of `d4b625f`) | RED_EVIDENCE_OK | Failed on `entry.update_listeners == []`: HEAD registered `_async_options_updated` |
| `tests/test_cert_coordinator.py::test_threshold_is_set_at_construction[21-None-21]` (`07-06-t2.json`, source of `45b4c7b`) | RED_EVIDENCE_OK | Threshold value matched; failed on the no-accessor assertion (setter/getter still defined) |

At Task 1 RED, the range/defaults tests and `test_tls_warn_days_option_reaches_state` already passed (the old schema and the listener produced the same observable values); the listener, selector, int-storage, no-reload and kept-options tests failed.

## Gate results

| Gate | After Task 1 | After Task 2 |
|---|---|---|
| `uv run pytest -q` (dev, HA 2026.11.1) | 946 passed | 947 passed |
| `ruff check custom_components tests` | clean | clean |
| `ruff format --check custom_components tests` (44 files) | clean | clean |
| `uv run mypy --strict custom_components/traefik_proxy` (15 files) | no issues | no issues |
| ha2611-venv suite (HA 2026.11.0) | 946 passed | 947 passed |
| "Lingering" in output | none | none |
| `tests/test_cert_entity_state.py` 5 runs in a row (after Task 2) | - | 24 passed x5 |

No failure in any gate run; no rerun used (M39). Acceptance greps: Task 1 A1-A5 pass, `tests/test_options_flow.py` 13 passed (>= 6); Task 2 `async_set_threshold|get_threshold` absent from `custom_components/` and `tests/`, no `"tls_warn_days"` literal in `cert_coordinator.py`, `CONF_TLS_WARN_DAYS` present.

Local hassfest: deferred to Phase 8 (Docker unavailable); no manifest/translation change in this plan.

## Files Created/Modified

- `custom_components/traefik_proxy/config_flow.py` - `OptionsFlowWithReload`, `_number_selector`, int coercion, schema/error path removed
- `custom_components/traefik_proxy/__init__.py` - options listener + registration + imports removed, unload docstring
- `custom_components/traefik_proxy/data.py` - frozen dataclass, docstring
- `custom_components/traefik_proxy/cert_coordinator.py` - setter/getter removed, `CONF_TLS_WARN_DAYS`, class docstring
- `custom_components/traefik_proxy/binary_sensor.py`, `entity.py` - docstrings no longer claim live threshold changes
- `tests/test_options_flow.py` (new), `tests/test_init.py`, `tests/test_verify_ssl.py`, `tests/test_cert_entity_state.py`, `tests/test_cert_coordinator.py`

## Decisions Made

Planner decisions (applied as written): `TraefikRuntimeData` frozen; boundary tests set `threshold_days` + `async_update_listeners()`; options texts untouched (07-07); reload and threshold cleanup in one plan.

Worker decisions:

| Decision | Reason | Alternative |
|---|---|---|
| The options step stores `{**current_options, <three fields>}` instead of only the three fields | `per_item_entities` (set in tests and by future 07-07 form) and any other stored option would otherwise be dropped silently on the next save; unchanged merged options still compare equal, so no spurious reload | Store only the form fields (HA's usual pattern; loses `per_item_entities` until 07-07 adds the field) |
| `verify_ssl` became `vol.Required` (was `vol.Optional`) | All three fields always have a default, and the step reads all three; matches the plan's `vol.Required(CONF_VERIFY_SSL, ...)` | Keep Optional and `.get()` with the effective value |
| `tests/test_init.py::test_press_refreshes_only_own_entry`: second entry moved onto 1.3 data (`auth_type: bearer`, `token`) and unique_id `traefik2.example.com:8080` | The file was touched anyway; the legacy `api_key` at minor 3 was silently ignored (07-05 note) | Leave the legacy fixture |
| Request-level `ssl=False` assertion via an autospec spy on `aiohttp.ClientSession.get` | aioclient_mock does not record the `ssl` kwarg; the behavior line asks for "the next request passes ssl=False" | Only assert `client._verify_ssl` |
| Task 2 RED test asserts `dir(CertCoordinator)` contains no name with "threshold" | Gives a real RED without spelling the removed names (the acceptance grep forbids them in `tests/`) | Construction test only (would pass at RED) |
| FLOW-02 left Pending in REQUIREMENTS.md | FLOW-02 also requires the per-item toggle and the grace period, which 07-07 (also `requirements: [FLOW-02]`) delivers; same handling as FLOW-04 after 07-04 | Mark it complete now (would overstate the state until 07-07) |
| Options flow tests spell stored option keys as literals (`"scan_interval"`, ...) | Persistence contract, as in 07-05 | Import the constants |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Stale docstrings claiming live threshold changes**
- **Found during:** Task 2 GREEN
- **Issue:** `binary_sensor.py` (expiring sensor: "an options change re-evaluates without a new probe") and `entity.py` (`TraefikCertCoordinatorEntity`: "threshold changes ... notify") described the removed live path.
- **Fix:** docstrings now say the threshold is read at setup and an options change reloads the entry.
- **Files modified:** `custom_components/traefik_proxy/binary_sensor.py`, `custom_components/traefik_proxy/entity.py` (outside `files_modified`, docstrings only)
- **Commit:** `f8e0a67`

Other notes: Task 2's GREEN commit uses type `refactor` (dead-code removal, no behavior change for users). RED evidence records were generated after the GREEN commits (see TDD Gate Compliance).

## Issues Encountered

None.

## Known Stubs

None.

## User-visible changes (for the Phase 8 CHANGELOG)

- Saving the integration options reloads the integration when a value changed; a changed certificate warning threshold or TLS verification option therefore re-reads the certificates (new certificate cycle). Saving unchanged values does nothing.
- Polling interval and certificate warning threshold are input boxes with units (seconds / days); values outside 15-300 s and 1-90 days are rejected by the form.

## Self-Check: PASSED
