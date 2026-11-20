---
phase: "05"
slug: "entity-model-lifecycle"
status: secured
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
block_on: high
created: "2026-11-15"
---

# Phase 05 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time (05-01..05-08 `<threat_model>` blocks); verified by gsd-security-auditor at HEAD 8c0ec05.
> Paths: `cc/` = `custom_components/traefik_proxy/`.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Traefik API → integration | Router/service/cert names and status from the user's Traefik (untrusted input shaping entities) | Item names, status, server URLs (internal) |
| Integration → HA registries / `.storage` | Entity/device registry writes, deletions, missing-since Store | Unique IDs, router names, timestamps |
| Upgrade path → user's registry and devices | 0.3.0 → 1.2 migration and legacy device cleanup delete and recreate persisted user-facing objects | disabled_by / hidden_by / entity_id customisations |
| HA UI → integration | Refresh button, options | Button press, options values |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-05-01 | Tampering | entity_manager.py deletion path (short paginated read, empty or failed snapshot) | high | mitigate | Removal only after 24 h grace (cc/entity_manager.py:239, :318; cc/const.py:33); failed cycle returns early (:286); empty snapshot only marks missing (:296-301); tests in tests/test_entity_manager.py (:381, :408, :443, :500, :520, :538) | closed |
| T-05-02 | Information disclosure | entity.py `dashboard_url` / `entry_host` | medium | mitigate | Netloc rebuilt from hostname+port, userinfo/query/fragment dropped (cc/entity.py:53-79); test_dashboard_url_variants, test_entry_host_falls_back_to_title | closed |
| T-05-03 | Denial of service | Entity creation driven by Traefik item names | medium | mitigate | Known-key set, `present - known` (cc/entity_manager.py:244-246, :290-293); `@internal` dropped (cc/models.py:250-252); tests :288, test_internal_routers_are_dropped | closed |
| T-05-04 | Information disclosure | Missing-since Store in `.storage` | low | accept | AR-05-01; Store deleted in `async_remove_entry` (cc/__init__.py:312) | closed |
| T-05-05 | Information disclosure | sensor.py service attributes | medium | mitigate | Fixed six-key attribute set (cc/sensor.py:249-261); test_service_sensor_attributes_are_private on v2.11 + v3.7 captures | closed |
| T-05-06 | Denial of service | binary_sensor.py `problems` attribute | low | mitigate | Capped at `MAX_PROBLEM_NAMES = 50` + `problem_count` (cc/binary_sensor.py:113-115); test_problem_names_capped_at_fifty | closed |
| T-05-07 | Denial of service | State-write volume of aggregates / diagnostics | low | mitigate | Write-on-change token (cc/entity.py:231-248); `always_update=False` (cc/coordinator.py:109); zero-write tests | closed |
| T-05-08 | Denial of service | Entity explosion on large installs | medium | mitigate | Per-item option: kinds not registered, entries purged, sub-devices via reference guard (cc/sensor.py:145-159; cc/__init__.py:266-269; cc/entity.py:124-130); per_item tests. UI field deferred to Phase 7 (W36) | closed |
| T-05-09 | Elevation of privilege | Refresh button acting on another entry / admin-only service bypass | medium | mitigate | `async_press` uses only its own `runtime_data` (cc/button.py:39-43); no service registered; test_press_refreshes_only_own_entry, test_no_service_registered | closed |
| T-05-10 | Denial of service | Repeated presses causing TLS-probe bursts | low | mitigate | `PARALLEL_UPDATES = 1`; HA default refresh debouncer; TLS semaphore 4 + 5 s timeout (cc/cert_coordinator.py:117, :145, :147) | closed |
| T-05-11 | Tampering | Mutating requests against Traefik | medium | mitigate | Only `session.get` (cc/api.py:185); test_only_get_requests_reach_traefik asserts `{GET}` | closed |
| T-05-12 | Repudiation | ERROR log noise per cert cycle (WR-05) | low | mitigate | Cert kinds through the manager's known set; test_known_cert_hosts_are_never_added_again | closed |
| T-05-13 | Tampering | `async_migrate_entry` (__init__.py) | high | mitigate | Scoped to this entry's registry entries; removes only router binary sensors + reload button; clears only INTEGRATION on aggregates; DEVICE→USER for survivors on disabled legacy devices (review fix CR-02); downgrade refused; test_migration_from_1_1, test_migration_is_idempotent, test_device_disabled_* | closed |
| T-05-14 | Information disclosure | Repair issue placeholders and texts | low | mitigate | Placeholders `{entry_title, removed_count}` only (cc/__init__.py:156); no URL/host/token in en/de texts | closed |
| T-05-15 | Tampering | `async_remove_legacy_devices` (entity.py) | medium | mitigate | Runs after platform forwarding; this entry only; exactly one legacy identifier, no current identifier; removal only via unreferenced guard (cc/entity.py:82-96, :158-185); tests in tests/test_devices.py (:88, :155, :177) | closed |
| T-05-16 | Tampering | Downgrade / unknown future entry version | low | mitigate | `entry.version > 1 → False` before registry access (cc/__init__.py:84-91); test_downgrade_fails_and_keeps_registry | closed |
| T-05-17 | Tampering | Migration replacement creation (`__init__.py`) | high | mitigate | Disabled/hidden router replacements created with mapped `disabled_by` (USER→USER, DEVICE→USER, INTEGRATION kept) and `hidden_by` (cc/__init__.py:56-60, :106-145); tests in tests/test_migration.py (:301, :348-402, :413, :458) | closed |
| T-05-18 | Denial of service | Options update listener (`__init__.py`) | medium | mitigate | `entry.async_on_unload(entry.add_update_listener(...))` (cc/__init__.py:285); test_update_listener_registered_once_across_reloads | closed |
| T-05-19 | Tampering | Per-item-off sub-device removal (`entity.py`) | medium | mitigate | Single `async_remove_device` call inside `_async_remove_device_if_unreferenced` (cc/entity.py:82-96); test_per_item_off_keeps_referenced_sub_device | closed |
| T-05-20 | Information disclosure | Replacement entity_ids and migration debug log | low | accept | AR-05-02 | closed |
| T-05-SC | Tampering | npm/pip/cargo installs | low | accept | AR-05-03 | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

