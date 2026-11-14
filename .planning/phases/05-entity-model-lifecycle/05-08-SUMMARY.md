---
phase: 05-entity-model-lifecycle
plan: 08
subsystem: entities
tags: [home-assistant, migration, entity-registry, device-registry, update-listener, gap-closure, traefik]
status: complete
gap_closure: true

requires:
  - phase: 05-entity-model-lifecycle
    provides: "05-07 async_migrate_entry (1.1 -> 1.2), repair issue, async_remove_legacy_devices; 05-04 async_setup_devices with per_item"
provides:
  - "__init__._ROUTER_REPLACEMENT_DISABLED_BY (USER->USER, DEVICE->USER, INTEGRATION->INTEGRATION); async_migrate_entry pre-creates disabled router sensor replacements with the old object id"
  - "async_setup_entry binds the update listener through entry.async_on_unload; async_unload_entry docstring corrected"
  - "entity._async_remove_device_if_unreferenced: the single device-removal path for the per-item-off sub-device removal and the legacy cleanup"
  - "05-REVIEW-DISPOSITION.md: CR-01, WR-01, WR-02 fixed"
affects: [phase-07-config-flow, phase-08-changelog]

actuals:
  tokens: 7300
  tasks: 3
  commits: 7
plan_head_before: 1f1db96c1087590ae8a00e479cfe6e00fb37a484
plan_head_after: 8c77e32f979afa2ae50506708162c57d825c1862

tech-stack:
  added: []
  patterns:
    - "Registry migrations that replace an entity carry its disabled state by pre-creating the replacement with async_get_or_create(..., disabled_by=..., suggested_object_id=<old object id>) after removing the old entry; the platform re-points device_id later"
    - "Update listeners are always registered as entry.async_on_unload(entry.add_update_listener(...))"
    - "Every device removal in entity.py goes through _async_remove_device_if_unreferenced (er.async_entries_for_device(..., include_disabled_entities=True) must be empty)"

key-files:
  created:
    - .planning/phases/05-entity-model-lifecycle/05-08-SUMMARY.md
  modified:
    - custom_components/traefik_proxy/__init__.py
    - custom_components/traefik_proxy/entity.py
    - tests/test_migration.py
    - tests/test_init.py
    - tests/test_devices.py
    - .planning/phases/05-entity-model-lifecycle/05-REVIEW-DISPOSITION.md

key-decisions:
  - "Disabled router replacements: USER->USER, DEVICE->USER, INTEGRATION->INTEGRATION; none for enabled or CONFIG_ENTRY - plan decision"
  - "The replacement entity_id is seeded with the removed binary sensor's object id; name, area, icon are not carried over - plan decision"
  - "One _async_remove_device_if_unreferenced helper guards both device-removal paths - plan decision"
  - "WR-01 fixed minimally now (async_on_unload wrap plus docstring) - plan decision"
  - "Planning references next to touched comments (D-15 labels in entity.py and __init__.py) were replaced by plain language instead of being relabelled D-13 - worker decision"

requirements-completed: []

coverage:
  - id: D1
    description: "A USER-disabled 0.3.0 router binary sensor becomes the USER-disabled sensor.traefik_http_router_file_ok_file on the Routers sub-device with no state; an enabled one comes back enabled with state; issue removed_count 2"
    requirement: ENT-09
    verification:
      - kind: integration
        ref: "tests/test_migration.py::test_user_disabled_router_stays_disabled"
        status: pass
  - id: D2
    description: "Replacement disabled_by per old value: user->USER, device (on a disabled legacy device)->USER, integration->INTEGRATION, enabled->enabled with platform entity_id; no user name carried over; legacy http_routers device removed"
    requirement: ENT-09
    verification:
      - kind: integration
        ref: "tests/test_migration.py::test_disabled_router_replacement_keeps_disabled_state[user,device,integration,enabled]"
        status: pass
  - id: D3
    description: "Second migration run with disabled replacements present leaves every registry entry unchanged and keeps one issue with removed_count 4"
    requirement: ENT-09
    verification:
      - kind: unit
        ref: "tests/test_migration.py::test_migration_with_disabled_routers_is_idempotent"
        status: pass
  - id: D4
    description: "Update listeners: 1 after setup, 1 after reload, one run per options change, 0 after unload"
    requirement: ENT-09
    verification:
      - kind: integration
        ref: "tests/test_init.py::test_update_listener_registered_once_across_reloads"
        status: pass
  - id: D5
    description: "Per-item off keeps a Routers sub-device a foreign (enabled or user-disabled) registry entry references; the unreferenced Services sub-device is removed; router/service entries purged"
    requirement: ENT-10
    verification:
      - kind: integration
        ref: "tests/test_devices.py::test_per_item_off_keeps_referenced_sub_device[enabled,user-disabled]"
        status: pass

