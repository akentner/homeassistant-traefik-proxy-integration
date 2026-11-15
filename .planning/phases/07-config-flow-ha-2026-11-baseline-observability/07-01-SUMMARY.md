---
phase: 07-config-flow-ha-2026-11-baseline-observability
plan: 01
subsystem: testing
tags: [home-assistant-2026.11, pytest-homeassistant, hacs, ci, uv, probatio]

requires:
  - phase: 06
    provides: "851-test suite green on HA 2026.10.4 (phcc 0.13.375)"
provides:
  - "Dev env on HA 2026.11.1 via pytest-homeassistant>=2026.11.0 (local, git-ignored uv.lock)"
  - "Local minimum venv ~/.cache/traefik-proxy-integration/ha2611-venv pinned to HA 2026.11.0"
  - "hacs.json minimum HA 2026.11.0"
  - "CI job test-min-ha (pytest-homeassistant==2026.11.0)"
  - "No pre-2026.11 import shims in config_flow.py / binary_sensor.py"
affects: [07-02, 07-03, 07-04, 07-05, 07-06, 07-07, 07-08, 07-09, phase-08]

actuals:
  tokens: 3400
  tasks: 2
  commits: 2
plan_head_before: 4e4d859bf61e42ba3e882fc1959995cd6423057f
plan_head_after: b5a395891ba22cfbf587e69819d1685bca8465c8

tech-stack:
  added: ["pytest-homeassistant 2026.11.x (dev only)"]
  patterns:
    - "HA test helpers imported from pytest_homeassistant.common / pytest_homeassistant.test_util.aiohttp"
    - "Minimum-HA suite run: ha2611-venv/bin/python -m pytest -q -o addopts=\"-p no:respx\" tests"

key-files:
  created: []
  modified:
    - pyproject.toml
    - tests/conftest.py
    - tests/test_config_flow.py
    - tests/test_cert_entity_state.py
    - custom_components/traefik_proxy/config_flow.py
    - custom_components/traefik_proxy/binary_sensor.py
    - hacs.json
    - .github/workflows/validate.yml

key-decisions:
  - "Phase 07: test stack switched to pytest-homeassistant>=2026.11.0 (M38), provenance asserted from installed metadata before any test run"
  - "Phase 07: HA 2026.3 import shims removed in the tracer commit together with the lock (mypy-strict on 2026.11 rejects them)"
  - "Phase 07: minimum HA 2026.11.0 enforced by hacs.json, local ha2611-venv and CI job test-min-ha"

patterns-established:
  - "Every later Phase 7 plan verifies on the dev env (2026.11.x) and on ha2611-venv (2026.11.0); ha2603-venv is retired"

requirements-completed: [FLOW-08]

coverage:
  - id: D1
    description: "Suite runs on HA 2026.11.x dev env through pytest-homeassistant; old package absent from pyproject/tests"
    requirement: FLOW-08
    verification:
      - kind: unit
        ref: "uv run pytest -q (851 passed)"
        status: pass
      - kind: other
        ref: "provenance assertion: pytest-homeassistant 2026.11.1, Repository https://github.com/home-assistant/core, pins homeassistant==2026.11.1"
        status: pass
    human_judgment: false
  - id: D2
    description: "Suite runs on exactly HA 2026.11.0 (ha2611-venv)"
    requirement: FLOW-08
    verification:
      - kind: unit
        ref: "~/.cache/traefik-proxy-integration/ha2611-venv/bin/python -m pytest -q -o addopts=\"-p no:respx\" tests (851 passed after Task 2)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Pre-2026.11 import shims removed; mypy --strict clean on 2026.11"
    requirement: FLOW-08
    verification:
      - kind: other
        ref: "uv run mypy --strict custom_components/traefik_proxy (no issues in 15 files)"
        status: pass
    human_judgment: false
  - id: D4
    description: "hacs.json minimum 2026.11.0 and CI job test-min-ha; existing CI jobs unchanged"
    requirement: FLOW-08
    verification:
      - kind: other
        ref: "Task 2 json/yaml assertion + additions-only diff guard on validate.yml"
        status: pass
    human_judgment: false

duration: 4min
completed: 2026-11-15
status: complete
---

# Phase 7 Plan 01: HA 2026.11 toolchain baseline Summary

**Test stack moved from the discontinued pytest-homeassistant-custom-component to pytest-homeassistant (HA 2026.11.1 dev, 2026.11.0 minimum venv), 2026.3 import shims removed, hacs.json and a new CI job test-min-ha require HA 2026.11.0**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-11-15T12:53:00Z
- **Completed:** 2026-11-15T12:57:00Z
- **Tasks:** 2
- **Files modified:** 17

## Accomplishments

- `pyproject.toml`: dev dependency `pytest-homeassistant>=2026.11.0`, `addopts` prefixed with `-p no:respx` (coverage flags untouched, Phase 8). Local `uv.lock` resolves `homeassistant` / `pytest-homeassistant` 2026.11.1 and stays git-ignored.
- Twelve test files import HA helpers from `pytest_homeassistant`; `tests/conftest.py` lost the `pytest_plugins` line and the autouse `enable_custom_integrations` fixture.
- `config_flow.py` imports `probatio as vol` in one statement; `binary_sensor.py` imports `BinarySensorDeviceClass`, `BinarySensorEntity` and `BinarySensorEntityDescription` in one statement from `homeassistant.components.binary_sensor`.
- `test_user_schema_serializes_for_config_flow_endpoint` uses `probatio.to_field_list` only; the 2026.3 comments in `test_config_flow.py` and `test_cert_entity_state.py` are gone (`test_init.py:72` belongs to 07-02).
- `~/.cache/traefik-proxy-integration/ha2611-venv` created (CPython 3.14.10, `pytest-homeassistant==2026.11.0`, HA 2026.11.0 asserted).
- `hacs.json` `"homeassistant": "2026.11.0"`; `.github/workflows/validate.yml` gained `test-min-ha` (additions only).

