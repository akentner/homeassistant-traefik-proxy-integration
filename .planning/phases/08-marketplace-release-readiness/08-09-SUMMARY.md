---
phase: 08-marketplace-release-readiness
plan: 09
subsystem: release-validation, brand, visual-check
tags: [visual-check, playwright, docker, brands-proxy, migration, repairs, de, en]
status: complete

requires:
  - phase: 08-marketplace-release-readiness
    provides: 08-03 entities_migrated text with final title and kept IDs; 08-05 brand images incl. dark_logo; 08-08 manifest 1.0.0
provides:
  - REL-02 evidence - HA 2026.11.0 serves all six shipped brand PNGs byte-for-byte (no fallback)
  - M35 / D-25 visual check in de and en (config flow auth selection, options units, repairs, device tree, states/icons, Refresh now, light/dark)
  - real 0.3.0 -> 1.0.0 migration seen in HA 2026.11.0 (entities_migrated repair in de and en)
  - 08-VISUAL-CHECK.md report, 26 screenshots under visual/, deferred-items.md (F-02)
affects: [08-10 README/CHANGELOG, 08-12 review dispositions, 08-13 push readiness]

actuals:
  tokens: 4200
  tasks: 3
  commits: 3
plan_head_before: 69d16246c31b4a5a4f2b89d0d2edd1b35622bf17
plan_head_after: 312319d38cb09ebbdc7e18f2fba8652b8bfab4c9

tech-stack:
  added: []
  patterns:
    - "Visual checks: HA system language must match the shot language (entity/device names are backend-translated)"
    - "Brand evidence by sha256 against the shipped file plus inequality between fallback pairs"

key-files:
  created:
    - .planning/phases/08-marketplace-release-readiness/08-VISUAL-CHECK.md
    - .planning/phases/08-marketplace-release-readiness/deferred-items.md
    - .planning/phases/08-marketplace-release-readiness/visual/ (26 JPEGs)
  modified: []

key-decisions:
  - "German shots taken with HA system language de, English shots with en (container restart in between), because HA renders entity and device names in the system language"
  - "Extra screen 13 (main device page, dark theme) per language: the integration page only shows the icon, the device page is where dark_logo.png is visible (D-28)"
  - "Before the 0.3.0 -> 1.0.0 swap one router binary sensor was disabled and one hidden, so the repair's kept-ID statement could be checked against the registry"
  - "No finding with a code cause: no fix(08-09) commit, custom_components/ and tests/ untouched"

patterns-established:
  - "Page-text check over shadow DOM plus label/placeholder/aria-label/title attributes for untranslated keys"

requirements-completed: [REL-02]

coverage:
  - id: D1
    description: "HA 2026.11.0 serves icon, icon@2x, logo, logo@2x, dark_logo, dark_logo@2x from the local brand folder, byte-identical, no fallback"
    requirement: REL-02
    verification:
      - kind: integration
        ref: "curl -H @authhdr /api/brands/integration/traefik_proxy/<image>?placeholder=no | sha256sum vs brand/<image> (08-VISUAL-CHECK.md 'Brand serving')"
        status: pass
  - id: D2
    description: "de/en screenshots of add flow (none/basic/bearer), options, insecure_credentials repair, device tree, router/cert states, Refresh now, integration page light/dark, dark device page; no untranslated keys"
    requirement: REL-02
    verification:
      - kind: automated_ui
        ref: "playwright: visual/{de,en}-01..11,13-*.jpg; page-text check 0 hits"
        status: pass
  - id: D3
    description: "Real 0.3.0 entry migrated by the working tree; entities_migrated repair names traefik-v3, removed_count 101, kept IDs verified in the registry"
    requirement: REL-02
    verification:
      - kind: automated_ui
        ref: "playwright: visual/{de,en}-12-repair-entities-migrated.jpg; WS repairs/list_issues + config/entity_registry/list"
        status: pass
  - id: D4
    description: "Throwaway containers, harness network and HA volumes removed; docker lists equal the baseline"
    verification:
      - kind: other
        ref: "diff of docker ps -a / network ls / volume ls against the pre-run baseline: empty"
        status: pass

duration: 15min
completed: 2026-11-15
---

# Phase 8 Plan 09: Visual check and local brand serving Summary

**Throwaway HA 2026.11.0 + Traefik v3.7.19: all six brand PNGs served byte-for-byte, 26 de/en screenshots with no untranslated key, a real 0.3.0 -> 1.0.0 migration repair checked against the registry, everything torn down to the baseline. No finding had a code cause.**

## Performance

- **Duration:** about 15 min (2026-11-15T20:44:03Z -> 2026-11-15T20:59Z)
- **Tasks:** 3/3
- **Files:** 2 Markdown files created and 26 JPEGs added, 1.9 MB total, each under 100 KB; one existing Markdown file extended twice

## Accomplishments

- **Brand serving (D-04, REL-02):** `/api/brands/integration/traefik_proxy/<image>?placeholder=no` returned `200 image/png` for all six images, each with the sha256 of the shipped file. `logo` differs from `icon`, `dark_logo` from `logo` (also for the @2x variants), so no fallback answered.
- **Visual check (M35, D-25), 12 screens per language:**
  - add flow with the conditional auth fields (none/basic/bearer)
  - options form with the `s`/`d`/`h` units, the grace-period field and the per-item field
  - the `insecure_credentials` repair
  - the main device with its three connected sub-devices
  - router states and icons (Error/Enabled) and certificate states and icons
  - Refresh now after a press
  - the integration page in light and dark theme, plus the dark device page that shows `dark_logo.png`