duration: 8min
completed: 2026-11-14
---

# Phase 5 Plan 08: Gap closure CR-01, WR-01, WR-02 Summary

**Disabled 0.3.0 routers stay disabled across the 1.2 migration (pre-created replacement with the old object id), the options listener is bound to entry unload, and both device-removal paths share one "only when unreferenced" guard.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-11-14T22:48:55Z
- **Completed:** 2026-11-14T22:56:19Z
- **Tasks:** 3 (1 tracer, 2 auto, all TDD)
- **Files modified:** 6

## Accomplishments

- **CR-01 / G6 closed (ENT-09, D-18):** `async_migrate_entry` records every removed router binary sensor whose `disabled_by` has a mapping and, after the removal loop, pre-creates `sensor` registry entries with the same unique_id, the mapped `disabled_by` and `suggested_object_id=<old object id>`. The platform later re-points `device_id` to the Routers sub-device. `removed_count` still counts every removed entry.
- **WR-01 closed:** `entry.async_on_unload(entry.add_update_listener(_async_options_updated))`; comment and `async_unload_entry` docstring describe the real behaviour.
- **WR-02 closed (ENT-10, ENT-03):** `_async_remove_device_if_unreferenced` is the only `async_remove_device` call in `entity.py`; `async_setup_devices` (per-item off) and `async_remove_legacy_devices` both use it.
- Review disposition updated: CR-01, WR-01, WR-02 `fixed`; IN-01..IN-04 unchanged.

## Task Commits

| Task | RED (test) | GREEN (fix) |
|------|------------|-------------|
| 1 Tracer: USER-disabled router survives migration | `50bcc4c` | `09241f2` |
| 2 DEVICE/INTEGRATION mapping, idempotency, listener lifecycle | `98602c2` | `c265fa5` |
| 3 Per-item-off sub-device reference guard | `6ba969e` | `db2762c` |
| 3 Disposition | - | `8c77e32` (docs) |

### RED evidence (`--runxfail`)

- Task 1: `test_user_disabled_router_stays_disabled` failed on the entity_id assertion: `sensor.traefik_routers_traefik_example_com_file_ok_file` instead of `sensor.traefik_http_router_file_ok_file` (the replacement was created by the platform, enabled).
- Task 2: `[device]` -> `assert None is <RegistryEntryDisabler.USER>`; `[integration]` -> `assert None is <RegistryEntryDisabler.INTEGRATION>`; idempotency -> `no sensor entity with unique_id legacy-entry_http_router_whoami@docker`; listener -> `assert 2 == 1` (two listeners after one reload). `[user]` and `[enabled]` passed at RED (no marker, as planned).
- Task 3: both params failed with `KeyError: ('traefik_proxy', 'device-entry_routers')` (Routers sub-device deleted after the per-item-off reload).

## Measured listener counts

| Point | Before (HEAD 1f1db96, from planning probe and RED run) | After |
|-------|------|-------|
| after setup | 1 | 1 |
| after one `async_reload` | 2 | 1 |
| listener runs per options change after reload | 2 | 1 |
| after `async_unload` | 2 | 0 |

## Verification (end of plan)

| Gate | Result |
|------|--------|
| `uv run pytest -q` | 572 passed (baseline 563, +9) |
| HA 2026.3.0 venv `pytest -q -o addopts="" tests` | 572 passed |
| `ruff check custom_components tests` | All checks passed |
| `ruff format --check custom_components tests` | 38 files already formatted |
| `mypy --strict custom_components/traefik_proxy` | no issues in 14 source files |
| `tests/test_migration.py` | 12 passed (baseline 6) |
| `tests/test_devices.py` | 9 passed (baseline 7) |
| `grep -rn xfail tests/` | empty |
| `grep -cE "^\s+device_registry\.async_remove_device\(" entity.py` | 1 |
| planning refs (`D-xx` etc.) in `__init__.py` / `entity.py` | 4 / 0 (baselines 5 / 1) |
| phase invariants (`registry.entities`, `self.entity_id = `, `via_device=`) | none found |

Every intermediate commit was green on both venvs (RED commits with strict xfail markers).

## Proofs for the user priorities

