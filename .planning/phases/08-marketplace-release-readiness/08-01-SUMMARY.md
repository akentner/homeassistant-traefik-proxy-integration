---
phase: 08-marketplace-release-readiness
plan: 01
subsystem: diagnostics
tags: [diagnostics, redaction, traefik-rules, tokenizer, security]

requires:
  - phase: 07-config-flow-ha-2026-11-baseline-observability
    provides: diagnostics download with credential/userinfo redaction (`_safe_url`, `TO_REDACT`)
provides:
  - "rules.redact_rule(rule) -> str: pure, linear, fail-closed redactor for Traefik v2/v3 HTTP rules"
  - "rules.has_matcher_call(text) -> bool: case-insensitive detection of a known matcher call"
  - "diagnostics download redacts every router `rule` and the router `errors` that repeat it"
affects: [08-03 full-tree guard, CHANGELOG 1.0.0, diagnostics]

actuals:
  tokens: 5100
  tasks: 2
  commits: 4
plan_head_before: 64afd5202ef35384f52331c8fcd722a87a25b940
plan_head_after: bed38cb1a73d1bee549dcba8889675b02185bebd

tech-stack:
  added: []
  patterns:
    - "Single-pass regex tokenizer whose alternatives start with disjoint character classes (linear, no backtracking blow-up)"
    - "Fail closed: any grammar violation replaces the whole value with the marker"

key-files:
  created: []
  modified:
    - custom_components/traefik_proxy/rules.py
    - custom_components/traefik_proxy/diagnostics.py
    - tests/test_rules.py
    - tests/test_diagnostics.py

key-decisions:
  - "Router errors are split at the raw rule; a matcher call in any remaining segment redacts the whole error (stricter than replace-only)"
  - "In a v2 Query call (argument 0 holds '='), an argument without '=' becomes the whole marker (ambiguous v2 key vs v3 value)"
  - "Only literals can carry values, so the operator grammar is not validated; every literal must sit inside a known matcher call"

patterns-established:
  - "Secret-bearing text from the Traefik API is redacted in the diagnostics dump only; entity attributes keep raw values"

requirements-completed: [REL-06]

coverage:
  - id: D1
    description: "redact_rule hides Header/HeaderRegexp/Headers/HeadersRegexp/Query/QueryRegexp values (v2 and v3, any case, backtick or double quote), keeps matcher names, keys and safe matchers, redacts unparsable rules whole, never raises"
    requirement: "REL-06"
    verification:
      - kind: unit
        ref: "tests/test_rules.py#test_redact_rule_table (21 rows)"
        status: pass
      - kind: unit
        ref: "tests/test_rules.py#test_redact_rule_random_rules_never_leak"
        status: pass
      - kind: unit
        ref: "tests/test_rules.py#test_redact_marker_matches_home_assistant"
        status: pass
    human_judgment: false
  - id: D2
    description: "Diagnostics download carries the redacted router rule; errors that repeat the rule get the redacted rule, errors with another matcher call become the marker; the router sensor attributes keep the raw rule and errors"
    requirement: "REL-06"
    verification:
      - kind: integration
        ref: "tests/test_diagnostics.py#test_diagnostics_redact_header_value_in_router_rule"
        status: pass
      - kind: integration
        ref: "tests/test_diagnostics.py#test_diagnostics_redact_router_errors_that_repeat_the_rule"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-11-15
status: complete
---

# Phase 8 Plan 01: Diagnostics rule redaction Summary

**Tokenizer-based `rules.redact_rule` hides Header/Query matcher values (v2 and v3 syntax) in the diagnostics download, including router errors that echo the rule, while entity attributes stay raw**

## Performance

- **Duration:** 8 min
- **Started:** 2026-11-15T19:28:37Z
- **Completed:** 2026-11-15T19:36:19Z
- **Tasks:** 2 (tracer + expansion, both TDD)
- **Files modified:** 4

## Accomplishments

