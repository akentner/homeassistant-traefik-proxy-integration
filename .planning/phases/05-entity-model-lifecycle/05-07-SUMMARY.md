---
phase: 05-entity-model-lifecycle
plan: 07
subsystem: entities
tags: [home-assistant, translations, icons, migration, repair-issue, device-registry, traefik]
status: complete

requires:
  - phase: 05-entity-model-lifecycle
    provides: "05-01 TraefikEntity base, device factory, write-on-change contract; 05-04 async_setup_devices + per_item; 05-05 TraefikCertEntity; 05-06 refresh button (last entity off the old bases)"
provides:
  - "translations/de.json: German device, entity and issues strings (config/options stay English until Phase 7)"
  - "icons.json: default icon per translation key, ENUM state icons for router/service, on/off icons for the problem aggregates and certificate_expiring"
  - "config_flow MINOR_VERSION 2; __init__.async_migrate_entry (1.1 -> 1.2) with persistent non-fixable repair issue entities_migrated_<entry_id>; async_remove_entry deletes it"
  - "entity.py: LEGACY_DEVICE_SUFFIXES, async_remove_legacy_devices (after platform forwarding, only empty legacy devices of this entry), async_track_sw_version (one device update per Traefik version change)"
  - "removed: _TraefikProxyBaseEntity, TraefikProxyEntity, TraefikProxyCertEntity, _CATEGORY_TO_MODEL, _category_to_model"
affects: [phase-07-config-flow, phase-08-changelog]

actuals:
  tokens: 14700
  tasks: 3
  commits: 6
plan_head_before: 941beff1954967fe52f764bfbb891e07fee94ada
plan_head_after: e483477e51113a3fc00629d0bb981cb1346744b2

tech-stack:
  added: []
  patterns:
    - "Legacy device cleanup runs after async_forward_entry_setups and removes a device only while er.async_entries_for_device(..., include_disabled_entities=True) is empty"
    - "Registry migrations iterate er.async_entries_for_config_entry of the entry only; disabled_by is cleared only when it is INTEGRATION"
    - "Zero-write tests snapshot State.last_reported values, not State objects (HA updates last_reported in place)"

key-files:
  created:
    - custom_components/traefik_proxy/translations/de.json
    - custom_components/traefik_proxy/icons.json
    - tests/test_translations.py
    - tests/test_migration.py
    - tests/test_devices.py
  modified:
    - custom_components/traefik_proxy/__init__.py
    - custom_components/traefik_proxy/entity.py
    - custom_components/traefik_proxy/config_flow.py
    - custom_components/traefik_proxy/translations/en.json
    - custom_components/traefik_proxy/strings.json
    - tests/test_entity_manager.py

key-decisions:
  - "Legacy devices are removed at every setup after the platforms are forwarded, and only while no registry entry references them - plan decision"
  - "sw_version is tracked by a main-coordinator listener that compares against the last version - plan decision"
  - "async_remove_legacy_devices also skips any device that carries a current (main/sub) identifier, besides requiring exactly one legacy identifier - worker decision"
  - "The second config entry in the cross-entry tests is a user-disabled entry, because setting up the integration sets up every enabled entry of the domain - worker decision"

requirements-completed: []

