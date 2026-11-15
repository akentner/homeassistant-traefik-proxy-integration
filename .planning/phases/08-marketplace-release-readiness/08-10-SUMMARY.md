---
phase: 08-marketplace-release-readiness
plan: 10
subsystem: docs
tags: [readme, changelog, marketplace, hacs, trademark, faq]
status: complete

requires:
  - phase: 08-marketplace-release-readiness
    provides: 08-01..08-08 final behaviour (redaction, migration texts, brand, version 1.0.0); 08-09 visual check (no code finding, entity ID scheme confirmed in HA 2026.11.0)
provides:
  - README.md rewritten as the Marketplace / HACS information page (REL-03, DOCS-04, REL-02 trademark note)
  - CHANGELOG.md (Keep a Changelog 1.1.0) for 0.1.0..1.0.0 with breaking changes and required actions first (DOCS-02)
affects: [08-11, 08-12, 08-13 push readiness and release notes]

actuals:
  tokens: 9800
  tasks: 2
  commits: 2
plan_head_before: 842d833f2155449ff7bbf2172bc833ed59783240
plan_head_after: a6215764a2deb0ade3e06eb8e2965f5c46ef6c5d

tech-stack:
  added: []
  patterns:
    - "README consistency check: every entity key, English entity name ({host} as <host>), item state and option key from translations/en.json must appear in README.md"

key-files:
  created:
    - CHANGELOG.md
  modified:
    - README.md

key-decisions:
  - "CHANGELOG 1.0.0 heading is '## [1.0.0] - Unreleased'; the user sets the date when tagging"
  - "README trademark note states that Traefik Labs' trademark guidelines were not reviewed and no permission is claimed (open assumption A3/A8)"
  - "Example entity IDs use the Traefik host traefik.example.com and the scheme confirmed in the 08-09 visual check (device name + entity name slug)"
  - "CHANGELOG 1.0.0 describes the final state against 0.3.0, not intermediate development states (for example the interim 'invalid URL' for URL credentials is replaced by the url_has_credentials error and the migration)"

patterns-established:
  - "Docs gates: private-host grep, removed-feature grep, en.json consistency check, version-order check"

requirements-completed: [REL-03, REL-02, DOCS-02, DOCS-04]

duration: 8min
completed: 2026-11-15
---

# Phase 8 Plan 10: README and CHANGELOG Summary

English Marketplace README (badge, basicAuth prerequisites, config/options tables from the code, entity table from en.json, cadence, automations, troubleshooting, FAQ, trademark note) and a Keep a Changelog history 0.1.0..1.0.0 that opens 1.0.0 with breaking changes and required actions.

## Performance

- **Duration:** about 8 min (2026-11-15T21:00:46Z to 21:08:47Z, plus gates)
- **Tasks:** 2 (Task 1 tracer, Task 2 auto)
- **Files:** 2 (README.md rewritten, 443 lines; CHANGELOG.md new, 311 lines)

## Task Commits

1. **Task 1 (tracer): README rewrite** - `33e6d4f` (docs)
2. **Task 2: CHANGELOG 0.1.0..1.0.0** - `a621576` (docs)

Tracer feedback gate (auto mode, `human_verify_mode` end-of-phase, automated-only verify): the three Task 1 gates were re-run after the commit and passed (`TRACER_OK`), then Task 2 started.

## What was built

