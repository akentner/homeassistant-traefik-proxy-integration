---
phase: 04-data-layer-correct-lean
plan: 05
subsystem: api
tags: [traefik, aiohttp, auth, error-taxonomy, config-flow, home-assistant]

requires:
  - phase: 04-04
    provides: "Typed read API (async_get_version / async_get_entrypoints / async_get_state), _get_paginated, TraefikProxyPayloadError, snapshot coordinator"
provides:
  - "api.py: AuthMode (StrEnum none/basic/bearer), frozen Auth with repr=False credentials and per-request header()"
  - "api.py: TraefikProxyApiError(path, detail, *, status) base with .path/.status; NotFound, Connection, InvalidUrl(Connection), Payload, Auth subclasses"
  - "api.py: _request core (JSON decoded outside the network block), reload_routers on the per-request Auth header"
  - "coordinator.py: auth_from_entry_data (D-09 seam) and build_api_client(auth=...)"
  - "config_flow.py: /api/version probe with the D-11 mapping (404 -> api_disabled reachable again)"
affects: [04-06, phase-05-entity-lifecycle, phase-07-flows, phase-08-changelog]

actuals:
  tokens: 17400
  tasks: 2
  commits: 3
plan_head_before: d5c371ba1a77058d76346d58f040bf76c4ca6e50
plan_head_after: fccbac6aaca7879cdf249295b1f228942f352f8f

tech-stack:
  added: []
  patterns:
    - "Client errors carry path + status (or exception type name) only; constructor TraefikProxyApiError(path, detail, *, status=None)"
    - "Authorization header built per request from a frozen Auth; never set on the shared session"
    - "Basic header built in-module (RFC 7617, UTF-8) instead of aiohttp.BasicAuth"
    - "Client tests run on hass + aioclient_mock; session kwargs inspected through MagicMock(wraps=session)"

key-files:
  created: []
  modified:
    - custom_components/traefik_proxy/api.py
    - custom_components/traefik_proxy/coordinator.py
    - custom_components/traefik_proxy/config_flow.py
    - tests/test_api.py
    - tests/test_api_pagination.py
    - tests/test_config_flow.py
    - tests/test_reconfigure.py
    - tests/test_verify_ssl.py
  deleted:
    - tests/fixtures/traefik_entrypoints.json
    - tests/fixtures/traefik_middlewares.json
    - tests/fixtures/traefik_overview.json
    - tests/fixtures/traefik_routers.json
    - tests/fixtures/traefik_services.json
    - tests/fixtures/traefik_version.json

key-decisions:
  - "04-05: Basic Authorization header is built in api.py (base64 of UTF-8 user:password) because aiohttp 3.14 deprecates BasicAuth and HA 2026.3's aiohttp 3.13 lacks encode_basic_auth"
  - "04-05: Auth also rejects credentials the mode does not use and control characters in any credential; the config flow maps such a ValueError to invalid_auth"
  - "04-05: reload_routers maps 401/403 -> AuthError and every other non-2xx -> base ApiError (no NotFound), as the plan states, to keep its behaviour unchanged until Phase 5 removes it"

patterns-established:
  - "Error construction: TraefikProxyXError(path, 'HTTP <status>', status=<status>) / (path, type(err).__name__) / (path, 'unexpected payload shape' | 'invalid JSON')"
  - "Entry data -> Auth only through coordinator.auth_from_entry_data"

requirements-completed: [DATA-03, DATA-04, DATA-07]

