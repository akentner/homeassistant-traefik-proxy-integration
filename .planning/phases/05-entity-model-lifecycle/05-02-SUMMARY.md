---
phase: 05-entity-model-lifecycle
plan: 02
subsystem: entities
tags: [home-assistant, entity-manager, grace-period, storage, entity-registry, enum-sensor, traefik]

requires:
  - phase: 05-entity-model-lifecycle
    provides: "05-01 TraefikEntityManager (async_add_kind, missing_since, kind listener), TraefikRouterSensor (ENUM), conftest helpers make_traefik_entry/setup_traefik_entry/entity_id_for/restub_traefik/rawdata_copy"
provides:
  - "Router binary_sensor removed; a router is only an ENUM sensor (router half of ENT-04)"
  - "const.py: MISSING_GRACE_PERIOD = timedelta(hours=24), MISSING_CHECK_INTERVAL = timedelta(minutes=5)"
  - "entity_manager.py: MISSING_STORE_VERSION, MissingData, missing_store_key(entry_id), async_remove_missing_store(hass, entry_id), TraefikEntityManager.async_load(), orphan adoption in async_add_kind, _async_check_deadlines (deadline timer), Store writes only on change"
  - "__init__.py: entity_manager.async_load() before async_setup_devices; async_remove_entry deletes the missing-since Store"
  - "tests: test_router_sensors (both captures), 9 grace-period tests in tests/test_entity_manager.py"
affects: [05-03, 05-04, 05-05, 05-07, phase-08-changelog]

actuals:
  tokens: 11671
  tasks: 2
  commits: 3
plan_head_before: f457eb074065ae4c928f3af7fcaa781f69a26433
plan_head_after: 9a5674a774fa982f41aa4b7d80a676b2bde60620

tech-stack:
  added: []
  patterns:
    - "Per-entry helpers.storage.Store holds {kind name: {key: ISO-8601 UTC}}; stored times of kinds not registered yet are carried through every write"
    - "Deadline check from async_track_time_interval(cancel_on_shutdown=True) registered via entry.async_on_unload; it walks only the in-memory missing maps"
    - "Registry access: one er.async_entries_for_config_entry read in async_load, then per-unique_id async_get_entity_id + async_remove on a fired deadline only"
    - "Tests drive the deadline check with async_fire_time_changed(hass, utcnow + CHECK_INTERVAL): every timer due within one interval fires, the wall clock stays put"

key-files:
  created: []
  modified:
    - custom_components/traefik_proxy/binary_sensor.py
    - custom_components/traefik_proxy/sensor.py
    - custom_components/traefik_proxy/const.py
    - custom_components/traefik_proxy/entity_manager.py
    - custom_components/traefik_proxy/__init__.py
    - tests/test_binary_sensor.py
    - tests/test_coordinator.py
    - tests/test_platforms_real_fixtures.py
    - tests/test_cert_entity_state.py
    - tests/test_entity_manager.py

key-decisions:
  - "missing_since persisted in a per-entry helpers.storage.Store (traefik_proxy.missing.<entry_id>), not RestoreEntity (plan decision, W38)"
  - "Deadline check by async_track_time_interval every 5 min (plan decision); removal lands at most one interval after the deadline"
  - "Stored missing-since times in the future are clamped to now at load, so a clock jump back cannot postpone removal without bound"
  - "The Store is created in async_load; a manager that was never loaded (unit tests) skips persistence"

patterns-established:
  - "Grace-period tests use test-local GRACE/CHECK_INTERVAL and a test-local store-key builder, so they check the spec values instead of the constants"

requirements-completed: []