- **README.md** with the `##` sections Features, Prerequisites, Installation,
  Removal, Configuration, Options, Entities, Data updates, Example automations,
  Troubleshooting, Known limitations, FAQ, Trademark (plus License at the end).
  - My Home Assistant `hacs_repository` badge for `akentner/homeassistant-traefik-proxy-integration`, category `integration`.
  - Prerequisites: HA 2026.11.0, Traefik v2.11+/v3.x, `api: {}` / `--api=true`, file-provider router on `api@internal` with a basicAuth middleware (htpasswd hint, `$$` in Docker labels), bearer only through forwardAuth or a plugin, `api.insecure` for no-auth on trusted networks, verify_ssl for self-signed certificates.
  - Configuration table (url, verify_ssl, auth_type, username, password, token) and Options table (scan_interval 15 s 15–300, verify_ssl, tls_warn_days 14 d 1–90, per_item_entities on, missing_grace_hours 24 h 1–168) from `const.py` / `config_flow.py` / en.json labels; reauth and reconfigure described.
  - Entity table: 16 rows (router, service, entrypoint, the six snapshot sensors, certificate_expiry, four problem aggregates, certificate_expiring, refresh) with platform, translation key, English name, device, states, attributes and enabled-by-default; attribute names cross-checked against `sensor.py` / `binary_sensor.py`.
  - Data updates: main cycle 15 s with `/api/rawdata`, paginated fallback with hourly rawdata retry, hourly version re-check, entrypoints on restart/upgrade, certificate cycle 6 h with 5 min retry, background first cycle, Refresh now, `homeassistant.update_entity`.
  - Three automations (router `error`, Router problems on, certificate expiring), troubleshooting table of all eight form errors, diagnostics redaction, debug logging, repair notices, known limitations, FAQ (nine out-of-scope rows plus the rawdata graph), trademark note linking `docs/BRAND.md`.
- **CHANGELOG.md**: header with Keep a Changelog 1.1.0 / SemVer links and the "every tag gets an entry" sentence; `## [1.0.0] - Unreleased` with `### Breaking changes and required actions` first, then Added, Changed, Removed, Fixed, Security; sections for 0.3.0, 0.2.1, 0.2.0, 0.1.6, 0.1.4, 0.1.3, 0.1.2, 0.1.1, 0.1.0 (all 2026-07-06 from `git log -1 --format=%as`), 0.1.2 as a one-line "no user-visible changes" entry, the untagged 0.1.5 noted under 0.1.6, compare links at the bottom.

## Verification

| Gate | Result |
|---|---|
| README consistency check (en.json entity keys, names with `<host>`, states, option keys) | `missing: []`, exit 0 |
| README private-host / Tailscale grep | no match |
| README reload / YAML-setup grep | no match |
| README badge, 13 section headings, trademark + `docs/BRAND.md`, `15 s` + `2026.11.0`, no `developers.home-assistant.io` | all exit 0 |
| CHANGELOG version order | `['1.0.0', '0.3.0', '0.2.1', '0.2.0', '0.1.6', '0.1.4', '0.1.3', '0.1.2', '0.1.1', '0.1.0']`, exit 0 |
| CHANGELOG first `###` under 1.0.0 | `### Breaking changes and required actions` |
| CHANGELOG strings (2026.11.0, update_entity, san_mismatch, not_found, Refresh now, host:port, 6 h) | all present |
| CHANGELOG internal IDs (`D-NN`, `M/W NN`, `Phase N`, `Plan NN-NN`) | none |
| CHANGELOG private-host grep (also `192.168`) | no match |
| CHANGELOG tag dates vs `git log -1 --format=%as <tag>` | all match |
| `uv run pytest -q` (incl. doc-link guard over README.md and CHANGELOG.md, coverage gate 99 %) | 1152 passed, coverage 99.29 % |
| `ruff check custom_components tests` / `ruff format --check` | All checks passed / 50 files already formatted |
| `uv run mypy --strict custom_components/traefik_proxy` | no issues in 16 source files |
| HA 2026.11.0 venv (`ha2611-venv`, `-p no:respx`) | 1152 passed |

README consistency-check output (recorded per plan output spec):

```text
missing: []
```

No Docker step in this plan; no container, network or volume was created.

## Deviations from Plan

None in scope. The README has a short `## License` section after `## Trademark`; the must-have order of the 13 required sections is unchanged (the plan names no section after Trademark).

## Worker Decisions

