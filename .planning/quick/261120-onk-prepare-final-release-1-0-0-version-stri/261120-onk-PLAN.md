---
phase: 261120-onk-prepare-final-release-1-0-0-version-stri
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - custom_components/traefik_proxy/manifest.json
  - pyproject.toml
  - uv.lock
  - CHANGELOG.md
  - .planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0.md
  - .planning/phases/08-marketplace-release-readiness/08-HACS-DEFAULT-PR.md
autonomous: true
requirements: [M8-FINAL-VERSION-BUMP, M8-FINAL-RELEASE-DOCS, M8-FINAL-GATES]

estimate:
  tokens: 50000
  raw_tokens: 50000
  tasks: 3
  confidence: low

must_haves:
  truths:
    - "manifest.json version is exactly 1.0.0, pyproject.toml [project] version and the uv.lock project entry are exactly 1.0.0. `python3 scripts/check_release_tag.py v1.0.0` exits 0 and `v1.0.0-rc1` now exits 1. Tags keep the v prefix (decision log I4/I5); the user cuts the tag and the release (M8, U1)"
    - "1.0.0 is the same code as the tested rc1: `git diff v1.0.0-rc1..HEAD -- custom_components` is exactly the one manifest version line (1.0.0-rc1 -> 1.0.0), and custom_components, pyproject.toml and uv.lock are byte-identical to the pre-rc1 commit 8a447c2. No test, script, workflow or Makefile changes"
    - "AwesomeVersion orders 0.3.0 < 1.0.0-rc1 < 1.0.0 and treats tag v1.0.0 as equal to the manifest version, so HACS offers 1.0.0 as an update to rc1 testers and to 0.3.x users"
    - "CHANGELOG.md heading reads `## [1.0.0] - 2026-11-20` with one prose line saying the integration code is identical to 1.0.0-rc1 apart from the version number. The [1.0.0-rc1] section and every link ref are unchanged; the file no longer contains the undated heading"
    - "08-RELEASE-NOTES-v1.0.0.md links to blob/v1.0.0/CHANGELOG.md#100---2026-11-20, says that rc1 was tested and that 1.0.0 has the same integration code, and its publish checklist says: not a pre-release, set as the latest release, the tagged commit must carry manifest version 1.0.0. Required actions, Highlights and the trademark line stay word for word. The rc1 notes file is unchanged"
    - "08-HACS-DEFAULT-PR.md changes only in its version/release-dependent tag precondition: v1.0.0 must be a full release marked latest, and the v1.0.0-rc1 pre-release does not count. Everything before and after that bullet, including the Validate/REL-07 bullet and the logo open item, is byte-identical to v1.0.0-rc1 (P4 deferred)"
    - "No private host name (list read from $HOME/CLAUDE.md at run time) and no private IPv4 in any added line or in the release notes; release-notes URL hosts are only github.com"
    - "These pass on the final tree: full pytest with the 99 % coverage gate, ruff check, ruff format --check, mypy --strict, `make pre-commit`, `make test-min-ha`, `make hassfest-sanity` and `make hassfest` (no leftover container or volume). Exactly two task commits with explicit path lists. .planning/config.json (modified) and .planning/state.json (untracked) stay untouched. No push, no tag, no merge, no release"
  artifacts:
    - path: "custom_components/traefik_proxy/manifest.json"
      provides: "Integration version read by HA, hassfest, HACS and scripts/check_release_tag.py"
      contains: "\"version\": \"1.0.0\""
    - path: "pyproject.toml"
      provides: "Dev project version (virtual project, never built or published)"
      contains: "version = \"1.0.0\""
    - path: "uv.lock"
      provides: "Lock with the root project version back at 1.0.0, nothing else changed"
      contains: "version = \"1.0.0\""
    - path: "CHANGELOG.md"
      provides: "Dated 1.0.0 entry plus the rc1 equivalence line"
      contains: "## [1.0.0] - 2026-11-20"
    - path: ".planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0.md"
      provides: "Final draft body for the GitHub release v1.0.0 (the user publishes it)"
      contains: "blob/v1.0.0/CHANGELOG.md#100---2026-11-20"
    - path: ".planning/phases/08-marketplace-release-readiness/08-HACS-DEFAULT-PR.md"
      provides: "hacs/default submission draft with current release preconditions"
      contains: "marked as the latest release"
  key_links:
    - from: "git tag v1.0.0 (created by the user)"
      to: "custom_components/traefik_proxy/manifest.json version"
      via: ".github/workflows/release.yml -> scripts/check_release_tag.py strips one leading v and compares the strings exactly"
      pattern: "tag_version == version"
    - from: "08-RELEASE-NOTES-v1.0.0.md change-list link"
      to: "CHANGELOG.md heading `## [1.0.0] - 2026-11-20` at tag v1.0.0"
      via: "GitHub heading slug: lowercase, brackets and dots dropped, spaces to hyphens"
      pattern: "blob/v1\\.0\\.0/CHANGELOG\\.md#100---2026-11-20"
    - from: "manifest.json version 1.0.0"
      to: "HACS update offer for installs on 1.0.0-rc1 and 0.3.x"
      via: "AwesomeVersion ordering 0.3.0 < 1.0.0-rc1 < 1.0.0"
      pattern: "1\\.0\\.0"
