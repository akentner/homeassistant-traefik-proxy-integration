---
phase: 05-entity-model-lifecycle
verified: 2026-11-14T22:45:00Z
status: gaps_found
score: 76/79 must-haves verified
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
covered_digest: "v4:sha256:dcfe9af74af9f6c7e7d1fed46d4b1331ba6417b5ecc766a36481495dde1eb4bb"
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "Existing installs are migrated cleanly: the 1.1 -> 1.2 migration MUST NOT re-enable an entity the user disabled (phase goal 'existing installs migrated cleanly', CONTEXT D-18 'user-disabled entries stay disabled', 05-07 prohibition ENT-09)"
    status: failed
    reason: "async_migrate_entry removes every binary_sensor with unique_id prefix '{entry_id}_http_router_' without looking at disabled_by. The sensor platform then registers a fresh sensor-domain registry entry with the same unique_id, enabled by default. In 0.3.0 router binary sensors were enabled by default (v0.3.0 binary_sensor.py:194-213, no entity_registry_enabled_default=False), so any disabled one was disabled by the user. Reproduced by the verifier: a USER-disabled 'binary_sensor ..._http_router_file-ok@file' becomes 'sensor.traefik_routers_traefik_example_com_file_ok_file' with disabled_by=None and live state 'enabled' after setup (review finding CR-01, disposition open)."
    artifacts:
      - path: "custom_components/traefik_proxy/__init__.py"
        issue: "lines 74-81: router binary sensors are removed regardless of RegistryEntryDisabler.USER; no disabled sensor-domain replacement is pre-created"
      - path: "tests/test_migration.py"
        issue: "no case for a USER-disabled 0.3.0 router binary sensor; _legacy_registry only creates enabled router binary sensors"
    missing:
      - "Collect the unique_ids of router binary sensors with disabled_by is RegistryEntryDisabler.USER before removing them, then pre-create the sensor-domain entry for each with registry.async_get_or_create('sensor', DOMAIN, unique_id, config_entry=entry, disabled_by=er.RegistryEntryDisabler.USER) (fix sketched in 05-REVIEW.md CR-01)"
      - "Test in tests/test_migration.py: a USER-disabled binary_sensor http_router_x becomes a sensor registry entry with disabled_by=USER and no state after setup; the migration stays idempotent"
deferred:
  - truth: "The update listener is unsubscribed on unload, so the forced post-migration reload does not accumulate duplicate/stale listeners (review WR-01)"
    addressed_in: "Phase 7"
    evidence: "Phase 7 SC2: '`entry.add_update_listener` is no longer used anywhere; the options flow is an `OptionsFlowWithReload` ...'; Phase 7 carry-over: 'WR-03 (update-listener leak) is already covered by SC2'"
