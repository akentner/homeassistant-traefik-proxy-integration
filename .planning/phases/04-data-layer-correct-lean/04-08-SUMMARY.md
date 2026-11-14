---
phase: 04-data-layer-correct-lean
plan: 08
subsystem: api
tags: [traefik, aiohttp, error-taxonomy, config-flow, userinfo, credentials, gap-closure, home-assistant]

requires:
  - phase: 04-05
    provides: "TraefikProxyApiClient error taxonomy incl. TraefikProxyInvalidUrlError, per-request Authorization header, _validate_input flow mapping"
  - phase: 04-07
    provides: "Previous gap plan of this wave (no code overlap)"
provides:
  - "api.py: aiohttp request-construction ValueError in _request and reload_routers -> TraefikProxyInvalidUrlError('<path>: ValueError')"
  - "config_flow.py: _check_url_shape / _validate_input reject URL userinfo unless allow_userinfo=True (reauth_confirm and YAML import opt out)"
  - "tests: real-session userinfo regression test, mocked mapping tests, leak scenario, setup-retry test, 9 flow tests"
affects: [phase-07-auth-selector, phase-08-changelog]

actuals:
  tokens: 4540
  tasks: 2
  commits: 4
plan_head_before: ce60ec9b4d52128d7d4d83946c4d9e00f6eaf968
plan_head_after: 73986d3d2b8090421aa493822840d30733a64faa

tech-stack:
  added: []
  patterns:
    - "Catch-all ValueError last in the network try block (after InvalidUrlClientError and ClientError), JSON decode kept outside"
    - "Strict-by-default validation keyword (allow_userinfo=False) with an explicit, commented opt-out per flow step"
    - "Real aiohttp.ClientSession in one test where aioclient_mock would bypass the behaviour under test"

key-files:
  created: []
  modified:
    - custom_components/traefik_proxy/api.py
    - custom_components/traefik_proxy/config_flow.py
    - tests/test_api.py
    - tests/test_coordinator.py
    - tests/test_config_flow.py
    - tests/test_reconfigure.py

key-decisions:
  - "Request-construction ValueError maps to TraefikProxyInvalidUrlError (a connection error), so setup retries via the unchanged D-16 path"
  - "Userinfo rejected only for newly entered URLs (user, reconfigure); reauth_confirm and YAML import pass allow_userinfo=True (W19)"
  - "Setup-retry test asserts no exc_info record above DEBUG, because HA itself logs ConfigEntryNotReady as DEBUG 'Full exception' with exc_info"

patterns-established:
  - "Any new config-flow step rejects URL credentials unless it opts out with a stated reason"

requirements-completed: []

