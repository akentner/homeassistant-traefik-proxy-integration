---
phase: 06-certificates
plan: 03
subsystem: certificates
tags: [tls, probe, cryptography, x509-verification, sni, wildcard, rfc6125, asyncio]

requires:
  - phase: 06-02
    provides: "models.TraefikCertificate (status str | None), CERT_FIXTURE_NOW in tests/conftest.py"
provides:
  - "tls.async_probe_certificate(connect_host, port, sni, *, handshake_timeout, trust_store, now) -> ProbeResult (threadless CERT_NONE handshake, never raises except CancelledError)"
  - "tls.ProbedCertificate / ProbeFailure / ProbeError (closed set) / ProbeResult"
  - "tls._PROBE_CONTEXT (shared CERT_NONE client context, nothing loaded)"
  - "tls.build_trust_store(ders) -> Store | None, tls.certificate_from_der(der), tls.chain_verified(chain, host, store, now)"
  - "tls.match_certificate(host, certificates) (exact > single-label wildcard > latest not_after; SANs + CN)"
  - "tls._hostname_matches_san(host, names: Iterable[str]) with the RFC 6125 single-label wildcard rule"
  - "tests/certgen.py (make_ca, make_intermediate, make_leaf, make_self_signed, write_pem, warm_up_datetime_types)"
  - "tests/conftest.py tls_server fixture + TlsServer (port, received, wait_connections)"
affects: [06-04, 06-05]

actuals:
  tokens: 15600
  tasks: 3
  commits: 6
plan_head_before: 7bd939eb3bc17844a84558f07f35d8bec2d3ad43
plan_head_after: 1a9624660fd1c8cf6dfef2f57963281d024fecba

tech-stack:
  added: []
  patterns:
    - "Certificate probe = one CERT_NONE asyncio handshake + offline cryptography.x509.verification against a Store; trust is a reported bool, never a handshake precondition"
    - "Exception classification through an ordered (type, ProbeError) table: TimeoutError > SSLError > gaierror > ConnectionRefusedError > OSError > unknown"
    - "Test TLS servers: one pre-built server SSLContext per certificate, the SNI callback only assigns sslobj.context"
    - "Tests that must wait for server-side callbacks under freezer yield with asyncio.sleep(0) in a bounded loop (timed sleeps never return under a frozen loop clock)"

key-files:
  created:
    - tests/certgen.py
  modified:
    - custom_components/traefik_proxy/tls.py
    - tests/conftest.py
    - tests/test_tls.py
    - tests/test_entity_manager.py

key-decisions:
  - "Planner decisions adopted as listed in 06-03-PLAN.md (TraefikCertificate inside ProbedCertificate, san_mismatch on SANs + CN, IP SAN verification, Store | None, leaf-only parse error, no HA import in tls.py, certgen module, handshake_timeout name, early migration of test_unchanged_notifications_write_no_state)"
  - "_close_writer aborts the transport on any Exception from wait_closed (plan: TimeoutError/OSError) and on CancelledError before re-raising, so the probe keeps its never-raises contract and never leaves a socket open"
  - "_hostname_matches_san never wildcard-matches an IP-literal host and lowercases ASCII only with one trailing dot removed (truth wording) instead of str.lower().rstrip('.')"
  - "conftest calls certgen.warm_up_datetime_types() at import: cryptography caches the datetime class on first use, and a first use under freezer cached freezegun's fake class (order-dependent TypeError)"

patterns-established:
  - "New probe tests generate certificates with tests/certgen.py relative to dt_util.utcnow() under freezer; wall-clock tests (timeout, cancel, abort) never request freezer"

requirements-completed: [CERT-02, CERT-04]  # CERT-04 marked; CERT-02 blocked by 06-04/06-05, which also declare it

