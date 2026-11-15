---
phase: 06-certificates
plan: 04
subsystem: certificates
tags: [cert-coordinator, tls-probe, sni, per-host-state, problem-sensor, live-days]

requires:
  - phase: 06-01
    provides: "CertCoordinator._collect_hosts (sorted, normalized, capped at MAX_CERT_HOSTS)"
  - phase: 06-02
    provides: "models.TraefikCertificate"
  - phase: 06-03
    provides: "tls.async_probe_certificate, ProbedCertificate, ProbeFailure, ProbeError, build_trust_store; tests/certgen.py, tls_server fixture"
provides:
  - "cert_coordinator.HostCertState (frozen, slots) with days_left(now), problem(threshold, now), is_problem(threshold, now)"
  - "cert_coordinator.CertSource (api, probe), CertProblem (expired, probe_failed, not_found, expiring), NOT_FOUND, CERT_FAILURES_FOR_PROBLEM = 2, PROBE_PORT = 443"
  - "CertCoordinator = DataUpdateCoordinator[dict[str, HostCertState]] with trust_store kwarg; _async_probe_states, _async_probe_host, _connect_host, _probe_state (history)"
  - "TraefikCertEntity._state() / _days_left(); availability = cycle ok + host present"
  - "TraefikCertExpirySensor D-16 attributes; TraefikCertExpiringBinarySensor D-15 precedence + reason"
  - "tests/conftest.py: mock_tls_probe on async_probe_certificate (ProbeError.UNKNOWN), make_cert_state()"
affects: [06-05, 06-06, 06-07]

actuals:
  tokens: 24900
  tasks: 2
  commits: 4
plan_head_before: 7d56a1f2041ff1ec098dec28e1fcdb547a60ebb6
plan_head_after: dc5c6627bd45d3fb1d9386fd125eaa8373c541df

tech-stack:
  added: []
  patterns:
    - "Coordinator data = one frozen per-host state value; entities derive days/problem at read time from dt_util.utcnow()"
    - "Probe history: the next cycle maps (probe result, previous state from self.data) -> new state; the dict is rebuilt from the host set every cycle"
    - "Write-on-change token of cert entities includes the live day count, so a day change writes without a new probe once something notifies"

key-files:
  created: []
  modified:
    - custom_components/traefik_proxy/cert_coordinator.py
    - custom_components/traefik_proxy/entity.py
    - custom_components/traefik_proxy/sensor.py
    - custom_components/traefik_proxy/binary_sensor.py
    - tests/conftest.py
    - tests/test_cert_coordinator.py
    - tests/test_sensor_tls.py
    - tests/test_binary_sensor_tls_expiring.py
    - tests/test_cert_entity_state.py
    - tests/test_entity_manager.py

key-decisions:
  - "Planner worker decisions adopted as listed in 06-04-PLAN.md (HostCertState + enums in cert_coordinator.py, module-local CERT_FAILURES_FOR_PROBLEM, closed last_error set without unreachable, failed probe keeps an API certificate, CN-only subject/issuer, probe-only switch)"
  - "subject attribute = certificate CN or None: an empty CN (probe parses a CN-less leaf as '') is shown as None"
  - "A cycle with an empty host set returns {} before resolving the connect host, so a host-less entry URL only fails cycles that would probe"
  - "Port 443 is a named module constant PROBE_PORT (06-05 replaces it with the resolved TLS entrypoint port)"

patterns-established:
  - "Probe-driven integration tests: version='v2.11' capture, probe patched at cert_coordinator.async_probe_certificate, clock frozen at REFERENCE"

requirements-completed: []  # CERT-02 / CERT-05 are also declared by 06-05..06-07; see Requirement status

