---
phase: 08-marketplace-release-readiness
plan: 05
subsystem: brand, release-hygiene
tags: [brand, logo, dark-logo, png, interlace, pillow, guard-test, licence, trademark, hacs, marketplace]

requires:
  - phase: 08-marketplace-release-readiness
    provides: re-exported icons, docs/icon.svg and the tests/test_brand.py helpers (08-04)
provides:
  - landscape brand/logo.png (337x128) and brand/logo@2x.png (674x256) from the Traefik webui ProxyLogo lockup
  - dark-theme brand/dark_logo.png / dark_logo@2x.png with the white wordmark
  - docs/logo.svg, docs/logo-dark.svg (vector sources, not shipped)
  - docs/BRAND.md (provenance, MIT notice, trademark statement, export recipe for all six PNGs)
  - tests/test_brand.py logo geometry, wordmark contrast and exact brand file set guards
affects: [08-09 local brand serving check, 08-10 README trademark note, 08-11 CHANGELOG, 08-13 release-notes draft (A3/A8)]

actuals:
  tokens: 12960
  tasks: 2
  commits: 4
plan_head_before: ffaf3fd14f740176766dabe619b6c5c2a484ed9b
plan_head_after: 3448a17876caf86a2ab3ffcee9f84e6811454436

tech-stack:
  added: []
  patterns:
    - "Upstream JSX artwork is converted to SVG by text substitution only (no execution), validated with xmllint"
    - "Wordmark readability is pinned by the mean luminance of opaque right-half pixels (Pillow, self-checked on planted samples)"

key-files:
  created:
    - docs/logo.svg
    - docs/logo-dark.svg
    - docs/BRAND.md
    - custom_components/traefik_proxy/brand/logo.png
    - custom_components/traefik_proxy/brand/logo@2x.png
    - custom_components/traefik_proxy/brand/dark_logo.png
    - custom_components/traefik_proxy/brand/dark_logo@2x.png
  modified:
    - tests/test_brand.py

key-decisions:
  - "Logo artwork = traefik/traefik webui ProxyLogo @ v3.7.19 (7dafd6d), black wordmark; dark_logo uses the webui's own dark-mode #fff"
  - "Dark logos share every logo check (size, RGBA, interlace, trim) through the LOGOS table; the wordmark test compares luminance, not exact colours"
  - "Logo licence/trademark assumption A3/A8 stays flagged for the user; D-03 escape hatch (icon only) remains available"

patterns-established:
  - "Brand logos: rsvg-convert -h 1024 then magick -trim +repage -resize xN -strip -define png:color-type=6 -interlace PNG"

requirements-completed: [REL-02]

coverage:
  - id: D1
    description: "logo.png / logo@2x.png landscape, heights 128 / 256, RGBA, interlaced, below 500 KB, @2x within 2 px of 2:1"
    requirement: REL-02
    verification:
      - kind: unit
        ref: "tests/test_brand.py#test_logo_size_mode_and_interlacing"
        status: pass
      - kind: unit
        ref: "tests/test_brand.py#test_logo_2x_is_twice_the_logo"
        status: pass
    human_judgment: false
  - id: D2
    description: "All four logos trimmed: alpha bbox equals the full image"
    requirement: REL-02
    verification:
      - kind: unit
        ref: "tests/test_brand.py#test_logo_is_trimmed"
        status: pass
    human_judgment: false
  - id: D3
    description: "dark_logo / dark_logo@2x have the logo sizes, different pixels, light wordmark (> 160) vs dark wordmark (< 96)"
    requirement: REL-02
    verification:
      - kind: unit
        ref: "tests/test_brand.py#test_dark_logo_mirrors_the_logo"
        status: pass
      - kind: unit
        ref: "tests/test_brand.py#test_wordmark_is_dark_on_logo_and_light_on_dark_logo"
        status: pass
      - kind: unit
        ref: "tests/test_brand.py#test_wordmark_luminance_against_planted_samples"
        status: pass
    human_judgment: false
  - id: D4
    description: "brand/ holds exactly the six PNGs; no SVG in the integration folder"
    requirement: REL-02
    verification:
      - kind: unit
        ref: "tests/test_brand.py#test_brand_folder_holds_exactly_the_brand_files"
        status: pass
      - kind: unit
        ref: "tests/test_brand.py#test_brand_folder_ships_no_svg"
        status: pass
    human_judgment: false
  - id: D5
    description: "docs/BRAND.md records source, tag + SHA, MIT notice, trademark statement, export commands, dark_logo/dark_icon rationale"
    requirement: REL-02
    verification:
      - kind: other
        ref: "grep 'Permission is hereby granted' / -i 'trademark of Traefik Labs' / 'v3.7.19' docs/BRAND.md"
        status: pass
      - kind: other
        ref: "re-running the recorded export commands reproduces logo.png, dark_logo.png, icon.png, icon@2x.png byte-identically (cmp)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Logos render correctly in the HA frontend / Marketplace on light and dark themes; trademark use is acceptable"
    verification: []
    human_judgment: true
    rationale: "Local brand serving on 2026.11.0 is confirmed in 08-09; A3/A8 (trademark guidelines, official lockup) is a flagged assumption for the user"

