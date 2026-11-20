---
phase: "06"
slug: "certificates"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
block_on: high
created: "2026-11-15"
---

# Phase 06 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time (06-01..06-07 `<threat_model>` blocks); verified at ASVS L1 (grep evidence + named tests) at HEAD be2c0ea.
> All threats closed at L1 with the register authored at plan time, so the workflow short-circuit applied (no auditor subagent at ASVS 1).
> Paths: `cc/` = `custom_components/traefik_proxy/`.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Traefik router config → cert host set | Router rules and `tls.domains` from the Traefik API are untrusted text | Rule strings, domain names |
| Traefik API → client | `/api/certificates` JSON is untrusted input and decides which certificate a host maps to | Certificate metadata, timestamps, pagination header |
| Traefik entrypoint config → probe port | Entrypoint addresses come from the Traefik API | Address strings |
| TLS peer → probe | The presented certificate chain (DER) is untrusted network input | DER certificates |
| Probe / cert coordinator → user network | `CERT_NONE` read-only connections to the Traefik host | TLS ClientHello with SNI |
| Cert coordinator → entity attributes / HA log / recorder | Per-host state and aggregates become recorded attributes and log lines | Host names, closed-set codes, dates |
| Wall clock → cert entity state; cert cycle → registry lifecycle | Day-boundary timer drives state; a failed cycle must not start removal clocks | Timestamps |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-06-01 | Denial of service | Cert host collection (`_collect_hosts`) | medium | mitigate | `MAX_CERT_HOSTS = 200` (cc/const.py:72); sorted set cut, one count-only WARNING (cc/cert_coordinator.py:526-533); test_max_cert_hosts_is_200, test_collect_hosts_cap_not_reached, test_collect_hosts_cap_201_drops_last_sorted, test_cert_cycle_cap_250_probes_200, test_cert_cycle_cap_warns_once_per_cycle (tests/test_cert_coordinator.py:1402-1455) | closed |
| T-06-02 | Tampering | `rules.extract_hosts` / `normalize_host` | low | mitigate | Literal `Host()` arguments only, precompiled module regexes (cc/rules.py:30-39), charset whitelist + IDNA 2008/UTS-46 (cc/rules.py:42-71, review fix WR-01), no eval, no state; test_extract_hosts_skips_non_literal_names, test_normalize_host_rejects, test_collect_hosts_skips_regex_sni_and_negated_names | closed |
| T-06-03 | Tampering | `parse_certificates` | medium | mitigate | Strict shape checks, naive/unparsable timestamps rejected (cc/models.py:423-428); violations → `TraefikProxyPayloadError` (cc/api.py:261-273); test_parse_certificates_shape_errors (tests/test_models.py:800) | closed |
| T-06-04 | Denial of service | `async_get_certificates` pagination | low | mitigate | Reuses `_get_paginated` with `MAX_PAGES = 100` and the X-Next-Page stop rule (cc/api.py:37, :219-242, :263-269); tests/test_api_pagination.py | closed |
| T-06-05 | Information disclosure | Exception texts of the certificates read | low | mitigate | Errors carry only path + status / exception type (cc/api.py:107-145; cc/cert_coordinator.py:303); test_credentials_never_leak (tests/test_api.py:344) | closed |
| T-06-06 | Spoofing | `CERT_NONE` probe connection | medium | mitigate | Read-only: no write/send in cc/tls.py; `server.received == [b""]` asserted after each probe (tests/test_tls.py:357-421); trust reported via offline `verified` (cc/tls.py:150), never assumed | closed |
| T-06-07 | Tampering | `certificate_from_der` / `chain_verified` on peer DER | medium | mitigate | Parsing only through `cryptography` (cc/tls.py:32-35, :110, :150); leaf failure → `parse`, malformed intermediates skipped, verifier errors → `verified=False`; test_probe_non_der_peer_certificate_is_parse and the unverified-chain tests (tests/test_tls.py:341-440, :622) | closed |
| T-06-08 | Denial of service | Hanging or slow peers | medium | mitigate | `asyncio.timeout` on connect (cc/tls.py:243) and `wait_closed`, `transport.abort()` fallback (cc/tls.py:212-222); test_probe_hanging_server_is_timeout, test_probe_aborts_transport_when_wait_closed_hangs, test_probe_cancelled_during_handshake_closes_connection; wall-clock bound under freezer (review fix WR-04, tests/test_tls.py:791) | closed |
| T-06-09 | Information disclosure | Exception details of failed probes | low | mitigate | `ProbeFailure.detail` documented debug-only (cc/tls.py:68-72); only consumer is a DEBUG log line (cc/cert_coordinator.py:447); entities expose closed-set codes | closed |
| T-06-10 | Spoofing / SSRF-like reach | Probe target selection | medium | mitigate | Connect host is always the entry URL host (cc/cert_coordinator.py:346-352, :398); router names only as SNI (cc/tls.py:244); no DNS lookup of router names; test_probe_connects_to_traefik_host_with_router_host_as_sni (tests/test_cert_coordinator.py:326) | closed |
| T-06-11 | Information disclosure | Cert entity attributes and cert-cycle logs | medium | mitigate | Attributes carry certificate metadata and closed-set codes; probe detail at DEBUG only (cc/cert_coordinator.py:447), cap WARNING carries counts only (:528); test_secret_token_never_in_cert_attributes_or_log (tests/test_cert_entity_state.py:507) | closed |
| T-06-12 | Repudiation (misleading health) | API mode for uncovered hosts; probe mode default certificate | medium | mitigate | Uncovered host → `not_found`, never probed (cc/cert_coordinator.py:314-328); SAN mismatch → `NOT_FOUND` (cc/cert_coordinator.py:193, review fix CR-01); API `status` ignored; test_api_uncovered_host_is_not_found_and_not_probed (tests/test_cert_coordinator.py:530), test_v37_api_status_field_never_changes_the_state (tests/test_cert_entity_state.py:650) | closed |
| T-06-13 | Denial of service | Per-host state growth | low | mitigate | `data` rebuilt from the capped host set every cycle (cc/cert_coordinator.py:405-410, :383); instance attributes are `_sem`, `_timeout`, `_trust_store`, `_trust_store_ready`, `_unsub_day_boundary` only (no per-host dict) | closed |
| T-06-14 | Denial of service | Probe fan-out and cancelled cycles | medium | mitigate | `TLS_SEMAPHORE = 4` (cc/const.py:67; cc/cert_coordinator.py:262), `TLS_HANDSHAKE_TIMEOUT = 5.0` (cc/const.py:66); CancelledError propagates, connection closed in `finally` (cc/tls.py:251-252); test_semaphore_default_is_4, test_probe_concurrency_is_bounded_by_semaphore (tests/test_cert_coordinator.py:293, :941), test_probe_cancelled_error_propagates | closed |
| T-06-15 | Denial of service (event-loop starvation) | Probe implementation | medium | mitigate | No thread/executor/blocking connect: test_probe_modules_use_no_threads_or_blocking_calls, test_blocking_probe_path_is_removed (tests/test_tls.py:140, :157); trust anchors read in memory from HA's pre-built `client_context()` once and cached (cc/cert_coordinator.py:354-364) | closed |
| T-06-16 | Tampering | `entrypoint_port` on untrusted addresses | low | mitigate | ASCII digits only, 1..65535, `/udp` → None (cc/cert_coordinator.py:95-108), 443 fallback (`DEFAULT_PROBE_PORT`, :69); test_entrypoint_port (tests/test_cert_coordinator.py:674) | closed |
| T-06-17 | Denial of service | Day-boundary timer | low | mitigate | One timer, cancelled before every reschedule and in `async_shutdown` (cc/cert_coordinator.py:461-491); no re-arm at unload (review fix WR-02); test_boundary_timer_is_replaced_on_every_cycle, test_no_timer_without_a_certificate, test_unload_cancels_the_boundary_timer (tests/test_cert_lifecycle.py:259-295) | closed |
| T-06-18 | Repudiation (masked failure) | First cert cycle | medium | mitigate | No `async_set_updated_data` in cc/ (grep gate); failed cycle → unavailable, restored hosts without missing stamp; setup does not wait for the first cycle (review fix WR-03); test_failed_first_cycle_keeps_restored_hosts_unavailable_not_missing, test_setup_does_not_wait_for_the_first_cert_cycle, test_unload_cancels_a_running_first_cert_cycle (tests/test_cert_lifecycle.py:338-480) | closed |
| T-06-19 | Information disclosure | Aggregate attributes | low | mitigate | Only host names (already exposed per host) and closed-set `reasons` values (cc/binary_sensor.py:150-172); no token, no error detail | closed |
| T-06-20 | Denial of service (recorder bloat) | Aggregate attribute size | low | mitigate | `problems` / `reasons` capped at `MAX_PROBLEM_NAMES` (cc/binary_sensor.py:168-172); write-on-change token; test_names_capped_count_complete (tests/test_certificates_problem.py:118), test_unchanged_cert_notification_writes_nothing (tests/test_cert_entity_state.py:402) | closed |
| T-06-SC | Tampering | npm/pip/cargo installs | low | accept | AR-06-01 | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