coverage:
  - id: D1
    description: "A vanished router keeps its registry entry (name, area) until 24 h have passed and is removed by the manager's own timer; the deadline is inclusive"
    requirement: ENT-01
    verification:
      - kind: integration
        ref: "tests/test_entity_manager.py#test_vanished_router_removed_after_grace_period"
        status: pass
      - kind: integration
        ref: "tests/test_entity_manager.py#test_grace_deadline_is_inclusive"
        status: pass
    human_judgment: false
  - id: D2
    description: "A router that reappears inside the grace period keeps one registry entry and its entity_id; the original deadline removes nothing"
    requirement: ENT-01
    verification:
      - kind: integration
        ref: "tests/test_entity_manager.py#test_reappearing_router_inside_grace_keeps_entity"
        status: pass
    human_judgment: false
  - id: D3
    description: "missing_since survives an entry reload (Store); orphan registry entries are adopted as missing or removed at setup when their stored deadline passed; entry removal deletes the Store"
    requirement: ENT-01
    verification:
      - kind: integration
        ref: "tests/test_entity_manager.py#test_grace_period_survives_entry_reload"
        status: pass
      - kind: integration
        ref: "tests/test_entity_manager.py#test_orphan_registry_entry_adopted_and_removed_after_grace"
        status: pass
      - kind: integration
        ref: "tests/test_entity_manager.py#test_expired_stored_orphan_removed_at_setup"
        status: pass
      - kind: integration
        ref: "tests/test_entity_manager.py#test_remove_entry_deletes_missing_store"
        status: pass
    human_judgment: false
  - id: D4
    description: "An empty snapshot only marks missing; a failed cycle makes router sensors unavailable and never marks a key missing"
    requirement: ENT-02
    verification:
      - kind: integration
        ref: "tests/test_entity_manager.py#test_empty_snapshot_marks_missing_and_deletes_nothing"
        status: pass
      - kind: integration
        ref: "tests/test_entity_manager.py#test_failed_cycle_never_marks_missing"
        status: pass
    human_judgment: false
  - id: D5
    description: "On the v2.11 and v3.7 captures every router has exactly one ENUM sensor whose state is the router status; no router binary_sensor registry entry"
    requirement: ENT-04
    verification:
      - kind: integration
        ref: "tests/test_platforms_real_fixtures.py#test_router_sensors"
        status: pass
    human_judgment: false

duration: 261min
completed: 2026-11-14
status: complete
---

# Phase 5 Plan 02: Router binary sensor removed, persisted 24 h grace period Summary

**Routers now exist only as ENUM sensors. A vanished router stays `missing` for 24 h of wall-clock time, and that time survives reloads and restarts through a per-entry Store. After that the manager's own 5-minute timer removes its registry entry. Orphan registry entries are adopted at setup. Everything passes on HA 2026.3 and 2026.10.**

## Performance

- **Duration:** 261 min wall clock, measured from the first command (05:05Z) to the SUMMARY (09:27Z). This includes time spent waiting outside the agent. Active work was far shorter.
- **Started:** 2026-11-14T05:05:10Z
- **Completed:** 2026-11-14T09:27Z
- **Tasks:** 2 (auto + tdd)
- **Files modified:** 10

## Accomplishments

- `binary_sensor.py`: removed `TraefikProxyRouterBinarySensor`, the Host-rule hint helper and its regex, and the `re`/`Router`/`Status` imports. The module and setup docstrings now describe only the aggregates and the certificate entities.
- Router tests now read the ENUM sensor through `entity_id_for` + `ROUTERS.unique_id`:
  - `test_router_sensors` covers both captures, with an exact router-key count and no `binary_sensor` router key.
  - Updated: the coordinator rawdata test (`enabled` / `error`) and the cert availability test (router sensor `unavailable` after a failed main cycle).
- `entity_manager.py`:
  - `async_load()` loads the Store, reads `er.async_entries_for_config_entry` once and starts the deadline timer.
  - `async_add_kind` adopts orphans: each one is missing since its stored time (or now when none is stored). It is removed at once if that time is already at least 24 h old.
  - `_async_check_deadlines` removes the registry entries whose grace period ran out.
  - `_async_schedule_save` writes the Store as a config-entry task, and only when the serialized map differs from the last write.
- `__init__.py`: `async_load()` runs between the cert first-refresh block and `async_setup_devices`. The new `async_remove_entry` deletes the Store.

## Task Commits

1. **Task 1: remove the router binary sensor; router tests read the ENUM sensor** - `d904200` (refactor)
2. **Task 2 RED: failing grace-period tests** - `945b22a` (test, 5 strict xfail)
3. **Task 2 GREEN: persisted grace period, deadline timer, orphan adoption, async_remove_entry** - `9a5674a` (feat)

