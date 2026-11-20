---
phase: 06-certificates
plan: 02
subsystem: certificates
tags: [traefik-api, certificates, parser, pagination, test-stubs, frozen-time]

requires:
  - phase: 04
    provides: "TraefikProxyApiClient._get_paginated (per_page/page, X-Next-Page, MAX_PAGES) and the TraefikProxy* error taxonomy"
provides:
  - "models.TraefikCertificate (frozen slots dataclass; UTC not_after/not_before; status str | None)"
  - "models.parse_certificates(payload: object) -> tuple[TraefikCertificate, ...] (strict, naive timestamps rejected)"
  - "TraefikProxyApiClient.async_get_certificates() -> tuple[TraefikCertificate, ...] (paginated, payload errors wrapped, 404 -> TraefikProxyNotFoundError)"
  - "tests/conftest.py: /api/certificates in stub_traefik (certificates= override) and stub_traefik_paginated; CERT_FIXTURE_NOW, STUB_CERT_VALIDITY, frozen_v37_certificates(freezer)"
affects: [06-03, 06-04, 06-05]

actuals:
  tokens: 6400
  tasks: 2
  commits: 4
plan_head_before: b3b2830c28f3422c5282c7cfbf04323f5987de5c
plan_head_after: 7f5552d21d104f0b9dd6ea0203ec2f6b2046a445

tech-stack:
  added: []
  patterns:
    - "Default test stubs serve time-dependent captures re-based on the clock; fixed capture dates only via a helper that freezes time first"
    - "Required timestamps parsed with datetime.fromisoformat and rejected when timezone-less (no guessed expiry)"

key-files:
  created: []
  modified:
    - custom_components/traefik_proxy/models.py
    - custom_components/traefik_proxy/api.py
    - tests/conftest.py
    - tests/test_models.py
    - tests/test_api.py

key-decisions:
  - "TraefikCertificate.status is str | None: the same model will carry probe-read certificates (06-03), which have no API status"
  - "notBefore is required like notAfter: Traefik always serializes both, a missing one means a foreign payload"
  - "/api/certificates is registered in the test stubs already now (inert until 06-04/06-05)"
  - "Default v3.7 stub serves the capture re-based on the clock (notBefore now-1d, notAfter now+3650d); fixed dates only via frozen_v37_certificates(freezer)"
  - "Empty issuerCN / status strings map to None, like a missing key"

patterns-established:
  - "Integration tests that need the real certificate capture dates call frozen_v37_certificates(freezer)"

requirements-completed: []  # CERT-01 data side delivered; CERT-01 is also declared by 06-05, which marks it

coverage:
  - id: D1
    description: "parse_certificates turns the v3.7 capture into one TraefikCertificate with UTC datetimes; Z suffix and +02:00 offset end up in UTC"
    requirement: "CERT-01"
    verification:
      - kind: unit
        ref: "tests/test_models.py#test_captured_certificates_parse, test_certificate_z_suffix_timestamp_is_utc, test_certificate_offset_timestamp_is_converted_to_utc"
        status: pass
    human_judgment: false
  - id: D2
    description: "Strict shape: non-list payload, non-object item, missing/non-string/unparsable/naive notAfter or notBefore raise; optional fields default; no de-duplication"
    requirement: "CERT-01"
    verification:
      - kind: unit
        ref: "tests/test_models.py#test_parse_certificates_shape_errors, test_certificate_optional_fields, test_certificates_are_not_deduplicated_and_keep_payload_order"
        status: pass
    human_judgment: false
  - id: D3
    description: "async_get_certificates: paginated read (per_page/page, X-Next-Page), status/connection/payload errors mapped to the taxonomy without URL or credentials"
    requirement: "CERT-01"
    verification:
      - kind: unit
        ref: "tests/test_api.py#test_certificates_capture_flows_through_the_client, test_certificates_pagination_follows_x_next_page, test_certificates_status_maps_to_taxonomy, test_certificates_connection_error, test_certificates_payload_errors"
        status: pass
    human_judgment: false
  - id: D4
    description: "Test stubs serve /api/certificates (clock-rebased v3.7 capture, 404 on v2.11, override); frozen_v37_certificates freezes to CERT_FIXTURE_NOW"
    requirement: "CERT-01"
    verification:
      - kind: unit
        ref: "tests/test_api.py#test_certificates_stub_v37_is_rebased_on_the_clock, test_certificates_stub_paginated_v37_is_rebased_on_the_clock, test_certificates_stub_v211_answers_404, test_certificates_stub_argument_replaces_payload, test_certificates_frozen_v37_helper_returns_the_capture_under_frozen_time"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-11-15
