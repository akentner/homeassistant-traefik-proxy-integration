---
phase: 261118-nnf-prepare-release-candidate-1-0-0-rc1-vers
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - custom_components/traefik_proxy/manifest.json
  - pyproject.toml
  - uv.lock
  - CHANGELOG.md
  - .planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0-rc1.md
autonomous: true
requirements: [M8-RC1-VERSION-BUMP, M8-RC1-RELEASE-DOCS]

estimate:
  tokens: 55000
  raw_tokens: 55000
  tasks: 3
  confidence: low

must_haves:
  truths:
    - "manifest.json version is exactly 1.0.0-rc1, and `python3 scripts/check_release_tag.py v1.0.0-rc1` exits 0. scripts/check_release_tag.py and .github/workflows/release.yml stay unchanged. Tags keep the v prefix (decision log I4/I5); the user cuts the tag and the release (M8, U1)"
    - "AwesomeVersion accepts the manifest version as SemVer, orders it after 0.3.0 and before 1.0.0, and treats the tag v1.0.0-rc1 as equal to it. HACS can therefore offer rc1 to pre-release testers on 0.3.x and offer 1.0.0 as an update later"
    - "Local hassfest (`make hassfest`, digest-pinned image) reports `Invalid integrations: 0`, and no Docker container or volume is left behind"
    - "pyproject.toml [project] version is the canonical PEP 440 form 1.0.0rc1. The project entry in uv.lock says 1.0.0rc1. uv.lock differs from HEAD in exactly that one line, and `uv lock --locked` passes"
    - "CHANGELOG.md has `## [1.0.0-rc1] - 2026-11-18` between the content of `## [1.0.0] - Unreleased` and `## [0.3.0] - 2026-07-06`, plus a `[1.0.0-rc1]:` compare link ref between the `[1.0.0]:` and `[0.3.0]:` refs. The diff only adds lines, so the [1.0.0] section is unchanged"
    - "08-RELEASE-NOTES-v1.0.0-rc1.md exists. Its header covers the pre-release status, a backup/snapshot before upgrading from 0.3.x (breaking changes, entity replacement, minimum HA 2026.11.0), installing through HACS with pre-releases enabled, and feedback through GitHub issues. The 1.0.0 notes follow the header. It has no private host names and links only to github.com and hacs.xyz. 08-RELEASE-NOTES-v1.0.0.md is unchanged"
    - "These pass on the final tree: full pytest with the coverage gate, ruff check, ruff format --check, mypy --strict, `make pre-commit`, `make test-min-ha`, and `make hassfest-sanity`. There are exactly two new commits, each staged and committed with explicit paths. .planning/config.json (modified) and .planning/state.json (untracked) stay untouched. No push, no tag and no release are made"
  artifacts:
    - path: "custom_components/traefik_proxy/manifest.json"
      provides: "Integration version read by HA, hassfest, HACS and scripts/check_release_tag.py"
      contains: "\"version\": \"1.0.0-rc1\""
    - path: "pyproject.toml"
      provides: "Dev project version (virtual project, never built or published)"
      contains: "version = \"1.0.0rc1\""
    - path: "uv.lock"
      provides: "Lock with the refreshed root project version, nothing else changed"
      contains: "version = \"1.0.0rc1\""
    - path: "CHANGELOG.md"
      provides: "Keep a Changelog entry for the rc1 tag and its compare link"
      contains: "## [1.0.0-rc1] - 2026-11-18"
    - path: ".planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0-rc1.md"
      provides: "Draft body for the GitHub pre-release v1.0.0-rc1 (the user publishes it)"
      contains: "1.0.0-rc1"
  key_links:
    - from: "git tag v1.0.0-rc1 (created by the user)"
      to: "custom_components/traefik_proxy/manifest.json version"
      via: ".github/workflows/release.yml -> scripts/check_release_tag.py strips one leading v and compares the strings exactly"
      pattern: "tag_version == version"
    - from: "manifest.json version 1.0.0-rc1"
      to: "HACS / HA loader version handling"
      via: "AwesomeVersion SemVer pre-release ordering (0.3.0 < 1.0.0-rc1 < 1.0.0)"
      pattern: "1\\.0\\.0-rc1"
    - from: "08-RELEASE-NOTES-v1.0.0-rc1.md change-list link"
      to: "CHANGELOG.md section [1.0.0] at tag v1.0.0-rc1"
      via: "blob/v1.0.0-rc1/CHANGELOG.md#100---unreleased (the heading at that tag is still Unreleased)"
      pattern: "blob/v1\\.0\\.0-rc1/CHANGELOG\\.md#100---unreleased"
