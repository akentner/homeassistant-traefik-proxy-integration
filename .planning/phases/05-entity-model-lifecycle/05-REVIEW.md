---
phase: 05-entity-model-lifecycle
reviewed: 2026-11-14T23:17:19Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - custom_components/traefik_proxy/__init__.py
  - custom_components/traefik_proxy/entity.py
  - tests/test_migration.py
findings:
  critical: 0
  warning: 0
  info: 6
  total: 6
  necessity: 1
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-11-14T23:17:19Z
**Depth:** standard
**Files Reviewed:** 3 (incremental re-review; earlier passes reviewed 28 and 5 files of the phase)
**Status:** issues_found

## Summary

This is an incremental re-review of the review-fix run (`git diff e145fc6..HEAD -- custom_components tests`, commits 4e1aee1..5ea22e5). The run claimed fixes for CR-02 and IN-05 of the previous review (2026-11-14T23:04:09Z). The findings of the earlier reviews are kept below. Frontmatter counts cover open findings only.

I checked HA behaviour against the installed HA 2026.3.0 source in `~/.cache/traefik-proxy-integration/ha2603-venv`:
- `helpers/entity_registry.py`: `async_get_or_create` (1080-1270), `async_device_modified` (1319-1418), `async_entries_for_device` (1955) and `async_entries_for_config_entry` (1996).
- `helpers/device_registry.py`: `async_entries_for_config_entry` (1730).
- `helpers/entity_platform.py`: 876-975 (existing-entry path, device-disabled handling, disabled abort).
- `config_entries.py`: `EntityRegistryDisabledHandler` (3910-3985).

Checks run:
- ruff: clean.
- mypy strict: clean (14 source files).
- `tests/test_migration.py`, `tests/test_devices.py` and `tests/test_init.py` on HA 2026.3.0: 33 passed.
- A scratch probe test on HA 2026.3.0 (deleted afterwards, not committed) confirmed the behaviour in IN-07.

Status of the earlier findings:
- **CR-02 and IN-05 are resolved.** Each one has a verification note below.
- **CR-01, WR-01 and WR-02 stay resolved.** This diff does not touch their code paths.
- **IN-01..IN-04 are still open.** Their text is carried over unchanged.
- **IN-06 is still open.** I updated it because the IN-05 fix widens it to hidden, enabled routers.

Verified against the user's priorities:
- **No device that still has entities is deleted.**
  - `async_remove_legacy_devices` (`entity.py:174-185`) now gets its devices from `async_legacy_devices` (`entity.py:158-171`). The predicate is the same as before the refactor: this entry's devices only, exactly one legacy identifier, no current identifier.
  - The behaviour is the same as before. The old code also iterated over the list that `dr.async_entries_for_config_entry` returns, built `legacy`/`current` once per call, and passed only `device.id` on to `_async_remove_device_if_unreferenced`. That function still checks `er.async_entries_for_device(..., include_disabled_entities=True)` before every removal.
  - The migration only reads devices. It removes none and updates none.
- **No user-disabled entity is re-enabled.**
  - The new step (`__init__.py:130-133`) changes only `DEVICE` to `USER`, so it never enables anything.
  - `EntityRegistryDisabledHandler._handle_entry_updated` returns early for a disabled entry (`config_entries.py:3940-3947`). A `DEVICE→USER` update therefore schedules no reload.
  - `entity_platform.py:911-930` calls `async_get_or_create` on the existing entry, which does not pass `disabled_by` or `hidden_by` on to `_async_update_entity` (`entity_registry.py:1120-1137`). `:932-935` changes `disabled_by` only for enabled entries on a disabled device. So the `USER` disabler survives the re-point to the new device.
  - `async_device_modified` clears only `DEVICE` (`entity_registry.py:1397-1406`), so later device updates leave `USER` alone.
- **No surviving entity is renamed or re-IDed.** The new step passes only `disabled_by`. The replacements for routers are new `sensor` entries, as in CR-01.
- **No object of another config entry is touched.** Both loops iterate over `er.async_entries_for_config_entry(registry, entry.entry_id)`, and `async_legacy_devices` lists only devices of this entry. `test_device_disabled_mapping_is_scoped_and_idempotent` covers a foreign entity on this entry's legacy device and on the foreign entry's own legacy device.
- **Migration idempotency.**
  - The `minor_version < 2` block (`__init__.py:93-163`) still has no `await`.
  - A second run finds no router binary sensors and no `DEVICE` entries on legacy devices, so it changes nothing.
  - The tests compare whole `RegistryEntry` objects, which include `modified_at`, before and after a forced second run (`test_migration.py:276-298`, `:458-501`, `:577-623`). An update that writes the same values would therefore also be caught.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Migration re-enables routers the user disabled (the replacement router sensor ignores the old `disabled_by`) — resolved

