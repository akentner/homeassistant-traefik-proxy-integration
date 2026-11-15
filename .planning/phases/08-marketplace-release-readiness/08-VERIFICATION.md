---
phase: 08-marketplace-release-readiness
verified: 2026-11-15T23:55:00Z
status: human_needed
score: 20/22 must-haves verified
covered_files: [".claude/skills/spike-findings-homeassistant-traefik-proxy-integration/MANIFEST.md", ".claude/skills/spike-findings-homeassistant-traefik-proxy-integration/SKILL.md", ".claude/skills/spike-findings-homeassistant-traefik-proxy-integration/references/tls-handshake.md", ".claude/skills/spike-findings-homeassistant-traefik-proxy-integration/run-all.sh", ".claude/skills/spike-findings-homeassistant-traefik-proxy-integration/sources/001-stdlib-tls-handshake/README.md", ".claude/skills/spike-findings-homeassistant-traefik-proxy-integration/sources/001-stdlib-tls-handshake/probe.py", ".claude/skills/spike-findings-homeassistant-traefik-proxy-integration/sources/002-notafter-format-strings/README.md", ".claude/skills/spike-findings-homeassistant-traefik-proxy-integration/sources/002-notafter-format-strings/probe.py", ".claude/skills/spike-findings-homeassistant-traefik-proxy-integration/sources/003-sni-routing-multicert/README.md", ".claude/skills/spike-findings-homeassistant-traefik-proxy-integration/sources/003-sni-routing-multicert/certs/generate.sh", ".claude/skills/spike-findings-homeassistant-traefik-proxy-integration/sources/003-sni-routing-multicert/server.py", ".claude/skills/spike-findings-homeassistant-traefik-proxy-integration/sources/004-error-handling-async-wrap/README.md", ".claude/skills/spike-findings-homeassistant-traefik-proxy-integration/sources/004-error-handling-async-wrap/probe.py", ".claude/skills/spike-findings-homeassistant-traefik-proxy-integration/sources/shared/tls.py", ".github/dependabot.yml", ".github/requirements-min-ha.in", ".github/requirements-min-ha.txt", ".github/workflows/release.yml", ".github/workflows/validate.yml", ".gitignore", ".planning/phases/08-marketplace-release-readiness/08-01-PLAN.md", ".planning/phases/08-marketplace-release-readiness/08-01-SUMMARY.md", ".planning/phases/08-marketplace-release-readiness/08-02-PLAN.md", ".planning/phases/08-marketplace-release-readiness/08-02-SUMMARY.md", ".planning/phases/08-marketplace-release-readiness/08-03-PLAN.md", ".planning/phases/08-marketplace-release-readiness/08-03-SUMMARY.md", ".planning/phases/08-marketplace-release-readiness/08-04-PLAN.md", ".planning/phases/08-marketplace-release-readiness/08-04-SUMMARY.md", ".planning/phases/08-marketplace-release-readiness/08-05-PLAN.md", ".planning/phases/08-marketplace-release-readiness/08-05-SUMMARY.md", ".planning/phases/08-marketplace-release-readiness/08-06-PLAN.md", ".planning/phases/08-marketplace-release-readiness/08-06-SUMMARY.md", ".planning/phases/08-marketplace-release-readiness/08-07-PLAN.md", ".planning/phases/08-marketplace-release-readiness/08-07-SUMMARY.md", ".planning/phases/08-marketplace-release-readiness/08-08-PLAN.md", ".planning/phases/08-marketplace-release-readiness/08-08-SUMMARY.md", ".planning/phases/08-marketplace-release-readiness/08-09-PLAN.md", ".planning/phases/08-marketplace-release-readiness/08-09-SUMMARY.md", ".planning/phases/08-marketplace-release-readiness/08-10-PLAN.md", ".planning/phases/08-marketplace-release-readiness/08-10-SUMMARY.md", ".planning/phases/08-marketplace-release-readiness/08-11-PLAN.md", ".planning/phases/08-marketplace-release-readiness/08-11-SUMMARY.md", ".planning/phases/08-marketplace-release-readiness/08-12-PLAN.md", ".planning/phases/08-marketplace-release-readiness/08-12-SUMMARY.md", ".planning/phases/08-marketplace-release-readiness/08-13-PLAN.md", ".planning/phases/08-marketplace-release-readiness/08-13-SUMMARY.md", ".pre-commit-config.yaml", "CHANGELOG.md", "CLAUDE.md", "Makefile", "README.md", "custom_components/traefik_proxy/__init__.py", "custom_components/traefik_proxy/api.py", "custom_components/traefik_proxy/brand/dark_logo.png", "custom_components/traefik_proxy/brand/dark_logo@2x.png", "custom_components/traefik_proxy/brand/icon.png", "custom_components/traefik_proxy/brand/icon@2x.png", "custom_components/traefik_proxy/brand/logo.png", "custom_components/traefik_proxy/brand/logo@2x.png", "custom_components/traefik_proxy/cert_coordinator.py", "custom_components/traefik_proxy/config_flow.py", "custom_components/traefik_proxy/const.py", "custom_components/traefik_proxy/coordinator.py", "custom_components/traefik_proxy/diagnostics.py", "custom_components/traefik_proxy/entity.py", "custom_components/traefik_proxy/manifest.json", "custom_components/traefik_proxy/rules.py", "custom_components/traefik_proxy/translations/de.json", "custom_components/traefik_proxy/translations/en.json", "docs/BRAND.md", "docs/icon.svg", "docs/logo-dark.svg", "docs/logo.svg", "hacs.json", "pyproject.toml", "scripts/check_release_tag.py", "scripts/hacs_action_local.py", "scripts/hassfest_checks.py", "scripts/pre-commit", "tests/conftest.py", "tests/test_baseline_guards.py", "tests/test_binary_sensor_tls_expiring.py", "tests/test_brand.py", "tests/test_cert_coordinator.py", "tests/test_cert_entity_state.py", "tests/test_coordinator.py", "tests/test_diagnostics.py", "tests/test_entity_manager.py", "tests/test_migration.py", "tests/test_release_tag_check.py", "tests/test_rules.py", "tests/test_sensor_tls.py", "tests/test_tls.py", "tests/traefik/capture.py", "uv.lock"]
covered_digest: "v4:sha256:cd3519549464df8c3a4731575cea8ff62289fd13eff4c752cac3ee31c89614d0"
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "After the manager's push, open the first Draft-PR run of validate.yml and check the HACS job (hacs/action, category integration, no ignore)"
    expected: "The HACS job is green and reports all 10 checks passed (a report of 5 checks is a failure); lint, test, test-min-ha (hashed install, uv sync --locked) and hassfest jobs are green too"
    why_human: "REL-07 user decision 2026-11-15 (M43): make hacs-action needs a GitHub token and is never run by agents; only the post-push CI run can prove the official validators on this tree"
  - test: "Manager pushes feat/marketplace-polish (run `git ls-remote origin` first) and opens the Draft PR to main with the body from 08-DRAFT-PR.md"
    expected: "Branch on origin, Draft PR open, no tag / release / hacs/default PR created; before pasting, refresh the 08-DRAFT-PR.md evidence table to the post-review numbers (1180 passed, coverage 99.31 %) and mention the review fixes (CR-01, WR-01..WR-04, committed uv.lock)"
    why_human: "REL-08 push/Draft-PR clause is a manager action after verification (M41); executors and the verifier must not push"
  - test: "Decide the logo trademark question A3/A8 (Traefik Labs trademark guidelines not reviewed)"
    expected: "Either keep logo.png/dark_logo.png as shipped (README and docs/BRAND.md already say the guidelines were not reviewed and no permission is claimed) or apply the icon-only fallback before the release and the hacs/default PR"
    why_human: "Legal/brand judgment; never auto-resolved"
  - test: "Review the two judgment-tier prohibitions and the container-cleanup prohibition (unverified-prohibition, human review recommended)"
    expected: "No GitHub token in any log, command line or evidence file (08-08); no HA access/refresh token in 08-VISUAL-CHECK.md or the 26 screenshots (08-09); `docker ps -a`, `docker network ls`, `docker volume ls` show no ha-visual-08*/traefik-harness* leftovers"
    why_human: "Judgment-tier items get only a non-authoritative LLM verdict in autonomous verification; the verifier was told not to run Docker, so the cleanup state rests on the executor's recorded baseline diff"
  - test: "Optional, with HACS_ACTION_TOKEN (fine-grained, read-only, public repos): run `make hacs-action` and the negative control (temporary copy with category computers_network.bogus)"
    expected: "Positive run: LOCAL OVERLAY lines and all 10 checks passed; negative control: integration_categories fails, non-zero exit"
    why_human: "Needs a user credential; the overlay itself is proven without a token, the validator run is not"
