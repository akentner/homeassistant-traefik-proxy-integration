---
phase: 05-entity-model-lifecycle
verified: 2026-11-14T23:24:07Z
status: human_needed
score: 90/90 must-haves verified
covered_files:
  - ".planning/phases/05-entity-model-lifecycle/05-01-PLAN.md"
  - ".planning/phases/05-entity-model-lifecycle/05-01-SUMMARY.md"
  - ".planning/phases/05-entity-model-lifecycle/05-02-PLAN.md"
  - ".planning/phases/05-entity-model-lifecycle/05-02-SUMMARY.md"
  - ".planning/phases/05-entity-model-lifecycle/05-03-PLAN.md"
  - ".planning/phases/05-entity-model-lifecycle/05-03-SUMMARY.md"
  - ".planning/phases/05-entity-model-lifecycle/05-04-PLAN.md"
  - ".planning/phases/05-entity-model-lifecycle/05-04-SUMMARY.md"
  - ".planning/phases/05-entity-model-lifecycle/05-05-PLAN.md"
  - ".planning/phases/05-entity-model-lifecycle/05-05-SUMMARY.md"
  - ".planning/phases/05-entity-model-lifecycle/05-06-PLAN.md"
  - ".planning/phases/05-entity-model-lifecycle/05-06-SUMMARY.md"
  - ".planning/phases/05-entity-model-lifecycle/05-07-PLAN.md"
  - ".planning/phases/05-entity-model-lifecycle/05-07-SUMMARY.md"
  - ".planning/phases/05-entity-model-lifecycle/05-08-PLAN.md"
  - ".planning/phases/05-entity-model-lifecycle/05-08-SUMMARY.md"
  - "custom_components/traefik_proxy/__init__.py"
  - "custom_components/traefik_proxy/api.py"
  - "custom_components/traefik_proxy/binary_sensor.py"
  - "custom_components/traefik_proxy/button.py"
  - "custom_components/traefik_proxy/config_flow.py"
  - "custom_components/traefik_proxy/const.py"
  - "custom_components/traefik_proxy/data.py"
  - "custom_components/traefik_proxy/entity.py"
  - "custom_components/traefik_proxy/entity_manager.py"
  - "custom_components/traefik_proxy/icons.json"
  - "custom_components/traefik_proxy/sensor.py"
  - "custom_components/traefik_proxy/strings.json"
  - "custom_components/traefik_proxy/translations/de.json"
  - "custom_components/traefik_proxy/translations/en.json"
  - "tests/conftest.py"
  - "tests/test_api.py"
  - "tests/test_binary_sensor.py"
  - "tests/test_binary_sensor_tls_expiring.py"
  - "tests/test_cert_entity_state.py"
  - "tests/test_coordinator.py"
  - "tests/test_devices.py"
  - "tests/test_entity_manager.py"
  - "tests/test_init.py"
  - "tests/test_migration.py"
  - "tests/test_platforms_real_fixtures.py"
  - "tests/test_sensor.py"
  - "tests/test_sensor_tls.py"
  - "tests/test_translations.py"