**File:** `custom_components/traefik_proxy/__init__.py:47-60`, `custom_components/traefik_proxy/__init__.py:105-145`
**Status:** resolved (plan 05-08, 50bcc4c..c265fa5; unchanged by 4e1aee1..5ea22e5 apart from the added `hidden_by` field)
**Original issue:**
- The migration removed every router binary sensor without looking at `disabled_by`.
- The platform then created a fresh, enabled `sensor` entry with the same unique_id.
- So routers the user had disabled came back enabled.

**Verification:**
- The migration collects the mapped `disabled_by` for every disabled router binary sensor (`USER→USER`, `DEVICE→USER`, `INTEGRATION→INTEGRATION`), removes the binary sensor and pre-creates a `sensor` entry with the same unique_id.
- `entity_platform.py:911-930` finds that entry, re-points it to the Routers sub-device and leaves `disabled_by` alone. It then aborts the add at `:967-975` because the entry is disabled.
- The tests `test_user_disabled_router_stays_disabled` and `test_disabled_router_replacement_keeps_disabled_state` pass on HA 2026.3.0.

### CR-02: Entities the user disabled through a 0.3.0 device are re-enabled by the next update of their new device — resolved

**File:** `custom_components/traefik_proxy/__init__.py:127-133`, `custom_components/traefik_proxy/entity.py:158-171`
**Status:** resolved (4e1aee1..80e1902)
**Original issue:**
- Entities that survived the migration with `disabled_by=DEVICE` were re-pointed to the new, enabled devices.
- From then on, any `update` event of such a device made `async_device_modified` set `disabled_by=None` on all of them. The integration triggers such events itself through `async_track_sw_version`.

**Verification:**
- After the removal loop, the migration reads this entry's registry entries again. It changes `DEVICE` to `USER` for every entry whose `device_id` is one of this entry's legacy devices (`__init__.py:130-133`).
  - Entries removed in the first loop are skipped, because the list is read again.
  - The pre-created router replacements come later and have no `device_id`, so the step cannot touch them.
- A `USER` disabler is out of reach for the HA paths that caused the bug:
  - `async_device_modified` (`entity_registry.py:1397-1406`) clears only `DEVICE`.
  - The platform's existing-entry path (`entity_platform.py:911-935`) does not write `disabled_by` for an entry that is already disabled.
- The legacy devices are found through the same predicate as the cleanup (`async_legacy_devices`). A disabled device that carries the current main identifier is therefore left alone, and HA correctly clears `DEVICE` there when the user re-enables it. `test_device_disabled_mapping_is_scoped_and_idempotent` covers this (`on_main` stays `DEVICE`).
- Tests on HA 2026.3.0:
  - `test_device_disabled_entities_stay_disabled_after_device_updates`. Setup: a service sensor, an aggregate and a cert sensor on three disabled legacy devices. After setup, all three are `USER`-disabled, have no state and are re-pointed to Services, main and Certificates, and the legacy devices are gone.
  - The same test then runs a real Traefik version change. It asserts `sw_version == "3.7.99"`, so `async_track_sw_version` really fired an `update` event. It also renames the Services and Certificates devices. All three entities stay `USER`-disabled.
  - This is the exact reproduction from the previous review, and it passes now.
- One edge case remains, which is out of the reach of the original finding: a stale `DEVICE` disabler on an *enabled* legacy device is also turned into `USER`. It is reported as IN-07 and does not reopen CR-02.

## Warnings

### WR-01: The update listener is never unsubscribed; the 1.2 migration now forces a reload, so every upgraded entry gets duplicate and stale listeners — resolved

**File:** `custom_components/traefik_proxy/__init__.py:281-285`, `custom_components/traefik_proxy/__init__.py:295-302`
**Status:** resolved (plan 05-08, 98602c2..c265fa5; not touched by 4e1aee1..5ea22e5)
**Original issue:** `entry.add_update_listener(...)` threw away the remover it returns, and HA 2026.3 does not clear `update_listeners` on unload. Every reload therefore added another listener, and a stale listener could read a deleted `runtime_data`.
**Verification:**
- The code calls `entry.async_on_unload(entry.add_update_listener(_async_options_updated))` at the end of a successful setup.
- `test_update_listener_registered_once_across_reloads` covers it.