## Verification (end of plan)

- `uv run pytest -q`: 535 passed (baseline 540). Task 1 deleted 14 router binary_sensor test items in tests/test_binary_sensor.py (parametrized cases counted) and replaced the capture test one for one (net -14). Task 2 added 9 tests. No "Lingering timer" in the output.
- `~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`: 535 passed (HA 2026.3.0)
- `uv run ruff check custom_components tests`: all checks passed. `ruff format --check`: 35 files already formatted
- `uv run mypy --strict custom_components/traefik_proxy`: no issues in 14 source files
- Acceptance greps (Task 1):
  - `RouterBinarySensor`, `friendly_rule`, `binary_sensor.traefik_http_router` and the duplicate attribute keys: 0 hits.
  - `def test_router_sensors`: 1.
- Acceptance greps (Task 2):
  - `MISSING_GRACE_PERIOD: Final = timedelta(hours=24)`: 1. `cancel_on_shutdown=True`: 1. `async_entries_for_config_entry`: 1. `async def async_remove_entry`: 1.
  - No `registry.entities` in entity_manager.py.
  - `-k "grace or reload or orphan or empty or failed or remove_entry"`: 10 passed.
- Mutation check: changing `>=` to `>` in `_async_check_deadlines` makes `test_grace_deadline_is_inclusive` fail. The change was reverted.
- No HA 2026.11-only API is used. The `config_entry_id` hits in entity.py are the existing 05-01 device-registry calls.

## TDD Gate Compliance (Task 2)

- RED: `945b22a`. Run with `--runxfail`, 5 failed / 2 passed. Each failure is on the planned assertion:
  - the registry entry still exists after the grace period (vanished);
  - KeyError on the Store key (reload, remove_entry);
  - no state for the orphan (orphan);
  - the expired orphan's registry entry still exists (expired).
- Empty-snapshot, failed-cycle and reappearing-router behaviour already held after 05-01, so those 3 tests are plain passing tests without markers.
- The RED commit marks the 5 failing tests `xfail(strict=True)`, so the commit stays green (the 05-01 convention).
- GREEN: `9a5674a` removes the markers. All 26 manager tests pass.
- REFACTOR: none needed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Comment in sensor.py named the removed class**
- **Found during:** Task 1 (acceptance grep `! grep -rn "RouterBinarySensor" custom_components tests`)
- **Issue:** A comment on the entrypoint sensor's `entrypoint_name` attribute still referred to the router binary sensor's `router_name` alias. It was one of the 4 baseline hits in custom_components.
- **Fix:** Deleted the two comment lines. sensor.py was not listed in Task 1's files, and there is no behaviour change.
- **Files modified:** custom_components/traefik_proxy/sensor.py
- **Commit:** d904200

### Additions beyond the plan

- `test_grace_deadline_is_inclusive`, a 9th grace test. The ±1 s boundary tests cannot tell `>=` from `>`. This test proves the inclusive-deadline truth (Edge ENT-01/adjacency) directly, and the mutation check confirmed it.

## Worker Decisions

