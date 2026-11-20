---
phase: 08-marketplace-release-readiness
plan: 13
subsystem: release
tags: [release-notes, hacs-default, draft-pr, deferred-items, push-readiness, hassfest]

requires:
  - phase: 08-marketplace-release-readiness
    provides: "CHANGELOG 1.0.0 and README (08-10), CLAUDE.md regeneration 52f41b2 (08-11), review dispositions (08-12), 08-LOCAL-VALIDATION.md (08-08), 08-VISUAL-CHECK.md (08-09)"
provides:
  - "08-RELEASE-NOTES-v1.0.0.md (required actions first, highlights, CHANGELOG link)"
  - "08-HACS-DEFAULT-PR.md (insertion after akentner/homeassistant-kroki-integration, filled template with link markers)"
  - "08-DRAFT-PR.md (title/body for feat/marketplace-polish -> main, CI checks, user actions, trademark decision)"
  - "closed deferred-items records of Phases 4, 5 and 7"
  - "Final pre-push run in 08-LOCAL-VALIDATION.md"
affects: [phase-08-verification, manager-push-M41, user-release-v1.0.0, hacs-default-submission]

actuals:
  tokens: 6373
  tasks: 3
  commits: 4
plan_head_before: 7cb200b7cb03a50d9a715279461dd37b43283c65
plan_head_after: cfa2871211a6f773adf159b109b13151efb65847

tech-stack:
  added: []
  patterns: []

key-files:
  created:
    - .planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0.md
    - .planning/phases/08-marketplace-release-readiness/08-HACS-DEFAULT-PR.md
    - .planning/phases/08-marketplace-release-readiness/08-DRAFT-PR.md
  modified:
    - .planning/phases/04-data-layer-correct-lean/deferred-items.md
    - .planning/phases/05-entity-model-lifecycle/deferred-items.md
    - .planning/phases/07-config-flow-ha-2026-11-baseline-observability/deferred-items.md
    - .planning/phases/08-marketplace-release-readiness/08-LOCAL-VALIDATION.md

key-decisions:
  - "hacs/default list and PR template read anonymously (curl, no token) instead of gh api: hard limit forbids authenticated remote calls"
  - "REL-07 stated as pending first PR CI run (HACS job) in every draft; make hacs-action not run (user decision)"
  - "git ls-remote replaced by local refs check (no upstream, no remote-tracking ref for the branch); hard limit"
  - "Validation record does not contain 'All (10) checks passed'; the plan's grep for it fails by design rather than being satisfied by a non-result"

requirements-completed: []  # REL-07 drafts delivered, hacs/action pending CI; REL-08 push/PR is the manager's action (M41). Neither marked complete in REQUIREMENTS.md.

coverage:
  - id: D1
    description: "Release-notes, hacs/default PR and Draft-PR drafts in the phase directory only, required actions first, no private hosts or tokens"
    requirement: REL-07
    verification:
      - kind: other
        ref: "Task 1 verify + acceptance commands (test -s, grep repo line/branch/CHANGELOG, private-name grep, awk first heading, ls-files location check)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Deferred items of Phases 4, 5, 7 resolved with commit pointers"
    verification:
      - kind: other
        ref: "Task 2 verify: no 'status: open' in 04; >=2 resolved markers and 7-hex commit pointers in 05/07"
        status: pass
    human_judgment: false
  - id: D3
    description: "Final pre-push gates green on the final tree (except hacs/action, deferred to CI)"
    requirement: REL-08
    verification:
      - kind: unit
        ref: "uv run pytest -q (1152 passed, 99.29 %); make test-min-ha; ha2611-venv pytest; ruff/format/mypy; pre-commit; make hassfest"
        status: pass
      - kind: other
        ref: "make hacs-action (REL-07)"
        status: unknown
    human_judgment: true
    rationale: "hacs/action needs the user's GitHub token; REL-07 is proven only by the first PR run of validate.yml (user decision)"
  - id: D4
    description: "Logo trademark use (A3/A8) acceptable"
    verification: []
    human_judgment: true
    rationale: "Traefik Labs trademark guidelines not reviewed; user decision listed in 08-DRAFT-PR.md"

duration: 30min
completed: 2026-11-15
status: complete
---

# Phase 8 Plan 13: Release drafts and push readiness Summary