---

<objective>
Prepare release candidate 1.0.0-rc1 on branch `feat/marketplace-polish`. The user publishes the current state as a
GitHub pre-release. Decision log M8: the user handles the tag and the release; agents prepare the version bump and the
release notes. This task changes only versions and release docs. No product code or test code changes.

Purpose: the user can create tag `v1.0.0-rc1` and a GitHub pre-release. The release check workflow passes, hassfest and
HACS accept the version, testers know how to install the RC safely, and HACS offers 1.0.0 as an update later.

Output: two commits.
1. Version bump: manifest.json, pyproject.toml, uv.lock.
2. Release docs: a CHANGELOG entry and the RC release-notes draft.
After that come a full gate run and the quick-task SUMMARY.md.

Planner findings the executor relies on (verified on HEAD 8a447c2, 2026-11-18):
- Only three places pin the current version: `custom_components/traefik_proxy/manifest.json:13`, `pyproject.toml:3` and
  the root project entry in `uv.lock` (line 1329). `git grep -n -F` for the quoted string `"1.0.0"` (excluding
  `.planning` and `tests/fixtures`) returns exactly these three lines.
- `scripts/check_release_tag.py` and `.github/workflows/release.yml` compare the tag with manifest.json only.
  `tests/test_release_tag_check.py` reads the manifest version dynamically, and no test reads the version from
  pyproject.toml. The pyproject form cannot break the release check.
- `.github/requirements-min-ha.txt` is `uv pip compile` output of `.github/requirements-min-ha.in`, which lists only
  `pytest-homeassistant==2026.11.0` and `pytest-cov`. It does not contain the project or its version, so `make test-min-ha`
  needs no lock refresh.
- AwesomeVersion probe: `1.0.0-rc1` is SEMVER, `0.3.0 < 1.0.0-rc1 < 1.0.0`, and `v1.0.0-rc1 == 1.0.0-rc1`. However,
  `1.0.0rc1` (PEP 440) != `1.0.0-rc1`, so the manifest must use the hyphenated SemVer form to match the tag
  `v1.0.0-rc1`.
- uv probe on a scratch copy: with pyproject `1.0.0rc1`, `uv lock` changed exactly one uv.lock line (1.0.0 -> 1.0.0rc1).
  With pyproject `1.0.0-rc1`, uv also wrote `1.0.0rc1` to the lock, because it normalises. awesomeversion 25.8.0 is
  already locked as a Home Assistant dependency, so no new package is added.
- hassfest runs locally as `make hassfest`:
  `docker run --rm -v "$(CURDIR)":/github/workspace:ro <digest-pinned ghcr.io/home-assistant/hassfest>`.
  Docker 29.9.3 is running, and the pinned digest `sha256:da6522993280...` is already in the local image cache, so it
  runs offline. hassfest accepts SemVer pre-release versions for custom integrations.
- README.md and hacs.json do not mention the current version. docs/ mentions only Traefik's version.
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
@custom_components/traefik_proxy/manifest.json
@scripts/check_release_tag.py
@.github/workflows/release.yml
@CHANGELOG.md
@.planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0.md
@Makefile

Rules from the brief and the orchestrator (binding):
- Commit on this branch only. Do NOT push, do NOT tag, do NOT create a GitHub release or PR (decision log U1, M8).
- Stage and commit with explicit paths only: `git add -- <paths>`, then `git commit -m ... -- <paths>`. Never use
  `git add -A`, `git add .` or `git commit -a`.
- Leave `.planning/config.json` (modified) and `.planning/state.json` (untracked) untouched and out of every commit.
- Do not use a real Home Assistant instance. Docker is allowed only for the throwaway hassfest container (`--rm`).
- If a gate cannot run (Docker daemon down, image pull or network failure, missing pre-commit cache), stop with a clear
  blocker in SUMMARY.md. Never fake a result.

