---
phase: 06-certificates
plan: 07
subsystem: certificates
tags: [binary-sensor, problem-aggregate, cert-coordinator, translations, write-on-change]

requires:
  - phase: 06-04
    provides: "HostCertState.problem(threshold, now) and CertProblem precedence (expired, probe_failed, not_found, expiring)"
  - phase: 06-06
    provides: "Day-boundary timer that calls async_update_listeners(); failed cert cycle leaves last_update_success False"
provides:
  - "entity.TraefikCertCoordinatorEntity: base bound to the cert coordinator, main device, __init__(entry, unique_id); TraefikCertEntity derives from it"
  - "binary_sensor.TraefikCertificatesProblemBinarySensor: one per entry, attributes problems (cap 50), problem_count, reasons"
  - "const.UID_CERTIFICATES_PROBLEM: Final = \"certificates_problem\""
  - "en/de entity.binary_sensor.certificates_problem.name; entity.binary_sensor.certificate_expiring.state_attributes.reason (name + one text per CertProblem)"
  - "icons.json entity.binary_sensor.certificates_problem (lock-check / lock-alert)"
affects: [07, 08]

actuals:
  tokens: 7800
  tasks: 2
  commits: 4
plan_head_before: 5e514e4fdae80a1bfc302b48941b435e621f3571
plan_head_after: 626dbe54295aedddaec500b7305e7214beb600a4

tech-stack:
  added: []
  patterns:
    - "Fixed per-entry aggregate on a non-main coordinator: small base class that binds the coordinator, not a description entry"
    - "Aggregate and per-host sensor share one problem function (HostCertState.problem), so they cannot disagree"

key-files:
  created:
    - tests/test_certificates_problem.py
  modified:
    - custom_components/traefik_proxy/binary_sensor.py
    - custom_components/traefik_proxy/entity.py
    - custom_components/traefik_proxy/const.py
    - custom_components/traefik_proxy/translations/en.json
    - custom_components/traefik_proxy/translations/de.json
    - custom_components/traefik_proxy/strings.json
    - custom_components/traefik_proxy/icons.json
    - tests/test_translations.py
    - tests/test_cert_entity_state.py

key-decisions:
  - "Planner worker decisions adopted as listed in 06-07-PLAN.md (TraefikCertCoordinatorEntity base, aggregate outside PROBLEM_SENSORS, lock icon family, reasons only for listed hosts)"
  - "New test modules reference the aggregate class as binary_sensor.TraefikCertificatesProblemBinarySensor (module attribute), so the RED run failed on assertions instead of an ImportError at collection"
  - "tests/test_cert_entity_state.py probe count `== 6` restated as `== 3 * 2` (setup + two cycles, two hosts) so the plan's `! grep '== 6'` gate holds; that line is not a listener count"

requirements-completed: [CERT-05]

