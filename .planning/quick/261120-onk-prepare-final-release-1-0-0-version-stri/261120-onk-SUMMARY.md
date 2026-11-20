---
phase: 261120-onk-prepare-final-release-1-0-0-version-stri
plan: 01
subsystem: release
tags: [release, version, changelog, hacs]
status: complete
requires: [v1.0.0-rc1 tested by the user]
provides: [manifest/pyproject/uv.lock version 1.0.0, dated CHANGELOG 1.0.0 entry, final 1.0.0 release notes, hacs/default latest-release precondition]
affects: [release.yml tag check, HACS update offer]
tech-stack:
  added: []
  patterns: []
key-files:
  created: []
  modified:
    - custom_components/traefik_proxy/manifest.json
    - pyproject.toml
    - uv.lock
    - CHANGELOG.md
    - .planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0.md
    - .planning/phases/08-marketplace-release-readiness/08-HACS-DEFAULT-PR.md
decisions:
  - "P1: pyproject.toml and uv.lock back to plain 1.0.0; all three version files equal 8a447c2"
  - "P2: CHANGELOG equivalence line as prose under the dated heading"
  - "P3: tested-rc1 paragraph in the release-notes body; checklist rewritten for the dated state"
  - "P5: existing 1.0.0 references in CLAUDE.md, STACK.md, pyproject comment, scripts/tests unchanged"
metrics:
  duration: ~15 min
  completed: 2026-11-20
actuals:
  tokens: 1437
  tasks: 3
  commits: 2
plan_head_before: 9959262a6d8402fa2167d4de6d6ef75130ed3f7e
plan_head_after: 0ae55b390c49136d762661c20de4736c69cc549d
---

# Quick Task 261120-onk: Prepare final release 1.0.0 Summary

Version 1.0.0 set in manifest, pyproject and uv.lock (byte-identical to pre-rc1 commit 8a447c2; the only
custom_components change since v1.0.0-rc1 is the manifest version line), CHANGELOG dated 2026-11-20 with an rc1
equivalence line, and the 1.0.0 release notes and hacs/default draft finalized for a full "latest" release.

## Commits

| Task | Hash | Subject | Paths |
|------|------|---------|-------|
| 1 | a88d1c7 | chore(release): bump version to 1.0.0 | custom_components/traefik_proxy/manifest.json, pyproject.toml, uv.lock |
| 2 | 0ae55b3 | docs(release): date 1.0.0 changelog entry and finalize release notes | CHANGELOG.md, 08-RELEASE-NOTES-v1.0.0.md, 08-HACS-DEFAULT-PR.md |
| 3 | — | (gates + this SUMMARY; not committed by the executor) | — |

`uv lock` output: `Updated homeassistant-traefik-proxy-integration v1.0.0rc1 -> v1.0.0` (no other package line).

## Gate results (final tree, HEAD 0ae55b3)

| Gate | Result |
|------|--------|
| `uv run pytest -q tests` | `1192 passed, 5 warnings in 33.14s`; `Required test coverage of 99.0% reached. Total coverage: 99.31%` |
| `uv run ruff check custom_components tests` | `All checks passed!` |
| `uv run ruff format --check custom_components tests` | `51 files already formatted` |
| `uv run mypy --strict custom_components/traefik_proxy` | `Success: no issues found in 16 source files` |
| `make pre-commit` | all 13 hooks `Passed`, no file rewritten (working tree unchanged afterwards) |
| `make test-min-ha` (homeassistant==2026.11.0, pytest-homeassistant==2026.11.0, hashed lock) | `1192 passed, 5 warnings in 31.59s` |
| `make hassfest-sanity` | `hassfest-style checks passed` |
| `make hassfest` (digest-pinned image, `--rm`, ro mount) | `Integrations: 1` / `Invalid integrations: 0`; run twice (after Task 1 and on the final tree), `docker ps -aq` and `docker volume ls -q` unchanged both times |
| `uv lock --locked` | exit 0 (`Resolved 146 packages`) |
| `python3 scripts/check_release_tag.py v1.0.0` | exit 0, `tag v1.0.0 matches manifest.json version 1.0.0` |
| `python3 scripts/check_release_tag.py v1.0.0-rc1` | exit 1, `::error::tag v1.0.0-rc1 (version 1.0.0-rc1) != manifest.json version 1.0.0` |
| AwesomeVersion assertion | `awesomeversion ok 1.0.0 SEMVER` (0.3.0 < 1.0.0-rc1 < 1.0.0, `v1.0.0 == 1.0.0`) |
| `pytest --no-cov tests/test_release_tag_check.py` | `8 passed` |
| `pytest --no-cov tests/test_baseline_guards.py` | `11 passed` |
| Task 1 and Task 2 `<verify>` chains | exit 0 (incl. no rc1 refs outside .planning/CHANGELOG, CHANGELOG numstat 3/1, rc1 section unchanged, Required actions..Full change list unchanged, HACS draft before/after tag bullet byte-identical, URL hosts only github.com, privacy grep clean, rc1 notes unchanged) |
| Task 3 repo checks | exit 0: custom_components numstat `1 1 manifest.json`; equals 8a447c2; changed paths outside quick docs = exactly the 6 planned; per-commit path sets exact; config.json/state.json untouched (` M` / `??`); no tag v1.0.0; v1.0.0-rc1 and `@{u}` = 22902d9; branch feat/marketplace-polish |