covered_digest: "v4:sha256:8250352d818ee52c8daf327f8ec43c5a538a15653bc0f25c37f28d32742d8ae7"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 76/79
  gaps_closed:
    - "G6 / CR-01: existing installs are migrated cleanly; the 1.1 -> 1.2 migration no longer re-enables a router binary sensor the user disabled (USER -> USER, DEVICE -> USER, INTEGRATION -> INTEGRATION replacement in the sensor domain; tests test_user_disabled_router_stays_disabled, test_disabled_router_replacement_keeps_disabled_state[user,device,integration,enabled], test_migration_with_disabled_routers_is_idempotent)"
    - "CR-02 (found by the re-review after 05-08): entities disabled through a 0.3.0 device are no longer re-enabled by the next update of their new device (DEVICE -> USER on this entry's legacy devices; test_device_disabled_entities_stay_disabled_after_device_updates, test_device_disabled_mapping_is_scoped_and_idempotent)"
    - "IN-05: hidden router binary sensors come back hidden (test_hidden_router_replacement_stays_hidden[enabled-user,disabled-user,enabled-integration])"
    - "Previously deferred WR-01: the update listener is now bound to entry unload (test_update_listener_registered_once_across_reloads); the Phase 7 deferral is no longer needed"
    - "WR-02 (previous warning): per-item-off sub-device removal goes through the same reference guard as the legacy cleanup (test_per_item_off_keeps_referenced_sub_device[enabled,user-disabled])"
    - "Backstop truth 05-02 Edge ENT-01/concurrency: previously insufficient_spec, now VERIFIED by directly observed behaviour (verifier scratch probes, both HA versions)"
    - "Backstop truth 05-04 Edge ENT-10/concurrency: previously insufficient_spec, now VERIFIED by directly observed behaviour (verifier scratch probes, both HA versions)"
  gaps_remaining: []
  regressions: []
advisory:
  - finding: "IN-06: pre-created router replacements (disabled or hidden) keep the old object id under sensor. (sensor.traefik_http_router_<name>), while visible enabled routers get the platform id sensor.traefik_routers_<host>_<name>; one router list mixes two id schemes"
    category: other
    reason: "Raised by the re-review after the gap-closure round. The repair text 'new entity IDs' stays literally true (the domain changes from binary_sensor to sensor), no automation can reference a sensor id that did not exist before, and no goal clause requires a uniform id scheme. Resolve by mentioning it in the repair text or by seeding the platform-style id"
    evidence_status: "none provided as a goal violation (review finding, info)"
  - finding: "IN-07: the DEVICE -> USER step also hardens a stale DEVICE disabler on an enabled legacy device"
    category: other
    reason: "Raised by the re-review after the gap-closure round (reviewer scratch probe on HA 2026.3). Nothing is enabled, renamed or re-IDed; the state only arises from hand-edited storage or a crash between the two registry saves. Resolve with 'if device.disabled' in the legacy_device_ids comprehension (__init__.py:130)"
    evidence_status: "reproduced by the reviewer, but no goal clause or prohibition is violated (stricter than HA, never less strict)"