---

<objective>
Prepare the final release 1.0.0 on branch `feat/marketplace-polish`. The user tested v1.0.0-rc1 (lightweight tag on
22902d9) and approved it. 1.0.0 must be the same code as rc1: only version strings and release docs change. Decision
log M8: the user handles merge, tag and release; agents prepare the version bump and the release docs.

Purpose: the user can tag `v1.0.0`, publish the GitHub release as latest and later submit to hacs/default without any
further file change. The release check passes, hassfest and HACS accept the version, and HACS offers 1.0.0 as an
update to rc1 testers.

Output: two commits.
1. Version bump: manifest.json, pyproject.toml, uv.lock.
2. Release docs: CHANGELOG.md, 08-RELEASE-NOTES-v1.0.0.md, 08-HACS-DEFAULT-PR.md.
After that come a full gate run and the quick-task SUMMARY.md.

Planner findings the executor relies on (verified on HEAD 22902d9, 2026-11-20):
- HEAD, tag `v1.0.0-rc1` and `@{u}` (origin/feat/marketplace-polish) all point to
  22902d90db2e77f4b5e136a1cdc92ca7bfeefa86. Working tree: only ` M .planning/config.json` and `?? .planning/state.json`.
- The rc1 bump (3e1b830) changed exactly one line in each of `custom_components/traefik_proxy/manifest.json:13`
  (`"version": "1.0.0-rc1"`, last key, no trailing comma), `pyproject.toml:3` (`version = "1.0.0rc1"`) and
  `uv.lock:1329` (root project entry under `name = "homeassistant-traefik-proxy-integration"`). Between 8a447c2 and
  22902d9 nothing else touched custom_components, pyproject.toml or uv.lock, so after the revert those three paths
  must be byte-identical to 8a447c2.
- `git grep -E '1\.0\.0-?rc1'` outside `.planning` hits only those three lines plus CHANGELOG.md:224 (rc1 heading) and
  CHANGELOG.md:313 (rc1 link ref). The CHANGELOG hits stay.
- CHANGELOG.md:9 is the undated 1.0.0 heading, line 10 is blank, line 11 is `### Breaking changes and required
  actions`. Link refs are lines 312-322; `[1.0.0]` compares v0.3.0...v1.0.0 and stays as is.
- GitHub heading slug for `## [1.0.0] - 2026-11-20` is `100---2026-11-20` (same rule that produced the old anchor of
  the undated heading).
- tests/test_baseline_guards.py scans README.md and CHANGELOG.md (no developers.home-assistant.io link, no `2026.3`).
  No test reads the CHANGELOG heading or the pyproject version; tests/test_release_tag_check.py reads the manifest
  version dynamically.
- `.pre-commit-config.yaml` excludes `^(\.planning/|tests/fixtures/)`, so hooks never touch the planning docs or
  .planning/config.json.
- No `UV_*` variable is set in the environment. uv 0.13.4. Docker 29.9.3 is running; the rc1 task ran `make hassfest`
  offline from the cached digest-pinned image.
- 08-RELEASE-NOTES-v1.0.0-rc1.md is factually correct for rc1 (its change-list anchor targets the heading as it was at
  tag v1.0.0-rc1). It stays unchanged.
</objective>

<execution_context>
@~/.claude/gsd-core/workflows/execute-plan.md
@~/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@/home/akentner/.cache/traefik-proxy-integration/brief-exec-phase.md
@/home/akentner/.cache/traefik-proxy-integration/decisions.md
@.planning/quick/261118-nnf-prepare-release-candidate-1-0-0-rc1-vers/261118-nnf-SUMMARY.md
@custom_components/traefik_proxy/manifest.json
@scripts/check_release_tag.py
@CHANGELOG.md
@.planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0.md
@.planning/phases/08-marketplace-release-readiness/08-HACS-DEFAULT-PR.md
@Makefile

Rules from the brief and the orchestrator (binding):
- Commit on this branch only. Do NOT push, tag, merge, or create a GitHub release or PR (decision log U1, M8).
- No product or test code changes. The only change under custom_components is the manifest version value.
- Stage and commit with explicit paths only: `git add -- <paths>`, then `git commit -m ... -- <paths>`. Never use
  `git add -A`, `git add .` or `git commit -a`.
- Leave `.planning/config.json` (modified) and `.planning/state.json` (untracked) untouched and out of every commit.
- Do not edit `.planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0-rc1.md` (historical rc1 draft).
- No real Home Assistant instance. Docker only for the throwaway hassfest container (`--rm`).
- Never write a private host name. The privacy gates read the host list from `$HOME/CLAUDE.md` at run time; do not
  copy that list into any file.
