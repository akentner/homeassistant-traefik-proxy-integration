---
phase: 08-marketplace-release-readiness
plan: 02
subsystem: data-layer
tags: [cert-coordinator, dns, getaddrinfo, probe-clock, test-hygiene, logging]

requires:
  - phase: 06-certificates
    provides: probe-mode cert cycle, tls.async_probe_certificate, ProbeFailure/ProbeError
  - phase: 07-config-flow-ha-2026-11-baseline-observability
    provides: _logged_cause chaining in the main coordinator
provides:
  - once-per-cycle resolution of the Traefik connect host in probe mode (CertCoordinator._async_resolve_connect_host)
  - certificates_failed chained from _logged_cause (no URL-bearing cause for invalid-URL errors)
  - RAWDATA_PROBE_INTERVAL, _interval_elapsed(since, interval), _probe_clock
  - debug line when the client switches to the paginated list endpoints
  - deterministic socket tests, tls_server teardown that always awaits wait_closed, T-06-13 regression test
  - autouse test resolver (tests/conftest.py traefik_test_dns, MOCK_TRAEFIK_ADDRESS)
affects: [08-12 CHANGELOG, phase verification]

actuals:
  tokens: 10300
  tasks: 3
  commits: 5
plan_head_before: 937be2117cc01897fcbde0eb103a735bfff69ad7
plan_head_after: 595e2e388af53c8b23084f2c6c5d1873ae510dcf

tech-stack:
  added: []
  patterns:
    - "Resolve the Traefik host once per cert cycle via loop.getaddrinfo (asyncio API, no executor call in module source)"
    - "Class-level autouse test resolver for the MOCK_URL host; tests spy by patching the running loop instance"
    - "Socket tests synchronise on server accept events, never on fixed sleeps"

key-files:
  created: []
  modified:
    - custom_components/traefik_proxy/cert_coordinator.py
    - custom_components/traefik_proxy/coordinator.py
    - custom_components/traefik_proxy/api.py
    - tests/conftest.py
    - tests/test_cert_coordinator.py
    - tests/test_cert_entity_state.py
    - tests/test_tls.py
    - tests/test_coordinator.py
    - tests/traefik/capture.py

key-decisions:
  - "A failed connect-host lookup becomes the same ProbeFailure for every host of the cycle (dns/timeout/oserror), so _probe_state keeps its failure semantics with one lookup"
  - "Only the first getaddrinfo address is used (no per-address fallback across the cycle)"
  - "An autouse class-level stub of BaseEventLoop.getaddrinfo maps the MOCK_URL host to 192.0.2.80 because the HA test plugin disables DNS"
  - "The capture docstring says the throwaway certificate is git-ignored (not committed, as the plan assumed)"

patterns-established:
  - "Probe-mode tests assert the resolved address (MOCK_TRAEFIK_ADDRESS) as the connect host and the router host as SNI"

requirements-completed: [REL-04]