human_verification:
  - test: "Judgment-tier prohibition ENT-01 (05-02, verification: null, flagged): MUST NOT delete a registry entry on any path other than grace-period expiry, the per-item opt-out, the 0.3.0 migration or entry removal"
    expected: "Confirm the non-authoritative verifier verdict: HOLDS. The only entity-registry removals in custom_components/traefik_proxy are entity_manager.py:268 (async_purge, per-item opt-out), entity_manager.py:335 (_async_remove_registry_entry, grace expiry), __init__.py:116 and :119 (0.3.0 router binary sensors and reload button in async_migrate_entry). The only device removal is entity.py:95 inside _async_remove_device_if_unreferenced, which returns early while any registry entry references the device, so a device removal cannot cascade into an entity removal. entity_manager.py:111 removes the missing-since Store (not a registry entry) on entry removal."
    why_human: "Judgment-tier prohibition: by design (ADR-550 D4, probe-core dispositionForProhibition) never green from the verifier, whatever the evidence. Blocks the goal: no (verdict holds). To close: confirm, or add an override."
  - test: "Judgment-tier prohibition ENT-07 (05-06, verification: null, flagged): MUST NOT send any non-GET request to the Traefik API"
    expected: "Confirm the non-authoritative verifier verdict: HOLDS. api.py:185 is the only HTTP call (self._session.get). A grep for .post/.put/.patch/.delete/.request( in custom_components/traefik_proxy finds nothing. tests/test_init.py::test_only_get_requests_reach_traefik (setup, both coordinator refreshes, a real button press) asserts the recorded methods are exactly {GET} and passes on HA 2026.3 and the dev venv."
    why_human: "Judgment-tier prohibition, never green by design. Blocks the goal: no. Wired enforcement exists, so you could also re-tier it to verification: test in 05-06-PLAN.md."
  - test: "Judgment-tier prohibition ENT-09 (05-07, verification: null, flagged): MUST NOT re-enable an entity the user disabled, rename or re-ID a surviving entity, or touch another config entry's registry entries or devices while migrating or cleaning up legacy devices"
    expected: "Confirm the non-authoritative verifier verdict: now HOLDS on all three clauses (it was VIOLATED on the re-enable clause before 05-08). Re-enable: router replacements keep the disabled and hidden state (USER/DEVICE -> USER, INTEGRATION kept); survivors on disabled legacy devices go DEVICE -> USER so async_device_modified cannot clear them; the only enabling write is aggregates with INTEGRATION -> None (the old disabled-by-default, D-18). Rename/re-ID and cross-entry: both loops iterate er.async_entries_for_config_entry(registry, entry.entry_id), async_legacy_devices lists only this entry's devices, and the DEVICE -> USER update passes only disabled_by. Tests: test_migration_from_1_1, test_device_disabled_mapping_is_scoped_and_idempotent (foreign entities on own and foreign legacy devices keep DEVICE), test_devices_of_other_entry_untouched, plus the 05-08 test-tier prohibitions, which are green."
    why_human: "Judgment-tier prohibition, never green by design. Its content is now also covered by the 05-08 test-tier ENT-09 prohibitions (green). Blocks the goal: no."
  - test: "Optional visual check in a real HA (2026.3 and 2026.10+) with an upgraded 0.3.0 entry, UI language German and English"
    expected: "Device page shows 'Traefik (<host>)' with nested Routers/Services/Certificates sub-devices; router/service ENUM state labels and state icons render translated; the repair notice reads correctly; 'Refresh now' is under Diagnostic"
    why_human: "Only frontend rendering is left. The backend side is proven by tests: device names in de and en (test_german_device_names), via_device_id links, translation key and placeholder parity, icons.json key coverage, entity_category. Blocks the goal: no (nice to confirm)."
---

# Phase 5: Entity model + lifecycle Verification Report

**Phase Goal:** Router, service and problem entities reflect live Traefik state for the lifetime of the config entry: new items appear without a reload, vanished items go `missing` and are removed only after a 24 h grace period, states update on every change (and only on change), and the entity/device model is readable, translated (en/de) and categorised — with the never-working reload feature replaced by a "Refresh now" button and existing installs migrated cleanly.
**Verified:** 2026-11-14T23:24:07Z
**Status:** human_needed (no gaps; 3 judgment-tier prohibition sign-offs by design, plus 1 optional visual check)
**Re-verification:** Yes, after gap closure (plan 05-08 and the review-fix run 4e1aee1..5ea22e5)

## Goal Achievement

The one failed goal clause from the previous report, "existing installs migrated cleanly" (G6 / CR-01), is closed. So is the follow-up defect CR-02 that the re-review found in the same clause. I checked the code directly (`__init__.py:47-165`, `entity.py:82-185`) and ran the named tests on both HA versions. Every truth in the goal, the roadmap and the plans is now VERIFIED, including the two `backstop` truths, which I confirmed with directly observed behaviour in throwaway probes.

The status is `human_needed` and not `passed` for one reason only. Three prohibitions in 05-02, 05-06 and 05-07 are declared judgment-tier (`verification: null`, `flagged: true`). The verifier contract never turns those green, whatever the evidence (ADR-550 D4; `dispositionForProhibition` in probe-core). My verdict is "holds" for all three, and none of them blocks the goal. The fourth human item, a visual check of frontend rendering, is optional.