Planner decisions (put them in SUMMARY.md under "Worker decisions"):
- P1 pyproject.toml uses the canonical PEP 440 form `1.0.0rc1`, not `1.0.0-rc1`. Reason: the project is virtual (never
  built or published), nothing compares the pyproject version with the tag or the manifest, and uv writes the
  normalised `1.0.0rc1` into uv.lock either way. The canonical form keeps pyproject.toml and uv.lock literally equal.
  Alternative: `1.0.0-rc1`, which uv accepts and normalises; the difference is cosmetic only.
- P2 manifest.json uses exactly `1.0.0-rc1`, the SemVer pre-release form. Reason: the tag is `v1.0.0-rc1`,
  check_release_tag.py compares strings exactly, and AwesomeVersion treats `1.0.0rc1` as different from `1.0.0-rc1`.
- P3 These places that name 1.0.0 stay unchanged, because none of them states the version being shipped now:
  - The `| version | 1.0.0 |` rows in CLAUDE.md:60 and .planning/research/STACK.md:44. Both documents describe the
    1.0.0 target state, and STACK.md says so in its header "shipped 1.0.0 state". The CLAUDE.md stack section is
    generated from STACK.md. The RC value is transient, and the final release sets the manifest back to 1.0.0.
  - The coverage comment in pyproject.toml:30 (a historical measurement).
  - The usage example in the docstring of scripts/check_release_tag.py.
  - The tag URL example in tests/test_hacs_action_local.py:188.
  - The CHANGELOG `[1.0.0]` heading and its link ref.
  - The AwesomeVersion examples in CLAUDE.md.
  Alternative: set the two table rows to `1.0.0-rc1` now and back to 1.0.0 at the final release.
- P4 `.github/requirements-min-ha.txt` is not refreshed, because it does not embed the project version (see the
  objective).
</context>

<tasks>

<task type="tracer">
  <name>Task 1: Version 1.0.0-rc1 end to end (manifest -> pyproject -> uv.lock -> release check -> AwesomeVersion -> hassfest)</name>
  <files>custom_components/traefik_proxy/manifest.json, pyproject.toml, uv.lock</files>
  <action>
1. In `custom_components/traefik_proxy/manifest.json`, set the value of the `version` key to `1.0.0-rc1`, the SemVer
   pre-release form (planner decision P2, decision log I4/I5). Change only that value and keep the key order (hassfest
   requires domain, name, then alphabetical).
2. In `pyproject.toml`, set the `[project]` `version` line (line 3) to `1.0.0rc1`, the canonical PEP 440 form (planner
   decision P1). Leave the coverage comment on line 30 unchanged (P3).
3. Refresh the lock with `uv lock` from the repo root. Make sure UV_LOCKED is not set in this shell, because with
   UV_LOCKED=1, `uv lock` refuses to change the lock. Expected uv output:
   `Updated homeassistant-traefik-proxy-integration v1.0.0 -> v1.0.0rc1`. If uv also reports other package changes,
   stop: the lock must change in exactly one line. Do not run any `uv run` before this step, because `uv run` would
   re-lock implicitly.
4. Confirm that no other tracked file pins the current version. The quoted-string git grep in `<verify>` must return
   nothing. Do not edit the places listed in P3.
5. Prove the end-to-end path. Run every command in `<verify>`:
   - the release check for `v1.0.0-rc1` (exit 0), plus the negative check that `v1.0.0` now exits 1;
   - the AwesomeVersion assertion on the real manifest value;
   - the release-check unit tests with `--no-cov`. A partial run without `--no-cov` trips the 99 % fail_under gate from
     pyproject.toml;
   - `make hassfest`, wrapped so that it checks for leftover containers and volumes.
   If Docker is not available or the pinned image is missing and cannot be pulled, stop with a blocker. Do not skip
   hassfest and do not report a result you did not see.