coverage:
  - id: D1
    description: "strings.json == en.json byte for byte; de.json keys/placeholders mirror en.json for device/entity/issues; no empty strings; router/service state keys == ITEM_STATE_OPTIONS; every code translation key has en/de text and icons; PARALLEL_UPDATES 0/0/1; German sub-device names"
    requirement: ENT-08
    verification: "tests/test_translations.py (8 tests)"
  - id: D2
    description: "1.1 -> 1.2 migration: replaced entries removed, aggregates enabled only where INTEGRATION-disabled, USER-disabled kept, service entity_id and user name kept, cert entry kept, one repair issue with exact fields; other config entry untouched"
    requirement: ENT-09
    verification: "tests/test_migration.py::test_migration_from_1_1"
  - id: D3
    description: "No issue for a 1.1 entry without old entries; 1.2 entry skips migration; issue survives reload and unload, deleted with the Store on remove; version 2 -> MIGRATION_ERROR, registry untouched; migration idempotent"
    requirement: ENT-09
    verification: "tests/test_migration.py (remaining 5 tests)"
  - id: D4
    description: "Empty legacy devices removed after re-pointing; legacy device holding an entity kept (enabled, user-disabled, integration-disabled); devices of another entry untouched; surviving entities keep entity_id, name, disabled_by"
    requirement: ENT-03
    verification: "tests/test_devices.py::test_legacy_devices_removed_after_entities_moved, ::test_legacy_device_with_entity_is_kept[3 cases], ::test_devices_of_other_entry_untouched"
  - id: D5
    description: "Main device sw_version follows the Traefik version with exactly one sw_version update; router-only change adds none"
    requirement: ENT-03
    verification: "tests/test_devices.py::test_main_device_sw_version_follows_traefik"
  - id: D6
    description: "Sub-devices via_device_id == main.id; no via_device / report_usage / 'Detected that custom integration' record on the dev venv"
    requirement: ENT-03
    verification: "tests/test_devices.py::test_sub_devices_linked_without_deprecation"
  - id: D7
    description: "With every entity enabled, a forced main notification, an unchanged cert notification and an unchanged refresh leave last_reported unchanged for every entity of the entry"
    requirement: ENT-02
    verification: "tests/test_entity_manager.py::test_unchanged_notifications_write_no_state"

duration: 14min
completed: 2026-11-14
---

# Phase 5 Plan 07: German strings, icons, 0.3.0 migration, legacy device cleanup and live sw_version Summary

**What this plan adds:**
- German device, entity and repair strings, plus `icons.json` with state icons.
- A one-time 1.1 -> 1.2 migration for 0.3.0 installs. It removes the replaced router binary sensors and the reload button, turns on the core-value aggregates and raises a persistent repair notice (English and German).
- Removal of old per-category devices, but only once no registry entry still uses them.
- A main device `sw_version` that follows Traefik upgrades.
- The old entity bases are gone. Tests now cover the phase-wide invariants: zero writes on unchanged data, and no deprecation records.

## Performance

- **Duration:** about 14 min
- **Started:** 2026-11-14T21:48:06Z
- **Completed:** 2026-11-14T22:02Z (approx.)
- **Tasks:** 3, each TDD with a RED and a GREEN commit
- **Files:** 5 created, 6 modified

## Accomplishments

- **Task 1 (ENT-08):**
  - `translations/de.json` has the sections `device`, `entity` and (from Task 2) `issues`, written with real umlauts.
  - `icons.json` gives a default icon for each of the 15 translation keys. Router and service also have an icon per `ITEM_STATE_OPTIONS` value. The three problem aggregates and `certificate_expiring` have on/off icons.
  - `tests/test_translations.py` reads the translation keys from the code: the class-level `__attr_translation_key` of six classes plus the `SNAPSHOT_SENSORS` and `PROBLEM_SENSORS` descriptions. A renamed key, a missing German text or icon, a drifting placeholder or a changed `PARALLEL_UPDATES` value fails the tests.
- **Task 2 (ENT-09, D-18, D-19, M34):**
  - `MINOR_VERSION = 2`.
  - `async_migrate_entry` returns False for `version > 1`. For 1.1 entries it does the following, in this entry's registry entries only:
    - removes the binary_sensor entries with prefix `{entry_id}_http_router_` and the button `{entry_id}_diagnostics_reload`;
    - clears `disabled_by` on the three aggregates only where it is `INTEGRATION`;
    - bumps the entry to 1.2;
    - creates the repair issue when something was removed, using only keywords that exist in HA 2026.3. Placeholders: `entry_title` and `removed_count`.
  - `async_remove_entry` deletes the issue. Unload leaves it in place.
  - `strings.json` is still byte-identical to `en.json`.
- **Task 3 (ENT-03, D-07, D-14, D-15, ENT-02):**
  - `async_remove_legacy_devices` runs right after `async_forward_entry_setups`. `async_track_sw_version` is bound through `entry.async_on_unload`.
  - The old per-category base classes, the category table and the now-unused imports (`DEFAULT_NAME`, `TraefikSnapshot`) are deleted from `entity.py`. Every entity now derives from `TraefikEntity` or `TraefikCertEntity`.