coverage:
  - id: D1
    description: "Real CERT_NONE handshake to 127.0.0.1 with a separate SNI name returns the parsed leaf (TraefikCertificate, status None) with verified True for a trusted chain; SNI routing and default certificate"
    requirement: "CERT-02"
    verification:
      - kind: integration
        ref: "tests/test_tls.py#test_probe_reads_verified_certificate_via_sni, test_probe_sni_routing_and_default_certificate"
        status: pass
    human_judgment: false
  - id: D2
    description: "Verification matrix: expired, self-signed, private CA, missing intermediate, other host (san_mismatch), IP SAN (verified), now after notAfter -> honest verified flag"
    requirement: "CERT-02"
    verification:
      - kind: integration
        ref: "tests/test_tls.py#test_probe_expired_leaf_is_read_unverified, test_probe_self_signed_leaf_is_read_unverified, test_probe_private_ca_not_in_store_is_unverified, test_probe_without_intermediate_is_unverified, test_probe_leaf_for_other_host_is_unverified_with_san_mismatch, test_probe_ip_san_with_ip_sni_is_verified, test_probe_verifies_at_given_time_after_not_after"
        status: pass
    human_judgment: false
  - id: D3
    description: "Closed error set (ssl, refused, timeout, dns, empty, parse, unknown), CancelledError propagates, no bytes sent, bounded close with abort, cancellation closes the connection"
    requirement: "CERT-02"
    verification:
      - kind: integration
        ref: "tests/test_tls.py#test_probe_plain_http_server_is_ssl_error, test_probe_closed_port_is_refused, test_probe_hanging_server_is_timeout, test_probe_dns_failure_is_dns, test_probe_empty_peer_certificate_is_empty, test_probe_non_der_peer_certificate_is_parse, test_probe_unexpected_exception_is_unknown, test_probe_cancelled_error_propagates, test_probe_aborts_transport_when_wait_closed_hangs, test_probe_cancelled_during_handshake_closes_connection, test_probe_sends_no_bytes_after_handshake"
        status: pass
    human_judgment: false
  - id: D4
    description: "build_trust_store: None without roots, skips garbage, HA client-context roots without CryptographyDeprecationWarning"
    requirement: "CERT-02"
    verification:
      - kind: unit
        ref: "tests/test_tls.py#test_build_trust_store_without_roots_is_none, test_build_trust_store_skips_unparsable_roots, test_build_trust_store_from_ha_roots_records_no_warning"
        status: pass
    human_judgment: false
  - id: D5
    description: "Single-label wildcard matching and match_certificate (exact > wildcard > latest not_after; CN counts; nameless never returned; U-label never equals A-label)"
    requirement: "CERT-04"
    verification:
      - kind: unit
        ref: "tests/test_tls.py#test_hostname_matches_san (15 cases), test_hostname_matches_san_empty_san_rejects_all, test_hostname_matches_san_wildcard_does_not_match_attacker_suffix, test_match_certificate_* (7)"
        status: pass
    human_judgment: false
  - id: D6
    description: "test_unchanged_notifications_write_no_state runs on mock_tls_probe + CERT_FIXTURE_NOW, independent of the cert data type"
    requirement: "CERT-02"
    verification:
      - kind: integration
        ref: "tests/test_entity_manager.py#test_unchanged_notifications_write_no_state"
        status: pass
    human_judgment: false

duration: 16min
completed: 2026-11-15
status: complete
---

# Phase 6 Plan 03: Threadless Certificate Probe Summary

**`tls.async_probe_certificate()` reads any certificate a TLS server presents (expired, self-signed and private-CA ones included) through one CERT_NONE asyncio handshake with a separate SNI name. It parses the DER leaf with `cryptography` into `TraefikCertificate` and reports trust honestly via offline `x509.verification` against a `Store`. Every failure maps to exactly one closed-set `ProbeError`. Wildcards now cover exactly one label, and `match_certificate()` maps a host to its API certificate.**

## Performance

- **Duration:** about 16 min
- **Started:** 2026-11-15T08:13:13Z
- **Completed:** 2026-11-15T08:29Z
- **Tasks:** 3 (all TDD: RED commit + GREEN commit, no refactor commit)
- **Files:** 1 created, 4 modified

## Accomplishments