### WR-02: Turning per-item entities off deletes the Routers and Services devices without the reference check used for legacy devices — resolved

**File:** `custom_components/traefik_proxy/entity.py:82-96`, `custom_components/traefik_proxy/entity.py:124-130`
**Status:** resolved (plan 05-08, 6ba969e..db2762c; not touched by 4e1aee1..5ea22e5)
**Original issue:** with `per_item=False`, the Routers and Services sub-devices were removed without a reference check, which silently unlinked other integrations' entities.
**Verification:**
- Both removal paths go through `_async_remove_device_if_unreferenced`, which still has no other caller and no bypass.
- `test_per_item_off_keeps_referenced_sub_device` covers it.

## Info

### IN-01: Already-defended-elsewhere: the cert host is lowercased twice more, and only the factory changes the key

**File:** `custom_components/traefik_proxy/entity.py:288-290`, `custom_components/traefik_proxy/entity.py:306-310`
**Category:** necessity
**Status:** open (carried over; line numbers updated for the 4e1aee1..5ea22e5 diff)
**Issue:**
- The cert data keys come only from `_collect_hosts_from_main_coordinator`, which lowercases every host (`cert_coordinator.py:205-213`, used at `:130-133`). The only other writer is `async_set_updated_data({})` (`__init__.py:261`).
- Lowercasing again in `cert_hosts()` and in `TraefikCertEntity.__init__` guards against a state that cannot occur.
- The `host.lower()` in the factory is also inconsistent with `KindSpec.key_of`, which returns the registry key unchanged. If a mixed-case key ever reached the factory (for example through orphan adoption), `factory(key)` would build a unique_id that differs from the orphan's, and the platform would see a duplicate unique_id.

**Fix:** Drop both extra `.lower()` calls and rely on the coordinator's normalisation, or normalise in exactly one place that `key_of` also uses.

### IN-02: `de.json` has no `config`, `options` or `exceptions` sections

**File:** `custom_components/traefik_proxy/translations/de.json`
**Status:** open (carried over; file not changed by 4e1aee1..5ea22e5)
**Issue:** The new German file translates only devices, entities and issues. All 30 `config.*`, `options.*` and `exceptions.*` keys in `en.json` are missing. HA falls back to `en`, so German users see the setup, reauth, reconfigure and options flows in English.
**Fix:** Add the German config, options and exceptions strings, or note the partial translation as deliberate in the phase notes.

### IN-03: Unused translation `exceptions.cert_unavailable`

**File:** `custom_components/traefik_proxy/strings.json:66`, `custom_components/traefik_proxy/translations/en.json:66`
**Status:** open (carried over; files not changed by 4e1aee1..5ea22e5)
**Issue:** No code raises an exception with `translation_key="cert_unavailable"` (`grep` finds it only in the JSON files). The string predates this phase but survived the translation rework.
**Fix:** Remove it from `strings.json` and `en.json`, or use it.

### IN-04: The per-item option has a code path but no UI

**File:** `custom_components/traefik_proxy/entity_manager.py:91-93`, `custom_components/traefik_proxy/config_flow.py:244-255`
**Status:** open (carried over; the `__init__.py` reference moved to line 266)
**Issue:**
- `CONF_PER_ITEM_ENTITIES` drives the purge and the device removal at setup.
- The options flow schema has no field for it, so users cannot turn it off.
- Nothing reloads the entry when it changes: `__init__.py:266` reads it once per setup.
- ROADMAP line 437 defers the toggle to the next phase. Until then, the purge path and the guarded sub-device removal can be reached only by editing options by hand.

**Fix:** None needed in this phase. Make sure the next phase adds the toggle together with `OptionsFlowWithReload`, so a change takes effect at once.

### IN-05: The migration keeps "disabled" but drops "hidden" for router sensors — resolved