coverage:
  - id: D1
    description: "Auth modes none/basic/bearer with exact per-request Authorization header; shared session default headers stay free of Authorization; Auth validation names the field only; repr hides credentials"
    requirement: DATA-03
    verification:
      - kind: unit
        ref: "tests/test_api.py#test_auth_header_per_mode, test_basic_header_encodes_utf8_credentials, test_auth_rejects_invalid_credentials, test_auth_repr_hides_credentials, test_each_mode_sends_exactly_its_header"
        status: pass
      - kind: integration
        ref: "tests/test_config_flow.py#test_every_auth_mode_round_trips_to_its_header"
        status: pass
    human_judgment: false
  - id: D2
    description: "Credentials never appear in log records, str(exc), repr(exc) or repr(client) across 401/404/500/connection/invalid-URL/invalid-JSON/shape errors, with a userinfo base URL, for basic and bearer"
    requirement: DATA-03
    verification:
      - kind: unit
        ref: "tests/test_api.py#test_credentials_never_leak (14 cases)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Error taxonomy: 401/403 Auth, 404 NotFound, other non-2xx base error with status, aiohttp/timeout/OS errors Connection, InvalidUrlClientError InvalidUrl, invalid JSON / wrong shape Payload; no assert in the package; legacy read surface removed"
    requirement: DATA-04
    verification:
      - kind: unit
        ref: "tests/test_api.py#test_status_maps_to_specific_error, test_other_non_2xx_raise_base_error_with_status, test_network_errors_raise_connection_error, test_invalid_url_raises_invalid_url_error, test_invalid_json_raises_payload_error, test_version_list_payload_raises_payload_error, test_api_module_contains_no_assert_statements, test_legacy_read_surface_removed"
        status: pass
      - kind: other
        ref: "AST assert count over custom_components/traefik_proxy = 0; grep fetch_all|get_overview|/api/overview over the package prints nothing"
        status: pass
    human_judgment: false
  - id: D4
    description: "verify_ssl reaches every GET and the refresh POST; every request targets the configured base URL; reload_routers keeps its behaviour with the Auth header and Content-Length 0"
    requirement: DATA-04
    verification:
      - kind: unit
        ref: "tests/test_api.py#test_verify_ssl_false_reaches_every_request, test_verify_ssl_defaults_to_true, test_real_captures_parse_and_requests_stay_on_base_url, test_reload_routers_*"
        status: pass
    human_judgment: false
  - id: D5
    description: "Config flow probes /api/version and maps Auth -> invalid_auth, NotFound -> api_disabled, InvalidUrl -> invalid_url, other API errors and timeouts -> cannot_connect; entry data maps to bearer/none"
    requirement: DATA-04
    verification:
      - kind: unit
        ref: "tests/test_config_flow.py#test_validate_input_maps_client_errors (8 cases), test_validate_input_maps_real_404_to_api_disabled, test_auth_from_entry_data, test_validate_input_empty_bearer_does_not_send_authorization_header"
        status: pass
      - kind: integration
        ref: "tests/test_reconfigure.py, tests/test_verify_ssl.py (probe header and verify_ssl kwargs on the version probe)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Synthetic traefik_*.json fixtures deleted; no test references them"
    requirement: DATA-07
    verification:
      - kind: other
        ref: "find tests/fixtures -maxdepth 1 -name 'traefik_*.json' -> 0; grep traefik_(version|...).json over tests prints nothing"
        status: pass
    human_judgment: false
  - id: D7
    description: "Full gate green on the dev venv and the HA 2026.3.0 venv"
    verification:
      - kind: unit
        ref: "uv run pytest -q (456 passed); ~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts='' tests (456 passed)"
        status: pass
      - kind: other
        ref: "uv run ruff check / ruff format --check custom_components tests; uv run mypy --strict custom_components/traefik_proxy (no issues, 13 files)"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-11-14
status: complete
---

# Phase 4 Plan 05: Client contract hardening Summary

**The Traefik client now authenticates with a frozen `Auth` value (none / basic / bearer) whose header is built per request. It raises only the `TraefikProxy*` error taxonomy, with path-and-status messages that tests prove never contain a credential. Asserts and the legacy dict API are gone, and the config flow probes `/api/version` so a 404 reaches `api_disabled` again.**

## Performance

- **Duration:** 8 min (start 2026-11-14T00:57:40Z, end 2026-11-14T01:05:25Z)
- **Tasks:** 2 of 2 (Task 1 TDD: RED + GREEN; Task 2 auto)
- **Files:** 14 (8 modified, 6 deleted)

## Accomplishments