- **Store creation:** the Store is created in `async_load` (not `__init__`), and `_async_schedule_save` does nothing while it is None. Reason: the 05-01 manager unit test builds a manager on a MagicMock hass and never loads it. Alternative: build the Store in `__init__` and change that test.
- **Write only on change:** a save is skipped when the serialized map equals the last written one. A kind update calls the save only when keys vanished or returned. Reason: this meets "no write when nothing changed" with one comparison. Alternative: track a dirty flag per mutation.
- **Kinds not registered yet:** their stored times are kept in `_stored` and carried into every write until the kind registers. Reason: the router saves in this plan must not wipe the service or certificate entries that 05-03/05-05 will read. Alternative: write only registered kinds, which would lose data.
- **Future timestamps:** stored times in the future are clamped to now at load. Reason: a clock jump back or a tampered file must not postpone deletion without bound. Alternative: keep them as stored.
- **Malformed Store data:** non-dict data, non-string keys and unparsable or naive values are dropped silently. Reason: the plan says unparsable/naive values are dropped, and this extends the same rule to structural damage. Alternative: discard the whole file.
- **Clock used by the check:** `_async_check_deadlines` uses `dt_util.utcnow()` and ignores the timer's `now` argument. Reason: the plan prescribes `dt_util.utcnow()`. Also, in tests the timer's argument is the patched fire time, not the wall clock. Alternative: use the argument.
- **Logging:** the setup log line now reads "Added N <kind> entities (M missing)". Reason: one debug line also shows how many orphans were adopted. Alternative: a separate log line.
- **How tests run the check:** grace tests fire the timer with `async_fire_time_changed(hass, utcnow + 5 min)`. Reason: after a check at 24 h - 1 s the interval timer is next due 5 min later, so a plain fire at 24 h + 1 s would not run it. Firing with a future time runs the next due check without moving the wall clock, so the check still sees exactly 24 h ± 1 s. Alternative: `fire_all=True`, or move the clock by a whole interval, which would lose the boundary.
- **Test-local spec values:** the tests use their own `GRACE`, `CHECK_INTERVAL` and `_store_key`, not the production constants. Reason: the RED commit can collect (the constants did not exist yet), and the tests check the spec values (24 h, key `traefik_proxy.missing.<entry_id>`) instead of echoing the constants. Alternative: import the constants.
- **Orphan test setup:** orphan tests create the registry entry after `entry.add_to_hass` and before `async_setup`, through a local helper (`_setup_with_ghost`). Reason: `setup_traefik_entry` adds the entry itself, and the registry entry must exist before setup. Alternative: extend the conftest helper.
- **Unused device label:** the now-unused `"http_routers"` label in `entity.py` `_CATEGORY_TO_MODEL` is left in place. Reason: the old per-category devices are cleaned up by the 0.3.0 migration (05-07), and the dead dict entry is harmless. Alternative: delete it now.

## User-visible changes (for the Phase 8 CHANGELOG)

- Router binary sensors (`binary_sensor.traefik_http_router_*`) are gone. The router ENUM sensors from 05-01 (`enabled` / `warning` / `error` / `disabled` / `missing`) replace them. The old registry entries are migrated or removed in 05-07.
- A router that disappears from Traefik keeps its entity in state `missing` (attribute `missing_since`) for 24 hours, including across restarts and reloads. After that the entity is removed, at most 5 minutes after the deadline. A router that comes back within 24 hours keeps its entity_id, name and area.
- Router entities left over in the registry whose router no longer exists show up as `missing` at startup and are removed 24 hours later (or right away when the stored deadline already passed).
- Removing the integration entry also removes its missing-since data in `.storage`.

## Known Stubs

- None. No placeholder values were introduced, and the grace-period lifecycle is fully wired for routers. Services, entrypoints and certificates get it when 05-03 and 05-05 register them as manager kinds.

## Threat Flags

None. The new `.storage` file is covered by T-05-04 (accepted), and the deletion path follows the T-05-01 mitigation (tests: grace boundary, reload, empty snapshot, failed cycle).

## Issues Encountered

- One attempted mutation check was blocked by the permission classifier because it ended with `git checkout -- <file>` on an uncommitted file. That would have discarded the Task 2 implementation, so the block was correct. Nothing ran. The check was then done reversibly with `sed` and passed.

## Next Phase Readiness

- 05-03 / 05-05: registering a kind through `async_add_kind` gives services, entrypoints and certificates the full lifecycle (missing, grace period, orphan adoption, persistence) with no extra manager code. The Store already keeps entries for kinds that are not registered.
- 05-04 (per-item purge) is the only other path that may delete registry entries. It should also drop the purged keys from the kind's `missing` map and save.

## Self-Check: PASSED

- FOUND: custom_components/traefik_proxy/entity_manager.py (`async_remove_missing_store`), custom_components/traefik_proxy/__init__.py (`async def async_remove_entry`), tests/test_platforms_real_fixtures.py (`def test_router_sensors`)
- FOUND commits: d904200, 945b22a, 9a5674a (all ancestors of HEAD)