- `rules.redact_rule(rule: str) -> str`: one regex tokenizer pass (whitespace, `&& || ! ( ) ,`, backtick literal, double-quoted Go string with escapes, identifier), then a grammar walk. Header family keeps argument 0, query family keeps the key (v3 argument 0, or every v2 `key=` prefix); safe matchers (`Host`, `HostHeader`, `HostRegexp`, `Path`, `PathPrefix`, `PathRegexp`, `Method`, `ClientIP`) stay verbatim; whitespace and operators are preserved exactly; redacted literals keep their quote character. Unknown matcher, stray literal or comma, unbalanced quote, trailing comma, empty argument list or single quotes: the whole rule becomes `**REDACTED**`. Empty or whitespace-only rules stay unchanged. Measured linear: 250 kB adversarial inputs run in under 0.1 s.
- `rules.has_matcher_call(text)`: detects a call of any known matcher name (case-insensitive, optional whitespace before `(`).
- `diagnostics._redact_router_rules` rewrites every router of the dumped snapshot: `rule` becomes the redacted rule, each `errors` entry goes through `_redact_error` (raw rule replaced by the redacted rule; a matcher call outside the verbatim rule redacts the whole error; other errors unchanged). Applied before `async_redact_data`. `sensor.py`, `models.py` and `TO_REDACT` are untouched.
- `rules.py` stays a pure module (no Home Assistant import, no module-level dict: matcher families are `frozenset`s); `_REDACTED` is pinned to Home Assistant's `REDACTED` by a test.

## User-visible changes

- Diagnostics downloads redact the values of Header/Query matchers in router rules and in router errors that repeat the rule; entity attributes are unchanged.

## Task Commits

1. **Task 1: Tracer, Header secret redacted in diagnostics, entity attribute raw**
   - `bfc4c87` test(08-01): add failing tests for router rule redaction in diagnostics (RED)
   - `d7c5d2d` feat(08-01): redact header and query values of router rules in diagnostics (GREEN)
2. **Task 2: Full matcher table, v2/v3 query forms, quoting, fail-closed cases, router errors**
   - `8d027f8` test(08-01): add redactor table, fuzz and router error redaction tests (RED)
   - `bed38cb` feat(08-01): redact router errors that quote a matcher call (GREEN)

No REFACTOR commits (nothing to clean up after GREEN).

## Files Created/Modified

- `custom_components/traefik_proxy/rules.py`: module docstring extended; `_REDACTED`, matcher `frozenset`s, `_TOKEN`, `_CALL`, `_tokenize`, `_redact_tokens`, `_redacted_arguments`, `redact_rule`, `has_matcher_call`.
- `custom_components/traefik_proxy/diagnostics.py`: module docstring extended; `_redact_error`, `_redact_router_rules`, applied to the snapshot dump.
- `tests/test_rules.py`: 4 tracer tests, 21-row `test_redact_rule_table`, whitespace-only test, 200-rule fuzz test.
- `tests/test_diagnostics.py`: rule redaction and router errors integration tests (both also assert the raw sensor attributes).

## TDD Gate Compliance

RED evidence as pytest JUnit XML in the git-ignored `.pytest_cache/gsd-red/`, recorded against the RED commit's source before each GREEN change and classified with `gsd-tools check tdd-red-evidence`.

| Target | Verdict | Semantic assessment |
|---|---|---|
| `tests/test_diagnostics.py::test_diagnostics_redact_header_value_in_router_rule` (`08-01-t1.json`, RED commit `bfc4c87`) | RED_EVIDENCE_OK | Failed on `assert 'diag-secret-41a' not in dump`: the raw rule with the header value was dumped. The 4 `test_rules.py` tracer tests failed with `AttributeError` (no `redact_rule` yet); they were not used as the RED target. |
| `tests/test_diagnostics.py::test_diagnostics_redact_router_errors_that_repeat_the_rule` (`08-01-t2.json`, RED commit `8d027f8`) | RED_EVIDENCE_OK | Failed on the errors list, index 1: `matcher Header(`A`, `x-fragment-secret`) is invalid` != `**REDACTED**`. 1 failed, 31 passed. |

At Task 2 RED the 21 table rows and the fuzz test already passed: Task 1's action specified the complete tokenizer (all matcher families, v2/v3 query, quoting, fail-closed), so Task 2's new code was the errors rewrite and `has_matcher_call`.

## Gate results

| Gate | After Task 1 | After Task 2 |
|---|---|---|
| `uv run pytest -q` | 1061 passed, no `Lingering` | 1085 passed, no `Lingering` |
| `ruff check custom_components tests` | pass | pass |
| `ruff format --check custom_components tests` | 48 files already formatted | 48 files already formatted |
| `mypy --strict custom_components/traefik_proxy` | no issues (16 files) | no issues (16 files) |
| HA 2026.11.0 venv (`ha2611-venv`, `-p no:respx`) | 1061 passed | 1085 passed |