coverage:
  - id: D1
    description: "HostCertState: integer floor days (10 d -> 10, 10 d - 1 µs -> 9, now -> 0, 1 µs past -> -1), D-15 precedence table, is_problem unknown only without certificate and < 2 failures"
    requirement: "CERT-05"
    verification:
      - kind: unit
        ref: "tests/test_cert_coordinator.py#test_days_left_is_signed_floor_days, test_problem_precedence, test_is_problem"
        status: pass
    human_judgment: false
  - id: D2
    description: "Cert cycle probes each host once with (traefik.example.com, 443, host), handshake_timeout, trust_store, now; ProbedCertificate/ProbeFailure mapping; URL without host -> UpdateFailed"
    requirement: "CERT-02"
    verification:
      - kind: unit
        ref: "tests/test_cert_coordinator.py#test_probe_connects_to_traefik_host_with_router_host_as_sni, test_probed_certificate_becomes_probe_state, test_probe_failure_becomes_state_without_certificate, test_entry_url_without_host_fails_the_cycle"
        status: pass
    human_judgment: false
  - id: D3
    description: "Trust store passed unchanged; a store with the test root verifies a real probed chain (verified True)"
    requirement: "CERT-02"
    verification:
      - kind: integration
        ref: "tests/test_cert_coordinator.py#test_trust_store_reaches_the_probe, test_trust_store_verifies_chain_through_real_probe"
        status: pass
    human_judgment: false
  - id: D4
    description: "Cert entities available after a failed probe and for not_found; unavailable for absent host / failed cycle; exact attribute key sets; reason precedence; live days in the state token"
    requirement: "CERT-05"
    verification:
      - kind: unit
        ref: "tests/test_sensor_tls.py, tests/test_binary_sensor_tls_expiring.py"
        status: pass
    human_judgment: false
  - id: D5
    description: "Full setup v2.11: probe state published (source probe, verified, timestamp ref + 30 d, 2 probes per cycle at traefik.example.com); failing probe -> available unknown entities with last_error unknown; secret token absent from attributes and DEBUG log; update_entity -> one cert refresh request"
    requirement: "CERT-05"
    verification:
      - kind: integration
        ref: "tests/test_cert_entity_state.py#test_probe_driven_setup_publishes_probe_state, test_failing_probe_keeps_cert_entities_available, test_secret_token_never_in_cert_attributes_or_log, test_update_entity_action_refreshes_cert_coordinator"
        status: pass
    human_judgment: false
  - id: D6
    description: "Probe history: last known certificate kept, consecutive failures, probe_failed after two, reset on success, API state followed by a failing probe, dropped / new hosts; full setup probe_failed after two failed refreshes with the timestamp unchanged"
    requirement: "CERT-05"
    verification:
      - kind: unit
        ref: "tests/test_cert_coordinator.py#test_probe_history_keeps_last_known_certificate_and_counts_failures, test_failed_probe_after_api_state_keeps_last_known_certificate, test_host_dropped_from_host_set_and_new_host_without_history"
        status: pass
      - kind: integration
        ref: "tests/test_cert_entity_state.py#test_probe_failed_after_two_failed_refreshes"
        status: pass
    human_judgment: false

duration: 11min
completed: 2026-11-15
status: complete
---

# Phase 6 Plan 04: Per-host Certificate State Summary

**The cert coordinator now publishes one frozen `HostCertState` per TLS host from the threadless probe. Each probe connects to the Traefik host of the entry URL on port 443 with the router host as SNI and gets the coordinator's trust store. A failed probe keeps the last known certificate and counts consecutive failures. The certificate entities stay available, compute days live and show problems (`expired` > `probe_failed` > `not_found` > `expiring`) instead of going unavailable.**

## Performance

- **Duration:** about 11 min
- **Started:** 2026-11-15T08:32:16Z
- **Completed:** 2026-11-15T08:43:16Z
- **Tasks:** 2 (both TDD: RED commit + GREEN commit)
- **Files:** 10 modified

## Accomplishments