6. Commit with explicit paths only:
   `git add -- custom_components/traefik_proxy/manifest.json pyproject.toml uv.lock`, then
   `git commit -m "<msg>" -- custom_components/traefik_proxy/manifest.json pyproject.toml uv.lock`.
   Subject: `chore(release): bump version to 1.0.0-rc1`.
   The body uses short English bullets:
   - manifest 1.0.0-rc1 (SemVer pre-release, tag v1.0.0-rc1);
   - pyproject 1.0.0rc1 (canonical PEP 440; uv.lock stores the normalised form either way, and nothing compares the
     pyproject version with the tag);
   - uv.lock refreshed (root project version only).
  </action>
  <verify>
    <automated>git grep -n -F '"1.0.0"' -- ':!.planning' ':!tests/fixtures'; test $? -eq 1 && test "$(grep -c -x '  "version": "1.0.0-rc1"' custom_components/traefik_proxy/manifest.json)" = 1 && test "$(grep -c -x 'version = "1.0.0rc1"' pyproject.toml)" = 1 && test "$(grep -A1 -x 'name = "homeassistant-traefik-proxy-integration"' uv.lock | grep -c -x 'version = "1.0.0rc1"')" = 1 && NS="$(git diff --numstat 8a447c2 -- uv.lock)" && test "$(cut -f1,2 <<<"$NS")" = "$(printf '1\t1')" && uv lock --locked && python3 scripts/check_release_tag.py v1.0.0-rc1 && { python3 scripts/check_release_tag.py v1.0.0; test $? -eq 1; } && uv run --with awesomeversion python3 -c 'import json; from awesomeversion import AwesomeVersion as V; m = json.load(open("custom_components/traefik_proxy/manifest.json"))["version"]; v = V(m); assert m == "1.0.0-rc1" and v.valid and v.strategy.name == "SEMVER", (m, v.strategy); assert V("0.3.0") < v < V("1.0.0"), "order"; assert V("v1.0.0-rc1") == v, "tag"; print("awesomeversion ok", m, v.strategy.name)' && uv run pytest -q --no-cov tests/test_release_tag_check.py && bash -c 'set -o pipefail; c0=$(docker ps -aq | sort); v0=$(docker volume ls -q | sort); make hassfest 2>&1 | tail -n 30 | tee /dev/stderr | grep -F "Invalid integrations: 0" >/dev/null; rc=$?; c1=$(docker ps -aq | sort); v1=$(docker volume ls -q | sort); if [ "$c0" != "$c1" ] || [ "$v0" != "$v1" ]; then echo "leftover docker container or volume" >&2; exit 3; fi; exit $rc'</automated>
  </verify>
  <done>The manifest says 1.0.0-rc1, pyproject.toml and the uv.lock project entry say 1.0.0rc1, and uv.lock differs from
  HEAD in exactly one line. `check_release_tag.py v1.0.0-rc1` exits 0, and `v1.0.0` exits 1. AwesomeVersion asserts SEMVER,
  0.3.0 &lt; rc1 &lt; 1.0.0, and tag equality. tests/test_release_tag_check.py passes. hassfest prints
  `Invalid integrations: 0` with no leftover container or volume. Commit `chore(release): bump version to 1.0.0-rc1`
  contains exactly the 3 paths.</done>
</task>

<task type="auto">
  <name>Task 2: CHANGELOG entry and RC release-notes draft</name>
  <files>CHANGELOG.md, .planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0-rc1.md</files>
  <action>
1. CHANGELOG.md (Keep a Changelog, newest first). Only add lines; change no existing line.
   - Insert a new section directly before the line `## [0.3.0] - 2026-07-06`, which is the end of the
     `## [1.0.0] - Unreleased` content. Keep one blank line before and after it, as the other sections do.
   - Heading: `## [1.0.0-rc1] - 2026-11-18`. Use no `###` subsection; the prose style of the `[0.1.2]` entry is the model.
   - Body: two to four short wrapped lines (wrap at about 80 columns like the rest of the file). They say three things.
     First, this is the release candidate for 1.0.0, published as a GitHub pre-release. Second, it contains every change
     listed under [1.0.0] above, including the breaking changes and required actions. Third, HACS offers it only when
     pre-releases are enabled for this repository.
   - Insert the link ref `[1.0.0-rc1]: https://github.com/akentner/homeassistant-traefik-proxy-integration/compare/v0.3.0...v1.0.0-rc1`
     directly after the existing `[1.0.0]:` link ref line and before the `[0.3.0]:` line.
   - The text must not contain the string `2026.3` and must not link to developers.home-assistant.io; the guards in
     tests/test_baseline_guards.py scan CHANGELOG.md for that link.
