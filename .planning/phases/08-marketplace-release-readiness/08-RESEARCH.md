# Phase 8: Marketplace + release readiness - Research

**Researched:** 2026-11-15
**Domain:** HA custom-integration release engineering (hassfest, `hacs/action`, GitHub Actions pinning, brand assets, throwaway HA visual check, Traefik rule redaction)
**Confidence:** HIGH (every core answer was verified by running it locally in throwaway containers or by reading the upstream source; the remaining assumptions are listed in the Assumptions Log)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### Release identity (REL-01, I4/I5)
- **D-01:** `manifest.json` gets `"version": "1.0.0"` and
  `"categories": ["computers_network.monitoring"]` (M6), keys in hassfest order
  (`domain`, `name`, then alphabetical). `hacs.json` keeps
  `"homeassistant": "2026.11.0"`. `pyproject.toml` `version` stays `1.0.0`
  (already set); project `name` becomes `homeassistant-traefik-proxy-integration`.
- **D-02:** Tag scheme stays `v<version>` (`v1.0.0`) per I4/I5. The release
  workflow strips one leading `v` from the tag and fails when the rest differs
  from `manifest.json` `version`.

### Brand (REL-02, M23, research §3)
- **D-03:** The Traefik mark stays. `brand/icon.png` (256×256) and
  `brand/icon@2x.png` (512×512) are re-exported from the vector source:
  trimmed (no padding), centred on a square transparent canvas, PNG,
  interlaced/compressed. `brand/logo.png` / `brand/logo@2x.png` are added in
  the brand's landscape aspect ratio (shortest side 128–256 px, `@2x` 256–512 px);
  if no landscape Traefik logo with a usable licence/source can be found, ship
  only the icon (research §3: "if the brand logo is square, ship only the icon")
  and record that as a worker decision. `brand/icon.svg` moves to
  `docs/icon.svg` (SVG is never served). README carries a trademark note
  ("Traefik is a trademark of Traefik Labs; this project is not affiliated…").
  Tools available locally: ImageMagick (`magick`), `rsvg-convert`.
- **D-04:** "Local brand serving confirmed for HA 2026.11.0" = in the throwaway
  HA 2026.11.0 container with the integration mounted, the brands proxy
  endpoint serves our local `icon.png` and `logo.png` (HTTP 200, PNG bytes
  equal to the shipped file). Evidence goes into the visual-check report.

### Docs (REL-03, DOCS-02, DOCS-04, H-01/H-02)
- **D-05:** README.md is rewritten in English: Marketplace/My-link badge
  (`hacs_repository` redirect for owner `akentner`, repository
  `homeassistant-traefik-proxy-integration`, category `integration`),
  prerequisites incl. enabling the Traefik API and protecting it with
  basicAuth (and bearer via a forward-auth/plugin note only if the code
  supports it), install / removal, every config + options field (matching
  `config_flow.py` and `const.py`), entity table generated from the code
  (platforms, translation keys, states, attributes, enabled/disabled default),
  data update cadence (main cycle, cert cycle, version check), example
  automations (router down, cert expiring), troubleshooting (incl.
  diagnostics download), known limitations, FAQ on out-of-scope features
  (DOCS-04: config-file edits, ACME in HA, Traefik v1, service actions/reload,
  …), trademark note. No reload service/button, no private hostnames or
  aliases (grep gate for the user's host names from the global CLAUDE.md:
  `haos-op3050-1`, `lxc-haos-104`, `hassio-n2plus`, and Tailscale names).
- **D-06:** `CHANGELOG.md` follows Keep a Changelog, covers 0.1.0–1.0.0 (tags
  `v0.1.0`…`v0.3.0` exist; dates from `git log -1 --format=%as <tag>`), and
  puts **Breaking changes / Required actions** at the top of 1.0.0 (minimum HA
  2026.11.0, YAML setup removed (W72), router/service entities replaced by
  ENUM sensors with new entity IDs (M13; disabled ones keep their old object
  id), reload button/service removed → "Refresh now" button (M12), auth
  selection + migration (M15), unique_id `host:port` (M21), etc.). 1.0.0 content
  is assembled from every Phase 4–7 SUMMARY "User-visible changes" section plus
  these explicitly carried items: W23 (`homeassistant.update_entity` on a cert
  entity triggers a cert refresh), W47 (host not covered by the API ⇒ immediate
  `not_found` problem; a pending ACME order shows a problem for up to 6 h or
  until "Refresh now"), Phase 6 notes (wildcard SAN covers exactly one label —
  `a.b.example.com` vs `*.example.com` ⇒ `san_mismatch`; uncovered hosts ⇒
  `not_found` also before Traefik 3.7; cert entities unavailable until the
  first cert cycle; a failed cert cycle is logged once as ERROR).
- **D-07:** CLAUDE.md is regenerated from its GSD sources, not hand-edited
  inside the markers: fix `.planning/research/STACK.md` (domain
  `traefik_proxy`, path `custom_components/traefik_proxy`, no
  `POST /api/http/routers/refresh` / reload service / `services.yaml`, min HA
  2026.11.0, `pytest-homeassistant`, developer-doc links →
  `contributors.home-assistant.io`), then regenerate the CLAUDE.md sections
  with the GSD tool (planner/researcher to find the exact `gsd-tools`
  verb); hand-edit only if no generator exists, and keep the markers.
  The skill directory `.claude/skills/spike-findings-homeassistant-traefik-integration`
  is renamed (`git mv`) to `spike-findings-homeassistant-traefik-proxy-integration`
  and its `SKILL.md` `name:` and internal paths updated, so the existing
  skill-routing marker in CLAUDE.md resolves.
- **D-08:** Planning-doc housekeeping: REQUIREMENTS ENT-09 wording "HA 2026.3
  API" → 2026.11 (`config_entry_id`-bound repair), the Probatio out-of-scope row
  reflects `import probatio as vol` (Phase 7); stale dispositions closed with a
  pointer (Phase 4 WR-03 fixed by Phase 7 M5); every open item in
  `04/05/07 deferred-items.md` marked resolved with the resolving commit or
  explicitly disposed.

### Tooling (REL-04, WR-04, IN-07, H-03/H-04/H-09/H-10/H-12)
- **D-09:** `.pre-commit-config.yaml`: `default_language_version` python3.14,
  every `files:` regex targets `custom_components/traefik_proxy`; hooks
  actually run (`pre-commit run --all-files` passes, executed via
  `uvx pre-commit` / `uv tool run`). `scripts/hassfest_checks.py`
  `strings-shape` accepts the valid top-level `entity` key (forbidden set only
  `reauth`/`reconfigure` or whatever is genuinely invalid) and exits 0 on HEAD;
  `scripts/pre-commit` (standalone hook) uses the same paths.
- **D-10:** `pyproject.toml` addopts measure `--cov=custom_components.traefik_proxy`;
  `[tool.coverage.report] fail_under` = measured total coverage rounded down to
  an integer (floor), but not below 90; CI's test job fails below it.
  `filterwarnings` turns `SyntaxWarning` into an error so the
  `tests/test_binary_sensor.py:35` class of bug cannot return.
- **D-11:** "No real multi-second sleeps in tests": every `asyncio.sleep` /
  `time.sleep` ≥ 1 s in `tests/` is replaced by frozen/advanced time
  (`async_fire_time_changed`, freezer) — a guard test fails on a literal sleep
  ≥ 1 s. Socket wall-clock guards (W59 `tls_server` 60-s limit) are not sleeps.
- **D-12:** Makefile targets mirror CI exactly (same commands for lint,
  typecheck, test with coverage gate, minimum-HA test), plus Docker targets for
  the local validators (`make hassfest`, `make hacs-action` or equivalent),
  each removing its container (`docker run --rm`).

### CI + release workflow (REL-05, DIST-04, WR-05/06/07, M9, M24)
- **D-13:** `validate.yml` triggers: `push`, `pull_request`, nightly
  `schedule`, `workflow_dispatch`. Every job has `timeout-minutes` (15 unless a
  job needs more). Every action is pinned to a **full commit SHA** with a
  trailing `# vX.Y.Z` comment (incl. `actions/checkout`, `astral-sh/setup-uv`,
  `home-assistant/actions/hassfest`, `hacs/action`). `.github/dependabot.yml`
  bumps `github-actions` weekly.
- **D-14:** `test-min-ha` installs a **locked** dependency set: a committed
  lock (e.g. `.github/requirements-min-ha.txt` from `uv pip compile` for Python
  3.14 pinning `pytest-homeassistant==2026.11.0`) installed with
  `uv pip sync`; a Makefile target regenerates it. Alternative only if the
  research shows it is cleaner: `uv sync --locked` with a dependency-group
  override.
- **D-15:** New `.github/workflows/release.yml`: runs on `release: published`
  and on pushed tags `v*`; one job compares tag (minus leading `v`) with
  `manifest.json` version and fails on mismatch; pinned actions, timeout. It
  creates nothing (no assets, no zip — `zip_release` is not used).

### Shipped-code hygiene (REL-06, A-19, H-07/H-08, M22)
- **D-16:** Grep for `CONTEXT.md`, `PITFALLS`, `D-[0-9]`, `BLOCKER`,
  `Phase [0-9]`, `.planning/`, `.claude/`, `spike` (case-insensitive) in
  `custom_components/` returns nothing; the Phase 7 "new lines only" M22 gate
  becomes a full-tree guard test in `tests/test_baseline_guards.py` (the ~25
  legacy references are reworded, not just deleted — keep the technical
  reason). Developer-doc links in shipped code and docs point at
  `contributors.home-assistant.io`.

### Remaining code findings (carried, all with regression tests where behaviour changes)
- **D-17 (M40):** Diagnostics redact secret-bearing router `rule` values:
  argument values of `Header`, `HeaderRegexp`, `Headers`, `HeadersRegexp`,
  `Query`, `QueryRegexp` (v2 and v3 matcher names) become `**REDACTED**`
  while the matcher name and the header/query **key** stay readable; `Host`,
  `PathPrefix`, `Path`, `Method`, `ClientIP` etc. stay. Applied to router rules
  everywhere they appear in the diagnostics snapshot. Unparseable rule ⇒
  whole rule redacted (fail closed). Alternative (rejected): drop rules
  entirely — they are the most useful field for support.
- **D-18 (Phase 7 IN-03):** `cert_coordinator.py` chains
  `from _logged_cause(err)` like the main coordinator.
- **D-19 (Phase 7 IN-04/IN-05, necessity):** keep the branches, document them
  in one comment each as deliberate defence against hand-edited
  `core.config_entries` / out-of-band values (no behaviour change before 1.0.0).