- If a gate cannot run (Docker daemon down, image missing, network failure for the min-HA install, missing pre-commit
  cache), stop with a clear blocker in SUMMARY.md. Never fake a result.

Planner decisions (put them in SUMMARY.md under "Worker decisions"):
- P1 pyproject.toml and uv.lock go back to plain `1.0.0` (no PEP 440 / SemVer split is needed for a final version).
  Result: all three version files equal 8a447c2. Alternative: none.
- P2 The CHANGELOG equivalence line is the exact sentence `The integration code is identical to 1.0.0-rc1 apart from
  the version number.` placed as prose directly under the dated heading, before the first `###` subsection (prose
  style as in the [1.0.0-rc1] and [0.1.2] entries). Reason: one line, Keep a Changelog compatible, says "code"
  because CHANGELOG and notes did change. Alternative: a `### Changed` bullet (would read as a code change).
- P3 The release-notes body gets one short paragraph after the intro (rc1 tested, same integration code, rc1 users
  just update, required actions apply to updates from 0.3.x). The publish checklist in the leading comment is
  rewritten for the dated state. Everything from `## Required actions` through `## Full change list` stays word for
  word; only the change-list URL changes. Alternative: put the rc1 mention only into the comment (testers would not
  see it).
- P4 deferred — proposed to the user, not done. The planner proposed also correcting two stale facts in
  08-HACS-DEFAULT-PR.md that do not depend on the version/release: the REL-07 status in the Validate bullet (passed
  in PR #2 CI per the decision log) and the logo open item A3/A8 (decided by the user on 2026-11-16: keep). The
  orchestrator dropped it because the user scoped edits to that file to version/release-dependent facts only. Both
  passages stay byte-identical in this task; list them in SUMMARY.md under "Deferred" so the user can decide.
- P5 The `| version | 1.0.0 |` rows in CLAUDE.md and .planning/research/STACK.md, the pyproject coverage comment and
  the example strings in scripts/tests stay unchanged; they already state 1.0.0.
</context>

<tasks>

<task type="tracer">
  <name>Task 1: Version 1.0.0 end to end (manifest -> pyproject -> uv.lock -> release check -> AwesomeVersion -> hassfest)</name>
  <files>custom_components/traefik_proxy/manifest.json, pyproject.toml, uv.lock</files>
  <action>
1. In `custom_components/traefik_proxy/manifest.json`, set the value of the `version` key to `1.0.0`. Change only that
   value; keep the key order and formatting (hassfest requires domain, name, then alphabetical).
2. In `pyproject.toml`, set the `[project]` `version` line (line 3) to `1.0.0` (planner decision P1). Change nothing
   else in the file.
3. Refresh the lock with `uv lock` from the repo root. Do not run any `uv run` before this step, because `uv run`
   would re-lock implicitly. Expected uv output: `Updated homeassistant-traefik-proxy-integration v1.0.0rc1 -> v1.0.0`
   and no other package line. If uv reports any other package change, stop: the lock must change in exactly one line.
4. Confirm that no tracked file outside `.planning` and CHANGELOG.md still names the rc1 version (the first check in
   `<verify>`), and that the three version files are byte-identical to the pre-rc1 commit 8a447c2.
5. Prove the end-to-end path by running every command in `<verify>`:
   - the release check for `v1.0.0` (exit 0) and the negative check that `v1.0.0-rc1` now exits 1;
   - the AwesomeVersion assertion on the real manifest value (order 0.3.0 < 1.0.0-rc1 < 1.0.0, tag equality);
   - the release-check unit tests with `--no-cov` (a partial run without it trips the 99 % fail_under gate);
   - `make hassfest`, wrapped so that it fails on leftover containers or volumes.
   If Docker is not available or the pinned image is missing and cannot be pulled, stop with a blocker. Do not skip
   hassfest and do not report a result you did not see.
6. Commit with explicit paths only:
   `git add -- custom_components/traefik_proxy/manifest.json pyproject.toml uv.lock`, then
   `git commit -m "<msg>" -- custom_components/traefik_proxy/manifest.json pyproject.toml uv.lock`.
   Subject: `chore(release): bump version to 1.0.0`. Body, short English bullets: manifest 1.0.0 (tag v1.0.0);
   pyproject 1.0.0; uv.lock refreshed (root project version only); code identical to v1.0.0-rc1, which the user tested.
  </action>
  <verify>
    <automated>git grep -n -E '1\.0\.0-?rc1' -- ':!.planning' ':!CHANGELOG.md'; test $? -eq 1 && test "$(grep -c -x '  "version": "1.0.0"' custom_components/traefik_proxy/manifest.json)" = 1 && test "$(grep -c -x 'version = "1.0.0"' pyproject.toml)" = 1 && test "$(grep -A1 -x 'name = "homeassistant-traefik-proxy-integration"' uv.lock | grep -c -x 'version = "1.0.0"')" = 1 && git diff --quiet 8a447c2 -- custom_components pyproject.toml uv.lock && test "$(git diff --numstat v1.0.0-rc1 -- custom_components)" = "$(printf '1\t1\tcustom_components/traefik_proxy/manifest.json')" && NSL="$(git diff --numstat v1.0.0-rc1 -- uv.lock)" && test "$(cut -f1,2 <<<"$NSL")" = "$(printf '1\t1')" && uv lock --locked && python3 scripts/check_release_tag.py v1.0.0 && { python3 scripts/check_release_tag.py v1.0.0-rc1; test $? -eq 1; } && uv run --with awesomeversion python3 -c 'import json; from awesomeversion import AwesomeVersion as V; m = json.load(open("custom_components/traefik_proxy/manifest.json"))["version"]; v = V(m); assert m == "1.0.0" and v.valid, m; assert V("0.3.0") < V("1.0.0-rc1") < v, "order"; assert V("v1.0.0") == v, "tag"; print("awesomeversion ok", m, v.strategy.name)' && uv run pytest -q --no-cov tests/test_release_tag_check.py && bash -c 'set -o pipefail; c0=$(docker ps -aq | sort); v0=$(docker volume ls -q | sort); make hassfest 2>&1 | tail -n 30 | tee /dev/stderr | grep -F "Invalid integrations: 0" >/dev/null; rc=$?; c1=$(docker ps -aq | sort); v1=$(docker volume ls -q | sort); if [ "$c0" != "$c1" ] || [ "$v0" != "$v1" ]; then echo "leftover docker container or volume" >&2; exit 3; fi; exit $rc'</automated>
  </verify>
  <done>manifest.json, pyproject.toml and the uv.lock project entry say 1.0.0; the three files equal 8a447c2 byte for
  byte; `git diff v1.0.0-rc1 -- custom_components` is the single manifest line. `check_release_tag.py v1.0.0` exits 0
  and `v1.0.0-rc1` exits 1. AwesomeVersion asserts 0.3.0 &lt; 1.0.0-rc1 &lt; 1.0.0 and tag equality.
  tests/test_release_tag_check.py passes. hassfest prints `Invalid integrations: 0` with no leftover container or
  volume. Commit `chore(release): bump version to 1.0.0` contains exactly the 3 paths.</done>
</task>

<task type="auto">
  <name>Task 2: Date the CHANGELOG, finalize the 1.0.0 release notes and the hacs/default draft</name>
  <files>CHANGELOG.md, .planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0.md, .planning/phases/08-marketplace-release-readiness/08-HACS-DEFAULT-PR.md</files>
  <action>
1. CHANGELOG.md (Keep a Changelog):
   - Replace the undated 1.0.0 heading on line 9 with `## [1.0.0] - 2026-11-20`.
   - Directly below it insert one blank line, then the exact line
     `The integration code is identical to 1.0.0-rc1 apart from the version number.` (planner decision P2), so that
     one blank line separates it from `### Breaking changes and required actions`.
   - Change nothing else: the [1.0.0-rc1] section (including its sentence about the changes listed under [1.0.0]
     above) and all link refs stay as they are. The diff against v1.0.0-rc1 is 3 added lines and 1 removed line.
2. `.planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0.md` (planner decision P3):
   a) Rewrite the numbered "Before publishing" list in the leading HTML comment. Keep its first two lines (draft for
      the GitHub release v1.0.0 created by the user; paste everything below the cut line), the closing "This file is a
      planning draft ..." line and the "----- cut -----" line. New items:
      1. Push first: the tagged commit must exist on GitHub, and its manifest.json version must be 1.0.0. The tag
         v1.0.0-rc1 carries 1.0.0-rc1 and fails the release check, so do not tag 22902d9 as v1.0.0.
      2. Release title "Traefik Proxy 1.0.0", tag `v1.0.0` (the release workflow compares the tag without `v` with
         manifest.json version 1.0.0).
      3. In the GitHub release form, do not tick "Set as a pre-release", and tick "Set as the latest release" (0.3.0
         stays the latest release until then; v1.0.0-rc1 remains a pre-release).
      4. CHANGELOG.md is dated `## [1.0.0] - 2026-11-20`, and the change-list link below uses its anchor
         `#100---2026-11-20`. If you publish on another day, change the CHANGELOG date and this anchor together.
   b) After the intro paragraph ("1.0.0 is a major rework ...") and before `## Required actions`, add one paragraph
      (wrap at about 80 columns like the rest of the file) with these sentences: "1.0.0 contains the same integration
      code as the release candidate 1.0.0-rc1, which was tested before this release; only the version number differs.
      If you already run 1.0.0-rc1, update through HACS; nothing else is needed. The required actions below apply
      when you update from 0.3.x."
   c) In `## Full change list`, change only the link target to
      `https://github.com/akentner/homeassistant-traefik-proxy-integration/blob/v1.0.0/CHANGELOG.md#100---2026-11-20`.
   d) Keep `## Required actions` (items 1-7), `## Highlights`, the rest of `## Full change list` and the Traefik
      trademark line word for word. After the edit the file must not mention the undated heading or its old anchor
      anywhere (comment included).