duration: 6min
completed: 2026-11-15
status: complete
---

# Phase 8 Plan 05: Brand logo and dark logo Summary

**Landscape Traefik Proxy logo (337x128 / 674x256) and a white-wordmark dark logo, exported from the webui `ProxyLogo` lockup at traefik v3.7.19, with provenance, MIT notice and export recipe in `docs/BRAND.md` and a Pillow guard for geometry, wordmark contrast and the exact six-file `brand/` set.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-11-15T20:11:44Z
- **Completed:** 2026-11-15T20:17:41Z
- **Tasks:** 2 (Task 1 tracer, both TDD: RED + GREEN commits each)
- **Files:** 7 created, 1 modified

## Accomplishments

- Fetched `webui/src/components/icons/Logo.tsx` and `LICENSE.md` read-only at tag `v3.7.19` (commit **`7dafd6dba371bd1aee70c443c2975c229c969711`**) into their own new scratch directory; converted the `ProxyLogo` element to `docs/logo.svg` by text substitution only (`fill={textColor}` -> `"#000"`, `clipPath=` attribute -> `clip-path=`, `{...props}` dropped, provenance comment added). `docs/logo-dark.svg` is the same with `#fff`. `xmllint --noout` passes for both.
- Exported the four logo PNGs with the F8 pipeline (sizes match the research prediction exactly).
- `docs/BRAND.md`: file table, source (repo, path, tag, SHA, `Logo` -> icon, `ProxyLogo` -> logo), conversion notes, full MIT notice copied from `LICENSE.md` @ v3.7.19, trademark/non-affiliation statement, exact export commands for all six PNGs, expected alpha bboxes, dark_logo/dark_icon rationale.
- `tests/test_brand.py`: 28 tests (was 11).

## Alpha-bbox measurements (P8: `magick f.png -alpha extract -format %@ info:`)

| File | Size | Alpha bbox | Mode / interlace | Bytes | Wordmark luminance |
|---|---|---|---|---|---|
| `brand/logo.png` | 337x128 | `337x128+0+0` | srgba, PNG interlace | 17133 | 0.0 |
| `brand/logo@2x.png` | 674x256 | `674x256+0+0` | srgba, PNG interlace | 40812 | 0.0 |
| `brand/dark_logo.png` | 337x128 | `337x128+0+0` | srgba, PNG interlace | 18949 | 255.0 |
| `brand/dark_logo@2x.png` | 674x256 | `674x256+0+0` | srgba, PNG interlace | 44658 | 255.0 |

Intermediate render: `rsvg-convert -h 1024` -> 2655x1024. Re-running the commands recorded in `docs/BRAND.md` reproduces `logo.png`, `dark_logo.png`, `icon.png` and `icon@2x.png` byte-identically.

## Task Commits

1. **Task 1 RED:** `f601e1c` test(08-05): add failing brand logo geometry guard
2. **Task 1 GREEN:** `26c0076` feat(08-05): add Traefik Proxy landscape logo from the webui ProxyLogo lockup
3. **Task 2 RED:** `8d580b9` test(08-05): add failing dark logo, wordmark contrast and brand file set guard
4. **Task 2 GREEN:** `3448a17` feat(08-05): add dark-theme logo and record brand provenance in docs/BRAND.md

No REFACTOR commits (nothing to clean up).

## TDD Gate Compliance

- **Task 1 RED:** `uv run pytest tests/test_brand.py -q --no-cov -p no:cacheprovider --junitxml=...` -> exit 1, 5 failed / 11 passed. `gsd-tools check tdd-red-evidence` -> `RED_EVIDENCE_OK` (`target_test_failed`, junit), target `tests.test_brand#test_logo_is_trimmed[logo.png]`.
  - semanticAssessment: the target executed and failed because `brand/logo.png` does not exist (`FileNotFoundError` inside the test body) - exactly the planned RED ("see them fail on the missing files"). All 5 failures are the new logo behaviour lines; the 11 icon/helper tests from 08-04 still passed.
- **Task 1 GREEN:** 16 passed. **Tracer gate:** auto mode active -> re-ran `<verify>` (`tests/test_brand.py` 16 passed, `xmllint --noout docs/logo.svg` OK) after the GREEN commit. Tracer verified end-to-end, expanded to Task 2.
- **Task 2 RED:** same command -> exit 1, 9 failed / 19 passed. Classifier `RED_EVIDENCE_OK` (`target_test_failed`), target `tests.test_brand#test_brand_folder_holds_exactly_the_brand_files`.
  - semanticAssessment: the target failed on its planned assertion (brand/ lists 4 files instead of the 6-file set). The other 8 failures are the planned dark-logo behaviour lines (missing files). The 3 planted luminance samples passed, as intended (they test the helper). Before the RED commit, a first run showed the teal planted sample expecting 133 instead of the real BT.601 luma 130 - a wrong expectation in the new test, fixed before committing RED.
