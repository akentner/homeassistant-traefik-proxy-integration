---
phase: 261118-nnf-prepare-release-candidate-1-0-0-rc1-vers
plan: 01
subsystem: release
tags: [release, versioning, changelog, hacs, pre-release]
status: complete
requires: []
provides:
  - "manifest.json version 1.0.0-rc1 matching tag v1.0.0-rc1"
  - "CHANGELOG [1.0.0-rc1] entry and draft GitHub pre-release body"
affects: [release.yml tag check, HACS update offers]
tech-stack:
  added: []
  patterns: ["SemVer pre-release in manifest, PEP 440 canonical form in the virtual pyproject"]
key-files:
  created:
    - .planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0-rc1.md
  modified:
    - custom_components/traefik_proxy/manifest.json
    - pyproject.toml
    - uv.lock
    - CHANGELOG.md
decisions:
  - "P1 pyproject.toml uses canonical PEP 440 1.0.0rc1 (uv.lock stores the normalised form either way)"
  - "P2 manifest.json uses exactly 1.0.0-rc1 (tag check compares strings; AwesomeVersion treats 1.0.0rc1 != 1.0.0-rc1)"
  - "P3 target-state 1.0.0 mentions (CLAUDE.md/STACK.md rows, comments, examples, [1.0.0] heading) stay unchanged"
  - "P4 .github/requirements-min-ha.txt not refreshed (it does not embed the project version)"
metrics:
  duration: "~4 min"
  completed: 2026-11-18
actuals:
  tokens: 2400
  tasks: 3
  commits: 2
commits: 2
plan_head_before: e6528cac3d43b4f7db151805db192dba19428977
plan_head_after: 9b427026c5fda4708b2793ecb3b3ad30cded97db
---

# Quick Task 261118-nnf Plan 01: Prepare release candidate 1.0.0-rc1 Summary

Version bumped to `1.0.0-rc1` (manifest, SemVer) / `1.0.0rc1` (pyproject + uv.lock, PEP 440), dated CHANGELOG
`[1.0.0-rc1]` entry with compare link, and a draft GitHub pre-release body with backup, HACS pre-release install and
feedback guidance in front of the unchanged 1.0.0 notes. No product or test code changed; no push, tag or release.

## Commits

| Task | Hash | Subject | Paths |
|------|------|---------|-------|
| 1 | `3e1b830` | `chore(release): bump version to 1.0.0-rc1` | `custom_components/traefik_proxy/manifest.json`, `pyproject.toml`, `uv.lock` |
| 2 | `9b42702` | `docs(release): add 1.0.0-rc1 changelog entry and release notes` | `CHANGELOG.md`, `.planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0-rc1.md` |
| 3 | — | (gates + this SUMMARY; not committed by the executor) | — |

Both commits were staged and committed with explicit paths. No whitespace fix commit was needed. Base: plan commit
`e6528ca` on top of `8a447c2`.

## Version forms

- `manifest.json`: `"version": "1.0.0-rc1"` (SemVer pre-release; equals tag `v1.0.0-rc1` after the `v` is stripped).
- `pyproject.toml`: `version = "1.0.0rc1"` (canonical PEP 440). Reason: the project is virtual (never built or
  published), nothing compares it with the tag or the manifest, and uv writes the normalised `1.0.0rc1` into uv.lock
  either way, so the canonical form keeps pyproject.toml and uv.lock literally equal.
- `uv.lock`: `uv lock` printed `Updated homeassistant-traefik-proxy-integration v1.0.0 -> v1.0.0rc1` and nothing else;
  `git diff --numstat 8a447c2 -- uv.lock` = `1 1`; `uv lock --locked` passes.

## Gate results (final tree, HEAD 9b42702)