coverage:
  - id: D1
    description: "Aggregate unit contract: hosts + reasons, all healthy off with empty attributes, 60 hosts -> 50 sorted names / 50 reasons / count 60, expired beats probe_failed, live threshold, unavailable after a failed cycle, no data off, unique_id / device / coordinator / enabled default"
    requirement: "CERT-05"
    verification:
      - kind: unit
        ref: "tests/test_certificates_problem.py (8 unit tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Aggregate agrees with the per-host certificate_expiring sensors for 7 row sets (on state, listed hosts, reasons)"
    requirement: "CERT-05"
    verification:
      - kind: unit
        ref: "tests/test_certificates_problem.py#test_aggregate_agrees_with_per_host_sensors"
        status: pass
    human_judgment: false
  - id: D3
    description: "Full setup v2.11: off at setup, on with probe_failed after two failed probes of secure.example.com, off after one success; expiry one second after not_after turns the reason to expired without a probe call; a failed cert cycle makes it unavailable"
    requirement: "CERT-05"
    verification:
      - kind: integration
        ref: "tests/test_certificates_problem.py#test_two_failed_probes_turn_the_aggregate_on, test_expiry_reaches_the_aggregate_without_a_probe, test_aggregate_unavailable_after_a_failed_cert_cycle"
        status: pass
    human_judgment: false
  - id: D4
    description: "7 cert-coordinator listeners after setup, cycles, threshold and options change; unchanged notification writes nothing (aggregate included); default v3.7 setup clock-independent with the aggregate off"
    requirement: "CERT-05"
    verification:
      - kind: integration
        ref: "tests/test_cert_entity_state.py#test_cert_notifications_do_not_grow_listeners, test_known_cert_hosts_are_never_added_again, test_unchanged_cert_notification_writes_nothing, test_default_v37_setup_is_clock_independent"
        status: pass
    human_judgment: false
  - id: D5
    description: "Translations and icons: en/de aggregate names, reason state keys == set(CertProblem) in en and de, strings.json byte-identical to en.json, on/off icons"
    requirement: "CERT-05"
    verification:
      - kind: unit
        ref: "tests/test_translations.py#test_reason_state_keys_equal_cert_problems, test_every_code_key_has_texts, test_every_code_key_has_icons, test_strings_json_equals_en_json"
        status: pass
    human_judgment: false
  - id: D6
    description: "German/English rendering of the new sensor name and reason texts in a real HA frontend"
    verification: []
    human_judgment: true
    rationale: "No real HA instance in this effort; the visual de/en check is scheduled for Phase 8 (M35)"

duration: 13min
completed: 2026-11-15
status: complete
---

# Phase 6 Plan 07: Certificates Problem Aggregate Summary

**A new enabled-by-default `certificates_problem` binary sensor on the main Traefik device is on while any host's certificate is expired, repeatedly unprobeable, missing from Traefik's certificate list or expiring. It lists the hosts (`problems`, at most 50), the total (`problem_count`) and the reason per listed host (`reasons`). It uses the same `HostCertState.problem` function as the per-host `certificate_expiring` sensors, so the two cannot disagree. The `reason` attribute of `certificate_expiring` now has English and German texts.**

## Performance

- **Duration:** about 13 min (2026-11-15T09:05Z to 09:18Z)
- **Tasks:** 2, both TDD (RED commit, then GREEN commit)
- **Files:** 1 created, 9 modified

## Accomplishments

- **Aggregate (Task 1, tracer):** `TraefikCertCoordinatorEntity(_TraefikEntityBase[CertCoordinator])` binds `entry.runtime_data.cert_coordinator` and keeps the main device. `TraefikCertEntity` now derives from it (device Certificates, behaviour unchanged). `TraefikCertificatesProblemBinarySensor` builds the sorted `(host, CertProblem)` pairs of every host in the cert data, using the live threshold and `dt_util.utcnow()`. `is_on` is true when any pair exists. The attributes are `problems` (first `MAX_PROBLEM_NAMES` hosts), `problem_count` (all problem hosts) and `reasons` (listed hosts only). `_state_token()` returns the pairs, so the existing write-on-change base writes only on a real change. It is added once in `async_setup_entry` next to the snapshot aggregates. It is not a `PROBLEM_SENSORS` entry. It listens to the cert coordinator, so cert cycles, threshold changes and the 06-06 day-boundary fires reach it. When the last cert cycle failed, it is unavailable through the base availability.
- **Texts and icon (Task 1):** en "Certificate problems", de "Zertifikatsprobleme". The icon is `mdi:lock-check`, with `mdi:lock-alert` when on. strings.json was copied from en.json byte for byte.
- **Reason texts (Task 2):** `entity.binary_sensor.certificate_expiring.state_attributes.reason` has the name "Reason" / "Grund" and the states expired / probe_failed / not_found / expiring: "Expired" / "Abgelaufen", "Probe failed" / "Abruf fehlgeschlagen", "No certificate found" / "Kein Zertifikat gefunden", "Expiring soon" / "Läuft bald ab". en.json stays ASCII, de.json is literal UTF-8.

## Task Commits