**File:** `custom_components/traefik_proxy/__init__.py:102-116`, `custom_components/traefik_proxy/__init__.py:134-145`
**Status:** resolved (c71cf6c..5ea22e5)
**Original issue:** The replacement logic looked only at `disabled_by`. A router binary sensor the user had hidden but left enabled came back visible.
**Verification:**
- A replacement is now pre-created when the router binary sensor has a mapped `disabled_by` *or* any `hidden_by` (`__init__.py:112-115`). `hidden_by` is passed to `async_get_or_create` (`:143`).
- In HA 2026.3, `async_get_or_create` sets `hidden_by` only when it creates the entry. On an existing entry it calls `_async_update_entity` without `hidden_by` (`entity_registry.py:1120-1137`). The platform's later `hidden_by=INTEGRATION`/`None` (`entity_platform.py:904-920`) therefore cannot overwrite it.
- No `deleted_entities` record can restore a different `hidden_by`: the removed record is keyed under `binary_sensor`, and 0.3.0 had no `sensor` router entity.
- `test_hidden_router_replacement_stays_hidden` passes on HA 2026.3.0 for three cases: `enabled-user`, `disabled-user` and `enabled-integration`. A visible sibling router still gets the platform's new-style id with `hidden_by=None`.
- Residuals, not part of the fix:
  - `area_id`, labels, categories, aliases, icon and name still do not carry over. The original finding rated this lower, and `test_disabled_router_replacement_keeps_disabled_state` asserts `name is None` on purpose.
  - The IN-05 fix makes hidden, enabled replacements keep the old object id. That is folded into IN-06.

### IN-06: Pre-created router replacements (disabled or hidden) keep the old object id, while the repair text says router sensors get new entity IDs

**File:** `custom_components/traefik_proxy/__init__.py:114,144`, `custom_components/traefik_proxy/translations/en.json:149`
**Status:** open (updated: the IN-05 fix widened the scope from disabled to disabled or hidden routers)
**Issue:**
- Visible, enabled routers get new-style ids from the platform, for example `sensor.traefik_routers_<host>_<router>`. Every pre-created replacement keeps the old object id under `sensor.`, for example `sensor.traefik_http_router_file_ok_file`. That applies to disabled routers and, since 5ea22e5, to hidden routers, enabled ones included (asserted in `test_migration.py:395,438`).
- One router list therefore mixes two id schemes. Hidden, enabled replacements are live entities with state and history under the old scheme. Disabled ones show the mix as soon as the user enables them.
- The repair issue says "Router binary sensors were replaced by router sensors with new entity IDs". That is not true for the disabled or hidden ones.
- Nothing breaks, because no automation can reference a `sensor.` id that did not exist before.

**Fix:** Either mention in the repair text that disabled and hidden routers keep their old object id under the `sensor` domain, or pre-create the replacements with the platform's new-style object id. Dropping `suggested_object_id` alone is not enough, because HA would then generate `sensor.traefik_proxy_<unique_id>` (see the fixer's decision table in `05-REVIEW-FIX.md`).

### IN-07: The DEVICE→USER step also hardens a stale `DEVICE` disabler on an enabled legacy device

**File:** `custom_components/traefik_proxy/__init__.py:130-133`, `custom_components/traefik_proxy/entity.py:158-171`
**Status:** open (new)
**Issue:**
- The step maps `DEVICE` to `USER` for every entry on any legacy device of this entry, whether or not that device is actually disabled. `async_legacy_devices` does not check `device.disabled`.
- An entity with `disabled_by=DEVICE` on an *enabled* device is a stale state. HA itself would clear it on the next `update` of that device (`entity_registry.py:1397-1406`), because the device the user disabled is no longer disabled.
- Converting such an entity to `USER` keeps it disabled for good, against HA's own resolution of the state.
- **Confirmed on HA 2026.3.0** with a scratch probe (deleted afterwards): an enabled legacy `http_services` device and a `DEVICE`-disabled service sensor on it give `disabled_by=USER` after `async_migrate_entry`.
- The state is rare. Under normal operation, enabling a device fires an `update` event that clears `DEVICE` in the same loop tick. Stale state can come from hand-edited storage, or from a crash between the device registry save and the entity registry save, which are debounced separately. That is why this is rated Info and not Warning. It does not contradict any of the user's priorities, since nothing is enabled and nothing is renamed. It only makes the intent "disabled through a device" stricter than HA would.

**Fix:** Restrict the mapping to legacy devices that are disabled:
```python
legacy_device_ids = {device.id for device in async_legacy_devices(hass, entry) if device.disabled}
```
Add a case with an enabled legacy device to `test_device_disabled_mapping_is_scoped_and_idempotent` and expect it to stay `DEVICE`. The router mapping (`DEVICE→USER` in `_ROUTER_REPLACEMENT_DISABLED_BY`) has the same blind spot. It is less important there, because the replacement is a new entry and the old disabler cannot be kept as it is anyway.

---

_Reviewed: 2026-11-14T23:17:19Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