Review fixes mapped to the register: CR-01 → T-06-12, WR-01 → T-06-02, WR-02 → T-06-17, WR-03 → T-06-18, WR-04 → T-06-08.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-06-01 | T-06-SC | No package installs or dependency changes in Phase 6 (pyproject.toml, uv.lock, manifest.json, hacs.json unchanged a7eeee8~1..be2c0ea; `requirements: []`); `cryptography` and `idna` are bundled with HA | Plan threat model (all plans), verified by security audit | 2026-11-15 |

*Accepted risks do not resurface in future audit runs.*

### Observations (informational, non-blocking)

1. T-06-09 / T-06-11: the DEBUG line at cc/cert_coordinator.py:447 includes `ProbeFailure.detail` (`<ExceptionType>: <message>`). It can carry the connect host or IP, which the user configured anyway; it never carries the API token, which the probe path does not have.
2. T-06-06: a man in the middle on the user's network can present any certificate. The integration reports it as `verified=False` and does not trust it. The probe sends no application data.
3. T-06-13: the "no per-host dict" rule is a plan-time grep gate, not a regression test.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-15 | 21 (T-06-01..T-06-20, T-06-SC) | 21 | 0 | /gsd-secure-phase orchestrator (ASVS L1 short-circuit, auditor not spawned; threat test modules at be2c0ea: 531 passed on HA 2026.10.4, 531 passed on HA 2026.3.0) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-15
