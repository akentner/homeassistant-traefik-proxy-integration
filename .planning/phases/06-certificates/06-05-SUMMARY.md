---
phase: 06-certificates
plan: 05
subsystem: certificates
tags: [cert-coordinator, api-certificates, tls-probe, trust-anchors, entrypoint-port, threadless, cancellation]

requires:
  - phase: 06-02
    provides: "TraefikProxyApiClient.async_get_certificates, stub_traefik certificates (clock-rebased v3.7, 404 on v2.11), frozen_v37_certificates"
  - phase: 06-03
    provides: "tls.match_certificate, tls.build_trust_store, tls_server fixture, tests/certgen.py"
  - phase: 06-04
    provides: "HostCertState, CertSource, NOT_FOUND, _async_probe_states/_probe_state, trust_store kwarg"
provides:
  - "API-first cert cycle: async_get_certificates() -> _api_states (match_certificate, uncovered -> not_found, never probed); 404 -> probe; other API errors -> UpdateFailed"
  - "CertCoordinator._get_trust_store(): kwarg store, else build_trust_store(ha_ssl.client_context().get_ca_certs(binary_form=True)) once, cached (None included)"
  - "cert_coordinator.entrypoint_port(address) -> int | None; CertCoordinator._probe_ports(hosts); _router_hosts/_router_ports helpers; DEFAULT_PROBE_PORT = 443 fallback"
  - "tls.py reduced to the threadless probe, trust verification and match_certificate; _ASCII_LOWER read-only"
  - "Suite gates: tls.py top-level definitions pinned, no thread/executor/blocking connect/CA loading in tls.py and cert_coordinator.py, no module-level dict in tls/cert_coordinator/rules"
affects: [06-06, 06-07]

actuals:
  tokens: 23700
  tasks: 3
  commits: 6
plan_head_before: 96cf976145c679b994f9a88f55f7276f5501cc4d
plan_head_after: bfe1f11fc66abed5c5545ac3f66a693cc29f8016

tech-stack:
  added: []
  patterns:
    - "Source selection per cycle: the API answer decides (list -> API states, 404 -> probe), re-evaluated every cycle"
    - "One private helper derives a router's hosts for both the host set and the port map"
    - "Lazy per-coordinator trust store from HA's pre-built client context (memory only)"
    - "Module gates as tests: AST allowlist of top-level definitions, forbidden-call regex over source, no module-level dict"

key-files:
  created: []
  modified:
    - custom_components/traefik_proxy/cert_coordinator.py
    - custom_components/traefik_proxy/tls.py
    - tests/conftest.py
    - tests/test_tls.py
    - tests/test_cert_coordinator.py
    - tests/test_cert_entity_state.py
    - tests/test_coordinator.py
    - tests/test_entity_manager.py

key-decisions:
  - "Planner worker decisions adopted as listed in 06-05-PLAN.md (uncovered host certificate None, 401 fails the cycle without reauth, lazy cached HA roots, port 443-if-offered-else-lowest, shared host helper, entrypoint_port in cert_coordinator.py, D-20 two gates)"
  - "The API is asked every cycle, also with an empty host set (plan key link 'every cycle awaits'); an empty host set in probe mode still returns {} before any connect"
  - "_ASCII_LOWER wrapped in MappingProxyType so the no-module-level-dict gate holds without an allowlist"
  - "The tls module gate pins tls.py's top-level definitions (AST allowlist) instead of listing removed names, because a list of removed names would itself trip the plan's grep gate"
  - "_refresh_paths in test_coordinator drops /api/certificates: it is the cert coordinator's own 6 h timer firing during long freezer ticks, not a main-coordinator request"

patterns-established:
  - "API-source integration tests: stub_traefik(aioclient_mock, certificates=frozen_v37_certificates(freezer)) for fixed dates, default stub for clock independence"

requirements-completed: [CERT-01, CERT-02, CERT-03]

