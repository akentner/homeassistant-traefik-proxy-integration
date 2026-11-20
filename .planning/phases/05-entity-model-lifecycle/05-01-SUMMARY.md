---
phase: 05-entity-model-lifecycle
plan: 01
subsystem: entities
tags: [home-assistant, entity-manager, enum-sensor, device-registry, write-on-change, translations, traefik]

requires:
  - phase: 04-data-layer-correct-lean
    provides: "TraefikSnapshot with typed Router models (dataclass equality), coordinator with always_update=False, real v2.11/v3.7 captures and stub_traefik"
provides:
  - "entity_manager.py: KindSpec + ROUTERS/SERVICES/ENTRYPOINTS/CERT_EXPIRY/CERT_EXPIRING (single D-09 unique_id scheme), TraefikEntityManager (async_add_kind, missing_since, kind listener: add new keys once in sorted order, mark vanished keys missing, re-bind returning keys)"
  - "entity.py: TraefikDevice, device_identifier, traefik_device_info (identifiers only), entry_host, dashboard_url, async_setup_devices, _TraefikEntityBase (write-on-change token), TraefikEntity, TraefikItemEntity[ModelT]"
  - "sensor.py: TraefikRouterSensor (ENUM, options enabled/warning/error/disabled/missing, translation_key router, Routers sub-device) registered as the ROUTERS kind"
  - "Device topology: main device 'Traefik (<host>)' (SERVICE, manufacturer Traefik, configuration_url <url>/dashboard/, sw_version) plus Routers/Services/Certificates sub-devices linked via async_update_device(via_device_id=main.id)"
  - "translations: device.<main|routers|services|certificates>.name, entity.sensor.router.state.*; strings.json byte-identical to en.json"
  - "tests/conftest.py helpers make_traefik_entry, setup_traefik_entry, entity_id_for, restub_traefik, rawdata_copy; tests/test_entity_manager.py (17 tests)"
affects: [05-02, 05-03, 05-04, 05-05, 05-06, 05-07, phase-08-changelog]

actuals:
  tokens: 11124
  tasks: 2
  commits: 3
plan_head_before: e4e7dc5d1de9a74cc4b997eda7d6beae416b9b19
plan_head_after: 03ad0573e7f51a9cce0c240c1e8014ec88e27be3

tech-stack:
  added: []
  patterns:
    - "One TraefikEntityManager per entry on runtime_data; platforms register kinds (KindSpec, key source, factory, async_add_entities); the kind listener is registered before any entity so it runs first on every notification"
    - "Per-item entities hold only their key; write-on-change via a (available, state token) comparison in _handle_coordinator_update; item token = (model, missing_since)"
    - "Devices registered in async_setup_entry before forwarding platforms; entities carry identifiers-only DeviceInfo; sub-device link via DeviceRegistry.async_update_device(via_device_id=...)"
    - "RED commit of a tdd task carries xfail(strict=True) markers so every commit stays green; GREEN removes them"

key-files:
  created:
    - custom_components/traefik_proxy/entity_manager.py
    - tests/test_entity_manager.py
  modified:
    - custom_components/traefik_proxy/entity.py
    - custom_components/traefik_proxy/sensor.py
    - custom_components/traefik_proxy/binary_sensor.py
    - custom_components/traefik_proxy/__init__.py
    - custom_components/traefik_proxy/data.py
    - custom_components/traefik_proxy/const.py
    - custom_components/traefik_proxy/translations/en.json
    - custom_components/traefik_proxy/strings.json
    - tests/conftest.py

key-decisions:
  - "RED commit of Task 2 carries xfail(strict=True) markers so every commit stays green (D-20/W42); the GREEN commit removes them"
  - "Manager adds entities for the initial key set with one async_add_entities call, also when the set is empty"
  - "TraefikRouterSensor sets _attr_options in __init__ (ruff RUF012 forbids a mutable class attribute)"

