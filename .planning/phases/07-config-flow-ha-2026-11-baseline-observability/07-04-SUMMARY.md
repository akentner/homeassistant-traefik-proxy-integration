---
phase: 07-config-flow-ha-2026-11-baseline-observability
plan: 04
subsystem: api-client-and-error-reporting
tags: [aiohttp, redirects, translations, exceptions, home-assistant-2026.11, reauth]
status: complete

requires:
  - phase: 07-02
    provides: "HA 2026.11 APIs adopted; cert coordinator with own _stopping flag"
  - phase: 07-03
    provides: "translations/en.json as the single English source"
provides:
  - "api.TraefikProxyRedirectError (TraefikProxyConnectionError subclass); allow_redirects=False on the single request"
  - "api.TraefikProxyApiError.detail (non-secret detail of the message)"
  - "coordinator._translated_update_error: one mapping point from client errors to translated HA exceptions"
  - "coordinator._logged_cause: invalid-URL chain dropped before HA's ERROR traceback"
  - "build_api_client raises ConfigEntryAuthFailed(invalid_credentials) for credentials Auth rejects"
  - "exceptions keys auth_failed, api_error, redirect, invalid_url, invalid_credentials, version_unavailable, certificates_failed, no_probe_host in en + de; cert_unavailable removed"
  - "tests/test_translations.py::test_every_exception_key_is_raised_and_translated (AST scan)"
affects: [07-05, 07-08, 07-09, phase-08]

actuals:
  tokens: 7900
  tasks: 2
  commits: 4
plan_head_before: 93a523cef20c9a38f603d978d81cd85ab6dd9f3f
plan_head_after: 9aabda129f9b8f44dcd762d13cf3f36294cab80b

tech-stack:
  added: []
  patterns:
    - "Client errors become HA exceptions in one helper; subclasses (invalid URL, redirect) checked before their bases"
    - "Translation placeholders only from error attributes (path, status, detail), never str(err)"
    - "AST gate: every UpdateFailed/ConfigEntry* in coordinator.py, cert_coordinator.py, __init__.py carries translation_domain and a literal translation_key"

key-files:
  created: []
  modified:
    - custom_components/traefik_proxy/api.py
    - custom_components/traefik_proxy/coordinator.py
    - custom_components/traefik_proxy/cert_coordinator.py
    - custom_components/traefik_proxy/translations/en.json
    - custom_components/traefik_proxy/translations/de.json
    - tests/test_api.py
    - tests/test_coordinator.py
    - tests/test_cert_coordinator.py
    - tests/test_translations.py

key-decisions:
  - "Phase 07: the client never follows redirects; 3xx raises TraefikProxyRedirectError and the coordinator reports the translated key redirect"
  - "Phase 07: an invalid stored URL raises ConfigEntryError(invalid_url) without its aiohttp cause chained, because HA logs ConfigEntryError tracebacks at ERROR"

requirements-completed: [FLOW-05]
requirements-partial: [FLOW-04]  # client half (IN-01) done; flow mapping and 100 % config_flow coverage in 07-08

duration: 9min
completed: 2026-11-15
---

# Phase 7 Plan 04: Redirects never followed, every integration exception translated Summary

The API client sends `allow_redirects=False` and turns a 3xx into `TraefikProxyRedirectError`; every `UpdateFailed` / `ConfigEntryAuthFailed` / `ConfigEntryError` in the coordinators carries a translation key with en + de texts, an unusable stored URL stops setup, and stored credentials the client cannot send open reauth.

## Performance

- **Duration:** ~9 min
- **Started:** 2026-11-15T13:42:59Z
- **Completed:** 2026-11-15T13:51:54Z
- **Tasks:** 2 (Task 1 tracer; both TDD RED + GREEN)
- **Files modified:** 9

## Accomplishments