- **Carry-over closures across the phase:**
  - IN-07 first half (empty `TYPE_CHECKING` block, 05-01): closed. `entity.py` has no `TYPE_CHECKING`.
  - IN-02 (reload verification loop, 05-06): closed. No `reload_routers` is left in the integration.
  - IN-11 (`_coordinator` alias, 05-05): closed. Zero hits for `self._coordinator`.

## Task Commits

1. **Task 1 RED:** `21a8a43` (test). Translation and icon tests, with the six de/icons-dependent tests marked `xfail(strict=True)`.
2. **Task 1 GREEN:** `ebcf631` (feat). de.json, icons.json, markers removed.
3. **Task 2 RED:** `3a397a3` (test). Migration tests; 5 are xfail(strict). The downgrade test passes already because HA reports MIGRATION_ERROR when there is no handler.
4. **Task 2 GREEN:** `090d156` (feat). MINOR_VERSION 2, `async_migrate_entry`, issue creation and deletion, en/strings/de issue strings.
5. **Task 3 RED:** `4a344b8` (test).
   - The cleanup and sw_version tests are xfail(strict).
   - The keep-path, other-entry, via_device and zero-write tests pass already, because they check existing invariants.
6. **Task 3 GREEN:** `e483477` (feat). Legacy device cleanup, sw_version tracking, old bases deleted.

## Verification (end of plan)

- `uv run pytest -q`: **563 passed** (baseline 541; +8 translations, +6 migration, +7 devices, +1 entity manager). No "Lingering" in the output.
- HA 2026.3.0 venv (`~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`): **563 passed**. This proves `async_create_issue` gets no keyword that only exists in 2026.11.
- `uv run ruff check custom_components tests`: all checks passed. `ruff format --check`: 38 files already formatted.
- `uv run mypy --strict custom_components/traefik_proxy`: no issues in 14 source files.
- Acceptance greps all pass:
  - Both JSON files load as UTF-8.
  - `Jetzt aktualisieren` occurs once.
  - `cmp strings.json en.json` reports identical files.
  - `(VERSION, MINOR_VERSION) == (1, 2)`.
  - The counts of `async def async_migrate_entry`, `is_persistent=True`, `async_delete_issue`, `async_remove_legacy_devices(` and `async_track_sw_version(` are 1 each.
  - Zero hits for the old base names, `registry\.entities`, `via_device=` and `self\.entity_id = `.
  - The integration never reads `DeviceEntry.config_entries`.
- Mutation checks were run and reverted, nothing committed:
  - Dropping the "no entities" guard fails `test_legacy_devices_removed_after_entities_moved` and all 3 keep-path cases.
  - `include_disabled_entities=False` fails the user-disabled and integration-disabled keep cases.
  - Moving the cleanup before `async_forward_entry_setups` fails `test_legacy_devices_removed_after_entities_moved`, because the re-pointed devices stay.
  - Always writing in `_handle_coordinator_update` fails the zero-write test.

## Device keep-path proof (user priority)

- `tests/test_devices.py::test_legacy_device_with_entity_is_kept[enabled]`, `[user-disabled]` and `[integration-disabled]`: a legacy `http_services` device whose only entity is not re-pointed by any platform (unique_id `{entry_id}_legacy_orphan`) is kept. Its entity keeps its entity_id, its user name "Kept name", its `disabled_by` and its `device_id`.
- `tests/test_devices.py::test_legacy_devices_removed_after_entities_moved` checks the full picture:
  - The `diagnostics` legacy device that still holds an entity is kept.
  - The five legacy devices whose entities were re-pointed are removed.
  - The 0.3.0 service sensor keeps `sensor.traefik_http_service_whoami_docker` and its user name "My whoami", and moves to the Services sub-device.
  - A USER-disabled entrypoint sensor is re-pointed to the main device and stays USER-disabled.