| Gate | Result |
|------|--------|
| `uv run pytest -q tests` (coverage gate 99 %) | `1192 passed, 5 warnings in 32.47s`; `Required test coverage of 99.0% reached. Total coverage: 99.31%` |
| `uv run ruff check custom_components tests` | `All checks passed!` |
| `uv run ruff format --check custom_components tests` | `51 files already formatted` |
| `uv run mypy --strict custom_components/traefik_proxy` | `Success: no issues found in 16 source files` |
| `make pre-commit` (`uvx pre-commit run --all-files`) | all 13 hooks `Passed` (no file rewritten) |
| `make test-min-ha` (HA 2026.11.0, hashed lock) | `1192 passed, 5 warnings in 32.09s`; `Total coverage: 99.31%`; venv reports `min-ha HA 2026.11.0` |
| `make hassfest-sanity` | `hassfest-style checks passed` |
| `make hassfest` (digest-pinned image, `--rm`) | `Integrations: 1` / `Invalid integrations: 0`; no leftover container or volume (run after Task 1 and again on the final tree) |
| `python3 scripts/check_release_tag.py v1.0.0-rc1` | `tag v1.0.0-rc1 matches manifest.json version 1.0.0-rc1`, exit 0 |
| `python3 scripts/check_release_tag.py v1.0.0` (negative) | `::error::tag v1.0.0 (version 1.0.0) != manifest.json version 1.0.0-rc1`, exit 1 |
| AwesomeVersion assertion | `awesomeversion ok 1.0.0-rc1 SEMVER` (SEMVER, `0.3.0 < 1.0.0-rc1 < 1.0.0`, `v1.0.0-rc1 == 1.0.0-rc1`) |
| `pytest --no-cov tests/test_release_tag_check.py` | `8 passed` |
| `pytest --no-cov tests/test_baseline_guards.py` | `11 passed` |
| `git grep -F '"1.0.0"'` (excl. `.planning`, `tests/fixtures`) | no match |
| Task 2 privacy gates | no private host names (list from `~/CLAUDE.md`), no private IPv4; URL hosts only `github.com` |

Repository checks: subjects present; diff since 8a447c2 (excluding the pre-dispatch plan docs under
`.planning/quick/261118-nnf-*`) is exactly the 5 planned paths; `.planning/config.json` (` M`) and
`.planning/state.json` (`??`) untouched; no local tag `v1.0.0-rc1`; `@{u}` still `8a447c2`;
`scripts/check_release_tag.py`, `.github/workflows/release.yml` and `.github/requirements-min-ha.txt` unchanged;
no file deletions in either commit.

## Worker decisions

- **P1** pyproject.toml uses `1.0.0rc1` (canonical PEP 440), not `1.0.0-rc1`. Reason: virtual project, no comparison
  with tag or manifest, uv.lock stores the normalised form anyway. Alternative: `1.0.0-rc1` (accepted and normalised by
  uv; cosmetic difference only).
- **P2** manifest.json uses exactly `1.0.0-rc1`. Reason: the tag is `v1.0.0-rc1`, `check_release_tag.py` compares
  strings exactly, and AwesomeVersion treats `1.0.0rc1` as different from `1.0.0-rc1`. Alternative: none viable.
- **P3** Mentions of the 1.0.0 target state stay unchanged: `| version | 1.0.0 |` rows in CLAUDE.md and
  `.planning/research/STACK.md`, the pyproject coverage comment, the `check_release_tag.py` docstring example, the
  tag URL example in `tests/test_hacs_action_local.py`, the CHANGELOG `[1.0.0]` heading and link ref, and the
  AwesomeVersion examples in CLAUDE.md. Alternative: set the two table rows to `1.0.0-rc1` now and back at 1.0.0.
- **P4** `.github/requirements-min-ha.txt` not refreshed: it does not embed the project version, and `make test-min-ha`
  passed unchanged.
- **New (W1)** The HACS install section was written from the UI labels given in the plan (sourced by the planner from
  hacs.xyz on 2026-11-18); the executor did not re-fetch hacs.xyz and invented no further labels. Alternative: re-verify
  the labels online before publishing.

## Deviations from Plan

- The Task 3 `<verify>` check `git diff --name-only 8a447c2 HEAD` would also list the pre-dispatch plan commit
  (`e6528ca`, `.planning/quick/261118-nnf-*/261118-nnf-PLAN.md`). As instructed by the orchestrator, the name check
  was run with the pathspec `':!.planning/quick/261118-nnf-*'`; with that exclusion it matched the 5 planned paths
  exactly. Likewise `git rev-list --count 8a447c2..HEAD` is 3 (plan commit + 2 task commits); the plan ledger
  (`e6528ca..HEAD`) measures 2.
- Otherwise none — plan executed as written.

## Known Stubs

None.

## Next steps for the user (not done by the agent)

1. Push the branch `feat/marketplace-polish`.
2. Create tag `v1.0.0-rc1` on the bump commit `3e1b830` or a later commit (for example `9b42702`).
3. Create the GitHub release as a pre-release ("Set as a pre-release" ticked, "Set as the latest release" not ticked)
   with the body below the cut line of `.planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0-rc1.md`.
4. Check the "Release check" workflow run.
5. For the final 1.0.0: set manifest.json and pyproject.toml back to `1.0.0`, run `uv lock`, and date the `[1.0.0]`
   heading in CHANGELOG.md.

## Self-Check: PASSED

- FOUND: custom_components/traefik_proxy/manifest.json, pyproject.toml, uv.lock, CHANGELOG.md,
  .planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0-rc1.md
- FOUND: 3e1b830, 9b42702 (ancestors of HEAD)