patterns-established:
  - "KindSpec.unique_id / key_of are the only place that builds or parses per-item unique_ids"
  - "Tests find devices through dr.async_entries_for_config_entry plus identifier filter and entities through er.async_get_entity_id (entity_id_for)"

requirements-completed: [ENT-01, ENT-02, ENT-03, ENT-04]

coverage:
  - id: D1
    description: "Entity manager adds new routers without reload, marks vanished routers missing (registry entry, name and area kept) and re-binds returning routers under the same entity_id"
    requirement: ENT-01
    verification:
      - kind: integration
        ref: "tests/test_entity_manager.py#test_new_router_appears_without_reload"
        status: pass
      - kind: integration
        ref: "tests/test_entity_manager.py#test_vanished_router_goes_missing_and_rebinds"
        status: pass
      - kind: unit
        ref: "tests/test_entity_manager.py#test_manager_adds_each_key_once_in_sorted_order"
        status: pass
    human_judgment: false
  - id: D2
    description: "Router sensors hold only their key and write state only on change (other routers keep last_reported)"
    requirement: ENT-02
    verification:
      - kind: integration
        ref: "tests/test_entity_manager.py#test_router_change_writes_only_that_router"
        status: pass
    human_judgment: false
  - id: D3
    description: "Main device and Routers/Services/Certificates sub-devices registered, named with the host, linked via via_device_id; configuration_url without userinfo"
    requirement: ENT-03
    verification:
      - kind: integration
        ref: "tests/test_entity_manager.py#test_router_sensor_on_routers_sub_device"
        status: pass
      - kind: unit
        ref: "tests/test_entity_manager.py#test_dashboard_url_variants"
        status: pass
    human_judgment: false
  - id: D4
    description: "Router ENUM sensor (enabled/warning/error/disabled/missing) follows a status change on both captures"
    requirement: ENT-04
    verification:
      - kind: integration
        ref: "tests/test_entity_manager.py#test_router_state_follows_status_change"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-11-14
status: complete
---

# Phase 5 Plan 01: Entity manager tracer (router ENUM sensor) and device topology Summary

**One entity manager per entry now adds, marks missing and re-binds router ENUM sensors that hold only their key and write on change, on a Routers sub-device linked to a named main device "Traefik (<host>)" through the device registry (HA 2026.3 and 2026.10)**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-11-14T04:50:54Z
- **Completed:** 2026-11-14T05:03Z
- **Tasks:** 2 (tracer + tdd)
- **Files modified:** 11 (2 created)

## Accomplishments

- `entity_manager.py`: `KindSpec` and the five kind constants keep the D-09 unique_id scheme in one place. `TraefikEntityManager.async_add_kind` registers the kind listener before it adds entities. The listener skips failed cycles, adds new keys once in sorted order in a single `async_add_entities` call, stamps vanished keys with `dt_util.utcnow()` and clears the mark when a key returns. No registry scan anywhere.
- `entity.py`: the device factory (`TraefikDevice`, `device_identifier`, identifiers-only `traefik_device_info`) and the write-on-change bases. `_TraefikEntityBase` records `(available, state token)` after it is added and calls `async_write_ha_state` only when that pair changes. `TraefikItemEntity` uses `(model, missing_since)` as its token and exposes `_missing_attributes()`. The empty `TYPE_CHECKING` block is gone (first half of IN-07 closed).
- `TraefikRouterSensor`: ENUM with options `list(ITEM_STATE_OPTIONS)`, translation_key `router`, `_attr_name` = Traefik router name, attributes `rule, service, provider, entry_points, middlewares, tls, errors` (lists in Traefik order), or `missing_since` while missing. It has no explicit entity_id and no icon.
- `async_setup_devices` runs between the cert first refresh and `async_forward_entry_setups`. It registers the main device (translation_key `main`, SERVICE, manufacturer Traefik, `configuration_url` from `dashboard_url`, `sw_version`) and the three sub-devices without a via argument, then links each one with `async_update_device(sub.id, via_device_id=main.id)`.
- The router stale-cleanup closure in `binary_sensor.py` is removed. It matched `http_router_` in every domain and would have deleted the new sensors. The router binary sensor class stays until 05-02.

