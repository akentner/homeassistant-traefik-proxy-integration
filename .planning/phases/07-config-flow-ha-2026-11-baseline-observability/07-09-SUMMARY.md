---
phase: 07-config-flow-ha-2026-11-baseline-observability
plan: 09
subsystem: observability
tags: [diagnostics, repairs, issue-registry, translations, redaction, hassfest, home-assistant-2026.11]
status: complete

requires:
  - phase: 07-02
    provides: "entry-bound migration issue (config_entry_id), async_unload_platforms_or_raise"
  - phase: 07-05
    provides: "entry data 1.3 (auth_type, username/password/token), split_url_userinfo"
  - phase: 07-08
    provides: "final config texts, config_flow.py at 100 % coverage"
provides:
  - "custom_components/traefik_proxy/diagnostics.py: TO_REDACT, async_get_config_entry_diagnostics, _jsonable, _safe_url"
  - "TraefikProxyApiClient.paginated (read-only property)"
  - "TraefikEntityManager.missing_map() -> MissingData (also used by the Store save)"
  - "__init__.ISSUE_INSECURE_CREDENTIALS, _insecure_issue_id, _async_check_insecure_credentials (step 8 of setup)"
  - "issues.insecure_credentials title/description in en and de ({entry_title})"
  - "Whole-file en/de parity tests (keys both ways, placeholders, label+description per field, no '://', issue keys, auth options)"
affects: [phase-08]

actuals:
  tokens: 8400
  tasks: 3
  commits: 5
plan_head_before: 5b388d0751c5b6e86206920cb02b990b78057e62
plan_head_after: 4129a9742336bd38e89c93f14aa6c3e594abb240

tech-stack:
  added: []
  patterns:
    - "Diagnostics from parsed models only: dataclasses.asdict + _jsonable, then async_redact_data"
    - "Entry-bound repair evaluated at the end of setup, deleted through entry.async_on_unload"
    - "Translation parity tested on the whole flattened files, not per section"

key-files:
  created:
    - custom_components/traefik_proxy/diagnostics.py
    - tests/test_diagnostics.py
    - tests/test_repairs.py
  modified:
    - custom_components/traefik_proxy/api.py
    - custom_components/traefik_proxy/entity_manager.py
    - custom_components/traefik_proxy/__init__.py
    - custom_components/traefik_proxy/translations/en.json
    - custom_components/traefik_proxy/translations/de.json
    - tests/test_translations.py

key-decisions:
  - "Phase 07: diagnostics dump parsed models only and redact username/password/token/api_key/users/authorization; URL userinfo is cut, an unparsable stored URL is redacted as a whole"
  - "Phase 07: insecure_credentials repair (WARNING, not fixable, entry-bound) is raised at the end of every setup while http is used with credentials; unload deletes it, so a reload resets a user's ignore (accepted)"
  - "Phase 07: en/de translation parity is enforced over the whole files"

requirements-completed: [DIAG-04, FLOW-06, FLOW-07]