**Release notes, hacs/default PR text and Draft-PR body drafted in the phase directory; Phase 4/5/7 deferred items closed with commit pointers; final gates green on the final tree (1152 tests, 99.29 % coverage, hassfest 0 invalid) with hacs/action (REL-07) pending the first PR CI run.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-11-15T21:03Z
- **Completed:** 2026-11-15T21:33Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- `08-RELEASE-NOTES-v1.0.0.md`: "Required actions" first (HA 2026.11.0; router binary sensors -> enum sensors; dismiss "Traefik entities were replaced"; Refresh now replaces reload; YAML users re-add via UI; check "Traefik credentials are sent unencrypted"; re-assign device areas), 8 highlights, link to `CHANGELOG.md#100---unreleased` with the anchor-update note. No internal IDs.
- `08-HACS-DEFAULT-PR.md`: read anonymously from `hacs/default@d1bec96` (2026-11-10, 5165 entries, sorted case-insensitively): insert `"akentner/homeassistant-traefik-proxy-integration",` after `"akentner/homeassistant-kroki-integration"` and before `"akinin/ha_keenetic"`; full template filled with `<RELEASE_URL>`, `<HACS_ACTION_RUN_URL>`, `<HASSFEST_RUN_URL>`; steps (fork from personal account, request no reviews, wait for bot checks); trademark open item.
- `08-DRAFT-PR.md`: title, body with Phase 4-8 summary, breaking changes, evidence table (REL-07 pending CI), `.planning/` note, CI checks (five jobs, hashed min-HA install, hacs with `permissions: {}`), maintenance notes (hassfest SHA pin, moving images), user actions after merge (CHANGELOG date, tag v1.0.0, release, hacs/default PR, optional negative control), decision A3/A8 with icon-only fallback.
- Deferred items closed: 04 SyntaxWarning (`f4bf7d7` + guards `2fdedc3`, `b6116e5`), 04 invalid_url (`6f1ab67`), 05 README reload (`33e6d4f`), 05 CLAUDE.md stack (`52f41b2`), 07 pre-commit paths + strings-shape (`b6116e5`), 07 tls_server teardown (`bcff94f`).

## Task Commits

1. **Task 1 (tracer): drafts** - `abe3823` (docs). Tracer gate (auto mode): verify re-run passed, continued.
2. **Task 2: deferred items** - `435751b` (docs)
3. **Task 3: final pre-push run** - `a5038ae` (docs, results into Draft PR body), `cfa2871` (docs, 08-LOCAL-VALIDATION.md)

## Final gate table (HEAD 435751b code tree; later commits are `.planning/` only)

| Gate | Exit | Result |
|---|---|---|
| `uv run pytest -q` | 0 | 1152 passed, 5 warnings; coverage 99.29 % (gate 99) ; no Lingering |
| `ruff check custom_components tests` | 0 | All checks passed |
| `ruff format --check custom_components tests` | 0 | 50 files already formatted |
| `mypy --strict custom_components/traefik_proxy` | 0 | no issues in 16 files |
| `make test-min-ha` (HA 2026.11.0 hashed lock) | 0 | 1152 passed, coverage gate reached |
| ha2611-venv suite (HA 2026.11.0) | 0 | 1152 passed |
| `uvx pre-commit run --all-files` | 0 | 13/13 Passed |
| `make hassfest` (digest `sha256:da65229…`) | 0 | Integrations: 1, Invalid integrations: 0 |
| `make hacs-action` | not run | REL-07 pending first PR run of validate.yml (HACS job) |
| README consistency (08-10) | 0 | `missing: []`, no private hosts, no reload/YAML |
| Planning-reference grep (08-03) + 4 guard tests | 0 | no match, 4 passed |

## Last read-only checks (outputs)

```
git status --porcelain -- . ':!.planning/config.json' ':!.planning/state.json'   -> (empty), exit 0
git status --short  ->  M .planning/config.json / ?? .planning/state.json   (GSD runtime files, not touched)
git tag --list      ->  v0.1.0 v0.1.1 v0.1.2 v0.1.3 v0.1.4 v0.1.6 v0.2.0 v0.2.1 v0.3.0   (exit 0)
git for-each-ref refs/remotes/ -> origin/HEAD, origin/main, origin/renovate/configure   (no marketplace-polish)
git branch -vv      -> feat/marketplace-polish has no upstream (never pushed)
docker ps -a grep ha-visual-08|traefik-harness|hassfest|hacs/action -> none (exit 0)
docker containers/networks/volumes == docker-baseline-phase8.txt (before/after hassfest identical)
git rev-parse --abbrev-ref HEAD -> feat/marketplace-polish; git rev-list --count origin/main..HEAD -> 331 (before SUMMARY commit)
```

## Files Created/Modified

- `.planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0.md` - release body draft
- `.planning/phases/08-marketplace-release-readiness/08-HACS-DEFAULT-PR.md` - catalog submission draft
- `.planning/phases/08-marketplace-release-readiness/08-DRAFT-PR.md` - Draft PR title/body
- `.planning/phases/0{4,5,7}-*/deferred-items.md` - resolutions with commit pointers
- `.planning/phases/08-marketplace-release-readiness/08-LOCAL-VALIDATION.md` - "Final pre-push run"