### Observable Truths (goal level: ROADMAP success criteria + goal clause)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC1 | Router `enabled -> error` and service server DOWN reach the entity on the next cycle; new router without reload; removed router goes `missing`, keeps its registry entry until 24 h, then removed; reappearing router re-binds | ✓ VERIFIED (regression check) | `entity_manager.py:281-335` unchanged since the previous run (`git diff 3ede5f7..HEAD` touches only `__init__.py`, `entity.py` and three test modules). The full suite passes, including the SC1 tests listed in the previous report |
| SC2 | Router/service ENUM sensors with the five translated options; `servers_up`/`servers_total`; no URLs/IPs; canonical keys | ✓ VERIFIED (regression) | `sensor.py` unchanged; `test_item_state_keys_equal_options` and the capture tests pass |
| SC3 | Problem aggregates enabled by default, one class + descriptions; DIAGNOSTIC categories; entrypoints disabled by default; zero writes on no-change refresh; no full-registry scan | ✓ VERIFIED (regression) | A grep finds no `registry.entities` in the package; `test_unchanged_notifications_write_no_state` passes |
| SC4 | Main device + sub-devices via `via_device_id` (no `DeviceInfo.via_device`); `sw_version` current; translation_key names en+de; `icons.json`; `PARALLEL_UPDATES` everywhere | ✓ VERIFIED (regression) | A grep finds no `via_device=`; `PARALLEL_UPDATES` is 1/0/0 in button/binary_sensor/sensor; `strings.json` is byte-identical to `en.json`; `test_german_device_names` passes |
| SC5 | Reload feature gone; own-entry "Refresh now"; 0.3.0 upgrade removes old router binary sensors + reload button with a non-fixable persistent repair notice; per-item off -> no router/service entities; cert entities on `TraefikCertEntity`, not re-added | ✓ VERIFIED (regression) | `services.yaml` absent; no `reload_routers`/`CONFIG_SCHEMA`; `ir.async_create_issue(... is_fixable=False, is_persistent=True)` at `__init__.py:148-157`, deleted only in `async_remove_entry` (`:311`, M34) |
| G6 | Existing installs are migrated cleanly: user-disabled entities stay disabled (goal clause; D-18) | ✓ VERIFIED (was ✗ FAILED) | `__init__.py:105-145`: a disabled or hidden router binary sensor is recorded with its mapped `disabled_by` (`_ROUTER_REPLACEMENT_DISABLED_BY`, `:56-60`), `hidden_by` and old object id, removed, then pre-created as a `sensor` entry with the same unique_id. `entity_platform` re-points it to the Routers sub-device and skips adding it while it is disabled. `:127-133` maps `DEVICE -> USER` for this entry's entities on its legacy devices (CR-02). Tests (all pass on HA 2026.3 and dev): `test_user_disabled_router_stays_disabled` asserts `disabled_by is USER`, `device_id == routers.id` and `hass.states.get(...) is None`; the parametrized `test_disabled_router_replacement_keeps_disabled_state` covers user/device/integration/enabled; `test_device_disabled_entities_stay_disabled_after_device_updates` drives a real `sw_version` update (`3.7.99`) and device renames, after which the entities are still `USER`-disabled without state |

### Plan must-have truths

| Plan | Truths | Verified | Not verified | Notes |
|------|--------|----------|--------------|-------|
| 05-01 tracer | 16 | 16 | 0 | Regression only (files unchanged, suite green) |
| 05-02 grace period | 9 | 9 | 0 | The `backstop` concurrency truth is now ✓ VERIFIED by directly observed behaviour (probes A3-A5 below) |
| 05-03 services/entrypoints/aggregates | 15 | 15 | 0 | Regression only |
| 05-04 per-item option | 5 | 5 | 0 | The `backstop` truth "read once per setup, applies on next reload" is now ✓ VERIFIED by directly observed behaviour (probes A1-A2) |
| 05-05 cert entities | 6 | 6 | 0 | Regression only |
| 05-06 reload removal + refresh button | 5 | 5 | 0 | Regression only |
| 05-07 translations, migration, devices | 17 | 17 | 0 | The `async_remove_legacy_devices` behaviour is unchanged; it now uses the shared `async_legacy_devices` predicate and the guard helper |
| 05-08 gap closure | 11 | 11 | 0 | See the next table |
| **Total (plan)** | **84** | **84** | **0** | |