- **Migration:** the v0.3.0 code (from `git archive`) created the entry "Traefik Proxy" with 100 router binary sensors and `button.traefik_reload`. After swapping the mount on the same volume:
  - the title is `traefik-v3`
  - `entities_migrated` reports `removed_count` 101
  - `insecure_credentials` is raised
  - the disabled router keeps `sensor.traefik_http_router_bulk_001_file` and the hidden one keeps `…bulk_002_file`
  - an enabled router got the new `sensor.traefik_routers_traefik_v3_bulk_000_file`
  - the de and en repair dialogs say exactly this
- **Cleanup:** `docker ps -a` (IDs and names), `docker network ls` and `docker volume ls` are identical to the baseline. Tokens and the scratch copies were deleted.

## Task Commits

1. **Task 1 (tracer): throwaway HA serves the shipped brand images:** `eeed4d3` (docs). The tracer gate was re-run live (icon, logo and dark_logo hashes) before expanding.
2. **Task 2: de/en screenshots and findings:** `b3729c4` (docs)
3. **Task 3: 0.3.0 migration repair, teardown, report complete:** `312319d` (docs)

## Findings summary

| ID | Cause | Resolution |
|---|---|---|
| F-01 | cosmetic: long certificate entity names are cut with an ellipsis in the device page's Sensors card (HA layout) | listed |
| F-02 | upstream: HA core logs `Failed to load integration for translation: Invalid domain <domain>.<platform>` after a system-language change, for core integrations as well | deferred-items F-02 |

There are no `fix(08-09)` commits and no regression tests from this plan, because no finding had a code cause.

## Deviations from Plan

None that change the plan's outcome. Additions:
- Screen `13-device-main-dark` was added per language. It is where `dark_logo.png` is visible; the integration page shows only the icon.
- The plan expected at least 12 screenshots per language; there are 13 (01-13).
- The HA system language was switched to `de` for the German shots and back to `en`, with a container restart each time. See Worker decisions.

### Deviations (declared scope)
None. No fix commit was needed, so `custom_components/traefik_proxy/` and `tests/` were not touched (`git status --porcelain -- custom_components tests` is empty, and the fix-commit scope gate passes trivially).

## Worker decisions

| Decision | Reason | Alternative not taken |
|---|---|---|
| Set the HA system language to the shot language (de/en) and restart before the device/entity shots | HA renders entity and device names in the backend language. Without the switch, German shots showed English names ("Refresh now", "Traefik routers") | Leave the system on en: the German shots would mix languages and hide missing de entity strings |
| Disable one and hide one 0.3.0 router before the migration | This makes the repair's kept-ID statement (08-03) checkable against the real registry | Migrate untouched: the statement would go unverified |
| Extra screenshot 13 (dark device page) | D-28 dark logo: the integration page shows only the icon | Treat the integration page in the dark theme as enough evidence |
| F-02 (a log warning, not a screen) recorded as an upstream finding | The fix protocol has no "log only" class; it is an HA core path | Leave it out of the report |
| Set the country through WS `config/core/update` (A1) | Avoids core's `country_not_configured` noise in the repair shots; the command exists and worked | Ignore the extra repair |

## Deferred items
- `deferred-items.md` F-02: HA core 2026.11.0 `homeassistant.helpers.translation` warns `Invalid domain <domain>.<platform>` after a language change. Harmless; names were correct after the restart.

## Playwright provenance (D-32)
Playwright 1.65.2 from PyPI (author "Microsoft Corporation", Apache-2.0, https://github.com/Microsoft/playwright-python) ran ephemerally through `uv run --no-project --with playwright --with pillow --with websockets`. It drove `chromium_headless_shell-1254` from `~/.cache/ms-playwright` (`executable_path`), headless, against 127.0.0.1 only. Nothing was added to the project. The helper scripts stayed in the scratch directory.

## Docker
- Images (already local, nothing pulled):
  - `ghcr.io/home-assistant/home-assistant:2026.11.0@sha256:c6c1ca99…`
  - `traefik:v3.7.19@sha256:b7b1b31e…`
  - `traefik/whoami:v1.12.0`
- Started:
  - harness `whoami` + `traefik-v3` (network `traefik-harness_default`, API on 127.0.0.1:18370)
  - `ha-visual-08` (127.0.0.1:18123, volume `ha-visual-08-config`)
  - `ha-visual-08-mig` (127.0.0.1:18124, volume `ha-visual-08-mig`)
  - the integration was mounted read-only
- **Cleanup check:** all of the above were removed. The `diff` against the baseline (= `docker-baseline-phase8.txt`) is empty for containers, networks and volumes. Pre-existing containers and networks were never touched.

## Gates

| Gate | Result |
|---|---|
| `uv run pytest -q` (dev env, coverage gate 99) | 1152 passed, coverage 99.29%, no "Lingering" |
| `ruff check custom_components tests` | All checks passed |
| `ruff format --check custom_components tests` | 50 files already formatted |
| `uv run mypy --strict custom_components/traefik_proxy` | Success: no issues found in 16 source files |
| HA 2026.11.0 venv (`ha2611-venv`, `homeassistant` 2026.11.0) | 1152 passed |

## User-visible changes
None. This plan made no code fix; README and CHANGELOG are 08-10's.

## Known Stubs
None.

## Issues Encountered
- Playwright's sync API runs its own event loop, so the WS helper now runs `asyncio.run` in a worker thread (scratch tooling only).
- The REST `GET /api/config/config_entries/flow` does not list flows in progress. WS `config_entries/flow/progress` was used to confirm that the closed add flows had been aborted.

## Next Phase Readiness
- 08-10 can cite: brand serving confirmed on HA 2026.11.0, the screenshots, and the migration behaviour (title, kept IDs, removed_count 101).
- REL-07 (`make hacs-action`) is still blocked on the user's GitHub token. This plan did not touch it.

## Self-Check: PASSED
