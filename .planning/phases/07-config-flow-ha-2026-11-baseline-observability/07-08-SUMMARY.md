---
phase: 07-config-flow-ha-2026-11-baseline-observability
plan: 08
subsystem: config-flow
tags: [config-flow, errors, redirect, url-credentials, translations, coverage, home-assistant-2026.11]
status: complete

requires:
  - phase: 07-04
    provides: "TraefikProxyRedirectError (3xx, never followed), message without URL"
  - phase: 07-05
    provides: "_async_probe_errors, _check_url_shape, _collect_credentials, auth selector, url_unique_id/url_host"
provides:
  - "config_flow._async_probe(hass, data) -> dict[str, str]: the only probe-error -> form-error mapping, incl. the 'unknown' catch-all with _LOGGER.exception"
  - "config_flow.Redirect, config_flow.UrlHasCredentials sentinels; InvalidUrl always raised without arguments"
  - "config_flow._url_errors(url): URL shape -> invalid_url, then URL credentials -> url_has_credentials (user, reconfigure)"
  - "Fixed error order in user/reconfigure: URL shape, URL credentials, duplicate, credential fields, probe"
  - "Final en + de texts for every config.error key (invalid_url, url_has_credentials, invalid_auth, cannot_connect, api_disabled, redirect, required, unknown) and config.abort.already_configured"
  - "config_flow.py 100 % line coverage from the flow test modules"
affects: [07-09, phase-08]

actuals:
  tokens: 8060
  tasks: 2
  commits: 4
plan_head_before: 3fc435fabb049a47485b1cabdb48993e4d82eb32
plan_head_after: 6f1ab6726f5a18c7fc00cd830ae86549d2c4955a

tech-stack:
  added: []
  patterns:
    - "Sentinel exceptions without arguments carry no user input; one helper maps them to form error keys"
    - "Error matrix test drives user, reauth and reconfigure through one _run_step helper"

key-files:
  created: []
  modified:
    - custom_components/traefik_proxy/config_flow.py
    - custom_components/traefik_proxy/translations/en.json
    - custom_components/traefik_proxy/translations/de.json
    - tests/test_config_flow.py
    - tests/test_reconfigure.py

key-decisions:
  - "Phase 07: a 3xx answer to the flow probe is the form error 'redirect' (user, reauth, reconfigure); the redirect is never followed"
  - "Phase 07: credentials in a newly entered URL are their own form error 'url_has_credentials'; a malformed URL is reported as invalid_url first"
  - "Phase 07: an unexpected exception during flow validation is 'unknown' and logged once with a fixed message (no URL, no credentials)"

requirements-completed: [FLOW-04]

