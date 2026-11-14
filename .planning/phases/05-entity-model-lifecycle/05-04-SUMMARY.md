---
phase: 05-entity-model-lifecycle
plan: 04
subsystem: entities
tags: [home-assistant, entity-manager, options, device-registry, traefik]
status: complete

requires:
  - phase: 05-entity-model-lifecycle
    provides: "05-01 TraefikEntityManager/KindSpec (ROUTERS, SERVICES), async_setup_devices and the device topology; 05-02 setup-time registry snapshot, missing-since Store and grace timer; 05-03 SERVICES and ENTRYPOINTS kinds registered in sensor.py"
provides:
  - "const.py: CONF_PER_ITEM_ENTITIES = \"per_item_entities\", DEFAULT_PER_ITEM_ENTITIES = True"
  - "entity_manager.py: per_item_entities_enabled(entry), TraefikEntityManager.async_purge(spec) (immediate removal, drops stored missing-since times)"
  - "entity.py: async_setup_devices(hass, entry, *, per_item=True) skips and removes the Routers and Services sub-devices when off"
  - "__init__.py: option read once per setup; purge of ROUTERS and SERVICES before devices and platforms"
  - "sensor.py: ROUTERS and SERVICES kinds registered only while per-item entities are on"
affects: [05-05, 05-06, 05-07, phase-07-options-flow, phase-08-changelog]

actuals:
  tokens: 4650
  tasks: 1
  commits: 2
plan_head_before: 3e0deb29905988cc86cf9e7b549b053b5ad92811
plan_head_after: 516f0b081c4f3502f38d1e33595c515bea6d5839

tech-stack:
  added: []
  patterns:
    - "A kind the user switched off is purged by the manager (registry entries + stored missing-since data) before platforms set up, and simply not registered by the platform"
    - "Device checks in tests go through dr.async_entries_for_config_entry and identifiers; async_get_device and registry.devices mapping access are deprecated on HA dev and avoided"

key-files:
  created: []
  modified:
    - custom_components/traefik_proxy/const.py
    - custom_components/traefik_proxy/entity_manager.py
    - custom_components/traefik_proxy/entity.py
    - custom_components/traefik_proxy/__init__.py
    - custom_components/traefik_proxy/sensor.py
    - tests/test_entity_manager.py

key-decisions:
  - "Per-item option read at setup only; options-form field and reload-on-change come in Phase 7 (plan decision, W36)"
  - "async_purge works from the setup-time registry snapshot and also drops the purged pairs from it, so nothing can be adopted as missing later"

patterns-established:
  - "RED commit uses the literal options key so the test module imports before the constant exists; GREEN switches to CONF_PER_ITEM_ENTITIES"

requirements-completed: []

coverage:
  - id: D1
    description: "Option off on a fresh entry: no router/service registry entry, no Routers/Services sub-device; entrypoint, certificate (expiring), snapshot and problem entities and main + Certificates devices exist"
    requirement: ENT-10
    verification: "tests/test_entity_manager.py::test_per_item_off_creates_no_router_or_service_entities"
  - id: D2
    description: "Option turned off then reload: router/service entries, states, missing-since Store data and both sub-devices gone right after the reload, no time advance"
    requirement: ENT-10
    verification: "tests/test_entity_manager.py::test_per_item_off_on_reload_removes_existing_entities"
  - id: D3
    description: "Second reload with the option off removes nothing more and logs no error"
    requirement: ENT-10
    verification: "tests/test_entity_manager.py::test_per_item_off_reload_is_idempotent"
  - id: D4
    description: "Default options keep router and service entities and all three sub-devices"
    requirement: ENT-10
    verification: "tests/test_entity_manager.py::test_per_item_default_keeps_router_and_service_entities"

duration: 5min
completed: 2026-11-14
---

# Phase 5 Plan 04: Per-item entities option Summary

**`per_item_entities` option (default on): when off, router and service sensors and the Routers/Services sub-devices are not created, and existing ones are purged without grace period at the next entry reload; entrypoint, certificate, aggregate and diagnostic entities stay.**

## Performance

- **Duration:** about 5 min
- **Started:** 2026-11-14T21:25:49Z
- **Completed:** 2026-11-14
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 6

