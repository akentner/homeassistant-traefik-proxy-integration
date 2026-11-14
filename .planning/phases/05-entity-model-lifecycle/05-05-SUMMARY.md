---
phase: 05-entity-model-lifecycle
plan: 05
subsystem: entities
tags: [home-assistant, entity-manager, certificates, write-on-change, translations, traefik]
status: complete

requires:
  - phase: 05-entity-model-lifecycle
    provides: "05-01 TraefikEntityManager/KindSpec incl. CERT_EXPIRY/CERT_EXPIRING, _TraefikEntityBase write-on-change, device topology; 05-02 grace period (Store, deadline timer, orphan adoption); 05-04 per-item option (does not gate cert kinds)"
provides:
  - "entity.py: TraefikCertEntity (cert coordinator, Certificates sub-device, _row/_info/_error, availability from cert cycle + CertInfo row, token (row,), {host} placeholder) and cert_hosts(coordinator)"
  - "sensor.py: TraefikCertExpirySensor (timestamp, translation_key certificate_expiry) registered as the CERT_EXPIRY kind"
  - "binary_sensor.py: TraefikCertExpiringBinarySensor (problem, translation_key certificate_expiring, token (row, threshold_days)) registered as the CERT_EXPIRING kind"
  - "translations: entity.sensor.certificate_expiry.name '{host} expiry', entity.binary_sensor.certificate_expiring.name '{host} expiring' (strings.json identical)"
affects: [05-06, 05-07, phase-06-certificates, phase-08-changelog]

actuals:
  tokens: 22800
  tasks: 1
  commits: 2
plan_head_before: d9264b434be71faac897212ea0326bae87074d70
plan_head_after: 2795b8c176824cb40a77262f5b0a9f58bf50217b

tech-stack:
  added: []
  patterns:
    - "Certificate entities are a manager kind keyed by the lowercase hosts of the cert data; the kind listener sits on the cert coordinator"
    - "Cert entity availability = cert cycle succeeded AND host row is a CertInfo; missing hosts are simply unavailable (no missing state)"
    - "Per-item names through translation_key + translation placeholders instead of _attr_name"

key-files:
  created: []
  modified:
    - custom_components/traefik_proxy/entity.py
    - custom_components/traefik_proxy/sensor.py
    - custom_components/traefik_proxy/binary_sensor.py
    - custom_components/traefik_proxy/translations/en.json
    - custom_components/traefik_proxy/strings.json
    - tests/test_sensor_tls.py
    - tests/test_binary_sensor_tls_expiring.py
    - tests/test_cert_entity_state.py
    - tests/test_entity_manager.py

key-decisions:
  - "Both cert kinds key on every host in the cert data (CertInfo and CertError rows) - plan decision (W39)"
  - "Cert names via translation_key + {host} placeholder ('{host} expiry' / '{host} expiring') - plan decision"

requirements-completed: []

coverage:
  - id: D1
    description: "Known cert hosts are never added again: three cert cycles, a threshold change and a tls_warn_days options change log no 'does not generate unique IDs' and keep 6 cert-coordinator listeners (WR-05)"
    requirement: ENT-01
    verification: "tests/test_cert_entity_state.py::test_known_cert_hosts_are_never_added_again, ::test_cert_notifications_do_not_grow_listeners"
  - id: D2
    description: "A cert host that leaves the router set is unavailable with its registry entries kept, removed 24 h + 1 s later"
    requirement: ENT-01
    verification: "tests/test_cert_entity_state.py::test_vanished_cert_host_unavailable_then_removed_after_grace"
  - id: D3
    description: "An unchanged cert notification writes nothing (last_reported of all four cert entities unchanged); token follows row and threshold"
    requirement: ENT-02
    verification: "tests/test_cert_entity_state.py::test_unchanged_cert_notification_writes_nothing, tests/test_binary_sensor_tls_expiring.py::test_state_token_follows_row_and_threshold"
  - id: D4
    description: "Cert entities on the Certificates sub-device (via_device_id = main), main sw_version = snapshot version, D-09 unique_ids kept"
    requirement: ENT-03
    verification: "tests/test_cert_entity_state.py::test_cert_entities_on_certificates_sub_device"
  - id: D5
    description: "No explicit entity_id, translated names with {host} placeholder, no icon, no coordinator alias"
    requirement: ENT-08
    verification: "tests/test_sensor_tls.py::test_identity_and_device, tests/test_binary_sensor_tls_expiring.py::test_identity_and_device"

duration: 7min
completed: 2026-11-14
---

# Phase 5 Plan 05: Certificate entities on TraefikCertEntity through the entity manager Summary