- **Task 2 GREEN:** 28 passed.
- RED evidence (JUnit XML + JSON records) kept in the session scratch area, not committed.

## Quality Gates (after Task 2; also run green after Task 1: 1132 passed on both envs)

| Gate | Result |
|---|---|
| `uv run pytest tests/test_brand.py -q --no-cov` | 28 passed |
| `uv run pytest -q` (dev env, with coverage gate) | **1144 passed**, exit 0, no "Lingering", no coverage failure |
| `uv run ruff check custom_components tests` | All checks passed |
| `uv run ruff format --check custom_components tests` | 49 files already formatted |
| `uv run mypy --strict custom_components/traefik_proxy` | no issues in 16 source files |
| HA 2026.11.0 venv (`ha2611-venv`, `-p no:respx`) | **1144 passed**, exit 0 |

## Acceptance Criteria

- Task 1: `magick identify` -> `337 128` / `674x256` height 256; `grep -q 'viewBox="0 0 280 108"' docs/logo.svg` -> PASS
- Task 2: `LC_ALL=C ls brand | sort` -> `dark_logo.png dark_logo@2x.png icon.png icon@2x.png logo.png logo@2x.png ` -> PASS (with the German default locale `sort` puts `dark_logo@2x.png` first; same set)
- `grep` for "Permission is hereby granted", "trademark of Traefik Labs" (-i), "v3.7.19" in `docs/BRAND.md` -> PASS
- `find brand -name '*.png' -size +499k | wc -l` -> 0 -> PASS

## Worker Decisions

| Decision | Reason | Alternative not taken |
|---|---|---|
| Provenance in `docs/BRAND.md` with the full MIT notice (planner) | MIT requires the notice with copies of the artwork; reproducible export | Notice only in README |
| `docs/BRAND.md` written after both icon and logo exports exist (planner) | One document covers all six PNGs with the commands actually used | Separate notes per plan |
| Dark logos added to the shared `LOGOS` table, so they get the size/RGBA/interlace/size-gate/trim checks too | The behaviour asks for "the logo's sizes"; the HA brand rules apply to every shipped image | Separate dark-only size test |
| Wordmark luminance measured on fully opaque pixels only (alpha 255), BT.601 luma via Pillow `convert("L")`, with planted self-check samples | Anti-aliased edge pixels would blur the mean; planted samples keep the guard non-vacuous (08-03/08-04 convention) | Exact colour match of the wordmark |
| Provenance comment (source, tag, SHA, MIT, trademark) at the top of both SVGs | The SVGs are copies of upstream artwork; the notice travels with them | Provenance only in BRAND.md |
| Kept the upstream `clip0`/`clip1` rect fills as `#000`/`#fff` (from `fill={textColor}`) | Fill of a clipPath child has no visual effect; keeping the plain substitution keeps the conversion auditable | Hand-edit the clip rects |
| Re-exported the icons into scratch with the recorded commands and compared bytes (no change to the shipped icons) | Proves the BRAND.md recipe for all six PNGs is exact, without touching 08-04's output | Copy the commands unverified |

## Deviations from Plan

None - plan executed exactly as written (additions inside the planned test module and BRAND.md are listed under Worker Decisions).

## Flagged assumption (A3/A8) - for the user

**Traefik Labs' trademark/brand guidelines permit nominative use of the `ProxyLogo` artwork with a trademark note, and the webui `ProxyLogo` equals the official horizontal lockup** (08-RESEARCH.md A3, A8; the guidelines and press kit at traefik.io/press were not fetched). MIT covers the file's copyright only, not the trademark. If wrong, D-03's escape hatch applies: delete the four logo PNGs and ship only the icon. Remains open; surfaced in the release-notes draft (08-13).

## Docker

No Docker used in this plan; no cleanup check needed.

## Known Stubs

None.

## Threat Flags

None. Downloaded `Logo.tsx` / `LICENSE.md` were fetched read-only at the pinned tag into their own new scratch directory and only transformed as text by a script kept in a different directory (`python3 -I`); nothing from them was executed (T-08-11). T-08-12 transferred via the BRAND.md notice; README note follows in 08-10.

## User-visible changes (for CHANGELOG)

- New landscape logo: the "traefik proxy" lockup (mark + wordmark) is shown where Home Assistant and the Marketplace display an integration logo, instead of falling back to the square icon.
- New dark-theme logo: on dark themes the logo uses a white wordmark, so it stays readable.

## Next Phase Readiness

Ready for 08-09 (local brand serving: `logo.png` must now be served with its own bytes, not the icon's) and 08-10 (README trademark note).

## Self-Check: PASSED

- FOUND: docs/logo.svg, docs/logo-dark.svg, docs/BRAND.md, brand/logo.png, brand/logo@2x.png, brand/dark_logo.png, brand/dark_logo@2x.png, tests/test_brand.py
- FOUND commits (ancestors of HEAD): f601e1c, 26c0076, 8d580b9, 3448a17
