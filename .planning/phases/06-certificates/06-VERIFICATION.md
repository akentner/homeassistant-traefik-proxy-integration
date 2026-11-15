---
phase: 06-certificates
verified: 2026-11-15T09:49:14Z
status: passed
score: 9/9 must-haves verified
covered_files:
  - .planning/phases/06-certificates/06-01-PLAN.md
  - .planning/phases/06-certificates/06-01-SUMMARY.md
  - .planning/phases/06-certificates/06-02-PLAN.md
  - .planning/phases/06-certificates/06-02-SUMMARY.md
  - .planning/phases/06-certificates/06-03-PLAN.md
  - .planning/phases/06-certificates/06-03-SUMMARY.md
  - .planning/phases/06-certificates/06-04-PLAN.md
  - .planning/phases/06-certificates/06-04-SUMMARY.md
  - .planning/phases/06-certificates/06-05-PLAN.md
  - .planning/phases/06-certificates/06-05-SUMMARY.md
  - .planning/phases/06-certificates/06-06-PLAN.md
  - .planning/phases/06-certificates/06-06-SUMMARY.md
  - .planning/phases/06-certificates/06-07-PLAN.md
  - .planning/phases/06-certificates/06-07-SUMMARY.md
  - custom_components/traefik_proxy/__init__.py
  - custom_components/traefik_proxy/api.py
  - custom_components/traefik_proxy/binary_sensor.py
  - custom_components/traefik_proxy/cert_coordinator.py
  - custom_components/traefik_proxy/const.py
  - custom_components/traefik_proxy/entity.py
  - custom_components/traefik_proxy/entity_manager.py
  - custom_components/traefik_proxy/icons.json
  - custom_components/traefik_proxy/models.py
  - custom_components/traefik_proxy/rules.py
  - custom_components/traefik_proxy/sensor.py
  - custom_components/traefik_proxy/strings.json
  - custom_components/traefik_proxy/tls.py
  - custom_components/traefik_proxy/translations/de.json
  - custom_components/traefik_proxy/translations/en.json
  - tests/certgen.py
  - tests/conftest.py
  - tests/test_cert_coordinator.py
  - tests/test_cert_entity_state.py
  - tests/test_cert_lifecycle.py
  - tests/test_certificates_problem.py
  - tests/test_rules.py
  - tests/test_tls.py
covered_digest: "v4:sha256:792dc6ee0e457d4407ba21ef5f5f18791348505359bab4be57121d471c76bfbc"
behavior_unverified: 0
overrides_applied: 0
deferred:
  - truth: "Visual check of the certificate entities, certificates_problem aggregate and reason texts (de/en) in a real Home Assistant UI"
    addressed_in: "Phase 8"
    evidence: "Decision log M35 / carry-over Phase 8: 'visueller Check (M35)' in a throwaway HA 2026.11; U2: no real HA instance"
coincidental_reliance_items:
  - truth: "A cert cycle that finishes after unload arms no day-boundary timer (WR-02)"
    reason: undeclared-precondition
    harden: "CertCoordinator._async_schedule_day_boundary reads the private HA attribute DataUpdateCoordinator._shutdown_requested (present in HA 2026.3.0 and 2026.10.4, test-covered on both). Nothing in the public API guarantees it; keep test_cycle_finishing_after_shutdown_schedules_no_day_boundary in the 2026.11 minimum-version job (Phase 7, I1) or track shutdown with an own flag set in async_shutdown()."
---

# Phase 6: Certificates Verification Report

**Phase Goal:** Users see correct expiry data for the certificates Traefik actually serves — including expired, self-signed and private-CA certificates — sourced from `GET /api/certificates` on Traefik >= 3.7 and otherwise from a threadless async probe against the Traefik host with SNI; an expired or unprobeable certificate is reported as a problem, never as "unavailable".
**Verified:** 2026-11-15T09:49:14Z
**Status:** passed
**Re-verification:** No — initial verification (after code-review fixes CR-01, WR-01..WR-04)

