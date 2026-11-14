---
phase: 05-entity-model-lifecycle
reviewed: 2026-11-14T23:04:09Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - custom_components/traefik_proxy/__init__.py
  - custom_components/traefik_proxy/entity.py
  - tests/test_devices.py
  - tests/test_init.py
  - tests/test_migration.py
findings:
  critical: 1
  warning: 0
  info: 6
  total: 7
  necessity: 1
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-11-14T23:04:09Z
**Depth:** standard
**Files Reviewed:** 5 (incremental re-review; the previous pass reviewed 28 files of the phase)
**Status:** issues_found

## Summary

This is an incremental re-review of plan 05-08 (`git diff 78b454c..HEAD -- custom_components tests`, commits 50bcc4c..0496c7b). The plan claimed fixes for CR-01, WR-01 and WR-02 of the previous review (2026-11-14T22:11:51Z, 28 files). The findings of that review are kept below. Frontmatter counts cover open findings only.

I checked HA behaviour against the installed HA 2026.3.0 source in `~/.cache/traefik-proxy-integration/ha2603-venv`:
- `helpers/entity_registry.py`: `async_get_or_create` (1080-1260), `_async_update_entity` (1436-1530) and `async_device_modified` (1319-1418).
- `helpers/entity_platform.py`: 876-990 and 1240-1270.
- `config_entries.py`: 1156-1162 and the `_async_process_on_unload` call sites.

Checks run:
- ruff: clean.
- mypy strict: clean.
- Full suite on the dev venv (HA 2026.10.4): 572 passed.
- `tests/test_migration.py`, `tests/test_devices.py` and `tests/test_init.py` on HA 2026.3.0: 28 passed.
- A scratch probe test (not committed) on HA 2026.3.0 reproduced CR-02.

Status of the earlier findings:
- **CR-01, WR-01 and WR-02 are resolved.** Each one has a verification note below.
- **IN-01..IN-04 are still open.** Their text is carried over; only line references moved because of the diff.

Verified as correct in the new code:
- **No device with registry entries is deleted.** Every `async_remove_device` call now goes through `_async_remove_device_if_unreferenced` (`entity.py:83-96`, used at `:130` and `:175`). `grep` finds no other removal path in `custom_components/`.
- **Migration idempotency.**
  - The whole `minor_version < 2` block (`__init__.py:84-143`) is synchronous and has no `await`, so it cannot be interrupted halfway.
  - A second run finds no router binary sensors, so it creates no replacements and does not touch the issue. `test_migration_with_disabled_routers_is_idempotent` covers this.
  - No `(sensor, traefik_proxy, {entry_id}_http_router_*)` key can sit in `deleted_entities` before the migration: 0.3.0 had no sensor-domain router entity (`v0.3.0:sensor.py`). So `async_get_or_create` cannot restore a stale `disabled_by` over the mapped one.
- **DEVICE→USER mapping for routers is justified.** `async_device_modified` (`entity_registry.py:1397-1406`) clears every `DEVICE` disabler on any `update` event of an enabled device, not only when `disabled_by` changes. Keeping `DEVICE` would re-enable the router on the next update of the Routers sub-device. CR-02 below shows that the same mechanism also hits entities the migration does not touch.
- **`suggested_object_id` collisions are handled.**
  - `async_get_available_entity_id` adds `_2` when the old object id is already taken in the `sensor` domain, so nothing crashes.
  - 0.3.0 object ids carry the category in the device name ("HTTP Routers" vs "HTTP Services"), so a router and a service with the same name do not collide.
  - The stored `suggested_object_id` is overwritten with `None` the first time the platform adds the entity (`entity_platform.py:901,928`, `_async_update_entity` compares `!=`). A later "recreate entity IDs" therefore produces the new-style id.
- **Listener cleanup on unload.** `add_update_listener` returns a remover (`config_entries.py:1161-1162`), and `entry.async_on_unload` runs it on unload and when setup fails. The listener is added only after a successful setup, so an entry in `SETUP_RETRY` has no stale listener. `test_update_listener_registered_once_across_reloads` covers it.

Main concern:
- **CR-02 (new):** the migration keeps `DEVICE`-disabled router sensors disabled (now as `USER`). Every other 0.3.0 entity the user disabled through a legacy device (services, entrypoints, overview counts, aggregates, cert sensors) survives with `disabled_by=DEVICE` and moves to an enabled new device. The next update of that device re-enables all of them. The integration triggers such an update itself on every Traefik version change. This is the same harm as CR-01, on a wider set of entities.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Migration re-enables routers the user disabled (the replacement router sensor ignores the old `disabled_by`) — resolved