- `tests/test_devices.py::test_devices_of_other_entry_untouched`: another (disabled) config entry owns two empty devices. One has an identifier built from the tested entry's id (`{entry_id}_overview`), the other the other entry's own `{other_id}_http_services`. Both survive the tested entry's setup.
- Migration side, `tests/test_migration.py::test_migration_from_1_1`:
  - The USER-disabled services aggregate stays disabled.
  - The service sensor keeps its entity_id and user name.
  - The other config entry's look-alike router binary_sensor and its INTEGRATION-disabled aggregate are untouched, and that entry stays at 1.1.

## TDD Gate Compliance

- Each task has a RED commit (`21a8a43`, `3a397a3`, `4a344b8`) and then a GREEN commit (`ebcf631`, `090d156`, `e483477`).
- RED evidence came from `--runxfail` runs before each GREEN, and each failure was on the planned assertion:
  - **Task 1:** `FileNotFoundError` for de.json/icons.json; English sub-device name "Traefik routers (...)".
  - **Task 2:** `router_a` registry entry still present; `minor_version` 1 != 2; `(1, 1) != (1, 2)`; no issue; `AttributeError: no attribute 'async_migrate_entry'`.
  - **Task 3:** `('traefik_proxy', 'device-entry_http_routers')` still present; sw_version `'3.7.19' != '3.7.99'`.
- Tests that pass at RED are invariant checks and carry no xfail marker: the downgrade test, the keep-path, other-entry and via_device tests, and the zero-write test.
- REFACTOR: none needed.
- No `gsd_run check tdd-red-evidence` junitxml record was produced. The `--runxfail` output above is the evidence.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug, test-only] Zero-write test compared a State object with itself**
- **Found during:** Task 3 RED (mutation check)
- **Issue:** On an unchanged write, HA updates `State.last_reported` on the existing State object in place. A `before` dict of State objects therefore always equalled the current states, and the test could not detect writes. A mutation that always writes still passed.
- **Fix:** Snapshot the `last_reported` values. With the fix, the always-write mutation fails the test.
- **Files modified:** tests/test_entity_manager.py
- **Commit:** 4a344b8

**2. [Rule 1 - Bug, test-only] Second config entry got migrated along with the entry under test**
- **Found during:** Task 2 GREEN
- **Issue:** `hass.config_entries.async_setup(entry_id)` sets up the integration, and that sets up (and migrates) every enabled entry of the domain. So the "other entry is untouched" check saw two issues.
- **Fix:** The other entry is created with `disabled_by=ConfigEntryDisabler.USER`. It stays unloaded and at 1.1. This still proves the migration loop only touches its own entry's registry entries. The same pattern is used in `test_devices_of_other_entry_untouched`.
- **Files modified:** tests/test_migration.py
- **Commit:** 090d156

Otherwise the plan was executed as written.

## Worker Decisions

- **Device skip rule.** `async_remove_legacy_devices` skips a device unless it has exactly one legacy identifier and no current identifier (main, routers, services, certificates).
  - Reason: if a registry merge ever put a legacy and a current identifier on one device, the main device or a sub-device must never be removed.
  - Alternative: match on any legacy identifier, as in the plan text.
- **Keep `async_remove_device`.** `async_remove_legacy_devices` uses `async_remove_device` as planned, not `async_update_device(remove_config_entry_id=...)`.
  - Reason: on HA 2026.10 devices belong to one config entry, so removal cannot reach another entry. On 2026.3 a shared legacy device would need another entry of this domain to register this entry's identifier. The empty-entity guard also covers entities of every entry.
  - Alternative: `remove_config_entry_id`, which has different pending-move semantics on 2026.10.