## Goal Achievement

### Observable Truths

Roadmap success criteria SC1–SC4 are the contract; the plan must-haves (06-01..06-07, ~75 truths) are merged under them. Every row was checked against the source and against a named passing test (full suite run once by the verifier: 851 passed on HA 2026.10.4 and 851 passed on the HA 2026.3.0 venv).

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | SC1: v3.7 fixture → cert coordinator reads `/api/certificates`, no probing, `source=api`; v2.11 (404) → probe; cert entities subscribed to the cert coordinator and managed by the Phase 5 entity manager | ✓ VERIFIED | `cert_coordinator.py:287-305` (`async_get_certificates`, `TraefikProxyNotFoundError` → `_async_probe_states`, other `TraefikProxyApiError` → `UpdateFailed`); `_api_states` never probes, uncovered host → `not_found`. `sensor.py:172-179`, `binary_sensor.py:96-103` register cert kinds with `coordinator=cert_coordinator` via `entity_manager.async_add_kind`. Tests: `test_v37_api_setup_publishes_api_state_without_probing` (probe call_count 0 over setup + 2 cycles, source api, days 88), `test_v211_certificates_404_probes_and_re_requests_each_cycle`, `test_api_uncovered_host_is_not_found_and_not_probed`, `test_certificates_error_fails_the_cycle_without_probe`, `test_v37_api_status_field_never_changes_the_state` |
| 2 | SC2: probe uses `asyncio.open_connection` (no to_thread/executor call), one shared `CERT_NONE` `SSLContext`, `getpeercert(binary_form=True)`, DER parse via `cryptography`; connects to the entry-URL host on the TLS entrypoint port with `server_hostname=<router host>` | ✓ VERIFIED | `tls.py:79-81` module-level `_PROBE_CONTEXT` (PROTOCOL_TLS_CLIENT, check_hostname False, CERT_NONE, no CA load); `tls.py:242-252` open_connection under `asyncio.timeout`, writer closed on every path (`_close_writer` aborts on hang/cancel); `tls.py:110-139` `load_der_x509_certificate`. `cert_coordinator.py:346-352` connect host = `urlsplit(entry URL).hostname`; `_probe_ports` resolves entrypoint addresses, 443 preferred, lowest else, fallback 443. Grep gate clean (no to_thread/run_in_executor/create_connection/load_default_certs/load_verify_locations/create_default_context). Tests: `test_end_to_end_probe_reaches_tls_entrypoint_port[trusted/untrusted]` (real handshake, 127.0.0.1 on websecure port, SNI = router host), `test_probe_connects_to_traefik_host_with_router_host_as_sni`, `test_probe_ports`, `test_probe_modules_use_no_threads_or_blocking_calls`, `test_probe_sends_no_bytes_after_handshake`, `test_cancelled_refresh_closes_connection_and_keeps_data` |
| 3 | SC2: an **expired** and a **self-signed** certificate are both read successfully, `verified=false` where the chain does not validate; private-CA read; trusted chain `verified=true` | ✓ VERIFIED | `tls.py:150-170` `chain_verified` (PolicyBuilder store/time/server_verifier, any VerificationError/ValueError → False); trust anchors from `ha_ssl.client_context().get_ca_certs(binary_form=True)` built once (`cert_coordinator.py:354-364`). Tests with real TLS server + generated certs: `test_probe_expired_leaf_is_read_unverified`, `test_probe_self_signed_leaf_is_read_unverified`, `test_probe_private_ca_not_in_store_is_unverified`, `test_probe_reads_verified_certificate_via_sni`, `test_probe_without_intermediate_is_unverified`, `test_probe_verifies_at_given_time_after_not_after`, `test_probe_ip_san_with_ip_sni_is_verified`, `test_trust_store_defaults_to_ha_roots_built_once`, `test_trust_store_never_built_in_api_mode` |
| 4 | SC3: `rules.extract_hosts()` handles v2 multi-arg `Host(`a`,`b`)`, v3 `\|\|`, skips HostRegexp/HostSNI/HostHeader/negated/wildcard/template; old regex copies gone | ✓ VERIFIED | `rules.py:30` `(?<![A-Za-z0-9_])Host\(` + argument-list parser, `!` negation skip, `normalize_host` (IDNA 2008/UTS-46 after WR-01, charset gate). No `_HOST_FROM_RULE` anywhere in custom_components/tests. Tests: `test_extract_hosts_literal_names`, `test_extract_hosts_skips_non_literal_names`, `test_normalize_host_accepts/rejects`, `test_collect_hosts_skips_regex_sni_and_negated_names`, `test_full_setup_registers_cert_entities_for_alt_host` |
| 5 | SC3: probe set capped at 200 hosts (sorted, one WARNING per cycle, counts only) | ✓ VERIFIED | `const.py:72` `MAX_CERT_HOSTS = 200`; `cert_coordinator.py:523-533`. Tests: `test_cert_cycle_cap_250_probes_200`, `test_cert_cycle_cap_warns_once_per_cycle`, `test_collect_hosts_cap_201_drops_last_sorted`, `test_collect_hosts_cap_not_reached` |
| 6 | SC3: wildcard SAN matching accepts exactly one label (RFC 6125 §6.4.3); API host mapping exact > wildcard, latest not_after | ✓ VERIFIED | `tls.py:272-316` (`rest == candidate[2:]`, non-empty first label, no wildcard for IP literals, partial-label wildcard only by equality). Tests: `test_hostname_matches_san`, `test_hostname_matches_san_wildcard_does_not_match_attacker_suffix`, `test_hostname_matches_san_empty_san_rejects_all`, `test_match_certificate_*` (6 tests) |
| 7 | SC3: TLS error classification distinguishes `ssl` from `oserror`; no module-level dict grows without bound | ✓ VERIFIED | `tls.py:175-190` ordered table TimeoutError → SSLError → gaierror → ConnectionRefusedError → OSError; CancelledError not caught (BaseException). `_parse_log_cooldown` and all old blocking/notAfter-string code removed (grep clean). Tests: `test_probe_plain_http_server_is_ssl_error`, `test_probe_closed_port_is_refused`, `test_probe_hanging_server_is_timeout`, `test_probe_dns_failure_is_dns`, `test_probe_empty_peer_certificate_is_empty`, `test_probe_non_der_peer_certificate_is_parse`, `test_probe_unexpected_exception_is_unknown`, `test_probe_cancelled_error_propagates`, `test_no_module_level_dict[tls/cert_coordinator/rules]`, `test_blocking_probe_path_is_removed` |
| 8 | SC4: `days_left` computed from `not_after` at read time; a threshold crossing / expiry / day change is written at the boundary, not 6 h later | ✓ VERIFIED | `HostCertState.days_left` (`(not_after - now) // DAY`, never stored), entities read `dt_util.utcnow()`; one day-boundary timer via `async_track_point_in_utc_time` re-armed after each cycle and fire, cancelled in `async_shutdown` and suppressed after shutdown (WR-02). Tests (time moved + `async_fire_time_changed`, no probe, no API call): `test_threshold_crossing_without_probe`, `test_expired_at_not_after_without_probe`, `test_daily_countdown_written_once_at_the_boundary`, `test_boundary_writes_only_the_host_that_changed`, `test_unload_cancels_the_boundary_timer`, `test_cycle_finishing_after_shutdown_schedules_no_day_boundary`, `test_days_left_is_signed_floor_days` |
| 9 | SC4: expired or repeatedly unprobeable certificate turns `certificate_expiring` and the `certificates_problem` aggregate (enabled by default) **on** with a `reason`; timestamp sensor keeps last value and stays available; failed first cycle stays failed (D-23) also with the background first cycle (WR-03) | ✓ VERIFIED | `HostCertState.problem` precedence expired > probe_failed (>= 2) > not_found (API-uncovered or, after CR-01, probed cert not covering the host) > expiring; `TraefikCertEntity.available` = cycle ok + data present + host present (failed probe never unavailable); `TraefikCertificatesProblemBinarySensor` uses the same `problem()` (problems capped 50, problem_count all, reasons), enabled by default, PROBLEM class, main device; en/de names + reason state texts, icons. `__init__.py:268` starts first cycle as entry background task; `entity_manager.async_add_kind` treats `data is None` like a failed cycle. Tests: `test_probe_failed_after_two_failed_refreshes` (timestamp keeps value, days 30), `test_failing_probe_keeps_cert_entities_available`, `test_two_failed_probes_turn_the_aggregate_on`, `test_aggregate_agrees_with_per_host_sensors`, `test_names_capped_count_complete`, `test_expiry_reaches_the_aggregate_without_a_probe`, `test_unavailable_when_cert_cycle_failed`, `test_failed_first_cycle_keeps_restored_hosts_unavailable_not_missing`, `test_restored_hosts_reconciled_by_the_next_successful_cycle`, `test_retry_five_minutes_after_a_failed_cycle`, `test_certificate_failure_never_raises_not_ready`, `test_setup_does_not_wait_for_the_first_cert_cycle` (setup < 5 s wall clock with a hanging probe; restored host unavailable and not missing; aggregate unavailable, never a fake "off"; values appear after release), `test_unload_cancels_a_running_first_cert_cycle`, `test_probe_of_default_certificate_is_not_found_problem` |