**File:** `custom_components/traefik_proxy/__init__.py:42-55`, `custom_components/traefik_proxy/__init__.py:93-125`
**Status:** resolved (plan 05-08, 50bcc4c..c265fa5)
**Original issue:**
- The migration removed every router binary sensor without looking at `disabled_by`.
- The platform then created a fresh, enabled `sensor` entry with the same unique_id.
- So routers the user had disabled came back enabled.

**Verification:**
- The migration now collects `(unique_id, mapped disabled_by, old object_id)` for every disabled router binary sensor. It removes the binary sensor and then pre-creates a `sensor` entry with the mapped `disabled_by` (`USER→USER`, `DEVICE→USER`, `INTEGRATION→INTEGRATION`).
- `entity_platform.py:911-930` finds that entry when it adds the router. It updates `device_id` and the metadata but never `disabled_by` (`_async_update_entity` gets no `disabled_by` from that call). It then aborts the add at `:967-975` because the entry is disabled. The replacement therefore stays disabled, has no state and moves to the Routers sub-device. `test_user_disabled_router_stays_disabled` asserts `device_id == routers.id`.
- A disabled router that is no longer in the snapshot is adopted as an orphan (`entity_manager.py:222-237`) and expires after the normal grace period. This matches how other missing items are handled.
- With per-item entities off, `async_purge` removes the replacements, because `async_load` reads the registry after the migration. That is consistent with the option.
- Tests: `test_user_disabled_router_stays_disabled` and `test_disabled_router_replacement_keeps_disabled_state` (user, device, integration, enabled) pass on HA 2026.3.0.
- One gap remains: the same `DEVICE` handling is missing for entities that survive the migration. It is reported as CR-02, not as a reopening of CR-01.

### CR-02: Entities the user disabled through a 0.3.0 device are re-enabled by the next update of their new device

**File:** `custom_components/traefik_proxy/__init__.py:84-126` (missing step), triggered via `custom_components/traefik_proxy/entity.py:196`
**Issue:**
- In 0.3.0 every category had its own device (`v0.3.0:entity.py:20-27,75`): HTTP Routers, HTTP Routers TLS, HTTP Services, HTTP Entrypoints, Overview, Diagnostics. Disabling such a device in the UI sets `disabled_by=DEVICE` on all its entities. That is the usual way to silence a whole category.
- Plan 05-08 handles this only for router binary sensors (`DEVICE→USER`, `__init__.py:44-46,53`). Its own comment states the reason: HA clears a `DEVICE` disabler on the next update of an enabled device.
- Every other 0.3.0 entity keeps its unique_id and survives the migration untouched: service sensors, entrypoint sensors, overview count sensors, the three aggregates and the cert sensors. When the platform adds them, it re-points them to the new, enabled devices (Services, Certificates, main). `disabled_by` stays `DEVICE` (`entity_platform.py:911-938` changes `disabled_by` only when the new device is disabled). The legacy device is then unreferenced and `async_remove_legacy_devices` deletes it.
- From then on, any `update` event of the new device runs `async_device_modified` (`entity_registry.py:1397-1406`). That handler sets `disabled_by=None` on every `DEVICE`-disabled entity on the device. `EntityRegistryDisabledHandler` then reloads the entry 30 s later, and the entities come back enabled and recording.
- The integration triggers this event itself:
  - `async_track_sw_version` calls `async_update_device(main_device_id, sw_version=...)` on every Traefik version change (`entity.py:196`). This re-enables the entrypoint sensors, snapshot sensors and aggregates on the main device.
  - The reconfigure flow can trigger it too: a URL with a new host changes the devices' `translation_placeholders` (`entity.py:113-140`).
  - Ordinary user actions such as renaming a device or assigning an area trigger it as well.
- **Reproduced on HA 2026.3.0** with a scratch test. Setup: a 1.1 entry, the legacy `http_services` and `http_entrypoints` devices disabled by the user, `sensor …_http_service_bulk-svc@file` and `…_http_entrypoint_web` with `disabled_by=DEVICE`.
  - After setup, both are still `DEVICE`, re-pointed to the Services and main devices, and the legacy devices are gone.
  - After `async_update_device(main.id, sw_version="9.9.9")` and a rename of the Services device, both have `disabled_by=None`.