coverage:
  - id: D1
    description: "302 probe answer -> errors {'base': 'redirect'} in user, reauth and reconfigure; exactly one request, Location host never contacted; entry unchanged; 301/307/308 -> Redirect, 400/500 -> CannotConnect"
    requirement: FLOW-04
    verification:
      - kind: integration
        ref: "tests/test_config_flow.py#test_user_step_redirect_shows_redirect_error, test_reauth_redirect_shows_redirect_error, test_validate_input_maps_redirect_status_to_redirect, test_validate_input_maps_other_error_status_to_cannot_connect; tests/test_reconfigure.py#test_reconfigure_redirect_shows_redirect_error"
        status: pass
    human_judgment: false
  - id: D2
    description: "Error matrix per step (user, reauth, reconfigure): 401/403 invalid_auth, 404 api_disabled, 500/ClientError/TimeoutError cannot_connect, 302 redirect, request-construction error invalid_url; one request, nothing stored"
    requirement: FLOW-04
    verification:
      - kind: integration
        ref: "tests/test_config_flow.py#test_error_matrix_probe_failure_maps_to_its_key, test_error_matrix_request_construction_error_is_invalid_url"
        status: pass
    human_judgment: false
  - id: D3
    description: "url_has_credentials in user and reconfigure (zero requests), reauth with a stored userinfo URL; InvalidUrl/UrlHasCredentials carry no args (IN-09); shape decided before credentials"
    requirement: FLOW-04
    verification:
      - kind: integration
        ref: "tests/test_config_flow.py#test_user_step_url_has_credentials, test_check_url_shape_rejects_userinfo, test_check_url_shape_raises_on_bad_urls, test_check_url_shape_reports_shape_before_credentials, test_validate_input_maps_request_construction_error_to_invalid_url, test_reauth_stored_url_has_credentials; tests/test_reconfigure.py#test_reconfigure_url_has_credentials"
        status: pass
    human_judgment: false
  - id: D4
    description: "Unexpected exception -> 'unknown' in all three steps; exactly one ERROR record from custom_components.traefik_proxy.config_flow with exc_info; no URL host, token, username or password in caplog"
    requirement: FLOW-04
    verification:
      - kind: integration
        ref: "tests/test_config_flow.py#test_unknown_error_is_logged_once_without_input, test_unknown_error_log_has_no_basic_credentials"
        status: pass
    human_judgment: false
  - id: D5
    description: "Empty/blank URL -> invalid_url without request (user, reconfigure); error order shape > URL credentials > duplicate > fields > probe"
    requirement: FLOW-04
    verification:
      - kind: integration
        ref: "tests/test_config_flow.py#test_user_step_empty_url_is_invalid_url, test_user_step_error_order; tests/test_reconfigure.py#test_reconfigure_unusable_url_is_invalid_url"
        status: pass
    human_judgment: false
  - id: D6
    description: "config_flow.py 100 % line coverage (194 statements, 0 missed) from test_config_flow, test_reconfigure, test_options_flow, test_verify_ssl; no pragma: no cover"
    requirement: FLOW-04
    verification:
      - kind: unit
        ref: "uv run pytest -q -o addopts='-p no:respx' --cov=custom_components.traefik_proxy ... && uv run coverage report --include='*/custom_components/traefik_proxy/config_flow.py' --fail-under=100"
        status: pass
    human_judgment: false
  - id: D7
    description: "en and de carry exactly the eight config.error keys and already_configured; no empty text, no '://', no placeholders"
    requirement: FLOW-07
    verification:
      - kind: unit
        ref: "tests/test_config_flow.py#test_flow_error_keys_have_texts; tests/test_translations.py#test_de_matches_en_keys_and_placeholders"
        status: pass
    human_judgment: true
    rationale: "Wording and rendering in the frontend is the Phase 8 visual check (M35)"

duration: 12min
completed: 2026-11-15
---

# Phase 7 Plan 08: Flow error mapping and config_flow coverage Summary

**Setup, re-authentication and reconfigure now name every failure with its own translated key — `redirect` for a 3xx answer, `url_has_credentials` for credentials typed into the address, `unknown` (logged once, without input) for anything unexpected — through one `_async_probe` helper, with `config_flow.py` at 100 % line coverage.**

## Performance

- **Duration:** ~12 min (14:45Z - ~14:57Z)
- **Tasks:** 2 (Task 1 tracer; both TDD RED + GREEN)
- **Files modified:** 5

## Accomplishments

- `config_flow.py`
  - `Redirect` sentinel; `_validate_input` catches `TraefikProxyRedirectError` before the generic `TraefikProxyApiError, TimeoutError` branch (RESEARCH Pitfall 6).
  - `_async_probe_errors` (07-05) renamed to `_async_probe`; it maps `InvalidUrl`, `UrlHasCredentials`, `InvalidAuth`, `ApiDisabled`, `Redirect`, `CannotConnect` and ends with `except Exception:` -> `_LOGGER.exception("Unexpected error while validating the Traefik connection")` -> `unknown`. All three steps call it (`await _async_probe(` x3).
  - `UrlHasCredentials` sentinel. `_check_url_shape` raises `InvalidUrl` (no arguments) for scheme/host/parse/port errors and only then `UrlHasCredentials` for any userinfo (also an empty one, `https://@host`). No `raise InvalidUrl(...)` with an argument is left (IN-09).
  - `_url_errors(url)` turns the shape check into form errors; user and reconfigure call it first, so only the first failing stage is reported (shape, URL credentials, duplicate, credential fields, probe).