| Decision | Reason | Alternative not taken |
|---|---|---|
| `## [1.0.0] - Unreleased` (planner) | The release date is the user's action | Today's date |
| Fixed `##` section list in README (planner) | Gate-able structure | Free structure |
| Trademark note says Traefik Labs' guidelines were not reviewed and no permission is claimed; describes the logo as the "traefik proxy" lockup used by the dashboard, not as "the official logo"; asks Traefik Labs to open an issue if they object | Open assumption A3/A8 (guidelines not fetched, ProxyLogo assumed to be the official horizontal logo); the note must not claim what was not verified | Claim permitted use, or omit the logo provenance |
| Entity IDs in examples: Traefik host `traefik.example.com`, router `nextcloud@docker`, e.g. `sensor.traefik_routers_traefik_example_com_nextcloud_docker`, `binary_sensor.traefik_traefik_example_com_router_problems` | Same slug scheme the 08-09 visual check saw in HA 2026.11.0 (`sensor.traefik_routers_traefik_v3_bulk_000_file`, `button.traefik_traefik_v3_refresh_now`); router names always carry `@provider` | The plan's shorter `sensor.traefik_routers_example_com_api` (would not match a real router name) |
| Entity names with a placeholder are written as one code span (`` `<host> expiry` ``) | The consistency check needs the literal `<host> expiry` | `` `<host>` expiry `` (fails the check) |
| Entrypoint sensor (translation key `entrypoint`, no en.json entry, name = entrypoint name) is listed in the entity table | It is a real entity of the integration (diagnostic, disabled by default); the plan's key list was taken from en.json only | Leave it out |
| HACS install text: badge or search, otherwise add as custom repository | The repository is not yet in the HACS default list (that PR is the user's action) | Claim it is in the default list |
| CHANGELOG describes the 1.0.0 end state against 0.3.0 and folds intermediate development steps (interim "invalid URL" for URL credentials, the "fixed before release" certificate update regression, intermediate unknown-vs-unavailable states) into their final wording | Users upgrade from 0.3.0 to 1.0.0; intermediate states never shipped | List every SUMMARY bullet verbatim |
| Developer-only SUMMARY items (lock file, coverage gate, CI pins, Dependabot, release check) are not in the CHANGELOG | Plan: "Write for users"; those SUMMARYs list them as developer-facing, not user-visible | A "Development" group (not a Keep a Changelog type) |
| 0.x sections from the tag commit messages; the private IP in the v0.1.6 commit message is not copied | Keep private data out | — |
| 0.1.5 noted inside the 0.1.6 entry ("never tagged") | Tags list has no v0.1.5; the plan forbids a section without a tag | A 0.1.5 heading (would break the order gate) |
| Breaking changes also cover the renamed problem aggregates, reduced count-sensor attributes, renamed certificate entities and the restructured devices | They break templates, dashboards or areas on upgrade ("anything else the SUMMARY sections mark as breaking") | List them only under Changed/Removed |

## Requirement coverage

- **REL-03**: README rewritten, no private names, no removed feature advertised (gates above).
- **REL-02**: trademark note with `docs/BRAND.md` link.
- **DOCS-02**: CHANGELOG with every tag, ordered, dated, compare links.
- **DOCS-04**: FAQ answers the Out of Scope rows (config-file edits / route editing, ACME, Traefik v1, TCP/UDP, per-middleware entities, service actions/reload, acme.json, Traefik Enterprise, DNS probe mode) plus the rawdata-graph row.
- Edge REL-03/idempotency: the consistency check is a pure function of README.md and en.json; 08-13 can re-run it unchanged.
- Edge DOCS-02/adjacency, /empty, /ordering: all tags share 2026-07-06 and are ordered by version; 0.1.2 has its one-line entry.

## Known Stubs

None.

## Threat Flags

None. Threats T-08-26 (private names) and T-08-27 (outdated promises) are mitigated by the grep gates and the consistency check above.

## Next Phase Readiness

- 08-11 / 08-12 must not edit README.md or CHANGELOG.md (REL-03/DOCS-04 concurrency backstops).
- 08-13 re-runs the README consistency check and both private-name gates; the release-notes draft takes the 1.0.0 breaking-changes block and replaces "Unreleased" with the tag date when the user tags.
- REL-07 stays "pending first PR CI run"; this plan did not mention it in the docs.

## Self-Check: PASSED

- FOUND: README.md, CHANGELOG.md, .planning/phases/08-marketplace-release-readiness/08-10-SUMMARY.md
- FOUND: 33e6d4f, a621576 (ancestors of HEAD)