2. Create `.planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0-rc1.md` in English, derived from
   `08-RELEASE-NOTES-v1.0.0.md`. Do not modify that source file.
   a) Leading HTML comment. Keep the source's structure and its "----- cut -----" line, and replace the content as
      follows:
      - This is the draft for the GitHub pre-release v1.0.0-rc1, created by the user, not by an agent. Paste everything
        below the cut line as the release body.
      - Before publishing, the tagged commit must exist on GitHub (push first), and its manifest.json version must be
        1.0.0-rc1.
      - Release title "Traefik Proxy 1.0.0-rc1", tag `v1.0.0-rc1`. The release workflow strips the v and compares the
        tag with manifest.json.
      - In the GitHub release form, tick "Set as a pre-release" and do not tick "Set as the latest release".
      - The CHANGELOG is already dated `## [1.0.0-rc1] - 2026-11-18`, and the change-list link needs no anchor edit.
      - For the final 1.0.0: set manifest.json and pyproject.toml back to 1.0.0, run `uv lock`, date the [1.0.0]
        heading, and use 08-RELEASE-NOTES-v1.0.0.md.
      - This file is a planning draft and is not shipped.
   b) Body heading: `# Traefik Proxy 1.0.0-rc1 (release candidate)`. Follow it with one short paragraph: this is a
      pre-release for testing before 1.0.0, it contains every 1.0.0 change, and feedback is welcome.
   c) `## Before you upgrade from 0.3.x`:
      - Make a full Home Assistant backup (Settings → System → Backups) or a snapshot of the VM or container first.
      - This release migrates the config entry and replaces entities: the router binary sensors are removed, and devices
        are replaced by a main device with sub-devices. Going back to 0.3.x does not restore them; restoring the backup
        is the way back.
      - Home Assistant 2026.11.0 or later is required, and HACS refuses older versions.
      - Read "Required actions" below before updating.
   d) `## Install the release candidate with HACS`. Sources: hacs.xyz/docs/use/entities/switch and
      hacs.xyz/docs/use/repositories/dashboard, checked 2026-11-18. Do not invent UI labels beyond these.
      - Already installed: HACS creates one switch entity per downloaded repository that includes pre-releases in update
        checks. The switch is disabled by default. Enable it under Settings → Devices & services → Entities, then turn it
        on, and HACS offers 1.0.0-rc1 as an update. Alternatively, open Traefik Proxy in HACS, choose Redownload, and
        pick `v1.0.0-rc1` under "Need a different version?".
      - New install: if HACS does not list the repository, add `https://github.com/akentner/homeassistant-traefik-proxy-integration`
        as a custom repository of type Integration (same wording as README.md). In the download dialog, pick
        `v1.0.0-rc1` under "Need a different version?". If it is not listed there, download the integration, then enable
        the pre-release switch and update.
      - Restart Home Assistant after the download.
      - When 1.0.0 is released, HACS offers it as an update to 1.0.0-rc1. Turn the pre-release switch off again if you do
        not want future pre-releases.
   e) `## Feedback`:
      - Open an issue at `https://github.com/akentner/homeassistant-traefik-proxy-integration/issues` and say that you run
        1.0.0-rc1.
      - Include the Home Assistant version and the Traefik version.
      - Attach the diagnostics download. Credentials and secret router-rule values are redacted, but review the file
        before posting.
   f) A horizontal rule, then the 1.0.0 notes from the source file: the intro paragraph ("1.0.0 is a major rework…"),
      `## Required actions` (items 1–7), `## Highlights`, `## Full change list`, and the Traefik trademark line.
      Adapt only these points:
      - In required action 1, the sentence "1.0.0 does not install on older versions" becomes "This release does not
        install on older versions".
      - The full-change-list link points to
        `https://github.com/akentner/homeassistant-traefik-proxy-integration/blob/v1.0.0-rc1/CHANGELOG.md#100---unreleased`.
        At the tag v1.0.0-rc1 the 1.0.0 heading is still "Unreleased", so this anchor is correct. Add that 1.0.0-rc1
        contains all of it.
      Keep everything else word for word.
   g) Write no host names other than github.com and hacs.xyz, no IP addresses, no tokens, and no personal data beyond
      the public repository URL and the codeowner already shown in the repository.