3. `.planning/phases/08-marketplace-release-readiness/08-HACS-DEFAULT-PR.md`, version/release-dependent facts only
   (P4 is deferred, see context):
   a) Preconditions, tag bullet (the one starting `- [ ] Tag `; keep that opening): it must say that tag `v1.0.0`
      exists and the GitHub release "Traefik Proxy 1.0.0" is published with the body from `08-RELEASE-NOTES-v1.0.0.md`,
      as a full release marked as the latest release (not a pre-release); that the pre-release `v1.0.0-rc1` does not
      count because its manifest version is 1.0.0-rc1; and, as before, that the `Release check` workflow passed.
   b) Change nothing else. Every line before the tag bullet (intro, merge bullet, the Validate bullet with its REL-07
      sentence) and every line from the bullet starting `- [ ] The repository is public` to the end of the file
      (Steps, PR title, PR body template with the `tid` comment, notes, and the logo open item) stay byte for byte.
4. Write no host names other than github.com in new text, no IP addresses, no tokens, and no personal data beyond
   the public repository URL already in these files.
5. Commit with explicit paths only:
   `git add -- CHANGELOG.md .planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0.md .planning/phases/08-marketplace-release-readiness/08-HACS-DEFAULT-PR.md`,
   then `git commit -m "<msg>" --` with the same three paths.
   Subject: `docs(release): date 1.0.0 changelog entry and finalize release notes`. Body: two or three short bullets.
  </action>
  <verify>
    <automated>R=.planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0.md; H=.planning/phases/08-marketplace-release-readiness/08-HACS-DEFAULT-PR.md; RC=.planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0-rc1.md; nrm() { tr -s '[:space:]' ' ' < "$1"; }; OLDC="$(git show v1.0.0-rc1:CHANGELOG.md)" && OLDR="$(git show "v1.0.0-rc1:$R")" && OLDH="$(git show "v1.0.0-rc1:$H")" && NSC="$(git diff --numstat v1.0.0-rc1 -- CHANGELOG.md)" && test "$(grep -c -x '## \[1\.0\.0\] - 2026-11-20' CHANGELOG.md)" = 1 && test "$(grep -c -i 'unreleased' CHANGELOG.md)" = 0 && test "$(grep -c -x -F 'The integration code is identical to 1.0.0-rc1 apart from the version number.' CHANGELOG.md)" = 1 && awk '/^## \[1\.0\.0\] - 2026-11-20$/{a=NR} /^The integration code is identical to 1\.0\.0-rc1 apart from the version number\.$/{b=NR} /^### Breaking changes and required actions$/{if(!c)c=NR} END{exit !(a && b-a==2 && c-a==4)}' CHANGELOG.md && test "$(cut -f1,2 <<<"$NSC")" = "$(printf '3\t1')" && diff <(sed -n '/^## \[1\.0\.0-rc1\]/,$p' <<<"$OLDC") <(sed -n '/^## \[1\.0\.0-rc1\]/,$p' CHANGELOG.md) && grep -q -F 'blob/v1.0.0/CHANGELOG.md#100---2026-11-20' "$R" && test "$(grep -c -i 'unreleased' "$R")" = 0 && nrm "$R" | grep -q -F 'same integration code as the release candidate 1.0.0-rc1, which was tested' && nrm "$R" | grep -q -F 'Set as the latest release' && nrm "$R" | grep -q -F '1.0.0 is a major rework of the integration' && grep -q -F 'Traefik is a trademark of Traefik Labs.' "$R" && diff <(sed -n '/^## Required actions$/,/^## Full change list$/p' <<<"$OLDR") <(sed -n '/^## Required actions$/,/^## Full change list$/p' "$R") && test -z "$(grep -o -E 'https?://[^/[:space:])>`]+' "$R" | sort -u | grep -v -x -F 'https://github.com')" && git diff --quiet v1.0.0-rc1 -- "$RC" && nrm "$H" | grep -q -F 'marked as the latest release' && nrm "$H" | grep -q -F 'v1.0.0-rc1' && grep -q -E '^- \[ \] Tag ' "$H" && grep -q -E '^- \[ \] The repository is public' "$H" && diff <(sed -n '1,/^- \[ \] Tag /p' <<<"$OLDH" | sed '$d') <(sed -n '1,/^- \[ \] Tag /p' "$H" | sed '$d') && diff <(sed -n '/^- \[ \] The repository is public/,$p' <<<"$OLDH") <(sed -n '/^- \[ \] The repository is public/,$p' "$H") && diff <(grep -o -E 'https?://[^/[:space:])>`]+' <<<"$OLDH" | sort -u) <(grep -o -E 'https?://[^/[:space:])>`]+' "$H" | sort -u) && HOSTS="$(sed -n -E 's/^- `([a-z0-9-]+)` — .*/\1/p' "$HOME/CLAUDE.md")" && test -n "$HOSTS" && DIFF="$(git diff v1.0.0-rc1 -- CHANGELOG.md "$R" "$H")" && ADDED="$(grep '^+' <<<"$DIFF")" && ! grep -n -i -F -f <(printf '%s\n' "$HOSTS") <<<"$ADDED" && ! grep -n -i -F -f <(printf '%s\n' "$HOSTS") "$R" && ! grep -n -E '(^|[^0-9.])(10|172|192)\.[0-9]+\.[0-9]+\.[0-9]+' <<<"$ADDED" && uv run pytest -q --no-cov tests/test_baseline_guards.py</automated>
  </verify>
  <done>CHANGELOG.md has `## [1.0.0] - 2026-11-20` followed by the equivalence line, no undated heading, an unchanged
  rc1 section and unchanged link refs (diff 3/1). The 1.0.0 release notes link to the dated anchor at blob/v1.0.0,
  mention the tested rc1 and the latest-release checklist, keep Required actions through Full change list word for
  word, and use only github.com URLs. 08-HACS-DEFAULT-PR.md has the latest-release precondition in its tag bullet;
  everything before and after that bullet (including the REL-07 sentence and the logo open item) is byte-identical,
  with the same URL hosts. The rc1 notes are unchanged.
  No private host name or private IPv4 in added lines. tests/test_baseline_guards.py passes. Commit
  `docs(release): date 1.0.0 changelog entry and finalize release notes` contains exactly the 3 paths.</done>
