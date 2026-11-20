---
phase: 07-config-flow-ha-2026-11-baseline-observability
plan: 03
subsystem: translations-and-baseline-housekeeping
tags: [translations, hassfest, home-assistant-2026.11, requirements, dead-code]
status: complete

requires:
  - phase: 07-01
    provides: "HA 2026.11.0 minimum in hacs.json/pyproject/CI and the ha2611-venv"
provides:
  - "translations/en.json is the single English source; strings.json, its mirror test and STRINGS constant are gone"
  - "test_english_texts_have_one_source guards the package root (only icons.json and manifest.json)"
  - "scripts/hassfest_checks.py strings-shape reads translations/*.json only"
  - "const.VERSION removed; Auth.header comment no longer argues by older HA releases"
  - "REQUIREMENTS REL-01/02/05 and ROADMAP Phase 8 SC1 name HA 2026.11.0 / 2026.11.x"
  - "tls_server timer threads joined on teardown (no lingering-thread teardown error)"
affects: [07-04, 07-05, 07-06, 07-07, 07-08, 07-09, phase-08]

actuals:
  tokens: 4300
  tasks: 2
  commits: 4
plan_head_before: 8b2b8dbea5fd6227b3c7cfcb5066ed1cb6cbe274
plan_head_after: 3d8b23afe490ea88843d96fb098a264ee5254566

tech-stack:
  added: []
  patterns:
    - "English texts only in translations/en.json (hassfest validates it for custom integrations)"
    - "threading.Timer used in tests: cancel() then join() before HA's verify_cleanup thread check"

key-files:
  created:
    - .planning/phases/07-config-flow-ha-2026-11-baseline-observability/deferred-items.md
  modified:
    - tests/test_translations.py
    - tests/conftest.py
    - scripts/hassfest_checks.py
    - .pre-commit-config.yaml
    - custom_components/traefik_proxy/config_flow.py
    - custom_components/traefik_proxy/const.py
    - custom_components/traefik_proxy/api.py
    - .planning/REQUIREMENTS.md
    - .planning/ROADMAP.md
  deleted:
    - custom_components/traefik_proxy/strings.json

key-decisions:
  - "Phase 07: translations/en.json is the single English source; a test pins the package root to icons.json + manifest.json"
  - "Phase 07: test threading.Timer instances are joined after cancel() so HA's verify_cleanup never sees a live timer thread"

requirements-completed: [FLOW-08]
requirements-partial: [FLOW-07]  # strings.json part; YAML step + de.json parity in 07-08/07-09

duration: 7min
completed: 2026-11-15
---

# Phase 7 Plan 03: Single English translation source and 2026.11 baseline housekeeping Summary

`strings.json` deleted with its mirror test and script reference, `const.VERSION` and the "older Home Assistant" comment gone, REQUIREMENTS/ROADMAP leftovers moved to the 2026.11.0 minimum, plus a fix for an intermittent lingering-thread teardown error in the `tls_server` fixture.

## Performance

- **Duration:** ~7 min
- **Started:** 2026-11-15T13:34:25Z
- **Completed:** 2026-11-15T13:41Z
- **Tasks:** 2 (Task 1 tracer, TDD RED + GREEN)
- **Files modified:** 9 (+1 deleted, +1 created)

## Accomplishments

- D-28: `custom_components/traefik_proxy/strings.json` deleted; `test_strings_json_equals_en_json` and the `STRINGS` constant removed; new `test_english_texts_have_one_source` asserts the package root holds only `icons.json` and `manifest.json`.
- `scripts/hassfest_checks.py` `check_strings_shape` builds its list from `sorted(TRANSLATIONS.glob("*.json"))` only; docstring, pre-commit hook name/`files` alternation and a `config_flow.py` comment point at `translations/en.json`.
- D-29: `const.VERSION` (no importer) removed.
- D-01: `Auth.header` comment keeps RFC 7617 and "aiohttp 3.14 deprecates BasicAuth" only.
- D-31: REL-01 `homeassistant: 2026.11.0`, REL-02 brand serving for HA 2026.11.0, REL-05 the HA 2026.11.x job added in Phase 7; the two Out-of-Scope rows (2026.11-only APIs, conditional form fields) deleted; audit row §5 reads "`UNDEFINED`, `ATTR_*` constants — not used (D-09)"; ROADMAP Phase 8 SC1 names HA 2026.11.0. ENT-09 unchanged.

## Task Commits

1. **Task 1: Tracer — translations/en.json is the single English source**
   - RED `4b310cc` (test) — `test_english_texts_have_one_source` failed on its assertion ("Left contains one more item: 'strings.json'")
   - Rule 1 fix `303214d` (fix) — join `tls_server` timer threads (see Deviations)
   - GREEN `c22b9bb` (feat) — delete strings.json, mirror test, script/hook/comment references
2. **Task 2: No code, comment or requirement text argues by HA releases older than 2026.11.0** — `3d8b23a` (chore)

## TDD Gate Compliance

RED evidence: pytest JUnit XML `.pytest_cache/gsd-red/07-03-t1.xml` (git-ignored), record `.pytest_cache/gsd-red/07-03-t1.json`, classified by `gsd-tools check tdd-red-evidence` → `RED_EVIDENCE_OK` (`target_test_failed`, 1 test, 1 fail, matched `tests.test_translations#test_english_texts_have_one_source`).
Semantic assessment: the target ran and failed on its planned assertion; the only extra root JSON was the mirror file D-28 deletes; no setup/collection fault. `feat(07-03)` `c22b9bb` descends from `test(07-03)` `4b310cc`.

