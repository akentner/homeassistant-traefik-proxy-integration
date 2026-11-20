---
phase: 07-config-flow-ha-2026-11-baseline-observability
plan: 05
subsystem: config-flow-and-entry-migration
tags: [config-flow, auth, basic-auth, bearer, migration, unique-id, translations, home-assistant-2026.11]
status: complete

requires:
  - phase: 07-04
    provides: "build_api_client turns rejected stored credentials into reauth; _logged_cause; translated exceptions"
  - phase: 07-03
    provides: "translations/en.json as the single English source"
provides:
  - "const.CONF_AUTH_TYPE; entry data 1.3 = {url, verify_ssl, auth_type} + username/password (basic) or token (bearer)"
  - "coordinator.auth_from_entry_data for 1.3 data (single mapping point, ValueError on unknown type)"
  - "coordinator.split_url_userinfo, coordinator.url_unique_id, coordinator.url_host"
  - "config_flow._auth_fields / _collect_credentials / _entry_data / _async_probe_errors / _stored_auth_type; MINOR_VERSION 3"
  - "async_migrate_entry 1.2 -> 1.3: auth type, URL userinfo, unique_id host:port with collision guard, default title -> host"
  - "en + de config.step texts (user, reauth_confirm, reconfigure), selector.auth_type, config.error.required"
affects: [07-06, 07-07, 07-08, 07-09, phase-08]

actuals:
  tokens: 30770
  tasks: 3
  commits: 6
plan_head_before: 7e77f23530c7d65124dcbaa2fc1d9e63af56da9b
plan_head_after: 58dc998c307deb8855910b3e3b2299f314298309

tech-stack:
  added: []
  patterns:
    - "One form with conditional credential fields: data_entry_flow.Optional(..., visible={field: auth_type, value: ...}); HA strips hidden fields server-side"
    - "Flows build complete entry data (_entry_data) and finish reauth/reconfigure with async_update_reload_and_abort(data=...), never data_updates"
    - "Credential field errors before any request: required, invalid_auth on the field Auth rejects"
    - "Stored-data keys spelled as literals in tests (persistence contract): tests.conftest.AUTH_TYPE"

key-files:
  created: []
  modified:
    - custom_components/traefik_proxy/const.py
    - custom_components/traefik_proxy/coordinator.py
    - custom_components/traefik_proxy/__init__.py
    - custom_components/traefik_proxy/config_flow.py
    - custom_components/traefik_proxy/translations/en.json
    - custom_components/traefik_proxy/translations/de.json
    - tests/conftest.py
    - tests/test_config_flow.py
    - tests/test_reconfigure.py
    - tests/test_verify_ssl.py
    - tests/test_migration.py
    - tests/test_coordinator.py

key-decisions:
  - "Phase 07: entry data 1.3 names its auth type (none/basic/bearer) and carries only that type's credentials; api_key is read only by the migration"
  - "Phase 07: config-entry unique_id is host:port (migrated unless another entry owns it); title = host unless the user renamed it"
  - "Phase 07: URL credentials of 0.3.0 entries move into basic auth; next to a token or when incomplete they are dropped with one WARNING naming the entry only"

requirements-completed: [FLOW-01, FLOW-03]

coverage:
  - id: D1
    description: "User, reauth and reconfigure offer none / basic / bearer with conditional credential fields, password selectors and per-field descriptions (en + de)"
    requirement: FLOW-01
    verification:
      - kind: unit
        ref: "tests/test_config_flow.py#test_user_form_credential_fields_are_visible_per_auth_type, test_reauth_form_credential_fields_are_visible_per_auth_type, test_reconfigure_form_credential_fields_are_visible_per_auth_type, test_flow_api_sends_visible_conditions"
        status: pass
    human_judgment: true
    rationale: "Frontend rendering of the visible conditions (fields appear/disappear) is the Phase 8 visual check (M35); the server side is proven by the HTTP API test"
  - id: D2
    description: "Basic auth from the user step is stored as 1.3 data and reaches Traefik's Authorization header; every mode round-trips"
    requirement: FLOW-01
    verification:
      - kind: integration
        ref: "tests/test_config_flow.py#test_user_step_basic_auth_reaches_traefik, test_entry_data_round_trips_to_probe_header"
        status: pass
    human_judgment: false
  - id: D3
    description: "Switching auth type (user, reauth, reconfigure) never keeps a credential of another type; none clears all"
    requirement: FLOW-01
    verification:
      - kind: integration
        ref: "tests/test_config_flow.py#test_user_step_strips_hidden_credentials, test_reauth_basic_to_bearer_drops_username_and_password, test_reauth_bearer_to_none_drops_token; tests/test_reconfigure.py#test_bearer_to_none_keeps_no_credential, test_basic_to_bearer_keeps_no_username_or_password"
        status: pass
    human_judgment: false
  - id: D4
    description: "0.3.0 entries migrate to 1.3 (token -> bearer, empty -> none, URL credentials -> basic)"
    requirement: FLOW-01
    verification:
      - kind: integration
        ref: "tests/test_migration.py#test_migration_1_2_maps_api_key_to_auth_type, test_userinfo_*, test_migrated_token_entry_loads_with_bearer_header"
        status: pass
    human_judgment: false
  - id: D5
    description: "unique_id host:port in user step, migration (collision guard) and reconfigure; title = host unless renamed; reauth/reconfigure finish via async_update_reload_and_abort"
    requirement: FLOW-03
    verification:
      - kind: integration
        ref: "tests/test_config_flow.py#test_user_step_unique_id_is_host_port_and_title_is_host, test_user_step_same_host_port_aborts_without_request; tests/test_reconfigure.py#test_reconfigure_moves_unique_id_and_host_title; tests/test_migration.py#test_migration_sets_host_port_unique_id_and_host_title, test_migration_keeps_unique_id_owned_by_another_entry"
        status: pass
    human_judgment: false