- `translations/en.json` / `de.json`: final texts for all eight `config.error` keys and `config.abort.already_configured`, describing Traefik's middleware auth model (basicAuth/forwardAuth in front of `api@internal`); German with "du"; no `://`.
- Tests: redirect tests per step, a 7-answer x 3-step error matrix, construction-error matrix, url_has_credentials (user, reconfigure, reauth with a stored userinfo URL), `unknown` per step with caplog checks, empty-URL and error-order tests, a translation-key test; existing userinfo tests switched from `invalid_url` to `url_has_credentials`.

## Task Commits

1. **Task 1: redirect error through one probe helper (tracer)**
   - RED `6deb9c3` (test)
   - GREEN `b64ae94` (feat)
2. **Task 2: url_has_credentials, unknown, error matrix, final texts, 100 % coverage**
   - RED `3e3f43f` (test)
   - GREEN `6f1ab67` (feat)

## TDD Gate Compliance

RED evidence as pytest JUnit XML in the git-ignored `.pytest_cache/gsd-red/`, recorded before each GREEN commit and classified with `gsd-tools check tdd-red-evidence`.

| Target | Record | Verdict | Semantic assessment |
|---|---|---|---|
| `tests/test_config_flow.py::test_user_step_redirect_shows_redirect_error` | `07-08-t1.json` | RED_EVIDENCE_OK | Ran and failed on the errors assertion (`cannot_connect` instead of `redirect`); no collection/fixture fault |
| `tests/test_config_flow.py::test_user_step_url_has_credentials` | `07-08-t2.json` | RED_EVIDENCE_OK | Ran and failed on the errors assertion (`invalid_url` instead of `url_has_credentials`); no collection/fixture fault |

At Task 1 RED 6 redirect tests failed (`_validate_input` tests via `AttributeError` on the missing `Redirect`, flow tests on the errors assertion). At Task 2 RED 20 tests failed (url_has_credentials/args assertions, `unknown` tests via the uncaught `RuntimeError("boom")`, two order cases); the matrix cases for existing keys passed already (they are coverage tests). The Task 2 RED tests referenced `config_flow.UrlHasCredentials` through the module so the file still collected; GREEN switched to the direct import.

Tracer gate (auto mode): after Task 1 GREEN all verify commands were re-run end-to-end and passed before Task 2 started.

## Gate results

| Gate | After Task 1 | After Task 2 |
|---|---|---|
| `uv run pytest -q` (dev env) | 967 passed | 1010 passed |
| "Lingering" in output | none | none |
| `ruff check custom_components tests` | clean | clean |
| `ruff format --check custom_components tests` (44 files) | clean | clean |
| `uv run mypy --strict custom_components/traefik_proxy` (15 files) | no issues | no issues |
| ha2611-venv suite (HA 2026.11.0) | 967 passed | 1010 passed |
| config_flow.py coverage gate | - | 100 % (194 stmts, 0 missed), `--fail-under=100` exit 0 |

No failure in any gate run; no rerun used (M39). Acceptance: Task 1 - `except TraefikProxyRedirectError` and `async def _async_probe` present, `await _async_probe(` count 3, `config.error.redirect` in en and de, `-k redirect` 6 passed (>= 4). Task 2 - no `raise InvalidUrl(` with argument, `class UrlHasCredentials` and `"url_has_credentials"` present, `_LOGGER.exception(` present, no `pragma: no cover`, all eight keys in en and de, no `://` in translations, `-k "unknown or url_has_credentials or matrix or empty or order"` 43 passed (>= 10).