**Score:** 9/9 truths verified (0 present, behavior-unverified)

All behavior-dependent truths (cancellation keeps `data` and closes the connection; timer cancel on unload; no timer re-arm after shutdown; background first-cycle cancel on unload; no fake success after a failed first cycle) are covered by named tests that ran green in the verifier's own suite run.

### Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | Visual check in a real HA UI (device tree, states/icons, `reason` texts de/en, aggregate) | Phase 8 | Decision log M35 and "Carry-over Phase 8: visueller Check (M35)"; U2 forbids a real HA instance now |

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `custom_components/traefik_proxy/rules.py` | `extract_hosts`, `normalize_host` | ✓ VERIFIED | 108 lines, used by `cert_coordinator._router_hosts` |
| `custom_components/traefik_proxy/tls.py` | async probe, trust store, verification, matching | ✓ VERIFIED | 316 lines, imported by cert_coordinator |
| `custom_components/traefik_proxy/cert_coordinator.py` | API-first cycle, probe mode, HostCertState, timer, retry | ✓ VERIFIED | 548 lines, created in `__init__.py`, bound to entities |
| `custom_components/traefik_proxy/models.py` | `TraefikCertificate`, `parse_certificates` | ✓ VERIFIED | tz-less / unparsable notAfter raise (`test_parse_certificates_shape_errors`) |
| `custom_components/traefik_proxy/api.py` | `async_get_certificates` via `_get_paginated` | ✓ VERIFIED | wraps shape errors into `TraefikProxyPayloadError` |
| `custom_components/traefik_proxy/binary_sensor.py` | expiring sensor + `certificates_problem` aggregate | ✓ VERIFIED | both added in `async_setup_entry` |
| `custom_components/traefik_proxy/sensor.py` | `TraefikCertExpirySensor` with D-16 attributes | ✓ VERIFIED | registered as CERT_EXPIRY kind |
| `custom_components/traefik_proxy/entity.py` | `TraefikCertCoordinatorEntity` / `TraefikCertEntity` availability | ✓ VERIFIED | `available` requires data not None (WR-03) and host present |
| `custom_components/traefik_proxy/const.py` | `MAX_CERT_HOSTS`, `CERT_RETRY_INTERVAL`, `UID_CERTIFICATES_PROBLEM` | ✓ VERIFIED | lines 45, 70, 72 |
| translations en/de, strings.json, icons.json | aggregate name, reason texts, icon | ✓ VERIFIED | "Certificate problems" / "Zertifikatsprobleme"; reason keys = {expired, probe_failed, not_found, expiring} in both; strings.json byte-identical to en.json; icon mdi:lock-alert/lock-check |
| `tests/certgen.py`, `tests/conftest.py` (`tls_server`, stubs, watchdog) | real-TLS test harness, clock-rebased v3.7 stub | ✓ VERIFIED | used by test_tls / test_cert_* |