---

# Phase 8: Marketplace + release readiness Verification Report

**Phase Goal:** The repository is ready for a 1.0.0 release and a `hacs/default` catalog submission: metadata, brand, documentation, CI and tooling meet the Marketplace/HACS requirements, shipped code is free of planning references, both validators pass locally, and the branch is pushed with a Draft PR — the release, tag and catalog PR themselves remain the user's action.
**Verified:** 2026-11-15T23:55:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

Binding context applied (user/manager): REL-07's hacs/action proof is deferred to the first PR CI run (M43, user decision 2026-11-15); the push and Draft PR are the manager's action after this verification (M41); the trademark assumption A3/A8 is an open user item. None of these is treated as a code gap.

## Gates run by the verifier (this session, HEAD 0da276a)

| Gate | Result |
|---|---|
| `uv run pytest -q` | 1180 passed, 5 warnings; `Required test coverage of 99.0% reached. Total coverage: 99.31%` |
| `uv run ruff check custom_components tests` | All checks passed |
| `uv run ruff format --check custom_components tests` | 50 files already formatted |
| `uv run mypy --strict custom_components/traefik_proxy` | Success: no issues found in 16 source files |
| `uv lock --check` | lock up to date (146 packages) |
| `make test-min-ha` (fresh `.venv-min-ha` from the hashed lock, HA 2026.11.0) | 1180 passed, coverage 99.31 %, no `Lingering` |