coverage:
  - id: D1
    description: "Probe-mode cert cycle resolves the Traefik host once per cycle (none for IP literals); every probe gets the address, SNI stays the router host; a lookup failure is every host's probe failure without connecting, no negative caching"
    requirement: REL-04
    verification:
      - kind: unit
        ref: "tests/test_cert_coordinator.py#test_probe_cycle_resolves_traefik_host_once_per_cycle"
        status: pass
      - kind: unit
        ref: "tests/test_cert_coordinator.py#test_probe_cycle_ip_literal_skips_getaddrinfo"
        status: pass
      - kind: unit
        ref: "tests/test_cert_coordinator.py#test_probe_cycle_resolve_failure_is_dns_for_every_host_without_connecting"
        status: pass
      - kind: unit
        ref: "tests/test_cert_coordinator.py#test_probe_cycle_resolve_error_maps_to_probe_error"
        status: pass
    human_judgment: false
  - id: D2
    description: "certificates_failed is chained from _logged_cause: no cause for an invalid-URL error, the API error otherwise"
    requirement: REL-04
    verification:
      - kind: unit
        ref: "tests/test_cert_coordinator.py#test_certificates_invalid_url_error_chains_no_cause"
        status: pass
      - kind: unit
        ref: "tests/test_cert_coordinator.py#test_certificates_api_error_is_the_chained_cause"
        status: pass
    human_judgment: false
  - id: D3
    description: "Deterministic socket tests (bound non-listening port, accept-event cancellation), tls_server teardown awaits wait_closed on every path, T-06-13 per-host leak regression test; 10 consecutive green runs"
    requirement: REL-04
    verification:
      - kind: unit
        ref: "tests/test_tls.py#test_probe_closed_port_is_refused"
        status: pass
      - kind: unit
        ref: "tests/test_tls.py#test_probe_cancelled_during_handshake_closes_connection"
        status: pass
      - kind: unit
        ref: "tests/test_cert_coordinator.py#test_cancelled_refresh_closes_connection_and_keeps_data"
        status: pass
      - kind: unit
        ref: "tests/test_cert_coordinator.py#test_cert_coordinator_keeps_no_per_host_state_besides_data"
        status: pass
      - kind: other
        ref: "for i in 1..10: uv run pytest tests/test_tls.py tests/test_cert_coordinator.py -q --no-cov -x"
        status: pass
    human_judgment: false
  - id: D4
    description: "RAWDATA_PROBE_INTERVAL decoupled from VERSION_RECHECK_INTERVAL; probe-clock edges (off-grid switch, failing cycle, recovering cycle) pinned; _probe_clock rename"
    requirement: REL-04
    verification:
      - kind: unit
        ref: "tests/test_coordinator.py#test_rawdata_probe_interval_is_one_hour"
        status: pass
      - kind: integration
        ref: "tests/test_coordinator.py#test_rawdata_probe_cadence_ignores_version_recheck_interval"
        status: pass
      - kind: integration
        ref: "tests/test_coordinator.py#test_rawdata_probe_after_off_grid_switch"
        status: pass
      - kind: integration
        ref: "tests/test_coordinator.py#test_rawdata_probe_due_in_failing_cycle_is_not_consumed"
        status: pass
      - kind: integration
        ref: "tests/test_coordinator.py#test_rawdata_probe_due_runs_in_recovering_cycle"
        status: pass
    human_judgment: false
  - id: D5
    description: "One DEBUG line when the switch to the paginated list endpoints is committed; none for a failing fallback"
    requirement: REL-04
    verification:
      - kind: integration
        ref: "tests/test_coordinator.py#test_committed_paginated_switch_is_logged_once"
        status: pass
      - kind: integration
        ref: "tests/test_coordinator.py#test_failing_fallback_logs_no_switch"
        status: pass
    human_judgment: false
  - id: D6
    description: "Capture harness docstring documents fixture byte-stability vs. the throwaway certificate"
    verification:
      - kind: other
        ref: "grep -qi byte-stable tests/traefik/capture.py"
        status: pass
    human_judgment: false

duration: 13min
completed: 2026-11-15
status: complete
---

# Phase 08 Plan 02: Data-layer carried findings Summary

**Probe-mode cert cycles resolve the Traefik host once via `loop.getaddrinfo` and hand the address to every SNI probe; cert-cycle errors chain through `_logged_cause`; the rawdata probe has its own 1 h interval and `_probe_clock`; socket tests synchronise on accept events instead of sleeps.**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-11-15T19:38:17Z
- **Completed:** 2026-11-15T19:51Z
- **Tasks:** 3 (Task 1 tracer)
- **Files modified:** 9

## Accomplishments

- Phase 6 IN-03: `CertCoordinator._async_resolve_connect_host` resolves the entry URL host once per probe cycle (IP literals pass through) within the handshake timeout. A `socket.gaierror` / `TimeoutError` / `OSError` becomes one `ProbeFailure` (DNS / TIMEOUT / OSERROR) that is every host's result for the cycle. No connection is opened, and the existing failure counting and kept certificate still apply. Nothing is cached.
- Phase 7 IN-03: `certificates_failed` is raised `from _logged_cause(err)`, so an invalid-URL aiohttp cause, which may carry userinfo, is dropped.
- Phase 6 IN-04 and the 07 deferred item:
  - The refused-port test keeps its port bound.
  - Both cancellation tests wait for an accept event.
  - The `tls_server` teardown now always awaits `server.wait_closed()` before `pytest.fail`. Before, that await came after `pytest.fail` and never ran.