coverage:
  - id: D1
    description: "API source: fixture certificates -> api states (verified None, san_mismatch False, port None, fetched_at now, failures 0), no probe; uncovered host -> not_found, never probed; 404 -> probe per host; 500/connection/payload/401 -> UpdateFailed without probe"
    requirement: "CERT-01"
    verification:
      - kind: unit
        ref: "tests/test_cert_coordinator.py#test_api_certificates_become_api_states, test_api_uncovered_host_is_not_found_and_not_probed, test_certificates_404_falls_back_to_probe, test_certificates_error_fails_the_cycle_without_probe"
        status: pass
    human_judgment: false
  - id: D2
    description: "Full setup v3.7: timestamps 2027-02-12T00:17:40+00:00, source api, days 88, expiring off, 0 probes over setup + 2 refreshes; extra host not_found right away; status 'expired' ignored; clock independence at 2027-01-30 and 2027-02-13; 500/401 later cycle -> unavailable, no probe, no reauth; v2.11 re-requests /api/certificates every cycle"
    requirement: "CERT-01"
    verification:
      - kind: integration
        ref: "tests/test_cert_entity_state.py#test_v37_api_setup_publishes_api_state_without_probing, test_v37_api_uncovered_host_is_not_found_right_away, test_v37_api_status_field_never_changes_the_state, test_default_v37_setup_is_clock_independent, test_v37_certificates_error_fails_the_cert_cycle, test_v211_certificates_404_probes_and_re_requests_each_cycle"
        status: pass
    human_judgment: false
  - id: D3
    description: "Request paths after setup end with /api/certificates (rawdata and pages variants); a main refresh alone requests only /api/rawdata"
    requirement: "CERT-01"
    verification:
      - kind: integration
        ref: "tests/test_coordinator.py#test_rawdata_snapshot_reaches_entities, test_rawdata_404_switches_to_pages_once, test_request_budget_matrix"
        status: pass
    human_judgment: false
  - id: D4
    description: "Trust store: HA roots read once over two probe cycles; kwarg replaces them; API mode never reads them"
    requirement: "CERT-02"
    verification:
      - kind: unit
        ref: "tests/test_cert_coordinator.py#test_trust_store_defaults_to_ha_roots_built_once, test_trust_store_kwarg_replaces_ha_roots, test_trust_store_never_built_in_api_mode"
        status: pass
    human_judgment: false
  - id: D5
    description: "entrypoint_port (10 cases) and _probe_ports (7 cases); a host of several routers probed once on its chosen port"
    requirement: "CERT-02"
    verification:
      - kind: unit
        ref: "tests/test_cert_coordinator.py#test_entrypoint_port, test_probe_ports, test_probe_ports_host_of_several_routers_probed_once"
        status: pass
    human_judgment: false
  - id: D6
    description: "End to end: v2.11 setup at https://127.0.0.1:8080, websecure at the tls_server port; probes connect to 127.0.0.1:<port> with both router hosts as SNI (fallback default cert proves SNI); timestamp = served leaf not_after, source probe, port <port>; verified True with the test root as HA roots, False with HA's real roots"
    requirement: "CERT-02"
    verification:
      - kind: integration
        ref: "tests/test_cert_coordinator.py#test_end_to_end_probe_reaches_tls_entrypoint_port"
        status: pass
    human_judgment: false
  - id: D7
    description: "Cancellation closes the hanging connection within 1 s and keeps data identical; overlapping refreshes both complete; at most 4 probes concurrently with 10 hosts"
    requirement: "CERT-01"
    verification:
      - kind: integration
        ref: "tests/test_cert_coordinator.py#test_cancelled_refresh_closes_connection_and_keeps_data, test_overlapping_refreshes_both_complete, test_probe_concurrency_is_bounded_by_semaphore"
        status: pass
    human_judgment: false
  - id: D8
    description: "Blocking path gone; no thread/executor/blocking connect/CA loading in tls.py and cert_coordinator.py; no module-level dict in tls/cert_coordinator/rules"
    requirement: "CERT-03"
    verification:
      - kind: unit
        ref: "tests/test_tls.py#test_blocking_probe_path_is_removed, test_probe_modules_use_no_threads_or_blocking_calls, test_no_module_level_dict"
        status: pass
    human_judgment: false

duration: 14min
completed: 2026-11-15
status: complete
---

# Phase 6 Plan 05: API-first Certificate Source, Trust Anchors, Entrypoint Ports Summary