## Task Commits

1. **Task 1 (tracer): router ENUM sensor through the entity manager** - `ff04249` (feat)
2. **Task 2 RED: failing tests for device topology and dashboard URL** - `3c60032` (test, strict xfail)
3. **Task 2 GREEN: main device + linked sub-devices, translations** - `03ad057` (feat)

## Verification (end of plan)

- `uv run pytest -q`: 540 passed (baseline 523; +17 in tests/test_entity_manager.py)
- `~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`: 540 passed (HA 2026.3.0)
- `uv run ruff check custom_components tests`: all checks passed. `ruff format --check`: 35 files already formatted
- `uv run mypy --strict custom_components/traefik_proxy`: no issues in 14 source files
- `cmp strings.json translations/en.json`: identical. The JSON key check from the acceptance criteria passes
- Tracer gate: Task 1 `<verify>` re-run end to end, all green on both HA versions, then Task 2 started
- Mutation check: removing the token comparison in `_handle_coordinator_update` makes `test_router_change_writes_only_that_router` fail

## TDD Gate Compliance (Task 2)

- RED: `3c60032`. Evidence: pytest `--junitxml` report checked with `gsd-tools check tdd-red-evidence`, verdict `RED_EVIDENCE_OK` (target `test_router_sensor_on_routers_sub_device`, 10 failed / 7 passed). Semantic assessment: the target ran and failed on the planned assertion. The main, services and certificates identifiers were missing from the entry's devices, and only the implicitly created Routers device existed. The dashboard_url and entry_host tests failed on an ImportError inside the test bodies, so they are not counted as RED targets.
- The RED commit marks the three new tests `xfail(strict=True)`, so the commit stays green (D-20). Strict xfail fails if the tests pass early.
- GREEN: `03ad057` removes the markers, and all 17 tests pass.
- REFACTOR: none needed.

## Deviations from Plan

### Acceptance-check nuance (no code change)

**1. `grep -nE "async_add_kind\(\s*ROUTERS" sensor.py` prints 0 lines.** `ruff format` puts `ROUTERS` on the line after `async_add_kind(`, and the call cannot fit on one line within the line length. A multi-line match (`grep -Pzo 'async_add_kind\(\s*ROUTERS'`, the key_link pattern) finds it. Behaviour is as planned.

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `registry` was undefined in binary_sensor.py after the router closure was removed**
- **Found during:** Task 1
- **Issue:** The removed block also defined `registry = er.async_get(hass)`, which the cert expiring cleanup still uses.
- **Fix:** Moved `registry = er.async_get(hass)` next to the cert coordinator lookup.
- **Commit:** ff04249

**2. [Rule 3 - Blocking] mypy list invariance in sensor.py after typing `async_add_entities`**
- **Found during:** Task 1
- **Fix:** The existing entity lists are now passed as `[*a, *b, *c]`.
- **Commit:** ff04249

## Worker Decisions