human_verification:
  - test: "Judgment-tier prohibition ENT-01 (05-02): MUST NOT delete a registry entry on any path other than grace-period expiry, the per-item opt-out, the 0.3.0 migration or entry removal"
    expected: "Confirm the LLM verdict: holds. Only registry.async_remove call sites: entity_manager._async_remove_registry_entry (grace expiry, incl. stored deadline already passed at setup), entity_manager.async_purge (opt-out), __init__.async_migrate_entry (0.3.0). Device removals in entity.py only cascade to this entry's router/service sensors that async_purge already removed (per_item off) or to devices with no entity left (legacy)."
    why_human: "Judgment-tier prohibition (verification: null, flagged); the verifier verdict is non-authoritative"
  - test: "Judgment-tier prohibition ENT-07 (05-06): MUST NOT send any non-GET request to the Traefik API"
    expected: "Confirm the LLM verdict: holds. api.py _request uses only self._session.get; no .post/.put/.patch/.delete/.request( in custom_components/traefik_proxy; tests/test_init.py::test_only_get_requests_reach_traefik passes."
    why_human: "Judgment-tier prohibition (verification: null, flagged); the verifier verdict is non-authoritative"
  - test: "Judgment-tier prohibition ENT-09 (05-07): MUST NOT re-enable a user-disabled entity, rename/re-ID a surviving entity, or touch another entry's registry entries/devices"
    expected: "LLM verdict: VIOLATED for the 're-enable' clause (CR-01, reproduced; recorded as the gap above). The rename/re-ID and cross-entry clauses hold (test_migration_from_1_1, test_devices_of_other_entry_untouched). Decide: fix CR-01 (recommended) or accept with an override."
    why_human: "Judgment-tier prohibition; whether a replacement entity in a new domain with the same unique_id counts as 'the entity the user disabled' is a product decision"
  - test: "Backstop truth 05-02 Edge ENT-01/concurrency: every manager state change runs in an event-loop callback without an await; Store writes run as config-entry tasks that unload awaits"
    expected: "Code reading agrees (async_add_kind, async_purge, _async_kind_updated, _async_check_deadlines, _async_schedule_save are @callback and sync; saves use entry.async_create_task). No held-out/property test exercises an interleaving."
    why_human: "verification: backstop (non-inferable); presence + wiring never qualifies -> insufficient_spec"
  - test: "Backstop truth 05-04 Edge ENT-10/concurrency: the per-item option is read once per setup; a change applies on the next reload"
    expected: "Code reading agrees (per_item_entities_enabled read in __init__.async_setup_entry and sensor.async_setup_entry within the same setup; no listener re-reads it). The UI toggle and reload-on-change belong to Phase 7 (W36)."
    why_human: "verification: backstop (non-inferable) -> insufficient_spec"
  - test: "Open a real HA (2026.3 and 2026.10+) with an upgraded 0.3.0 entry in German and English UI"
    expected: "Device page shows 'Traefik (<host>)' with nested 'Traefik routers/services/certificates (<host>)' sub-devices; router/service ENUM states and state icons render translated; the repair notice text reads correctly; 'Refresh now' button sits under diagnostics"
    why_human: "Visual rendering of translations, icons and device nesting cannot be checked by tests (no real HA instance allowed in this verification)"
---

# Phase 5: Entity model + lifecycle Verification Report

**Phase Goal:** Router, service and problem entities reflect live Traefik state for the lifetime of the config entry: new items appear without a reload, vanished items go `missing` and are removed only after a 24 h grace period, states update on every change (and only on change), and the entity/device model is readable, translated (en/de) and categorised — with the never-working reload feature replaced by a "Refresh now" button and existing installs migrated cleanly.
**Verified:** 2026-11-14T22:45:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

The entity lifecycle, write-on-change, device topology, translations, refresh button and per-item option are implemented, wired and covered by passing tests on both HA 2026.3.0 and the dev venv. One goal clause fails: "existing installs migrated cleanly". The migration re-enables every router entity the user disabled in 0.3.0 (CR-01). The verifier reproduced this independently.