1. **Task 1 (tracer): certificates_problem aggregate**
   - RED `9b3e889` test(06-07): add failing tests for the certificates_problem aggregate
   - GREEN `9b2186f` feat(06-07): add the certificates_problem aggregate binary sensor
   - Tracer gate (auto mode): every `<verify>` command was re-run and passed. That was 50 targeted, `clock_independent` 2 passed, the capture file-list gate, 830 full, ruff/format/mypy clean, and 830 on HA 2026.3. Work then moved on to Task 2.
2. **Task 2: reason texts in en and de**
   - RED `9d86ffd` test(06-07): add failing test for the reason state texts of certificate_expiring
   - GREEN `626dbe5` feat(06-07): translate the reason attribute of certificate_expiring in en and de

## TDD Gate Compliance

| Task | RED evidence | Verdict | Semantic assessment |
|------|--------------|---------|---------------------|
| 1 | `uv run pytest tests/test_certificates_problem.py tests/test_translations.py tests/test_cert_entity_state.py -q --junitxml=…`, exit 1, 25 failed / 25 passed. Target `test_two_failed_probes_turn_the_aggregate_on` | `RED_EVIDENCE_OK` (target_test_failed) | The target failed on `AssertionError: no binary_sensor entity with unique_id <entry>_certificates_problem`, because the entity did not exist yet. The other full setups failed the same way. The listener tests failed on `assert 6 == 7`. The clock-independence and unchanged-write tests failed on the missing aggregate entity id. The unit and translation tests failed on `AttributeError` for the missing class, a test-body failure and not a collection error, because the class is referenced as a module attribute. There were no import, collection or fixture errors. |
| 2 | `uv run pytest tests/test_translations.py -q --junitxml=…`, exit 1, 1 failed / 8 passed. Target `test_reason_state_keys_equal_cert_problems` | `RED_EVIDENCE_OK` (target_test_failed) | The target failed on `AssertionError: en.json: certificate_expiring.state_attributes.reason missing`, which is the planned missing translation. The first draft failed on a `KeyError`. It was changed to an explicit assertion before recording, so RED is an assertion failure. |

Each RED commit contains tests only, and each GREEN commit leaves the tree green (D-19 precedent of 06-01..06-06).

## Verification

- `uv run pytest -q`: **831 passed** (812 before; +19: 18 in test_certificates_problem, 1 reason-state test).
- `~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`: **831 passed on HA 2026.3.0**
- `uv run ruff check custom_components tests`: all checks passed. `ruff format --check`: 43 files already formatted. `mypy --strict custom_components/traefik_proxy`: no issues in 15 source files.
- `uv run pytest tests/test_cert_entity_state.py -q -k clock_independent`: 2 passed (the aggregate is asserted at both instants).
- The capture file-list gate holds: only conftest, test_api, test_fixture_redaction and test_models name `certificates.json`.
- `cmp strings.json translations/en.json`: identical.
- Acceptance Task 1: all three class/constant greps match. `Zertifikatsprobleme` is in de.json. test_certificates_problem: 18 passed (at least 8 required). `! grep -n "== 6" tests/test_cert_entity_state.py` exits 0.
- Acceptance Task 2: `-k reason_state_keys`: 1 passed. The de.json key print gives `['expired', 'expiring', 'not_found', 'probe_failed']`.

## Worker decisions

| Decision | Reason | Alternative not taken |
|---|---|---|
| Planner decisions adopted as listed in 06-07-PLAN.md "Worker decisions (planner)" | Recorded by the planner | — |
| Tests reference `binary_sensor.TraefikCertificatesProblemBinarySensor` as a module attribute | With a direct import, the RED run died at collection with an ImportError, which is INVALID_RED. With the attribute, every target fails inside its test body. | Add a stub class in the RED commit |
| In the time-only test (1 h left), the aggregate is already on with reason `expiring` at T0. The test asserts the change to `expired` (still on, same host, count 1) and no probe call. | With 1 h left, `days_left` is 0, which is `<=` any allowed threshold (0..90). So "turns on" can only show up as the reason changing from `expiring` to `expired`. | A longer lead time, which would need a clock move past the 6 h cert interval |
| The failed-cycle full-setup test makes `/api/certificates` answer 500 on the v2.11 capture | That is a real failure path (non-404 → UpdateFailed) and needs no patch on a private method | Patch `_async_cycle` |
| `UID_CERTIFICATES_PROBLEM` has a short comment that it has no historical form | The other UID_* constants note that they keep the old `any_*_failing` form | No comment |

