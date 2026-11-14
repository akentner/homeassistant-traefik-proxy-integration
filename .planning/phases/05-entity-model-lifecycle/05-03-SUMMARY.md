---
phase: 05-entity-model-lifecycle
plan: 03
subsystem: entities
tags: [home-assistant, entity-manager, enum-sensor, entity-description, translations, diagnostics, traefik]

requires:
  - phase: 05-entity-model-lifecycle
    provides: "05-01 TraefikEntityManager/KindSpec (SERVICES, ENTRYPOINTS), TraefikEntity/TraefikItemEntity with write-on-change token, device topology; 05-02 persisted 24 h grace period and orphan adoption for every kind"
provides:
  - "sensor.py: TraefikServiceSensor (ENUM, Services sub-device, kind SERVICES), TraefikEntrypointSensor (main device, diagnostic, disabled by default, kind ENTRYPOINTS)"
  - "sensor.py: TraefikSensorEntityDescription, SNAPSHOT_SENSORS (routers_count, services_count, middlewares_count, version, start_time, healthy_ratio), TraefikSnapshotSensor, healthy_ratio(), PARALLEL_UPDATES = 0"
  - "binary_sensor.py: TraefikProblemEntityDescription, PROBLEM_SENSORS (routers_problem, services_problem, middlewares_problem), TraefikProblemBinarySensor, PARALLEL_UPDATES = 0"
  - "const.py: MAX_PROBLEM_NAMES = 50, UID_ROUTERS_PROBLEM, UID_SERVICES_PROBLEM, UID_MIDDLEWARES_PROBLEM"
  - "translations: entity.sensor.service.state.*, entity.sensor.<snapshot key>.name, entity.binary_sensor.<problem key>.name; strings.json byte-identical to en.json"
affects: [05-04, 05-05, 05-06, 05-07, phase-08-changelog]

actuals:
  tokens: 24979
  tasks: 3
  commits: 6
plan_head_before: 9a1a2e67d66a141bb1185ccec3e6ab45e1a1efd4
plan_head_after: 7ba72dc20a2076c437ed338ffb9daab02b5915d6

tech-stack:
  added: []
  patterns:
    - "Static main-device entities are one class plus frozen kw_only entity descriptions (unique_id_suffix + value/attrs/problems functions); names come from translation_key"
    - "Services and entrypoints follow the same manager lifecycle as routers (add once, missing, grace-period removal, re-bind)"
    - "RED commits carry xfail(strict=True) markers and in-function imports; GREEN removes the markers and hoists the imports"

key-files:
  created: []
  modified:
    - custom_components/traefik_proxy/sensor.py
    - custom_components/traefik_proxy/binary_sensor.py
    - custom_components/traefik_proxy/const.py
    - custom_components/traefik_proxy/translations/en.json
    - custom_components/traefik_proxy/strings.json
    - tests/test_sensor.py
    - tests/test_binary_sensor.py
    - tests/test_binary_sensor_tls_expiring.py
    - tests/test_platforms_real_fixtures.py
    - tests/test_entity_manager.py

key-decisions:
  - "Translation keys routers_count/services_count/middlewares_count mirror the kept unique_id suffixes (plan decision)"
  - "healthy_ratio rounded to one decimal (plan decision)"
  - "Aggregate unique_id suffixes live in const.py for the 05-07 migration (plan decision)"
  - "Entrypoint missing state is the string missing, entrypoint sensors are not ENUM (plan decision)"

patterns-established:
  - "Capture tests find every entity by unique_id (entity_id_for) and its device through the Traefik identifier; no entity_id literals"

requirements-completed: []