Not run by instruction: Docker (`make hassfest`, `make hacs-action`), any push, `gh` write call, `git ls-remote`.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | SC1: manifest has `categories: ["computers_network.monitoring"]`, version 1.0.0, hassfest key order; brand has trimmed/centred icons, logo / logo@2x (+ dark logos); `icon.svg` in `docs/`; local brand serving confirmed on HA 2026.11.0 | ✓ VERIFIED | Manifest key-order assertion passes; `hacs.json` homeassistant 2026.11.0. Icons 256x256 / 512x512, alpha bbox 256x231+0+12 / 512x461+0+25; logos 337x128 / 674x256 trimmed; brand set exactly six PNGs; `docs/icon.svg` history follows the move (4 commits). `tests/test_brand.py` 28 passed. 08-VISUAL-CHECK brand-serving table: six rows `200 image/png match`, and the recorded sha256 prefixes equal the current files' sha256 (e673beb5fb85, e25cb6e1626a, f0d7d448d440, 1e63160a40d7, 66228f7fe4ac, c37e8caf6661); dark device screenshot shows the dark logo |
| 2 | SC2: README rewritten (badge, basicAuth prerequisites, install/removal, options, entity table matching code, automations, troubleshooting, FAQ, trademark note), no private hosts; CHANGELOG 0.1.x–1.0.0 with breaking changes first | ✓ VERIFIED | 13 required `##` sections in order (+ License); My-link badge URL exact; consistency check vs en.json `missing: []`; private-host/Tailscale/192.168 grep and reload/YAML grep clean; no developers.home-assistant.io link. CHANGELOG headings `1.0.0 … 0.1.0` newest first, first `###` under 1.0.0 is "Breaking changes and required actions", required strings present, no internal IDs, compare links correct |
| 3 | SC3: pre-commit on py3.14 targeting traefik_proxy; coverage on `custom_components.traefik_proxy` with fail_under; Makefile = CI; CI on push/PR/schedule/dispatch with HA 2026.11 job; every action pinned; release workflow fails on tag != manifest; no SyntaxWarning, no real multi-second sleeps | ✓ VERIFIED | `.pre-commit-config.yaml` python3.14, 7× `custom_components/traefik_proxy`, 0× old path; pyproject `--cov=custom_components.traefik_proxy`, `fail_under = 99`, `error::SyntaxWarning`. Parity check `missing: []`; 11 `uses:` lines, 0 unpinned; every job has timeout, none has `needs`; triggers push[main], pull_request[main], cron `17 3 * * *`, workflow_dispatch; `permissions: {}`; no `${{` in a release `run:`. `check_release_tag.py` v1.0.0→0, v1.0.1→1, vv1.0.0→1. Guards `test_no_syntax_warning_on_compile`, `test_no_real_multi_second_sleep_in_tests` pass |
| 4 | SC4: planning-reference grep over `custom_components/` returns nothing; CLAUDE.md describes `custom_components/traefik_proxy` and routes to the renamed skill | ✓ VERIFIED | Grep (`CONTEXT.md|PITFALLS|\bD-[0-9]|BLOCKER|Phase [0-9]|.planning/|.claude/|spike|Plan NN-NN`, *.py/*.json) exit 1 = no match; guard test passes and is non-vacuous. CLAUDE.md contains traefik_proxy, 2026.11.0, contributors.home-assistant.io, the renamed skill, skill-routing and profile blocks; stale-term grep clean; routing path resolves; generator rerun on a scratch copy is byte-identical (idempotent) |
| 5 | SC5a: local hassfest passes | ✓ VERIFIED | Recorded three times (08-08, 08-13 final run, after WR-03 with digest pin + read-only mount): `Integrations: 1 / Invalid integrations: 0`, exit 0. Not rerun by the verifier (Docker excluded by instruction); offline `scripts/hassfest_checks.py all` passes |
| 6 | SC5b: local `hacs/action` (category integration, no ignore) passes | ? UNCERTAIN (human / CI) | Not run (user decision M43). Overlay harness proven on the image digest without a token (fail-closed guard, file list from `git ls-files -co --exclude-standard`); five public metadata checks green. Proof deferred to the first PR CI run — see Human Verification 1 |
| 7 | SC5c: release notes and the hacs/default PR text drafted in `.planning/` | ✓ VERIFIED | `08-RELEASE-NOTES-v1.0.0.md` (first `##` = Required actions, CHANGELOG link), `08-HACS-DEFAULT-PR.md` (exact line, `<RELEASE_URL>` markers, "no review"), `08-DRAFT-PR.md`; all only in the phase directory; private-name/token grep clean |
| 8 | SC5d: `feat/marketplace-polish` is pushed and a Draft PR to main is open | ? UNCERTAIN (manager action) | By design not done (M41). Push readiness verified: tree clean except `.planning/config.json` (M) and `.planning/state.json` (??); no upstream configured; no `origin/*marketplace-polish` remote-tracking ref; 342 commits ahead of `origin/main`; drafts present. See Human Verification 2 |
| 9 | SC5e: no tag, release or hacs/default PR created by the assistant; tests, ruff, mypy --strict green | ✓ VERIFIED | `git tag --list` = v0.1.0 v0.1.1 v0.1.2 v0.1.3 v0.1.4 v0.1.6 v0.2.0 v0.2.1 v0.3.0 (unchanged); gates table above all green |
| 10 | 08-01: diagnostics redact Header/HeaderRegexp/Headers/HeadersRegexp/Query/QueryRegexp values (v2/v3, both quote styles), unparseable rules whole, router errors that repeat or quote values fail closed; entity attributes stay raw | ✓ VERIFIED | `rules.redact_rule`, `has_matcher_call`, `rule_secret_values`; `diagnostics._redact_router_rules` / `_redact_error` applied before `async_redact_data`; `rules.py` has no HA import. Tests pass: `test_redact_rule_table`, `test_redact_rule_random_rules_never_leak`, `test_diagnostics_redact_header_value_in_router_rule`, `test_diagnostics_redact_router_errors_that_repeat_the_rule`, `test_diagnostics_redact_regexp_errors_that_quote_a_header_value` (review WR-01), `test_redact_error_fails_closed` |
| 11 | 08-02: probe cycle resolves the Traefik host once per cycle (IP literal skips lookup), probes use resolved addresses with router host as SNI (review WR-02: addresses tried in order), lookup failure = DNS failure for every host; `certificates_failed` chained `from _logged_cause`; deterministic socket tests and teardown; per-host leak guard; `RAWDATA_PROBE_INTERVAL`, `_interval_elapsed(since, interval)`, `_probe_clock`; switch debug line; capture byte-stability note | ✓ VERIFIED | Code at `cert_coordinator.py:66,330,397`, `coordinator.py:55,185,226`, `api.py:352`; `_probe_armed_at` 0 hits; no `asyncio.sleep(0.2)`; `tls_server` teardown awaits `wait_closed` before `pytest.fail`. Named tests exist and pass in the 1180 run (resolve-once, ip-literal, resolve-failure, chain cause ×2, closed port, cancellation ×2, per-host state, five probe-clock tests, two switch-log tests, four address-fallback tests) |
| 12 | 08-03: `entities_migrated` names the post-migration title; en/de text on kept IDs of disabled or hidden routers; DEVICE→USER only for disabled legacy devices; single cert host normalisation point; defence branches commented; planning-ref / doc-link / SyntaxWarning / sleep guards non-vacuous | ✓ VERIFIED | `__init__.py:234` `device.disabled`; en "disabled or hidden" / de "deaktivierte oder ausgeblendete"; `.lower()` count in entity.py 0; "hand-edited" in config_flow.py and `__init__.py`; tests `test_migration_issue_names_title_after_migration`, `test_title_migration_updates_existing_issue`, `test_device_disabled_mapping_is_scoped_and_idempotent`, `test_disabled_router_replacement_keeps_disabled_state`, `test_cert_factory_unique_id_round_trips_through_key_of`, four guards + detector self-check pass. Real 0.3.0 → 1.0.0 repair screenshot (en-12) shows title "traefik-v3", kept-ID sentence and removed count 101 |
| 13 | 08-04/05: brand geometry, interlacing, exact file set, light vs dark wordmark; `docs/BRAND.md` with source tag v3.7.19 + SHA 7dafd6d…, MIT notice, trademark statement, export commands | ✓ VERIFIED | `magick identify`: all RGBA, interlaced; xmllint passes on both logo SVGs (`viewBox="0 0 280 108"`); BRAND.md greps pass; brand tests 28 passed |
| 14 | 08-06: hashed min-HA lock + `make test-min-ha` (three commands, no addopts override); coverage gate bites; pre-commit on traefik_proxy; `hassfest_checks.py` strings-shape forbids only reauth/reconfigure; Makefile CI strings | ✓ VERIFIED | Lock: 2832 hashes, `pytest-homeassistant==2026.11.0` once; `.venv-min-ha/` ignored; verifier ran `make test-min-ha` → 1180 passed; `hassfest_checks.py all` exit 0; `forbidden_top = {"reauth", "reconfigure"}` |
| 15 | 08-07: release.yml (`release: published`, `push: tags v*`, `permissions: {}`, 5 min timeout, tag via env); validate.yml triggers, pins, timeouts, locked min-HA job with Makefile commands; dependabot github-actions weekly | ✓ VERIFIED | See truth 3; `tests/test_release_tag_check.py` 6 tests pass; dependabot.yml parses |
| 16 | 08-08: release identity 1.0.0 agrees (manifest, pyproject, tag check); `make hassfest` and `make hacs-action` targets; overlay refuses to run as a no-op; token only by variable name (review CR-01: opt-in `HACS_ACTION_TOKEN`, digest-pinned image, no `gh auth token`) | ✓ VERIFIED | pyproject version 1.0.0; Makefile targets read; `hacs_action_local.py:135-136` hasattr guard, `LOCAL OVERLAY` lines; Makefile has no `gh auth token` call (only a warning comment) and exits 2 without the variable |
| 17 | 08-09: visual check in de/en (config flow none/basic/bearer, options units, repairs, device tree, states/icons, Refresh now, light/dark), real migration repair, no untranslated keys, screenshots < 500 KB / ≤ 5 MB, findings handled | ✓ VERIFIED | 13 de + 13 en JPEGs, none ≥ 500 KB, 1956 KB total; report sections Setup, Brand serving, Tool provenance, Screenshots, Findings, Migration, Cleanup; JWT grep 0; F-01 cosmetic, F-02 upstream in `deferred-items.md`; no `fix(08-09)` commit needed. Verifier inspected en-12 and de-13 |
| 18 | 08-10: README/CHANGELOG content truths (entity table from code, data-update cadence, FAQ answers out-of-scope rows, trademark note linking docs/BRAND.md; Keep a Changelog, every tag once, dates, compare links) | ✓ VERIFIED | See truth 2; trademark section states Traefik Labs' guidelines were not reviewed and no permission is claimed (A3/A8 stated honestly); FAQ covers config edits, ACME, v1, TCP/UDP, middleware entities, reload/actions, acme.json, Enterprise, DNS probe mode |
| 19 | 08-11: skill `git mv`-renamed, `name:` equals directory, no old paths; PROJECT.md/STACK.md shipped state; CLAUDE.md regenerated, no hand edits | ✓ VERIFIED | `test -f` new SKILL.md, old directory gone; stale-path greps clean; PROJECT.md title "Home Assistant Traefik Proxy Integration"; generator idempotency confirmed on a scratch copy |
| 20 | 08-12: ENT-09 names `config_entry_id`; Probatio row "probatio as vol"; footer equals the traceability table; no `open` disposition in 04/05/06; Phase 7 deferred rows carry commits | ✓ VERIFIED | Footer script: footer (87, 78, 76, 2, 9) == table; `open: 0`; no open rows/frontmatter; no "deferred to Phase 8 \| - \|" row |
| 21 | 08-13: deferred-items of Phases 4/5/7 resolved with commit pointers; final pre-push run recorded; clean tree, unchanged tags, no remote ref | ✓ VERIFIED | 04: 2× `status: resolved`, no `status: open`; 05/07: ≥ 2 resolved markers with hashes; "Final pre-push run" section present; tree/tag/upstream checks in truth 8/9 |
| 22 | Post-execution review: CR-01 and WR-01..WR-04 fixed in code (407b55f, dd4e3f4, ca1f5eb, b17dda4, 759874c) | ✓ VERIFIED | CR-01/WR-03 in Makefile and validate.yml comments; WR-01/WR-02 tests listed in truths 10/11 pass; WR-04: `uv.lock` tracked, `uv lock --check` passes, `uv sync --locked` + `UV_LOCKED: "1"` in CI, `export UV_LOCKED := 1` in Makefile |

**Score:** 20/22 truths verified (0 present, behavior-unverified; 2 uncertain, both routed to human/manager by binding decision)

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `custom_components/traefik_proxy/rules.py` | redact_rule, has_matcher_call, rule_secret_values | ✓ VERIFIED | pure module, 100 % covered |
| `custom_components/traefik_proxy/diagnostics.py` | router rule/errors redaction | ✓ VERIFIED | wired before `async_redact_data` (line 126) |
| `custom_components/traefik_proxy/cert_coordinator.py` | once-per-cycle resolution, chained cause | ✓ VERIFIED | getaddrinfo line 397, `from _logged_cause(err)` line 330 |
| `custom_components/traefik_proxy/coordinator.py` | RAWDATA_PROBE_INTERVAL, _probe_clock | ✓ VERIFIED | |
| `custom_components/traefik_proxy/api.py` | switch debug line | ✓ VERIFIED | line 352 |
| `custom_components/traefik_proxy/__init__.py` | final-title repair, disabled-device mapping | ✓ VERIFIED | |
| `custom_components/traefik_proxy/translations/{en,de}.json` | kept-ID wording | ✓ VERIFIED | |
| `custom_components/traefik_proxy/manifest.json` | 1.0.0 + category | ✓ VERIFIED | |
| `custom_components/traefik_proxy/brand/*.png` (6) | trimmed icons, logos, dark logos | ✓ VERIFIED | |
| `docs/icon.svg`, `docs/logo.svg`, `docs/logo-dark.svg`, `docs/BRAND.md` | sources, provenance | ✓ VERIFIED | |
| `tests/test_baseline_guards.py`, `tests/test_brand.py`, `tests/test_release_tag_check.py` | guards | ✓ VERIFIED | all pass |
| `.github/requirements-min-ha.{in,txt}`, `Makefile`, `pyproject.toml`, `.pre-commit-config.yaml`, `scripts/pre-commit`, `scripts/hassfest_checks.py` | tooling | ✓ VERIFIED | |
| `.github/workflows/{validate,release}.yml`, `.github/dependabot.yml`, `scripts/check_release_tag.py` | CI + release gate | ✓ VERIFIED | |
| `scripts/hacs_action_local.py` | fail-closed overlay | ✓ VERIFIED (exists, wired via `make hacs-action`) | validator run itself pending CI |
| `README.md`, `CHANGELOG.md` | Marketplace docs | ✓ VERIFIED | |
| `CLAUDE.md`, renamed skill | project instructions | ✓ VERIFIED | |
| `08-LOCAL-VALIDATION.md`, `08-VISUAL-CHECK.md`, three drafts | evidence and drafts | ✓ VERIFIED | `All (10) checks passed` deliberately absent (not run) |

### Key Link Verification

| From | To | Via | Status |
|---|---|---|---|
| diagnostics.py | rules.py | `redact_rule(` / `rule_secret_values(` | ✓ WIRED |
| cert_coordinator.py | coordinator.py | `from .coordinator import _logged_cause` | ✓ WIRED |
| cert_coordinator.py | tls.async_probe_certificate | resolved address as connect host, router host as SNI | ✓ WIRED (tests) |
| test_baseline_guards.py | custom_components/traefik_proxy/ | `PLANNING_REFS` byte scan | ✓ WIRED |
| `__init__.py` async_migrate_entry | issue_registry | `entities_migrated` after last step | ✓ WIRED |
| test_brand.py | brand/*.png | Pillow alpha bbox | ✓ WIRED |
| Makefile test-min-ha / validate.yml test-min-ha | requirements-min-ha.txt | `uv pip sync --require-hashes` | ✓ WIRED (parity `missing: []`) |
| pyproject addopts | custom_components.traefik_proxy | `--cov=` + `fail_under` | ✓ WIRED (99.31 % reached) |
| release.yml | manifest.json | `scripts/check_release_tag.py "$TAG"` | ✓ WIRED |
| Makefile hacs-action | scripts/hacs_action_local.py | `--entrypoint python3 … /harness/hacs_action_local.py` | ✓ WIRED (not executed) |
| CLAUDE.md skill-routing marker | renamed SKILL.md | source path | ✓ WIRED |
| README Entities table | translations/en.json | consistency check | ✓ WIRED |
| 07-REVIEW-FIX.md deferred rows | Phase 8 commits | commit column | ✓ WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real data | Status |
|---|---|---|---|---|
| diagnostics download `routers[*].rule/errors` | snapshot from coordinator | `_jsonable(dataclasses.asdict(snapshot))` → `_redact_router_rules` | yes (integration tests use real fixture rawdata) | ✓ FLOWING |
| `entities_migrated` placeholders | entry title / removed count | migration steps | yes (real 0.3.0 migration in 08-09, removed_count 101) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Tag check accepts v1.0.0, rejects v1.0.1 / vv1.0.0 | `python3 scripts/check_release_tag.py …` | 0 / 1 / 1 with `::error::` | ✓ PASS |
| Manifest identity and key order | python json assertion | `manifest ok` | ✓ PASS |
| Makefile/CI parity | yaml parity script | `missing: []` | ✓ PASS |
| README consistency | en.json script | `missing: []` | ✓ PASS |
| REQUIREMENTS footer | recount script | footer == table | ✓ PASS |
| CLAUDE.md generator idempotent | generator on scratch copy + `diff -q` | identical | ✓ PASS |
| Full suite + coverage | `uv run pytest -q` | 1180 passed, 99.31 % | ✓ PASS |
| Minimum-HA suite | `make test-min-ha` | 1180 passed | ✓ PASS |
| hassfest / hacs/action containers | `make hassfest` / `make hacs-action` | not run (instruction) | ? SKIP |

### Probe Execution

No `scripts/*/tests/probe-*.sh` exists and no plan declares one. Step 7c: not applicable.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| REL-01 | 08-07, 08-08 | categories, sorted keys, version 1.0.0, hacs.json 2026.11.0 | ✓ SATISFIED | truth 1, 16 |
| REL-02 | 08-04, 08-05, 08-09, 08-10 | brand re-export, logos, icon.svg in docs, local serving, trademark note | ✓ SATISFIED | truths 1, 13, 17, 18 (trademark decision itself is a user item) |
| REL-03 | 08-10 | README rewritten, no private hosts | ✓ SATISFIED | truth 2, 18 |
| REL-04 | 08-02, 08-03, 08-06, 08-07 | tooling consistent, no SyntaxWarning, no multi-second sleeps | ✓ SATISFIED | truths 3, 11, 12, 14 |
| REL-05 | 08-07 | CI triggers, HA 2026.11 job, pinned actions | ✓ SATISFIED (config); first GitHub run is in human item 1 | truth 15 |
| REL-06 | 08-01, 08-03, 08-11, 08-12 | no planning references, CLAUDE.md/skill, contributor doc links | ✓ SATISFIED | truths 4, 10, 12, 19, 20 |
| REL-07 | 08-08, 08-13 | local hassfest + hacs/action pass; drafts in `.planning/` | ? NEEDS HUMAN | hassfest + drafts satisfied; hacs/action deferred to first PR CI run (M43) |
| REL-08 | 08-13 | branch pushed + Draft PR; no tag/release/hacs-default PR by assistant | ? NEEDS HUMAN | push readiness and "no tag/release/PR" verified; push + Draft PR = manager action (M41) |
| DIST-04 | 08-07 | hassfest, HACS and pytest workflows; release workflow tag == manifest | ✓ SATISFIED | truth 15 (flagged: SHA pins freeze only the wrappers of hassfest/hacs, documented in validate.yml) |
| DOCS-02 | 08-10 | CHANGELOG for first release and every tag | ✓ SATISFIED | truth 2 |
| DOCS-04 | 08-10 | FAQ on locked-out anti-features | ✓ SATISFIED | truth 18 |

All 11 phase requirement IDs appear in at least one plan's `requirements:`; REQUIREMENTS.md maps no further ID to Phase 8 (no orphans). REQUIREMENTS.md correctly keeps REL-07 "Pending (first PR CI run, M43)" and REL-08 "Pending".

### Prohibitions (must-NOT)

| Prohibition | Tier | Disposition |
|---|---|---|
| No header/query matcher value in the diagnostics download (REL-06) | test | ✓ enforced by redaction tests incl. fuzz and WR-01 regexp-error case |
| No planning references in `custom_components/` (REL-06) | test | ✓ enforced by `test_shipped_code_has_no_planning_references` |
| No hand edits in CLAUDE.md GSD markers (REL-06) | test | ✓ generator rerun is byte-identical |
| No private hosts in README/CHANGELOG; no removed feature advertised (REL-03) | test | ✓ grep gates clean |
| Drafts only in the phase directory; no private hosts/tokens in drafts (REL-07) | test | ✓ `git ls-files` location check and grep clean |
| No push/tag/release/PR/fork; no push to satisfy GitHub-only checks (REL-08, REL-07) | test | ✓ local evidence: tags unchanged, no upstream, no remote-tracking ref (`git ls-remote` not run by instruction) |
| No real HA instance; no leftover container/network/volume (REL-02) | test | flagged — rests on the executor's recorded baseline diff; verifier did not run Docker (human item 4) |
| Never print/log/write the GitHub token (REL-07) | judgment | flagged, non-authoritative LLM verdict: holds (token passed by variable name only; no token pattern in evidence; the run never happened) — unverified-prohibition, human review recommended |
| Never show HA access/refresh tokens in screenshots or report (REL-02) | judgment | flagged, non-authoritative LLM verdict: holds (JWT grep 0 on the report; inspected screenshots show none) — unverified-prohibition, human review recommended |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| (all 69 phase-modified files) | — | `TBD` / `FIXME` / `XXX` | — | none found |
| `.planning/phases/08-marketplace-release-readiness/08-DRAFT-PR.md` | 73, 75 | stale evidence: 1152 passed / 99.29 % (pre-review); review fixes and committed `uv.lock` not mentioned | ⚠️ Warning | PR body would understate the final state; refresh before pasting (human item 2) |
| `08-REVIEW-DISPOSITION.md` | — | IN-01..IN-06 `open` (info) | ℹ️ Info | not blocking; IN-01 (attributes keep raw rule), IN-02 (repair issue after 1.3 step), IN-03 (`UnicodeError` from getaddrinfo), IN-04 (release check after publication / fires twice), IN-05 (overlay URL parsing), IN-06 (partial runs need `--no-cov`, x86-only lock) are candidates for triage before or after 1.0.0 |
| `08-LOCAL-VALIDATION.md` | 16 | historical hassfest command with `--pull always` | ℹ️ Info | superseded by the WR-03 note in the same section |

### Human Verification Required

### 1. First Draft-PR CI run (REL-07, REL-05)

**Test:** After the manager's push, open the first run of `validate.yml` on the Draft PR.
**Expected:** HACS job green with all 10 hacs/action checks passed (5 checks = failure); lint, test (`uv sync --locked`), test-min-ha (hashed install), hassfest green.
**Why human:** User decision 2026-11-15 (M43): the official hacs/action validators need a GitHub token and are proven only by CI.

### 2. Push and Draft PR (REL-08)

**Test:** Manager runs `git ls-remote origin`, pushes `feat/marketplace-polish`, opens the Draft PR to `main` with `08-DRAFT-PR.md`.
**Expected:** Draft PR open; no tag, release or hacs/default PR. Before pasting, update the evidence table to 1180 passed / 99.31 % and mention the review fixes (CR-01, WR-01..WR-04, committed `uv.lock`).
**Why human:** M41 — the push is the manager's action after verification.

### 3. Logo trademark (A3/A8)

**Test:** Decide whether to keep the Traefik Proxy logo lockup.
**Expected:** Keep (README and `docs/BRAND.md` state honestly that the guidelines were not reviewed and no permission is claimed) or apply the icon-only fallback before release.
**Why human:** Legal/brand judgment.

### 4. Flagged prohibitions

**Test:** Skim 08-08/08-09 evidence for tokens; run `docker ps -a`, `docker network ls`, `docker volume ls`.
**Expected:** No GitHub or HA token anywhere; no `ha-visual-08*` / `traefik-harness*` leftovers.
**Why human:** Judgment-tier prohibitions get only a non-authoritative verdict; the verifier did not run Docker.

### 5. Optional local hacs/action run

**Test:** With `HACS_ACTION_TOKEN` (fine-grained, read-only, public repos) run `make hacs-action` and the negative control.
**Expected:** 10 checks passed; negative control fails `integration_categories`.
**Why human:** Needs a user credential.

### Gaps Summary

No code or documentation gap blocks the phase goal inside this run's reach. Every must-have the executors could achieve is present, substantive, wired and, where behaviour-dependent, covered by passing tests (1180 tests, 99.31 % coverage, identical on the locked HA 2026.11.0 stack). The two open truths are exactly the items the user and manager reserved: the official hacs/action validator run (REL-07, deferred to the first PR CI run) and the push plus Draft PR (REL-08, manager action M41). The trademark question A3/A8 stays a user decision; the README states it honestly. One warning: refresh the stale evidence numbers in `08-DRAFT-PR.md` before opening the PR.

---

_Verified: 2026-11-15T23:55:00Z_
_Verifier: Claude (gsd-verifier)_