**Certificate timestamp and expiring sensors are now entity-manager kinds on a cert-coordinator base. Known hosts are added once (no more "does not generate unique IDs" errors on cert cycles, threshold or options changes), vanished hosts get the 24 h grace period, states are written only on change, and they sit on the Certificates sub-device with translated `{host}` names.**

## Performance

- **Duration:** about 7 min
- **Started:** 2026-11-14T21:32:28Z
- **Completed:** 2026-11-14T21:38:46Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 9

## Accomplishments

- `TraefikCertEntity` in `entity.py`. It is bound to `entry.runtime_data.cert_coordinator`, uses `_traefik_device = CERTIFICATES` and gets its unique_id from `_spec.unique_id`. It holds only the lowercase host. `_row()`, `_info()` and `_error()` read through `self.coordinator`. It is available only when the cert cycle succeeded and the row is a `CertInfo` (W22, D-03). Its token is `(row,)`. W23 still holds: `update_entity` uses the inherited `CoordinatorEntity.async_update`, so it requests a cert refresh.
- `TraefikCertExpirySensor` and `TraefikCertExpiringBinarySensor` keep today's values and attribute keys. The expiring sensor reads `coordinator.threshold_days` and its token is `(row, threshold_days)`, so a threshold change triggers a write.
- Both kinds are registered without the per-item gate. Their keys are `cert_hosts(cert_coordinator)`, which includes hosts whose probe failed.
- Removed: both create/cleanup closure pairs (the last two global `registry.entities` scans), `_cert_cache_availability` and its public alias, the `_coordinator` alias, explicit entity_ids, `_attr_icon`, and the now-unused imports (`er`, `slugify`, `cast`, `is_error`, `logging`).
- WR-05 is fixed: an options change no longer logs duplicate unique-ID errors for `tls_expiring_` entities. The 05-04 orchestrator note is covered by `test_known_cert_hosts_are_never_added_again`, which includes a `tls_warn_days` options change.
- **IN-11 is closed.** The redundant `_coordinator` alias is gone from all cert entities, and `grep "self\._coordinator\b"` finds nothing. The Phase 8 carry-over can be dropped.

## Task Commits

1. **Task 1 RED: failing tests for cert entities on the entity manager** - `0777d99` (test, strict xfail)
2. **Task 1 GREEN: certificate entities on TraefikCertEntity through the entity manager** - `2795b8c` (feat)

## Verification (end of plan)

- `uv run pytest -q`: 549 passed. The baseline was 550: two tests were deleted and one net test was added. The deleted ones are the restore re-bind test (by plan) and the per-category TLS device test, which is replaced by the sub-device test. The unit test files were rebuilt.
- HA 2026.3.0 venv (`~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`): 549 passed
- `uv run ruff check custom_components tests`: all checks passed. `ruff format --check`: 35 files already formatted
- `uv run mypy --strict custom_components/traefik_proxy`: no issues in 14 source files
- Acceptance greps: all pass. Zero hits for `registry.entities`, `_create_pending_cert|_remove_stale`, `cert_cache_availability`, `self._coordinator`, `_attr_icon` and `slugify`. There is no `def available` or `self.entity_id =` in sensor.py or binary_sensor.py, and the restore test is gone. `class TraefikCertEntity` appears once. `cmp strings.json en.json` reports identical files. `pytest -k per_item`: 4 passed.
- Key links: `grep -Pzo 'async_add_kind\(\s*CERT_EXPIRY'` matches in sensor.py and `CERT_EXPIRING` matches in binary_sensor.py. The match spans lines because of ruff formatting, as in 05-01.
- Probe run (not committed): on a fresh install the entity_ids are `sensor.traefik_certificates_traefik_example_com_secure_example_com_expiry` and `binary_sensor.traefik_certificates_traefik_example_com_secure_example_com_expiring`. The friendly name is "Traefik certificates (traefik.example.com) secure.example.com expiry". Apart from HA's standard "custom integration not tested" message, nothing is logged at WARNING or ERROR.

## TDD Gate Compliance

- RED: `0777d99`. The evidence is a pytest `--junitxml` run with `--runxfail`, checked with `gsd-tools check tdd-red-evidence`. Verdict: `RED_EVIDENCE_OK`, reason `target_test_failed`, with target `test_known_cert_hosts_are_never_added_again` (4 failed, 8 passed).
- Semantic assessment: every target failed on its planned assertion.
  - WR-05 test: caplog contained "does not generate unique IDs" for `tls_expiring_secure.example.com`.
  - Grace test: the stale cleanup had already deleted the www host's entity.
  - Write test: `last_reported` moved by 1 s.
  - Device test: the Certificates device was not the entities' device.