- **User-disabled routers stay disabled:** `tests/test_migration.py::test_user_disabled_router_stays_disabled` and `::test_disabled_router_replacement_keeps_disabled_state[user|device|integration]` (no state, disabled_by kept, old object id), plus `::test_migration_with_disabled_routers_is_idempotent` (a second run changes nothing).
- **A referenced sub-device is kept:** `tests/test_devices.py::test_per_item_off_keeps_referenced_sub_device[enabled|user-disabled]` (same device id, foreign entry keeps `device_id` and `disabled_by`); the existing `test_legacy_device_with_entity_is_kept[...]` still guards the legacy path through the same helper.
- **No rename/re-ID of survivors:** `test_migration_from_1_1` (service sensor keeps entity_id and name) is unchanged and green; `async_get_or_create` returns existing entries unchanged.

## TDD Gate Compliance

Each task has a `test(05-08)` RED commit followed by a `fix(05-08)` GREEN commit; RED tests carried `xfail(strict=True)` and were confirmed failing with `--runxfail` on behaviour assertions, not fixture or import errors. All markers are removed.

## Deviations from Plan

None in behaviour. Small adjustments:

- The idempotency test and the parametrized test share a `_disabled_legacy_routers_device` helper in `tests/test_migration.py` (instead of inlining the device creation twice).
- The tracer gate ran in auto mode (`workflow.auto_advance: true`): `<verify>` re-run green on both venvs before expansion.

## Worker Decisions

| Decision | Reason | Alternative |
|---|---|---|
| Replaced the two `(D-15)` comment labels (above `LEGACY_DEVICE_SUFFIXES` in `entity.py`, the "Safe order" comment in `async_setup_entry`) with plain language instead of relabelling them `D-13` | The plan-checker advisory asked to cite D-13 for "remove a device only when unreferenced"; in `05-CONTEXT.md` that rule actually sits in D-15's text, while D-13 defines the device topology the rule protects. Dropping the id avoids a wrong label either way and follows M22 (no planning refs in shipped code); counts went 5 -> 4 and 1 -> 0 | Relabel to `D-13` (contradicts CONTEXT text) or leave `D-15` |
| `mapped` is computed with an explicit `is not None` check before `dict.get` | mypy --strict rejects `dict.get` with an `Optional` key on a `dict[RegistryEntryDisabler, ...]` | `if disabled_by in mapping: mapping[disabled_by]` (same typing issue) |
| The migration debug line also logs the number of disabled routers kept disabled (counts and entry_id only) | The plan allowed it optionally; useful when diagnosing an upgrade, no URL or token involved (T-05-20) | Leave the log line unchanged |
| `async_remove_legacy_devices` docstring shortened; the "why" (removing a device removes/unlinks entities) moved to the helper's docstring | One place explains the rule the helper enforces | Repeat the explanation in both docstrings |
| The listener test asserts `entry.state is LOADED` after the reload | Makes a failed reload fail loudly instead of surfacing as a listener-count mismatch | Count only |

Plan decisions (recorded in the plan's decision table, applied as written): USER->USER, DEVICE->USER, INTEGRATION->INTEGRATION mapping, none for enabled/CONFIG_ENTRY; object-id seed via `suggested_object_id`; no carry-over of name/area/icon/labels/hidden; one guard helper for both removal paths; minimal WR-01 fix now; disposition update in the last task.

Decision references: the "remove a device only when unreferenced" rule is CONTEXT D-15's legacy-cleanup text, protecting the D-13 device topology; D-06 (purge before devices) and D-18 (user-disabled entries stay disabled) are unchanged.

## User-visible changes (Phase 8 CHANGELOG)

- A router disabled in 0.3.0, directly, by disabling its "HTTP Routers" device, or through the "disable new entities" preference, stays disabled after the upgrade and appears as the disabled sensor `sensor.<old object id>`, for example `sensor.traefik_http_router_<name>`.
- A router disabled in 0.3.0 keeps its old-style entity id (`sensor.traefik_http_router_<x>`) even if re-enabled later, while other routers use `sensor.traefik_routers_<host>_<x>`.
- Options changes no longer apply twice after a reload.
- Switching per-item entities off keeps a Routers/Services device that another integration's entity still uses.

## Known Stubs

None.

## Threat Flags

None. The new registry writes (T-05-17), listener binding (T-05-18) and device guard (T-05-19) are the mitigations from the plan's threat register; no new endpoint, auth path or file access.

## Issues Encountered

None.

## Next Phase Readiness

Gap G6 and review findings CR-01, WR-01, WR-02 are closed; Phase 5 is ready for re-verification. ENT requirements stay Pending in REQUIREMENTS.md until phase completion (phase convention).