- **`cert_coordinator.py` rewritten:** `CertSource`, `CertProblem`, `NOT_FOUND`, `CERT_FAILURES_FOR_PROBLEM: Final = 2`, `DAY`, `PROBE_PORT` and the frozen `HostCertState`. `days_left` = `(not_after - now) // DAY`, `problem` applies the D-15 precedence and `is_problem` returns True / None / False. The coordinator is `DataUpdateCoordinator[dict[str, HostCertState]]` and takes a `trust_store: Store | None = None` keyword. `_async_update_data` collects the hosts, takes `dt_util.utcnow()` and gathers `_async_probe_host` (semaphore-wrapped `async_probe_certificate(connect_host, 443, host, handshake_timeout, trust_store, now)`). The old `_probe`, the port dict, the `_reset` seam and every import from the blocking path are gone.
- **History (Task 2):** `_probe_state(host, port, result, previous, now)` reads the previous state from `self.data`. A success resets `failures`/`error` and sets `fetched_at = now`. A failure keeps the previous `certificate`, `verified`, `san_mismatch` and `fetched_at` and sets `failures = previous.failures + 1` (1 without history), `error = code` and `source = probe`. The dict is rebuilt from the current host set, so hosts that leave it disappear in the same cycle. There is no other per-host dict.
- **Entities:** `TraefikCertEntity._state()` / `_days_left()` replace the old row/info/error accessors. `available` = cycle ok and host present. The state token is `(state, days_left)` (binary sensor: `(state, threshold, days_left)`). `certificate_expiry` attributes are exactly `{days_until_expiry, subject, issuer, san, san_mismatch, verified, source, host, port, fetched_at, last_error}`. `certificate_expiring` attributes are exactly `{reason, days_until_expiry, threshold_days, not_after, last_error, verified, source, san_mismatch, host, fetched_at}`.
- **Tests migrated in the same task:** `mock_tls_probe` now patches `cert_coordinator.async_probe_certificate` and returns `ProbeFailure(UNKNOWN, "probe disabled in tests")`. The new `make_cert_state()` builder is in conftest. The sensor/binary-sensor unit tests run on `HostCertState` under `freezer`. `test_cert_entity_state.py` uses the v2.11 capture with the clock frozen at `REFERENCE`, and the availability test now expects a failed-probe row to stay available. Listener count stays 6. New tests cover the failing probe, the secret token, `update_entity`, the trust store through a real probe and probe_failed.

## Task Commits

1. **Task 1 (tracer): probed certificate -> HostCertState -> cert entities, problem-on semantics**
   - RED `5a5c997` test(06-04): add failing tests for per-host certificate state and probe-driven cert entities
   - GREEN `44bcaa8` feat(06-04): per-host certificate state from the threadless probe with problem-on cert entities
   - Tracer gate (auto mode): every `<verify>` command re-run green (109 targeted, 767 full, ruff, format, mypy, 767 on HA 2026.3), then expanded to Task 2
2. **Task 2: probe history, last known certificate, probe_failed after two**
   - RED `7629d90` test(06-04): add failing tests for probe history and probe_failed after two failures
   - GREEN `dc5c662` feat(06-04): keep last known certificate across failed probes and count consecutive failures

## TDD Gate Compliance

| Task | RED evidence | Verdict | Semantic assessment |
|------|--------------|---------|---------------------|
| 1 | `pytest` on the 4 cert test files `--junitxml`, exit 1, 69 failed / 40 passed; target `test_days_left_is_signed_floor_days[not_after0-10]` | `RED_EVIDENCE_OK` (target_test_failed) | The tests import new symbols, so collection needed a throwaway, never-committed stub: the enums, the constants and a `HostCertState` whose methods return None were appended to the old module, plus an ignored `trust_store` kwarg. The target failed on `assert None == 10`. The entity, coordinator and setup tests failed on their assertions against the old semantics. Tests that already passed in RED: the unchanged defaults, collect-host, cap and identity tests. |
| 2 | `pytest tests/test_cert_coordinator.py tests/test_cert_entity_state.py --junitxml`, exit 1, 4 failed / 70 passed; target `test_probe_history_keeps_last_known_certificate_and_counts_failures` | `RED_EVIDENCE_OK` (target_test_failed) | The target failed on `assert None == TraefikCertificate(...)`, because the Task 1 code drops the certificate on failure. The API-state, dropped-host (`failures 1 == 2`) and full-setup probe_failed tests failed on their assertions. |