coverage:
  - id: D1
    description: "Diagnostics of a basic and a bearer entry contain none of the username/password/token values; data keys show **REDACTED**; entry, coordinator (paginated False), snapshot router keys, cert host not_after as ISO string"
    requirement: DIAG-04
    verification:
      - kind: integration
        ref: "tests/test_diagnostics.py#test_basic_entry_diagnostics_redact_credentials, test_bearer_entry_diagnostics_redact_token"
        status: pass
    human_judgment: false
  - id: D2
    description: "URL userinfo stripped; unparsable URL redacted; no serverStatus/usedBy in the dump"
    requirement: DIAG-04
    verification:
      - kind: integration
        ref: "tests/test_diagnostics.py#test_diagnostics_strip_url_userinfo, test_diagnostics_contain_no_raw_payload, test_safe_url_redacts_an_unparsable_url"
        status: pass
    human_judgment: false
  - id: D3
    description: "Paginated client reported; failed first cert cycle -> last_update_success False, hosts {}; vanished router listed under missing.router with an ISO time"
    requirement: DIAG-04
    verification:
      - kind: integration
        ref: "tests/test_diagnostics.py#test_diagnostics_report_paginated_client, test_diagnostics_before_a_successful_cert_cycle, test_diagnostics_list_missing_items"
        status: pass
    human_judgment: false
  - id: D4
    description: "http + bearer/basic raises insecure_credentials_<entry_id> (WARNING, not fixable, not persistent, config_entry_id, entry_title); http+none, https+bearer, https+basic raise none"
    requirement: FLOW-06
    verification:
      - kind: integration
        ref: "tests/test_repairs.py#test_http_bearer_raises_insecure_credentials_issue, test_issue_only_for_credentials_over_http"
        status: pass
    human_judgment: false
  - id: D5
    description: "Unload deletes, setup re-raises; reconfigure to https or to none leaves no issue; removal leaves no issue; ignore is reset by a reload"
    requirement: FLOW-06
    verification:
      - kind: integration
        ref: "tests/test_repairs.py#test_unload_deletes_issue_and_setup_raises_it_again, test_reconfigure_fix_deletes_issue, test_removal_leaves_no_issue, test_ignored_issue_returns_after_reload"
        status: pass
    human_judgment: false
  - id: D6
    description: "de.json has exactly the keys of en.json (whole file, both ways), same placeholders, data == data_description per config/options step, no empty string, no '://', issue keys raised in __init__.py, auth options == AuthMode"
    requirement: FLOW-07
    verification:
      - kind: unit
        ref: "tests/test_translations.py#test_de_has_exactly_the_keys_of_en, test_placeholders_match, test_every_field_has_label_and_description, test_no_empty_strings, test_no_url_literals, test_issue_keys_are_raised, test_auth_type_options_match_auth_modes"
        status: pass
    human_judgment: true
    rationale: "Wording and rendering of the repair text in the frontend is the Phase 8 visual check (M35)"

duration: 17min
completed: 2026-11-15
---

# Phase 7 Plan 09: Diagnostics, insecure-credentials repair and whole-file translation parity Summary

**A redacted diagnostics download (entry, both coordinators, parsed snapshot, certificate state per host, missing items; no credential, no URL userinfo, no raw Traefik payload), an entry-bound `insecure_credentials` repair while credentials travel over plain HTTP, and whole-file en/de translation parity enforced by tests; local hassfest reports 0 invalid integrations.**

## Performance

- **Duration:** ~17 min (14:54Z - 15:11Z)
- **Tasks:** 3 (Task 1 tracer + TDD, Task 2 TDD, Task 3 checks)
- **Files modified:** 9 (3 created)

## Accomplishments

- `diagnostics.py` (new): `TO_REDACT = {password, token, username, api_key, users, authorization}`; `async_get_config_entry_diagnostics` returns `entry` (title, unique_id, version, minor_version, data with the URL passed through `split_url_userinfo`, options), `coordinator` (last_update_success, update_interval seconds, paginated), `snapshot` (`_jsonable(dataclasses.asdict(...))`), `certificates` (last_update_success, update_interval, threshold_days, hosts) and `missing` - all through `async_redact_data`. Reads public attributes only.
- `api.py`: read-only `TraefikProxyApiClient.paginated`.
- `entity_manager.py`: `TraefikEntityManager.missing_map()` (stored kinds merged, registered kinds win); `_async_schedule_save` now uses it instead of the duplicated expression.
- `__init__.py`: `ISSUE_INSECURE_CREDENTIALS`, `_insecure_issue_id`, `_async_check_insecure_credentials` as setup step 8 (create with `config_entry_id=entry.entry_id`, else delete; `entry.async_on_unload` deletes). Docstrings updated. No `async_refresh_issues`.
- Translations: `issues.insecure_credentials` in en and de (informal "du", `{entry_title}`, no `://`, says the notice returns after a restart/reload while HTTP is used).
- `tests/test_translations.py`: `PHASE_SECTIONS` / `_phase_strings` / the section-limited parity test replaced by six whole-file tests; `_flatten`, `_placeholders` and the entity/icon/state tests kept.

## Task Commits

1. **Task 1: diagnostics download (tracer)**
   - RED `0009349` (test)
   - GREEN `8f771f4` (feat)
2. **Task 2: insecure_credentials repair + whole-file parity**
   - RED `5e452c1` (test)
   - GREEN `cdd4229` (feat)
3. **Task 3: phase-level checks** - no code change needed; coverage additions `4129a97` (test, see Deviations)

## TDD Gate Compliance

RED evidence as pytest JUnit XML in the git-ignored `.pytest_cache/gsd-red/`, recorded before each GREEN commit and classified with `gsd-tools check tdd-red-evidence`.