### Observable Truths (goal level: ROADMAP success criteria + goal clause)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC1 | Router `enabled -> error` and service server DOWN change entity state on the next cycle; a new router appears without reload; a removed router goes `missing`, keeps its registry entry (name/area) until 24 h (freezer), then is removed; a router back inside the grace period re-binds to the same entity | ✓ VERIFIED | `entity_manager.py:282-310` (add/missing/re-bind), `:313-325` (deadline timer, `async_track_time_interval` at `:193`), Store persistence `:105-111,337-348`. Tests: `test_router_state_follows_status_change` (v2.11+v3.7), `test_service_server_down_reaches_sensor_next_cycle`, `test_new_router_appears_without_reload` (asserts the same runtime_data, so no reload), `test_vanished_router_goes_missing_and_rebinds` (name+area kept), `test_vanished_router_removed_after_grace_period` (24 h - 1 s kept, + 1 s removed), `test_grace_deadline_is_inclusive`, `test_grace_period_survives_entry_reload`, all passing |
| SC2 | Routers/services are ENUM sensors with options `enabled/warning/error/disabled/missing` (translated); service attributes `servers_up`/`servers_total`, no URLs/IPs; one canonical key per attribute | ✓ VERIFIED | `sensor.py:182-261` (ENUM, `ITEM_STATE_OPTIONS`, attribute sets exactly as D-10); `en.json`/`de.json` `entity.sensor.{router,service}.state.*`; `test_item_state_keys_equal_options`; service capture tests assert no `://` / `192.0.2.` |
| SC3 | Problem aggregates are enabled-by-default `binary_sensor`/`problem`, one class + descriptions; counts/version/entrypoints/refresh are DIAGNOSTIC, entrypoints disabled by default; a no-change refresh writes zero states; no listener scans the whole registry | ✓ VERIFIED | `binary_sensor.py:35-115` (`PROBLEM_SENSORS`, no `entity_registry_enabled_default=False`); `sensor.py:75-129,264-274`; `button.py:194`; write-on-change base `entity.py:206-223`; `test_unchanged_notifications_write_no_state` (all entities enabled, `last_reported` unchanged); grep: no `.entities` / `registry.entities` in the package, only `er.async_entries_for_config_entry` |
| SC4 | Main device `Traefik (<host>)` (SERVICE, `/dashboard/` URL, `sw_version` kept current) + Routers/Services/Certificates sub-devices linked via registry `via_device_id` (no `DeviceInfo.via_device`); translation_key names in en+de, `icons.json` state icons, `PARALLEL_UPDATES` everywhere | ✓ VERIFIED | `entity.py:82-124` (`async_update_device(sub.id, via_device_id=main.id)`, DeviceInfo identifiers only at `:50`), `:163-183` sw_version tracker; `icons.json`; `PARALLEL_UPDATES` 0/0/1. Tests: `test_sub_devices_linked_without_deprecation` (dev venv 2026.10, no `report_usage`), `test_main_device_sw_version_follows_traefik` (exactly one update), `test_parallel_updates`, `test_every_code_key_has_texts/icons`, `test_german_device_names` |
| SC5 | Reload button/service/`services.yaml`/client refresh method gone; "Refresh now" refreshes both coordinators of its own entry; 0.3.0 upgrade removes old router `binary_sensor` + reload button and raises a non-fixable repair notice; per-item off -> no router/service entities; cert entities subclass `TraefikCertEntity`, never re-added | ✓ VERIFIED | `services.yaml` absent; grep finds no `reload_routers`/`CONFIG_SCHEMA`/`async_setup(`; `button.py:190-207`; `__init__.py:48-102` (migration + `ir.async_create_issue(... is_fixable=False, is_persistent=True)`), `:242-249` deletes it on remove only (M34). Tests: `test_press_refreshes_only_own_entry`, `test_no_service_registered`, `test_migration_from_1_1`, `test_issue_survives_reload_and_is_deleted_on_remove`, `test_per_item_off_*`, `test_known_cert_hosts_are_never_added_again`, `test_cert_notifications_do_not_grow_listeners` |
| G6 | Existing installs are migrated cleanly: user-disabled entities stay disabled (goal clause; D-18; 05-07 prohibition) | ✗ FAILED | CR-01: `__init__.py:74-81` removes router binary sensors regardless of `disabled_by`; the replacement sensor is created enabled. Verifier probe (scratch copy of the repo; repo untouched): a USER-disabled `binary_sensor` `legacy-entry_http_router_file-ok@file` -> `sensor.traefik_routers_traefik_example_com_file_ok_file` with `disabled_by=None`, state `enabled` |

### Plan must-have truths