### Key Link Verification

| From | To | Via | Status |
| --- | --- | --- | --- |
| cert_coordinator.py | rules.py | `_router_hosts` → `extract_hosts`, `normalize_host` | ✓ WIRED |
| cert_coordinator.py | const.py | `MAX_CERT_HOSTS` cut in `_collect_hosts` | ✓ WIRED |
| api.py | models.py | `parse_certificates(_get_paginated('/api/certificates'))` | ✓ WIRED |
| cert_coordinator.py | api.py | `runtime_data.client.async_get_certificates()`; 404 → probe, other → UpdateFailed | ✓ WIRED |
| cert_coordinator.py | tls.py | `async_probe_certificate` under semaphore; `match_certificate`; `build_trust_store` | ✓ WIRED |
| tls.py | cryptography.x509.verification | `PolicyBuilder().store().time().build_server_verifier().verify()` | ✓ WIRED |
| cert_coordinator.py | homeassistant.helpers.event | `async_track_point_in_utc_time(..., _async_handle_day_boundary, ...)` | ✓ WIRED |
| __init__.py | cert_coordinator.py | `entry.async_create_background_task(hass, cert_coordinator.async_refresh(), ...)` | ✓ WIRED |
| binary_sensor.py | cert_coordinator.py | expiring sensor + aggregate both call `HostCertState.problem(threshold, utcnow())` | ✓ WIRED |
| sensor.py / binary_sensor.py | entity_manager.py | `async_add_kind(CERT_EXPIRY/CERT_EXPIRING, coordinator=cert_coordinator)` | ✓ WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| `TraefikCertExpirySensor.native_value` | `HostCertState.certificate.not_after` | `/api/certificates` (parse) or DER from TLS handshake | Yes (real handshake e2e test; fixture-driven API test) | ✓ FLOWING |
| `TraefikCertExpiringBinarySensor.is_on/reason` | `HostCertState.problem(threshold, now)` | cert coordinator data + live clock | Yes | ✓ FLOWING |
| `TraefikCertificatesProblemBinarySensor` | `_problems()` over `cert_coordinator.data` | same `problem()` | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Full suite, HA 2026.10.4 (run once) | `uv run pytest -q -rA` | 851 passed | ✓ PASS |
| Full suite, HA 2026.3.0 minimum venv | `~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests` | 851 passed | ✓ PASS |
| Lint / format | `uv run ruff check custom_components tests`; `ruff format --check` | All checks passed; 43 files formatted | ✓ PASS |
| Types | `uv run mypy --strict custom_components/traefik_proxy` | no issues in 15 source files | ✓ PASS |
| Translations / icons | python json check | en/de keys match, strings.json == en.json, icon present | ✓ PASS |
| Prohibition grep gates | grep for thread/executor/CA-loading calls, old regex/types, module dicts | no matches | ✓ PASS |