coverage:
  - id: D1
    description: "Services are ENUM sensors on the Services sub-device with exactly type/provider/servers_up/servers_total/used_by/errors, no URL or 192.0.2.x on both captures; unique_ids unchanged"
    requirement: ENT-04
    verification:
      - kind: integration
        ref: "tests/test_platforms_real_fixtures.py#test_service_enum_sensors"
        status: pass
      - kind: unit
        ref: "tests/test_sensor.py#test_service_sensor_attributes_are_private"
        status: pass
    human_judgment: false
  - id: D2
    description: "Server DOWN between two refreshes changes servers_up next cycle; disabled + error turns the state to error (both captures)"
    requirement: ENT-04
    verification:
      - kind: integration
        ref: "tests/test_entity_manager.py#test_service_server_down_reaches_sensor_next_cycle"
        status: pass
    human_judgment: false
  - id: D3
    description: "New services appear without reload, vanished services and entrypoints read missing; same-name router and service are separate entities on their sub-devices"
    requirement: ENT-01
    verification:
      - kind: integration
        ref: "tests/test_entity_manager.py#test_new_service_appears_and_vanished_service_goes_missing"
        status: pass
      - kind: integration
        ref: "tests/test_entity_manager.py#test_vanished_entrypoint_goes_missing"
        status: pass
      - kind: integration
        ref: "tests/test_entity_manager.py#test_router_and_service_with_same_name_are_separate"
        status: pass
    human_judgment: false
  - id: D4
    description: "Problem aggregates enabled by default, no category, main device, on for both captures, problems capped at 50 with problem_count"
    requirement: ENT-05
    verification:
      - kind: integration
        ref: "tests/test_platforms_real_fixtures.py#test_problem_aggregates_enabled_and_on"
        status: pass
      - kind: unit
        ref: "tests/test_binary_sensor.py#test_problem_names_capped_at_fifty"
        status: pass
    human_judgment: false
  - id: D5
    description: "Counts, version, start_time diagnostic and enabled; healthy_ratio diagnostic and disabled; entrypoints diagnostic and disabled; all on the main device"
    requirement: ENT-06
    verification:
      - kind: integration
        ref: "tests/test_platforms_real_fixtures.py#test_snapshot_sensors"
        status: pass
      - kind: integration
        ref: "tests/test_platforms_real_fixtures.py#test_entrypoint_sensors_diagnostic_and_disabled"
        status: pass
      - kind: unit
        ref: "tests/test_sensor.py#test_healthy_ratio"
        status: pass
    human_judgment: false
  - id: D6
    description: "PARALLEL_UPDATES = 0 in sensor and binary_sensor; static names from translation keys; no explicit entity_id outside the certificate classes"
    requirement: ENT-08
    verification:
      - kind: unit
        ref: "tests/test_sensor.py#test_snapshot_descriptions"
        status: pass
      - kind: unit
        ref: "tests/test_binary_sensor.py#test_problem_descriptions_enabled_by_default_without_category"
        status: pass
    human_judgment: false

duration: 13min
completed: 2026-11-14
status: complete
---

# Phase 5 Plan 03: Services, entrypoints, problem aggregates and diagnostic sensors Summary

**Services became ENUM sensors on the Services sub-device and entrypoints became diagnostic sensors that are disabled by default. Both now go through the entity manager. The three problem aggregates are one enabled-by-default class with three descriptions (capped `problems` plus `problem_count`). Counts, version, start time and healthy ratio come from one description-based diagnostic sensor class. Everything passes on HA 2026.3 and 2026.10.**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-11-14T09:30:09Z
- **Completed:** 2026-11-14T09:43Z
- **Tasks:** 3 (all tdd, RED + GREEN each)
- **Files modified:** 10

## Accomplishments

- `TraefikServiceSensor`:
  - ENUM sensor with `list(ITEM_STATE_OPTIONS)` and translation_key `service`, on the Services sub-device.
  - State is the Traefik status, or `missing` with `missing_since` while the service is gone.
  - Attributes are exactly `type, provider, servers_up, servers_total, used_by, errors`.
  - unique_id `{entry_id}_http_service_{name}` is unchanged.
- `TraefikEntrypointSensor`:
  - On the main device, diagnostic, disabled by default.
  - State is the address (or `missing`). The only attribute is `protocol`.
- `async_setup_entry` (sensor) registers the kinds ROUTERS, SERVICES and ENTRYPOINTS. The service and entrypoint stale-cleanup closures, both of which scanned the whole registry, are gone. The only `registry.entities` scan left is the certificate cleanup (05-05).
- `TraefikProblemBinarySensor` + `PROBLEM_SENSORS`:
  - `routers_problem` / `services_problem` / `middlewares_problem`: PROBLEM device class, enabled by default, no entity category, on the main device.
  - Attributes: `problems` (sorted, at most 50) and `problem_count`.
  - unique_id suffixes are kept in const.py.
- `TraefikSnapshotSensor` + `SNAPSHOT_SENSORS`:
  - Three count sensors (kept unique_ids; attributes `enabled, warning, error, disabled`).
  - `version` (attribute `codename`) and `start_time` (timestamp).
  - `healthy_ratio` (%, disabled by default).
  - All diagnostic, on the main device, MEASUREMENT where it applies.
- Removed: the old entrypoint/service classes, the count-sensor base and its three subclasses, the three any-*-failing classes, and with them their explicit entity_ids, hard-coded names, redundant `available` overrides and duplicate attributes (`name`, `status`, `server_count`, `service_name`, `entrypoint_name`, `transport`, `status_breakdown`, `success_pct`, `filtered_count`, `*_count`, `http_count`, `failing_*`).
- `PARALLEL_UPDATES = 0` in sensor.py and binary_sensor.py. Names come from translations in `en.json` (`strings.json` byte-identical).

## Task Commits