- **D-20 (Phase 6 IN-03/IN-04):** probe mode resolves the connect host once per
  cert cycle instead of once per probe (SNI unchanged); the small races in the
  socket tests are fixed (Phase 6 `06-REVIEW.md` details). Plus the dead
  `await server.wait_closed()` in the `tls_server` teardown (07 deferred-items).
- **D-21 (Phase 5 IN-01/IN-03/IN-06/IN-07):** IN-01 drop the redundant cert-host
  lowercasing where the factory already normalises (tests prove it); IN-03
  remove the unused `exceptions.cert_unavailable` translation (en + de) if
  still unused; IN-06 the migration repair text (en + de) says enabled router
  sensors get new entity IDs while disabled/hidden ones keep their old ID;
  IN-07 the DEVICE→USER migration step only acts on a legacy device that is
  actually disabled (regression test).
- **D-22 (Phase 4 IN-11..IN-14 + fixture doc):** as written in the ROADMAP
  Carry-over line (close IN-11 as resolved if the cert-entity rewrite removed
  the alias; IN-12 comment + three timing tests; IN-13
  `RAWDATA_PROBE_INTERVAL = timedelta(hours=1)`, `_interval_elapsed(since,
  interval)`, `_probe_armed_at` → `_probe_clock`; IN-14 debug log on committing
  the paginated switch; capture-harness note on certificate-bound fixture
  byte-stability). Optional cheap extra: a regression test for T-06-13 (no
  per-host dict leak) — include it.
- **D-23:** Phase 4 deferred `invalid_url` text: close as resolved if the
  Phase 7 auth selector + current text already covers userinfo URLs, else add
  the hint (en + de).

### Validation in throwaway Docker (REL-07, M35)
- **D-24:** Local hassfest: run the same hassfest the CI action runs, in a
  `docker run --rm` container against the working tree; 0 errors required.
  Local `hacs/action` (category `integration`, **no** `ignore`): run its image
  locally. Checks that can only be evaluated against GitHub (description,
  topics, issues, license, archived, releases, brands from the remote tree)
  must not be satisfied by pushing anything — no fork, no temporary repo, no
  push. If the action cannot validate an unpushed tree, run every validator
  that works offline/locally, evaluate the GitHub-only ones against the
  current public repository state, and record precisely which checks the
  post-push CI run must confirm (research to determine the mechanics).
- **D-25 (M35):** Visual check in a throwaway **HA 2026.11.0** container plus a
  throwaway Traefik v3 (the `tests/traefik/compose.yaml` setup can be reused)
  with the integration mounted read-only: onboarding and the config flow driven
  through the HA REST/WebSocket API, screenshots taken headless (Playwright via
  `uv run --with playwright`) for **de and en**: auth selection with
  conditional fields (none/basic/bearer), options form incl. units and the
  grace-period / per-item fields, `insecure_credentials` repair text, device
  tree (main device + Router/Service/Certificate sub-devices), entity states
  and icons, the 0.3.0 migration repair text (set up a 1.1/0.3.0-shaped entry
  if feasible), "Refresh now" button, brand icon/logo (D-04). Findings that
  need code changes are fixed in the same phase (own commit + test); cosmetic
  issues without code cause are listed. Report `08-VISUAL-CHECK.md` plus
  downscaled screenshots under the phase directory (each < 500 KB because of
  the `check-added-large-files` hook, total ≤ ~5 MB). All containers, networks
  and volumes are removed afterwards (`docker ps -a` / `docker network ls`
  show none of them).

### Drafts for the user / manager (REL-07, REL-08, M8, M41)
- **D-26:** Drafts live only in the phase directory, never in shipped files:
  `08-RELEASE-NOTES-v1.0.0.md` (required user actions first, then highlights,
  then full change list referencing CHANGELOG), `08-HACS-DEFAULT-PR.md`
  (fork `hacs/default`, alphabetical insertion into `integration`, template
  fields with placeholders for the release / HACS-action / hassfest run links,
  "from a personal account, no review requests"), `08-DRAFT-PR.md` (title and
  body for the Draft PR `feat/marketplace-polish` → `main`, M41, incl. the
  `.planning/` note and the user actions list).
- **D-27 (REL-08):** The phase ends **push-ready**, not pushed: clean working
  tree, all gates green (tests, ruff, ruff format, mypy --strict, coverage
  gate, pre-commit, local hassfest, local hacs/action), `git tag --list`
  unchanged (`v0.1.0`…`v0.3.0` only), no new remote refs. The push and the
  Draft PR are done by the manager after phase verification; the verifier
  treats REL-08's push/PR clause as a manager action (M41), not a gap.

### Claude's Discretion
- Plan split and wave order (suggested: code findings ∥ tooling/CI ∥
  metadata/brand → docs → Docker validation + visual check → drafts and
  push-readiness last, because README/CHANGELOG/drafts must describe the
  final state).
- Exact README wording/structure, CHANGELOG grouping below the breaking-changes
  block, screenshot set beyond the list in D-25.
- Whether the minimum-HA lock is a requirements file or a uv group (D-14).