</task>

<task type="auto">
  <name>Task 3: Full gates on the final tree, rc1 equivalence proof and SUMMARY</name>
  <files>.planning/quick/261120-onk-prepare-final-release-1-0-0-version-stri/261120-onk-SUMMARY.md</files>
  <action>
1. Run these gates on the final tree from the repo root, in this order, and record the exact result lines (the same
   commands the rc1 task 261118-nnf used):
   - `uv run pytest -q tests`: full suite with the coverage gate (fail_under 99 on custom_components.traefik_proxy).
     Report the test count (1192 at rc1) and the total coverage.
   - `uv run ruff check custom_components tests` and `uv run ruff format --check custom_components tests`.
   - `uv run mypy --strict custom_components/traefik_proxy`.
   - `make pre-commit` (`uvx pre-commit run --all-files`; every hook must pass). If a fixer hook rewrites a file such
     as CHANGELOG.md, the gate counts as failed: fix the content, rerun, and record the fix as a separate commit
     `docs(release): fix whitespace in 1.0.0 changelog entry` with explicit paths. Do not amend.
   - `make test-min-ha` (HA 2026.11.0, hashed lock). If the hashed install cannot run (network or cache), use the
     brief's venv `~/.cache/traefik-proxy-integration/ha2611-venv/bin/python -m pytest -q tests` as a cross-check and
     name the reason.
   - `make hassfest-sanity`.
   If a gate fails because of this task's changes, fix the cause in a new commit with explicit paths. If a gate also
   fails at v1.0.0-rc1, stop and report it as a blocker; do not fix product code in this task.