### Probe Execution

Step 7c: not applicable — no `scripts/*/tests/probe-*.sh` exist and no plan declares a probe script.

### Prohibitions (all `verification: test`)

Every test-tier prohibition has wired enforcement in a passing test, so none falls to the fail-closed "unverified" state:

| Prohibition | Enforcing test(s) | Status |
| --- | --- | --- |
| CERT-03: no more than 200 hosts probed | `test_cert_cycle_cap_250_probes_200` | ✓ enforced |
| CERT-03: no HostRegexp/HostSNI/template/wildcard probe targets | `test_extract_hosts_skips_non_literal_names`, `test_collect_hosts_skips_regex_sni_and_negated_names` | ✓ enforced |
| CERT-01: no tz-less/unparsable notAfter accepted | `test_parse_certificates_shape_errors[notAfter-naive/unparsable]`, `test_certificates_payload_errors` | ✓ enforced |
| CERT-02: no bytes sent over CERT_NONE connection | `test_probe_sends_no_bytes_after_handshake` (+ `received == [b""]` in probe tests) | ✓ enforced |
| CERT-02: no verified=True for invalid chains | expired / self-signed / private CA / no intermediate / other host / time tests | ✓ enforced |
| CERT-04: wildcard never covers >1 label or the apex | `test_hostname_matches_san*` | ✓ enforced |
| CERT-05: failed probe / missing cert never unavailable while cycle ok | `test_failing_probe_keeps_cert_entities_available`, `test_probe_failed_after_two_failed_refreshes` | ✓ enforced |
| CERT-02: never connect to router host via DNS | `test_probe_connects_to_traefik_host_with_router_host_as_sni`, e2e test | ✓ enforced |
| CERT-05: unique_id scheme unchanged | `test_sensor_tls.py:228`, `test_binary_sensor_tls_expiring.py:231`, `test_cert_entity_state.py:449` | ✓ enforced |
| CERT-05: no token in attributes/logs | `test_secret_token_never_in_cert_attributes_or_log` | ✓ enforced |
| CERT-01: no TLS connection in API mode | `test_api_uncovered_host_is_not_found_and_not_probed`, `test_v37_api_setup_publishes_api_state_without_probing`, `test_default_v37_setup_is_clock_independent` | ✓ enforced |
| CERT-02: no thread/executor/blocking/CA-loading calls | `test_probe_modules_use_no_threads_or_blocking_calls` | ✓ enforced |
| CERT-03: no module-level growing structure | `test_no_module_level_dict` | ✓ enforced |
| CERT-01: cancelled cycle leaves no connection / half state | `test_cancelled_refresh_closes_connection_and_keeps_data`, `test_probe_cancelled_during_handshake_closes_connection` | ✓ enforced |
| CERT-05: no fake success after failed first refresh | `test_failed_first_cycle_keeps_restored_hosts_unavailable_not_missing`, `test_unavailable_when_cert_cycle_failed` | ✓ enforced |
| CERT-05: crossing not held back to next cycle | `test_threshold_crossing_without_probe`, `test_expired_at_not_after_without_probe` | ✓ enforced |
| CERT-05: restored hosts not marked missing on failed first cycle | same as above + `test_setup_does_not_wait_for_the_first_cert_cycle` | ✓ enforced |
| CERT-05: problem_count counts every host | `test_names_capped_count_complete` | ✓ enforced |
| CERT-05: aggregate and per-host sensors never disagree | `test_aggregate_agrees_with_per_host_sensors` (shared `problem()`) | ✓ enforced |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| CERT-01 | 06-02, 06-05 | `/api/certificates` on >= 3.7, `source=api`, no probing; 404 → probe | ✓ SATISFIED | Truth 1 |
| CERT-02 | 06-03, 06-04, 06-05 | native async probe, shared CERT_NONE ctx, DER via cryptography, entry host + TLS port + SNI, `verified`, ssl vs oserror | ✓ SATISFIED | Truths 2, 3, 7 |
| CERT-03 | 06-01, 06-05 | `extract_hosts` v2/v3, regex/wildcard skipped, cap 200, no unbounded cache | ✓ SATISFIED | Truths 4, 5, 7 |
| CERT-04 | 06-03 | single-label wildcard matching | ✓ SATISFIED | Truth 6 |
| CERT-05 | 06-04, 06-06, 06-07 | live days, problem-on with reason (per host + aggregate), timestamp keeps last value | ✓ SATISFIED | Truths 8, 9 |

