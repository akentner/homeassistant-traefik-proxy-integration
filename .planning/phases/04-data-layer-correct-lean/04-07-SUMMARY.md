---
phase: 04-data-layer-correct-lean
plan: 07
subsystem: entities
tags: [traefik, tls, cert-coordinator, coordinator-entity, generics, pep695, home-assistant, gap-closure]

requires:
  - phase: 04-06
    provides: "stub_traefik helper, real v3.7 capture, main coordinator with always_update=False"
  - phase: 03
    provides: "CertCoordinator, TLS cert entities, _cert_cache_availability"
provides:
  - "entity.py: private generic base _TraefikProxyBaseEntity[CoordinatorT: DataUpdateCoordinator[Any]]"
  - "entity.py: TraefikProxyEntity (main coordinator, unchanged constructor) and TraefikProxyCertEntity (cert coordinator)"
  - "entity.py: _sw_version reads entry.runtime_data.coordinator.data for every entity"
  - "sensor.py / binary_sensor.py: both cert entity classes are CoordinatorEntity listeners of the cert coordinator (CR-01 closed)"
  - "tests/test_cert_entity_state.py: 8 full-setup HA-state tests (cert cycle, threshold boundary, options, availability, probe count, listener count, sw_version)"
affects: [phase-05-entity-lifecycle, phase-06-certificates, phase-08-changelog]

actuals:
  tokens: 5290
  tasks: 2
  commits: 4
plan_head_before: fd3bd078ec53212114a1d7ab52106d49e474d737
plan_head_after: 90af13a674d61b13304f93befe4bb1bba69ac700

tech-stack:
  added: []
  patterns:
    - "Generic entity base over the coordinator type (PEP 695), one thin subclass per coordinator, no typing cast"
    - "Device info data that belongs to the main snapshot is read through entry.runtime_data, not self.coordinator"
    - "HA-state propagation tests: full setup + coordinator.async_set_updated_data / async_set_update_error + hass.states"

key-files:
  created:
    - tests/test_cert_entity_state.py
  modified:
    - custom_components/traefik_proxy/entity.py
    - custom_components/traefik_proxy/sensor.py
    - custom_components/traefik_proxy/binary_sensor.py
    - tests/test_sensor_tls.py
    - tests/test_binary_sensor_tls_expiring.py

key-decisions:
  - "Cert entities bind to the cert coordinator through TraefikProxyCertEntity(_TraefikProxyBaseEntity[CertCoordinator]); mypy --strict clean without cast (W21)"
  - "Cert entity availability stays _cert_cache_availability(cert_coordinator, host) only; a failed main cycle never blanks a cert alarm (W22)"
  - "Task 2 committed as RED test commit + fix commit instead of one combined commit, to keep the TDD gate visible"
  - "TLS device lookup in tests via dr.async_entries_for_config_entry, because async_get_device raises in the dev HA and async_get_device_by_identifier is not guaranteed on HA 2026.3"

patterns-established:
  - "TraefikProxyCertEntity: any future entity whose state comes from the cert coordinator derives from it"

requirements-completed: [DATA-06]

