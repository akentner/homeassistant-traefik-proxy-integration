---
phase: "08"
slug: "marketplace-release-readiness"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
block_on: high
created: "2026-11-16"
---

# Phase 08 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time (08-01..08-13 `<threat_model>` blocks: 47 rows, IDs T-08-01..T-08-34 plus one
> T-08-SC per plan); verified at ASVS L1 by gsd-security-auditor at HEAD add0599 (focused threat modules: 314 passed).
> The one non-blocking gap (T-08-20, overlay negative control) was closed in a0e3bb7. Full gates after the fix:
> 1190 passed, coverage 99.31 %, ruff, mypy --strict, minimum HA 2026.11.0 run 1190 passed.
> Paths: `cc/` = `custom_components/traefik_proxy/`.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Traefik API → integration | Router rules and errors are untrusted text | Rule strings, router/service/middleware errors |
| Diagnostics download → public issue tracker | The file leaves the user's trust domain | Redacted entry data, parsed snapshot with redacted rules/errors |
| Integration → DNS / Traefik host | Probe connections and name resolution leave the process | Host names, one resolution per cert cycle |
| Exception chain → HA log | Logged tracebacks are read by users and posted in issues | Exception causes (invalid-URL causes dropped) |
| Stored config entry / registries → migration | Persisted data may be hand-edited or stale | Device/entity disabled_by, titles |
| Shipped package / repository docs → public users | Comments, images and docs are world-readable | Code comments, brand PNGs, README, CHANGELOG |
| GitHub (traefik/traefik) → local scratch | Downloaded source is untrusted data | `Logo.tsx` text (never executed) |
| PyPI → local / CI test venv | Packages for the minimum-HA job and ephemeral tools | Hashed lock, `uvx pre-commit`, Playwright |
| pre-commit fixers → working tree | Hooks rewrite files in place | Planning docs and captured fixtures (excluded) |
| Third-party GitHub Actions → CI runner | Action code runs with the workflow token | `GITHUB_TOKEN` (`permissions: {}`) |
| Tag / release name → workflow shell | Attacker-influenced event text reaches a run step | Tag string via `env: TAG` and argv only |
| Host → validator containers | Repository mounted read-only into third-party images | Working tree (`:ro`), harness file list |
| Host credential store → hacs/action container | A GitHub token enters the container | Opt-in fine-grained `HACS_ACTION_TOKEN`, by env name only |
| Host → throwaway HA/Traefik containers, browser automation | Local visual check | HA access/refresh tokens (0600 scratch), ports on 127.0.0.1 |
| Repository instructions → future AI sessions | Stale guidance steers later changes | CLAUDE.md, project skill |
| Planning records → verifier / future phases | Review dispositions | Disposition tables |
| Local branch / drafts → GitHub and public PRs | Publishing is the user's action only | Branch, tags, draft PR / release text |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-08-01 | Information Disclosure | router `rule` in diagnostics snapshot | high | mitigate | `_redact_router_rules` runs `redact_rule` on every router (cc/diagnostics.py:89-97, :126); fail-closed tokenizer cc/rules.py:146-263; `test_redact_rule_table` (21 cases), `test_diagnostics_redact_header_value_in_router_rule` | closed |
| T-08-02 | Information Disclosure | router `errors` echoing the rule | medium | mitigate | `_redact_error` cc/diagnostics.py:69-86 (verbatim rule replaced; whole error redacted on unparsable rule, matcher call, hidden value or quoted text); `test_redact_error_fails_closed` (10 rows) + two integration tests | closed |
| T-08-03 | Denial of Service | crafted rule fed to the tokenizer | low | mitigate | single linear `_TOKEN.match` pass, never raises; `test_redact_rule_random_rules_never_leak` (200 rules); auditor timing 600 k chars in 0.05 s | closed |
| T-08-04 | Information Disclosure | router sensor `rule`/`errors` attributes | low | accept | AR-08-01 | closed |
| T-08-SC (08-01) | Tampering | npm/pip/cargo installs | low | accept | AR-08-03 | closed |
| T-08-05 | Denial of Service | per-probe name resolution | low | mitigate | one `loop.getaddrinfo` per cycle inside `asyncio.timeout` (cc/cert_coordinator.py:396-397, :453); `test_probe_cycle_resolves_traefik_host_once_per_cycle`, `test_probe_cycle_ip_literal_skips_getaddrinfo` | closed |
| T-08-06 | Information Disclosure | `certificates_failed` exception chain | medium | mitigate | `from _logged_cause(err)` cc/cert_coordinator.py:330; `test_certificates_invalid_url_error_chains_no_cause` | closed |
| T-08-07 | Denial of Service | per-host state growth in CertCoordinator | low | mitigate | `test_cert_coordinator_keeps_no_per_host_state_besides_data` over `vars(c)` (tests/test_cert_coordinator.py:1317-1345) | closed |
| T-08-SC (08-02) | Tampering | npm/pip/cargo installs | low | accept | AR-08-03 | closed |
| T-08-08 | Information Disclosure | planning references in `custom_components/` | low | mitigate | `test_shipped_code_has_no_planning_references` + non-vacuous check (tests/test_baseline_guards.py); grep 0 hits | closed |
| T-08-09 | Tampering | 1.1 → 1.2 DEVICE → USER mapping | low | mitigate | restricted to disabled legacy devices (cc/__init__.py:234, :247-251, :274-278); `test_device_disabled_mapping_is_scoped_and_idempotent`, `test_disabled_router_replacement_keeps_disabled_state` | closed |
| T-08-10 | Repudiation | migration repair text/title | low | mitigate | issue raised after the 1.3 step (cc/__init__.py:327-328); en/de text names kept IDs; `test_migration_issue_names_title_after_migration`, `test_title_migration_updates_existing_issue` | closed |
| T-08-SC (08-03) | Tampering | npm/pip/cargo installs | low | accept | AR-08-03 | closed |
| T-08-32 | Tampering | re-exported icon PNGs | low | mitigate | export recipe from `docs/icon.svg` in docs/BRAND.md; Pillow geometry guards and `MAX_IMAGE_BYTES` gate in tests/test_brand.py (largest PNG 44.6 KB) | closed |
| T-08-SC (08-04) | Tampering | npm/pip/cargo installs | low | accept | AR-08-03 | closed |
| T-08-11 | Tampering | downloaded `Logo.tsx` | low | mitigate | read-only fetch at pinned tag, text-only transform with `python3 -I` (08-05-SUMMARY); `docs/*.svg` have no script/handlers/hrefs/foreignObject, `xmllint --noout` passes | closed |
| T-08-12 | Spoofing | Traefik Labs logo (trademark) | low | transfer | MIT notice + trademark/non-affiliation in docs/BRAND.md:73-78 and README.md:427-441 | closed |
| T-08-SC (08-05) | Tampering | npm/pip/cargo installs | low | accept | AR-08-03 | closed |
| T-08-15 | Tampering | minimum-HA dependency set | medium | mitigate | `.github/requirements-min-ha.txt`: 123 `==` pins, all with `--hash=sha256`; CI (validate.yml) and Makefile run `uv venv --clear` + `uv pip sync --require-hashes` | closed |
| T-08-33 | Tampering | pre-commit fixers rewriting planning docs / fixtures | low | mitigate | `.pre-commit-config.yaml:18` `exclude: ^(\.planning/\|tests/fixtures/)`; clean second run recorded in 08-06-SUMMARY | closed |
| T-08-SC (08-06) | Tampering | `uvx pre-commit`, min-HA lock packages | medium | mitigate | pre-commit ephemeral (`make pre-commit` = `uvx pre-commit`), not in pyproject/manifest; provenance in 08-06-SUMMARY; lock pins `homeassistant==2026.11.0` and `pytest-homeassistant==2026.11.0` with hashes | closed |
| T-08-13 | Tampering | action references | high | mitigate | all 11 `uses:` pinned to 40-hex SHAs with version comments (10 validate.yml, 1 release.yml), 0 unpinned; `.github/dependabot.yml` weekly github-actions | closed |
| T-08-14 | Tampering | script injection via tag name | high | mitigate | only `${{` is `env: TAG` (release.yml:21); `run:` reads `"$TAG"` (:22); `scripts/check_release_tag.py` reads argv only | closed |
| T-08-16 | Elevation of Privilege | workflow token scope | medium | mitigate | `permissions: {}` top-level in validate.yml:23 and release.yml:9; no job widens it | closed |
| T-08-17 | Tampering | floating validator images behind SHA-pinned actions | low | accept | AR-08-02 | closed |
| T-08-18 | Denial of Service | hung CI job | low | mitigate | `timeout-minutes` on every job (15 in validate.yml, 5 in release.yml) | closed |
| T-08-SC (08-07) | Tampering | npm/pip/cargo installs | low | accept | AR-08-03 | closed |
| T-08-19 | Information Disclosure | GitHub token in the local hacs/action run | high | mitigate | Makefile:74-75 `INPUT_GITHUB_TOKEN="$$HACS_ACTION_TOKEN" docker run … -e INPUT_GITHUB_TOKEN` (name only, `@` recipe not echoed); opt-in fine-grained read-only token, no `gh auth token` (review CR-01); exits 2 without the variable; token-shape grep over tracked files, `.planning/` and main..HEAD: 0 hits | closed |
| T-08-20 | Tampering | overlay silently not applied | medium | mitigate | `hasattr` guard before and identity check after patching (scripts/hacs_action_local.py `_apply`), `LOCAL OVERLAY` lines; **a0e3bb7**: guard now runs before any patch target is read (a missing `async_download_file` crashed with AttributeError before); tests/test_hacs_action_local.py (10 tests: missing/shadowed targets exit 1, empty list exit 1, bogus local category reaches the validators, unlisted files not served); offline probe in the pinned image digest: positive run exit 0, removed method → `LOCAL OVERLAY ERROR`, exit 1. Full-validator negative control with a token not run (see observations) | closed |
| T-08-21 | Tampering | containers writing into the working tree | low | mitigate | hassfest `--rm` + `:/github/workspace:ro` (Makefile:59); hacs-action `--rm`, `/repo:ro`, `/harness:ro` (Makefile:74-77) | closed |
| T-08-SC (08-08) | Tampering | floating validator images | low | accept | AR-08-04 | closed |
| T-08-22 | Information Disclosure | HA access/refresh tokens (visual check) | medium | mitigate | 0600 scratch file, never printed, deleted at teardown (08-VISUAL-CHECK.md); 08-09 scratch holds no token; JWT grep over report and `.planning/`: 0 hits | closed |
| T-08-23 | Denial of Service | leftover containers/networks/volumes | low | mitigate | `docker ps -a` / `volume ls` / `network ls` equal `~/.cache/traefik-proxy-integration/docker-baseline-phase8.txt` | closed |
| T-08-24 | Tampering | root-owned files from HA | low | mitigate | named volumes, integration `:ro`; no foreign-owned file in the repo; `git status` clean for `custom_components tests` | closed |
| T-08-25 | Information Disclosure | HA reachable from the network | low | mitigate | ports bound to `127.0.0.1:18123/18124`; tests/traefik/compose.yaml:42/:48 bind 127.0.0.1 | closed |
| T-08-34 | Tampering | unplanned code change from a visual finding | medium | mitigate | no `fix(08-09)` commit needed (F-01 cosmetic, F-02 upstream); all 08-09 commits touch `.planning/` only | closed |
| T-08-SC (08-09) | Tampering | Playwright (ephemeral) | medium | mitigate | `uv run --no-project --with playwright` only; version/author in 08-VISUAL-CHECK.md:74; absent from pyproject, uv.lock, manifest, min-HA lock | closed |
| T-08-26 | Information Disclosure | private host names in README/CHANGELOG | medium | mitigate | case-insensitive grep (HA host names, n2plus/odroid, ts.net/tailscale/tailnet, RFC1918/CGNAT IPs, .lan/.local/.fritz.box/.home.arpa): 0 hits | closed |
| T-08-27 | Repudiation | docs promising removed features / wrong defaults | low | mitigate | README options table = cc/const.py ranges and defaults; "no YAML configuration" (README:114); FAQ "no reload action" (:408-409) | closed |
| T-08-SC (08-10) | Tampering | npm/pip/cargo installs | low | accept | AR-08-03 | closed |
| T-08-28 | Tampering | stale CLAUDE.md / skill guidance | low | mitigate | stale-term negative gates pass; SKILL.md:16 names `tls.py` authoritative; `to_thread` only as forbidden in CLAUDE.md | closed |
| T-08-SC (08-11) | Tampering | npm/pip/cargo installs | low | accept | AR-08-03 | closed |
| T-08-29 | Repudiation | review findings without a decision (04-07) | low | mitigate | no `\| open \|` row or `disposition: open` in 04/05/06-REVIEW-DISPOSITION.md | closed |
| T-08-SC (08-12) | Tampering | npm/pip/cargo installs | low | accept | AR-08-03 | closed |
| T-08-30 | Elevation of Privilege | accidental publication by the executor | high | mitigate | tags unchanged (v0.1.0..v0.3.0, no v1.0.0); origin/main unchanged at 8849929; no branch ref at 08-13 end; the later `origin/feat/marketplace-polish` push (2026-11-15 23:33) is the M41 feature-branch push outside the executor | closed |
| T-08-31 | Information Disclosure | host names / tokens / harness credentials in drafts | medium | mitigate | grep over 08-DRAFT-PR.md, 08-HACS-DEFAULT-PR.md, 08-RELEASE-NOTES-v1.0.0.md: 0 hits | closed |
| T-08-SC (08-13) | Tampering | `uvx pre-commit`, lock install | low | accept | AR-08-03 | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-08-01 | T-08-04 | D-29 / decision W76: M40 redaction applies to the diagnostics download only; entity attributes stay raw for the user's own HA. Integration tests pin the raw attributes. Note: review IN-01 shows the attributes also reach the recorder and non-admin users, so "same trust domain" is weaker than written (see observations) | user decision W76 (D-29); verified by gsd-security-auditor | 2026-11-16 |
| AR-08-02 | T-08-17 | `hassfest:latest` / `hacs/action:main` behind SHA-pinned wrappers is upstream design and matches what catalog reviewers run (flagged assumption DIST-04, validate.yml:6-9); local runs pin both images by digest | plan threat model; verified by gsd-security-auditor | 2026-11-16 |
| AR-08-03 | T-08-SC (08-01, 02, 03, 04, 05, 07, 10, 11, 12, 13) | No new dependency in pyproject, manifest (`requirements: []`) or hacs.json across Phase 8; tools only ephemeral or already bundled (Pillow) | plan threat model; verified by gsd-security-auditor | 2026-11-16 |
| AR-08-04 | T-08-SC (08-08) | Floating validator images pulled for local validation; digests recorded in 08-LOCAL-VALIDATION.md:14/:69 and since pinned in the Makefile | plan threat model; verified by gsd-security-auditor | 2026-11-16 |