**Each cert cycle now reads `GET /api/certificates` first. Traefik 3.7 and later answers it, and every host is mapped to its certificate without a single TLS connection. Hosts that no certificate covers show `not_found` right away and are never probed. Older Traefik answers 404 and falls back to the threadless probe. The probe now runs once per host on the router's TLS entrypoint port and checks the chain against Home Assistant's own trust anchors. The old blocking probe path and its throttle dict are deleted, and suite gates keep them from coming back.**

## Performance

- **Duration:** about 14 min
- **Started:** about 2026-11-15T08:45Z
- **Completed:** 2026-11-15T08:59Z
- **Tasks:** 3, all TDD (RED commit, then GREEN commit)
- **Files:** 8 modified

## Accomplishments

- **API source (Task 1):** `_async_update_data` awaits `runtime_data.client.async_get_certificates()`. `TraefikProxyNotFoundError` leads to `_async_probe_states`. Any other `TraefikProxyApiError` raises `UpdateFailed("Reading certificates failed: <path>: <detail>")`. `_api_states` calls `match_certificate` for each host. A match gives `source=api, verified=None, san_mismatch=False, port=None, fetched_at=now`. No match gives `certificate=None, error=not_found, failures=0, fetched_at=None`, and that host is never probed. The API `status` field stays on the certificate and the state logic never reads it. The module and class docstrings now describe the API-first cycle.
- **Trust anchors and ports (Task 2):** `_get_trust_store()` returns the kwarg store, or else builds a store once from `ha_ssl.client_context().get_ca_certs(binary_form=True)` and caches it (None included). The new function `entrypoint_port()` parses `:443`, `0.0.0.0:443`, `[::]:443` and a `/tcp` suffix. UDP addresses, non-numeric ports and ports outside 1..65535 give None. `_probe_ports()` picks 443 when any router of the host offers it, else the lowest port, else 443. `_router_hosts()` now feeds both `_collect_hosts()` and the port map, and `PROBE_PORT` is gone (`DEFAULT_PROBE_PORT` is the fallback).
- **Cleanup (Task 3):** `tls.py` lost the thread wrapper, the blocking connect/fetch path, the notAfter string parser and its formats, `CertDict`/`CertInfo`/`CertError`/`is_error`, the RDN formatter, the error-dict builder, the parse-log cooldown dict and `DEFAULT_PORT`. In `tests/conftest.py` the openssl-subprocess certificate server, its helpers and the tls pre-import are gone. In `tests/test_tls.py` the old blocking-path tests are gone. New tests cover cancellation, overlapping refreshes and the semaphore bound.

## Task Commits

1. **Task 1 (tracer): /api/certificates source, 404 probe fallback**
   - RED `3b91217` test(06-05): add failing tests for the /api/certificates source and the 404 probe fallback
   - GREEN `88eb12e` feat(06-05): read certificates from /api/certificates first, probe only on 404
   - Tracer gate (auto mode): every `<verify>` command re-run green (110 targeted, 786 full, `clock_independent` 2 passed, file-list gate, ruff, format, mypy, 786 on HA 2026.3), then expanded to Task 2
2. **Task 2: HA trust anchors, TLS entrypoint port, real-handshake end to end**
   - RED `c1edb1a` test(06-05): add failing tests for HA trust anchors, TLS entrypoint ports and a real end-to-end handshake
   - GREEN `799c7a3` feat(06-05): verify probes against HA trust anchors and probe on the router's TLS entrypoint port
3. **Task 3: cancellation/overlap safety; delete the blocking probe path**
   - RED `2085c0e` test(06-05): add failing gates for the removed blocking probe path, plus cancellation and overlap tests
   - GREEN `bfe1f11` feat(06-05): delete the blocking probe path and its parse-log throttle

## TDD Gate Compliance