coverage:
  - id: D1
    description: "Expiring binary sensor re-renders on cert cycles, only for the host whose row changed, and keeps the new state across an unchanged main refresh (CR-01)"
    requirement: DATA-06
    verification:
      - kind: integration
        ref: "tests/test_cert_entity_state.py#test_cert_cycle_updates_expiring_binary_sensor_state"
        status: pass
    human_judgment: false
  - id: D2
    description: "Cert timestamp sensor re-renders on cert cycles with the new not_after; days_until_expiry attribute equals the cache integer"
    requirement: DATA-06
    verification:
      - kind: integration
        ref: "tests/test_cert_entity_state.py#test_cert_cycle_updates_timestamp_sensor_state"
        status: pass
    human_judgment: false
  - id: D3
    description: "Threshold change and tls_warn_days option reach HA state at the exact boundary (== on, one below off, one above on)"
    requirement: DATA-06
    verification:
      - kind: integration
        ref: "tests/test_cert_entity_state.py#test_threshold_change_reaches_state_at_the_boundary"
        status: pass
      - kind: integration
        ref: "tests/test_cert_entity_state.py#test_tls_warn_days_option_reaches_state"
        status: pass
    human_judgment: false
  - id: D4
    description: "Cert entity availability follows only the cert coordinator; CertError row makes that host unavailable"
    requirement: DATA-06
    verification:
      - kind: integration
        ref: "tests/test_cert_entity_state.py#test_cert_availability_follows_cert_coordinator_only"
        status: pass
    human_judgment: false
  - id: D5
    description: "Main cycles never probe certificates; cert notifications do not grow the listener count; TLS device keeps the Traefik sw_version"
    verification:
      - kind: integration
        ref: "tests/test_cert_entity_state.py#test_main_cycles_never_probe_certificates"
        status: pass
      - kind: integration
        ref: "tests/test_cert_entity_state.py#test_cert_notifications_do_not_grow_listeners"
        status: pass
      - kind: integration
        ref: "tests/test_cert_entity_state.py#test_cert_device_keeps_traefik_sw_version"
        status: pass
    human_judgment: false
  - id: D6
    description: "Both cert entity classes have entity.coordinator set to the cert coordinator (unit level)"
    verification:
      - kind: unit
        ref: "tests/test_binary_sensor_tls_expiring.py#test_entity_is_bound_to_cert_coordinator"
        status: pass
      - kind: unit
        ref: "tests/test_sensor_tls.py#test_restore_after_ha_restart_rebinds_existing_entities"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-11-14
status: complete
---

# Phase 4 Plan 07: Cert entities bound to the cert coordinator (CR-01) Summary

**Both TLS certificate entity classes now subscribe to the cert coordinator through a typed `TraefikProxyCertEntity` base, so cert cycles, threshold changes and `tls_warn_days` options reach HA state again while the main coordinator keeps `always_update=False`.**

## Performance

- **Duration:** about 6 min
- **Started:** 2026-11-14T02:08:28Z
- **Completed:** 2026-11-14T02:14:30Z
- **Tasks:** 2 (tracer + expansion)
- **Files modified:** 6 (3 production, 3 test)

## Accomplishments

- `entity.py`: new private generic base `_TraefikProxyBaseEntity[CoordinatorT: DataUpdateCoordinator[Any]]` holding device info, `_url_host`, `_sw_version` and the `_router_name` alias. `TraefikProxyEntity` keeps its public constructor `(entry, category, *, description_key=None)` and binds the main coordinator. The new `TraefikProxyCertEntity(entry, coordinator, category, *, description_key)` binds the given `CertCoordinator`. No cast, no `type: ignore` in entity.py.
- `_sw_version` reads the main snapshot through `self._entry.runtime_data.coordinator.data`, so the "HTTP Routers TLS" device keeps the Traefik version.
- `TraefikProxyCertExpiryBinarySensor` and `TraefikProxyCertTimestampSensor` derive from `TraefikProxyCertEntity`. Constructors, unique_ids, entity_ids, names, platform listeners and `_cert_cache_availability` are unchanged.
- Eight full-setup HA-state tests in `tests/test_cert_entity_state.py` encode the verifier's CR-01 scenario and the DATA-06 probe items (boundary, adjacency, CertError, precision, availability, probe count, listener count, sw_version).

## Measurements (requested by the plan)

- **Cert coordinator listener count:** 6 after setup = 2 platform listeners (`sensor.py` `_cert_update_listener`, `binary_sensor.py` `_on_cert_update`) + 4 entity listeners (2 hosts x 2 classes). Unchanged after three `async_set_updated_data` calls and one `async_set_threshold` call. During Task 2's RED run, before the timestamp sensor was rebound, the count was 4.
- **TLS probe calls:** 2 after setup (two v3.7 TLS hosts). Still 2 after three main refreshes, the last one with a changed rawdata payload that adds a new TLS router `extra@file` (`Host(\`extra.example.com\`)`).