| Target | Record | Verdict | Semantic assessment |
|---|---|---|---|
| `tests/test_diagnostics.py::test_basic_entry_diagnostics_redact_credentials` | `07-09-t1.json` | RED_EVIDENCE_OK | Ran and failed on the helper's HTTP 200 assertion (404: no diagnostics platform yet); no collection/fixture fault. All 7 diagnostics tests failed the same way |
| `tests/test_repairs.py::test_http_bearer_raises_insecure_credentials_issue` | `07-09-t2.json` | RED_EVIDENCE_OK | Ran and failed on the issue-exists assertion (None); no collection/fixture fault |

At Task 2 RED 8 tests failed: 7 repair tests (6 on the issue assertions, the ignore test with `KeyError` because the issue to ignore did not exist) and `test_issue_keys_are_raised` (missing `insecure_credentials`). The other whole-file translation tests passed at RED already: de.json had reached full key parity in 07-07/07-08, so no translation gap had to be fixed.

Tracer gate (interactive, end-of-phase, automated-only verify): after Task 1 GREEN all verify commands were re-run end-to-end and passed before Task 2 started.

## Gate results

| Gate | After Task 1 | After Task 2 | After Task 3 |
|---|---|---|---|
| `uv run pytest -q` (dev env) | 1017 passed | 1032 passed | 1034 passed |
| "Lingering" in output | none | none | none |
| `ruff check custom_components tests` | clean | clean | clean |
| `ruff format --check custom_components tests` | clean (46 files) | clean (47) | clean (47) |
| `uv run mypy --strict custom_components/traefik_proxy` (16 files) | no issues | no issues | no issues |
| ha2611-venv suite (HA 2026.11.0) | 1017 passed | 1032 passed | 1034 passed |

No failure in any gate run; no rerun used (M39). Task 1 acceptance: diagnostics.py with `async def async_get_config_entry_diagnostics`, `async_redact_data`, `"authorization"`; no `._paginated|._kinds|._stored` in diagnostics.py; `def paginated` / `def missing_map` present; `tests/test_diagnostics.py` 7 passed (>= 6; 9 after Task 3). Task 2 acceptance: constant present; `config_entry_id=entry.entry_id` count 2; no `async_refresh_issues`; both description keys load; no `PHASE_SECTIONS`; flattened en == de; `-k "exactly_the_keys or placeholders or label_and_description or url_literals or issue_keys or auth_type_options"` 6 passed; `tests/test_repairs.py` 10 passed (>= 6).

## Phase-level checks (Task 3)

| # | Check | Result |
|---|---|---|
| 1 | D-07: no private `DataUpdateCoordinator` attribute (`self._shutdown_requested` etc.) in `custom_components/` | PASS (no match) |
| 2 | D-09: no `UNDEFINED`, `ATTR_*`, `device*.config_entries` in `custom_components/traefik_proxy` | PASS (no match) |
| 3 | D-16: no `add_update_listener` | PASS (no match) |
| 4 | D-10: `CONF_API_KEY` only in `__init__.py`, `const.py`, `diagnostics.py` | PASS (exactly these three files; the host `sort` uses the de_DE collation, so it prints const.py before diagnostics.py before `__init__.py`) |
| 5 | D-28: no `strings.json` | PASS |
| 6 | M22 scoped: no added line in `custom_components/` since `4e4d859` (the commit that added 07-01-PLAN.md) carries a planning reference | PASS (no line printed, exit 0); nothing to fix |
| D-22 | config_flow.py coverage from the flow test modules | 100 % (194 stmts, 0 missed), `--fail-under=100` exit 0; 180 passed |