Tracer feedback gate (auto mode): Task 1 `<verify>` re-run end-to-end on the GREEN tree — all green — then Task 2 expanded.

## Verification Results

| Gate | Result |
|---|---|
| `uv run pytest -q` (dev env, HA 2026.11.1) | 854 passed, 0 Lingering (after Task 1 and after Task 2) |
| `ha2611-venv` (HA 2026.11.0) `pytest -q -o addopts="-p no:respx" tests` | 854 passed (after Task 1 and after Task 2) |
| `ruff check custom_components tests scripts/hassfest_checks.py` | All checks passed |
| `ruff format --check custom_components tests` | 43 files already formatted |
| `mypy --strict custom_components/traefik_proxy` | no issues in 15 source files |
| `hassfest_checks.py strings-shape` | no Traceback, no `strings.json`; only the pre-existing `entity` lines for de.json/en.json (exit 1, Phase 8) |
| Task 1 + Task 2 acceptance greps | all pass |
| d18f96a verify-only line (Phase 7 heading, FLOW-08, Phase 8 SC3 `2026.11.x`) | passed before any doc edit; not redone |

Test count is unchanged (854): one test added, one mirror test removed.
Local hassfest via Docker: deferred to Phase 8 (Docker unavailable); CI's hassfest job validates `translations/en.json`.

## A-18 items (D-29) — already absent, nothing re-created

- `if TYPE_CHECKING:` followed by `pass` — absent (all four `TYPE_CHECKING` blocks import `TraefikProxyConfigEntry`)
- `_router_name` alias — absent
- `_host_port` — absent
- `_reset` test seam — absent
- `cert_cache_availability` alias — absent
- `const.VERSION` — was present, removed in `3d8b23a`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Lingering-thread teardown error in the `tls_server` fixture**
- **Found during:** Task 1 (first full `uv run pytest -q` run: `ERROR tests/test_tls.py::test_probe_expired_leaf_is_read_unverified - AssertionError`, 854 passed, 1 error)
- **Issue:** `TlsServer.wait_connections` and `wall_clock_watchdog` (tests/conftest.py, Phase 6 WR-04) call `threading.Timer.cancel()` without `join()`. The thread stays alive briefly after `cancel()` (measured: alive in 2000/2000 cases right after cancel); HA's `verify_cleanup` asserts no new non-dummy thread exists after the test, so a slow exit raises `AssertionError` in teardown. Not caused by this plan's change. Investigated per M39 (no rerun used as a pass).
- **Fix:** `timer.join()` after `timer.cancel()` in both places. No retry, sleep or skip.
- **Files modified:** tests/conftest.py
- **Commit:** `303214d`

**2. [Rule 1 - Stale reference] Remaining `strings.json` mentions outside the plan's file list**
- **Found during:** Task 1 (`git grep strings.json`)
- **Issue:** `.pre-commit-config.yaml` hook name + `files` alternation and a `config_flow.py` comment named the deleted file.
- **Fix:** hook name "translations/*.json shape", `files` alternation reduced to `translations/.*`; comment points at `translations/en.json`. The hook's wrong `custom_components/traefik/` base path is left for REL-04.
- **Commit:** `c22b9bb`

### Process note

The first attempt at committing `303214d` swept the already-staged `git rm strings.json` into the fix commit. Both unpushed commits were re-made with `git reset --soft 4b310cc` + `git restore --staged` (no working-tree change) so the deletion lives in the GREEN commit.

## Worker Decisions

| Decision | Reason | Alternative not taken |
|---|---|---|
| RED test pins the package root to `icons.json` + `manifest.json` without naming the deleted file | Gives the tracer a real RED and guards re-introduction while keeping the acceptance grep (`strings.json` absent from test_translations.py) | No RED (deletion-only task) |
| Fix the timer-thread race in this plan | M39: any failure is real and the gates must be green; the fix is two `join()` calls, deterministic | Log only and accept a red run |
| `wait_closed()` dead code in `tls_server` teardown left alone | No observed failure; changing teardown order is beyond 07-03 | Fix it now |
| FLOW-07 stays `Pending` in REQUIREMENTS.md (`requirements.mark-complete` set it, reverted) | Only the `strings.json` part is done; the YAML step and de.json parity land in 07-08/07-09 | Mark Complete now |
| REL-05 wording "the test job against HA 2026.11.x added in Phase 7" | Plan text; the job exists since 07-01 | "a test job" |

## Deferred Items

See `deferred-items.md`: pre-commit `files:` paths still `custom_components/traefik/` (REL-04), `hassfest_checks.py` `entity` false positive (Phase 8, REL-04), `tls_server` `wait_closed()` dead code.

## User-visible changes (Phase 8 CHANGELOG)

None.

## Known Stubs

None.

## Next Phase Readiness

07-04..07-09 edit only `translations/en.json` (+ `de.json`); no second English copy exists.

## Self-Check: PASSED

- FOUND: deferred-items.md, tests/test_translations.py, scripts/hassfest_checks.py; strings.json absent
- FOUND commits: 4b310cc, 303214d, c22b9bb, 3d8b23a (all ancestors of HEAD)