- The RED commit uses `xfail(strict=True)` markers, and the GREEN commit removes them. Reason: the TDD RED commit and "every commit green" (D-20/W42) both hold. Alternative: a plain failing RED commit, which breaks bisect.
- The `dashboard_url`/`entry_host` imports in the new tests are inside the test functions. Reason: the module still collects in the RED state, so the target assertion fails instead of a collection error. Alternative: module-level import.
- `async_add_kind` always calls `async_add_entities` once, also with an empty key list. Reason: simpler, and harmless. Alternative: skip the call when there are no keys.
- Kinds are keyed by `spec.name`, and the listener is `functools.partial(self._async_kind_updated, spec.name)`. Reason: no closure per kind, and the listener can be read in debug. Alternative: closure.
- Keys that vanish in the same cycle share one `utcnow()` timestamp. Only known keys can become missing. Reason: one clock read per cycle. Alternative: one read per key.
- `TraefikRouterSensor._attr_options` is set in `__init__`. Reason: ruff RUF012, and a `ClassVar` annotation would clash with HA's instance attribute type. Alternative: `# noqa`.
- `dashboard_url` also returns None for URLs without a scheme and for invalid ports. It lowercases scheme and host, because `urlsplit` normalizes them. Reason: HA rejects invalid configuration URLs with ValueError. Alternative: pass invalid URLs through.
- `entry_host` also falls back to the title for a host-less URL. Reason: the device name must never read "Traefik (None)". Alternative: an empty placeholder.
- Extra tests beyond the plan: a manager unit test with a fake coordinator (sorted order, idempotency, failed-cycle gate, re-bind), a `KindSpec` round trip, `entry_host` fallback, and four extra `dashboard_url` cases. Reason: they cover the ENT-01 ordering/idempotency edge truths directly. Alternative: full-setup tests only.
- Registry lookups in tests filter by `ROUTERS.domain` as well as `key_of`. Reason: the old router binary sensors share the `http_router_` prefix until 05-02. Alternative: none.
- The vanish/re-bind test ticks the clock 5 min before the router returns. Reason: it proves the re-bound state drops `missing_since` rather than reusing it. Alternative: no tick.
- ENT-01..04 stay unchecked ("Pending") in REQUIREMENTS.md. The `requirements.mark-complete` change was reverted. Reason: each of them is only partly delivered here (grace period 05-02, services 05-03, cert base 05-05, `sw_version` kept current later), and Phase 4 set the precedent W26 (pending until phase.complete). `requirements-completed` above lists the IDs this plan contributes to. Alternative: check them off now.
- The RED evidence files (`.red-05-01/` in the phase dir) were deleted after classification, not committed. Reason: they are generated artefacts, and the verdict is recorded here. Alternative: commit them.

## User-visible changes (for the Phase 8 CHANGELOG)

- New router ENUM sensors (`enabled` / `warning` / `error` / `disabled` / `missing`, attribute `missing_since` while missing). They replace the router binary sensors once 05-02 removes them. On a fresh install their entity_ids come from device name + router name (for example `sensor.traefik_routers_<host>_file_ok_file`).
- New routers appear without a reload. A vanished router stays registered with state `missing` and comes back under the same entity_id with its name and area.
- New main device "Traefik (<host>)" with a dashboard link and the Traefik version. New sub-devices "Traefik routers / services / certificates (<host>)" are linked to it. The old per-category devices remain until 05-03/05-05/05-07 move the remaining entities.

## Known Stubs

- None that block the plan goal. The Services and Certificates sub-devices have no entities yet (05-03 and 05-05 move service and certificate entities there). An install without TLS routers shows an empty Certificates device; this was accepted in the plan (flagged assumption, D-14).

## Issues Encountered

- None. Carry-over status: IN-07 first half (empty TYPE_CHECKING block) is closed. IN-11 (`_coordinator` alias on cert entities) is untouched; it belongs to the cert-entity rewrite in 05-05.

## Next Phase Readiness

- 05-02 can add the persisted 24 h grace period (`async_load`, deadline timer, Store) to `TraefikEntityManager`, remove `TraefikProxyRouterBinarySensor` and migrate the router tests.
- `traefik_device_info` is final for every later entity. Services and certificates attach via `_traefik_device = TraefikDevice.SERVICES / CERTIFICATES`.

## Self-Check: PASSED

- FOUND: custom_components/traefik_proxy/entity_manager.py, tests/test_entity_manager.py
- FOUND commits: ff04249, 3c60032, 03ad057 (all ancestors of HEAD)