### Deferred Ideas (OUT OF SCOPE)
- Stale-bot `issues.yaml` workflow (pattern from the user's other integrations) — not required by the Marketplace; post-1.0.
- `dark_icon.png` — not needed (teal mark reads on dark, research §3).
- Submitting to `home-assistant/brands` — not needed for custom integrations.
- Creating the tag/release/`hacs/default` PR and pushing — user/manager (U1, M8, M41).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REL-01 | manifest `categories: ["computers_network.monitoring"]` (sorted keys), version `1.0.0`; `hacs.json` keeps `homeassistant: 2026.11.0` | Q10: both validators run against the target manifest; hassfest errors on unsorted keys, hacs fails on unknown categories (§ Findings F1, F2, F10) |
| REL-02 | Brand re-export, logo, `icon.svg` → `docs/`, local brand serving on 2026.11.0, trademark note | Q6 brands proxy endpoint + byte-equality recipe (F6); Q8 logo source + verified export pipeline (F8) |
| REL-03 | README rewrite, no private hostnames | Facts for README: default scan interval 15 s, option ranges, translation keys (F11); current README line 28/32 contain `haos-op3050-1` |
| REL-04 | pre-commit 3.14 + paths, pyproject name/coverage/`fail_under`, Makefile = CI, no SyntaxWarning, no real sleeps | Coverage measured 99 % (F4); SyntaxWarning-gate pitfall (P3); ruff version drift (P5); `strings-shape` allowed keys (F10) |
| REL-05 | CI triggers, timeouts, SHA pins, min-HA job | Pins (F3), lock procedure (F4), workflow skeletons (Code Examples) |
| REL-06 | No planning refs in shipped code; CLAUDE.md regenerated; doc links | `generate-claude-md` mechanics (F9); grep result: 8 lines, all in `const.py` + `__init__.py:53` |
| REL-07 | Local hassfest + `hacs/action` pass; drafts | F1 exact hassfest command; F2 local `hacs/action` overlay harness (verified pass/fail); post-push check list |
| REL-08 | Push-ready, no push | Nothing pushed during research; `git ls-remote` shows only `main`, `renovate/configure`, `v0.1.0`..`v0.3.0` |
| DIST-04 | hassfest, HACS action, pytest workflows; release workflow tag == manifest | F1–F3, release.yml skeleton |
| DOCS-02 | CHANGELOG | Tag list verified: `v0.1.0 v0.1.1 v0.1.2 v0.1.3 v0.1.4 v0.1.6 v0.2.0 v0.2.1 v0.3.0` (no `v0.1.5`) |
| DOCS-04 | FAQ on out-of-scope features | (content task; no research unknowns) |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Python 3.14+, Home Assistant Core min **2026.11.0** (project CLAUDE.md still says 2026.3.x — it is stale and is regenerated in this phase), `aiohttp` only via `async_get_clientsession`, HACS-compatible, `requirements: []`, no `quality_scale` key.
- No external services, no telemetry; API tokens never logged; self-signed certificates via user option.
- Global CLAUDE.md: code, comments, commits in English; user-facing chat in German; Python via `uv run --with <pkg>`, never global pip; no plaintext secrets in files; the assistant never pushes; Fish is the primary shell (Makefile recipes run in `/bin/sh` anyway).
- GSD workflow enforcement: edits go through GSD commands; `.planning/` state must be respected.
- Herdr rule (manager concern): workers run in named herdr panes.

## Summary

All ten research questions were answered by running the real tools locally. **hassfest** is a plain `docker run` of `ghcr.io/home-assistant/hassfest` (`:latest`, now 2026.11.1) with the repo mounted at `/github/workspace`; it passes on HEAD and on the D-01 target manifest, errors on unsorted manifest keys and only warns on an unknown category. **`hacs/action`** never reads the checkout: it fetches the tree from the GitHub API and file contents from `raw.githubusercontent.com` at a ref. So an unpushed tree cannot be validated by the stock image. A ~70-line overlay script, run with `--entrypoint python3` inside the official image, swaps three methods so that tree and file content come from the local working tree. GitHub metadata (description, topics, issues, license, archived) still comes from the live API. All 10 checks passed on the working tree and on the D-01 target, and the overlay demonstrably fails on a local bogus category and on a missing `icon.png`.

The **minimum-HA lock** works: `uv pip compile --python-version 3.14.2` (not `3.14`) produces a 123-package, 248 KB hashed lock. `uv pip sync --require-hashes` installs it, and 1056 tests pass on it. The **visual check** recipe was executed end to end on HA 2026.11.0. It covers REST onboarding, the REST config flow against Traefik v3 from the compose harness, the brands proxy (HTTP 200, byte-equal), Playwright screenshots in German with the token injected via `localStorage.hassTokens`, and the real **0.3.0 → 1.0 migration**: v0.3.0 from `git archive` is set up first, then the mount is swapped on the same config volume, which raises `entities_migrated` with `removed_count` 101. Everything was cleaned up afterwards.

**Primary recommendation:** use the verified commands and scripts in this document as-is: `make hassfest`, the `hacs-action` overlay harness (`scripts/hacs_action_local.py`), `.github/requirements-min-ha.txt` + `uv pip sync`, the SHA pins in F3, the tokenizer-based rule redactor (also applied to router `errors` and to the router sensor's `rule` attribute — see P1), and the visual-check scripts.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Manifest/brand metadata | Repo (shipped integration folder) | HA core brands proxy | Core serves `custom_components/<domain>/brand/*.png`; the Marketplace reads the release |
| Rule redaction (M40) | Integration backend (`diagnostics.py` + a pure helper module) | Entity attributes (`sensor.py`) | Diagnostics and state attributes are both server-side outputs; the helper is pure Python like `rules.py` |
| Validators | CI (GitHub Actions) | Local Docker (Makefile) | Catalog needs CI run links; local runs are pre-push evidence |
| Min-HA test | CI job + committed lock | Makefile regen target | Reproducible install needs the lock in git |
| Visual check | Throwaway Docker (HA + Traefik) | Headless browser (Playwright) | No real HA instance (U2) |
| CLAUDE.md | GSD generator (`gsd-tools`) | Hand-maintained `skill-routing` block | Generator only owns 6 sections |

## Standard Stack

### Tools (no runtime dependency changes; `manifest.json` `requirements` stays `[]`)

| Tool | Version / ref | Purpose | Source |
|------|---------------|---------|--------|
| `ghcr.io/home-assistant/hassfest` | `:latest` = **2026.11.1**, index digest `sha256:da6522993280166fe072704989a2b4c33e639e8ceb69c8ab6ad7ec5045c1a1e3` (local `2026.11.0` was `sha256:f9ac52cf…`) | The image the hassfest action runs | [VERIFIED: GHCR manifest API + `docker run`] |
| `ghcr.io/hacs/action` | `:main`, digest `sha256:187499a09c5d41f9f0d42ff80d203ed87b974c028290140913b61e005fb0aab2`, created 2026-10-20, Python 3.14.8, bundles `homeassistant 2026.10.2`, `aiogithubapi 26.0.0` | The image `hacs/action` runs | [VERIFIED: `docker image inspect`, `pip list` in image] |
| `ghcr.io/home-assistant/home-assistant` | `2026.11.0`, index digest `sha256:c6c1ca9931036bf3a2c4cc088d8db25dfea3b33935a5ecc83c40349462e2f69e` | Throwaway visual-check instance | [VERIFIED: GHCR + pull + run] |
| Traefik harness | `traefik:v3.7.19@sha256:b7b1b31e…` from `tests/traefik/compose.yaml` | Throwaway Traefik v3 | [VERIFIED: compose up] |
| `uv` | 0.13.4 local | lock compile / sync | [VERIFIED] |
| Playwright (Python) | 1.65.2 on PyPI (1.64.1 cached locally); Chromium headless shell build 1254 (`158.0.8127.18`) in `~/.cache/ms-playwright` | Screenshots | [VERIFIED: launched] |
| `rsvg-convert`, `magick` | `/usr/bin` | Brand export | [VERIFIED] |
| `pre-commit` | 4.7.0 on PyPI, run via `uvx pre-commit` | Hooks | [VERIFIED: PyPI JSON] |

### Action pins (D-13) — resolved read-only on 2026-11-15

| Action | Pin (full SHA) | Comment to write | Notes |
|--------|----------------|------------------|-------|
| `actions/checkout` | `3d3c42e5aac5ba805825da76410c181273ba90b1` | `# v7.0.1` | Latest release v7.0.1 (2026-07-20); lightweight tag = commit. v7 changes: ESM, blocks fork checkout for `pull_request_target`/`workflow_run` (not used here). Current workflow uses `@v6` (`d23441a…`). [VERIFIED: `gh api` + `git ls-remote`] |
| `astral-sh/setup-uv` | `68559e99cc807c1eb7e9238fd43a15bba460eec2` | `# v10.3.3` | Latest v10.3.3 (2026-10-28). Since v8 **no major/minor tags** (`@v8` impossible); v9 `prune-cache` default false; v10 disables the cache by default for `pull_request_target`, `workflow_run`, `release` events. Current workflow `@v5` works but is unpinned. [VERIFIED: release notes] |
| `home-assistant/actions/hassfest` | `86d4564712fa02543c808e3a693dd04f9d3f8361` | `# master (2026-10-26)` | Only tag is `1.0.0` (2020, obsolete Dockerfile layout). `hassfest/action.yml` blob `4f46ae0` unchanged since 2024-08-28. No `vX.Y.Z` exists → the `# vX.Y.Z` comment rule of D-13 cannot be met literally. [VERIFIED] |
| `hacs/action` | `d556e736723344f83838d08488c983a15381059a` | `# 22.5.0` | Tag 22.5.0 (2022-05-28); its `action.yml` is **byte-identical** to `main` (`1ebf01c408f29afcb6406bd431bc98fd8cbb15aa`, 2026-06-08), both run `docker://ghcr.io/hacs/action:main`. [VERIFIED: `diff` empty] |

**Pinning caveat:** pinning the hassfest and hacs actions by SHA does **not** pin what runs. Both pull a floating image (`hassfest:latest`, `hacs/action:main`). That is acceptable and matches what the catalog reviewers run. [VERIFIED: both action.yml files]

## Package Legitimacy Audit

No package is added to the integration or to `pyproject.toml`. The phase uses these **transient** tools (`uv run --with`, `uvx`) and one committed lock of an already-approved dev package.

| Package | Registry | Seam verdict | Source repo | Disposition |
|---------|----------|--------------|-------------|-------------|
| `playwright` | PyPI | SUS (unknown-age, unknown-downloads, no-repository — seam could not fetch signals) | Microsoft (PyPI metadata lists no Source URL) | Transient only (`uv run --with playwright`, never in pyproject). Planner: `checkpoint:human-verify` before first install **or** accept as manager decision like M38 |
| `pre-commit` | PyPI | SUS (unknown-downloads) | github.com/pre-commit/pre-commit | Transient (`uvx pre-commit`) — same handling |
| `pytest-homeassistant` | PyPI | SUS (too-new, no-repository) | home-assistant/core (provenance checked by manager, M38) | Already approved (M38); lock pins `==2026.11.0` |
| `pytest-cov` | PyPI | SUS (unknown-downloads, no-repository) | pytest-dev | Already a dev dependency |

**Packages removed due to [SLOP]:** none. **Flagged [SUS]:** all four, because the seam returned no registry signals. They are well-known packages; follow the M38 precedent (manager decision) or add one `checkpoint:human-verify` before the visual-check plan installs Playwright.

## Findings (the ten questions)

### F1 — Local hassfest = exactly what the action runs [VERIFIED]
`home-assistant/actions/hassfest/action.yml` is a composite action whose only real step is:
`docker run --rm -v ${{ github.workspace }}://github/workspace ghcr.io/home-assistant/hassfest`.
The image entrypoint `/usr/src/homeassistant/script/hassfest/docker/entrypoint.sh` discovers `custom_components/*/manifest.json` (depth 2) plus a root `manifest.json`, then runs `python3 -m script.hassfest --action validate --integration-path …`.

Local equivalent (run from repo root):
```bash
docker run --rm --pull always -v "$PWD":/github/workspace ghcr.io/home-assistant/hassfest
```
Results on 2026-11-15 with 2026.11.1: HEAD passes (`Integrations: 1`, `Invalid integrations: 0`). The D-01 manifest also passes. A bogus category gives only `[WARNING] [MANIFEST] Unknown category …` (exit 0). Unsorted keys give `[ERROR] [MANIFEST] Manifest keys are not sorted correctly: domain, name, then alphabetical order` (exit ≠ 0). hassfest has **no brand validator**, so `brand/icon.svg` and the logo files are irrelevant to it. `computers_network.monitoring` exists in core `homeassistant/strings.json` (`integration_category.computers_network.subcategory.monitoring.name = Monitoring`).

### F2 — `hacs/action` against an unpushed tree [VERIFIED by running it]
**Mechanics (source: hacs/integration `action/action.py`, `repositories/base.py`, `repositories/integration.py`):**
- The action is `runs: using: docker, image: docker://ghcr.io/hacs/action:main`, with entrypoint `python3 /hacs/action.py`.
- The repository comes from `INPUT_REPOSITORY`/`REPOSITORY`, else `GITHUB_REPOSITORY`. The ref comes from the PR head ref, else the push `ref`, else `REPOSITORY_REF`, else the default branch.
- The token comes **only from `INPUT_GITHUB_TOKEN`** and is required ("No GitHub token found"). The workflow's `env: GITHUB_TOKEN` is unused; the token arrives through the input default `${{ github.token }}`.
- Tree: `githubapi.repos.git.get_tree(tree_sha=ref, recursive)`. `hacs.json` and `manifest.json` come from `repos.contents.get(..., ref)`. Other files come from `https://raw.githubusercontent.com/{repo}/{ref}/…`. **The local workspace is never read** (except for the `hacs/default` repo itself).
- A private repo errors immediately.
- Validators for category `integration` (10): `archived`, `brands`, `description`, `hacsjson`, `information`, `integration_categories`, `integration_manifest`, `issues`, `license`, `topics`. (`images` is only for plugin/theme.) There is **no release check in the action**; a release is a catalog requirement only.
- `description`, `topics`, `issues`, `license`, `archived` have `allow_fork = False`. They are **silently skipped** when `INPUT_REPOSITORY` is unset and `GITHUB_REPOSITORY` ≠ the repo ("All (5) checks passed"). Always set both.

**Best achievable local procedure (no push):** a local-overlay harness run inside the official image. It patches `HacsRepository.get_tree`, `HacsRepository.async_get_hacs_json`, `HacsIntegrationRepository.async_get_integration_manifest` and `HacsBase.async_download_file` (only for `raw.githubusercontent.com/<repo>/` URLs) so tree and files come from the working tree, restricted to `git ls-files -co --exclude-standard`. GitHub metadata still comes from the live API with a read-only token.
- Working tree today: **All (10) checks passed** (warning: no categories).
- Negative control (local copy with `computers_network.bogus` and no `icon.png`): `2/10 checks failed` (`integration_categories`, `brands`). This proves the overlay reads local content.
- D-01 target (categories + `1.0.0`): **All (10) checks passed**, no warning.
- The unmodified stock image against public `main`: All (10) passed (categories warning).

**Checks the post-push CI run must still confirm** (the overlay emulates them but cannot prove them for the pushed ref): (1) `brands` and `information` against the **pushed tree** at the PR head ref; (2) `hacsjson`, `integration_manifest`, `integration_categories` read via the API and raw URLs at that ref (encoding/LFS/case issues would only show there); (3) the job runs with the CI `github.token` under the workflow's `permissions`. The metadata checks (`description`, `topics`, `issues`, `license` MIT, `archived` false) are already green on the live repo [VERIFIED: `gh api repos/akentner/homeassistant-traefik-proxy-integration` → `archived:false, has_issues:true, license:MIT, private:false, topics:[hacs, hass, home-assistant, integration, traefik]`, description set]. A **GitHub release** for 1.0.0 is a catalog requirement checked by humans, not by the action.

Token handling: `INPUT_GITHUB_TOKEN="$(gh auth token)" docker run -e INPUT_GITHUB_TOKEN …` passes the token by name. It never appears in argv or logs. Any token that can read public repos works; the user's `gh` token is logged in via keyring.

### F3 — Pins: see the table in Standard Stack [VERIFIED]

### F4 — Minimum-HA locked install (D-14) [VERIFIED]
- `uv pip compile requirements-min-ha.in --python-version 3.14 …` **fails**: `pytest-homeassistant==2026.11.0 depends on Python>=3.14.2`. Use `--python-version 3.14.2`.
- The working command (inputs: `pytest-homeassistant==2026.11.0`, `pytest-cov>=7.0.0`):
  `UV_HTTP_TIMEOUT=300 uv pip compile .github/requirements-min-ha.in --python-version 3.14.2 --python-platform x86_64-manylinux_2_28 --generate-hashes -o .github/requirements-min-ha.txt`
  It produces 123 pinned packages, 3210 lines, **248 KB** (under the 500 KB hook limit). Key pins: `homeassistant==2026.11.0`, `pytest-homeassistant==2026.11.0`, `pytest==9.0.3`, `pytest-asyncio==1.4.0`, `pytest-cov==7.1.0`, `coverage==7.17.3`, `probatio==0.13.0`, `respx==0.23.1` (via pytest-homeassistant).
- The first attempt failed with `Failed to fetch: https://pypi.org/simple/regex/ … operation timed out`. Set `UV_HTTP_TIMEOUT=300`; the compile then takes minutes.
- `uv venv --python 3.14 venv && uv pip sync --python venv/bin/python --require-hashes .github/requirements-min-ha.txt` → `Python 3.14.2`, then `venv/bin/python -m pytest -q tests` → **1056 passed** with the pyproject addopts (the coverage warnings came from the stale `--cov=custom_components.traefik`).
- `-p no:respx`: respx stays installed (transitive), but the full suite also passes **without** `-p no:respx` on this lock (1056 passed with `-o addopts=""`). Recommendation: keep `-p no:respx` in pyproject `addopts` (single source) and run the min-HA job with plain `python -m pytest -q tests`, i.e. drop the `-o addopts="-p no:respx"` override. The job then also enforces `fail_under`, which is the same suite and therefore fine.
- `aioresponses` (dev group) is **not imported by any test** (grep: no hits in `tests/`), so it is a dead dev dependency. The lock does not need it.
- **Use the requirements-file approach.** A `uv sync --locked` group override would need two conflicting HA pins in one `uv.lock` [ASSUMED: needs `[tool.uv] conflicts`]. That is more machinery for no gain.
- Coverage measured on the correct package (D-10): `TOTAL 2001 15 99%` (line, about 99.25 %); with `--cov-branch`, 99 % (2447 items, 27 missed) [VERIFIED: run]. So `fail_under = 99` (line coverage, matching today's addopts without `--cov-branch`).

### F5 — Throwaway HA 2026.11.0 visual check: verified recipe
Everything below was executed on 2026-11-15 and torn down afterwards (baseline `docker ps -a` / `docker network ls` restored).

1. Traefik: `docker compose -f tests/traefik/compose.yaml up -d whoami traefik-v3` creates network **`traefik-harness_default`**. API: `http://traefik-v3:8080`, basicAuth `capture` / `harness-only-not-a-secret` (harness-only, from `capture.py`). `dynamic/bulk.yml` is present, so 120+ routers exist.
2. HA: `docker volume create ha-visual-08-config`, then
   `docker run -d --name ha-visual-08 --network traefik-harness_default -p 127.0.0.1:18123:8123 -e TZ=Europe/Berlin -v ha-visual-08-config:/config -v "$PWD/custom_components/traefik_proxy":/config/custom_components/traefik_proxy:ro ghcr.io/home-assistant/home-assistant:2026.11.0`.
   Use a **named volume**, not a bind mount: HA runs as root and would leave root-owned files in the user's tree. `/api/onboarding` answers 200 within ~6 s.
3. Onboarding (REST, verified schema from `onboarding/views.py` in the image): `POST /api/onboarding/users {client_id, name, username, password, language}` → `auth_code`; `POST /auth/token` (form: `grant_type=authorization_code, code, client_id`) → `access_token` (expires_in 1800), `refresh_token`; then `POST /api/onboarding/core_config {}`, `POST /api/onboarding/analytics {}`, `POST /api/onboarding/integration {client_id, redirect_uri}`, all 200. `client_id` = `http://127.0.0.1:18123/`. Keep tokens in a 0600 scratch file and never print them.
4. Config flow (REST): `POST /api/config/config_entries/flow {"handler":"traefik_proxy"}` returns the form. The schema shows `auth_type` select `none|basic|bearer`, and `username`/`password`/`token` carry `"visible": {"field":"auth_type","value":…}`. `POST …/flow/<flow_id> {"url":"http://traefik-v3:8080","verify_ssl":true,"auth_type":"basic","username":"capture","password":"harness-only-not-a-secret"}` → `create_entry`, title `traefik-v3`, 146 entities. Repairs then list `insecure_credentials_<entry_id>` (WS `repairs/list_issues`) plus core's `country_not_configured`. To avoid that noise, set the country, e.g. WS `config/core/update {"country":"DE"}` [ASSUMED command name].
5. Options flow (REST): `POST /api/config/config_entries/options/flow {"handler": "<entry_id>"}` → step `init` with `scan_interval` (s, 15–300, default **15**), `verify_ssl`, `tls_warn_days` (d, 1–90, 14), `per_item_entities` (true), `missing_grace_hours` (h, 1–168, 24). Abort with `DELETE …/options/flow/<id>`. For the **screenshot**, open the options form in the UI (integration page → entry → configure). The UI cannot attach to a REST-created flow.
6. Devices (WS `config/device_registry/list`): `Traefik (traefik-v3)` (entry_type service, `configuration_url http://traefik-v3:8080/dashboard/`) plus `Traefik routers|services|certificates (traefik-v3)` with `via_device_id` = main device. Device page URL: `/config/devices/device/<id>`.
7. Playwright: `uv run --with playwright python3 …` (or `--offline --with playwright==1.64.1` when PyPI is slow; a fresh `uv run --with playwright` took 6:41 min here). Launch with `executable_path=~/.cache/ms-playwright/chromium_headless_shell-1254/chrome-headless-shell-linux64/chrome-headless-shell` if the installed browser build does not match the Python package (otherwise `uv run --with playwright python -m playwright install chromium`). Inject auth with `context.add_init_script("localStorage.setItem('hassTokens', <json>); localStorage.setItem('selectedLanguage', '\"de\"')")`. `hassTokens` = `{access_token, token_type:"Bearer", expires_in, hassUrl, clientId, expires:<epoch ms>, refresh_token}`. **German UI verified** ("Reparaturen", "Traefik-Zugangsdaten werden unverschlüsselt gesendet").
8. Config-flow screenshots: `/config/integrations/dashboard/add?domain=traefik_proxy` first shows a confirm dialog ("Möchtest du Traefik Proxy einrichten?"). Click `get_by_role("button", name="OK")`, then click radios with `page.get_by_text("<label>", exact=True).click()`. `get_by_label` times out on HA radios. Labels: en `Basic auth (username and password)` / `Bearer token`; de `Basic Auth (Benutzername und Passwort)` / `Bearer-Token`. Use viewport ≥ 1280×1200; at 900 px the basic-auth form overflows. Conditional username/password fields appeared after selecting basic [VERIFIED screenshot]. JPEG q75 at 1280×900 is **35–55 KB** per shot, far below 500 KB.
9. **0.3.0 migration repair (verified):** `git archive v0.3.0 custom_components/traefik_proxy | tar -x -C <scratch>` → run a second HA (`ha-visual-08-mig`, port 18124, volume `ha-visual-08-mig`) with that code mounted. The 0.3.0 flow fields are `url`, `api_key`, `verify_ssl`; basicAuth goes through userinfo `http://capture:harness-only-not-a-secret@traefik-v3:8080`. It **loads on HA 2026.11.0** and creates `binary_sensor.traefik_http_router_*` plus `button.traefik_reload`. Then `docker stop/rm` the container and `docker run` the same volume with the **working-tree** mount. After start: entry title `traefik-v3`, repairs `entities_migrated_<entry_id>` (`removed_count: "101"`) and `insecure_credentials_<entry_id>`. No hand-written `.storage` is needed.
10. Cleanup (verified): `docker rm -f ha-visual-08 ha-visual-08-mig; docker compose -f tests/traefik/compose.yaml down -v --remove-orphans; docker volume rm ha-visual-08-config ha-visual-08-mig`, then compare `docker ps -a`, `docker network ls`, `docker volume ls` with the pre-run baseline. The host has unrelated pre-existing containers (`WinBoat`, `boring_nobel`, …) and network `winboat_default` that must not be touched.

### F6 — Brands proxy in HA 2026.11.0 [VERIFIED: core source @2026.11.0 + live run]
- View `BrandsIntegrationView`, URL **`/api/brands/integration/{domain}/{image}`** (also `/api/brands/marketplace/{domain}/{image}` and `/api/brands/hardware/{category}/{image}`).
- `requires_auth = False`, but `_authenticate` accepts an authenticated request (Bearer) **or** `?token=<brands token>` from WS `brands/access_token` (rotates every 30 min, two kept). No auth → **403**; a wrong Bearer → **401** and counts toward the IP ban.
- `ALLOWED_IMAGES` = `icon.png, logo.png, icon@2x.png, logo@2x.png, dark_icon.png, dark_logo.png, dark_icon@2x.png, dark_logo@2x.png`; anything else → 404 (`icon.svg` → 404 verified). Local custom-integration files win (`_serve_from_custom_integration`, if `integration.has_branding` = `"brand" in top-level files`). `?placeholder=no` disables the placeholder on a CDN miss.
- **Fallback chains apply to local files too** (`_read_brand_file` walks `IMAGE_FALLBACKS`: `logo.png → icon.png`; `logo@2x.png → logo.png → icon.png`; `dark_logo.png → dark_icon.png → logo.png → icon.png`). Verified: today `logo.png` returns the **icon bytes** (same sha256 `50b144cb…`). The D-04 evidence must therefore assert `sha256(served logo.png) == sha256(brand/logo.png)` **and** `!= sha256(brand/icon.png)`.
- Evidence command:
  `curl -s -H "Authorization: Bearer $T" "http://127.0.0.1:18123/api/brands/integration/traefik_proxy/logo.png?placeholder=no" | sha256sum` versus `sha256sum custom_components/traefik_proxy/brand/logo.png`. Repeat for `icon.png`, `icon@2x.png`, `logo@2x.png`, and check `content-type: image/png` with `curl -w '%{http_code} %{content_type}'`.

### F7 — Traefik rule grammar (M40 / D-17) [VERIFIED: Traefik source + docs]
- **v3 HTTP matchers** (`pkg/muxer/http/matcher.go` @v3.7.19, `httpFuncs`): `ClientIP(1)`, `Method(1)`, `Host(1)`, `HostRegexp(1)`, `Path(1)`, `PathRegexp(1)`, `PathPrefix(1)`, `Header(2)`, `HeaderRegexp(2)`, `Query(1|2)`, `QueryRegexp(1|2)`. Docs: `Query(`mobile`)` = key without value.
- **v2 syntax** (`matcher_v2.go` @v3.7.19 for `ruleSyntax: v2`, and `pkg/muxer/http/mux.go` @v2.11.33): `Host` and `HostHeader` (variadic), `HostRegexp`, `ClientIP`, `Path`, `PathPrefix`, `Method` (variadic), `Headers(key, value)`, `HeadersRegexp(key, regexp)`, `Query(`k=v`, …)` (variadic `key=value`). v2 has **no** `QueryRegexp`. `ruleSyntax`/`core.defaultRuleSyntax` is deprecated ("will be removed in the next major version"), so a v3 instance can still report v2-syntax rules.
- **Case:** `pkg/rules/parser.go` (v2.11 and v3.7) registers each matcher as exact, `lower`, `UPPER` and `Title(lower)`. `headers(…)`, `HEADERSREGEXP(…)` and `Headerregexp(…)` are valid. **Match names case-insensitively.**
- **Quoting:** "use backticks `` ` `` or escaped double-quotes `\"`"; "Single quotes `'` are not accepted since the values are Go's String Literals". So a double-quoted argument may contain `\"` and other Go escapes; a backtick literal cannot contain a backtick. Operators: `&&`, `||`, `!`, parentheses.
- **Secrets also leak via router `errors`:** Traefik builds errors like `error while parsing rule %s: %w` with the **full rule** (`pkg/muxer/http/mux.go` @v3.7.19 l.83, `pkg/rules/parser.go` l.195/200). A broken rule containing a secret is echoed in `Router.errors`.
- **Where rules surface in this integration:** `models.Router.rule` (models.py:69, set at :326). Diagnostics dumps `dataclasses.asdict(snapshot)` → `snapshot.routers[*].rule` and `snapshot.routers[*].errors`. The **router sensor state attributes** `"rule": router.rule` and `"errors": list(router.errors)` (sensor.py:207-219) go into the state machine and the recorder, which every HA user and history can read. Fixtures today contain only `Host(...)` and `PathPrefix(`/api`)` rules.
- **Approach:** a tokenizer, not one regex (reference implementation in Code Examples, 16/16 cases pass): tokens = whitespace | `&& || ! ( ) ,` | backtick literal | double-quoted literal with `\\.` escapes | identifier. Each identifier must be a known matcher (case-insensitive) followed by `(` literal (`,` literal)* `)`. Header family: keep arg 0, redact the rest. Query family: if arg 0 contains `=` (v2 form), every arg becomes `key=**REDACTED**`; else (v3) keep arg 0 and redact the rest. Safe matchers stay verbatim. **Anything else** (unknown name, stray literal, unbalanced quote, trailing comma, empty arg list) → the whole rule becomes `**REDACTED**` (fail closed). Apply the same function to each `errors` entry by replacing the raw rule substring with the redacted rule, and fully redact an error that contains a matcher call when the rule is not found verbatim. Put it in a pure module next to `rules.py` (e.g. `rules.redact_rule`) so the sensor attribute can reuse it.

### F8 — Logo source and export pipeline [VERIFIED pipeline; licence partly ASSUMED]
- The current `brand/icon.svg` (viewBox `0 0 101 103`, ids `clip0_2122_26`, fill `#2AA2C1`) is the small-screen `Logo` variant from **traefik/traefik `webui/src/components/icons/Logo.tsx`** (@v3.7.19, added 2025-05-28, "Migrate Traefik Proxy dashboard UI to React"). The same file holds **`ProxyLogo`**: a landscape "traefik proxy" lockup, `viewBox="0 0 280 108"` (≈ 2.59:1), mark `#2AA2C1` + wordmark `fill={textColor}` (default `#000`; the webui uses `#fff` in dark mode).
- The repo also has `docs/content/assets/img/traefikproxy-vertical-logo-color.svg` (209×318, **portrait**, unusable for `logo.png`) and `traefik.logo.png` (600×600 square).
- Licence: the repo `LICENSE.md` is MIT ("Copyright (c) 2016-2020 Containous SAS; 2020-2025 Traefik Labs"). MIT covers the file's copyright, **not the trademark**. The official brand guidelines (2020 PDF) and a current press kit exist at `traefik.io/press` and were not fetched. They name the "standard horizontal lockup (icon + wordmark)" as the official logo [CITED: web search summary of containo.us brand-guidelines PDF; LOW].
- **Verified pipeline** (extract `ProxyLogo` JSX → SVG by replacing `{textColor}` with `"#000"`/`"#fff"`, `clipPath=` → `clip-path=`, dropping `{...props}`; `xmllint` valid):
  - icon: `rsvg-convert -w 2048 -h 2048 --keep-aspect-ratio docs/icon.svg -o big.png && magick big.png -trim +repage -resize 256x256 -background none -gravity center -extent 256x256 -strip -define png:color-type=6 -interlace PNG brand/icon.png` (512 for `@2x`) → alpha bbox `256x231+0+12` / `512x461+0+25`: trimmed to the edges and vertically centred, interlaced, 17 KB / 44 KB.
  - logo: `rsvg-convert -h 1024 --keep-aspect-ratio docs/logo.svg -o big.png && magick big.png -trim +repage -resize x128 -strip -define png:color-type=6 -interlace PNG brand/logo.png` → **337×128** (17 KB); `x256` → **674×256** (41 KB). Both meet the 128–256 / 256–512 shortest-side rule.
  - The current icons are **not centred**: alpha bbox `225x203+13+25` in 256² (`449x405+26+51` in 512²), i.e. padded and offset. That confirms the re-export.
- **Dark theme:** with a black wordmark, `logo.png` is unreadable on dark backgrounds. Without `dark_logo.png`, the dark chain is `dark_logo → dark_icon → logo`, so the black-text logo is shown. Shipping `dark_logo.png`/`dark_logo@2x.png` (white text, same pipeline) fixes it. The deferred list excludes only `dark_icon.png` → Open Question 1.

### F9 — CLAUDE.md regeneration (D-07) [VERIFIED: source + dry run on a scratch copy]
- Verb: **`node ~/.claude/gsd-core/bin/gsd-tools.cjs query generate-claude-md --output CLAUDE.md`** (`profile-output.cjs` `cmdGenerateClaudeMd`). **`--output` is mandatory here.** Without it, the default target is `.claude/CLAUDE.md` (#1098), and `.planning/config.json` has no `claude_md_path`.
- Managed sections: `project` (← `.planning/PROJECT.md`), `stack` (← `.planning/codebase/STACK.md`, else `.planning/research/STACK.md`; **only headings, table rows and bullet lines are copied, prose is dropped**), `conventions`, `architecture` (fallback text: no `.planning/codebase/`), `skills` (table from `.claude/skills/*/SKILL.md` frontmatter `name`/`description`), `workflow`. Sections are replaced between `<!-- GSD:<name>-start` and `<!-- GSD:<name>-end -->`. A missing marker is **appended** at the end of the file.
- **`skill-routing` is not generated by any gsd-core code** (grep: no occurrence under `~/.claude/gsd-core`). It came from the spike wrap-up commit `34587b1` and already points at the new name `.claude/skills/spike-findings-homeassistant-traefik-proxy-integration/SKILL.md`. After the `git mv` it resolves without edits.
- Dry run against a copy of today's CLAUDE.md: it **regresses** content. The title becomes "Home Assistant Traefik Integration" (PROJECT.md heading), the stack becomes `>=2025.4.0`, Python 3.12/3.13, hacs name `"Traefik"` (STACK.md is older than the hand-edited CLAUDE.md), the workflow list becomes `/gsd-fast`, `/gsd-quick`, … and a new `## Project Skills` table is appended after the profile block (with the old skill name until the rename).
- Required order: (1) fix `.planning/PROJECT.md` (title "Home Assistant Traefik Proxy Integration"; constraints: min HA 2026.11.0, no `info.md`, default scan interval 15 s; DIAG-03 reload text marked superseded); (2) fix `.planning/research/STACK.md` (tables/bullets: domain `traefik_proxy`, paths, HA 2026.11.0, Python ≥ 3.14.2, `pytest-homeassistant`, no refresh endpoint / `services.yaml`, contributors links); (3) `git mv` the skill dir and update `SKILL.md` `name:`/`description:` plus internal paths (`custom_components/traefik/` occurs in `SKILL.md`, `MANIFEST.md:72`, `references/tls-handshake.md:3,29,166`, `sources/shared/tls.py:5`); (4) run the generator with `--output CLAUDE.md`; (5) grep-verify (`traefik_proxy`, `2026.11.0`, no `routers/refresh`, the new skill name in `## Project Skills`).

### F10 — What would fail today after D-01..D-03 [VERIFIED]
- **Nothing in either validator.** hassfest 2026.11.1 and the `hacs/action` overlay both pass with `categories` + `1.0.0` + sorted keys. `brand/icon.svg` is ignored by both (hassfest has no brand validator; HACS `brands` only checks `<path>/brand/icon.png`). `hacs.json` (`name`, `homeassistant`, `hacs`) matches `HACS_MANIFEST_JSON_SCHEMA` (`extra=PREVENT_EXTRA`; allowed keys `content_in_root, country, filename, hacs, hide_default_branch, homeassistant, persistent_directory, render_readme, zip_release, name`).
- Failure modes to guard: inserting `categories` out of order (hassfest ERROR); an unknown category (HACS FAIL, hassfest only WARN); more than 3 or duplicate categories (HACS FAIL); deleting `brand/icon.png` (HACS `brands` falls back to the brands repo → FAIL).
- `scripts/hassfest_checks.py all` exits non-zero on HEAD: `top-level keys ['entity'] not allowed` for en/de. hassfest's real strings schema (`_gen_strings_schema`, image l.421-660) **allows** `title, config, config_subentries, options, preview_features, selector, device_automation, system_health, config_panel, application_credentials, issues, entity_component, device, entity, services, conditions, triggers, conversation`; `exceptions` is also accepted (our en/de.json carry it and hassfest passes). Fix the forbidden set to `{"reauth", "reconfigure"}`.

### F11 — Facts the README/CHANGELOG writers need [VERIFIED: Read const.py, en.json]
- `const.py:35` `DEFAULT_SCAN_INTERVAL: Final = 15  # seconds (CONTEXT.md D-12)` → the README says **15 s** (CLAUDE.md/PROJECT.md "30s" is stale). `const.py:64-68` `MIN_SCAN_INTERVAL: Final = 15`, `MAX_SCAN_INTERVAL: Final = 300`, `MIN_TLS_WARN_DAYS: Final = 1`, `MAX_TLS_WARN_DAYS: Final = 90`, `DEFAULT_TLS_WARN_DAYS: Final = 14`. `const.py:28-31` `DEFAULT_MISSING_GRACE_HOURS: Final = 24`, `MIN_MISSING_GRACE_HOURS: Final = 1`, `MAX_MISSING_GRACE_HOURS: Final = 168`. `const.py:41` `ITEM_STATE_OPTIONS: Final = ("enabled", "warning", "error", "disabled", STATE_MISSING)`. `const.py:79-83` `DEFAULT_TLS_CERT_COOLDOWN: Final = 21600`, `CERT_RETRY_INTERVAL: Final = 300`, `MAX_CERT_HOSTS: Final = 200`. `const.py:87` `PLATFORMS: Final = ["binary_sensor", "sensor", "button"]`.
- `en.json:98-105` selector `auth_type` options `"none": "No authentication"`, `"basic": "Basic auth (username and password)"`, `"bearer": "Bearer token"`. `en.json:223-231` issues `entities_migrated`, `insecure_credentials`. Entity translation keys `en.json:147-221`: sensors `router`, `service`, `routers_count`, `services_count`, `middlewares_count`, `version`, `start_time`, `healthy_ratio`, `certificate_expiry`; binary sensors `routers_problem`, `services_problem`, `middlewares_problem`, `certificates_problem`, `certificate_expiring`; button `refresh` ("Refresh now").
- `exceptions` in en.json (`en.json:107-132`) has no `cert_unavailable` key, and a grep of `custom_components/traefik_proxy` finds no `cert_unavailable`. D-21 IN-03 looks already resolved; check de.json and close it as resolved.
- The `entities_migrated` text (`en.json:226`) currently says "Router binary sensors were replaced by router sensors with new entity IDs". D-21 IN-06 must add that disabled/hidden ones keep their old ID.
- The `entities_migrated` placeholder `entry_title` is filled during the 1.1→1.2 step, **before** the 1.2→1.3 step renames the default title (`__init__.py:262-273` vs `:290-299`). Verified live: the repair says "Traefik Proxy" while the entry is now "traefik-v3". This is cosmetic; either pass the post-migration title or accept it (list it in 08-VISUAL-CHECK.md).
- Planning references in shipped code (D-16 grep, case-insensitive): **8 lines**, all comments — `const.py:35,58,60,63,70,75,86` and `__init__.py:53` (`(D-19)`); `const.py:58` also carries "Plan 02-02". The guard regex should also cover `Plan [0-9]{2}-[0-9]{2}` (REL-06 "phase/plan numbers").
- `README.md:28,32` contain `haos-op3050-1` (D-05 grep gate).
- Tests: the only literal sleep ≥ 1 s under `tests/` is `tests/traefik/capture.py:298 time.sleep(1.0)`. That is a non-test capture **script** (polling Traefik readiness), not a test. The D-11 guard must exclude `tests/traefik/` or the script must be reworded.

## Architecture Patterns

### Validation flow (local, pre-push)
```
working tree ──► make hassfest ──► docker run hassfest:latest (/github/workspace) ──► "Invalid integrations: 0"
      │
      ├──► git ls-files -co --exclude-standard ──► files.txt
      │                                              │
      └──► make hacs-action ──► docker run hacs/action:main --entrypoint python3 hacs_action_local.py
                                   │  tree + hacs.json + manifest + brand/README  ◄── /repo (ro)
                                   │  description/topics/issues/license/archived ◄── GitHub API (gh token, read-only)
                                   └──► "All (10) checks passed"
post-push CI (manager): validate.yml hassfest + hacs jobs at the PR head ref ──► links for hacs/default PR
```

### Visual check flow
```
compose up traefik-v3 ──► network traefik-harness_default ◄── HA 2026.11.0 (named volume, code :ro)
REST onboarding ──► tokens (0600 file) ──► REST config flow ──► entry + repairs
WS (device list, repairs, brands token) ──► evidence
Playwright (hassTokens + selectedLanguage in localStorage, de/en) ──► JPEG q75 shots ──► phase dir
[migration] v0.3.0 code on 2nd volume ──► swap mount to working tree ──► entities_migrated repair
teardown: rm -f containers, compose down -v, volume rm, compare with baseline
```

### Recommended file layout for new artefacts
```
.github/workflows/validate.yml      # pinned, timeouts, schedule + dispatch
.github/workflows/release.yml       # tag vs manifest
.github/dependabot.yml              # github-actions weekly
.github/requirements-min-ha.in      # 2 lines
.github/requirements-min-ha.txt     # uv pip compile output (hashes)
scripts/hacs_action_local.py        # overlay harness (runs inside ghcr.io/hacs/action:main)
docs/icon.svg, docs/logo.svg, docs/logo-dark.svg   # vector sources (not shipped)
custom_components/traefik_proxy/brand/{icon,icon@2x,logo,logo@2x[,dark_logo,dark_logo@2x]}.png
```

### Anti-Patterns to Avoid
- **Running the stock `hacs/action` image and calling it local validation**: it validates GitHub's `main`, not the working tree.
- **Bind-mounting a host dir as HA `/config`**: it leaves root-owned files; use a named volume.
- **Asserting the brand logo only by HTTP 200**: the fallback serves the icon with 200 (F6).
- **Running `generate-claude-md` before fixing PROJECT.md/STACK.md**: it regresses CLAUDE.md (F9).
- **Interpolating `${{ github.event.release.tag_name }}` directly into `run:`**: script injection. Pass it through `env:`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HACS validation logic | A re-implementation of the 10 checks | The official image + method overlay (`hacs_action_local.py`) | Validator code stays upstream; only I/O is redirected |
| hassfest checks | Extending `scripts/hassfest_checks.py` into a hassfest clone | `make hassfest` (official image) | The script is only a fast pre-commit approximation |
| Min-HA lock | A hand-maintained pin list | `uv pip compile --generate-hashes` + `uv pip sync --require-hashes` | Hash-checked and reproducible |
| HA onboarding | UI clicking | REST onboarding (F5 step 3) | Deterministic, scriptable |
| Rule parsing | Ad-hoc `re.sub` on `Header\(` | The tokenizer with fail-closed behaviour (Code Examples) | Case variants, escapes, v2/v3 arity |
| PNG trimming/centring | Manual pixel math | `magick -trim +repage -resize -gravity center -extent` | Verified bbox output |

## Common Pitfalls

### P1: Rule secrets leak outside diagnostics
**What goes wrong:** D-17 redacts diagnostics, but the router sensor exposes `rule` and `errors` as **state attributes** (`sensor.py:213`). These are recorded in history, visible to all users, and included in any state export. Traefik `errors` can contain the full rule.
**How to avoid:** apply `redact_rule` to the `rule` attribute **and** to `errors` (or mark `rule` unrecorded via `_unrecorded_attributes`). This goes beyond D-17's wording, so the planner/manager must decide (Open Question 2). At minimum, redact `errors` in diagnostics too.
**Warning signs:** a diagnostics test with `Header(`X-Token`, `secret`)` passes, but `hass.states.get(...).attributes["rule"]` still contains `secret`.

### P2: `hacs/action` silently runs only 5 checks
**What goes wrong:** without `INPUT_REPOSITORY` (or a matching `GITHUB_REPOSITORY`), `is_pull_from_fork` is true and the five `allow_fork=False` checks are skipped, yet the run reports "All (5) checks passed".
**How to avoid:** set `INPUT_REPOSITORY`, `REPOSITORY` and `GITHUB_REPOSITORY`, and require "All (10) checks passed" in the evidence.

### P3: The `filterwarnings = error::SyntaxWarning` gate is bypassed by a stale pytest pyc
**What goes wrong:** verified with a scratch test. Fresh run → collection error. Run once without the gate (writes `__pycache__/*.pyc`), then with the gate → **1 passed**. SyntaxWarning is only emitted at compile time. CI (fresh checkout) catches it; local runs may not.
**How to avoid:** keep the `filterwarnings` entry (D-10) **and** add a guard test that compiles every `*.py` under `tests/` and `custom_components/` with `warnings.simplefilter("error", SyntaxWarning)` via `compile(source, path, "exec")`. That is deterministic and independent of caches.

### P4: hassfest image floats; local image may be stale
**What goes wrong:** the local cached `:latest` was 2026.11.0 while CI pulls 2026.11.1.
**How to avoid:** `docker run --rm --pull always …` in `make hassfest`. Record the digest/HA version in evidence.

### P5: ruff version drift between pre-commit and CI
**What goes wrong:** `.pre-commit-config.yaml` pins `ruff-pre-commit rev: v0.15.15`, while `uv.lock` resolves **ruff 0.17.5** (`uv run ruff --version`) and CI uses `uv run ruff`. Formatting/lint verdicts can differ.
**How to avoid:** make ruff and mypy pre-commit hooks `repo: local` with `entry: uv run ruff check --fix` / `uv run ruff format` (`language: system`). Or bump `rev` to `v0.17.5` and keep it in sync. The local-hook option is the only one that guarantees "Makefile = CI = pre-commit". `pre-commit-hooks` latest is `v6.0.0` (repo pins v5.0.0).

### P6: `pre-commit run --all-files` mutates files
**What goes wrong:** `end-of-file-fixer`, `trailing-whitespace`, `mixed-line-ending --fix=lf` and `ruff --fix` rewrite files.
**How to avoid:** run it in the tooling plan, commit the fixes, run it a second time and require a clean pass with no diff.

### P7: `uv pip compile --python-version 3.14` is unsatisfiable
**How to avoid:** use `3.14.2` (the `requires-python` floor of `pytest-homeassistant==2026.11.0`) and `UV_HTTP_TIMEOUT=300`.

### P8: Brand verification with `magick -trim -format %@` on RGBA reports `+0+0`
**What goes wrong:** `-trim` keyed on the corner colour reported `256x231+0+0` for a correctly centred icon.
**How to avoid:** measure the alpha channel: `magick f.png -alpha extract -format %@ info:` (gives `256x231+0+12`).

### P9: Playwright version vs installed browser build
**What goes wrong:** `playwright==1.64.1` expects `chromium_headless_shell-1248`; the cache has `-1254`.
**How to avoid:** use the latest `playwright` (1.65.2 matches 1254 [ASSUMED from the cache layout]) or pass `executable_path`. Never install browsers globally beyond `~/.cache/ms-playwright`.

### P10: Wrong Bearer tokens get the host IP banned
**What goes wrong:** the brands proxy and REST count a wrong `Authorization` header as a failed login (401). That matters only if `ip_ban_enabled`; HA's default config does not ban [ASSUMED].
**How to avoid:** always read the token from the tokens file and never probe with dummy tokens repeatedly.

### P11: Exit codes through pipes
**What goes wrong:** `docker run … | tail` returns tail's status. zsh/sh differ (`PIPESTATUS` vs `pipestatus`).
**How to avoid:** redirect output to a log file and check `$?` of the `docker run`, or use `set -o pipefail` in Makefile recipes.

## Code Examples

### `scripts/hacs_action_local.py` (verified: pass on tree, fail on bogus category / missing icon)
```python
"""Run the official hacs/action validators against a LOCAL working tree.

Runs inside ghcr.io/hacs/action:main. Repository metadata (description, topics,
issues, license, archived, releases) still comes from the GitHub API for
REPOSITORY; the file tree and file contents (hacs.json, manifest.json, brand/,
README) come from /repo, restricted to the paths listed in /harness/files.txt
(host: `git ls-files -co --exclude-standard`).
"""

from __future__ import annotations

import json
import os
import runpy
import sys
from pathlib import Path

sys.path.insert(0, "/hacs")

from aiogithubapi.models.git_tree import GitHubGitTreeEntryModel  # noqa: E402

from custom_components.hacs.base import HacsBase  # noqa: E402
from custom_components.hacs.exceptions import HacsException  # noqa: E402
from custom_components.hacs.repositories.base import HacsRepository  # noqa: E402
from custom_components.hacs.repositories.integration import (  # noqa: E402
    HacsIntegrationRepository,
)

ROOT = Path(os.environ.get("LOCAL_ROOT", "/repo"))
FILES = [
    line.strip()
    for line in Path(os.environ.get("LOCAL_FILES", "/harness/files.txt")).read_text().splitlines()
    if line.strip() and (ROOT / line.strip()).is_file()
]
REPO = os.environ["REPOSITORY"]
RAW_PREFIX = f"https://raw.githubusercontent.com/{REPO}/"


def _tree() -> list[GitHubGitTreeEntryModel]:
    dirs: set[str] = set()
    for path in FILES:
        parts = path.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add("/".join(parts[:i]))
    entries = [{"path": d, "type": "tree", "mode": "040000"} for d in sorted(dirs)]
    entries += [
        {"path": f, "type": "blob", "mode": "100644", "size": (ROOT / f).stat().st_size}
        for f in FILES
    ]
    return [GitHubGitTreeEntryModel(e) for e in entries]


async def _get_tree(self, ref):  # noqa: ANN001, ANN202
    self.logger.info("LOCAL OVERLAY: tree from %s (%s files)", ROOT, len(FILES))
    return _tree()


async def _get_hacs_json(self, ref=None):  # noqa: ANN001, ANN202
    return json.loads((ROOT / "hacs.json").read_text())


async def _get_integration_manifest(self, ref=None):  # noqa: ANN001, ANN202
    path = f"{self.content.path.remote}/manifest.json"
    if path not in FILES:
        raise HacsException(f"No manifest.json file found '{path}'")
    return json.loads((ROOT / path).read_text())


_orig_download = HacsBase.async_download_file


async def _download(self, url, **kwargs):  # noqa: ANN001, ANN202
    if url and url.startswith(RAW_PREFIX):
        rel = url[len(RAW_PREFIX) :].split("/", 1)[1]  # drop the ref segment
        if rel.startswith("tags/"):
            rel = rel.split("/", 2)[2]
        if rel in FILES:
            return (ROOT / rel).read_bytes()
        return None
    return await _orig_download(self, url, **kwargs)


HacsRepository.get_tree = _get_tree
HacsRepository.async_get_hacs_json = _get_hacs_json
HacsIntegrationRepository.async_get_integration_manifest = _get_integration_manifest
HacsBase.async_download_file = _download

runpy.run_path("/hacs/action.py", run_name="__main__")
```

### Makefile validator targets (D-12)
```make
REPO         ?= akentner/homeassistant-traefik-proxy-integration
HASSFEST_IMG ?= ghcr.io/home-assistant/hassfest:latest
HACS_IMG     ?= ghcr.io/hacs/action:main

hassfest:  ## Run hassfest exactly like home-assistant/actions/hassfest (throwaway container).
	docker run --rm --pull always -v "$(CURDIR)":/github/workspace $(HASSFEST_IMG)

hacs-action:  ## Run hacs/action validators (category integration, no ignore) on the LOCAL tree.
	@tmp=$$(mktemp -d); \
	git ls-files -co --exclude-standard > $$tmp/files.txt; \
	cp scripts/hacs_action_local.py $$tmp/; \
	INPUT_GITHUB_TOKEN="$$(gh auth token)" docker run --rm --pull always \
	  -e INPUT_GITHUB_TOKEN -e INPUT_CATEGORY=integration -e REPOSITORY_REF=local-tree \
	  -e INPUT_REPOSITORY=$(REPO) -e REPOSITORY=$(REPO) -e GITHUB_REPOSITORY=$(REPO) \
	  -v "$(CURDIR)":/repo:ro -v $$tmp:/harness:ro \
	  --entrypoint python3 $(HACS_IMG) /harness/hacs_action_local.py; \
	rc=$$?; rm -rf $$tmp; exit $$rc

min-ha-lock:  ## Regenerate the locked minimum-HA test stack.
	UV_HTTP_TIMEOUT=300 uv pip compile .github/requirements-min-ha.in --python-version 3.14.2 \
	  --python-platform x86_64-manylinux_2_28 --generate-hashes -o .github/requirements-min-ha.txt

test-min-ha:  ## Same as the CI test-min-ha job.
	uv venv --python 3.14 .venv-min-ha
	uv pip sync --python .venv-min-ha/bin/python --require-hashes .github/requirements-min-ha.txt
	.venv-min-ha/bin/python -m pytest -q tests
```
(`.venv-min-ha/` must be added to `.gitignore`.)

### `validate.yml` skeleton (D-13, D-14)
```yaml
name: Validate
on:
  push:
  pull_request:
  schedule:
    - cron: "17 3 * * *"
  workflow_dispatch:
permissions:
  contents: read
jobs:
  test-min-ha:
    name: Tests (minimum HA 2026.11.0)
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3
      - run: uv python install 3.14
      - run: uv venv --python 3.14 .venv-min-ha
      - run: uv pip sync --python .venv-min-ha/bin/python --require-hashes .github/requirements-min-ha.txt
      - run: .venv-min-ha/bin/python -m pytest -q tests
  hassfest:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: home-assistant/actions/hassfest@86d4564712fa02543c808e3a693dd04f9d3f8361 # master (2026-10-26)
  hacs:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: hacs/action@d556e736723344f83838d08488c983a15381059a # 22.5.0
        with:
          category: integration
```
(The `lint` and `test` jobs keep their commands with the pinned actions plus `timeout-minutes: 15`. `push:` without a branch filter plus `pull_request:` runs twice for PR branches pushed to this repo; keep `push: branches: [main]` if double runs are unwanted. The validation page wording only requires "every push and pull request, nightly, and on manual start".)

### `release.yml` (D-15)
```yaml
name: Release check
on:
  release:
    types: [published]
  push:
    tags: ["v*"]
permissions:
  contents: read
jobs:
  tag-matches-manifest:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - name: Tag equals manifest version
        env:
          TAG: ${{ github.event.release.tag_name || github.ref_name }}
        run: |
          python3 - <<'EOF'
          import json, os, sys
          tag = os.environ["TAG"]
          version = tag[1:] if tag.startswith("v") else tag
          manifest = json.load(open("custom_components/traefik_proxy/manifest.json"))["version"]
          if version != manifest:
              print(f"::error::tag {tag} (version {version}) != manifest.json version {manifest}")
              sys.exit(1)
          print(f"tag {tag} matches manifest.json version {manifest}")
          EOF
```

### `dependabot.yml`
```yaml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
```

### Rule redactor (verified 16/16 cases; adapt names/typing to the codebase)
```python
REDACTED = "**REDACTED**"
_SAFE = {"host", "hostheader", "hostregexp", "path", "pathprefix", "pathregexp", "method", "clientip"}
_HEADER = {"header", "headerregexp", "headers", "headersregexp"}  # keep arg 0 (key)
_QUERY = {"query", "queryregexp"}  # v3 (key[, value]) or v2 (`k=v`, ...)
_TOKEN = re.compile(
    r"""(?P<ws>\s+)|(?P<op>&&|\|\||!|\(|\)|,)|(?P<raw>`[^`]*`)|(?P<dq>"(?:[^"\\]|\\.)*")|(?P<name>[A-Za-z][A-Za-z0-9]*)""",
)
# Algorithm: tokenize fully (no match => fail closed); every name must be a known matcher
# (case-insensitive) followed by "(" literal ("," literal)* ")"; header family -> redact args[1:];
# query family -> if "=" in args[0]: each arg -> "key=**REDACTED**" else redact args[1:];
# safe matchers verbatim; any violation -> return REDACTED for the whole rule.
# Test cases that must hold:
#   Header(`X-Token`, `s3cret`)         -> Header(`X-Token`, `**REDACTED**`)
#   headers(`Authorization`, `Bearer x`)-> headers(`Authorization`, `**REDACTED**`)
#   Query(`token=abc`, `x=1`)           -> Query(`token=**REDACTED**`, `x=**REDACTED**`)
#   Query(`key`, `val=ue`)              -> Query(`key`, `**REDACTED**`)
#   Query(`mobile`)                     -> unchanged
#   Header("K", "v\"q")                 -> Header("K", "**REDACTED**")
#   Heder(`X`, `y`) / unterminated ` / trailing comma / stray literal -> **REDACTED**
```
The full reference implementation (≈120 lines) was run from the research scratchpad. The planner should have the executor re-create it test-first from the cases above.

### Visual-check onboarding (verified)
```python
# POST /api/onboarding/users  {"client_id": BASE+"/", "name": ..., "username": ..., "password": ..., "language": "en"} -> auth_code
# POST /auth/token (form) grant_type=authorization_code&code=<auth_code>&client_id=<BASE/> -> access_token, refresh_token
# POST /api/onboarding/core_config {} ; POST /api/onboarding/analytics {} ;
# POST /api/onboarding/integration {"client_id": BASE+"/", "redirect_uri": BASE+"/?auth_callback=1"}
# Playwright init script:
#   localStorage.setItem('hassTokens', JSON.stringify({access_token, token_type:'Bearer', expires_in,
#       hassUrl: BASE, clientId: BASE+'/', expires: Date.now()+expires_in*1000, refresh_token}));
#   localStorage.setItem('selectedLanguage', '"de"');
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `astral-sh/setup-uv@v5` major tags | Immutable releases, no major/minor tags (`@v8+` impossible) | setup-uv v8 | Must pin a full version or SHA |
| `actions/checkout@v6` | v7.0.1 | 2026-07 | ESM; fork-checkout block for `pull_request_target` |
| hassfest action Dockerfile (tag 1.0.0) | Composite `docker run ghcr.io/home-assistant/hassfest` | 2024-08 | Local run = identical command |
| `pytest-homeassistant-custom-component` | `pytest-homeassistant` (M38) | HA 2026.11 | Lock pins `pytest-homeassistant==2026.11.0` |
| Brand images via home-assistant/brands | Local `brand/` served by `/api/brands/integration/...` | HA 2026.3 | Fallbacks apply locally |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | WS command `config/core/update {"country":"DE"}` sets the country and clears `country_not_configured` | F5 step 4 | Only cosmetic noise in repairs screenshots |
| A2 | A `uv sync --locked` group override would need `[tool.uv] conflicts` | F4 | None; the requirements-file approach is verified |
| A3 | Traefik Labs trademark/brand guidelines permit nominative use of the logo with a trademark note | F8 | The catalog reviewer or Traefik Labs could object; fallback: icon only (D-03 escape hatch) |
| A4 | Playwright 1.65.2 maps to Chromium build 1254 | P9 | Use `executable_path` instead |
| A5 | HA's default config does not IP-ban on wrong Bearer tokens | P10 | Locked out of the throwaway instance; restart it |
| A6 | On `release: published`, `actions/checkout` checks out the release tag ref | release.yml | Mismatch compares against the wrong manifest; mitigated because both triggers run |
| A7 | Dependabot updates SHA pins whose comment is a branch (`# master (…)`) — it may not | D-13 | The hassfest pin needs manual bumps; acceptable (action.yml unchanged since 2024) |
| A8 | The webui `ProxyLogo` equals the official horizontal lockup | F8 | Wrong artwork; the press kit at traefik.io/press is authoritative |

## Open Questions

1. **Ship `dark_logo.png`/`dark_logo@2x.png`?**
   - Known: the black wordmark is unreadable on dark themes, and the dark chain falls back to `logo.png`. CONTEXT defers only `dark_icon.png`.
   - Recommendation: ship `dark_logo` (white text, same pipeline) as a worker decision recorded in the SUMMARY; otherwise ship only the icon.
2. **Redact `rule`/`errors` in entity attributes too (P1)?**
   - D-17 names diagnostics only; the same secrets sit in state attributes and the recorder.
   - Recommendation: apply the same redactor to the `rule` attribute (keeps it useful) and to `errors`. This is a manager decision because it changes visible attributes before 1.0.0.
3. **Logo artwork source:** the webui `Logo.tsx` (MIT repo, verified geometry) vs the official press-kit horizontal lockup (traefik.io/press, not fetched). Recommendation: the executor tries the press kit first and falls back to `Logo.tsx` `ProxyLogo`, recording the source URL and licence in `docs/` (e.g. `docs/BRAND.md`) and the README trademark note.
4. **`push:` trigger scope:** an unfiltered `push` plus `pull_request` double-runs CI for PR branches in the same repo. Keep `push: branches: [main]` + `pull_request` + `schedule` + `workflow_dispatch` (meets "push, PR, nightly, manual").

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker daemon | hassfest, hacs-action, visual check | ✓ | 29.9.3 | — |
| `docker compose` | Traefik harness | ✓ | (plugin) | — |
| `gh` (authenticated, keyring) | hacs-action token, read-only API | ✓ | scopes `repo, workflow, read:org, gist` | Any read-only PAT via env |
| `uv` | locks, tools | ✓ | 0.13.4 | — |
| Python 3.14 | pre-commit `default_language_version` | ✓ | `/usr/bin/python3.14` 3.14.10 | — |
| `rsvg-convert`, `magick`, `xmllint` | brand export | ✓ | — | — |
| Playwright + Chromium | screenshots | ✓ | headless shell 1254 cached | `executable_path` |
| HA image 2026.11.0 | visual check | ✓ (pulled, ~1 min) | digest `c6c1ca99…` | — |
| PyPI throughput | lock compile, `uv run --with` | ⚠ slow (timeouts seen) | — | `UV_HTTP_TIMEOUT=300`, `--offline` with cached versions |

**Missing dependencies with no fallback:** none.

## Validation Architecture

(Nyquist validation is disabled; these are the phase gates the plans must run.)
- Per task: `uv run pytest -q`; `uv run ruff check custom_components tests && uv run ruff format --check custom_components tests && uv run mypy --strict custom_components/traefik_proxy`.
- Min-HA: the `make test-min-ha` sequence (lock + `uv pip sync` + `pytest -q tests`).
- Phase gate (D-27): `uvx pre-commit run --all-files` (twice, second run clean), `make hassfest` (`Invalid integrations: 0`), `make hacs-action` ("All (10) checks passed", no categories warning), `git tag --list` = 9 tags `v0.1.0`…`v0.3.0`, `git ls-remote origin` unchanged (`main`, `renovate/configure`, tags), Docker baseline restored.
- New guard tests: full-tree planning-reference grep (D-16, incl. `Plan NN-NN`); literal sleep ≥ 1 s in `tests/` excluding `tests/traefik/` (D-11); `compile()`-based SyntaxWarning guard (P3); redactor table test (D-17); brand PNG geometry test (sizes 256²/512², logo shortest side 128/256, alpha bbox touches two opposite edges).

## Security Domain

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (no new auth) | — |
| V5 Input Validation | yes | Router rules from the API are untrusted text; tokenizer with fail-closed redaction |
| V7 Error Handling / Logging | yes | Diagnostics and attributes must not leak header/query secrets; tokens never printed in scripts |
| V14 Configuration (CI supply chain) | yes | SHA-pinned actions, least-privilege `permissions`, tag passed through `env:` (no `${{ }}` in `run:`) |

| Threat | STRIDE | Mitigation |
|--------|--------|------------|
| Secret in `Header(...)`/`Query(...)` rule posted in a public issue via diagnostics | Information disclosure | `redact_rule` on `rule` + `errors` (D-17, P1) |
| Workflow script injection via a crafted tag name | Tampering | `env: TAG: ${{ … }}` + Python reads `os.environ` |
| Compromised action tag moved to malicious commit | Tampering | Full-SHA pins (D-13); images still float (accepted, documented) |
| Token leak in local tooling | Information disclosure | `INPUT_GITHUB_TOKEN="$(gh auth token)" docker run -e INPUT_GITHUB_TOKEN`; tokens file 0600; never echo |

## Sources

### Primary (HIGH confidence — read or executed this session)
- `gh api repos/home-assistant/actions/contents/hassfest/action.yml` + image `entrypoint.sh` (hassfest 2026.11.1)
- `gh api repos/hacs/action/contents/action.yml` (main and 22.5.0, diff empty); `hacs/integration` `action/action.py`, `action/Dockerfile`, `custom_components/hacs/validate/*.py`, `repositories/base.py`, `repositories/integration.py`, `utils/validate.py`
- `home-assistant/core@2026.11.0` `homeassistant/components/brands/{const,__init__}.py`, `loader.py` `has_branding`; onboarding `views.py`/`const.py` read inside the 2026.11.0 image
- `traefik/traefik@v3.7.19` `pkg/muxer/http/{matcher,matcher_v2,mux}.go`, `pkg/rules/parser.go`; `@v2.11.33` `pkg/muxer/http/mux.go`, `pkg/rules/parser.go`; `webui/src/components/icons/Logo.tsx`; `LICENSE.md`
- https://doc.traefik.io/traefik/reference/routing-configuration/http/routing/rules-and-priority/ (v3 matchers, quoting, ruleSyntax deprecation)
- https://doc.traefik.io/traefik/v2.11/routing/routers/ (v2 matchers)
- `gh api` releases/tags for `actions/checkout`, `astral-sh/setup-uv` (v8/v9/v10 notes), `home-assistant/actions`, `hacs/action`; GHCR manifest API for hassfest and home-assistant images
- `~/.claude/gsd-core/bin/lib/profile-output.cjs` (`cmdGenerateClaudeMd`) + dry run
- Local executions: hassfest runs, hacs overlay runs (positive/negative), lock compile/sync/pytest, HA 2026.11.0 onboarding/flow/options/repairs/brands/devices, Playwright screenshots, v0.3.0 → working-tree migration

### Secondary (MEDIUM/LOW)
- [Traefik Labs Brand Guidelines (PDF)](https://Containo.Us/downloads/Traefik_Labs_Brand_Guidelines.pdf) — via web-search summary only (horizontal lockup = official logo); LOW
- [Traefik press page](https://traefik.io/press) — press kit location; not fetched; LOW
- [Containous Brand Guidelines](https://traefik.io/downloads/Containous-Brand-Guidelines.pdf) — outdated; LOW
- `.planning/research/MARKETPLACE-BEST-PRACTICES.md` §2/§3/§6 (prior research, built upon)

## Metadata

**Confidence breakdown:**
- Validators (hassfest, hacs/action), pins, lock, brands proxy, visual-check recipe, migration seeding: HIGH (executed)
- Rule grammar and redactor: HIGH (Traefik source + docs + 16 executed cases)
- CLAUDE.md generator: HIGH (source + dry run)
- Logo licence/trademark: LOW (guidelines not fetched)

**Research date:** 2026-11-15
**Valid until:** ~2026-12-01 (floating images `hassfest:latest` / `hacs/action:main` and action releases move; HA 2026.12 is due early December)