- This contradicts the docstring promise "User-disabled entities stay disabled" (`__init__.py:71-72`) and decision D-18.
- `tests/test_migration.py` has no case for a surviving `DEVICE`-disabled entity.

**Fix:** In the 1.2 migration, after the removal loop, turn the `DEVICE` disabler of every surviving entry on one of this entry's legacy devices into `USER`. That is the same mapping the routers get:
```python
from homeassistant.helpers import device_registry as dr
from .entity import LEGACY_DEVICE_SUFFIXES

legacy_identifiers = {(DOMAIN, f"{entry.entry_id}_{suffix}") for suffix in LEGACY_DEVICE_SUFFIXES}
legacy_device_ids = {
    device.id
    for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    if device.identifiers & legacy_identifiers
}
# Re-read after the removals so removed entries are skipped.
for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
    if reg_entry.disabled_by is er.RegistryEntryDisabler.DEVICE and reg_entry.device_id in legacy_device_ids:
        registry.async_update_entity(reg_entry.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
```
Add a test in `tests/test_migration.py`:
- Setup: a service sensor on a user-disabled legacy `http_services` device and an entrypoint sensor on a user-disabled `http_entrypoints` device.
- Assert both end up `USER`-disabled after setup.
- Assert both stay disabled after `async_update_device(main.id, sw_version=...)` and an update of the Services device.

## Warnings

### WR-01: The update listener is never unsubscribed; the 1.2 migration now forces a reload, so every upgraded entry gets duplicate and stale listeners — resolved

**File:** `custom_components/traefik_proxy/__init__.py:261-265`, `custom_components/traefik_proxy/__init__.py:275-282`
**Status:** resolved (plan 05-08, 98602c2..c265fa5)
**Original issue:** `entry.add_update_listener(...)` threw away the remover it returns, and HA 2026.3 does not clear `update_listeners` on unload. Every reload therefore added another listener, and a stale listener could read a deleted `runtime_data`.
**Verification:**
- The code now calls `entry.async_on_unload(entry.add_update_listener(_async_options_updated))`.
- In HA 2026.3, `add_update_listener` returns `lambda: self.update_listeners.remove(listener)` (`config_entries.py:1161-1162`), and `_async_process_on_unload` runs on unload and on setup failure (`:876`, `:1013`).
- The listener is registered at the very end of a successful setup, so a failed or retrying setup leaves no listener behind.
- The incorrect docstring of `async_unload_entry` is corrected.
- `test_update_listener_registered_once_across_reloads` asserts: one listener after setup, one after reload, exactly one `build_api_client` call per options change, none after unload.

### WR-02: Turning per-item entities off deletes the Routers and Services devices without the reference check used for legacy devices — resolved

**File:** `custom_components/traefik_proxy/entity.py:82-96`, `custom_components/traefik_proxy/entity.py:125-130`
**Status:** resolved (plan 05-08, 6ba969e..db2762c)
**Original issue:** with `per_item=False`, the Routers and Services sub-devices were removed without checking for references, which silently unlinked other integrations' entities.
**Verification:**
- Both removal paths now share `_async_remove_device_if_unreferenced`. It keeps any device that `er.async_entries_for_device(..., include_disabled_entities=True)` returns entries for.
- This entry's own router and service entries are purged before `async_setup_devices` runs (`__init__.py:247-252`), so only foreign or unexpected references keep a sub-device.
- A kept sub-device keeps its `via_device` link and is reused when per-item entities are turned back on.
- `test_per_item_off_keeps_referenced_sub_device` (enabled and user-disabled foreign entity) asserts that the referenced Routers device is kept with the foreign link intact, and that the unused Services device is removed.

## Info

### IN-01: Already-defended-elsewhere: the cert host is lowercased twice more, and only the factory changes the key

**File:** `custom_components/traefik_proxy/entity.py:278-280`, `custom_components/traefik_proxy/entity.py:296-300`
**Category:** necessity
**Status:** open (carried over; line numbers updated for the 05-08 diff)
**Issue:**
- The cert data keys come only from `_collect_hosts_from_main_coordinator`, which lowercases every host (`cert_coordinator.py:205-213`, used at `:130-133`). The only other writer is `async_set_updated_data({})` (`__init__.py:241`).
- Lowercasing again in `cert_hosts()` and in `TraefikCertEntity.__init__` guards against a state that cannot occur.
- The factory-side `host.lower()` is also inconsistent with `KindSpec.key_of`, which returns the registry key unchanged. If a mixed-case key ever reached the factory (for example through orphan adoption), `factory(key)` would build a unique_id that differs from the orphan's, and the platform would see a duplicate unique_id.