The RED commits contain tests only, so the tree at `5a5c997` fails at conftest import (the new symbols do not exist yet) and the tree at `7629d90` has 4 failing tests. Each GREEN commit restores a green tree, the same precedent as 06-01..06-03. So D-19 holds per task, not per commit.

## Verification

- `uv run pytest -q`: **771 passed** (724 before this plan)
- `~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`: **771 passed on HA 2026.3.0**
- `uv run ruff check custom_components tests`: all checks passed
- `uv run ruff format --check custom_components tests`: 41 files already formatted
- `uv run mypy --strict custom_components/traefik_proxy`: no issues in 15 source files
- Acceptance Task 1: no `CertInfo|CertError` in the four production files. No `fetch_cert_info` in cert_coordinator/conftest/test_cert_coordinator/test_cert_entity_state/test_entity_manager. No `to_thread` in cert_coordinator. `^class HostCertState:` and `^CERT_FAILURES_FOR_PROBLEM: Final = 2` are present, and const.py has no such constant. `-k "failing_probe or secret or update_entity"`: 3 passed. `tests/test_init.py -k press`: 2 passed.
- Acceptance Task 2: `-k "history or failures or last_known or dropped"`: 4 passed. `-k probe_failed`: 1 passed. No `self._x: dict[` instance dict in cert_coordinator.

## Worker decisions

| Decision | Reason | Alternative not taken |
|---|---|---|
| Planner decisions adopted as listed in 06-04-PLAN.md "Worker decisions (planner)" | Recorded by the planner | — |
| `subject` = `common_name or None` | The probe parses a CN-less leaf as `""`. An empty string means "no CN", so None is the honest value. | Show `""` |
| An empty host set returns `{}` before `_connect_host()` | Nothing to probe means no connect host is needed. The plan's "URL without host -> UpdateFailed" test has a host. | Fail every cycle of a host-less URL even without TLS routers |
| Port 443 as the module constant `PROBE_PORT` | It is one named value that 06-05 replaces with the resolved entrypoint port | Literal `443` at two call sites |
| `_probe_state` is a staticmethod taking `previous` | Pure mapping that is easy to reason about. `_async_probe_states` reads `self.data` once per cycle. | Read `self.data` inside the mapper |
| Cap tests (`test_cert_cycle_cap_250_probes_200`) use successful probes | The failure debug line names the host by design (plan action). The test's "no host names in any record" check is about the cap warning and stays intact with successes. | Narrow the assertion to WARNING records |
| `test_unchanged_cert_notification_writes_nothing` first publishes certificates 30.5 days out | With certificates exactly on a day boundary, floor days drop after one second, so the live day count would legitimately change the token. The half-day offset keeps the test about "unchanged data writes nothing". | Freeze the clock without a tick |
| `test_trust_store_verifies_chain_through_real_probe` redirects port 443 to the local `tls_server` port through a wrapper around the real probe | The coordinator probes 443 until 06-05. A real handshake proves the store object reaches the verifier unchanged (truth D-10/D-24). | Assert only the kwarg identity (also done, separately) |
| `mock_certificate_server` docstring no longer names `fetch_cert_info` (fixture body untouched) | Acceptance grep on conftest. The fixture stays for 06-05 to remove, as the handoff says. | Leave the docstring and fail the gate |
| Stale comment in `tests/test_entity_manager.py` ("reports every host unreachable") reworded | `unreachable` no longer exists as a code | Leave it |

## Deviations from Plan