## rc1 equivalence proof

`git diff v1.0.0-rc1..HEAD -- custom_components`:

```
diff --git a/custom_components/traefik_proxy/manifest.json b/custom_components/traefik_proxy/manifest.json
index 9a7ae05..d678abf 100644
--- a/custom_components/traefik_proxy/manifest.json
+++ b/custom_components/traefik_proxy/manifest.json
@@ -10,5 +10,5 @@
   "iot_class": "local_polling",
   "issue_tracker": "https://github.com/akentner/homeassistant-traefik-proxy-integration/issues",
   "requirements": [],
-  "version": "1.0.0-rc1"
+  "version": "1.0.0"
 }
```

`git diff v1.0.0-rc1..HEAD --stat` (before the orchestrator's docs commit):

```
 .../08-HACS-DEFAULT-PR.md                          |   7 +-
 .../08-RELEASE-NOTES-v1.0.0.md                     |  21 +-
 .../261120-onk-PLAN.md                             | 371 +++++++++++++++++++++
 CHANGELOG.md                                       |   4 +-
 custom_components/traefik_proxy/manifest.json      |   2 +-
 pyproject.toml                                     |   2 +-
 uv.lock                                            |   2 +-
 7 files changed, 398 insertions(+), 11 deletions(-)
```

`git diff --quiet 8a447c2 HEAD -- custom_components pyproject.toml uv.lock` -> exit 0 (byte-identical to pre-rc1).

## Worker decisions

- **P1** pyproject.toml and uv.lock back to plain `1.0.0`. Reason: no PEP 440 / SemVer split for a final version;
  all three version files now equal 8a447c2. Alternative: none.
- **P2** CHANGELOG equivalence line `The integration code is identical to 1.0.0-rc1 apart from the version number.`
  as prose directly under `## [1.0.0] - 2026-11-20`. Reason: Keep a Changelog compatible, says "code" because docs
  did change. Alternative: a `### Changed` bullet (would read as a code change).
- **P3** One paragraph after the release-notes intro (rc1 tested, same code, rc1 users just update, required actions
  apply from 0.3.x); publish checklist rewritten (push first / title+tag / not pre-release, set latest / date and
  anchor together). Required actions through Full change list kept word for word except the anchor. Alternative:
  mention rc1 only in the comment (testers would not see it).
- **P5** The `| version | 1.0.0 |` rows in CLAUDE.md and .planning/research/STACK.md, the pyproject coverage comment
  and the example strings in scripts/tests stay unchanged; they already say 1.0.0.
- No new worker decisions.

## Deferred

- **P4 (proposed to the user, not done):** two stale, version-independent facts in
  `.planning/phases/08-marketplace-release-readiness/08-HACS-DEFAULT-PR.md` stay byte-identical:
  1. The Validate bullet still says REL-07 "was deferred to CI; it is not proven locally" although the decision log
     records that REL-07 passed in PR #2 CI.
  2. The logo open item (A3/A8) is still listed as open although the user decided on 2026-11-16 to keep the logo.
  The user scoped edits to this file to version/release-dependent facts, so both wait for the user's decision.

## Deviations from Plan

None - plan executed exactly as written. (Gate commands were run individually instead of as one `&&` chain so each
result line could be recorded; every command in the Task 1/2/3 `<verify>` blocks was run and exited 0. The Task 3
SUMMARY privacy grep runs after this file is written.)

## Known Stubs

None.

## Next steps for the user (not done by the agent)

1. Push the branch `feat/marketplace-polish`.
2. Mark PR #2 ready, merge to main, and check the Validate run on main.
3. Create tag `v1.0.0` on the version-bump commit (a88d1c7) or a later commit, never on 22902d9.
4. Publish the GitHub release "Traefik Proxy 1.0.0" with the body below the cut line of
   `08-RELEASE-NOTES-v1.0.0.md`, not as a pre-release and set as latest. If the date is not 2026-11-20, change the
   CHANGELOG date and the anchor together first.
5. Check the "Release check" run.
6. Submit to hacs/default following `08-HACS-DEFAULT-PR.md`.

No push, tag, merge, PR or release was done by the agent.

## Self-Check: PASSED

- Files: all 6 modified paths present; SUMMARY.md exists.
- Commits: a88d1c7 and 0ae55b3 are ancestors of HEAD.
- Privacy: no private host name in SUMMARY.md (list read at run time, 3 names).