**05-08 truths in detail**

| # | Truth (shortened) | Status | Evidence |
|---|-------------------|--------|----------|
| 1 | USER-disabled router binary sensor -> USER-disabled `sensor` with the same unique_id, no state, on the Routers sub-device | ✓ | `test_user_disabled_router_stays_disabled` |
| 2 | DEVICE -> USER, INTEGRATION -> INTEGRATION, enabled -> no pre-created entry, comes back enabled with state | ✓ | `test_disabled_router_replacement_keeps_disabled_state[user,device,integration,enabled]`; the device case also asserts that the legacy `http_routers` device is removed |
| 3 | The replacement takes the old object id, with no user name; enabled routers keep the platform id | ✓ | Same test: `replacement_id == "sensor.traefik_http_router_file_ok_file"`, `name is None`, `!=` for enabled. `async_get_or_create` passes no name/area/icon (`__init__.py:137-145`) |
| 4 | `removed_count` counts every removed router binary sensor, disabled ones included | ✓ | `"2"` in the user and hidden tests, `"4"` in the idempotency test |
| 5 | A second migration run with replacements present changes nothing; exactly one issue | ✓ | `test_migration_with_disabled_routers_is_idempotent` compares whole `RegistryEntry` maps (`modified_at` included) |
| 6 | Listener via `entry.async_on_unload`; 1 / 1 / 0 listeners; one run per options change; docstring accurate | ✓ | `__init__.py:285`, `:295-302`; `test_update_listener_registered_once_across_reloads` |
| 7 | Per-item off: Routers/Services removed only while unreferenced; a referenced one keeps its id and link | ✓ | `entity.py:118-123`; `test_per_item_off_keeps_referenced_sub_device[enabled,user-disabled]` |
| 8 | One guard helper; exactly one `async_remove_device` call in `entity.py` | ✓ | grep: the only call is `entity.py:95`; both paths call `_async_remove_device_if_unreferenced` |
| 9 | Gates green on both venvs; no API newer than HA 2026.3; no `via_device=` | ✓ | 577 passed on dev (my single full run) and HA 2026.3 (orchestrator; my targeted run there: 28/28); ruff, format and mypy strict are clean; `hidden_by=` in `async_get_or_create` exists in 2026.3 (tests pass there) |
| 10 | Disposition: CR-01, WR-01 and WR-02 fixed with their 05-08 ranges | ✓ | `05-REVIEW-DISPOSITION.md`. Later, the review-fix docs commit `2963139` set IN-02 and IN-04 to `deferred` (Phase 7). That is an intentional follow-up, not a 05-08 deviation |
| 11 | No new planning references in shipped code | ✓ | Count is 4 in `__init__.py` (≤ 5 baseline) and 0 in `entity.py` |

**Score:** 90/90 truths verified (6 goal level + 84 plan level), 0 present but behavior-unverified, 0 insufficient_spec, 0 overrides.

### Prohibitions

| Plan | Requirement | Tier | Disposition | Evidence |
|------|-------------|------|-------------|----------|
| 05-08 | ENT-09 no re-enable during migration | test | ✓ green | Wired, passing: `test_user_disabled_router_stays_disabled`, `test_disabled_router_replacement_keeps_disabled_state`, `test_device_disabled_entities_stay_disabled_after_device_updates` |
| 05-08 | ENT-09 no rename/re-ID, no cross-entry writes | test | ✓ green | `test_migration_from_1_1`, `test_device_disabled_mapping_is_scoped_and_idempotent`, `test_devices_of_other_entry_untouched` |
| 05-08 | ENT-10 never delete a referenced device | test | ✓ green | `test_per_item_off_keeps_referenced_sub_device`, the legacy keep/remove tests in `test_devices.py` |
| 05-02 | ENT-01 registry deletions only on the four allowed paths | judgment (null) | flagged; verdict HOLDS | Human item 1 |
| 05-06 | ENT-07 GET-only | judgment (null) | flagged; verdict HOLDS | Human item 2 |
| 05-07 | ENT-09 no re-enable / re-ID / cross-entry | judgment (null) | flagged; verdict HOLDS (was VIOLATED) | Human item 3 |