## Task Commits

1. **Task 1 (tracer): cert cycle -> expiring binary sensor -> HA state**
   - RED `a845757` test(04-07): add failing cert state propagation test
   - GREEN `7125643` fix(04-07): bind cert expiry binary sensor to the cert coordinator
   - Tracer gate (auto mode): `<verify>` re-run after the commit passed; continued with expansion.
2. **Task 2: timestamp sensor binding + HA-state expansion**
   - RED `b27b92c` test(04-07): add failing HA-state tests for cert timestamp sensor and cert paths
   - GREEN `90af13a` fix(04-07): bind cert timestamp sensor to the cert coordinator and prove HA state propagation

## TDD Gate Compliance

- **RED 1** (`a845757`): `test_cert_cycle_updates_expiring_binary_sensor_state` failed with `AssertionError: assert 'off' == 'on'` after the 3-day cert update. Classifier: `RED_EVIDENCE_OK` (JUnit report via `pytest --junitxml`). Semantic assessment: the target test ran, setup succeeded, the initial `off`/30-day assertions passed, and it failed on the planned assertion (state after the cert cycle). That is the CR-01 reproduction.
- **RED 2** (`b27b92c`): `test_cert_cycle_updates_timestamp_sensor_state` failed because the state kept the old `not_after` (2026-12-01 instead of 2026-11-04). Classifier: `RED_EVIDENCE_OK`. Semantic assessment: it failed on the planned assertion. The availability, listener-count (4 instead of 6) and `entity.coordinator is cert_coord` tests failed for the same reason. The threshold, options, probe-count and sw_version tests already passed at that point. That was expected: the binary sensor was rebound in Task 1, and the sw_version test is a guard.
- **GREEN commits use `fix(04-07):`**, as the plan prescribes for a gap-closure bug fix, not `feat(04-07):`. A grep-based gate that only looks for `feat(` will not find them. The RED -> GREEN order is intact for both tasks.
- No REFACTOR commit was needed.

## Files Created/Modified

- `custom_components/traefik_proxy/entity.py`: generic base, `TraefikProxyEntity`, `TraefikProxyCertEntity`, `_sw_version` source
- `custom_components/traefik_proxy/binary_sensor.py`: base class and `super().__init__` of `TraefikProxyCertExpiryBinarySensor`
- `custom_components/traefik_proxy/sensor.py`: base class and `super().__init__` of `TraefikProxyCertTimestampSensor`
- `tests/test_cert_entity_state.py` (new): 8 HA-state tests, `cert_probe_ok` fixture, `_setup`, `_cert`, `_state` helpers
- `tests/test_sensor_tls.py`: binding assertion now `entity.coordinator is cert_coord`
- `tests/test_binary_sensor_tls_expiring.py`: new `test_entity_is_bound_to_cert_coordinator`

## Gate Results

- `.venv/bin/pytest -q`: 490 passed
- `.venv/bin/ruff check custom_components tests`: all checks passed
- `.venv/bin/ruff format --check custom_components tests`: 33 files already formatted
- `.venv/bin/mypy --strict custom_components` (and `custom_components/traefik_proxy`): no issues in 13 source files
- HA 2026.3.0 venv `~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`: 490 passed
- Acceptance greps: `class TraefikProxyCertEntity` 1, `TraefikProxyCertExpiryBinarySensor(TraefikProxyCertEntity` 1, `TraefikProxyCertTimestampSensor(TraefikProxyCertEntity` 1, `runtime_data.coordinator.data` in entity.py 1, no `cast(`/`type: ignore` in entity.py, `always_update=False` 1, `(TraefikProxyEntity,` class count 7, `async_add_entities(` 2 + 2, test count 8, PASSED count 8, `entity.coordinator is cert_coord` 1