| Plan | Truths | Verified | Not verified | Notes |
|------|--------|----------|--------------|-------|
| 05-01 tracer (manager, router ENUM, devices) | 16 | 16 | 0 | Manager on `runtime_data.entity_manager` (`data.py:28`, `__init__.py:160`); sorted adds, no re-adds (`test_manager_adds_each_key_once_in_sorted_order`); `dashboard_url` variants test; `test_router_change_writes_only_that_router` |
| 05-02 grace period | 9 | 8 | 1 insufficient_spec | Store key `traefik_proxy.missing.<entry_id>`; orphan adoption/expiry tests; failed cycle never marks missing. The concurrency truth is a `backstop` truth -> human item |
| 05-03 services/entrypoints/aggregates/diagnostics | 15 | 15 | 0 | `dup@file` router+service separate; 51-problem cap test; healthy_ratio cases; unique_ids kept (`const.py:39-41`) |
| 05-04 per-item option | 5 | 4 | 1 insufficient_spec | `async_purge` + device removal; idempotent reload test. Concurrency truth is `backstop` -> human item. No UI field until Phase 7 (W36, by design) |
| 05-05 cert entities | 6 | 6 | 0 | `TraefikCertEntity` (`entity.py:268-306`) on cert coordinator; no `_coordinator` alias (IN-11 closed); WR-05 tests |
| 05-06 reload removal + refresh button | 5 | 5 | 0 | GET-only test; `PARALLEL_UPDATES = 1`; no explicit `entity_id` assignment anywhere (grep) |
| 05-07 translations, icons, migration, devices | 17 | 17 | 0 | Each listed truth holds as worded (the aggregate `disabled_by` rule, the issue lifecycle, legacy device cleanup with the reference guard, sw_version, no deprecation). The 05-07 **prohibition** fails on its "re-enable" clause -> G6 |
| **Total (plan)** | **73** | **71** | **2** | |

**Score:** 76/79 truths verified (6 goal-level + 73 plan-level): 1 FAILED (G6), 2 insufficient_spec (backstop truths), 0 present but behavior-unverified.

### Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | WR-01: `entry.add_update_listener(...)` result discarded (`__init__.py:223`). HA 2026.3 never clears `update_listeners` on unload (`config_entries.py:532,1161`, verified in the ha2603 venv). The migration's `disabled_by` change makes HA reload the entry 30 s later, so upgraded entries accumulate duplicate listeners | Phase 7 | SC2 "`entry.add_update_listener` is no longer used anywhere"; carry-over note "WR-03 (update-listener leak) is already covered by SC2". The fix is one line (`entry.async_on_unload(entry.add_update_listener(...))`), so applying it alongside CR-01 is cheap |

### Required Artifacts

`gsd-tools verify.artifacts` on all 7 plans returned `all_passed: true`: every declared artifact exists and contains its required marker. Level 3 (wiring) was checked manually:

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `custom_components/traefik_proxy/entity_manager.py` | KindSpec, manager, Store, timer, purge | ✓ VERIFIED | Built in `__init__.py:160`; kinds registered from `sensor.py:146-179`, `binary_sensor.py:83` |
| `custom_components/traefik_proxy/entity.py` | device factory, devices, bases, legacy cleanup, sw_version | ✓ VERIFIED | `async_setup_devices`, `async_remove_legacy_devices` and `async_track_sw_version` are called from `__init__.py:197-207` |
| `custom_components/traefik_proxy/sensor.py` | router/service/entrypoint/snapshot/cert sensors | ✓ VERIFIED | Platform forwarded through `PLATFORMS` |
| `custom_components/traefik_proxy/binary_sensor.py` | problem aggregates, cert expiring | ✓ VERIFIED | |
| `custom_components/traefik_proxy/button.py` | `TraefikRefreshButton` | ✓ VERIFIED | |
| `custom_components/traefik_proxy/__init__.py` | migration, issue, remove_entry | ✓ VERIFIED (behavior gap G6) | |
| `custom_components/traefik_proxy/translations/de.json`, `icons.json` | German strings, icons | ✓ VERIFIED | Key and placeholder parity with en tested; `strings.json` byte-identical to `en.json` (`cmp`) |
| `tests/test_entity_manager.py`, `test_migration.py`, `test_devices.py`, `test_translations.py` | lifecycle, migration, device and translation tests | ✓ VERIFIED | Substantive assertions (read), all passing |

### Key Link Verification