| Task | RED evidence | Verdict | Semantic assessment |
|------|--------------|---------|---------------------|
| 1 | `pytest` on test_cert_coordinator / test_cert_entity_state / test_coordinator `--junitxml`, exit 1, 17 failed / 93 passed; target `test_api_certificates_become_api_states` | `RED_EVIDENCE_OK` (target_test_failed) | The target failed on `Expected mock to not have been awaited. Awaited 2 times.`: the probe-only cycle probed instead of reading the API. Every failure was an assertion against the missing API source or the missing `/api/certificates` request. There were no collection or fixture errors. |
| 2 | `pytest` on test_cert_coordinator / test_cert_entity_state `--junitxml`, exit 1, 14 failed / 98 passed; target `test_trust_store_defaults_to_ha_roots_built_once` | `RED_EVIDENCE_OK` (target_test_failed) | The target failed on `Expected 'get_ca_certs' to be called once. Called 0 times.`. A throwaway stub let the module collect (`entrypoint_port` -> None, `_probe_ports` -> 443). It was never committed and was replaced before GREEN. Port, once-per-host and end-to-end tests failed on port assertions, and the two default-store assertions on `isinstance(None, Store)`. The kwarg and API-mode trust-store tests passed in RED by design: they are guards. |
| 3 | `pytest` on test_tls / test_cert_coordinator `--junitxml`, exit 1, 3 failed / 167 passed; target `test_blocking_probe_path_is_removed` | `RED_EVIDENCE_OK` (target_test_failed) | The target failed because 15 old blocking-path names were still defined. The source gate failed on tls (`to_thread`, `create_connection`, `load_default_certs`, ...), and the dict gate on `_parse_log_cooldown` and `_ASCII_LOWER`. The cancellation, overlap and concurrency tests passed already. 06-04 builds the per-host dict only after `gather` and runs every probe under the semaphore, so these tests pin existing behaviour. The plan expects no coordinator change unless a behaviour line fails. |

Each RED commit holds tests only, and each GREEN commit restores a green tree. This is the same per-task D-19 precedent as 06-01..06-04.

## Verification

- `uv run pytest -q`: **796 passed** (771 before this plan)
- `~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`: **796 passed on HA 2026.3.0**
- `uv run ruff check custom_components tests`: all checks passed. `ruff format --check`: 41 files already formatted. `mypy --strict custom_components/traefik_proxy`: no issues in 15 source files.
- Acceptance Task 1: `async_get_certificates()` and `match_certificate(` are in cert_coordinator. `"/api/certificates"` is in test_coordinator. `-k "api or not_found or status or non_404 or unauthorized or re_request"`: 6 passed. `-k clock_independent`: 2 passed. File-list gate: `tests/conftest.py tests/test_api.py tests/test_fixture_redaction.py tests/test_models.py`.
- Acceptance Task 2: `^def entrypoint_port(address: str) -> int | None:` and `get_ca_certs(binary_form=True)` are present. `-k "trust_store or entrypoint_port or probe_ports or end_to_end"`: 25 passed (at least 15 required).
- Acceptance Task 3: the P7 grep finds no line in tls.py/cert_coordinator.py. The old-symbol grep finds nothing across custom_components and tests. The module-dict grep finds nothing in tls/cert_coordinator/rules. `openssl` does not appear in conftest. `-k "cancel or overlap or concurren"`: 3 passed.

## Worker decisions

| Decision | Reason | Alternative not taken |
|---|---|---|
| Planner decisions adopted as listed in 06-05-PLAN.md "Worker decisions (planner)" | Recorded by the planner | — |
| The API is asked every cycle, also when the host set is empty | Plan key link: "every cycle awaits ... async_get_certificates()". A failing API is visible even before any TLS router exists. | Skip the request without hosts |
| `UpdateFailed` text is `Reading certificates failed: <err>` | The client's error message is `<path>: <detail>` and never carries a URL or credential, so it is safe to show | Bare status code |
| `_ASCII_LOWER` wrapped in `MappingProxyType` | `str.maketrans` returns a dict. A read-only proxy keeps the new "no module-level dict" gate free of an allowlist and makes the table immutable. | Allowlist the name in the gate |
| The tls module gate pins tls.py's top-level definitions (AST allowlist); the RED version listed the removed names | A list of the removed names in a test file would itself match the plan's old-symbol grep over `tests`. The allowlist fails for the same RED reason and also catches any other new top-level name. | Keep the name list and fail the plan's grep gate |
| `_refresh_paths` in test_coordinator drops `/api/certificates` | During the request-budget matrix the freezer passes more than 6 h, so the cert coordinator's own timer fires inside a main refresh window. The budget is about the main coordinator. | Disable the cert timer in that test |
| `test_full_setup_registers_cert_entities_for_alt_host` now runs on the v2.11 capture | It asserts probe calls. On v3.7 the API now answers and no probe runs. | Assert not_found on v3.7 |
| `test_unchanged_notifications_write_no_state` serves the capture's fixed dates via `frozen_v37_certificates` | The rebased default certificate ends exactly on a day boundary (now + 3650 d), so the live day count drops after the test's 1 s tick and the state is legitimately written. The fixed capture leaves 88.5 days. Same reason as the 06-04 half-day offset. | Tick-free test |
| Probe-mode default for the `MagicMock` entry in test_cert_coordinator (`async_get_certificates` raises 404) | Keeps every existing probe unit test meaningful. An un-awaitable MagicMock would break them. | Patch each test |
| The end-to-end test serves a different default certificate (`fallback.invalid`) | A matching `not_after` then proves SNI was sent for both hosts | Single certificate for every name |
| Removed the now-unused `_LOGGER` from tls.py | No log call remains after the throttle was deleted | Keep a dead logger |