status: complete
---

# Phase 6 Plan 02: Certificates API Read Path Summary

**`TraefikProxyApiClient.async_get_certificates()` reads every page of Traefik's `/api/certificates` (>= 3.7) and parses it into frozen `TraefikCertificate` models with UTC `not_after`/`not_before`; naive or unparsable timestamps are payload errors, and the test stubs serve the v3.7 capture re-based on the clock (404 on v2.11).**

## Performance

- **Duration:** about 5 min
- **Started:** 2026-11-15T08:05:57Z
- **Completed:** 2026-11-15T08:10:49Z
- **Tasks:** 2 (both TDD: RED commit + GREEN commit, no refactor needed)
- **Files modified:** 5

## Accomplishments

- `models.TraefikCertificate` (`common_name`, `sans`, `not_after`, `not_before`, `issuer_cn`, `status`, `serial_number`) and `parse_certificates()`: list payload and object items required; `notAfter`/`notBefore` required strings, parsed with `datetime.fromisoformat`, rejected without timezone, converted with `.astimezone(UTC)`; optional fields default (`""`, `()`, `None`); payload order kept, no de-duplication. `models.py` stays stdlib-only.
- `api.async_get_certificates()` next to `async_get_entrypoints`: `_get_paginated("/api/certificates")` then `parse_certificates`, `ValueError`/`TypeError`/`KeyError` wrapped into `TraefikProxyPayloadError("/api/certificates", "unexpected payload shape")`. 404/401/403/500/connection errors come from the existing `_request` mapping unchanged.
- `tests/conftest.py`: `CERT_FIXTURE_NOW = 2026-11-15T12:00Z` (88 days before the capture's notAfter), `STUB_CERT_VALIDITY = 3650 d`, `_rebased_certificates()`, `_stub_certificates()`, `frozen_v37_certificates(freezer)`; `stub_traefik(..., certificates=...)` and `stub_traefik_paginated` register `/api/certificates` after their existing endpoints. `restub_traefik` inherits it.

## Task Commits

1. **Task 1: Tracer, v3.7 capture -> client -> TraefikCertificate**
   - RED `c42916d` test(06-02): add failing tests for the v3.7 certificates tracer
   - GREEN `5a04bf1` feat(06-02): parse /api/certificates into TraefikCertificate via the paginated client
   - Tracer gate (auto mode): all `<verify>` commands re-run green -> expanded to Task 2
2. **Task 2: Error taxonomy, strict validation, pagination, test stubs**
   - RED `67295dc` test(06-02): add failing tests for certificate errors, pagination and stubs
   - GREEN `7f5552d` feat(06-02): serve /api/certificates from the Traefik test stubs

## TDD Gate Compliance

| Task | RED evidence | Verdict | Semantic assessment |
|------|--------------|---------|---------------------|
| 1 | `pytest tests/test_models.py tests/test_api.py -k certificate --junitxml`, exit 1, 4 failed / 0 passed; target `test_captured_certificates_parse` | `RED_EVIDENCE_OK` (target_test_failed) | Target ran and failed on its assertion (`() == (TraefikCertificate(...),)`) against a throwaway uncommitted stub (`TraefikCertificate` fields, `parse_certificates` and `async_get_certificates` returning `()`). The Z/offset tests failed unpacking the empty tuple, the client test on `certificates[0]`. |
| 2 | `pytest tests/test_models.py tests/test_api.py -k certificate --junitxml`, exit 1, 4 failed / 50 passed; target `test_certificates_stub_v37_is_rebased_on_the_clock` | `RED_EVIDENCE_OK` (target_test_failed) | Target failed on `not_after == now + 3650 d` (RED stub served the unmodified capture). The paginated stub, `certificates=[]` override and frozen helper tests failed on their assertions too. The parser/client error, pagination and v2.11-404 tests passed already in RED: the Task 1 parser was already strict and `_get_paginated` already follows X-Next-Page (plan step 1 "only if a behavior line fails" -> no `models.py` change in Task 2). |

The RED commits are test-only, so the tree at `67295dc` does not import (`CERT_FIXTURE_NOW` etc. absent from the committed conftest); the GREEN commit after each RED restores a green tree. Same pattern as 06-01.

## Verification

- `uv run pytest -q`: 684 passed (HA dev venv; was 630 before this plan)
- `~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`: **684 passed on HA 2026.3.0**
- `uv run ruff check custom_components tests`: all checks passed
- `uv run ruff format --check custom_components tests`: 40 files already formatted
- `uv run mypy --strict custom_components/traefik_proxy`: no issues in 15 source files
- Acceptance: `pytest tests/test_api.py -k certificates` 29 passed (>= 6), `pytest tests/test_models.py -k certificate` 25 passed (>= 10), `pytest tests/test_coordinator.py` 21 passed with the file unchanged; all grep criteria of both tasks pass; `models.py` has no `homeassistant` import.
- Clock independence: outside `tests/conftest.py`, `certificates.json` is mentioned only by `tests/test_models.py`, `tests/test_api.py`, `tests/test_fixture_redaction.py` and the capture tool `tests/traefik/capture.py` (pre-existing, writes the fixture, not a test).

## Worker decisions

| Decision | Reason | Alternative not taken |
|---|---|---|
| Planner decisions adopted as listed in the plan (status `str \| None`, `notBefore` required, stubs register the endpoint now, clock-rebased default stub) | Recorded by the planner in 06-02-PLAN.md | — |
| An empty `issuerCN` / `status` string maps to `None` (via `_str(...) or None`) | Plan action prescribes `_str(...) or None`; tests pin it (`issuerCN-empty`) | Keep `""` |
| A missing `serialNumber` gives `""` (no error) | Plan action uses `_str`; the serial number is informational | Required field |
| Client error tests run with both basic and bearer credentials | Covers every `_secret_forms()` entry in the exception text check | Bearer only |
| Paginated stub registers `/api/certificates` via the same `_stub_certificates` helper (no `certificates=` argument on `stub_traefik_paginated`) | Plan: "No other helper changes"; the override exists on `stub_traefik` only | Add an override parameter there too |
| RED-only throwaway stubs (models/api in Task 1, conftest in Task 2) kept out of the RED commits | RED commits stay test-only; the stub made RED assertion-based instead of an import error (06-01 precedent) | Commit stubs with the tests |

## Deviations from Plan

None - plan executed exactly as written.

## Requirement status

CERT-01 is **not** marked complete: `requirements.ready-ids` reports it blocked because 06-05 also declares it and has no SUMMARY yet. This plan delivers the data side (read, paginate, parse; 404 for the 06-04 fallback).

## `state.update-progress`

Reported again "phase scope is unscoped, not complete" (`updated: false`); skipped as instructed. `roadmap.update-plan-progress 06` (2/7, In Progress), `state.advance-plan` (plan 3 of 7), `record-metric`, `add-decision` x3 and `record-session` ran normally.

## User-visible changes (for the Phase 8 CHANGELOG)

None by itself: the client can now read Traefik >= 3.7 certificate data; it is used from 06-04.

## Known Stubs

None. (The RED stubs were throwaway and never committed.)

## Threat Flags

None. T-06-03 (strict shape checks, naive/unparsable timestamps rejected, every violation a payload error, one test per shape), T-06-04 (reuses `_get_paginated` with `MAX_PAGES`) and T-06-05 (texts carry only path + status / exception type; tests assert no URL and no credential form) are mitigated as planned. No new endpoint, auth path or file access beyond the planned `GET /api/certificates`.

## Next Phase Readiness

- 06-04 can call `client.async_get_certificates()` and branch on `TraefikProxyNotFoundError` for the probe fallback.
- Default v3.7 setups now serve a certificate valid for 3650 days from the clock; tests needing the real capture dates use `frozen_v37_certificates(freezer)`.
- No production code requests `/api/certificates` yet; every existing request-path assertion is unchanged.

## Self-Check: PASSED

- FOUND: custom_components/traefik_proxy/models.py (`class TraefikCertificate`), custom_components/traefik_proxy/api.py (`async def async_get_certificates`), tests/conftest.py (`/api/certificates`)
- FOUND commits: c42916d, 5a04bf1, 67295dc, 7f5552d (ancestors of HEAD)