Review fixes mapped to the register: CR-01 → T-05-17, CR-02 → T-05-13, WR-01 → T-05-18, WR-02 → T-05-19, IN-05 → T-05-17.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-05-01 | T-05-04 | Missing-since Store holds router names and timestamps at the same trust level as the entity registry; deleted in `async_remove_entry` (cc/__init__.py:312) | Plan threat model (05-02), verified by security audit | 2026-11-15 |
| AR-05-02 | T-05-20 | Replacement entity_id seed is the old object id (no secret); migration debug line carries only entry_id and counts (cc/__init__.py:158-163) | Plan threat model (05-08), verified by security audit | 2026-11-15 |
| AR-05-03 | T-05-SC | No package installs or dependency changes (pyproject.toml, uv.lock, manifest.json, hacs.json unchanged c77655c..8c0ec05; `requirements: []`) | Plan threat model (all plans), verified by security audit | 2026-11-15 |

*Accepted risks do not resurface in future audit runs.*

### Observations (informational, non-blocking)

1. T-05-08: the per-item opt-out has no options-flow field yet (IN-04, Phase 7 W36); reachable only by editing entry options until then.
2. T-05-13: the CR-02 DEVICE→USER step also hardens a stale DEVICE disabler on an enabled legacy device (IN-07, info); errs on the safe side (never enables).
3. T-05-17: the CONFIG_ENTRY disabler is excluded from the mapping by design and not parametrized in tests.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-15 | 21 (T-05-01..T-05-20, T-05-SC) | 21 | 0 | gsd-security-auditor (ASVS L1; named tests at 8c0ec05: 77 passed on HA 2026.10.4, 119 passed on HA 2026.3.0) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