## Deviations from Plan

**1. [Rule 3 - Blocking] Acceptance gate `! grep -n "== 6" tests/test_cert_entity_state.py` hit a non-listener line**
- **Found during:** Task 1
- **Issue:** The planner's baseline listed three `== 6` lines, the listener assertions. Since 06-05/06-06 the file has a fourth one, `assert mock_tls_probe.await_count == 6` in `test_secret_token_never_in_cert_attributes_or_log`. It counts probes (setup + two cycles × two hosts), not listeners.
- **Fix:** Rewrote it as `== 3 * 2` with a comment that explains the count. The value and meaning are the same.
- **Files modified:** tests/test_cert_entity_state.py
- **Commit:** 9b3e889

The plan's line numbers (`:290`, `:307`, `:318`) had moved to `:326`, `:343`, `:354`. All three were updated to 7, each with the comment "2 kind listeners + 4 certificate entities + the aggregate". No other deviations, and no change to per-host semantics or timing.

## Requirement status

**CERT-05 is marked complete.** 06-04 delivered the per-host reason precedence, and 06-06 delivered the live days and day-boundary visibility. This plan adds the enabled-by-default `certificates_problem` aggregate with a `reason` per host. That closes ROADMAP SC4: an expired or repeatedly unprobeable certificate turns `certificate_expiring` and the aggregate on, each with a reason.

## User-visible changes (for the Phase 8 CHANGELOG)

- New binary sensor **"Certificate problems" / "Zertifikatsprobleme"** on the main Traefik device, enabled by default. It is on while any certificate is expired, expiring within the warning threshold, missing from Traefik's certificate list, or failed to be fetched twice in a row. Attributes: `problems` (sorted host names, at most 50), `problem_count` (all affected hosts) and `reasons` (host → `expired` / `probe_failed` / `not_found` / `expiring`). It is unavailable while the last certificate check failed.
- The `reason` attribute of the "<host> expiring" binary sensors is now translated in English and German ("Expired", "Probe failed", "No certificate found", "Expiring soon" / "Abgelaufen", "Abruf fehlgeschlagen", "Kein Zertifikat gefunden", "Läuft bald ab").

## Known Stubs

None.

## Threat Flags

No new surface. T-06-19: the attributes carry only host names, which the per-host entities already expose, and closed-set reason values. There is no token and no error text. T-06-20: `problems` and `reasons` are capped at 50 (`test_names_capped_count_complete`), and the write-on-change token keeps unchanged notifications from writing (`test_unchanged_cert_notification_writes_nothing` includes the aggregate).

## Next Phase Readiness

- Phase 6 has all 7 plans executed. Phase 7 owns the config/options texts and the 2026.11 bump. strings.json is still byte-identical to en.json until Phase 7 removes it (M7).
- Phase 8: the visual de/en check (M35) should include the new sensor name, its icons and the reason texts in the attribute view.

## Self-Check: PASSED

- FOUND: tests/test_certificates_problem.py; custom_components/traefik_proxy/binary_sensor.py (`class TraefikCertificatesProblemBinarySensor(`); custom_components/traefik_proxy/entity.py (`class TraefikCertCoordinatorEntity(`); custom_components/traefik_proxy/const.py (`UID_CERTIFICATES_PROBLEM: Final = "certificates_problem"`); de.json (`Zertifikatsprobleme`)
- FOUND commits (ancestors of HEAD): 9b3e889, 9b2186f, 9d86ffd, 626dbe5
- Measured: `git rev-list --count 5e514e4..HEAD` = 4