## Task Commits

1. **Task 1: Tracer — the suite runs on HA 2026.11** - `5ca4f33` (chore)
2. **Task 2: HACS and CI enforce the 2026.11.0 minimum** - `b5a3958` (ci)

## Gate results

| Gate | After Task 1 | After Task 2 |
|---|---|---|
| Provenance assertion (`pytest-homeassistant` 2026.11.1, repo home-assistant/core, pins own HA version) | pass | — |
| `uv run pytest -q` (dev, HA 2026.11.1) | 851 passed | 851 passed |
| `ruff check` / `ruff format --check` (43 files) / `mypy --strict` (15 files) | clean | clean |
| ha2611-venv HA version assertion | 2026.11.0 | — |
| ha2611-venv suite (HA 2026.11.0) | 850 passed, 1 failed (known flake, see below); file rerun 24 passed | 851 passed |
| "Lingering" / "httpx was already imported" in output | none | none |

Known flake (observation only, M39 / D-33, no code change): on the first ha2611-venv run after Task 1,
`tests/test_cert_entity_state.py::test_vanished_cert_host_unavailable_then_removed_after_grace` failed with
`AssertionError: no binary_sensor entity with unique_id …_tls_expiring_www.secure.example.com`. One rerun of the
file passed (24 passed), and the full ha2611-venv run after Task 2 passed (851). The root-cause fix is the
orchestrator's separate commit after this plan.

## Files Created/Modified

- `pyproject.toml` - dev dependency switch, `-p no:respx`
- `tests/conftest.py` - import rename, plugin line and autouse fixture removed
- `tests/test_api.py`, `test_api_pagination.py`, `test_cert_entity_state.py`, `test_cert_lifecycle.py`, `test_certificates_problem.py`, `test_config_flow.py`, `test_coordinator.py`, `test_entity_manager.py`, `test_platforms_real_fixtures.py`, `test_reconfigure.py`, `test_verify_ssl.py` - import rename (plus comment/serializer cleanup in two of them)
- `custom_components/traefik_proxy/config_flow.py` - probatio import only
- `custom_components/traefik_proxy/binary_sensor.py` - single binary_sensor import
- `hacs.json` - minimum HA 2026.11.0
- `.github/workflows/validate.yml` - job `test-min-ha`

## Decisions Made

Planner decisions (from the plan, applied as written):

| Decision | Reason | Alternative not taken |
|---|---|---|
| Shim removal lands in the tracer task together with the lock | mypy-strict on HA 2026.11 rejects the shims; a later task would leave the tracer commit red | Separate shim task |
| No human checkpoint before installing `pytest-homeassistant`; automated metadata assertion instead | M38 / CONTEXT D-01 | `checkpoint:human-verify gate="blocking-human"` |
| 2026.11.0 venv created in the tracer; HACS and CI in Task 2 | D-02 needs the 2026.11.0 run after every task | Venv in Task 2 |
| Toolchain bump only; API work and cleanup in 07-02 / 07-03 | Checker per-plan budget | One baseline plan |

Worker decisions:

| Decision | Reason | Alternative |
|---|---|---|
| `BinarySensorDeviceClass` import written as a parenthesised multi-line import (ruff-format style) | One statement as the plan requires; matches line-length formatting | One long line |
| `probatio.to_field_list` import stays local to the test function (as before) | Minimal diff; the test only needed the fallback removed | Module-level import |
| Reworded comment in `test_cert_entity_state.py` to "Look devices up by config entry and index them by identifier." | Plan asks to drop the HA-release justification only | Delete the comment |
| Ran pytest with `-p no:cacheprovider` for gate runs | Avoid writing `.pytest_cache` noise; does not change test behaviour | Default cache |

## Deviations from Plan

None - plan executed exactly as written.

- Docker: this plan contains no local Docker / hassfest step, so nothing was deferred. CI's hassfest job remains the backstop (local hassfest deferred to Phase 8, Docker unavailable).

## Issues Encountered

- Known flake in `tests/test_cert_entity_state.py` on the first ha2611-venv run (see Gate results). Not masked; no code change.

## User-visible changes (for the Phase 8 CHANGELOG)

- Home Assistant 2026.11.0 is now required (HACS refuses older versions). Nothing else changes for users.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 07-02 / 07-03 can verify on the dev env (HA 2026.11.1) and `~/.cache/traefik-proxy-integration/ha2611-venv` (HA 2026.11.0). `ha2603-venv` is retired and still exists on disk (not removed, not a gate).
- `tests/test_init.py:72` still mentions HA 2026.3 (owned by 07-02).
- Orchestrator: flaky-test root-cause commit (M39) is next.

## Self-Check: PASSED

- Commits `5ca4f33` and `b5a3958` are ancestors of HEAD; all modified files exist; all Task 1 and Task 2 acceptance criteria and plan-level verification commands re-run green.

---
*Phase: 07-config-flow-ha-2026-11-baseline-observability*
*Completed: 2026-11-15*