Local hassfest (throwaway `docker run --rm -v "$PWD":/github/workspace ghcr.io/home-assistant/hassfest`): `Integrations: 1, Invalid integrations: 0`. No container left behind.

## Files Created/Modified

- `custom_components/traefik_proxy/config_flow.py` - sentinels, `_url_errors`, `_async_probe` with `unknown`, step order
- `custom_components/traefik_proxy/translations/en.json`, `de.json` - final flow error texts
- `tests/test_config_flow.py` - redirect, matrix, unknown, url_has_credentials, empty, order, translation-key tests
- `tests/test_reconfigure.py` - redirect and url_has_credentials tests, empty URLs

## Decisions Made

Planner decisions (applied as written): fixed error precedence (first failing stage only); coverage gate on the flow test modules only; separate `invalid_url` and `url_has_credentials` keys.

Worker decisions:

| Decision | Reason | Alternative |
|---|---|---|
| Renamed 07-05's `_async_probe_errors` to `_async_probe` instead of adding a helper | The planning facts predate 07-05's dedup; one helper with the planned name keeps a single mapping | Keep both names |
| `_url_errors` maps the direct URL check in user/reconfigure; `_async_probe` maps the same sentinels when they come through `_validate_input` (reauth, defensive) | The URL must be decided before the duplicate check, which must precede the probe; reusing `_async_probe` there would send a request | Call `_check_url_shape` with inline try/except in each step (duplicated mapping) |
| An empty userinfo (`https://@host`) counts as credentials (`username is not None`) | The old truthiness check let `https://@host` through; aiohttp would then build an odd authority | Only non-empty user/password |
| Reauth with a stored userinfo URL shows `url_has_credentials` (tested) | Migration removes userinfo (D-14), but the probe path must not fall to `unknown`; covers the last two lines for 100 % | `# pragma: no cover` (forbidden by the plan) |
| `cannot_connect` text names TLS verification for a self-signed certificate | A certificate error is an aiohttp `ClientError` and lands here; it is the most common setup failure in a homelab | Generic text only |
| `invalid_auth` keeps the sentence about control characters / colon | The same key marks a field the client cannot send (07-05) | Separate field-level key (out of scope: no new key planned) |
| Translation-key test asserts the exact set of `config.error` keys | A new flow error without text, or a stale text, fails the test | Subset check only |
| Kept the dedicated redirect tests next to the matrix's 302 case | They assert the Location host is never contacted and the entry is unchanged per step (T-07-16); the matrix asserts the key | Fold into the matrix only |
| FLOW-04 marked Complete; FLOW-07 left Pending | This plan delivers the flow mapping and coverage; 07-09 lists FLOW-07 for the whole-file de parity | Mark both |
| Ran local hassfest | Docker is available and translations changed | Defer to CI |

## Deviations from Plan

None in scope - plan executed as written. Notes:
- The translation-key test (`test_flow_error_keys_have_texts`) and the two coverage tests for the probe-path `invalid_url`/`url_has_credentials` were added in the Task 2 GREEN commit while closing the coverage gate, not in the RED commit.
- The plan's "one rerun of tests/test_cert_entity_state.py allowed (D-33)" clause is void per M39; no rerun was needed or used.

## Issues Encountered

None.

## Known Stubs

None.

## User-visible changes (for the Phase 8 CHANGELOG)

- The setup, re-authentication and reconfigure forms show specific errors: "redirect" when Traefik answers with a redirect (enter the target address, usually HTTPS), "credentials in the address" when a user name or password is typed into the URL (use the authentication fields), and "unexpected error" (details in the log, without address or credentials) instead of Home Assistant's generic error.
- A 404 explains how to enable Traefik's API and route it to `api@internal`; a rejected login points to the basicAuth/forwardAuth middleware.
- All form error texts are available in English and German.

## Next Phase Readiness

07-09 (repair, diagnostics, whole-file de parity, FLOW-07 completion) can build on the final `config` texts; no open item from this plan.

## Self-Check: PASSED