coverage:
  - id: D1
    description: "Real aiohttp session: userinfo URL + bearer token raises TraefikProxyInvalidUrlError from async_get_version, async_get_state and reload_routers, message is path + 'ValueError' only (WR-02)"
    requirement: DATA-04
    verification:
      - kind: unit
        ref: "tests/test_api.py#test_userinfo_url_with_bearer_token_raises_invalid_url_error"
        status: pass
    human_judgment: false
  - id: D2
    description: "Mocked request-construction ValueError maps to TraefikProxyInvalidUrlError on the read path and reload_routers; invalid JSON stays a payload error"
    requirement: DATA-04
    verification:
      - kind: unit
        ref: "tests/test_api.py#test_request_construction_value_error_maps_to_invalid_url"
        status: pass
      - kind: unit
        ref: "tests/test_api.py#test_invalid_json_raises_payload_error"
        status: pass
    human_judgment: false
  - id: D3
    description: "No credential form or userinfo URL in logs, str or repr for the new mapping (basic and bearer)"
    requirement: DATA-04
    verification:
      - kind: unit
        ref: "tests/test_api.py#test_credentials_never_leak[request-construction-*]"
        status: pass
    human_judgment: false
  - id: D4
    description: "Entry hitting a request-construction error ends in SETUP_RETRY without 'Unexpected error fetching' and without a traceback above DEBUG"
    requirement: DATA-04
    verification:
      - kind: integration
        ref: "tests/test_coordinator.py#test_request_construction_error_retries_setup_without_traceback"
        status: pass
    human_judgment: false
  - id: D5
    description: "User and reconfigure steps refuse userinfo URLs with invalid_url and send no request; shape check strict by default, opt-in keeps the scheme check"
    requirement: DATA-04
    verification:
      - kind: unit
        ref: "tests/test_config_flow.py#test_check_url_shape_rejects_userinfo"
        status: pass
      - kind: unit
        ref: "tests/test_config_flow.py#test_check_url_shape_allows_userinfo_when_opted_in"
        status: pass
      - kind: unit
        ref: "tests/test_config_flow.py#test_validate_input_rejects_userinfo_url_without_request"
        status: pass
      - kind: integration
        ref: "tests/test_config_flow.py#test_user_step_rejects_userinfo_url"
        status: pass
      - kind: integration
        ref: "tests/test_reconfigure.py#test_reconfigure_rejects_userinfo_url"
        status: pass
    human_judgment: false
  - id: D6
    description: "Reauth and YAML import on a userinfo URL reach the client: with a token -> invalid_url after exactly one /api/version request; reauth without a token completes"
    requirement: DATA-04
    verification:
      - kind: unit
        ref: "tests/test_config_flow.py#test_validate_input_maps_request_construction_error_to_invalid_url"
        status: pass
      - kind: integration
        ref: "tests/test_config_flow.py#test_reauth_confirm_userinfo_url_with_token_maps_construction_error"
        status: pass
      - kind: integration
        ref: "tests/test_config_flow.py#test_reauth_confirm_userinfo_url_without_token_succeeds"
        status: pass
      - kind: integration
        ref: "tests/test_config_flow.py#test_yaml_step_userinfo_url_with_token_maps_construction_error"
        status: pass
    human_judgment: false

duration: 7min
completed: 2026-11-14
status: complete
---

# Phase 4 Plan 08: Request-construction errors mapped, URL credentials refused on new input (WR-02) Summary

**aiohttp's "Cannot combine AUTHORIZATION header ... credentials encoded in URL" ValueError now leaves the client as `TraefikProxyInvalidUrlError('<path>: ValueError')`, and the user and reconfigure steps refuse URLs with embedded credentials before any request, while reauth and YAML import still reach the client and get `invalid_url` instead of a traceback.**

## Performance

- **Duration:** about 7 min
- **Started:** 2026-11-14T02:13:00Z (RED commit ledger recorded 02:16:24Z)
- **Completed:** 2026-11-14T02:20:30Z
- **Tasks:** 2 (tracer + expansion)
- **Files modified:** 6 (2 production, 4 test)

## Accomplishments

- `api.py`: `except ValueError` added as the last clause of the network try block in `_request` and `reload_routers`, after `InvalidUrlClientError` (itself a ValueError subclass) and `(ClientError, TimeoutError, OSError)`. It raises `TraefikProxyInvalidUrlError(path, "ValueError") from err`. JSON decoding stays outside the block, so invalid JSON is still a `TraefikProxyPayloadError`. `TraefikProxyInvalidUrlError` docstring extended.
- `config_flow.py`: `_check_url_shape(url, *, allow_userinfo=False)` raises `InvalidUrl` for `parsed.username or parsed.password`; `_validate_input(hass, data, *, allow_userinfo=False)` forwards it. `async_step_user` and `async_step_reconfigure` keep the strict default; `async_step_reauth_confirm` (stored URL, not editable there) and `async_step_yaml` (existing YAML imports) pass `allow_userinfo=True` with a one-line comment each. Error keys, except branches and the outer timeout are unchanged.
- Tests: real-session regression test, parametrized mocked mapping test, `request-construction` leak scenario (basic + bearer), setup-retry test, 8 config-flow tests and 1 reconfigure test.

## Observed error strings (requested by the plan)

Real aiohttp session, base URL `https://u:p@192.0.2.1:1`, bearer token `t`:

| Entry point | `str(err)` | `type(err)` | `__cause__` |
|---|---|---|---|
| `async_get_version()` | `/api/version: ValueError` | `TraefikProxyInvalidUrlError` | `ValueError` |
| `async_get_state()` | `/api/rawdata: ValueError` | `TraefikProxyInvalidUrlError` | `ValueError` |
| `reload_routers()` | `/api/http/routers/refresh: ValueError` | `TraefikProxyInvalidUrlError` | `ValueError` |

None of the messages contains `u:p` or `192.0.2.1`. Before the fix the bare aiohttp error escaped: `ValueError: Cannot combine AUTHORIZATION header with AUTH argument or credentials encoded in URL` (aiohttp/client.py:789, dev venv aiohttp 3.14.5).

## Task Commits

1. **Task 1 (tracer): userinfo URL + bearer -> TraefikProxyInvalidUrlError -> SETUP_RETRY**
   - RED `6890f51` test(04-08): add failing userinfo URL taxonomy test
   - GREEN `8291802` fix(04-08): map aiohttp request-construction errors to TraefikProxyInvalidUrlError
   - Tracer gate (auto mode): `<verify>` re-run after the commit passed (91 tests in test_api.py + test_coordinator.py); continued with expansion.
2. **Task 2: userinfo rejection on new input, reauth/YAML opt-out, gates**
   - RED `7558154` test(04-08): add failing userinfo URL flow tests
   - GREEN `73986d3` fix(04-08): reject embedded credentials in newly entered URLs

## TDD Gate Compliance

- **RED 1** (`6890f51`): `test_userinfo_url_with_bearer_token_raises_invalid_url_error` failed with the bare `ValueError: Cannot combine AUTHORIZATION header with AUTH argument or credentials encoded in URL` from aiohttp/client.py:789. That is exactly the WR-02 reproduction.
- **Negative control for Task 1's mocked tests:** with HEAD's api.py restored temporarily, `test_request_construction_value_error_maps_to_invalid_url[read-path]`, `[reload_routers]` and `test_request_construction_error_retries_setup_without_traceback` all failed; restored to the GREEN file afterwards. These tests were committed together with the GREEN change, as the plan's action step 5 prescribes.
- **RED 2** (`7558154`): 8 tests failed on the planned assertions: the 4 `test_check_url_shape_rejects_userinfo` cases (no InvalidUrl), `test_check_url_shape_allows_userinfo_when_opted_in` (`TypeError: unexpected keyword argument 'allow_userinfo'`), `test_validate_input_rejects_userinfo_url_without_request`, `test_user_step_rejects_userinfo_url` (request sent: `No mock registered for GET https://u:p@.../api/version`) and `test_reconfigure_rejects_userinfo_url`. The reauth, YAML and `_validate_input` mapping tests already passed at RED, as expected: they rely on Task 1's mapping and guard against Task 2 over-rejecting on the opt-out paths.
- GREEN commits use `fix(04-08):` as the plan prescribes for a gap-closure fix. No REFACTOR commit was needed.

## Files Created/Modified

- `custom_components/traefik_proxy/api.py`: ValueError clause in `_request` and `reload_routers`, docstring of `TraefikProxyInvalidUrlError`
- `custom_components/traefik_proxy/config_flow.py`: `allow_userinfo` in `_check_url_shape` and `_validate_input`, opt-out in reauth_confirm and yaml, `InvalidUrl` docstring
- `tests/test_api.py`: `test_userinfo_url_with_bearer_token_raises_invalid_url_error`, `test_request_construction_value_error_maps_to_invalid_url`, `CONSTRUCTION_ERROR`, `request-construction` scenario
- `tests/test_coordinator.py`: `test_request_construction_error_retries_setup_without_traceback`, `import logging`
- `tests/test_config_flow.py`: 8 new tests, `_userinfo_entry` and `_version_requests` helpers, `USERINFO_URL` / `CONSTRUCTION_ERROR` constants
- `tests/test_reconfigure.py`: `test_reconfigure_rejects_userinfo_url`

## Gate Results