- D-23 / IN-01 (client half): `_request` passes `allow_redirects=False` on the single `session.get` call; `_status_error` maps 300-399 to `TraefikProxyRedirectError` (message `"<path>: HTTP <status>"`, `Location` never read). `TraefikProxyApiError` keeps `detail`.
- D-25: `_translated_update_error(err)` replaces the three duplicate except ladders (`_async_setup`, `_async_refresh_version`, `_async_update_data`): invalid URL → `ConfigEntryError(invalid_url)`, auth → `ConfigEntryAuthFailed(auth_failed, {path})`, redirect → `UpdateFailed(redirect, {path, status})`, else `UpdateFailed(api_error, {path, detail})`. Missing version → `version_unavailable`.
- `cert_coordinator.py`: `certificates_failed` (`{path}`, `{detail}`) and `no_probe_host`.
- D-15 / IN-04 / IN-08 (runtime half): invalid stored URL → SETUP_ERROR with `error_reason_translation_key == "invalid_url"` (no endless retry); a token `Auth` rejects → `ConfigEntryAuthFailed(invalid_credentials)` from `build_api_client`, reauth flow started, no request sent.
- Translations: 8 exception keys in `en.json` and a new `exceptions` section in `de.json` (informal du, no `://`); `exceptions.cert_unavailable` removed (A-18).
- Tests: redirect not followed / no Location leak / one request; 300/302/307/399 vs 400 classification; `allow_redirects` on every request; redirect scenario added to `test_credentials_never_leak`; setup and cycle redirect; auth/api_error keys and placeholders in the cycle matrix; invalid URL, invalid credentials, version_unavailable; cert keys; `exceptions` in de parity; AST code-key test.

## Task Commits

1. **Task 1 (tracer): redirect surfaces as translated error, never followed**
   - RED `321f0eb` (test) — `test_cycle_redirect_keeps_entry_loaded` failed on `translation_key == "redirect"` (`UpdateFailed('/api/rawdata: HTTP 302')` had none)
   - GREEN `02b255b` (feat)
   - Tracer gate (auto mode): full verify re-run green → expanded to Task 2
2. **Task 2: every coordinator/cert exception translated; no futile retries**
   - RED `e45966b` (test) — `test_request_construction_error_stops_setup_without_traceback` failed on `SETUP_RETRY is SETUP_ERROR`
   - GREEN `9aabda1` (feat)

## TDD Gate Compliance

RED evidence as pytest JUnit XML in the git-ignored `.pytest_cache/gsd-red/`, classified with `gsd-tools check tdd-red-evidence`:

| Target | Verdict | Semantic assessment |
|---|---|---|
| `tests/test_coordinator.py::test_cycle_redirect_keeps_entry_loaded` (`07-04-t1.json`) | RED_EVIDENCE_OK | Failed on the translation-key assertion: the coordinator still raised `UpdateFailed(str(err))` |
| `tests/test_coordinator.py::test_request_construction_error_stops_setup_without_traceback` (`07-04-t2.json`) | RED_EVIDENCE_OK | Failed on the entry-state assertion: the unusable URL still went to SETUP_RETRY (endless retry D-15 removes) |

The RED runs used the HEAD versions of the source files (working-tree source changes restored with `git checkout -- <file>` for the run, then put back); each `feat(07-04)` commit descends from its `test(07-04)` commit. In the Task 1 RED run the `test_api.py` redirect tests failed with `AttributeError` (class not yet defined); the targets above are clean assertion failures.

## Gate results

| Gate | After Task 1 | After Task 2 |
|---|---|---|
| `uv run pytest -q` (dev, HA 2026.11.1) | 864 passed | 867 passed |
| `ruff check custom_components tests` | clean | clean |
| `ruff format --check custom_components tests` (43 files) | clean | clean |
| `uv run mypy --strict custom_components/traefik_proxy` (15 files) | no issues | no issues |
| ha2611-venv suite (HA 2026.11.0) | 864 passed | 867 passed |
| "Lingering" in output | none | none |

No failure occurred in any final gate run; no rerun was used (M39). Acceptance criteria: all Task 1 and Task 2 greps pass; `-k redirect` 11 passed; `-k exception_key` 1 passed; `-k "invalid_url or invalid_credentials or construction"` 2 passed.