3. Commit with explicit paths only:
   `git add -- CHANGELOG.md .planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0-rc1.md`, then
   `git commit -m "<msg>" -- CHANGELOG.md .planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0-rc1.md`.
   Subject: `docs(release): add 1.0.0-rc1 changelog entry and release notes`. The body is one or two bullets.
  </action>
  <verify>
    <automated>F=.planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0-rc1.md; test "$(grep -c -x '## \[1\.0\.0-rc1\] - 2026-11-18' CHANGELOG.md)" = 1 && awk '/^## \[1\.0\.0\] - Unreleased$/{a=NR} /^## \[1\.0\.0-rc1\] - 2026-11-18$/{b=NR} /^## \[0\.3\.0\] - 2026-07-06$/{c=NR} /^\[1\.0\.0\]: /{d=NR} /^\[1\.0\.0-rc1\]: https:\/\/github\.com\/akentner\/homeassistant-traefik-proxy-integration\/compare\/v0\.3\.0\.\.\.v1\.0\.0-rc1$/{e=NR} /^\[0\.3\.0\]: /{f=NR} END{exit !(a&&b&&c&&d&&e&&f && a<b && b<c && d<e && e<f)}' CHANGELOG.md && NS="$(git diff --numstat 8a447c2 -- CHANGELOG.md)" && test "$(cut -f2 <<<"$NS")" = 0 && test -f "$F" && git diff --quiet 8a447c2 -- .planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0.md && grep -q -F '# Traefik Proxy 1.0.0-rc1 (release candidate)' "$F" && grep -q -x '## Before you upgrade from 0.3.x' "$F" && grep -q -x '## Install the release candidate with HACS' "$F" && grep -q -x '## Feedback' "$F" && grep -q -x '## Required actions' "$F" && grep -q -x '## Highlights' "$F" && grep -q -x '## Full change list' "$F" && grep -q -F 'blob/v1.0.0-rc1/CHANGELOG.md#100---unreleased' "$F" && grep -q -F 'Set as a pre-release' "$F" && grep -q -F '2026.11.0' "$F" && grep -q -i -E 'backup|snapshot' "$F" && grep -q -F 'homeassistant-traefik-proxy-integration/issues' "$F" && test -z "$(grep -o -E 'https?://[^/[:space:])>`]+' "$F" | sort -u | grep -v -x -E 'https://(github\.com|hacs\.xyz)')" && test -n "$(sed -n -E 's/^- `([a-z0-9-]+)` — .*/\1/p' "$HOME/CLAUDE.md")" && ! grep -n -i -F -f <(sed -n -E 's/^- `([a-z0-9-]+)` — .*/\1/p' "$HOME/CLAUDE.md") "$F" CHANGELOG.md && ! grep -n -E '(^|[^0-9.])(10|172|192)\.[0-9]+\.[0-9]+\.[0-9]+' "$F" && uv run pytest -q --no-cov tests/test_baseline_guards.py</automated>
  </verify>
  <done>CHANGELOG.md has the dated rc1 section between [1.0.0] Unreleased and [0.3.0], and the rc1 compare link ref
  between the [1.0.0] and [0.3.0] refs. Its diff only adds lines. The release-notes draft exists with the RC comment
  header, the four RC sections and the unchanged 1.0.0 sections. Its change-list link points to the tag blob anchor.
  It contains no private host names or IP addresses, and its only URL hosts are github.com and hacs.xyz. The source notes
  file is unchanged, and tests/test_baseline_guards.py passes. Commit
  `docs(release): add 1.0.0-rc1 changelog entry and release notes` contains exactly the 2 paths.</done>
</task>

<task type="auto">
  <name>Task 3: Full gates on the final tree and SUMMARY</name>
  <files>.planning/quick/261118-nnf-prepare-release-candidate-1-0-0-rc1-vers/261118-nnf-SUMMARY.md</files>
  <action>