`gsd-tools verify.key-links` on all 7 plans returned `all_verified: true` (19 links), including `async_add_kind(ROUTERS|SERVICES|ENTRYPOINTS|CERT_EXPIRY|CERT_EXPIRING)`, `async_setup_devices(` before forwarding, `via_device_id=main`, `entity_manager=`, `Store[`, `async_remove_missing_store`, `async_track_time_interval(`, `per_item_entities_enabled(`, `async_purge(`, `cert_coordinator.async_request_refresh`, `async_delete_issue`, `async_remove_legacy_devices(` and `MINOR_VERSION = 2`.

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| Router/service/entrypoint sensors | `_model()` | `coordinator.data.{routers,services,entrypoints}[key]` (Phase 4 snapshot from `/api/rawdata`) | Yes (capture-fixture tests) | ✓ FLOWING |
| Problem aggregates | `problems_fn(snapshot)` | `snapshot.{router,service,middleware}_problems` | Yes | ✓ FLOWING |
| Snapshot sensors | `value_fn` | `router_counts`, `version`, `start_date` | Yes | ✓ FLOWING |
| Cert entities | `_row()` | `cert_coordinator.data[host]` | Yes | ✓ FLOWING |
| Main device `sw_version` | `coordinator.data.version.version` | coordinator listener | Yes (test proves one update per change) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full suite, dev venv (HA 2026.10) | `.venv/bin/python -m pytest -q -o addopts="" tests` (scratch copy) | 563 passed | ✓ PASS |
| Full suite, HA 2026.3.0 venv | `ha2603-venv/bin/python -m pytest -q -o addopts="" tests` (scratch copy) | 563 passed | ✓ PASS |
| Lint/format/types | `uv run ruff check`, `ruff format --check`, `mypy --strict custom_components/traefik_proxy` | clean / 38 formatted / no issues | ✓ PASS |
| CR-01 reproduction | scratch probe `test_cr01_user_disabled_router` (repo copy in the scratchpad; repo untouched) | new router sensor `disabled_by=None`, state `enabled` | ✗ FAIL (gap G6) |

### Probe Execution

Step 7c: no `scripts/*/tests/probe-*.sh` declared or present for this phase. Not applicable.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ENT-01 | 05-01..05-03, 05-05 | Entity manager: add, missing, 24 h removal, re-bind; config-entry registry reads only; cert hosts never re-added | ✓ SATISFIED | SC1, SC3, SC5 evidence |
| ENT-02 | 05-01..05-03, 05-05, 05-07 | Key-only per-item entities, write on change, no redundant `available` | ✓ SATISFIED | `entity.py:206-260`; zero-write tests |
| ENT-03 | 05-01, 05-05, 05-07 | `TraefikEntity`/`TraefikCertEntity` sharing one DeviceInfo factory; main device + linked sub-devices; `sw_version` current | ✓ SATISFIED | SC4 evidence |
| ENT-04 | 05-01..05-03 | Router/service ENUM sensors; `servers_up`/`servers_total`; canonical keys | ✓ SATISFIED | SC2 evidence |
| ENT-05 | 05-03 | Problem aggregates on by default, one class + descriptions | ✓ SATISFIED | `binary_sensor.py:43-115` |
| ENT-06 | 05-03 | DIAGNOSTIC category; entrypoints + healthy ratio disabled by default | ✓ SATISFIED | `sensor.py:75-129,271-274` |
| ENT-07 | 05-06 | Reload feature removed; own-entry refresh button, no admin bypass | ✓ SATISFIED | SC5 evidence |
| ENT-08 | 05-03, 05-05..05-07 | translation_key names en+de, icons.json, PARALLEL_UPDATES | ✓ SATISFIED | `test_translations.py` (8 tests). German config/options strings belong to Phase 7 (FLOW-07), as planned |
| ENT-09 | 05-07 | 0.3.0 migration removes old router binary sensors + reload button; persistent non-fixable repair notice deleted on entry removal (M34: not on unload) | ✗ PARTIAL | The literal text is met (tests). The migration does not preserve user-disabled routers (CR-01 -> gap G6), which contradicts "migrated cleanly" and the 05-07 prohibition. M34's departure from "remove on unload" is intended and was honored |
| ENT-10 | 05-04 | Per-item option honoured; off -> no router/service entities, existing removed | ✓ SATISFIED | `test_per_item_off_*`, `test_per_item_default_keeps_router_and_service_entities`. No UI field until Phase 7 (W36, by design) |

