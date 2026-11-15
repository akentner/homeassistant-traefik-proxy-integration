---
phase: 07-config-flow-ha-2026-11-baseline-observability
plan: 07
subsystem: options-flow
tags: [options-flow, entity-manager, grace-period, per-item-entities, translations, home-assistant-2026.11]
status: complete

requires:
  - phase: 07-06
    provides: "TraefikProxyOptionsFlow(OptionsFlowWithReload) with scan_interval / verify_ssl / tls_warn_days, merged option storage, int coercion"
provides:
  - "const.CONF_/DEFAULT_/MIN_/MAX_MISSING_GRACE_HOURS (1..168 h, default 24); const.MISSING_GRACE_PERIOD removed"
  - "entity_manager.missing_grace_period(entry) -> timedelta; TraefikEntityManager._grace used by every deadline check"
  - "Options form: scan_interval, verify_ssl, tls_warn_days, per_item_entities, missing_grace_hours (in that order)"
  - "en + de options texts (title, description, data, data_description for all five fields); options.error removed"
  - "de parity test covers config, options and selector in addition to exceptions/device/entity/issues"
affects: [07-08, 07-09, phase-08]

actuals:
  tokens: 8800
  tasks: 2
  commits: 4
plan_head_before: c5c61b260e568346079d565f16a7335b96213b4b
plan_head_after: 52db8fa5e888e7c3ef98a07266cb21b26d09e407

tech-stack:
  added: []
  patterns:
    - "Runtime knobs from options are read once per setup (constructor) and apply through the OptionsFlowWithReload reload"
    - "Translation-completeness test opens the real options form and compares its field names with data/data_description in en and de"

key-files:
  created: []
  modified:
    - custom_components/traefik_proxy/const.py
    - custom_components/traefik_proxy/entity_manager.py
    - custom_components/traefik_proxy/config_flow.py
    - custom_components/traefik_proxy/translations/en.json
    - custom_components/traefik_proxy/translations/de.json
    - tests/test_entity_manager.py
    - tests/test_options_flow.py
    - tests/test_translations.py

key-decisions:
  - "Phase 07: the missing-entity grace period is an option (missing_grace_hours, 1-168 h, default 24 h), read once per setup; stored missing-since times survive a reload, so a shortened period removes long-missing items within one check interval after the reload"
  - "Phase 07: per_item_entities is part of the options form (BooleanSelector, default on); all five options are labelled and described in en and de"

requirements-completed: [FLOW-02]

coverage:
  - id: D1
    description: "missing_grace_hours: box NumberSelector 1..168 h step 1, default 24; 0/169 raise InvalidData; 1/168 accepted; 24.9 stored as int 24"
    requirement: FLOW-02
    verification:
      - kind: integration
        ref: "tests/test_options_flow.py#test_options_form_selectors, test_values_outside_a_range_raise_invalid_data, test_missing_grace_hours_bounds_are_accepted, test_missing_grace_hours_stored_as_truncated_int"
        status: pass
    human_judgment: false
  - id: D2
    description: "Configured grace period: 2 h keeps a vanished router at 2 h - 1 s and removes it at 2 h; after an options change to 2 h a router missing 3 h is removed within 5 min, with 48 h it stays with its original missing-since time"
    requirement: FLOW-02
    verification:
      - kind: integration
        ref: "tests/test_entity_manager.py#test_configured_grace_period_removes_vanished_router, test_changed_grace_period_applies_after_options_reload[2-True], [48-False]"
        status: pass
    human_judgment: false
  - id: D3
    description: "per_item_entities through the options flow: off removes router/service entities and the Routers/Services sub-devices after the reload, on recreates them; identical second off-submit does not reload"
    requirement: FLOW-02
    verification:
      - kind: integration
        ref: "tests/test_options_flow.py#test_per_item_entities_off_and_on_through_the_options_flow, test_per_item_entities_off_twice_reloads_once"
        status: pass
    human_judgment: false
  - id: D4
    description: "Form order and empty-options defaults (15 / effective verify_ssl / 14 / True / 24); first submit stores all five keys"
    requirement: FLOW-02
    verification:
      - kind: integration
        ref: "tests/test_options_flow.py#test_options_form_selectors, test_options_form_defaults_without_options, test_first_submit_of_empty_options_stores_all_five_keys"
        status: pass
    human_judgment: false
  - id: D5
    description: "Every options field labelled and described in en and de; no options error text; de parity over config/options/selector"
    requirement: FLOW-02
    verification:
      - kind: unit
        ref: "tests/test_translations.py#test_every_option_field_is_labelled_and_described, test_de_matches_en_keys_and_placeholders"
        status: pass
    human_judgment: true
    rationale: "Wording and rendering of the form texts in the frontend is the Phase 8 visual check (M35)"