- T-06-13: a regression test over `vars(coordinator)` fails if the coordinator keeps a per-host container besides `data`. A mutation check confirmed it: a temporary `self._seen_ports = dict(ports)` failed the test, and the change was then reverted.
- Phase 4 IN-12, IN-13 and IN-14:
  - Added `RAWDATA_PROBE_INTERVAL`, `_interval_elapsed(since, interval)` and the `_probe_clock` rename.
  - Matrix row 15 comment reworded.
  - Five new probe tests and two switch-log tests.
  - New debug line "switched to the paginated list endpoints".
- Fixture determinism: the capture docstring now has the byte-stability note.

## Task Commits

1. **Task 1 (tracer): once-per-cycle resolution and cause chaining**
   - `029934a` (test, RED)
   - `4cf98b0` (feat, GREEN)
   - Tracer gate (auto mode): all four `<verify>` commands re-run green before expansion.
2. **Task 2: deterministic socket tests, teardown, per-host leak guard**
   - `bcff94f` (test)
3. **Task 3: probe clock, timing edges, switch log, fixture note**
   - `712c6ec` (test, RED)
   - `595e2e3` (feat, GREEN)

## Results

| Gate | Result |
|------|--------|
| `uv run pytest -q` (dev env) | 1103 passed (baseline 1094 before the plan's new tests; no Lingering) |
| `ruff check custom_components tests` | All checks passed |
| `ruff format --check custom_components tests` | 48 files already formatted |
| `mypy --strict custom_components/traefik_proxy` | no issues (16 files) |
| HA 2026.11.0 venv (`ha2611-venv`, `-p no:respx`) | 1103 passed |
| 10 consecutive runs `tests/test_tls.py tests/test_cert_coordinator.py -x` (after Task 2) | 10/10 green, 173 passed each |
| `pytest tests/test_coordinator.py -k probe` | before: 0 selected; after: 5 passed (+5) |
| `pytest tests/test_cert_coordinator.py -k "resolve or getaddrinfo or cause"` | 10 passed |
| `pytest tests/test_cert_coordinator.py -k "leak or per_host"` | 1 passed |

All acceptance-criteria greps pass. Results:
- `from _logged_cause(err)`: present.
- `getaddrinfo` count: 1.
- `to_thread` / `run_in_executor`: none.
- `asyncio.sleep(0.2)`: none.
- `server.wait_closed` comes before `pytest.fail`.
- `RAWDATA_PROBE_INTERVAL` and the two-parameter `_interval_elapsed`: present.
- `_probe_armed_at`: 0 matches.
- Switch log line and `byte-stable`: present.

## TDD Gate Compliance

- **Task 1 RED:** `test_probe_cycle_resolves_traefik_host_once_per_cycle` failed on its assertion (`[] == ['traefik.example.com']`, no lookup yet). JUnit evidence → `gsd-tools check tdd-red-evidence`: `RED_EVIDENCE_OK`. The other new tests also failed on their planned assertions, for example the invalid-URL cause being chained. Semantic assessment: it failed for the intended reason.
- **Task 3 RED:** `test_rawdata_probe_cadence_ignores_version_recheck_interval` failed with probes every 10 min instead of `[60, 120]`: `RED_EVIDENCE_OK`. The failing-cycle and recovering-cycle tests failed on the missing `_probe_clock` attribute, which is the rename. The behaviour they pin already held at HEAD, as the 04 review predicted for case B. So these two RED failures prove the rename, not new behaviour.
- **Task 2:** test-only hygiene task. The T-06-13 test guards existing behaviour, so it passed right away. A mutation check showed it can fail.
- `workflow.tdd_mode` is false; this section is informational.

## Worker decisions

| Decision | Reason | Alternative not taken |
|---|---|---|
| A resolution failure becomes the same `ProbeFailure` for every host of the cycle (planner decision) | Keeps `_probe_state` semantics with one lookup | Each probe fails on its own lookup (200 lookups again) |
| `RAWDATA_PROBE_INTERVAL` in `coordinator.py` (planner decision) | Both clocks belong to the coordinator | `const.py` |
| `_logged_cause` imported from `.coordinator` as is (planner decision) | No import cycle | Move it to `api.py` |
| Use only the first `getaddrinfo` address | Plan wording; one address for the whole cycle | Per-address fallback, which would mean several lookups or connects per host. Trade-off: a dual-stack Traefik host with a broken first-family route now fails every probe of the cycle. Before, `open_connection` fell back to the next address. |
| Map the lookup error classes explicitly in `cert_coordinator.py` (gaierror → DNS, TimeoutError → TIMEOUT, OSError → OSERROR) and keep the "no address" answer as DNS | Same classes as `tls._classify`, without importing a private helper | Import `tls._classify` |
| Autouse `traefik_test_dns` fixture in `tests/conftest.py`: a class-level `BaseEventLoop.getaddrinfo` stub. It maps the MOCK_URL host to `MOCK_TRAEFIK_ADDRESS` (192.0.2.80) and passes every other name to the real resolver. | The HA test plugin raises `RuntimeError("DNS resolution disabled in tests")`. Every probe-mode setup with the MOCK_URL host would otherwise fail its cert cycle. | Patch the resolution in every probe test, or move the resolver behind a patchable module function |
| Accept-event waits use a 5 s `asyncio.timeout` guard. The existing 1 s EOF guard is unchanged. | Localhost accept is immediate; 5 s only bounds a hang | A 1 s guard for the accept as well |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Test resolver added to `tests/conftest.py` in Task 1. The plan listed conftest only for Task 2.**
- **Found during:** Task 1
- **Issue:** with the resolution in place, every probe-mode test whose entry URL host is `traefik.example.com` would hit the HA plugin's DNS block.
- **Fix:** autouse `traefik_test_dns` plus `MOCK_TRAEFIK_ADDRESS`. `tests/test_cert_entity_state.py`, which is not in the plan's file list, now asserts the resolved address instead of the host name, and its local `CONNECT_HOST` constant is removed.
- **Commit:** `029934a`

**2. [Rule 1 - Factual] Capture docstring: the certificate is git-ignored, not committed**
- **Found during:** Task 3
- **Issue:** the plan and the must-have say "the committed throwaway certificate". `tests/traefik/certs/` is in `.gitignore` (line 34), and `git ls-files` lists no certificate.
- **Fix:** the docstring says the fixtures are byte-stable only while the git-ignored throwaway certificate is kept, and that a fresh checkout or a deleted `certs/` changes the certificate fixtures. Committing the throwaway key was not done: that is a repo-content decision, left to the user or manager.
- **Commit:** `595e2e3`

**Total deviations:** 2. **Impact:** no scope change. The cert-key question stays open for the manager.

## User-visible changes (for the CHANGELOG)

- Probe-mode certificate checks (Traefik < 3.7) resolve the Traefik host once per cycle instead of once per probe. If that lookup fails, every certificate host of the cycle reports the probe failure (`dns` / `timeout` / `oserror`) and no connection is attempted.
- Cert-cycle errors no longer chain a URL-bearing cause into the log: an invalid-URL error has no chained cause.
- Debug logs show when the client switches to the paginated list endpoints.

## Issues Encountered

None.

## Known Stubs

None.

## Next Phase Readiness

- 08-12 can take the CHANGELOG lines above.
- Open for the manager: whether to commit the throwaway capture certificate so that fixtures re-capture byte-stable on a fresh checkout. Today it is git-ignored.

## Self-Check: PASSED

- Files exist: all 9 modified files are present.
- Commits on this branch: `029934a`, `4cf98b0`, `bcff94f`, `712c6ec` and `595e2e3`, all ancestors of HEAD.

---
*Phase: 08-marketplace-release-readiness*
*Completed: 2026-11-15*