1. Run these gates on the final tree from the repo root, in this order, and record the exact result lines:
   - `uv run pytest -q tests`. This is the full suite with the coverage gate (fail_under 99 on
     custom_components.traefik_proxy). Report the test count (1192 at HEAD 8a447c2) and the total coverage.
   - `uv run ruff check custom_components tests`.
   - `uv run ruff format --check custom_components tests`.
   - `uv run mypy --strict custom_components/traefik_proxy`.
   - `make pre-commit` (= `uvx pre-commit run --all-files`; all hooks must pass). If a fixer hook rewrites a file such as
     CHANGELOG.md (end-of-file or trailing whitespace), the gate counts as failed. Fix the content, rerun the hook, and
     record the fix as a separate commit `docs(release): fix whitespace in 1.0.0-rc1 changelog entry` with explicit
     paths. Do not amend.
   - `make test-min-ha` (HA 2026.11.0, hashed lock). The brief requires the minimum HA to stay green. If the hashed
     install cannot run (network or cache), use the brief's venv
     `~/.cache/traefik-proxy-integration/ha2611-venv/bin/python -m pytest -q tests` as a cross-check and name the
     reason.
   - `make hassfest-sanity`.
   If a gate fails because of this task's changes, fix the cause in a new commit with explicit paths. If a gate fails
   for a reason that existed before (it also fails at 8a447c2), stop and report it as a blocker. Do not fix product
   code in this task (scope: version and release docs only).
2. Run the final repository checks (see `<verify>`):
   - Exactly the two task commits sit on top of 8a447c2, each with its own path list. A whitespace fix commit from step 1
     may follow, if one was needed.
   - `.planning/config.json` and `.planning/state.json` are untouched.
   - No tag `v1.0.0-rc1` exists locally.
   - Nothing was pushed: the upstream ref `origin/feat/marketplace-polish` still points to 8a447c2.
3. Write `.planning/quick/261118-nnf-prepare-release-candidate-1-0-0-rc1-vers/261118-nnf-SUMMARY.md` with these parts:
   - Commit hashes and subjects.
   - Every gate with its result line: test count, coverage, ruff, mypy, pre-commit hooks, min-HA count, hassfest
     `Integrations: 1` / `Invalid integrations: 0`, release check, and the AwesomeVersion line.
   - Worker decisions P1–P4 from the context, plus any new ones (decision, reason, alternative).
   - Deviations from this plan.
   - "Next steps for the user (not done by the agent)":
     1. Push the branch.
     2. Create tag `v1.0.0-rc1` on the bump commit or a later commit.
     3. Create the GitHub release as a pre-release with the body from 08-RELEASE-NOTES-v1.0.0-rc1.md.
     4. Check the "Release check" workflow run.
     5. For the final 1.0.0: set manifest.json and pyproject.toml back to 1.0.0, run `uv lock`, and date the [1.0.0]
        heading.
   Do not stage or commit SUMMARY.md, PLAN.md, `.planning/STATE.md`, `.planning/config.json` or `.planning/state.json`.
   The quick workflow's final docs commit handles the quick-task artifacts.
  </action>
  <verify>
    <automated>uv run pytest -q tests && uv run ruff check custom_components tests && uv run ruff format --check custom_components tests && uv run mypy --strict custom_components/traefik_proxy && make pre-commit && make test-min-ha && make hassfest-sanity && test "$(git rev-list --count 8a447c2..HEAD)" -ge 2 && SUBJ="$(git log --format=%s 8a447c2..HEAD)" && grep -q -x -F 'chore(release): bump version to 1.0.0-rc1' <<<"$SUBJ" && grep -q -x -F 'docs(release): add 1.0.0-rc1 changelog entry and release notes' <<<"$SUBJ" && NAMES="$(git diff --name-only 8a447c2 HEAD)" && test "$(LC_ALL=C sort <<<"$NAMES" | tr '\n' ' ')" = ".planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0-rc1.md CHANGELOG.md custom_components/traefik_proxy/manifest.json pyproject.toml uv.lock " && PORC="$(git status --porcelain -- .planning/config.json .planning/state.json)" && test "$(tr '\n' '|' <<<"$PORC")" = " M .planning/config.json|?? .planning/state.json|" && test -z "$(git tag --list 'v1.0.0-rc1')" && test "$(git rev-parse '@{u}')" = "$(git rev-parse 8a447c2)" && test -f .planning/quick/261118-nnf-prepare-release-candidate-1-0-0-rc1-vers/261118-nnf-SUMMARY.md</automated>
  </verify>
  <done>All gates pass on the final tree, and SUMMARY.md records the exact result lines: full pytest with coverage at or
  above 99 %, ruff check, ruff format --check, mypy --strict, every pre-commit hook, min-HA 2026.11.0, and
  hassfest-sanity. The branch diff since 8a447c2 touches exactly the 5 planned paths. config.json and state.json are
  unchanged and uncommitted. No tag or push exists, and the next steps for the user are listed.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Git tag (user) -> release.yml | The tag name the user pushes is compared with manifest.json by scripts/check_release_tag.py (argv only, no shell interpolation; unchanged here). |