## Decisions Made / Worker decisions

| Decision | Reason | Alternative |
|---|---|---|
| hacs/default `integration` and `.github/PULL_REQUEST_TEMPLATE.md` fetched with anonymous `curl` (raw.githubusercontent.com, api.github.com) into a scratch directory, parsed with jq/python | Hard limit: no authenticated remote calls; public data needs no token | `gh api` GET (authenticated, plan text) |
| Insertion point computed with `sorted(key=str.casefold)` check on the live list | List is case-insensitively sorted (raw sort is not) | Raw byte sort (would misplace entries) |
| Release-notes link uses the literal `#100---unreleased` anchor plus an HTML-comment note to change it to `#100---YYYY-MM-DD` | Plan text; a working link until the date is set | A placeholder marker |
| Draft PR body carries internal IDs (REL-07, M1, A3/A8) | Audience is the manager/user; release notes stay ID-free as the plan requires | Strip IDs everywhere |
| Final min-HA and pre-commit results written into the Draft PR body in an own commit `a5038ae` before the validation commit | Done criterion: drafts usable "without further writing"; the validation commit stays the last non-SUMMARY commit | Leave "see 08-LOCAL-VALIDATION.md" |
| Icon-only fallback described as "delete the four logo PNGs, adjust tests/test_brand.py and docs/BRAND.md" | D-03 escape hatch from 08-05; exact brand file set guard in tests | — |

## Deviations from Plan

1. **[Hard limit] `make hacs-action` not run (Task 3 step 1).** User decision 2026-11-15 (REL-07 deferred to CI). Consequently the Task 3 verify `grep -q "All (10) checks passed" 08-LOCAL-VALIDATION.md` **fails by design** (exit 1); the phrase was deliberately not written, so the check is not satisfied by a non-result. REL-07's hacs/action part is pending the first PR run of `validate.yml` (HACS job). The negative control is a manual follow-up for the user.
2. **[Hard limit] `git ls-remote origin` not run (Task 3 verify).** Replaced by local evidence: no upstream for `feat/marketplace-polish`, no remote-tracking ref for it, tags unchanged. The manager can run `git ls-remote origin` before pushing.
3. **[Hard limit] `gh api` GETs replaced by anonymous curl** (Task 1 step 2), see decisions.
4. **Extra commit `a5038ae`** (Draft PR results) inside Task 3, see decisions.
5. **REQUIREMENTS.md left unchanged.** `requirements.mark-complete REL-07 REL-08` marked REL-08 `[x]` / Complete although the branch is not pushed and no Draft PR exists; reverted (`git checkout -- .planning/REQUIREMENTS.md`). REL-07 stays "Pending (first PR CI run, M43)", REL-08 "Pending" until the manager's push + Draft PR.
6. 08-LOCAL-VALIDATION.md's older sentence "08-13 re-runs both validators before the push" is marked superseded in the new section, not edited in place.

No code change was needed: every gate that ran was green.

## Docker cleanup

Only `make hassfest` (`--rm`, no ports, no network). `docker ps -a`, `docker network ls`, `docker volume ls` identical before/after and equal to `docker-baseline-phase8.txt`.

## Open items for the user (also in the drafts)

- REL-07: pending — proven by the first PR run of validate.yml (HACS job).
- hacs/action negative control (`computers_network.bogus`): manual follow-up, needs the user's token.
- Trademark assumption A3/A8 (Traefik Labs guidelines not reviewed): keep the logo or ship only the icon; decide before the release and the hacs/default PR.
- First CI run: all five `validate.yml` jobs (esp. `test-min-ha` hashed install and `hacs` with `permissions: {}`); hassfest action SHA pin `# master (2026-10-26)` may need manual bumps; hassfest/hacs actions pull moving images.

## Hand-off

**Manager:** push `feat/marketplace-polish` and open the Draft PR with `08-DRAFT-PR.md` (M41) after phase verification. Then user: merge, set the CHANGELOG date, tag v1.0.0, publish the release with `08-RELEASE-NOTES-v1.0.0.md`, open the hacs/default PR with `08-HACS-DEFAULT-PR.md`.

## Self-Check: PASSED

- FOUND: 08-RELEASE-NOTES-v1.0.0.md, 08-HACS-DEFAULT-PR.md, 08-DRAFT-PR.md, 08-LOCAL-VALIDATION.md "Final pre-push run"
- FOUND commits: abe3823, 435751b, a5038ae, cfa2871 (ancestors of HEAD)