No orphaned requirements: REQUIREMENTS.md maps exactly CERT-01..05 to Phase 6, and every one is claimed by at least one plan.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| (phase-modified files) | — | TBD / FIXME / XXX / TODO / placeholder | — | none found |
| `tls.py` | 244 | `asyncio.open_connection(connect_host, ...)` resolves the connect hostname through `loop.getaddrinfo` (default executor) once per probe (review IN-03) | ℹ️ Info | The handshake is threadless and the loop never blocks; the requirement itself mandates `asyncio.open_connection`, so the intent of "no executor" (no offloaded blocking handshake, P-05/P-06) holds. Up to 200 resolutions per cycle; with round-robin DNS probes may reach different Traefik instances. Optional fix: resolve once per cycle |
| `cert_coordinator.py` | 260 | magic string `"tls_warn_days"` instead of `CONF_TLS_WARN_DAYS` (IN-02) | ℹ️ Info | relevant when Phase 7 reworks options |
| `cert_coordinator.py` | 535 | `get_threshold()` has no production caller (IN-01) | ℹ️ Info | dead code |
| `tests/test_tls.py`, `tests/test_cert_coordinator.py` | — | port-reuse race / fixed `sleep(0.2)` in socket tests (IN-04) | ℹ️ Info | possible flakiness on slow runners |
| `const.py`, `__init__.py` | various | pre-existing planning references (`CONTEXT.md D-xx`, `Phase N`) in shipped code | ℹ️ Info | not introduced by Phase 6; scheduled for the Phase 8 planning-reference sweep (M22) |