- **Auth (D-08):** `AuthMode(StrEnum)` with `none`, `basic` and `bearer`. `Auth` is a frozen, slotted dataclass; `username`, `password` and `token` use `repr=False`. `__post_init__` raises `ValueError` naming only the field: basic needs a username without `:` and a password, bearer needs a token, and a mode must not carry credentials it does not use or control characters. `header()` returns `{}`, `Bearer <token>` or `Basic <base64(UTF-8 user:password)>`.
- **Taxonomy (D-10):** `TraefikProxyApiError(path, detail, *, status=None)` stores `.path` and `.status`. Subclasses: `TraefikProxyAuthError` (401/403), `TraefikProxyNotFoundError` (404), `TraefikProxyConnectionError` (`aiohttp.ClientError`, `TimeoutError`, `OSError`), `TraefikProxyInvalidUrlError(TraefikProxyConnectionError)` and `TraefikProxyPayloadError`. Messages are `"<path>: HTTP <status>"`, `"<path>: <ExceptionTypeName>"` or a fixed description, chained with `from err`.
- **`_request` core:** a GET with `params`, `headers=self._auth.header()` and `ssl=verify_ssl`. It logs path/page/status at debug level and reads the body and `X-Next-Page` inside the response context. JSON is decoded after the network block, so a decode `ValueError` can never look like an invalid URL. The version, entrypoints and paginated readers use it.
- **Removed:** the six dict getters, the overview probe, the six-endpoint aggregate fetch, the old request helpers, the internal-item filter and its regex, and all 6 `assert` statements (AST count 0).
- **`reload_routers` (D-06):** same POST with `{**auth.header(), "Content-Length": "0"}`. 401/403 raise `AuthError`, any other non-2xx the base error, network failures `ConnectionError`. The docstring no longer cites planning documents.
- **Entry mapping (D-09):** `coordinator.auth_from_entry_data` maps a non-empty string `api_key` to bearer and anything else to `Auth()`. `build_api_client` passes `auth=`.
- **Config flow (D-11):** `_validate_input` probes `async_get_version()` inside `asyncio.timeout(10)` and maps errors in this order: `AuthError` → `InvalidAuth`, `NotFoundError` → `ApiDisabled`, `InvalidUrlError` → `InvalidUrl`, `ApiError`/`TimeoutError` → `CannotConnect`. The direct aiohttp exception imports and every overview mention in the package are gone.
- **Tests:** `tests/test_api.py` was rewritten on `hass` + `aioclient_mock` with the v3.7 capture (66 tests). The `tests/test_config_flow.py` probe tests now mock `/api/version`; it gained an 8-case mapping test, a real-404 test, an `auth_from_entry_data` test and the AuthMode round-trip invariant. Reconfigure and verify_ssl stubs no longer register the overview endpoint. The six synthetic fixtures are deleted (D-22).

## Task Commits

1. **Task 1 RED: failing client contract tests** - `ff3ff58` (test)
2. **Task 1 GREEN: Auth modes, taxonomy, `_request`, no asserts, legacy surface removed, synthetic fixtures deleted** - `89e9952` (feat)
3. **Task 2: D-09 entry mapping, D-11 config-flow mapping, flow tests adjusted** - `fccbac6` (feat)

REFACTOR: none needed (no commit).

## TDD Gate Compliance

- **RED** (`ff3ff58`): `uv run pytest tests/test_api.py -q -p no:cacheprovider --junitxml=.gsd-red/red.xml -o addopts=""` → exit 1, 59 tests, 58 failed, 1 passed. Classifier `gsd_run check tdd-red-evidence` (JUnit format): `RED_EVIDENCE_OK`, reason `target_test_failed`, target `test_api_module_contains_no_assert_statements`.
- **Semantic assessment:** collection succeeded, because the tests reference new names through the `api` module at runtime instead of importing them at module level. The target test failed on its planned assertion: `asserts == []` received the 6 legacy assert lines. `test_legacy_read_surface_removed` also failed on its assertion. The other 56 failures are `AttributeError`s raised inside test bodies for the missing `Auth` / new error classes, which is the planned behaviour being absent. No fixture, syntax or collection fault occurred.
- **GREEN** (`89e9952`): `tests/test_api.py` passed in full. Two expectations in the test file were corrected in the GREEN commit; see deviation 2.
- Gate order in git: `test(04-05)` precedes both `feat(04-05)` commits.

## Verification

- `uv run pytest -q`: 456 passed (388 before the plan)
- HA 2026.3.0 venv (`~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`): 456 passed
- `uv run ruff check custom_components tests`: all checks passed
- `uv run ruff format --check custom_components tests`: 31 files already formatted
- `uv run mypy --strict custom_components/traefik_proxy`: no issues in 13 source files
- AST assert count over `custom_components/traefik_proxy`: 0 (baseline 6)
- `! grep -rnE 'fetch_all|get_overview|/api/overview' custom_components/traefik_proxy`: no output
- `find tests/fixtures -maxdepth 1 -name 'traefik_*.json' | wc -l`: 0
- Task 1 acceptance: 4 taxonomy class lines, 1 `InvalidUrlError(ConnectionError)` line, `repr=False` count 3, no legacy names in api.py, no fixture references in tests, `class _` count 0 in test_api.py
- Task 2 acceptance: `except TraefikProxyNotFoundError` 1 line; no `ClientConnectorError|ClientResponseError|InvalidUrlClientError` in config_flow.py; `def auth_from_entry_data` 1 line; no `filter_internal_items` in the package; no `/api/overview` in the three flow test files
- No Docker containers, networks or volumes were started (the one running container, `WinBoat`, predates this session and is not related to it).