- The RED commit marks the 4 new tests `xfail(strict=True)`, so the commit stays green. GREEN `2795b8c` removes the markers.
- REFACTOR: none needed. The RED evidence files were deleted after classification and not committed, following 05-01.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Stale test comment] `tests/test_entity_manager.py` per-item helper**
- **Found during:** Task 1 GREEN
- **Issue:** `_assert_per_item_off` said only the expiring sensor exists for an error host. After W39 that is false.
- **Fix:** Rewrote the comment and added an assertion that the CERT_EXPIRY keys equal the CERT_EXPIRING keys, which proves D-06 for both cert kinds. The file is not in `files_modified`, but the plan requires the per-item tests to keep passing.
- **Commit:** 2795b8c

Otherwise the plan was executed as written.

## Worker Decisions

- `cert_hosts(coordinator)` is a public helper in `entity.py` that both platforms use. Reason: one key source for both kinds, so the sensor and binary sensor always cover the same hosts. Alternative: a lambda in each platform.
- `TraefikCertEntity` narrows with `isinstance(row, CertInfo)` and adds an `_error()` accessor instead of using `is_error` + `cast`. Reason: mypy narrows `CertInfo` / `CertError` without a cast. Valid cert data behaves the same. Alternative: keep `is_error` + `cast`.
- `_row()` reads `(self.coordinator.data or {})`. Reason: unit tests and a coordinator before its first data never raise. Setup always seeds a dict. Alternative: no guard.
- After a failed cert cycle `native_value` still returns the cached `not_after`, and the unit test checks only `available is False`. Reason: this is today's semantics, which the plan says to keep. HA shows "unavailable" regardless of the value. Alternative: return None whenever the entity is unavailable.
- The expiring sensor's attribute `threshold_days` reads `coordinator.threshold_days`, not `get_threshold()`. Reason: the plan names `threshold_days`, and it is the same value. Alternative: keep `get_threshold()`.
- `_attr_entity_registry_enabled_default = True` stays explicit on the expiring sensor. Reason: it documents the security-alarm default. Alternative: rely on HA's default.
- The binary_sensor `async_setup_entry` is now typed (`HomeAssistant`, `AddConfigEntryEntitiesCallback`) instead of `Any`. Reason: `async_add_kind` expects the callback type. Alternative: keep `Any`.
- The old `TraefikProxyCertEntity` base stays in `entity.py` without users. Reason: 05-07 deletes the old bases, and its grep gate covers it. Alternative: delete it now.
- The en.json rewrite keeps the `—` escapes (`ensure_ascii=True`). Reason: the diff stays at the two new keys. Alternative: literal characters, which would rewrite 8 lines.
- The new tests include extra cases: signed boundaries 15/14 and 0/0, host lowercasing, a no-alias check, and empty cert data. Reason: they cover the ENT-08/IN-11 truths and the threshold token directly. Alternative: only the plan's behavior lines.

## User-visible changes (Phase 8 CHANGELOG)

- Certificate entities are renamed. They are now "`<host>` expiry" (timestamp) and "`<host>` expiring" (problem) on the device "Traefik certificates (`<traefik host>`)". New installs get entity_ids derived from those names, for example `sensor.traefik_certificates_<traefik_host>_<host>_expiry`. Existing installs keep their registry entity_ids because the unique_ids are unchanged.
- There is now a timestamp sensor for every probed host, including hosts whose probe fails. It is unavailable while there is no certificate (Phase 6 changes this to problem-on).
- A host that disappears from the routers is no longer deleted right away. Its certificate entities are unavailable for up to 24 h before they are removed, and they come back unchanged if the host returns.
- No more "does not generate unique IDs" errors in the HA log on certificate cycles, threshold changes or options changes.
- Certificate entities no longer have hard-coded icons (icons.json follows in 05-07).

## Known Stubs

None.

## Issues Encountered

- None. Carry-over: IN-11 is closed here. WR-05 is closed for certificates (routers/services were closed in 05-01..05-03).

## Next Phase Readiness

- 05-06 can replace the reload button. After this plan it is the only entity left on the old per-category base.
- 05-07 can delete `_TraefikProxyBaseEntity`, `TraefikProxyEntity`, `TraefikProxyCertEntity` and the category table. It can also remove the legacy `http_routers_tls` device, which now holds no entities after a fresh setup.

## Self-Check: PASSED

- FOUND: all nine modified files
- FOUND commits: 0777d99, 2795b8c (ancestors of HEAD)