### Advisory (New Scope, Unevidenced)

These findings came from the re-review after the gap-closure round. They are reported here and do not block. Each one was checked against the re-verification evidence gate: neither is a carried-forward gap, and neither violates a goal clause or prohibition.

| # | Finding | Category | Why Advisory |
|---|---------|----------|--------------|
| 1 | IN-06: disabled or hidden router replacements keep the old object id (`sensor.traefik_http_router_<name>`), while visible routers get `sensor.traefik_routers_<host>_<name>` | other | The id scheme is cosmetic. The repair text "new entity IDs" stays true, because the domain changes from `binary_sensor` to `sensor`. No goal clause requires uniform ids |
| 2 | IN-07: `DEVICE -> USER` also applies to a stale `DEVICE` disabler on an *enabled* legacy device | other | Only stricter than HA, never re-enabling. Rare (hand-edited storage or a crash between the registry saves). One-line fix: `if device.disabled` at `__init__.py:130` |

### Required Artifacts

`gsd-tools verify.artifacts` on all 8 plans returned `all_passed: true` (31/31 artifacts). For 05-08 (6/6), I checked wiring manually:

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `custom_components/traefik_proxy/__init__.py` | `_ROUTER_REPLACEMENT_DISABLED_BY`, replacement pre-creation, `async_on_unload` listener | ✓ VERIFIED | Defined at `:56`, used at `:108`; `async_migrate_entry` is registered by HA as the entry migrator (exercised by every 1.1 test entry) |
| `custom_components/traefik_proxy/entity.py` | `_async_remove_device_if_unreferenced` | ✓ VERIFIED | Called from `async_setup_devices` (`:123`) and `async_remove_legacy_devices` (`:185`), both called from `__init__.py:272,278` |
| `tests/test_migration.py`, `tests/test_init.py`, `tests/test_devices.py` | Gap tests | ✓ VERIFIED | Assertions are substantive (read in full); all pass; `grep -rn xfail tests/` is empty |
| `05-REVIEW-DISPOSITION.md` | CR-01/WR-01/WR-02 fixed | ✓ VERIFIED | Rows show `Plan 05-08 (50bcc4c..c265fa5)`, `(98602c2..c265fa5)`, `(6ba969e..db2762c)` |

### Key Link Verification

`gsd-tools verify.key-links` on all 8 plans returned `all_verified: true` (21/21). The 05-08 links are `suggested_object_id=` in `__init__.py`, `entry.async_on_unload(entry.add_update_listener(` and `def _async_remove_device_if_unreferenced`. Behind each pattern is a real call path, which the tests above exercise.

### Data-Flow Trace (Level 4)