1. **Task 1 RED: failing tests for managed service and entrypoint sensors** - `6b55039` (test, 21 strict xfail)
2. **Task 1 GREEN: services and entrypoints as entity manager kinds** - `286fc27` (feat)
3. **Task 2 RED: failing tests for problem aggregate descriptions** - `e753237` (test, 13 strict xfail)
4. **Task 2 GREEN: problem aggregates as one class plus three descriptions** - `0db9405` (feat)
5. **Task 3 RED: failing tests for diagnostic snapshot sensors** - `6fdf897` (test, 20 strict xfail)
6. **Task 3 GREEN: diagnostic snapshot sensors from one description-based class** - `7ba72dc` (feat)

## Verification (end of plan)

- `uv run pytest -q`: 546 passed (baseline 535; 540 after Task 1, 541 after Task 2)
- `~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`: 546 passed (HA 2026.3.0)
- `uv run ruff check custom_components tests`: all checks passed. `ruff format --check`: 35 files already formatted
- `uv run mypy --strict custom_components/traefik_proxy`: no issues in 14 source files
- `cmp strings.json translations/en.json`: identical after every task
- Acceptance greps:
  - Task 1: `registry\.entities` 1. No duplicate attribute keys. `-k "service or entrypoint or same_name"` 5 passed.
  - Task 2: `PARALLEL_UPDATES == 0`. No `AnyRouterFailing|AnyServiceFailing|AnyMiddlewareFailing` and no `failing_*_(count|names)` in custom_components or tests. 1 `class TraefikProblemBinarySensor`.
  - Task 3: `PARALLEL_UPDATES == 0`. No `status_breakdown|success_pct|filtered_count|http_count` and no `CountSensor`. 1 `class TraefikSnapshotSensor`.

## TDD Gate Compliance

- Each task has a RED commit before its GREEN commit (6b55039 -> 286fc27, e753237 -> 0db9405, 6fdf897 -> 7ba72dc).
- RED evidence came from `--runxfail` runs. Every target failed on its planned assertion or on the missing symbol:
  - Task 1 (21 failed): `KeyError: 'servers_total'` / `'protocol'` / `'options'`; entrypoint `disabled_by None`; the vanished service had no entity and the added service had none either; the same-name service sat on the wrong device; ImportError for the new classes in unit tests.
  - Task 2 (13 failed): the aggregate registry entry was `disabled_by INTEGRATION`; ImportError for `PROBLEM_SENSORS`.
  - Task 3 (20 failed): count attributes were the old `*_count` set; ImportError/AttributeError for `SNAPSHOT_SENSORS` and `healthy_ratio`.
- RED commits mark the new tests `xfail(strict=True)` so every commit stays green. GREEN removes the markers.
- REFACTOR: none needed.

## Deviations from Plan

### Acceptance-check nuance (no code change)

**1. `grep -cE "async_add_kind\(\s*(SERVICES|ENTRYPOINTS)" sensor.py` prints 0, not 2.** `ruff format` puts the spec argument on the line after `async_add_kind(`, the same situation 05-01 recorded for ROUTERS. The multi-line match (`grep -Pzo`, the key_link pattern) finds exactly 2. Behaviour is as planned.

### Auto-fixed Issues

**1. [Rule 1 - Test bug] Two new manager tests compared `missing_since` with an unfrozen clock**
- **Found during:** Task 1 GREEN
- **Issue:** `test_new_service_appears_and_vanished_service_goes_missing` and `test_vanished_entrypoint_goes_missing` compared the attribute with a later `dt_util.utcnow()`, so they differed by microseconds.
- **Fix:** Added the `freezer` fixture to both tests.
- **Commit:** 286fc27

**2. [Rule 1 - Test bug] start_time capture assertion compared microseconds**
- **Found during:** Task 3 GREEN
- **Issue:** HA writes timestamp sensor states at second precision, while the capture start dates carry microseconds.
- **Fix:** The test compares with `start_date.replace(microsecond=0)`. The unit test still checks that the full-precision datetime is the native value.
- **Commit:** 7ba72dc

**3. [Rule 3 - Blocking] Cert expiring class docstring named the removed aggregate class**
- **Found during:** Task 2 (acceptance grep `! grep -rn "AnyRouterFailing..."`)
- **Fix:** Deleted the paragraph that compared it with the old opt-in aggregate. No behaviour change. The cert class itself is untouched until 05-05.
- **Commit:** 0db9405

## Worker Decisions