## Decisions Made

- The plan's decisions (generic base, availability on the cert coordinator only, sw_version from the main snapshot, keeping `self._coordinator`) were implemented as written. Worker decisions are listed below.

## Worker Decisions

- Task 2 committed as RED + fix (two commits) instead of one combined commit. Reason: keeps TDD discipline visible for a `tdd="true"` task. Alternative: one `fix(04-07)` commit as in the plan's action step 5.
- TLS device lookup in `test_cert_device_keeps_traefik_sw_version` via `dr.async_entries_for_config_entry` + identifier filter. Reason: `DeviceRegistry.async_get_device` raises a deprecation `RuntimeError` in the dev HA, and `async_get_device_by_identifier` is not guaranteed on HA 2026.3. Alternative: version-dependent lookup.
- The changed rawdata payload in `test_main_cycles_never_probe_certificates` adds a new TLS router with a new host, not just a status change. Reason: the strongest form of "a main cycle never probes", because even a new probe target waits for the cert cycle. Alternative: change only a router status.
- RED evidence captured as a pytest JUnit XML report (`--junitxml`) for the `tdd-red-evidence` classifier. Reason: the classifier has no pytest console adapter. Records were kept in the session scratchpad, not committed. Alternative: semantic assessment only.
- `TraefikProxyCertEntity.__init__` makes `description_key: str` a required keyword with no default. Reason: every cert entity is per-host, and the plan's signature `*, description_key` has no default. Alternative: `str | None = None` like the main base.
- The listener count is asserted as exactly 6 (2 platform + 4 entity), not only "unchanged". Reason: it also proves both classes subscribe. Alternative: assert only stability.
- DATA-06 marked complete in REQUIREMENTS.md through `requirements.ready-ids` (reported ready; no sibling plan declares it in frontmatter). Reason: executor protocol. Alternative: leave it to the phase re-verification (see the earlier revert in 2d6f513).

## User-visible changes (Phase 8 CHANGELOG)

- Calling `homeassistant.update_entity` on a certificate entity (`sensor.traefik_<host>_cert`, `binary_sensor.traefik_<host>_expiring`) now requests a cert-coordinator refresh, i.e. TLS probes of the router hostnames (debounced, Semaphore(4), 5 s timeout), instead of a Traefik API refresh. This is accepted threat T-04-18; no test covers it, by design.
- Certificate entities update again as soon as a cert cycle or a `tls_warn_days` change happens (regression from the Phase 4 `always_update=False` change, fixed before release).

## Deviations from Plan

None in production code. The plan was executed as written. The extra RED commit for Task 2 and the device lookup variant are listed under Worker Decisions.

## Issues Encountered

- The first attempt at the device test used `dr.async_get(hass).async_get_device(...)`, which raised the HA deprecation `RuntimeError` (`MissingIntegrationFrame`). It was replaced by the config-entry lookup before the RED commit.
- The existing cert re-add listeners still log "does not generate unique IDs" on every cert notification (WR-05). This is unchanged, deferred to Phase 5 (M28), and does not grow the listener count.

## Known Stubs

None.

## Threat Flags

None. The only new surface, `update_entity` on a cert entity triggering a cert refresh, is already in the plan's threat model as T-04-18 (accepted).

## User Setup Required

None. No external service configuration required.

## Next Phase Readiness

- CR-01 (VERIFICATION gap 1, ROADMAP Phase 4 SC5) is closed. Ready for 04-08 and 04-09, then phase re-verification.
- Phase 5's entity manager can build on `TraefikProxyCertEntity` and replace the re-add listeners (WR-05).

## Self-Check: PASSED

- FOUND custom_components/traefik_proxy/entity.py, tests/test_cert_entity_state.py
- FOUND commits a845757, 7125643, b27b92c, 90af13a (ancestors of HEAD)

---
*Phase: 04-data-layer-correct-lean*
*Completed: 2026-11-14*