duration: 12min
completed: 2026-11-15
---

# Phase 7 Plan 07: Grace period and per-item toggle in the options form Summary

**The options form now sets how long a vanished router, service or certificate stays "missing" (1-168 h, default 24 h; the entity manager reads it once per setup) and whether per-router/per-service entities exist; all five options carry an English and German label and description.**

## Performance

- **Duration:** ~12 min in this session (resumed, ~14:30Z - 14:42Z); the interrupted first executor's time is not measurable
- **Tasks:** 2 (Task 1 tracer; both TDD RED + GREEN)
- **Files modified:** 8

## Resumption

The plan was resumed after a host reboot killed the previous executor. No 07-07 commit existed (HEAD `c5c61b2`); the working tree held uncommitted changes in `tests/test_entity_manager.py` and `tests/test_options_flow.py` (+131/-19, backup at `~/.cache/traefik-proxy-integration/07-07-partial.patch`).

- Inspected against the plan: the diff was exactly Task 1's RED test set (grace-period selector, bounds 0/169/1/168, 24.9 -> 24 int, 2 h boundary test, shorten/lengthen-after-options-reload test with the stored missing-since check, existing options tests extended with `missing_grace_hours`). Nothing of Task 2 was present.
- Kept unchanged and committed as the Task 1 RED commit `61bcc39` after confirming RED (14 failed, 44 passed) and recording RED evidence. Nothing was dropped or rewritten.

## Accomplishments

- `const.py`: `CONF_MISSING_GRACE_HOURS`, `DEFAULT_MISSING_GRACE_HOURS = 24`, `MIN_MISSING_GRACE_HOURS = 1`, `MAX_MISSING_GRACE_HOURS = 168`; the fixed 24 h constant is gone; the `MISSING_CHECK_INTERVAL` comment says removal lands at most one interval after the configured period.
- `entity_manager.py`: `missing_grace_period(entry)` next to `per_item_entities_enabled`; `TraefikEntityManager.__init__` stores it as `self._grace`; stored-orphan check at registration, periodic deadline check and the removal debug log use it; module docstring describes the configured, once-per-setup period. Stored missing-since times are untouched by a changed period.
- `config_flow.py`: options form gets `per_item_entities` (BooleanSelector, default current or True, stored via `bool()`) and `missing_grace_hours` (box NumberSelector 1..168 step 1 unit `h`, default current or 24, stored via `int()`), in the order scan_interval, verify_ssl, tls_warn_days, per_item_entities, missing_grace_hours. The `{**current, ...}` merge and the reload-only-on-change behaviour of 07-06 are unchanged.
- `translations/en.json` / `de.json`: `options.step.init` with title, description (changes apply after the automatic reload; address/credentials via Reconfigure), `data` and `data_description` for all five fields; `options.error.scan_interval_out_of_range` removed. German uses "du"; no `://`.
- `tests/test_translations.py`: `PHASE_SECTIONS` now includes config, options and selector; new test opens the real options form and requires `data` and `data_description` keys in en and de to equal the form fields, and no `options.error`.

## Task Commits

1. **Task 1: grace period as an option (tracer)**
   - RED `61bcc39` (test) - kept from the interrupted executor
   - GREEN `9d3eb7a` (feat)
2. **Task 2: per-item toggle; options texts en + de**
   - RED `52b8c00` (test)
   - GREEN `52db8fa` (feat)

## TDD Gate Compliance

RED evidence as pytest JUnit XML in the git-ignored `.pytest_cache/gsd-red/`, recorded before each GREEN commit this time and classified with `gsd-tools check tdd-red-evidence`.

| Target | Record | Verdict | Semantic assessment |
|---|---|---|---|
| `tests/test_entity_manager.py::test_configured_grace_period_removes_vanished_router` | `07-07-t1.json` | RED_EVIDENCE_OK | Ran and failed on the removal assertion at 2 h (registry entry still present under the fixed 24 h period); the 2 h - 1 s assertions passed; no collection/fixture fault |
| `tests/test_options_flow.py::test_options_form_selectors` | `07-07-t2.json` | RED_EVIDENCE_OK | Ran and failed on the field-order assertion (`per_item_entities` missing at index 3); no collection/fixture fault |

At Task 1 RED, 14 tests failed (the options tests via `InvalidData` for the unknown `missing_grace_hours` key, the entity-manager tests on removal assertions). At Task 2 RED, 16 failed (options tests via `InvalidData` for `per_item_entities`, the order/default assertions, both translation tests). RED and GREEN commits exist for both tasks, each GREEN after its RED.