- **Probe (`tls.py`, additive):** module-level `_PROBE_CONTEXT` (`PROTOCOL_TLS_CLIENT`, `check_hostname=False`, `CERT_NONE`, nothing loaded). `async_probe_certificate` opens the connection under `asyncio.timeout(handshake_timeout)`, reads `getpeercert(binary_form=True)` and `get_unverified_chain() or [der]`, and returns `ProbedCertificate(certificate, verified, san_mismatch)`. It never writes to the stream. `_close_writer` closes the connection on every path: `wait_closed` is bounded by the same timeout and followed by `transport.abort()`.
- **Classification:** an ordered table `TimeoutError -> timeout`, `ssl.SSLError -> ssl`, `socket.gaierror -> dns`, `ConnectionRefusedError -> refused`, `OSError -> oserror`, anything else `-> unknown`. No peer certificate gives `empty`, a leaf `ValueError` gives `parse`, and `asyncio.CancelledError` propagates. `detail` is `"<Type>: <message>"`, for debug logs only.
- **Parsing / trust:** `certificate_from_der` reads the first subject CN (or `""`), the first issuer CN (or None), the SAN DNS names followed by the IP SANs, `not_valid_*_utc` and `str(serial_number)`; every parse problem raises `ValueError`. `build_trust_store` suppresses `CryptographyDeprecationWarning`, skips roots that do not parse and returns None for an empty result. `chain_verified` checks against `IPAddress` subjects for IP literals and `DNSName` subjects otherwise, ignores intermediates that do not parse, and returns False on a None store, `VerificationError` or `ValueError`.
- **Matching:** `_hostname_matches_san(host, names: Iterable[str])` lets a wildcard cover exactly one label, compares with ASCII lowercasing and one trailing dot removed, applies no Unicode normalization and matches IP literals only by equality. `match_certificate` ranks the candidates `sans ∪ {CN}`: exact beats wildcard, and the latest `not_after` breaks ties. The blocking `CertInfo` path uses the same helper, so its `san_mismatch` follows the new rule.
- **Test infrastructure:** `tests/certgen.py` (EC P-256 CA, intermediate, leaf and self-signed certificates with the extensions the verifier requires, plus a PEM writer) and the `tls_server` fixture (pre-built server context per certificate, SNI callback, received-bytes log, `wait_connections` that works under freezer). The old `mock_certificate_server` stays untouched until 06-05.
- **Switch preparation:** `test_unchanged_notifications_write_no_state` now uses `mock_tls_probe` + `freezer.move_to(CERT_FIXTURE_NOW)`. Its own probe patch, the `_fixed_cert` helper and the `CertInfo` import are gone.

## Task Commits

1. **Task 1: Tracer, real CERT_NONE handshake with SNI**
   - RED `8c58aa2` test(06-03): add failing tracer test for the threadless CERT_NONE probe
   - GREEN `0400772` feat(06-03): add threadless CERT_NONE certificate probe with offline chain verification
   - Tracer gate (auto mode): every `<verify>` command re-run green, then expanded to Task 2
2. **Task 2: Verification matrix, error classification, no data sent, bounded close, cancellation**
   - RED `192a5ee` test(06-03): add failing tests for probe error classes, verification matrix and bounded close
   - GREEN `df50fbe` feat(06-03): classify probe failures into a closed set and bound the connection close
3. **Task 3: Single-label wildcard, match_certificate, switch-independent test**
   - RED `b2927f1` test(06-03): add failing tests for single-label wildcard matching and match_certificate
   - GREEN `1a96246` feat(06-03): single-label wildcard matching and API host-to-certificate mapping

## TDD Gate Compliance

| Task | RED evidence | Verdict | Semantic assessment |
|------|--------------|---------|---------------------|
| 1 | `pytest tests/test_tls.py -k 'probe or certgen' --junitxml`, exit 1, 2 failed / 3 passed; target `test_probe_reads_verified_certificate_via_sni` | `RED_EVIDENCE_OK` (target_test_failed) | The target failed on `isinstance(result, ProbedCertificate)` against a throwaway uncommitted stub (`async_probe_certificate` returned None). The SNI-routing test failed the same way. The certgen extension checks passed already (they test the test helper). |
| 2 | `pytest tests/test_tls.py --junitxml`, exit 1, 8 failed / 51 passed; target `test_probe_plain_http_server_is_ssl_error` | `RED_EVIDENCE_OK` (target_test_failed) | The target failed on `failure.error is ProbeError.SSL` (got UNKNOWN) against a throwaway wrapper that mapped every exception to unknown. refused/timeout/dns/empty/parse/unknown and the abort test failed on their assertions. The verification matrix, no-bytes, cancellation and trust-store tests passed already in RED: Task 1 had implemented `chain_verified`/`build_trust_store` completely, and asyncio closes the transport itself when a handshake is cancelled. |
| 3 | `pytest tests/test_tls.py tests/test_entity_manager.py -k 'matches_san or match_certificate or test_unchanged…' --junitxml`, exit 1, 6 failed / 19 passed; target `test_hostname_matches_san[a.b.example.com-names1-False]` | `RED_EVIDENCE_OK` (target_test_failed) | The target failed on `is False` (the old label-count rule returned True). The IP-wildcard case and four `match_certificate` cases (throwaway stub returning None) failed on assertions. The migrated entity-manager test passed in RED, as planned (it must be green before and after). |

