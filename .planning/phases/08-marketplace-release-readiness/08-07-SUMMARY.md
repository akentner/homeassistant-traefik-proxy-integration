---
phase: 08-marketplace-release-readiness
plan: 07
subsystem: ci, release
tags: [github-actions, sha-pinning, dependabot, release-check, uv, hashed-lock, timeout-minutes]

requires:
  - phase: 08-marketplace-release-readiness
    provides: 08-06 Makefile command strings (lint/typecheck/test/test-min-ha) and the hashed minimum-HA lock .github/requirements-min-ha.txt
provides:
  - scripts/check_release_tag.py (check(tag, version), main(argv)) + tests/test_release_tag_check.py
  - .github/workflows/release.yml (tag == manifest version gate, creates nothing)
  - .github/workflows/validate.yml on main pushes, PRs, nightly and manual runs; 11 SHA-pinned uses lines over both workflows; timeouts; locked min-HA job
  - .github/dependabot.yml (github-actions weekly)
affects: [08-08 (manifest bump to 1.0.0: release check reads the manifest, tests keep passing), 08-13 (CHANGELOG developer notes, post-push CI check list)]

actuals:
  tokens: 2500     # chars/4 over the realized diff (10070 chars)
  tasks: 2
  commits: 3
plan_head_before: 8feff28f3dbfdbe07fc378dd210a776430722ecb
plan_head_after: df061f4b438b441b7bc109caf87e09bc23ce0522

tech-stack:
  added: []
  patterns:
    - "Event payload text (tag names) reaches a run step only via env: and argv, never via ${{ }} in run:"
    - "CI run: strings = Makefile command strings, gated by a substring parity check"
    - "Actions pinned to 40-hex commit SHAs with a trailing # <version> comment; Dependabot proposes bumps"

key-files:
  created:
    - scripts/check_release_tag.py
    - tests/test_release_tag_check.py
    - .github/workflows/release.yml
    - .github/dependabot.yml
  modified:
    - .github/workflows/validate.yml

key-decisions:
  - "RED commit carries an interface-only script skeleton (check -> None, main -> 0) so the RED tests fail on assertions instead of a fixture load error (INVALID_RED otherwise)"
  - "main() without exactly one argument returns 2 (usage error), never 0, so a workflow that forgets the tag cannot pass"
  - "Each CI command is its own run: step so it matches a Makefile line verbatim (parity gate), instead of one multi-line run block"

patterns-established:
  - "Release tag check: python3 scripts/check_release_tag.py \"$TAG\" with TAG from env"

requirements-completed: [REL-05, DIST-04, REL-01, REL-04]

coverage:
  - id: D1
    description: "Release check fails when the tag (minus one leading v) differs from manifest.json version; creates nothing"
    requirement: DIST-04
    verification:
      - kind: unit
        ref: "tests/test_release_tag_check.py (8 passed)"
        status: pass
      - kind: other
        ref: "python3 scripts/check_release_tag.py v0.3.0 -> 0; v9.9.9 -> 1 with ::error:: line"
        status: pass
      - kind: other
        ref: "release.yml yaml gate: permissions {}, timeout-minutes 5, no needs; no ${{ in run:; 1 uses line, SHA-pinned"
        status: pass
    human_judgment: false
  - id: D2
    description: "validate.yml triggers on push to main, PRs to main, nightly cron 17 3 * * * and workflow_dispatch; permissions {}"
    requirement: REL-05
    verification:
      - kind: other
        ref: "grep workflow_dispatch + cron gate (rc 0); parsed on: block = push[main], pull_request[main], schedule, workflow_dispatch"
        status: pass
    human_judgment: false
  - id: D3
    description: "Every job in both workflows has timeout-minutes and no needs; all 11 uses lines pinned to 40-hex SHAs with a version comment"
    requirement: REL-05
    verification:
      - kind: other
        ref: "uses count 11, unpinned 0; timeout/needs gate prints [] (rc 0); pins re-resolved with git ls-remote on 2026-11-15"
        status: pass
    human_judgment: false
  - id: D4
    description: "test-min-ha installs the hashed lock with the make test-min-ha commands and no addopts override; lint/test/test-min-ha run: strings are in the Makefile"
    requirement: REL-04
    verification:
      - kind: other
        ref: "Makefile parity gate: missing: [] (rc 0); grep uv pip sync --require-hashes (rc 0); ! grep addopts= (rc 0)"
        status: pass
      - kind: integration
        ref: "make test-min-ha (fresh .venv-min-ha from the lock) -> 1152 passed, coverage 99.29 %"
        status: pass
    human_judgment: false
  - id: D5
    description: "Dependabot updates github-actions weekly"
    requirement: REL-05
    verification:
      - kind: other
        ref: "grep 'package-ecosystem: github-actions' .github/dependabot.yml (rc 0); YAML parses"
        status: pass
    human_judgment: false
  - id: D6
    description: "Workflows behave as intended on GitHub (first real run after the manager's push)"
    requirement: REL-05
    verification: []
    human_judgment: true
    rationale: "Workflows are validated locally only (no push, no workflow runs, REL-08); the post-push CI run must confirm them"