- `.venv/bin/pytest -q`: 508 passed
- `.venv/bin/ruff check custom_components tests`: all checks passed
- `.venv/bin/ruff format --check custom_components tests`: 33 files already formatted
- `.venv/bin/mypy --strict custom_components`: no issues in 13 source files
- HA 2026.3.0 venv `~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`: 508 passed
- Acceptance greps: `except ValueError` in api.py 4; `parsed.username or parsed.password` 1 line; `allow_userinfo: bool = False` 2; non-comment `allow_userinfo=True` 2; `allow_userinfo` in user..yaml range 0 and in reconfigure range 0; new config-flow test names 8; `test_reconfigure_rejects_userinfo_url` 1; non-comment `errors["base"] = "invalid_url"` 4; `id="request-construction"` 1; RED test fails at `6890f51`.

## Decisions Made

- The plan's decisions (mapping to the connection-error subclass, strict default with opt-out, reauth/YAML opt-out per W19, real session in one test) were implemented as written. W20 (basicAuth-protected Traefik without token cannot be newly added until Phase 7) applies unchanged.

## Worker Decisions

- Setup-retry test asserts "no exc_info record above DEBUG" instead of "no record with exc_info". Reason: HA's `config_entries` always logs `ConfigEntryNotReady` as a DEBUG "Full exception" record with exc_info (config_entries.py line 825 dev, 826 HA 2026.3); the negative control shows the narrowed assertion still fails without the fix. Alternative: filter by logger name/message.
- New docstrings and comments in production code say "basic auth gets its own selector later" instead of naming D-08 / Phase 7. Reason: M22 removes planning references from shipped code; no new ones added. Alternative: plan wording with D-xx / phase numbers.
- `_validate_input` docstring avoids the literal `allow_userinfo=True`. Reason: the acceptance grep counts non-comment occurrences and expects exactly the 2 call sites. Alternative: put the hint in a `#` comment.
- Reauth-with-token test additionally asserts the stored token is unchanged (`"old"`); reauth-without-token test asserts the stored token becomes `""`. Reason: proves the failed probe writes nothing and the success path writes the entry. Alternative: assert only the flow result.
- `test_check_url_shape_allows_userinfo_when_opted_in` uses `ftp://u:p@...` as the "bad scheme still raises" case. Reason: proves the opt-in skips only the userinfo rule even when userinfo is present. Alternative: a bad-scheme URL without userinfo.
- `invalid_url` translation text left unchanged although it does not mention credentials; logged in deferred-items.md. Reason: translation files are outside files_modified and the plan forbids changing error keys. Alternative: extend en/de text now.
- REQUIREMENTS.md left untouched (DATA-04 not marked complete); `requirements-completed: []`. Reason: orchestrator rule, phase is re-verified after all gap plans. Alternative: executor protocol's mark-complete step.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug in test spec] Setup-retry exc_info assertion narrowed to records above DEBUG**
- **Found during:** Task 1
- **Issue:** The planned assertion "no caplog record has exc_info set" failed with the fix in place, because HA logs every `ConfigEntryNotReady` as `logger.debug("Full exception", exc_info=True)`. That record is HA behaviour, not an escaping traceback.
- **Fix:** assert no exc_info record with `levelno > logging.DEBUG`; comment in the test explains why. Negative control (HEAD api.py) still fails the test.
- **Files modified:** tests/test_coordinator.py
- **Commit:** 8291802

## Deferred Issues

- `invalid_url` text does not mention URL credentials (deferred-items.md, open).

## User-visible changes (Phase 8 CHANGELOG)

- Setting up or reconfiguring the integration with a URL that contains credentials (`https://user:pass@host`) now shows "invalid URL" instead of being accepted. Put the token into the token field; basic auth gets its own option later.
- An existing entry or YAML import whose URL contains credentials and that also has a token no longer logs a traceback on every retry; setup retries quietly and the flow shows "invalid URL".

## Self-Check: PASSED

- Files: all 6 modified files exist; SUMMARY at `.planning/phases/04-data-layer-correct-lean/04-08-SUMMARY.md`
- Commits: 6890f51, 8291802, 7558154, 73986d3 are ancestors of HEAD
- `git rev-list --count ce60ec9..73986d3` = 4