### Human Verification Required

None. The code-review fixer marked CR-01, WR-02 and WR-03 "requires human verification"; each is covered by named behavioral tests that the verifier read and ran (`test_probe_of_default_certificate_is_not_found_problem`, `test_cycle_finishing_after_shutdown_schedules_no_day_boundary`, `test_probe_cycle_never_reads_runtime_data_after_the_api_call`, `test_setup_does_not_wait_for_the_first_cert_cycle`, `test_unload_cancels_a_running_first_cert_cycle`). The UI visual check is deferred to Phase 8 (M35).

### Gaps Summary

No gaps. The phase goal is achieved in the codebase:

- API source on >= 3.7 with zero TLS connections; probe fallback on 404, re-tried every cycle.
- Threadless CERT_NONE probe to the entry-URL host on the router's TLS entrypoint port with SNI = router host; expired, self-signed and private-CA certificates are read, `verified` computed offline against HA's in-memory roots.
- Bounded, normalized host set (`rules.py`, cap 200), single-label wildcard matching, ordered error classes.
- Live day count with a day-boundary timer; expired, repeatedly unprobeable, uncovered (API) and non-covering (probe, CR-01) certificates are problems with a `reason`, per host and in the enabled-by-default `certificates_problem` aggregate, while the timestamp sensor keeps its last value and stays available.
- WR-03 keeps D-23's observable semantics: no fake success, restored hosts not marked missing, no `ConfigEntryNotReady`, 5-minute retry, and cert entities plus the aggregate unavailable (not a false "off") until the first cycle ends.

Notes for the decision log (not blocking):
- CR-01 extends the `not_found` reason to probe mode (a presented certificate that does not cover the host). This is consistent with W47 but is a new user-visible semantic not yet recorded in `decisions.md`.
- WR-02 relies on the private `DataUpdateCoordinator._shutdown_requested` (see `coincidental_reliance_items`); re-check it with the Phase 7 minimum-HA bump.

---

_Verified: 2026-11-15T09:49:14Z_
_Verifier: Claude (gsd-verifier)_