duration: 19min
completed: 2026-11-15
---

# Phase 7 Plan 05: Auth selector, entry data 1.3 and host:port identity Summary

**Setup, re-authentication and reconfigure offer no auth / basic auth / bearer token in one form with conditional credential fields; entries store one explicit 1.3 auth shape, 0.3.0 entries (including broken credentials-in-URL ones) migrate to it, and entries are identified by `host:port` and named after their host.**

## Performance

- **Duration:** ~19 min
- **Started:** 2026-11-15T13:53:32Z
- **Completed:** 2026-11-15T14:12Z
- **Tasks:** 3 (Task 1 tracer; all three TDD RED + GREEN)
- **Files modified:** 12

## Accomplishments

- **Entry data 1.3 (D-10):** `{url, verify_ssl, auth_type}` plus `username`/`password` (basic) or `token` (bearer) from `homeassistant.const`; keys of an unused mode are absent. `auth_from_entry_data` is the single mapping to `Auth` (unknown type -> `ValueError` -> `invalid_credentials` reauth via 07-04's `build_api_client`). `CONF_API_KEY` is no longer read by `config_flow.py` or `coordinator.py`.
- **Flows (D-11..D-13, D-08):** one `SelectSelector` (`translation_key` `auth_type`, list mode) plus `data_entry_flow.Optional` credential fields with `visible` conditions in user, reauth_confirm and reconfigure; password/token use `TextSelector(PASSWORD)` without default or suggested value. `_collect_credentials` yields `required` per missing field and `invalid_auth` on the field `Auth` rejects, before any request. Reauth requires every credential and finishes with `async_update_reload_and_abort(entry, data=...)` (central `reauth_successful`, `translation_domain` `homeassistant`). Reconfigure keeps a stored credential only when the auth type is unchanged and the field is empty, finishes with `data=` + `options` (verify_ssl mirrored).
- **Removed (D-24, D-29):** `async_step_yaml`, `STEP_YAML_DATA_SCHEMA`, `allow_userinfo`, `config.step.yaml`, `api_key` strings, local `config.abort.reauth_successful`, conftest `mock_traefik_config_entry`.
- **Migration 1.2 -> 1.3 (D-14, IN-08):** runs after the 1.1 -> 1.2 block (a 1.1 entry reaches 1.3 in one setup). api_key -> bearer/none; URL userinfo -> basic (percent-decoded, URL cut after the last `@`, host spelling/IPv6/port/path/query kept); userinfo next to a token or incomplete userinfo -> dropped with one WARNING naming entry id and title only; unique_id -> `host:port` unless another entry owns it (kept + WARNING naming both entry ids); default title -> host. Idempotent (existing `auth_type` keeps its auth keys; no second WARNING).
- **unique_id / title (D-20, D-21, IN-10):** `url_unique_id` (host lowercased, IPv6 bracketed, 80/443 default). User step sets it and aborts `already_configured` before credentials and probe; title = host. Reconfigure runs the shape check first (`http://[::1`, port 99999 -> `invalid_url`), aborts before any request on another entry's `host:port`, moves the unique_id, moves a title that was the old host or "Traefik Proxy", keeps a renamed title.
- **Translations (D-30):** en + de `config.step.{user,reauth_confirm,reconfigure}` with `title`, `description`, `data` and `data_description` for every field (Traefik's middleware-in-front-of-`api@internal` model, HTTPS hint, "empty keeps the stored value" in reconfigure), `selector.auth_type.options`, `config.error.required`, German texts for all `config.error` keys and `already_configured`. No `://`, informal du.

## Task Commits

1. **Task 1 (tracer): entry data 1.3 end-to-end**
   - RED `bef5b34` (test) — `test_entry_data_round_trips_to_probe_header[basic]`
   - GREEN `5835986` (feat)
   - Tracer gate (auto mode): full verify re-run green (875 dev / 875 HA 2026.11.0) -> expanded to Task 2
2. **Task 2: conditional fields, field errors, auth switches, URL credentials migration**
   - RED `bf56493` (test) — `test_userinfo_without_token_becomes_basic`
   - GREEN `d51d61d` (feat)
3. **Task 3: unique_id host:port and host titles**
   - RED `03f48aa` (test) — `test_user_step_unique_id_is_host_port_and_title_is_host`
   - GREEN `58dc998` (feat)

## TDD Gate Compliance

RED evidence as pytest JUnit XML in the git-ignored `.pytest_cache/gsd-red/`, classified with `gsd-tools check tdd-red-evidence` against unchanged HEAD source:

| Target | Verdict | Semantic assessment |
|---|---|---|
| `tests/test_config_flow.py::test_entry_data_round_trips_to_probe_header[basic]` (`07-05-t1.json`) | RED_EVIDENCE_OK | Failed on the Basic-prefix assertion: the HEAD reader mapped 1.3 basic data to no auth (empty header). A first run failed with a KeyError inside the assertion; the assertion was tightened to `.get()` and RED re-recorded |
| `tests/test_migration.py::test_userinfo_without_token_becomes_basic` (`07-05-t2.json`) | RED_EVIDENCE_OK | Failed on the `entry.data` equality: URL userinfo kept, auth type none |
| `tests/test_config_flow.py::test_user_step_unique_id_is_host_port_and_title_is_host` (`07-05-t3.json`) | RED_EVIDENCE_OK | Failed on the unique_id assertion: bare host instead of host:port |

In Task 2 the new flow tests (markers, serialization, stripping, required/rejected, reauth/reconfigure switches) passed at RED: Task 1's flow code already satisfied them (the plan's action 3 said "fix only what the new tests reveal"; nothing was revealed). The migration tests were the failing part.

## Gate results

| Gate | After Task 1 | After Task 2 | After Task 3 |
|---|---|---|---|
| `uv run pytest -q` (dev, HA 2026.11.1) | 875 passed | 910 passed | 933 passed |
| `ruff check custom_components tests` | clean | clean | clean |
| `ruff format --check custom_components tests` (43 files) | clean | clean | clean |
| `uv run mypy --strict custom_components/traefik_proxy` (15 files) | no issues | no issues | no issues |
| ha2611-venv suite (HA 2026.11.0) | 875 passed | 910 passed | 933 passed |
| "Lingering" in output | none | none | none |

No failure occurred in any final gate run; no rerun was used (M39). Acceptance criteria: Task 1 greps A1–A7 pass, `-k "round_trip or basic"` 9 passed; Task 2 `split_url_userinfo` grep passes, `-k "visible or strip or required or rejected or reauth or keep or none"` 26 passed, `-k userinfo` 7 passed; Task 3 greps pass, `-k "unique_id or title or collision or invalid_url"` 12 passed.

Local hassfest: deferred to Phase 8 (Docker unavailable); CI's hassfest job validates the new `config`/`selector` texts (every `data_description` key also exists in `data`).

## Files Created/Modified

- `custom_components/traefik_proxy/const.py` - `CONF_AUTH_TYPE`; `CONF_API_KEY` documented as migration-only
- `custom_components/traefik_proxy/coordinator.py` - 1.3 `auth_from_entry_data`, `split_url_userinfo`, `url_host`, `url_unique_id`
- `custom_components/traefik_proxy/__init__.py` - `_migrated_entry_data`, `_migrated_unique_id`, `< 3` migration block
- `custom_components/traefik_proxy/config_flow.py` - auth selector, credential helpers, rewritten user/reauth/reconfigure, YAML step removed, MINOR_VERSION 3
- `custom_components/traefik_proxy/translations/en.json`, `de.json` - config steps, selector, errors (de: new `config` and `selector` sections)
- `tests/conftest.py` - `make_traefik_entry` 1.3 default (`AUTH_TYPE`, `ENTRY_DATA`, `LEGACY_ENTRY_DATA`), `mock_traefik_config_entry` removed
- `tests/test_config_flow.py`, `tests/test_reconfigure.py`, `tests/test_verify_ssl.py`, `tests/test_migration.py`, `tests/test_coordinator.py` - see Accomplishments

## Decisions Made

Planner decisions (applied as written): default test entries 1.3 at minor 3, legacy data only below minor 3; legacy test entries elsewhere unchanged; reconfigure keeps an empty username like the secrets, reauth requires all; incomplete userinfo -> none + WARNING; URL cut after the last `@`; user step sets the unique_id before credentials and probe; helpers in `coordinator.py`.

Worker decisions:

| Decision | Reason | Alternative |
|---|---|---|
| Tests spell stored keys as literals (`tests.conftest.AUTH_TYPE = "auth_type"`, HA's `CONF_TOKEN` etc.) instead of importing `CONF_AUTH_TYPE` | Stored keys are a persistence contract; also keeps RED runs collectable against HEAD source | Import the new constant (RED would fail at collection) |
| `_async_probe_errors` replaces the copied except ladders of the steps | One mapping point; 07-08 adds `redirect`/`unknown` there | Keep per-step ladders |
| `_stored_auth_type` falls back to `none` for an unknown stored type (e.g. `digest`) as the form default | A default outside the selector options would make the reauth/reconfigure form reject an omitted auth type | Use the stored value as is |
| `_collect_credentials` answers an unknown submitted auth type with `errors = {"auth_type": "invalid_auth"}` | Only reachable by bypassing the selector (`async_init` with data); no new error key in this plan | Raise / `unknown` (07-08's key) |
| `_rejected_field` re-validates the username alone with a dummy password to find the rejected basic field | Reuses `Auth`'s rules instead of importing `api._has_control_chars` | Import the private helper |
| `_check_url_shape` also requires a hostname (not only a netloc) and reads `.port`, all inside `try/except ValueError` | A URL that passes always has a `url_unique_id`, so the steps need no second ValueError branch | Catch ValueError around `url_unique_id` in each step |
| Shared `coordinator.url_host` (lowercased hostname, None when unparsable) for titles in flow and migration | Same rule in both places, no duplicate | Private copies in both modules |
| An unparsable stored URL is kept as stored by the migration, with one WARNING (unique_id kept); auth type from the token only | Setup then reports `invalid_url` (07-04) and reconfigure fixes it; the migration must not fail | Fail the migration |
| Userinfo-to-basic setup test uses `https://admin:p%40ss%3Aw@traefik.example.com:8080`; the path/query URL case is asserted on the direct migration call | A base URL with a query cannot be stubbed meaningfully (`?x=1/api/version`) | One test with the query URL through setup |
| Owner entry in the collision test is disabled | Setting up the integration sets up every enabled entry of the domain | Two enabled entries with two stubs |
| `en.json` re-serialized with literal "—" instead of `—` in the untouched options description | Same string value; the file was rewritten as UTF-8 | Hand-edit around the escape |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Correctness] Unknown stored auth type as form default**
- **Found during:** Task 1 (writing the `digest` reauth case)
- **Issue:** `_auth_fields(<stored auth_type>)` with a stored `digest` would give the selector a default outside its options; submitting without the field would fail schema validation instead of showing a form.
- **Fix:** `_stored_auth_type` maps an unknown stored type to `none`.
- **Files modified:** `custom_components/traefik_proxy/config_flow.py`
- **Commit:** `5835986`

**2. [Rule 1 - Bug] mypy: name clash with the 1.2 block's loop variable**
- **Found during:** Task 3 GREEN
- **Issue:** `unique_id` in the `< 3` block collided with the `< 2` block's `for unique_id, ...` (typed `str`).
- **Fix:** renamed to `new_unique_id`.
- **Files modified:** `custom_components/traefik_proxy/__init__.py`
- **Commit:** `58dc998`

Other notes: the `ruff format` pass of Task 1 reformatted `tests/test_config_flow.py`, so that file is also in the Task 1 GREEN commit; Task 3's GREEN commit carries two extra tests (`test_url_host`, unparsable-URL unique_id/WARNING assertions) written after GREEN for the new branches. `tests/test_init.py::test_press_refreshes_only_own_entry` builds a second entry at the new default minor 3 with legacy data (`api_key`); it is outside this plan's files and only checks button refresh scoping, so it was left unchanged (its `api_key` is ignored as auth type none).

## Issues Encountered

None.

## User-visible changes (for the Phase 8 CHANGELOG)

- Setup, re-authentication and reconfigure offer "No authentication", "Basic auth (username and password)" and "Bearer token"; only the fields of the chosen type are shown, and missing or unusable credentials are flagged on the field before Traefik is contacted.
- Existing entries with a token become "Bearer token", entries without a token "No authentication".
- Credentials embedded in the URL (`user:password@host`) move into the basic-auth fields; if the entry also had a token, the token is kept, the URL credentials are dropped and a warning is logged (such entries did not work before).
- Switching the authentication type never leaves old credentials stored; in reconfigure an empty password/token keeps the stored one while the type stays the same.
- Entries are identified by host and port: two Traefik instances on the same host (different ports) can be added, the same one cannot be added twice. Entries are named after their host; a name you chose yourself is kept, also when reconfiguring to a new host.
- The YAML import path is gone.

## Self-Check: PASSED