## Decisions Made

See key-decisions above and Worker Decisions below.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `aiohttp.BasicAuth` is deprecated in the dev aiohttp and its replacement is missing at the HA minimum**
- **Found during:** Task 1 GREEN
- **Issue:** D-08 and the plan say to build the Basic header with `aiohttp.BasicAuth(...).encode()`. aiohttp 3.14.5 (dev venv) emits `DeprecationWarning: BasicAuth is deprecated ... use aiohttp.encode_basic_auth()`. The HA 2026.3 venv ships aiohttp 3.13.3, which has no `encode_basic_auth`.
- **Fix:** `Auth.header()` builds `"Basic " + base64(f"{username}:{password}".encode())` (UTF-8, RFC 7617, the same bytes as aiohttp's new helper). For ASCII credentials the output equals `BasicAuth(...).encode()`. Added `test_basic_header_encodes_utf8_credentials`.
- **Files modified:** custom_components/traefik_proxy/api.py, tests/test_api.py
- **Commit:** 89e9952

**2. [Rule 1 - Test bug] Two RED expectations corrected during GREEN**
- **Found during:** Task 1 GREEN
- **Issue:** `test_auth_header_per_mode` computed its expected value with the deprecated `aiohttp.BasicAuth` (see 1). `test_reload_routers_success_sends_auth_and_empty_body` compared the recorded method to `"post"`, but aiohttp records `"POST"`.
- **Fix:** The expected value is now computed with the test's base64 helper (same bytes), and the method comparison is case-insensitive. Both tests assert the same behaviour as before.
- **Commit:** 89e9952

**3. [Scope] Second constructor call in test_api_pagination.py**
- **Found during:** Task 1
- **Issue:** The plan said to update only the `_client` helper in tests/test_api_pagination.py, but `test_page_size_defaults_to_module_constant` also built the client with the old `api_key=` argument.
- **Fix:** Both calls now pass `api.Auth()`. Module-attribute access was used so the RED commit still collects.
- **Commit:** ff3ff58

**4. [Ordering] Task 1 verify included a coordinator-level test that only Task 2 fixes**
- **Found during:** Task 1
- **Issue:** Task 1's `<verify>` command includes tests/test_api_pagination.py. Its `test_failing_page_keeps_previous_snapshot` sets up a config entry through `build_api_client`, which still used the old `api_key=` constructor until Task 2. `mypy --strict` failed on coordinator.py for the same reason.
- **Fix:** None needed beyond Task 2, matching the plan's own note ("Task 2 fixes them, so verify only the client tests here"). The test and mypy pass after Task 2. coordinator.py was not touched in the Task 1 commit, to keep each commit inside its task's file list.

**5. [Rule 2 - Hardening] Config flow catches an Auth `ValueError`**
- **Found during:** Task 2
- **Issue:** With control-character validation in `Auth`, a token like `"tok\r\n..."` would raise `ValueError` out of `_validate_input` and show HA's generic error. The old code had the same failure through aiohttp's header check.
- **Fix:** `_validate_input` builds the `Auth` first and maps `ValueError` to `InvalidAuth`. Added `test_validate_input_rejects_token_with_control_characters`, which also asserts that no request is sent.
- **Commit:** fccbac6

**Total deviations:** 5 (1 blocking, 1 test fix, 1 scope, 1 ordering note, 1 hardening). **Impact:** no scope creep; the request set and user-visible behaviour are unchanged, apart from the restored `api_disabled` error.

## Worker Decisions

- Exception constructor is `TraefikProxyApiError(path, detail, *, status=None)` with the message `"<path>: <detail>"`. Reason: every message is path-scoped by construction, and the existing pagination messages (`"<path>: unexpected payload shape"`, `"<path>: more than N pages"`) keep their exact text. Alternative: a free-form message plus separate `path` / `status` keywords.
- JSON decode failures use the detail `"invalid JSON"`; shape failures keep `"unexpected payload shape"`. Reason: both are fixed descriptions with no payload content. Alternative: the decode exception's type name (`JSONDecodeError`).
- `Auth` rejects credentials the mode does not use (for example a bearer `Auth` with a username), not only credentials passed with mode `none`. Reason: one invariant for all modes; nothing can silently carry an unused secret. Alternative: validate only the `none` mode as the plan lists it.
- `Auth` rejects control characters in any credential. Reason: aiohttp would otherwise raise a raw `ValueError` at request time, outside the taxonomy. Alternative: catch `ValueError` around the request.
- Basic encoding is UTF-8, not aiohttp's legacy latin-1 default. Reason: RFC 7617 charset, matches aiohttp's replacement helper, and latin-1 cannot encode many characters anyway. Alternative: latin-1 for byte-identity with `BasicAuth`.
- `reload_routers` maps 404 to the base `TraefikProxyApiError`, not `NotFoundError`, and reads the status after leaving the response context. Reason: the plan's literal "its own 401/403 -> Auth, other non-2xx -> ApiError", keeping it separate from the read path until Phase 5 removes it. Alternative: reuse the read path's status mapping.
- The config flow raises its flow exceptions `from None` (also for `InvalidUrl` and `ApiDisabled`, which used `from err` before). Reason: the chain would carry aiohttp's exception, whose text can contain the URL with userinfo. Alternative: keep `from err`.
- In the RED tests, new names are referenced through the `api` module (`api.Auth`, `getattr(api, name)` in parametrizations) instead of module-level imports. Reason: an `ImportError` at collection would be invalid RED evidence. No REFACTOR switched them to direct imports, because the module-attribute style reads fine and avoids churn. Alternative: a REFACTOR commit with direct imports.
- Added `test_auth_from_entry_data` (token / empty / missing / `None`) to tests/test_config_flow.py. Reason: the D-09 seam gets a direct unit test besides the indirect flow-header tests. Alternative: rely on the flow tests only.
- The concurrency edge (options listener replacing the client mid-refresh) has no dedicated test. Reason: the plan marks it `verification: backstop`; structurally, each request reads the header from its own client's frozen `Auth`. Alternative: a race test with two clients.
- tests/test_coordinator.py and tests/test_init.py still register an unused `/api/overview` mock. Reason: outside this plan's file list and harmless; the plan's gates cover only the package and the three flow test files. Alternative: remove them now (fits 04-06 or the Phase 8 sweep).

## Known Stubs

None. (`config_flow.py:197` says "stored as a placeholder" in a pre-existing options-flow docstring about `tls_warn_days`; it is not a stub of this plan.)

## Threat Flags

None. No new network endpoint, auth path or trust-boundary surface beyond the plan's threat model. T-04-10 (secrecy tests), T-04-11 (session default headers), T-04-12 (`ssl=` on every GET and the POST) and T-04-13 (specific branches first, parametrized mapping test) are mitigated as planned.

## Issues Encountered

- The flagged assumption from the plan stays open for a human: no 3xx or redirect-to-other-host handling was added. A 302 that aiohttp does not follow is treated as a non-2xx base error (tested). With real aiohttp, `allow_redirects` defaults to True for GET, so a redirect is followed. aiohttp drops a per-request Authorization header when the redirect changes origin, so a redirect to another host would not carry the credential, but the request would still leave the configured host. Confirm in Phase 7/8 whether `allow_redirects=False` is wanted (it would also make the host-pinning prohibition hold against a redirecting server).
- The deferred `SyntaxWarning` entry in deferred-items.md is still marked open, although 04-04 removed its cause; left for the verifier, as 04-04 noted.

## User Setup Required

None.

## Next Phase Readiness

- 04-06 can put `/api/rawdata` in front of `async_get_state` and fall back on `TraefikProxyNotFoundError`. `_request(path)` returns `(payload, x_next_page)` for it.
- Phase 7 (FLOW-01) adds the auth selector: entry data gets an explicit mode, and `auth_from_entry_data` is the single place to extend, including basic credentials.

## Self-Check: PASSED

- FOUND: custom_components/traefik_proxy/api.py, custom_components/traefik_proxy/coordinator.py, custom_components/traefik_proxy/config_flow.py, tests/test_api.py, tests/test_config_flow.py
- MISSING (intentionally deleted): tests/fixtures/traefik_*.json (6)
- FOUND commits: ff3ff58, 89e9952, fccbac6 (ancestors of HEAD; 3 commits since plan_head_before)
- All task acceptance criteria and the plan-level verification commands re-run after Task 2 and passing