2. Run the rc1 equivalence proof and the repository checks (see `<verify>`), and paste their output into SUMMARY.md:
   - `git diff v1.0.0-rc1..HEAD -- custom_components` shows only the manifest version line.
   - `git diff v1.0.0-rc1..HEAD --stat` lists every changed path. Expected: manifest.json, pyproject.toml, uv.lock,
     CHANGELOG.md, the two 08-*.md docs, plus this quick task's own docs (and STATE.md only if the orchestrator's
     pre-dispatch commit touched it).
   - Each task commit contains exactly its planned paths; neither .planning/config.json nor .planning/state.json is in
     any commit, and their working-tree status is unchanged.
   - No tag `v1.0.0` exists, `v1.0.0-rc1` still points to 22902d9, nothing was pushed (`@{u}` is still 22902d9), and
     the branch is still `feat/marketplace-polish` (no merge).
3. Write `.planning/quick/261120-onk-prepare-final-release-1-0-0-version-stri/261120-onk-SUMMARY.md` with:
   - Commit hashes and subjects.
   - Every gate with its result line: test count, coverage, ruff, mypy, pre-commit hooks, min-HA count, hassfest
     `Integrations: 1` / `Invalid integrations: 0`, hassfest-sanity, release check (positive and negative), and the
     AwesomeVersion line.
   - The rc1 equivalence output (custom_components diff and `--stat`).
   - Worker decisions P1, P2, P3 and P5 from the context, plus any new ones (decision, reason, alternative).
   - A "Deferred" section with P4 (REL-07 status and logo open item in 08-HACS-DEFAULT-PR.md: proposed to the user,
     not done).
   - Deviations from this plan.
   - "Next steps for the user (not done by the agent)": 1. Push the branch. 2. Mark PR #2 ready, merge to main, and
      check the Validate run on main. 3. Create tag `v1.0.0` on the version-bump commit or a later commit (never on
      22902d9). 4. Publish the GitHub release "Traefik Proxy 1.0.0" with the body below the cut line of
      08-RELEASE-NOTES-v1.0.0.md, not as a pre-release and set as latest; if the date is not 2026-11-20, change the
      CHANGELOG date and the anchor together first. 5. Check the "Release check" run. 6. Submit to hacs/default
      following 08-HACS-DEFAULT-PR.md.
   Write no private host names into SUMMARY.md. Do not stage or commit SUMMARY.md, PLAN.md, `.planning/STATE.md`,
   `.planning/config.json` or `.planning/state.json`; the quick workflow's final docs commit handles the quick-task
   artifacts.
  </action>
  <verify>
    <automated>uv run pytest -q tests && uv run ruff check custom_components tests && uv run ruff format --check custom_components tests && uv run mypy --strict custom_components/traefik_proxy && make pre-commit && make test-min-ha && make hassfest-sanity && git diff --stat v1.0.0-rc1..HEAD && test "$(git diff --numstat v1.0.0-rc1 HEAD -- custom_components)" = "$(printf '1\t1\tcustom_components/traefik_proxy/manifest.json')" && D0="$(git diff -U0 v1.0.0-rc1 HEAD -- custom_components)" && test "$(grep -E '^[-+]' <<<"$D0" | grep -v -E '^(---|\+\+\+) ')" = "$(printf '%s\n' '-  "version": "1.0.0-rc1"' '+  "version": "1.0.0"')" && git diff --quiet 8a447c2 HEAD -- custom_components pyproject.toml uv.lock && NAMES="$(git diff --name-only v1.0.0-rc1 HEAD -- . ':!.planning/quick/261120-onk-*' ':!.planning/STATE.md')" && test "$(LC_ALL=C sort <<<"$NAMES" | tr '\n' ' ')" = ".planning/phases/08-marketplace-release-readiness/08-HACS-DEFAULT-PR.md .planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0.md CHANGELOG.md custom_components/traefik_proxy/manifest.json pyproject.toml uv.lock " && LOG="$(git log --format='%H%x09%s' v1.0.0-rc1..HEAD)" && C1="$(awk -F'\t' '$2=="chore(release): bump version to 1.0.0"{print $1}' <<<"$LOG")" && C2="$(awk -F'\t' '$2=="docs(release): date 1.0.0 changelog entry and finalize release notes"{print $1}' <<<"$LOG")" && F1="$(git show --name-only --format= "$C1")" && test "$(LC_ALL=C sort <<<"$F1" | tr '\n' ' ')" = "custom_components/traefik_proxy/manifest.json pyproject.toml uv.lock " && F2="$(git show --name-only --format= "$C2")" && test "$(LC_ALL=C sort <<<"$F2" | tr '\n' ' ')" = ".planning/phases/08-marketplace-release-readiness/08-HACS-DEFAULT-PR.md .planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0.md CHANGELOG.md " && ALLNAMES="$(git diff --name-only v1.0.0-rc1 HEAD)" && ! grep -q -E '^\.planning/(config|state)\.json$' <<<"$ALLNAMES" && PORC="$(git status --porcelain -- .planning/config.json .planning/state.json)" && test "$(tr '\n' '|' <<<"$PORC")" = " M .planning/config.json|?? .planning/state.json|" && test -z "$(git tag --list 'v1.0.0')" && test "$(git rev-parse 'v1.0.0-rc1^{commit}')" = 22902d90db2e77f4b5e136a1cdc92ca7bfeefa86 && test "$(git rev-parse '@{u}')" = 22902d90db2e77f4b5e136a1cdc92ca7bfeefa86 && test "$(git rev-parse --abbrev-ref HEAD)" = feat/marketplace-polish && S=.planning/quick/261120-onk-prepare-final-release-1-0-0-version-stri/261120-onk-SUMMARY.md && test -f "$S" && HOSTS="$(sed -n -E 's/^- `([a-z0-9-]+)` — .*/\1/p' "$HOME/CLAUDE.md")" && test -n "$HOSTS" && ! grep -n -i -F -f <(printf '%s\n' "$HOSTS") "$S"</automated>
  </verify>
  <done>All gates pass on the final tree and SUMMARY.md records the exact result lines: full pytest with coverage at or
  above 99 %, ruff check, ruff format --check, mypy --strict, every pre-commit hook, min-HA 2026.11.0, hassfest-sanity
  and hassfest. `git diff v1.0.0-rc1..HEAD -- custom_components` is the single manifest line, and the three version
  files equal 8a447c2. Outside this quick task's docs the branch diff since v1.0.0-rc1 touches exactly the 6 planned
  paths, each task commit holds exactly its paths, config.json and state.json are untouched, and there is no tag
  v1.0.0, no push and no merge. The user's next steps are listed.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Git tag (user) -> release.yml | The tag name the user pushes is compared with manifest.json by scripts/check_release_tag.py (argv only, unchanged here). |