| Repository -> HACS / HA loader | The manifest version string is parsed by AwesomeVersion in hassfest, HACS and the HA loader. |
| Release notes / CHANGELOG -> public GitHub | Text written here becomes public on the release page and in the repository. |
| Local Docker -> worktree | The hassfest container mounts the worktree read-only. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-261118-nnf-01 | Tampering | manifest.json version vs tag `v1.0.0-rc1` | medium | mitigate | Manifest set to exactly `1.0.0-rc1` (P2). Task 1 runs `check_release_tag.py v1.0.0-rc1` (exit 0) and `v1.0.0` (exit 1), plus the AwesomeVersion order and tag-equality assertion. |
| T-261118-nnf-02 | Information Disclosure | 08-RELEASE-NOTES-v1.0.0-rc1.md, CHANGELOG.md | medium | mitigate | Task 2 gates: no private host name (list read from the user's CLAUDE.md at run time, not copied into the repo), no private IPv4, and URL hosts limited to github.com and hacs.xyz. |
| T-261118-nnf-03 | Elevation of Privilege | accidental push / tag / release by the agent | high | mitigate | No push, tag or gh release command in any task (U1, M8). Task 3 verifies that no local tag `v1.0.0-rc1` exists and that the upstream ref still points to 8a447c2. |
| T-261118-nnf-04 | Tampering | uv.lock refresh | medium | mitigate | `uv lock` without upgrade flags. The gate requires `git diff --numstat HEAD -- uv.lock` = `1 1` and `uv lock --locked` to pass, so no dependency moves. |
| T-261118-nnf-05 | Denial of Service | Testers upgrading from 0.3.x (entity replacement, one-way migration) | medium | mitigate | The RC header tells testers to make a backup or snapshot first and names the restore as the way back. The minimum HA 2026.11.0 is stated, and HACS shows the RC only with pre-releases enabled. |
| T-261118-nnf-06 | Tampering | Local hassfest container | low | mitigate | `make hassfest` uses the digest-pinned image with a read-only mount and `--rm`. The Task 1 gate fails if any container or volume is left over. |
| T-261118-nnf-SC | Tampering | `uv run --with awesomeversion` | low | accept | awesomeversion 25.8.0 is already locked in uv.lock and in .github/requirements-min-ha.txt as a Home Assistant dependency. No new package enters the project, and the uv.lock one-line gate proves it. |
</threat_model>

<verification>
Run from the repo root on the final tree, after the task commits:
- `python3 scripts/check_release_tag.py v1.0.0-rc1` -> exit 0, `tag v1.0.0-rc1 matches manifest.json version 1.0.0-rc1`
- AwesomeVersion assertion (Task 1 verify) -> `awesomeversion ok 1.0.0-rc1 SEMVER`
- `make hassfest` -> `Invalid integrations: 0`; `docker ps -aq` and `docker volume ls -q` are the same before and after
- `uv run pytest -q tests` -> all pass (1192 at HEAD), coverage >= 99 %
- `uv run ruff check custom_components tests`, `uv run ruff format --check custom_components tests`,
  `uv run mypy --strict custom_components/traefik_proxy` -> clean
- `make pre-commit` -> every hook Passed; `make test-min-ha` -> green on HA 2026.11.0; `make hassfest-sanity` -> passed
- `git diff --name-only 8a447c2 HEAD` -> exactly manifest.json, pyproject.toml, uv.lock, CHANGELOG.md and the rc1
  release notes
- `.planning/config.json` / `.planning/state.json` are untouched; no tag; no push
</verification>

<success_criteria>
- The user can push, tag `v1.0.0-rc1` and publish a GitHub pre-release without any further file change. The release
  check passes, and hassfest and the HACS version parsing accept the version.
- Testers find the backup warning, the HACS pre-release install steps and the feedback channel at the top of the release
  notes.
- HACS will offer 1.0.0 as an update to 1.0.0-rc1 (AwesomeVersion order proven).
- Every repository gate is green, and the commits are atomic with explicit paths.
</success_criteria>

<output>
Create `.planning/quick/261118-nnf-prepare-release-candidate-1-0-0-rc1-vers/261118-nnf-SUMMARY.md` when done.
</output>