duration: 5min
completed: 2026-11-15
status: complete
---

# Phase 8 Plan 07: Release-grade CI and release gate Summary

**Release workflow that fails when the `v`-stripped tag differs from `manifest.json` (tested script, tag via env/argv only), and `validate.yml` on main pushes, PRs, nightly and manual runs with every action SHA-pinned, 15-minute timeouts, the hashed minimum-HA lock installed with the Makefile's exact commands, plus Dependabot for actions.**

## Performance

- **Duration:** about 5 min
- **Started:** 2026-11-15T20:28:58Z
- **Completed:** 2026-11-15T20:33:46Z
- **Tasks:** 2 (both committed; Task 1 as RED + GREEN)
- **Files:** 4 created, 1 modified

## Accomplishments

- `scripts/check_release_tag.py`: `check(tag, version)` strips exactly one leading `v` (`str.removeprefix`). `main(argv)` reads `custom_components/traefik_proxy/manifest.json` relative to the repo root. It prints `::error::tag <tag> (version <x>) != manifest.json version <y>` and returns 1 on mismatch, a confirmation and 0 on match, and 2 on a usage error.
- `.github/workflows/release.yml` ("Release check"): runs on `release: published` and pushed `v*` tags, with `permissions: {}`. Its one job `tag-matches-manifest` has `timeout-minutes: 5` and checkout pinned to `3d3c42e…` (`# v7.0.1`). The tag goes in via `env: TAG: ${{ github.event.release.tag_name || github.ref_name }}` and `run: python3 scripts/check_release_tag.py "$TAG"`. It creates nothing.
- `validate.yml`:
  - Triggers: push to main, pull_request to main, `schedule` cron `17 3 * * *`, `workflow_dispatch`. `permissions: {}` is kept.
  - All 5 jobs have `timeout-minutes: 15` and no `needs:`.
  - All 10 `uses:` lines are SHA-pinned with a version comment.
  - Lint runs `make lint` + `make typecheck` strings, test runs `uv run pytest -q tests` (single-entry matrix dropped).
  - test-min-ha runs the three `make test-min-ha` commands, with no `-o addopts` override.
  - The hacs job drops the unused `env: GITHUB_TOKEN`.
- `.github/dependabot.yml`: version 2, `github-actions`, `/`, weekly.

## Task Commits

1. **Task 1 RED:** `b932a39` test(08-07): add failing tests for the release tag check
2. **Task 1 GREEN:** `3e617c3` feat(08-07): release workflow fails when the tag differs from the manifest version
3. **Task 2:** `df061f4` ci(08-07): SHA-pinned, time-boxed CI on main, PRs, nightly and manual runs

## TDD Gate Compliance (Task 1, tdd="true")

- **RED:** `uv run pytest tests/test_release_tag_check.py -q --no-cov -p no:cacheprovider --junitxml=.pytest_cache/gsd-red/08-07-t1.xml` -> exit 1, 5 failed / 3 passed. The record is `.pytest_cache/gsd-red/08-07-t1.json` (git-ignored). `gsd-tools check tdd-red-evidence` -> `RED_EVIDENCE_OK` (`target_test_failed`, junit), target `tests.test_release_tag_check#test_main_fails_with_error_annotation_on_mismatch`.
  - **semanticAssessment:** the target executed and failed on the planned assertion: the skeleton `main(["v9.9.9"])` returned 0, not 1.
  - The 3 mismatch cases and the usage-error test also failed on their assertions.
  - The 3 match cases passed at RED, because the skeleton returns "no error". That is expected: they pin the behaviour that a matching tag passes.
  - A first run without the skeleton gave 8 fixture load errors (`FileNotFoundError`). That is INVALID_RED by contract, so it was not used.
- **GREEN:** the implementation makes all 8 pass.
- **REFACTOR:** none needed.

## Quality Gates (after each task; final numbers after Task 2)