| Repository -> HACS / HA loader | The manifest version string is parsed by AwesomeVersion in hassfest, HACS and the HA loader. |
| Release notes / CHANGELOG / hacs/default draft -> public GitHub | Text written here becomes public on the release page, in the repository and in the hacs/default PR. |
| Local Docker -> worktree | The hassfest container mounts the worktree read-only. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-261120-onk-01 | Tampering | 1.0.0 differs from the tested rc1 code | high | mitigate | Task 1 and Task 3 gate that `git diff v1.0.0-rc1..HEAD -- custom_components` is exactly the manifest version line and that custom_components, pyproject.toml and uv.lock equal 8a447c2 byte for byte. |
| T-261120-onk-02 | Tampering | manifest.json version vs tag `v1.0.0` | medium | mitigate | `check_release_tag.py v1.0.0` exits 0 and `v1.0.0-rc1` exits 1; AwesomeVersion order and tag equality asserted. The release-notes checklist warns not to tag 22902d9 as v1.0.0. |
| T-261120-onk-03 | Information Disclosure | CHANGELOG.md, release notes, hacs/default draft, SUMMARY.md | medium | mitigate | Privacy gates: no private host name in added lines, the release notes or SUMMARY.md (list read from the user's CLAUDE.md at run time, never copied), no private IPv4 in added lines, release-notes URL hosts only github.com, hacs/default draft URL host set unchanged. |
| T-261120-onk-04 | Elevation of Privilege | accidental push / tag / merge / release by the agent | high | mitigate | No push, tag, merge or gh release command in any task (U1, M8). Task 3 verifies no tag v1.0.0, v1.0.0-rc1 unchanged, `@{u}` still 22902d9 and the branch unchanged. |
| T-261120-onk-05 | Tampering | uv.lock refresh | medium | mitigate | `uv lock` without upgrade flags; numstat against v1.0.0-rc1 must be `1 1`, the lock must equal 8a447c2, and `uv lock --locked` must pass. |
| T-261120-onk-06 | Repudiation | release published as pre-release or not as latest | low | mitigate | Release-notes checklist and the hacs/default preconditions state "not a pre-release, set as the latest release"; gated by grep in Task 2. |
| T-261120-onk-07 | Tampering | Local hassfest container | low | mitigate | `make hassfest` uses the digest-pinned image, read-only mount and `--rm`; the Task 1 gate fails on any leftover container or volume. |
| T-261120-onk-SC | Tampering | `uv run --with awesomeversion` | low | accept | awesomeversion is already locked as a Home Assistant dependency; no new package enters the project, and the uv.lock gates prove it. |
</threat_model>

<verification>
Run from the repo root on the final tree, after the task commits:
- `python3 scripts/check_release_tag.py v1.0.0` -> exit 0, `tag v1.0.0 matches manifest.json version 1.0.0`;
  `v1.0.0-rc1` -> exit 1
- AwesomeVersion assertion (Task 1 verify) -> `awesomeversion ok 1.0.0 <strategy>`
- `make hassfest` -> `Invalid integrations: 0`; `docker ps -aq` and `docker volume ls -q` unchanged
- `uv run pytest -q tests` -> all pass (1192 at rc1), coverage >= 99 %
- `uv run ruff check custom_components tests`, `uv run ruff format --check custom_components tests`,
  `uv run mypy --strict custom_components/traefik_proxy` -> clean
- `make pre-commit` -> every hook Passed; `make test-min-ha` -> green on HA 2026.11.0; `make hassfest-sanity` -> passed
- `git diff v1.0.0-rc1..HEAD -- custom_components` -> only `"version": "1.0.0-rc1"` -> `"version": "1.0.0"`
- `git diff v1.0.0-rc1..HEAD --stat` -> manifest.json, pyproject.toml, uv.lock, CHANGELOG.md, the two 08-*.md docs,
  plus quick-task docs
- `.planning/config.json` / `.planning/state.json` untouched; no tag v1.0.0; no push; no merge
</verification>

<success_criteria>
- 1.0.0 is provably the tested rc1 code with only the manifest version changed.
- The user can push, merge, tag `v1.0.0` and publish the release as latest without any further file change; the
  release check passes, and hassfest and HACS accept the version.
- CHANGELOG, release notes and the hacs/default draft state today's facts (dated heading, valid anchor, rc1 tested,
  latest-release precondition) and contain no private host names. The REL-07 and logo passages are untouched
  (P4 deferred).
- Every repository gate is green, and the commits are atomic with explicit paths.
</success_criteria>

<output>
Create `.planning/quick/261120-onk-prepare-final-release-1-0-0-version-stri/261120-onk-SUMMARY.md` when done.
</output>