*Accepted risks do not resurface in future audit runs.*

### Non-blocking observations (for the release / next milestone)

- T-08-20 residual: the full-validator negative control (unknown category → failed `integration_categories`) has not run against the shipped overlay; it needs `HACS_ACTION_TOKEN`, which agents never handle. The overlay-level part is now pinned by tests and an offline probe in the pinned image; the HACS CI job on the PR head is the authoritative validator.
- Leftover dead HA tokens (from the planning-research visual session, not a plan) in an old session scratchpad under `/tmp/akentner/claude-1000/…/6e9fdb1d-…/scratchpad/visual{,-mig}/tokens.json` (0600, instances gone). Deletion by the agent was blocked; the user should delete them.
- `.planning/` docs on the pushed feature branch name private tailnet hosts (08-10-PLAN, 08-13-PLAN, 08-CONTEXT, 08-RESEARCH, research/AUDIT-ARCH-PERF-UX; origin/main already has 8 from Phase 1). Outside T-08-26/T-08-31 scope; low impact.
- 08-REVIEW-DISPOSITION.md keeps IN-01..IN-06 at `open` (untriaged); T-08-29 covered only Phases 4-7.
- IN-01: router `rule`/`errors` attributes reach the recorder and non-admin users; a README note (recorder exclude) or a redaction decision would tighten AR-08-01.
- IN-03: a `UnicodeError` from `getaddrinfo` is not caught at cc/cert_coordinator.py:398-403.
- Rule redaction (by design D-17): `Path`/`PathPrefix` values stay readable (webhook-style secrets in paths are not hidden); a hidden value echoed in a different letter case in an error is not detected.
- Middleware/service `errors` are dumped unredacted; a malformed basic-auth `users` entry can be quoted by Traefik in a middleware error (outside M40 scope).
- No pytest guard pins the workflow invariants (SHA pins, no `${{` in `run:`, `permissions: {}`, timeouts); Dependabot may not bump the `# master (2026-10-26)` hassfest pin. `actions/checkout` keeps the default `persist-credentials: true`, so the capability-less job token sits in `.git/config` visible to the moving validator images (hardening: `persist-credentials: false`).
- `.pre-commit-config.yaml` remote hooks use a mutable tag (`rev: v6.0.0`); `uvx pre-commit` is not version-pinned.
- The hacs-action and hassfest local runs mount the whole working tree (including ignored files) into third-party images; both images are digest-pinned.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-16 | 47 | 46 | 1 (T-08-20, medium, non-blocking) | gsd-security-auditor (ASVS L1, HEAD add0599) |
| 2026-11-16 | 47 | 47 | 0 | orchestrator after fix a0e3bb7 (T-08-20 closed; full gates + minimum-HA run green) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-16