No orphaned requirements: REQUIREMENTS.md maps exactly ENT-01..ENT-10 to Phase 5, and every ID appears in a plan's `requirements`. They remain "Pending" until phase.complete, as expected.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `custom_components/traefik_proxy/__init__.py` | 74-81 | Migration deletes user-disabled router entities and lets them come back enabled (CR-01) | 🛑 Blocker | Gap G6. A user who disabled many noisy routers gets them all back, enabled and recording |
| `custom_components/traefik_proxy/__init__.py` | 223, 233-239 | Update-listener remover discarded; the docstring wrongly says HA removes it on unload (WR-01) | ⚠️ Warning | Deferred to Phase 7 SC2. The phase's migration triggers a reload, so duplicates appear on every upgraded entry |
| `custom_components/traefik_proxy/entity.py` | 107-111 | With per-item off, the Routers/Services devices are removed without the "no entity references it" guard that `async_remove_legacy_devices` uses (WR-02) | ⚠️ Warning | This entry loses nothing (its sensors are purged first). Another entry's helper entities linked to the device are silently unlinked (`device_id=None`). Not covered by a later phase. Reachable today only by editing options by hand |
| `custom_components/traefik_proxy/entity.py` | 265, 282 | Redundant `.lower()` on cert hosts, not mirrored in `KindSpec.key_of` (IN-01) | ℹ️ Info | No current path produces mixed-case keys |
| `custom_components/traefik_proxy/translations/en.json` | 66 | Unused `exceptions.cert_unavailable` (IN-03) | ℹ️ Info | Phase 7 translation cleanup |

Debt-marker gate: no `TBD`/`FIXME`/`XXX` (and no `TODO`/`HACK`/placeholder) in any file this phase modified.

### Human Verification Required

These items are kept even though the status is `gaps_found`:

1. **Prohibition ENT-01 (05-02): no registry deletion outside the four allowed paths.** LLM verdict (non-authoritative): holds. See the frontmatter for the call sites.
2. **Prohibition ENT-07 (05-06): GET-only.** LLM verdict: holds. Backed by `test_only_get_requests_reach_traefik`.
3. **Prohibition ENT-09 (05-07).** LLM verdict: **violated** on the "re-enable a user-disabled entity" clause (CR-01, reproduced). The other clauses hold. Fix it, or accept it with an override.
4. **Backstop truth 05-02 (manager concurrency).** insufficient_spec: the code reading agrees, but no test exercises interleaving.
5. **Backstop truth 05-04 (per-item option read once per setup).** insufficient_spec: the code reading agrees.
6. **Visual check in a real HA (en/de).** Check device nesting, translated ENUM states, state icons, the repair text and the button placement.

### Gaps Summary

One root cause blocks the "existing installs migrated cleanly" clause of the goal:

- **CR-01 / G6.** The 1.1 -> 1.2 migration treats every 0.3.0 router binary sensor the same. It deletes the registry entry, and the router sensor that replaces it (same unique_id, `sensor` domain) is registered as a fresh, enabled entry.
  - In 0.3.0 router binary sensors were enabled by default, so every disabled one was a deliberate user choice. That choice is lost on upgrade.
  - This contradicts the phase's own decision D-18 ("user-disabled entries stay disabled") and the 05-07 prohibition. The tests miss it because `_legacy_registry` creates only enabled router binary sensors.
  - The fix is about 10 lines: pre-create USER-disabled sensor-domain replacements before the removal. 05-REVIEW.md CR-01 sketches it, and one migration test covers it.

Everything else in the goal is delivered and proven by passing tests on HA 2026.3.0 and 2026.10:
- live state on every change and only on change;
- add without reload, `missing` state, a 24 h wall-clock grace period that survives reloads, and re-bind;
- one main device with linked sub-devices and `sw_version` tracking;
- en/de translations and icons, entity categories and `PARALLEL_UPDATES`;
- reload removed and the refresh button scoped to its own entry;
- the per-item opt-out and the repair notice lifecycle (M34).

WR-01 is deferred to Phase 7 SC2. WR-02 is a warning, not a gap: it unlinks other entries' helper entities only when per-item entities are switched off, which no UI can do yet. Consider fixing it together with CR-01, since the guard already exists in the same module.

---

_Verified: 2026-11-14T22:45:00Z_
_Verifier: Claude (gsd-verifier)_