**Fix:** Drop both extra `.lower()` calls and rely on the coordinator's normalisation, or normalise in exactly one place that `key_of` also uses.

### IN-02: `de.json` has no `config`, `options` or `exceptions` sections

**File:** `custom_components/traefik_proxy/translations/de.json`
**Status:** open (carried over; file not changed by 05-08)
**Issue:** The new German file translates only devices, entities and issues. All 30 `config.*`, `options.*` and `exceptions.*` keys in `en.json` are missing. HA falls back to `en`, so German users see the setup, reauth, reconfigure and options flows in English.
**Fix:** Add the German config, options and exceptions strings, or note the partial translation as deliberate in the phase notes.

### IN-03: Unused translation `exceptions.cert_unavailable`

**File:** `custom_components/traefik_proxy/strings.json:66`, `custom_components/traefik_proxy/translations/en.json:66`
**Status:** open (carried over; files not changed by 05-08)
**Issue:** No code raises an exception with `translation_key="cert_unavailable"` (`grep` finds it only in the JSON files). The string predates this phase but survived the translation rework.
**Fix:** Remove it from `strings.json` and `en.json`, or use it.

### IN-04: The per-item option has a code path but no UI

**File:** `custom_components/traefik_proxy/entity_manager.py:91-93`, `custom_components/traefik_proxy/config_flow.py:244-255`
**Status:** open (carried over; the `__init__.py` reference moved to line 246, and the WR-02 remark is updated because WR-02 is resolved)
**Issue:**
- `CONF_PER_ITEM_ENTITIES` drives the purge and the device removal at setup.
- The options flow schema has no field for it, so users cannot turn it off.
- Nothing reloads the entry when it changes: `__init__.py:246` reads it once per setup.
- ROADMAP line 437 defers the toggle to the next phase. Until then, the purge path and the now-guarded sub-device removal can be reached only by editing options by hand.

**Fix:** None needed in this phase. Make sure the next phase adds the toggle together with `OptionsFlowWithReload`, so a change takes effect at once.

### IN-05: The migration keeps "disabled" but drops "hidden" for router sensors

**File:** `custom_components/traefik_proxy/__init__.py:96-105`, `custom_components/traefik_proxy/__init__.py:117-125`
**Status:** open (new)
**Issue:**
- The replacement logic looks only at `disabled_by`. A router binary sensor the user hid but left enabled (`hidden_by=USER`) is removed, and the platform creates a visible replacement.
- The same applies to `area_id`, labels and categories, which matters less.
- A user who hid noisy routers to keep them off auto-generated dashboards sees them again after the upgrade.
- D-18 promises only to keep entities disabled, so this is a gap in expectations, not a broken contract.

**Fix:** Also carry `hidden_by=USER` over: collect `reg_entry.hidden_by` next to `disabled_by` and pass `hidden_by=` to the pre-created replacement, including for enabled routers. Alternatively, state in the repair text that hidden flags are not carried over.

### IN-06: Disabled replacements keep the old object id, while the repair text says router sensors get new entity IDs

**File:** `custom_components/traefik_proxy/__init__.py:103,124`, `custom_components/traefik_proxy/translations/en.json:149`
**Status:** open (new)
**Issue:**
- Enabled routers get new-style ids from the platform, for example `sensor.traefik_routers_<host>_<router>`. Disabled replacements are pre-created with the old object id, for example `sensor.traefik_http_router_file_ok_file` (asserted in `tests/test_migration.py`).
- One router list therefore mixes two id schemes. A user who later enables a replacement gets an id that differs from its siblings.
- The repair issue says "Router binary sensors were replaced by router sensors with new entity IDs", which is not true for the disabled ones.
- Nothing breaks, because no automation can reference a `sensor.` id that did not exist before.

**Fix:** Either drop `suggested_object_id` so that disabled replacements get the same new-style id as enabled ones, or mention in the repair text that disabled routers keep their old object id under the `sensor` domain.

---

_Reviewed: 2026-11-14T23:04:09Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