hassfest (FLOW-07, A3): `docker info` succeeded; `docker run --rm -v "$PWD":/github/workspace ghcr.io/home-assistant/hassfest` (image digest `sha256:f9ac52cf...`) -> `Integrations: 1`, `Invalid integrations: 0`, every validator incl. translations, icons, manifest and config_flow ran without warning or error. `docker ps -a` before and after is identical (no container left; the host's unrelated old containers were not touched).

## Files Created/Modified

- `custom_components/traefik_proxy/diagnostics.py` - new diagnostics platform
- `custom_components/traefik_proxy/api.py` - `paginated` property
- `custom_components/traefik_proxy/entity_manager.py` - `missing_map()`, save uses it
- `custom_components/traefik_proxy/__init__.py` - insecure_credentials repair (setup step 8)
- `custom_components/traefik_proxy/translations/en.json`, `de.json` - `issues.insecure_credentials`
- `tests/test_diagnostics.py`, `tests/test_repairs.py` - new
- `tests/test_translations.py` - whole-file parity tests

## Decisions Made

Planner decisions (applied as written): version/codename and cert threshold in the dump; public accessors instead of private reads; repair evaluated at the end of setup; repair and diagnostics in one plan; whole-file parity with the repair task; diff-scoped planning-reference gate.

Worker decisions:

| Decision | Reason | Alternative |
|---|---|---|
| An unparsable stored URL is replaced by `**REDACTED**` (`_safe_url`) | `split_url_userinfo` raises `ValueError` for such URLs, and the raw string could still carry userinfo; failing the download would hide all other data | Keep the raw URL / let the download fail |
| Auth type compared with `!= AuthMode.none`, missing key treated as none | The plan's `is not AuthMode.none` would always be true for the stored plain string; after migration 1.3 the key always exists | Identity comparison |
| The repair check lives in a `@callback` helper `_async_check_insecure_credentials` called after `async_track_sw_version` | Keeps `async_setup_entry` readable; same position the plan asks for (after forwarding the platforms) | Inline block in setup |
| `_async_schedule_save` reuses `missing_map()` | Removes the duplicated merge expression the new method introduced; behaviour unchanged (tests green) | Leave the duplicate |
| Repair tests also cover https + basic (4 parametrized cases) | Both credential types on both schemes | Only the three listed cases |
| `test_issue_keys_are_raised` resolves module-level `Final` string constants via `ast` | `__init__.py` passes the keys as constants (`ISSUE_ENTITIES_MIGRATED`, `ISSUE_INSECURE_CREDENTIALS`), not literals | Grep for the literal strings |
| German "Neu konfigurieren" for Reconfigure in the repair text | Same term the existing de texts already use (options description, exception messages) | "Rekonfigurieren" |
| FLOW-06, FLOW-07 and DIAG-04 marked Complete | All behaviour lines are tested and green, whole-file parity is enforced, hassfest 0 invalid | Leave FLOW-07 pending for the Phase 8 visual check (M35 covers wording/rendering only) |

## Deviations from Plan

**1. [Rule 2 - coverage of a security path] Unit tests for `_jsonable` and `_safe_url` in Task 3**
- **Found during:** Task 3 (coverage look at the new modules)
- **Issue:** the integration tests left `diagnostics.py` at 91 %: the unparsable-URL redaction branch, the non-string URL branch and the `timedelta` conversion (no current model field is a timedelta) were never run.
- **Fix:** two unit tests in `tests/test_diagnostics.py`; `diagnostics.py` now 100 %.
- **Files modified:** `tests/test_diagnostics.py` (Task 3 is "checks only"; this is a test-only commit, no production change)
- **Commit:** `4129a97`

Notes:
- The plan's "one rerun of tests/test_cert_entity_state.py allowed (D-33)" clause is void per M39; no rerun was needed or used.
- RED evidence files and gate runs used `-p no:cacheprovider` (as in 07-08) so pytest's cache plugin does not rewrite `.pytest_cache` around the evidence.

## Issues Encountered

None.

## Known Stubs

None.

## Threat Flags

None - the diagnostics endpoint and the repair are the surfaces of T-07-17..T-07-19 in the plan's threat model; all three mitigations are implemented and tested.

## User-visible changes (for the Phase 8 CHANGELOG)

- A diagnostics download is available for each Traefik entry (Settings -> Devices & services -> Traefik -> Download diagnostics). It contains the entry settings, the polling status, the parsed Traefik state, the certificate state per host and items currently marked missing; user name, password, token and any credentials in the URL are redacted.
- A repair notice warns when the integration sends credentials (basic auth or token) to Traefik over plain HTTP. It explains how to switch to HTTPS via Reconfigure and disappears once the entry uses HTTPS or no authentication; it reappears after every restart or reload while HTTP with credentials is used (ignoring it lasts until the next reload).
- All texts are available in English and German.

## Next Phase Readiness

Phase 7 is complete (9/9 plans). Phase 8 inherits: the visual check of the repair text (M35), the 25 pre-existing planning references in `__init__.py`/`config_flow.py`/`const.py` (REL-06), and the deferred items in `deferred-items.md`.

## Self-Check: PASSED