Unchanged from the previous report. Router/service/entrypoint sensors read `coordinator.data.*[key]`, aggregates read `snapshot.*_problems`, cert entities read `cert_coordinator.data[host]`, and `sw_version` is updated by the coordinator listener. All are ✓ FLOWING. The gap-closure code writes registry state only; it renders nothing.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full suite, dev venv | `uv run pytest -q -o addopts="" tests` | 577 passed | ✓ PASS |
| Gap tests, both HA versions | `pytest tests/test_migration.py tests/test_devices.py tests/test_init.py::test_update_listener_registered_once_across_reloads tests/test_init.py::test_only_get_requests_reach_traefik` (dev venv and `ha2603-venv`) | 28 passed / 28 passed | ✓ PASS |
| Lint, format, types | `uv run ruff check custom_components tests`, `ruff format --check`, `mypy --strict custom_components/traefik_proxy` | clean / 38 formatted / no issues in 14 files | ✓ PASS |
| Commits cited in the summaries | `gsd-tools verify.commits 50bcc4c 09241f2 98602c2 c265fa5 6ba969e db2762c 4e1aee1 80e1902 c71cf6c 5ea22e5` | 10/10 valid | ✓ PASS |
| A1 backstop 05-04: options on -> off without reload | verifier probe (scratch copy of the repo, not in the repo) | Without a reload, after a refresh: same `runtime_data`, router/service registry entries and states, and the Routers sub-device all unchanged; after a reload all are gone | ✓ PASS (both HA versions) |
| A2 backstop 05-04: options off -> on without reload | verifier probe | No router/service entity and no Routers device until the reload; present with state after it | ✓ PASS (both) |
| A3 backstop 05-02: manager state changes are sync callbacks | verifier probe | `async_add_kind`, `async_purge`, `_async_kind_updated`, `_async_check_deadlines`, `_async_remove_registry_entry`, `_async_schedule_save` are not coroutines and carry `_hass_callback` | ✓ PASS (both) |
| A4 backstop 05-02: concurrent notifications cannot interleave | verifier probe: re-entrancy counter on `_async_kind_updated` through setup (concurrent platform setups) plus 40 concurrent tasks pushing random router subsets | Over 40 calls, maximum nesting depth 1; each router unique_id registered exactly once; `missing_since` and `missing` states match the final snapshot exactly | ✓ PASS (both) |
| A5 backstop 05-02: unload awaits pending Store writes | verifier probe: `Store.async_save` slowed by 200 ms, refresh schedules a save, then immediate `async_unload` | The save had not finished before unload and had finished when `async_unload` returned; `hass_storage` holds the missing router | ✓ PASS (both) |

The probe file `test_zz_verifier_probe.py` was run from a copy of the repo in the verifier scratchpad. The repository was not modified (`git status` shows only the pre-existing `.planning/config.json` / `.planning/state.json` changes).

### Probe Execution

Step 7c: no `scripts/*/tests/probe-*.sh` is declared or present for this phase. Not applicable.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ENT-01 | 05-01..05-03, 05-05 | Entity manager: add, missing, 24 h removal, re-bind; config-entry registry reads only; cert hosts never re-added | ✓ SATISFIED | SC1, SC3, SC5; the backstop truth is now verified |
| ENT-02 | 05-01..05-03, 05-05, 05-07 | Key-only entities, write on change, no redundant `available` | ✓ SATISFIED | Regression |
| ENT-03 | 05-01, 05-05, 05-07, 05-08 | Entity bases, one DeviceInfo factory, main device + linked sub-devices, `sw_version` current | ✓ SATISFIED | SC4; 05-08 adds the device-removal guard |
| ENT-04 | 05-01..05-03 | Router/service ENUM sensors; `servers_up`/`servers_total`; canonical keys | ✓ SATISFIED | SC2 |
| ENT-05 | 05-03 | Problem aggregates on by default, one class + descriptions | ✓ SATISFIED | Regression |
| ENT-06 | 05-03 | DIAGNOSTIC category; entrypoints + healthy ratio disabled by default | ✓ SATISFIED | Regression |
| ENT-07 | 05-06 | Reload feature removed; own-entry refresh button, no admin bypass | ✓ SATISFIED | SC5; GET-only test |
| ENT-08 | 05-03, 05-05..05-07 | translation_key names en+de, `icons.json`, `PARALLEL_UPDATES` | ✓ SATISFIED | German config/options strings are Phase 7 (FLOW-07, IN-02 deferred), as planned |
| ENT-09 | 05-07, 05-08 | 0.3.0 migration removes old router binary sensors + reload button; persistent non-fixable repair notice deleted on entry removal (M34) | ✓ SATISFIED (was ✗ PARTIAL) | G6 closed; CR-02 and IN-05 closed. ENT-09 says "router/service `binary_sensor`", but 0.3.0 service entities were already sensors (CONTEXT: kept, ids preserved), so routers are the only binary sensors to remove |
| ENT-10 | 05-04, 05-08 | Per-item option honoured; off -> no router/service entities, existing removed | ✓ SATISFIED | `test_per_item_off_*`; the referenced sub-device is kept (05-08). No UI until Phase 7 (W36 / IN-04 deferred, by design) |