## Deviations from Plan

None in production behaviour. The test-side changes listed under Worker decisions were needed to migrate existing tests to the API-first cycle (D-19 "every other test that fails ... is updated in this task"). One change of approach: the Task 3 RED test `test_blocking_probe_path_is_removed` was rewritten in GREEN from a name list to an AST allowlist, for the grep-gate conflict described above. It is the same test name and the same intent.

## Requirement status

CERT-01, CERT-02 and CERT-03 are marked complete. This plan delivers the remaining parts: the API source end to end (SC1), the entrypoint port, HA trust anchors and the threadless guarantee (SC2), and no unbounded module cache (SC3, P-08), plus the CERT-01 concurrency edge. 06-06/06-07 still hold CERT-05 parts (day-boundary timer, aggregate).

## User-visible changes (for the Phase 8 CHANGELOG)

- On Traefik 3.7 and later, certificate data comes from Traefik's `/api/certificates`. The integration opens no TLS connections, and the entities show `source: api` and `verified: None`.
- A TLS host that has no certificate in Traefik's list shows `certificate_expiring` on with reason `not_found` right away. A pending ACME order shows this until the next cert cycle or "Refresh now".
- In probe mode (Traefik before 3.7), `verified` is checked against Home Assistant's trust store.
- Probes go to the Traefik host on the router's TLS entrypoint port. Router hostnames get no DNS lookup, and routers on non-443 entrypoints now work.
- Certificate checks no longer use worker threads.

## Known Stubs

None. The Task 2 RED stub was throwaway and never committed.

## Threat Flags

None new. T-06-12: uncovered hosts are not_found and never probed (`test_api_uncovered_host_is_not_found_and_not_probed`, `test_v37_api_uncovered_host_is_not_found_right_away`), and the API status is ignored (`test_v37_api_status_field_never_changes_the_state`). T-06-14: semaphore maximum 4, cancellation closes the connection and keeps the state. T-06-15: the grep gate passes and the suite gates are in test_tls.py. Trust anchors come from HA's pre-built context in memory. T-06-16: `entrypoint_port` accepts only digits in 1..65535, skips `/udp` and falls back to 443.

## `state.update-progress`

It reported "phase scope is unscoped, not complete" (`updated: false`), so it was skipped as instructed. These ran normally: `roadmap.update-plan-progress 06` (5/7, In Progress), `state.advance-plan` (plan 6 of 7), `record-metric`, `add-decision` x4, `record-session` and `requirements.mark-complete CERT-01 CERT-02 CERT-03`.

## Next Phase Readiness

- 06-06: `__init__.py` still seeds an empty successful cert state after a failed first cert refresh. The non-404 tests here fail a later cycle on purpose. The day-boundary timer only needs `async_update_listeners()`.
- 06-07: the aggregate can rely on `HostCertState.problem()` for both sources.

## Self-Check: PASSED

- FOUND: custom_components/traefik_proxy/cert_coordinator.py (`def entrypoint_port`, `async_get_certificates()`, `match_certificate(`, `get_ca_certs(binary_form=True)`), custom_components/traefik_proxy/tls.py (`async def async_probe_certificate`), tests/test_cert_coordinator.py (`tls_server`)
- FOUND commits (ancestors of HEAD): 3b91217, 88eb12e, c1edb1a, 799c7a3, 2085c0e, bfe1f11
- Measured: `git rev-list --count 96cf976..HEAD` = 6