## Accomplishments

- `CONF_PER_ITEM_ENTITIES` / `DEFAULT_PER_ITEM_ENTITIES` in `const.py`; `per_item_entities_enabled(entry)` in `entity_manager.py`
- `TraefikEntityManager.async_purge(spec)`: removes every setup-time registry entry of the kind right away, drops the kind's stored missing-since times and saves only when the Store content changed
- `async_setup`: option read once after `async_load`; off purges ROUTERS and SERVICES, then `async_setup_devices(..., per_item=False)` removes and skips the Routers and Services sub-devices
- `sensor.py` registers the ROUTERS and SERVICES kinds only while the option is on
- Four per-item tests in `tests/test_entity_manager.py`

## Task Commits

1. **Task 1 RED: failing per-item tests** - `cb2afd9` (test)
2. **Task 1 GREEN: per-item option implementation** - `516f0b0` (feat)

## Files Created/Modified

- `custom_components/traefik_proxy/const.py` - options key and default
- `custom_components/traefik_proxy/entity_manager.py` - `per_item_entities_enabled`, `async_purge`
- `custom_components/traefik_proxy/entity.py` - `async_setup_devices(..., per_item=...)`
- `custom_components/traefik_proxy/__init__.py` - purge and device gating in setup
- `custom_components/traefik_proxy/sensor.py` - gated router/service kinds
- `tests/test_entity_manager.py` - per-item tests

## Gates

- `uv run pytest -q`: 550 passed
- HA 2026.3.0 venv: 550 passed
- `ruff check`, `ruff format --check`: clean; `mypy --strict`: no issues (14 files)

## Decisions Made

- Per-item option read once per setup; a change applies on the next reload (plan decision; Phase 7 adds the form field and reload).

## Worker Decisions

- Purge works from the manager's setup-time registry snapshot and removes the purged pairs from it - reason: the snapshot is what orphan adoption reads, so no purged key can come back as a missing entity; alternative: scan the live registry again.
- Certificate assertion in the per-item tests checks the `tls_expiring_` binary sensors only - reason: the test probe reports every host unreachable and the Phase 4 cert code creates no timestamp sensor for error hosts (W39 changes that in 05-05); alternative: a probe fixture that returns a CertInfo.
- Sub-device absence checked through `dr.async_entries_for_config_entry` only - reason: `async_get_device` and mapping access on `registry.devices` raise deprecation errors on the HA dev version while their replacements are missing on 2026.3; alternative: version-dependent lookups.
- Idempotency test clears caplog before the second reload - reason: any options update already logs duplicate unique_id errors from the Phase 4 cert closures (pre-existing WR-05, moved to 05-05), with or without this option; alternative: filter by logger name.
- RED commit used the literal `"per_item_entities"` key instead of an in-function import - reason: one module constant for all tests; alternative: in-function imports like 05-03.

## Deviations from Plan

None - plan executed exactly as written. (Test assertions adjusted inside the GREEN step as listed under Worker Decisions.)

## Issues Encountered

- Pre-existing, out of scope: `hass.config_entries.async_update_entry(entry, options=...)` fires the update listener, `async_set_threshold` re-runs the cert binary-sensor closure and HA logs "does not generate unique IDs" for the `tls_expiring_` entities. Reproduced with an unrelated option (`tls_warn_days`). It is the WR-05 item already scheduled for 05-05 (cert entities onto the manager); not added to deferred-items.

## User-visible changes (Phase 8 CHANGELOG)

- New option `per_item_entities` (default on). Off: no router or service sensors and no "Traefik routers" / "Traefik services" devices; existing ones are removed at the next reload of the entry. Until the Phase 7 options form it can only be set through `entry.options`.

## Next Phase Readiness

- 05-05 moves certificate entities onto `TraefikCertEntity` and the manager; per-item purge leaves the cert kinds alone.
- Phase 7 adds the options-form field (FLOW-02) and reload-on-change (`OptionsFlowWithReload`).

## Self-Check: PASSED

- FOUND: all six modified files; FOUND: commits cb2afd9, 516f0b0 (ancestors of HEAD)