| Gate | Result |
|---|---|
| `uv run pytest -q` (dev env, coverage gate) | 1152 passed, coverage 99.29 % >= 99, 0 "Lingering" |
| `uv run ruff check custom_components tests` | All checks passed |
| `uv run ruff format --check custom_components tests` | 50 files already formatted |
| `uv run mypy --strict custom_components/traefik_proxy` | no issues in 16 source files |
| HA 2026.11.0 venv (`ha2611-venv … -o addopts="-p no:respx" tests`) | 1152 passed |
| `make test-min-ha` (fresh `.venv-min-ha` from the hashed lock = the CI job's commands) | 1152 passed, coverage 99.29 % |
| ruff check/format on `scripts/check_release_tag.py` (outside the gate paths) | clean |

Task 1 gates gave the same numbers: 1152 passed in the dev env (99.29 %), 1152 passed on HA 2026.11.0, and ruff/mypy were clean.

## Acceptance Criteria

All PASS:
- Task 1:
  - The script exits 0 for `v0.3.0` and 1 for `v9.9.9`.
  - No `${{` appears in a `run:` line.
  - release.yml has 1 `uses:` line, and it is pinned.
  - The release.yml yaml gate passes (rc 0).
- Task 2:
  - 11 `uses:` lines, 0 unpinned.
  - The timeout/needs gate prints `[]`.
  - The `workflow_dispatch` and cron greps pass.
  - The `uv pip sync … --require-hashes` grep passes.
  - There is no `addopts=` in validate.yml.
  - The Dependabot grep passes.
  - All three YAML files parse.
  - The Makefile parity check prints `missing: []`.
- Extra check: injection probe `check_release_tag.py 'v0.3.0"; echo pwned'`. It exits 1 and prints the string as data.

## Worker Decisions

| Decision | Reason | Alternative not taken |
|---|---|---|
| (planner) Release check as `scripts/check_release_tag.py` + unit test, not inline Python in YAML | Testable locally; tag reaches it via env/argv only | Inline heredoc (research skeleton) |
| (planner) Keep `permissions: {}` in both workflows | Least privilege; validate.yml was green with it on main; checkout of a public repo needs no token scope | `contents: read` (research skeleton) |
| (planner) The release check is the tracer of the plan | It is the only new end-to-end path (tag -> workflow -> script -> manifest) that can be proven locally | Start with the validate.yml rewrite |
| RED commit includes an interface-only script skeleton | Without it every test errors in the module fixture (INVALID_RED); with it the target fails on its assertion | Commit the test alone and accept a load-error RED |
| `main()` returns 2 on a missing or extra argument | A workflow that loses the tag must not pass silently | Treat a missing tag as an empty string (would also fail, but with a misleading message) |
| One `run:` step per CI command | The plan's parity gate matches each `run:` string against the Makefile; a multi-line block would never be a substring of the tab-indented recipe | One multi-line `run: |` block per job |
| The test-min-ha job keeps the `uv venv --clear` flag from the Makefile | Parity requires the verbatim Makefile string; `--clear` is harmless on a fresh runner | Research skeleton without `--clear` |
| Pins re-resolved read-only (`git ls-remote`) before writing | Confirm that the 08-RESEARCH table still matches upstream. It does: all four SHAs are identical, and `v7.0.1`, `v10.3.3` and `22.5.0` are lightweight tags pointing at those commits | Trust the research table unchecked |
| No local actionlint run | Not installed. A Docker run was not in the plan's validation scope (YAML parse + gates) | Throwaway `rhysd/actionlint` container |

## Flagged assumption DIST-04 (never auto-resolved)

- Pinning `home-assistant/actions/hassfest` and `hacs/action` by SHA does **not** pin what runs. Both actions pull a floating image (`ghcr.io/home-assistant/hassfest:latest`, `docker://ghcr.io/hacs/action:main`). This is accepted as T-08-17: it is upstream design and matches what the catalog reviewers run.
- The hassfest pin carries `# master (2026-10-26)`, not `# vX.Y.Z`. No version tag exists upstream; the only tag, `1.0.0` from 2020, is obsolete. So D-13's comment rule cannot be met literally for this action.
- Dependabot may not propose bumps for a SHA whose comment is a branch name (research A7). The hassfest pin may need manual bumps. Its `action.yml` has been unchanged since 2024-08.

## Deviations from Plan

None in scope. The RED skeleton and the usage-error exit code 2 are recorded above as worker decisions. They are not plan deviations: the behaviour lines are all met, and exit code 2 is an addition.

**Total deviations:** 0.

## Docker

No Docker steps were run in this plan, so no cleanup check was needed (`docker ps -a` count unchanged at 7 containers versus session start).

## Known Stubs

None. The RED skeleton was replaced in the GREEN commit `3e617c3`.

## Threat Flags

None. The new surface (the release workflow and the tag string reaching the shell) is covered by T-08-13, T-08-14 and T-08-16 in the plan's threat model, and all three are mitigated as planned.

## User-visible changes (for CHANGELOG)

- End users: none.
- Developer-facing:
  - CI also runs nightly (03:17 UTC) and on manual dispatch. `push` runs only on main; PRs to main still run.
  - All GitHub Actions are pinned to commit SHAs, and Dependabot proposes weekly updates.
  - Every CI job has a 15-minute timeout.
  - A new "Release check" workflow fails a published release or `v*` tag whose version differs from `manifest.json`.
  - The minimum-HA CI job installs the committed hashed lock, exactly as `make test-min-ha` does.

## Next Phase Readiness

- 08-08 can bump the manifest to 1.0.0. `tests/test_release_tag_check.py` reads the current manifest, so it keeps passing. After the bump, the tag `v1.0.0` passes the check.
- Post-push (manager, M41): the first PR run must confirm all five validate.yml jobs on GitHub, especially `test-min-ha` with `--require-hashes` on the runner and `hacs` with the input-default token under `permissions: {}`. The release workflow can only be exercised when the user tags (M8).

## Self-Check: PASSED

- FOUND: scripts/check_release_tag.py, tests/test_release_tag_check.py, .github/workflows/release.yml, .github/dependabot.yml, .github/workflows/validate.yml
- FOUND commits on HEAD: b932a39, 3e617c3, df061f4
- All acceptance criteria and plan-level verification re-run green (see above)
