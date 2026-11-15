# Phase 8: Marketplace + release readiness - Context

**Gathered:** 2026-11-15
**Status:** Ready for planning
**Source:** PRD Express Path (ROADMAP Phase 8 incl. Carry-over lines, REQUIREMENTS
REL-01..08 + DIST-04 + DOCS-02 + DOCS-04, audit items, decision log
`~/.cache/traefik-proxy-integration/decisions.md` — user interview I1–I8 override
everything else —, review carry-overs of Phases 4–7 (`04/05/06-REVIEW-DISPOSITION.md`,
`07-REVIEW-FIX.md`), `deferred-items.md` of Phases 4/5/7, research
`MARKETPLACE-BEST-PRACTICES.md` §2/§3/§4.6/§6, `AUDIT-ARCH-PERF-UX.md`)

<domain>
## Phase Boundary

Last phase of milestone v1.0. The repository becomes ready for the **1.0.0**
release and a `hacs/default` catalog submission: manifest metadata, brand
images, README, CHANGELOG, dev tooling, CI and the release workflow meet the
Marketplace/HACS requirements; shipped code is free of planning references;
the remaining review findings of Phases 4–7 are closed or explicitly disposed;
both validators (hassfest, `hacs/action`) pass locally in throwaway Docker
containers; the visual check deferred from Phase 5/7 (M35) is done in a
throwaway HA 2026.11 container in German and English. Release notes, the
`hacs/default` PR text and the Draft-PR body are drafted in the phase
directory for the user / manager.

**In scope:** `manifest.json`, `brand/`, `docs/`, `README.md`, `CHANGELOG.md`,
`CLAUDE.md` (via its GSD source files), `.claude/skills/` rename,
`.pre-commit-config.yaml`, `scripts/hassfest_checks.py`, `scripts/pre-commit`,
`pyproject.toml` / `uv.lock`, `Makefile`, `.github/workflows/*`, a lock file for
the minimum-HA CI job, `.github/dependabot.yml`, the remaining small code
findings (`diagnostics.py`, `cert_coordinator.py`, `tls.py`, `coordinator.py`,
`config_flow.py`, `__init__.py`, translations), test hygiene, guard tests,
planning-doc housekeeping (REQUIREMENTS wording, deferred-items, stale
dispositions), drafts in the phase directory.

**Out of scope (never planned):** `git push`, opening the Draft PR, creating a
tag, a GitHub release, the `hacs/default` PR, any push to `main` (U1, M8, M41).
The manager pushes `feat/marketplace-polish` and opens the Draft PR **after**
Phase 8 is verified. No real HA instance (U2) — only throwaway local Docker
containers that are removed afterwards.

</domain>

<decisions>
## Implementation Decisions

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

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Decisions and scope
- `~/.cache/traefik-proxy-integration/decisions.md` — decision log (I1–I8 override everything; M23, M35, M40, M41, Phase-8 carry-over lists)
- `.planning/ROADMAP.md` § Phase 8 — goal, success criteria, Carry-over lines
- `.planning/REQUIREMENTS.md` — REL-01..08, DIST-04, DOCS-02, DOCS-04

### Research
- `.planning/research/MARKETPLACE-BEST-PRACTICES.md` §2 (catalog checklist), §3 (brand recipe), §4.6, §6 (Q1 tag, Q4 trademark, Q5 hacs/action checks, Q7 doc URLs, Q8 info.md)
- `.planning/research/AUDIT-ARCH-PERF-UX.md` — items A-19, B-01..B-06, H-01..H-10, H-12

### Carried findings
- `.planning/phases/04-data-layer-correct-lean/04-REVIEW.md` + `04-REVIEW-DISPOSITION.md` (IN-11..IN-14, WR-03 stale) + `deferred-items.md`
- `.planning/phases/05-entity-model-lifecycle/05-REVIEW.md` + `05-REVIEW-DISPOSITION.md` (IN-01, IN-03, IN-06, IN-07) + `deferred-items.md`
- `.planning/phases/06-certificates/06-REVIEW.md` + `06-REVIEW-DISPOSITION.md` (IN-03, IN-04), `06-SECURITY.md` (T-06-13)
- `.planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-REVIEW.md` + `07-REVIEW-FIX.md` (WR-04..07, IN-03, IN-04, IN-05, IN-07) + `deferred-items.md`
- Every `*-SUMMARY.md` "User-visible changes" section of Phases 4–7 (CHANGELOG source)

### Code / config touched
- `custom_components/traefik_proxy/` (manifest.json, brand/, diagnostics.py, cert_coordinator.py, tls.py, coordinator.py, config_flow.py, __init__.py, translations/)
- `.pre-commit-config.yaml`, `scripts/hassfest_checks.py`, `scripts/pre-commit`, `pyproject.toml`, `Makefile`, `.github/workflows/validate.yml`
- `tests/traefik/compose.yaml`, `tests/traefik/capture.py` (throwaway Traefik + capture harness)
- `CLAUDE.md` (GSD-generated sections), `.planning/research/STACK.md`, `.claude/skills/spike-findings-homeassistant-traefik-integration/`

</canonical_refs>

<code_context>
## Existing Code Insights

- `manifest.json` is at `0.3.0`, no `categories`; `pyproject.toml` already says `version = "1.0.0"` but `name = "homeassistant-traefik-integration"` and `--cov=custom_components.traefik`.
- `brand/` holds `icon.png`, `icon@2x.png`, `icon.svg`; no `docs/` directory yet.
- `.pre-commit-config.yaml` uses `python3.13` and `custom_components/traefik/` regexes; `check-added-large-files --maxkb=500`.
- `validate.yml` jobs `lint`, `test`, `test-min-ha`, `hassfest`, `hacs`; `actions/checkout@v6`, `astral-sh/setup-uv@v5`, `hassfest@master`, `hacs/action@main`; no timeouts, no schedule/dispatch.
- `diagnostics.py` dumps the parsed snapshot via `dataclasses.asdict` with `async_redact_data(TO_REDACT)` — router `rule` strings currently pass through unredacted.
- `coordinator.py` still has `_probe_armed_at` and `_interval_elapsed(since)`; `_logged_cause` lives in `coordinator.py`.
- README still mentions the removed "reload service"; CLAUDE.md stack section still describes domain `traefik` and the refresh endpoint.
- Validated Phase 7 commands: `uv run pytest -q`; `uv run ruff check custom_components tests && uv run ruff format --check custom_components tests && uv run mypy --strict custom_components/traefik_proxy`; minimum HA: `~/.cache/traefik-proxy-integration/ha2611-venv/bin/python -m pytest -q -o addopts="-p no:respx" tests`.
- Docker daemon is available (since 2026-11-15 reboot).

</code_context>

<specifics>
## Specific Ideas

- Tests stay green on the dev env (HA 2026.11.x) and on the minimum venv (HA 2026.11.0) after every plan; tests are migrated in the same task as the code change.
- German UI texts are checked in the visual check; translations keep en/de key parity (existing test).

</specifics>

<deferred>
## Deferred Ideas

- Stale-bot `issues.yaml` workflow (pattern from the user's other integrations) — not required by the Marketplace; post-1.0.
- `dark_icon.png` — not needed (teal mark reads on dark, research §3).
- Submitting to `home-assistant/brands` — not needed for custom integrations.
- Creating the tag/release/`hacs/default` PR and pushing — user/manager (U1, M8, M41).

</deferred>

---

*Phase: 08-marketplace-release-readiness*
*Context gathered: 2026-11-15 via PRD Express Path*
