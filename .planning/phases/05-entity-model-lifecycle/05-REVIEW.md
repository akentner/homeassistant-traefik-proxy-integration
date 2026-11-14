---
phase: 05-entity-model-lifecycle
reviewed: 2026-11-14T22:11:51Z
depth: standard
files_reviewed: 28
files_reviewed_list:
  - custom_components/traefik_proxy/__init__.py
  - custom_components/traefik_proxy/api.py
  - custom_components/traefik_proxy/binary_sensor.py
  - custom_components/traefik_proxy/button.py
  - custom_components/traefik_proxy/config_flow.py
  - custom_components/traefik_proxy/const.py
  - custom_components/traefik_proxy/data.py
  - custom_components/traefik_proxy/entity.py
  - custom_components/traefik_proxy/entity_manager.py
  - custom_components/traefik_proxy/icons.json
  - custom_components/traefik_proxy/sensor.py
  - custom_components/traefik_proxy/strings.json
  - custom_components/traefik_proxy/translations/de.json
  - custom_components/traefik_proxy/translations/en.json
  - tests/conftest.py
  - tests/test_api.py
  - tests/test_binary_sensor.py
  - tests/test_binary_sensor_tls_expiring.py
  - tests/test_cert_entity_state.py
  - tests/test_coordinator.py
  - tests/test_devices.py
  - tests/test_entity_manager.py
  - tests/test_init.py
  - tests/test_migration.py
  - tests/test_platforms_real_fixtures.py
  - tests/test_sensor.py
  - tests/test_sensor_tls.py
  - tests/test_translations.py
findings:
  critical: 1
  warning: 2
  info: 4
  total: 7
  necessity: 1
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-11-14T22:11:51Z
**Depth:** standard
**Files Reviewed:** 28
**Status:** issues_found

## Summary

I reviewed the phase diff `e4e7dc5..HEAD` for `custom_components/` and `tests/`. I also read the called modules that are out of scope (`coordinator.py`, `cert_coordinator.py`, `models.py`) and checked HA behaviour against the installed HA 2026.3 source (`config_entries.py`, `helpers/entity_registry.py`). Checks run: ruff (clean), mypy strict (clean) and pytest (563 passed).

What I verified as correct:
- **Registry and device removal stays inside this entry:**
  - `async_purge`, the deadline removal and the migration all build unique_ids from this entry's ID, which is a fixed-length ULID with no `_`, so they cannot match another entry's objects.
  - `async_remove_legacy_devices` keeps any device that a registry entry still references (disabled entries and other config entries included).
  - Platform setup awaits the entity add tasks, so every surviving entity, disabled ones too, is moved to its new device before the legacy cleanup runs.
- **Old unique_ids still match:** every 0.3.0 unique_id (`v0.3.0` tag) maps onto a current kind prefix, or the migration removes it. 0.3.0 already lowercased cert hosts, so no casing mismatch occurs.
- **Cleanup on unload:** the timer, the kind listeners and the `sw_version` listener are all registered through `entry.async_on_unload`.
- **Writes only on change:** Store writes are skipped when the data equals the last write, and entities write state only when their token changes.
- **HA 2026.3 compatibility:** no `DeviceInfo(via_device=...)` and no APIs newer than 2026.3.
- **Secrets:** no token or password is logged, and `dashboard_url` drops userinfo.

Main concerns:
- **CR-01:** a router binary sensor the user disabled in 0.3.0 comes back enabled as a router sensor after the migration.
- **WR-01:** the update listener is never removed. This phase's migration now forces a reload of every upgraded entry 30 s after start, so every upgraded entry ends up with duplicate listeners.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Migration re-enables routers the user disabled (the replacement router sensor ignores the old `disabled_by`)

**File:** `custom_components/traefik_proxy/__init__.py:76-81` (with `custom_components/traefik_proxy/entity_manager.py:244-246`)
**Issue:**
- In 0.3.0, router binary sensors were enabled by default (`v0.3.0:binary_sensor.py`, class `TraefikProxyRouterBinarySensor`, no `entity_registry_enabled_default = False`). So any router binary sensor that is disabled was disabled by the user (`RegistryEntryDisabler.USER`).
- The migration removes every `binary_sensor` with the `{entry_id}_http_router_` prefix and does not check `disabled_by`.
- On the next setup, `async_add_kind(ROUTERS, ...)` creates a `sensor` entity with the same unique_id (`{entry_id}_http_router_{name}`) for every router in the snapshot. A fresh registry entry is enabled by default.
- Result: on a large install, a user who turned off dozens of noisy router binary sensors gets all of them back, enabled and recording, after the upgrade. This contradicts the D-18 intent ("user-disabled entities stay disabled"). The routers are the same items under the same unique_id, so from the user's side these are the same entities.
- `tests/test_migration.py` has no case for a user-disabled router binary sensor.

**Fix:** Before removing an old router binary sensor that the user disabled, pre-create its sensor-domain replacement, disabled by the user, so the platform finds a disabled entry:
```python
user_disabled_routers: list[str] = []
for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
    if reg_entry.domain == "binary_sensor" and reg_entry.unique_id.startswith(router_prefix):
        if reg_entry.disabled_by is er.RegistryEntryDisabler.USER:
            user_disabled_routers.append(reg_entry.unique_id)
        registry.async_remove(reg_entry.entity_id)
        removed += 1
    ...
for unique_id in user_disabled_routers:
    registry.async_get_or_create(
        "sensor",
        DOMAIN,
        unique_id,
        config_entry=entry,
        disabled_by=er.RegistryEntryDisabler.USER,
    )
```
Add a test in `tests/test_migration.py`: a user-disabled `binary_sensor` `http_router_x` becomes a `sensor` registry entry with `disabled_by=USER` and no state.