None in behavior: the plan was executed as written. The test-side adjustments listed under Worker decisions (cap tests, half-day offset, docstring) were needed to migrate existing tests to the new semantics (D-19 "migrated in the same task").

## Requirement status

CERT-02 and CERT-05 are not marked complete: 06-05 (API source, trust anchors, entrypoint port) and 06-06/06-07 (day-boundary timer, aggregate) also declare them. This plan delivers the coordinator half of CERT-02 (connect host = Traefik host, SNI = router host, trust store passed) and the per-host half of CERT-05.

## User-visible changes (for the Phase 8 CHANGELOG)

- New attribute `source` (`probe`; `api` follows in 06-05) on both certificate entities.
- New attribute `verified` on both certificate entities: True only when the presented chain validates against the trust store.
- New attribute `reason` on `certificate_expiring`: `expired`, `probe_failed`, `not_found`, `expiring`, or None when off.
- A failed probe no longer makes certificate entities unavailable. `certificate_expiring` turns on with `probe_failed` after two consecutive failures. `certificate_expiry` keeps its last value (until an HA restart) and stays available. Before the first successful probe both entities are unknown, not unavailable.
- `days_until_expiry` is computed live from the clock (signed floor days) instead of being stored at probe time.
- `last_error` values: `timeout`, `ssl` (now reachable), `dns`, `refused`, `oserror`, `parse`, `empty`, `unknown`, plus `not_found` (06-05). `unreachable` is gone.
- `subject` / `issuer` now hold the common names (`secure.example.com`, `R3`) instead of `CN=…, O=…` strings.
- Probes connect to the Traefik host from the integration URL with the router host as SNI. Router hostnames are no longer resolved through DNS.

## Known Stubs

None. The RED stub of Task 1 was throwaway and never committed.

## Threat Flags

None new. T-06-10: `test_probe_connects_to_traefik_host_with_router_host_as_sni` and `test_probe_driven_setup_publishes_probe_state` assert the connect host argument, and router names are only SNI values. T-06-11: attributes carry certificate metadata and closed-set codes only, probe `detail` is logged at debug level only, and `test_secret_token_never_in_cert_attributes_or_log` checks attributes and the DEBUG log over setup plus two cycles. T-06-13: `data` is rebuilt from the capped host set every cycle, and the instance-dict gate passes.

## `state.update-progress`

Reported "phase scope is unscoped, not complete" (`updated: false`); skipped as instructed. `roadmap.update-plan-progress 06` (4/7, In Progress), `state.advance-plan` (plan 5 of 7), `record-metric`, `add-decision` x4 and `record-session` ran normally.

## Next Phase Readiness

- 06-05 can add the API source by building `HostCertState(source=CertSource.API, port=None, ...)` and `error=NOT_FOUND` for uncovered hosts. It can pass HA's roots as the default `trust_store` (`tls.build_trust_store(client_context().get_ca_certs(binary_form=True))`) and replace `PROBE_PORT` with the resolved TLS entrypoint port. `_probe_state` already keeps an API certificate when a later probe fails.
- The blocking path in `tls.py` (`fetch_cert_info*`, `CertInfo`, `CertError`, `parse_not_after`, `_parse_log_cooldown`) and `mock_certificate_server` are still in place, unused by the coordinator, for 06-05 to delete.
- 06-06: the entities already put the live day count into their write token, so the day-boundary timer only needs to call `async_update_listeners()`.

## Self-Check: PASSED

- FOUND: custom_components/traefik_proxy/cert_coordinator.py (`class HostCertState`, `async_probe_certificate(`), entity.py (`HostCertState`), sensor.py (`class TraefikCertExpirySensor`), binary_sensor.py (`.problem(`), tests/conftest.py (`async_probe_certificate`, `def make_cert_state`)
- FOUND commits (ancestors of HEAD): 5a5c997, 44bcaa8, 7629d90, dc5c662
- Measured: `git rev-list --count 7d56a1f..HEAD` = 4