The RED commits are test-only, so the trees at `8c58aa2`, `192a5ee` and `b2927f1` do not import or fail. The GREEN commit after each RED restores a green tree (06-01/06-02 precedent). D-19's "no red intermediate commits" therefore holds per task, not per commit.

## Verification

- `uv run pytest -q`: **724 passed** (HA dev venv; 684 before this plan)
- `~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`: **724 passed on HA 2026.3.0** (cryptography 46.0.5)
- `uv run ruff check custom_components tests`: all checks passed
- `uv run ruff format --check custom_components tests`: 41 files already formatted
- `uv run mypy --strict custom_components/traefik_proxy`: no issues in 15 source files
- `tests/test_tls.py` re-run 6x (dev) and 3x (ha2603): 59 passed every time (checks the plain-HTTP `ssl` classification and the timing tests for flakiness)
- Acceptance, Task 1: `async_probe_certificate` and `_PROBE_CONTEXT` greps pass; `homeassistant` does not appear in `tls.py`; `make_leaf`/`tls_server` present; `-k probe` 20 passed
- Acceptance, Task 2: matrix selection 18 passed (>= 6), error selection 25 passed (>= 9), `received or no_bytes or abort or trust_store` 5 passed (>= 3); no `freezer` on timeout/cancel tests
- Acceptance, Task 3: `match_certificate` present; no `host_lower.count`; `-k "matches_san or match_certificate"` 24 passed (>= 20); no `traefik_proxy.tls import` or `cert_coordinator.fetch_cert` in `tests/test_entity_manager.py`; the migrated test passes

## Worker decisions

| Decision | Reason | Alternative not taken |
|---|---|---|
| Planner decisions adopted as listed in 06-03-PLAN.md "Worker decisions (planner)" | Recorded by the planner | — |
| `_close_writer` aborts on any `Exception` from `wait_closed` (plan: TimeoutError or OSError) and also on `CancelledError` before re-raising it | Keeps the "never raises except CancelledError" contract and never leaves a socket open when the probe task is cancelled while closing | Catch only `(TimeoutError, OSError)` |
| IP-literal hosts never wildcard-match (`*.168.1.10` does not cover `192.168.1.10`); extra test case | RFC 6125: wildcards apply to DNS names only; the plain label rule would otherwise match | No IP guard |
| Normalization: ASCII-only lowercase (`str.translate`) + `removesuffix(".")` | Follows the truth "ASCII-lowercased names with one trailing dot removed, no Unicode normalization" (the action said `.lower().rstrip(".")`) | `str.lower().rstrip(".")` |
| A missing `ssl_object` counts as `empty`, like a None peer certificate | No certificate can be read; same class as "no peer certificate" | `unknown` |
| `TlsServer.wait_connections(n)` yields with `asyncio.sleep(0)` up to 10 000 times, then fails | Under `freezer` timed sleeps and `asyncio.timeout` never fire (P3); a bounded loop fails instead of hanging | `asyncio.Event` without a bound |
| Abort test wraps the probe in an outer `asyncio.timeout(handshake_timeout + 1)` | An unbounded `wait_closed` (pre-fix behaviour) failed the test instead of hanging the suite. The first RED run hung and was killed. | Rely on an external pytest timeout (not installed) |
| Plain-HTTP and hanging servers come from a local `tcp_server` fixture in `tests/test_tls.py` | Only these tests use them; conftest stays focused | Put them in conftest |
| `san_mismatch` candidates leave out an empty CN | `""` never covers a host; avoids a meaningless candidate | Always append the CN |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Order-dependent `TypeError` from cryptography under `freezer`**
- **Found during:** Task 2 (acceptance selection `-k "received or no_bytes or abort or trust_store"`)
- **Issue:** `cryptography` resolves and caches `datetime.datetime` on first use. When that first use happened inside a `freezer` test, it cached freezegun's `HAFakeDatetime`, and every later real datetime (e.g. `make_ca` in a non-frozen test) failed with `TypeError: 'datetime' object is not an instance of 'HAFakeDatetime'`. The full file passed only because a non-frozen certgen test ran first.
- **Fix:** `tests/certgen.warm_up_datetime_types()` creates one certificate and reads `not_valid_after_utc`; `tests/conftest.py` calls it at import time, before any test freezes the clock. Production code is unaffected (no freezegun).
- **Files modified:** tests/certgen.py, tests/conftest.py
- **Verification:** the failing selection passes 3/3 runs; full suites green on both HA versions
- **Commit:** df50fbe