Local hassfest: not part of this plan (deferred to Phase 8, Docker unavailable; CI's hassfest job validates the new `exceptions` texts).

## Files Created/Modified

- `custom_components/traefik_proxy/api.py` - `TraefikProxyRedirectError`, 3xx mapping, `allow_redirects=False`, `detail` attribute
- `custom_components/traefik_proxy/coordinator.py` - `_translated_update_error`, `_logged_cause`, guarded `build_api_client`, `version_unavailable`
- `custom_components/traefik_proxy/cert_coordinator.py` - `certificates_failed`, `no_probe_host`
- `custom_components/traefik_proxy/translations/en.json`, `de.json` - `exceptions` section
- `tests/test_api.py`, `tests/test_coordinator.py`, `tests/test_cert_coordinator.py`, `tests/test_translations.py` - see Accomplishments

## Decisions Made

Planner decisions (applied as written): one helper for the three coordinator sites; placeholders from attributes with `detail` newly stored; the 8 exception keys; invalid-URL mapping in Task 2.

Worker decisions:

| Decision | Reason | Alternative |
|---|---|---|
| `_logged_cause(err)` drops the cause chain for `TraefikProxyInvalidUrlError` (`raise … from None`), all other errors keep `from err` | HA 2026.11 logs a setup `ConfigEntryError` with `logger.exception` (traceback at ERROR); below the invalid-URL error sits aiohttp's `InvalidUrlClientError`, whose text is the URL (userinfo possible) | Keep `from err` (credential-bearing URL could reach the ERROR log) |
| `test_other_non_2xx_raise_base_error_with_status` lost its `302` case | 302 is now the redirect subclass; covered by the new classification test | Keep it and expect the subclass there |
| Redirect scenario added to `test_credentials_never_leak` (`Location` = userinfo URL) | Extends the existing secrecy matrix to the new error at no extra cost | Separate test only |
| AST test also rejects a bare `raise <HAException>` and positional messages | Makes "no untranslated exception" structural, not just key equality | Key-set equality only |
| `version_unavailable` test patches `_async_refresh_version` with `AsyncMock` and sets `_version = None` | The branch is unreachable through HTTP (a version refresh always precedes it) | Leave it untested |
| German "Reconfigure" rendered as „Neu konfigurieren“ | HA's German UI label for the reconfigure action | Keep the English word |
| FLOW-04 left `Pending` in REQUIREMENTS.md | 07-08 still delivers the flow mapping and the 100 % `config_flow.py` coverage | Mark complete now |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1/2 - Framework fact + security] "No traceback above DEBUG" is impossible for a `ConfigEntryError` on HA 2026.11**
- **Found during:** Task 2 GREEN
- **Issue:** `homeassistant/config_entries.py` logs a setup `ConfigEntryError` with `logger.exception` at ERROR. The plan's truth "no traceback above DEBUG" for `invalid_url` cannot hold; with `from err` the logged chain would also include aiohttp's error text (for `InvalidUrlClientError` the URL, possibly with userinfo).
- **Fix:** `_logged_cause` drops the chain for invalid-URL errors; the test (renamed `..._stops_setup_without_traceback`) now asserts that HA's own `homeassistant.config_entries` record is the only one above DEBUG with a traceback, that its exception is the translated `invalid_url` error with `__cause__ is None` and `__suppress_context__`, and that aiohttp's message ("Cannot combine") is absent from the log. No integration-owned record carries a traceback.
- **Files modified:** `custom_components/traefik_proxy/coordinator.py`, `tests/test_coordinator.py`
- **Commit:** `9aabda1`

## Issues Encountered

None beyond the deviation above.

## User-visible changes (for the Phase 8 CHANGELOG)

- An http-to-https (or any other) redirect in front of the Traefik API shows a "redirect" error instead of an authentication or connection error; the integration never follows redirects, so credentials never reach the redirect target.
- Error messages in the log and UI are translated (English and German).
- An unusable stored URL stops the setup (error state with a "correct the URL via Reconfigure" message) instead of retrying forever; HA logs this once at ERROR with a traceback that contains no URL.
- Stored credentials the client cannot send (for example a token with a control character) open the re-authentication dialog.

## Self-Check: PASSED