Orphan check: REQUIREMENTS.md maps exactly ENT-01..ENT-10 to Phase 5, and every ID appears in at least one plan's `requirements`. No orphans. They remain "Pending" until phase.complete, as expected.

### Decision Coverage

`check.decision-coverage-verify`: 21/21 trackable CONTEXT.md decisions honored. D-18 ("user-disabled entries stay disabled") now holds in code and tests.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `custom_components/traefik_proxy/entity.py` | 288-290, 306-310 | Redundant `.lower()` on cert hosts, not mirrored in `KindSpec.key_of` (IN-01) | ℹ️ Info | No current path produces mixed-case keys |
| `custom_components/traefik_proxy/translations/en.json` | 66 | Unused `exceptions.cert_unavailable` (IN-03) | ℹ️ Info | Cosmetic |
| `custom_components/traefik_proxy/__init__.py` | 130 | DEVICE -> USER also on enabled legacy devices (IN-07) | 📋 Advisory | See Advisory |
| `custom_components/traefik_proxy/__init__.py` | 114, 144 | Old object id for disabled or hidden replacements (IN-06) | 📋 Advisory | See Advisory |

Debt-marker gate: no `TBD`/`FIXME`/`XXX` (and no `TODO`/`HACK`/placeholder) in `custom_components/traefik_proxy` or `tests/`. No disabled tests (`xfail`/`skip`) on any requirement.

The previous blocker (CR-01) and warnings (WR-01, WR-02) are resolved.

### Human Verification Required

None of these items blocks the phase goal. Items 1-3 need a sign-off only because judgment-tier prohibitions can never turn green from the verifier. Item 4 is optional.

1. **Prohibition ENT-01 (05-02): registry deletions only on the four allowed paths.** Verdict: holds. The removal call sites are listed in the frontmatter. The device guard makes a cascading entity removal impossible.
2. **Prohibition ENT-07 (05-06): GET-only.** Verdict: holds. There is one `session.get` call site, no other HTTP verb in the package, and `test_only_get_requests_reach_traefik` passes. Because a wired test exists, you could re-tier this prohibition to `verification: test`.
3. **Prohibition ENT-09 (05-07): no re-enable / re-ID / cross-entry writes.** Verdict: **now holds on all three clauses** (it was violated before). Its content is also covered by the green test-tier ENT-09 prohibitions of 05-08.
4. **Optional: visual check in a real HA (en/de).** Check device nesting, translated ENUM state labels, state icons, the repair text and "Refresh now" under Diagnostic. Only the frontend rendering is unproven. Device names (de/en), links, translation and icon key coverage, and the entity categories are all proven by tests.

### Gaps Summary

No gaps remain.
- **G6 / CR-01 closed.** Disabled or hidden 0.3.0 router binary sensors are re-created as `sensor` entries with the same unique_id and the mapped disabled and hidden state. The platform attaches them to the Routers sub-device and never adds a disabled one. All four disabler cases, the hidden cases and idempotency are tested on HA 2026.3 and 2026.10.
- **CR-02 closed.** Entities that were disabled through a 0.3.0 device are converted to `USER`, so device updates (including the integration's own `sw_version` tracking) cannot re-enable them.
- **WR-01 and WR-02 closed.** The listener is bound to entry unload, and both device-removal paths share one reference guard.
- **Both backstop truths verified** by directly observed probe behaviour.

What remains open is info level (IN-01, IN-03), advisory (IN-06, IN-07) or deferred to Phase 7 (IN-02 German config/options strings, IN-04 per-item UI). None of it touches the phase goal.

---

_Verified: 2026-11-14T23:24:07Z_
_Verifier: Claude (gsd-verifier)_