- **Disabled second entry.** The cross-entry tests use a user-disabled second entry. Reason: it is the only way to keep a second entry of the same domain unloaded during setup (deviation 2). Alternative: set up both entries, which would migrate the second one too.
- **Extra keep-path cases.** The keep-path test is parametrized over enabled, USER-disabled and INTEGRATION-disabled entities, and it also checks the user name and entity_id. Reason: the user-priority brief asks for the enabled and disabled-only cases plus preserved customisations. Alternative: one case per plan behaviour line.
- **Extra entities in the full cleanup test.** The full cleanup test adds two entities: a USER-disabled entrypoint sensor on the legacy `http_entrypoints` device, and a user name on the service sensor. Reason: this proves that re-pointing keeps `disabled_by` and the name. Alternative: only the four entities the plan lists.
- **Extra cross-entry check in the migration test.** The migration test also covers a second entry's look-alike router binary_sensor and INTEGRATION-disabled aggregate. Reason: this is the ENT-09 prohibition (no cross-entry changes). Alternative: no cross-entry case.
- **Issue lifecycle steps.** The issue test also asserts the issue after a plain unload, before `async_remove`. Reason: M34 says unload must keep it. Alternative: test only reload and remove.
- **Translation test scope.**
  - `test_every_code_key_has_texts` does not require an en/de node for `entrypoint`. Reason: its name comes from the item key and it has no states, so there is nothing to translate. Alternative: add an empty `entrypoint` node, which the no-empty-strings rule forbids.
  - `test_every_code_key_has_icons` also fails on an icon key the code no longer uses. Reason: this catches drift in both directions. Alternative: check one direction only.
- **JSON formatting.** The translation JSON is written with `json.dumps(indent=2)`. en.json keeps the `\uXXXX` escapes (`ensure_ascii`, as before), and de.json uses real UTF-8 (`ensure_ascii=False`). Reason: the existing en.json layout stays unchanged, and the plan asks for real umlauts in de.json. Alternative: real UTF-8 in en.json too, which would re-encode existing strings.
- **Migration debug log.** The migration writes one debug log line with the entry_id and the removed count, and none with a URL or token. Reason: it helps diagnosis without leaking secrets (T-05-14). Alternative: no log.

## User-visible changes (Phase 8 CHANGELOG)

- **German UI:** device names ("Traefik-Router (host)", "Traefik-Dienste (host)", "Traefik-Zertifikate (host)"), entity names (for example "Router-Probleme", "Jetzt aktualisieren", "{host} läuft ab") and router/service states ("Aktiviert", "Warnung", "Fehler", "Deaktiviert", "Fehlt") are translated. Config and options dialogs stay English until Phase 7.
- **Icons:** router and service sensors change icon with their state. Problem sensors and certificate-expiring sensors show an alert or check icon. All entities get icons through `icons.json`.
- **Upgrade from 0.3.0:**
  - The old router binary sensors and the Reload button are removed automatically.
  - The router, middleware and service problem aggregates are switched on, unless the user disabled them.
  - A persistent repair notice ("Traefik entities were replaced") lists how many entities were removed and asks the user to update automations.
- **Removed devices:** the old per-category devices ("... Traefik Proxy - HTTP Routers", "HTTP Services", "Overview", and so on) are removed once no entity uses them. Device names or areas set on them by the user are not carried over. Entity customisations survive.
- **Live version:** the Traefik device's firmware/software version follows Traefik upgrades without a reload.

## Known Stubs

None.

## Threat Flags

None. The plan's register covers every change:
- T-05-13: the migration tests check the USER-disabled aggregate, the kept entity_id and the cert entry, and that the other entry is untouched.
- T-05-14: the only placeholders are the entry title and a count.
- T-05-15: the keep-path and order mutations above.
- T-05-16: the downgrade test.

## Issues Encountered

- None blocking. As the plan says, one entry reload happens 30 s after the first start of an upgraded install, because HA reloads entries whose entities were re-enabled. The tests do not advance time after setup.

## Next Phase Readiness

- Phase 5 plans are all executed. ENT requirements stay "Pending" in REQUIREMENTS.md until phase completion (convention).
- Phase 7 bumps `MINOR_VERSION` to 3 and adds German config/options strings. The README/CLAUDE.md reload mentions stay in `deferred-items.md` for Phase 8.

## Self-Check: PASSED

- FOUND: translations/de.json, icons.json, tests/test_translations.py, tests/test_migration.py, tests/test_devices.py
- FOUND commits: 21a8a43, ebcf631, 3a397a3, 090d156, 4a344b8, e483477 (ancestors of HEAD)