Coverage of the touched modules (`tests/test_rules.py` + `tests/test_diagnostics.py` alone): `rules.py` 100 %, `diagnostics.py` 100 %.
Acceptance criteria: `def redact_rule(rule: str) -> str:` present; `redact_rule(` in `diagnostics.py`; `-k rule` 1 passed; no HA import in `rules.py`; `-k redact` 27 passed (≥ 16); `-k error` 1 passed; `test_no_module_level_dict` 3 passed. Tracer gate (auto mode): verify re-run green, then expansion.

Docker: not used by this plan (no containers, networks or volumes created; no cleanup check needed).

## Decisions Made

Planner worker decisions (from the plan, applied unchanged):

| Decision | Reason | Alternative not taken |
|---|---|---|
| The redactor lives in `rules.py` | Pure-module home of the existing rule parsing; no HA import needed; reusable | A private helper inside `diagnostics.py` |
| `_REDACTED` is a local constant equal to HA's `REDACTED` (pinned by a test) | Keeps `rules.py` free of Home Assistant imports | Import HA's constant into the pure module |
| Errors without the verbatim rule but with a matcher call are redacted whole | Fail closed: Traefik may quote a fragment or a normalised rule | Keep such errors |

## Worker decisions (executor)

| Decision | Reason | Alternative not taken |
|---|---|---|
| An error is split at the raw rule; a matcher call in any remaining segment redacts the whole error | An error may quote the rule and also a fragment with a secret; replacing only the rule would leak the fragment | Replace the raw rule and keep the rest unchecked (plan wording) |
| In a v2-form query call (argument 0 contains `=`), a further argument without `=` becomes the whole marker | Ambiguous: a v2 key-only argument or a v3 value; fail closed | Keep it as a key, or print `arg=**REDACTED**` (would invent an `=`) |
| The operator grammar (balanced parentheses, operator placement) is not validated; every literal must sit in a known matcher call | Only literals carry values, so this is enough for secrecy and keeps the walker small; e.g. `)(` stays as is | Full expression parser |
| Whitespace between a matcher name and `(` is accepted; names match in any letter case | Traefik's parser accepts the whitespace; any-case matching only makes redaction more eager for header/query names | Only Traefik's four case forms |
| Fuzz test uses generated rules (random matchers, cases, quotes, `!()` groups, 0-2 random character mutations) with digit-only secrets; the property is "no run of 4 digits in the output" | Fully random printable strings almost always redact whole and test nothing; digit-only secrets make leak detection independent of the parser (seed 4040: 78 whole, 98 partial, 24 unchanged) | Random printable strings only |
| Matcher-call detection exposed as `rules.has_matcher_call` with a module-level `_MATCHERS` frozenset union | One source for the name sets, no dict (plan option) | Duplicate the names in `diagnostics.py` |
| Table has 21 rows (plan: 16 minimum) | Added: whitespace kept between tokens, unclosed call, stray comma between calls | Plan minimum only |

## Deviations from Plan

None - plan executed exactly as written. (The stricter errors segment check is recorded as a worker decision above; it fulfils every plan behaviour row.)

## Issues Encountered

- One ruff finding (RUF059, unused unpacked variable) in the first GREEN draft of Task 1; fixed before the commit.

## Known Stubs

None.

## Threat Flags

None. T-08-01/T-08-02/T-08-03 mitigated as planned; T-08-04 accepted (attributes raw, pinned by both integration tests).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- CHANGELOG (later plan) can take the "User-visible changes" line verbatim.
- No comment or docstring under `custom_components/` names a decision ID, phase or plan (grep on the added lines: no match), ready for the 08-03 full-tree guard.

## Self-Check: PASSED

- Files: `custom_components/traefik_proxy/rules.py`, `custom_components/traefik_proxy/diagnostics.py`, `tests/test_rules.py`, `tests/test_diagnostics.py` exist.
- Commits on this branch: `bfc4c87`, `d7c5d2d`, `8d027f8`, `bed38cb` (FOUND, ancestors of HEAD); `git rev-list --count 64afd52..HEAD` = 4.

---
*Phase: 08-marketplace-release-readiness*
*Completed: 2026-11-15*