**Total deviations:** 1 auto-fixed (Rule 1). **Impact:** test infrastructure only; it also protects 06-04/06-05 tests that combine `freezer` with generated certificates against test-order failures.

## Requirement status

`requirements.ready-ids`: **CERT-04 marked complete**. CERT-02 is blocked, because 06-04 and 06-05 also declare it and have no SUMMARY yet. This plan delivers the probe half of CERT-02 (the coordinator wiring comes in 06-04).

## `state.update-progress`

Reported "phase scope is unscoped, not complete" (`updated: false`) again; skipped as instructed. `roadmap.update-plan-progress 06` (3/7, In Progress), `state.advance-plan` (plan 4 of 7), `record-metric`, `add-decision` x4 and `record-session` ran normally.

## User-visible changes (for the Phase 8 CHANGELOG)

- None by itself: the new probe is wired in 06-04.
- **Wildcard SAN matching now covers exactly one label** (also in the existing blocking probe path): a host like `a.b.example.com` behind a `*.example.com` certificate now reports `san_mismatch: true` (before: false).

## Known Stubs

None. (The RED stubs were throwaway and never committed.)

## Threat Flags

None. T-06-06 (nothing sent: `received` holds only `b""` after every probe; trust reported via `verified`), T-06-07 (parsing only through `cryptography`; leaf failure `parse`, malformed intermediates skipped, verifier errors `verified=False`), T-06-08 (`asyncio.timeout` on connect and `wait_closed`, `transport.abort()` fallback, cancellation closes the connection, all tested) and T-06-09 (`ProbeFailure.detail` debug-only) are mitigated as planned. No new endpoint, auth path or file access in production code. The only file access is PEM writes in test `tmp_path`.

## Next Phase Readiness

- 06-04 can call `async_probe_certificate(traefik_host, port, router_host, handshake_timeout=TLS_HANDSHAKE_TIMEOUT, trust_store=..., now=dt_util.utcnow())` inside the existing semaphore. It can build the store once via `build_trust_store(homeassistant.util.ssl.client_context().get_ca_certs(binary_form=True))` and map API certificates with `match_certificate`.
- `mock_tls_probe` still patches `cert_coordinator.fetch_cert_info_async`; 06-04 must re-point it to the new probe. `test_unchanged_notifications_write_no_state` depends only on the fixture, not on the result type.
- The blocking path (`fetch_cert_info*`, `CertInfo`, `CertError`, `parse_not_after`, `_parse_log_cooldown`, `mock_certificate_server`) is still in place for 06-05 to remove.

## Self-Check: PASSED

- FOUND: tests/certgen.py (`def make_leaf`), tests/conftest.py (`def tls_server`), custom_components/traefik_proxy/tls.py (`async def async_probe_certificate`, `def match_certificate`, `_PROBE_CONTEXT`)
- FOUND commits (ancestors of HEAD): 8c58aa2, 0400772, 192a5ee, df50fbe, b2927f1, 1a96246
- Measured: `git rev-list --count 7bd939e..HEAD` = 6