## Warnings

### WR-01: The update listener is never unsubscribed; the 1.2 migration now forces a reload, so every upgraded entry gets duplicate and stale listeners

**File:** `custom_components/traefik_proxy/__init__.py:223`, `custom_components/traefik_proxy/__init__.py:233-239`
**Issue:**
- `entry.add_update_listener(_async_options_updated)` discards the remover it returns.
- The `async_unload_entry` docstring claims "HA removes the update listener automatically as part of entry unload". That is false for the supported HA version. In HA 2026.3, `ConfigEntry.update_listeners` is reset only in `__init__` (`config_entries.py:532`). `add_update_listener` only appends (`:1161`), and unload never clears the list. Unload does delete `runtime_data` (`:1014-1015`).
- **Effect 1, duplicates:** every reload appends another copy. `_async_options_updated` then runs N times per options change: N client rebuilds and N threshold pushes.
- **Effect 2, crash:** if the entry is unloaded or in `SETUP_RETRY` (for example, the reload fails while Traefik is down) and the user saves options, the stale listener reads `entry.runtime_data` and raises `AttributeError` in an unhandled task.
- **Why this phase makes it worse:** the code is older than this phase, but the phase now triggers it on every upgrade. `async_migrate_entry` clears `disabled_by` on the aggregates (`__init__.py:87`). HA's `EntityRegistryDisabledHandler` (`config_entries.py:3930-3987`) then schedules an entry reload 30 s later. `tests/test_migration.py:3-5` documents this reload.
- ROADMAP Phase 6 (line 437) plans to drop `add_update_listener`. Until then, the shipped migration creates the leak.

**Fix:** Register the remover so unload removes the listener, and correct the docstring:
```python
entry.async_on_unload(entry.add_update_listener(_async_options_updated))
```

### WR-02: Turning per-item entities off deletes the Routers and Services devices without the reference check used for legacy devices

**File:** `custom_components/traefik_proxy/entity.py:105-110`
**Issue:**
- With `per_item=False`, `async_setup_devices` calls `device_registry.async_remove_device` on the entry's Routers and Services sub-devices without checking for entity references.
- `async_remove_legacy_devices` (`entity.py:155-160`) deliberately keeps a device while any registry entry references it. The two removal paths in the same module follow different safety rules.
- This entry's own router and service sensors are purged first (`__init__.py:204-206`), so nothing of this entry is lost.
- Entities of other config entries linked to the device (helpers that support a device link, such as template or derivative helpers) are silently unlinked: HA sets their `device_id` to None (`helpers/entity_registry.py:1330-1344`). The user loses that link without notice.

**Fix:** Apply the same guard as for legacy devices. Remove the device only when no registry entry references it:
```python
entity_registry = er.async_get(hass)
for device_entry in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
    if device_entry.identifiers & unwanted and not er.async_entries_for_device(
        entity_registry, device_entry.id, include_disabled_entities=True
    ):
        device_registry.async_remove_device(device_entry.id)
```

## Info

### IN-01: Already-defended-elsewhere: the cert host is lowercased twice more, and only the factory changes the key

**File:** `custom_components/traefik_proxy/entity.py:262-264`, `custom_components/traefik_proxy/entity.py:280-284`
**Category:** necessity
**Issue:**
- The cert data keys come only from `_collect_hosts_from_main_coordinator`, which lowercases every host (`cert_coordinator.py:205-213`, used at `:130-133`). The only other writer is `async_set_updated_data({})` (`__init__.py:198`).
- `cert_hosts()` lowercasing again and `TraefikCertEntity.__init__` lowercasing again guard against a state that cannot occur.
- The factory-side `host.lower()` is also inconsistent with `KindSpec.key_of`, which returns the registry key unchanged. If a mixed-case key ever reached the factory (for example through orphan adoption), `factory(key)` would build a unique_id that differs from the orphan's, and the platform would see a duplicate unique_id.

**Fix:** Drop both extra `.lower()` calls and rely on the coordinator's normalisation, or normalise in exactly one place that `key_of` also uses.

### IN-02: `de.json` has no `config`, `options` or `exceptions` sections

**File:** `custom_components/traefik_proxy/translations/de.json`
**Issue:** The new German file translates only devices, entities and issues. All 30 `config.*`, `options.*` and `exceptions.*` keys in `en.json` are missing, so German users see the setup, reauth, reconfigure and options flows in English (HA falls back to `en`).
**Fix:** Add the German config, options and exceptions strings, or note the partial translation as deliberate in the phase notes.

### IN-03: Unused translation `exceptions.cert_unavailable`

**File:** `custom_components/traefik_proxy/strings.json:66`, `custom_components/traefik_proxy/translations/en.json:66`
**Issue:** No code raises a `translation_key="cert_unavailable"` exception (`grep` finds only the JSON files). The string predates this phase but survived the translation rework.
**Fix:** Remove it from `strings.json` and `en.json`, or use it.

### IN-04: The per-item option has a code path but no UI

**File:** `custom_components/traefik_proxy/entity_manager.py:91-93`, `custom_components/traefik_proxy/config_flow.py:244-255`
**Issue:**
- `CONF_PER_ITEM_ENTITIES` drives the purge and device removal at setup.
- The options flow schema has no field for it, so users cannot turn it off, and nothing reloads the entry when it changes (`__init__.py:202` reads it once per setup).
- ROADMAP line 437 defers the toggle to the next phase. Until then, the purge path (and WR-02) is reachable only by editing options by hand.

**Fix:** None needed in this phase. Make sure the next phase adds the toggle together with `OptionsFlowWithReload`, so a change takes effect at once.

---

_Reviewed: 2026-11-14T22:11:51Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