Tracer gate (auto mode): after Task 1 GREEN all verify commands were re-run end-to-end and passed before Task 2 started.

## Gate results

| Gate | After Task 1 | After Task 2 |
|---|---|---|
| `uv run pytest -q` (dev env) | 955 passed | 959 passed |
| "Lingering" in output | none | none |
| `ruff check custom_components tests` | clean | clean |
| `ruff format --check custom_components tests` (44 files) | clean | clean |
| `uv run mypy --strict custom_components/traefik_proxy` (15 files) | no issues | no issues |
| ha2611-venv suite (HA 2026.11.0) | 955 passed | 959 passed |

No failure in any gate run; no rerun used (M39). Acceptance: Task 1 - `MISSING_GRACE_PERIOD` absent from `custom_components/` and `tests/`, the two const lines and `def missing_grace_period` present, `-k grace` 13 passed (>= 4). Task 2 - the `data_description` JSON check exits 0 for en and de, `scan_interval_out_of_range` absent from `custom_components/`, no `://` in translations, `-k "per_item or order or empty"` 3 passed (>= 3).

Local hassfest (throwaway `docker run --rm ... ghcr.io/home-assistant/hassfest`, image 10 days old): `Integrations: 1, Invalid integrations: 0` (translations validated). No container left behind.

## Files Created/Modified

- `custom_components/traefik_proxy/const.py` - grace-hours constants, fixed period removed
- `custom_components/traefik_proxy/entity_manager.py` - `missing_grace_period`, `_grace`, docstring
- `custom_components/traefik_proxy/config_flow.py` - two new option fields, docstrings
- `custom_components/traefik_proxy/translations/en.json`, `de.json` - options texts
- `tests/test_entity_manager.py`, `tests/test_options_flow.py`, `tests/test_translations.py`

## Decisions Made

Planner decisions (applied as written): `int()` truncation (24.9 -> 24); grace period as tracer; all options texts written once here; de parity extended to config/options/selector here.

Worker decisions:

| Decision | Reason | Alternative |
|---|---|---|
| Kept the interrupted executor's uncommitted Task 1 tests unchanged as the RED commit | They matched every Task 1 behavior line and acceptance check (verified RED with valid evidence); rewriting would only add risk | Drop and rewrite them |
| `test_options_outside_the_form_are_kept` now uses an arbitrary key `not_in_form` | `per_item_entities` became a form field, so it no longer exercises the 07-06 merge property | Delete the test (would lose the merge guarantee 07-06 asked to keep) |
| Labels lost their range/unit hints ("Polling interval" instead of "Polling interval (seconds, 15-300)"); ranges live in `data_description` | The selectors show the unit; the description field is where HA renders explanatory text, so the label stays short | Keep ranges in the labels |
| Options description does not point to Reconfigure for TLS verification | `verify_ssl` is in this form; pointing there for it would contradict the form | Plan's wording "URL changes use Reconfigure" extended with credentials only |
| Options texts test opens the real options form and compares field names (instead of a hard-coded list) | A new form field without texts fails the test automatically | Static key list |
| `per_item` test asserts device identifiers by suffix (`routers`, `services`, `certificates`) with the domain spelled as a literal | Same persistence-contract style as the option keys in this file | Import `device_identifier` / `TraefikDevice` |
| FLOW-02 marked Complete | 07-06 delivered the listener removal and selectors, this plan the per-item toggle and grace period; 07-08/07-09 do not list FLOW-02 | Leave Pending |
| Ran local hassfest although the plan does not ask for it | Docker is available again and this plan changes translations; cheap schema check | Defer to Phase 8 |

## Deviations from Plan

None in scope - plan executed as written. Notes:
- The plan's "one rerun of tests/test_cert_entity_state.py allowed (D-33)" clause is void per M39; no rerun was needed or used.
- Pre-existing planning references in `const.py` comments (e.g. "Phase 2 — Plan 02-02", "CONTEXT.md D-09") were left alone: Phase 8's REL-06 sweep owns them (07-09 scoped gate); lines added by this plan carry none.

## Issues Encountered

None.

## Known Stubs

None.

## User-visible changes (for the Phase 8 CHANGELOG)

- New option "Create router and service entities" (default on): off keeps the aggregate, diagnostic and certificate entities and removes the router and service entities after the automatic reload; on recreates them.
- New option "Grace period for missing entities" (1-168 h, default 24 h): how long a router, service or certificate that vanished from Traefik stays as "missing" before its entity is removed. Shortening it removes items already missing longer within about five minutes after saving; the time an item went missing is kept across the reload.
- All options have a label and a description in English and German (the options form is now translated into German).

## Self-Check: PASSED