- RED tests import the new symbols inside the test functions, and GREEN moves those imports to module level. Reason: the RED module still collects, so the targets fail on the missing symbol instead of a collection error (05-01 convention). Alternative: keep the in-function imports.
- `_entry_with_snapshot` in tests/test_sensor.py sets `entity_manager.missing_since.return_value = None` for every unit test. Reason: a MagicMock return value would make every item look missing. Alternative: a separate helper for item entities.
- The en.json rewrite keeps `ensure_ascii=True` and a 2-space indent. Reason: the existing escapes (`—`) stay byte-identical and the diff only shows the added keys. Alternative: UTF-8 output, which would rewrite unrelated lines.
- `TraefikSnapshotSensor.extra_state_attributes` returns None for descriptions without `attrs_fn` (start_time, healthy_ratio). Reason: no empty attribute dict in the recorder. Alternative: `{}`.
- Capture tests check exact attribute sets by subtracting HA's own keys (`options`, `device_class`, `friendly_name`, `state_class`). Reason: the plan asks for the exact Traefik attribute set, and HA adds these itself. Alternative: subset checks like the router test.
- Removed old unit tests without one-for-one replacement: the entrypoint `entity_id` convention test, the breakdown/`success_pct`/`http_count` tests and the cert "inverted default" pin. Their behaviour is gone on purpose (D-08, P-09, U-01). The "excludes internal" and "follows latest snapshot" checks were carried over into the new tests.
- Extra tests beyond the plan:
  - `test_service_sensor_shape` / `test_entrypoint_sensor_shape` / `test_snapshot_sensor_unique_id_and_main_device` / `test_problem_sensor_keeps_unique_id_on_main_device`, covering device placement and the absence of an explicit entity_id per class;
  - `healthy_ratio` case `("enabled",) -> 100.0`.
  Reason: they pin D-08/D-13 per class at unit level. Alternative: rely on the capture tests only.
- ENT-01/02/04/05/06/08 stay "Pending" in REQUIREMENTS.md (`requirements.mark-complete` not run), as the phase convention requires. `requirements-completed: []`.

## User-visible changes (for the Phase 8 CHANGELOG)

- Service sensors are ENUM sensors (`enabled` / `warning` / `error` / `disabled` / `missing`) on the new "Traefik services (<host>)" device.
  - Attributes are now `type, provider, servers_up, servers_total, used_by, errors`. Removed: `name`, `status`, `server_count`, `service_name`.
  - Existing service entity_ids are kept.
  - New services appear without a reload. Vanished ones show `missing` for 24 h before removal (previously deleted at once).
- Entrypoint sensors are diagnostic and, on new installs, disabled by default. Their only attribute is `protocol` (removed: `name`, `address`, `transport`, `entrypoint_name`). Vanished entrypoints show `missing`.
- "Router problems", "Service problems" and "Middleware problems" (formerly "Any … failing") are enabled by default on new installs.
  - Attributes `problems` (sorted, at most 50) and `problem_count` replace `failing_*_names` / `failing_*_count`.
  - Existing entity_ids are kept. The 05-07 migration enables existing installs.
- Router/Service/Middleware count sensors are diagnostic. Their attributes are only `enabled, warning, error, disabled`. Removed: `filtered_count`, `*_count`, `status_breakdown`, `success_pct`, `http_count`.
- New diagnostic sensors: "Traefik version" (attribute `codename`) and "Start time" (timestamp), both enabled. "Healthy routers" (%, enabled ÷ non-disabled routers) is disabled by default.

## Known Stubs

None. The Services sub-device now has its entities. The old per-category devices (`_http_services`, `_http_entrypoints`, `_overview`, `_diagnostics`) lose their last entities with this plan. They stay as empty devices until the device cleanup in 05-07 (D-15). This is a temporary state, not a stub.

## Threat Flags

None. No new network, auth or file surface. T-05-05 (service attributes without URLs/IPs, tested on both captures), T-05-06 (cap 50 + `problem_count`, tested with 51) and T-05-07 (write-on-change token inherited from `TraefikEntity`) are mitigated as planned.

## Issues Encountered

- Existing installs keep the registry flags their entities were created with: entrypoint sensors stay enabled and the aggregates stay INTEGRATION-disabled until the 05-07 migration (flagged plan assumption).
- IN-11 (`_coordinator` alias on cert entities) is untouched and belongs to 05-05.

## Next Phase Readiness

- 05-04 can gate the ROUTERS and SERVICES kinds on `CONF_PER_ITEM_ENTITIES`. Both kinds are registered at the top of `sensor.async_setup_entry`.
- 05-07 can import `UID_ROUTERS_PROBLEM` / `UID_SERVICES_PROBLEM` / `UID_MIDDLEWARES_PROBLEM` from const.py for the migration, and add de.json/icons.json for the translation keys `service`, `entrypoint`, `routers_problem`, `services_problem`, `middlewares_problem`, `routers_count`, `services_count`, `middlewares_count`, `version`, `start_time` and `healthy_ratio`.

## Self-Check: PASSED

- FOUND: custom_components/traefik_proxy/sensor.py, binary_sensor.py, const.py, 05-03-SUMMARY.md
- FOUND commits: 6b55039, 286fc27, e753237, 0db9405, 6fdf897, 7ba72dc (all ancestors of HEAD)
