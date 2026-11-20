---
phase: 08-marketplace-release-readiness
plan: 04
subsystem: brand, release-hygiene
tags: [brand, icon, png, interlace, pillow, guard-test, hacs, marketplace]

requires:
  - phase: 08-marketplace-release-readiness
    provides: release-hygiene guard style (planted-sample self-checks) from 08-03
provides:
  - trimmed, centred, interlaced brand/icon.png (256x256) and brand/icon@2x.png (512x512)
  - docs/icon.svg as the vector source (moved from brand/ with history)
  - tests/test_brand.py with reusable helpers (open_image, alpha_bbox, margins, trim_problems) for 08-05
affects: [08-05 logos + BRAND.md, 08-09 local brand serving check, 08-10 README trademark note, 08-11 CHANGELOG]

actuals:
  tokens: 2119
  tasks: 1
  commits: 2
plan_head_before: ef469c859c66885274e63fba97692418cb2a055f
plan_head_after: d1ffffc30301061a4e47b4329ffc30c9d002acb5

tech-stack:
  added: []
  patterns:
    - "Brand geometry is measured on the alpha channel (Pillow getchannel('A').getbbox()), not by corner-colour trim"
    - "Brand guard helpers self-check against planted RGBA samples (non-vacuous)"

key-files:
  created:
    - tests/test_brand.py
    - docs/icon.svg
  modified:
    - custom_components/traefik_proxy/brand/icon.png
    - custom_components/traefik_proxy/brand/icon@2x.png

key-decisions:
  - "Brand guard uses Pillow (bundled with HA in both envs), no new dependency"
  - "Icon and logo tests share tests/test_brand.py; 08-05 extends it via the open_image/alpha_bbox/margins/trim_problems helpers"
  - "File-size gate (< 500 KB) added to the icon test as the T-08-32 mitigation"

patterns-established:
  - "Brand images: export from the tracked SVG in docs/ with rsvg-convert at 2048 px, then magick trim/resize/extent/strip/RGBA/interlace"

requirements-completed: [REL-02]

coverage:
  - id: D1
    description: "brand/icon.png 256x256 and brand/icon@2x.png 512x512, RGBA, interlaced, below 500 KB"
    requirement: REL-02
    verification:
      - kind: unit
        ref: "tests/test_brand.py#test_icon_size_mode_and_interlacing"
        status: pass
    human_judgment: false
  - id: D2
    description: "Icon artwork trimmed to two opposite edges and centred within 1 px on the other axis"
    requirement: REL-02
    verification:
      - kind: unit
        ref: "tests/test_brand.py#test_icon_is_trimmed_and_centred"
        status: pass
      - kind: unit
        ref: "tests/test_brand.py#test_trim_helper_against_planted_samples"
        status: pass
    human_judgment: false
  - id: D3
    description: "icon.svg moved to docs/ with history; no SVG left under brand/"
    requirement: REL-02
    verification:
      - kind: unit
        ref: "tests/test_brand.py#test_brand_folder_ships_no_svg"
        status: pass
      - kind: other
        ref: "git log --follow --format=%h -- docs/icon.svg (3 commits)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Icon looks right in the HA frontend / Marketplace (light and dark)"
    verification: []
    human_judgment: true
    rationale: "Visual rendering in HA is confirmed in 08-09 (local brand serving on 2026.11.0); no test asserts appearance"

duration: 3min
completed: 2026-11-15
status: complete
---

# Phase 8 Plan 04: Brand icon re-export Summary

**Integration icon re-exported from `docs/icon.svg` as trimmed, centred, interlaced 256/512 px RGBA PNGs, pinned by a Pillow alpha-bbox guard in `tests/test_brand.py`.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-11-15T20:06:41Z
- **Completed:** 2026-11-15T20:09:53Z
- **Tasks:** 1 (tracer, TDD: RED + GREEN commits)
- **Files modified:** 4 (1 created, 1 moved, 2 re-exported)

## Accomplishments

- `brand/icon.svg` moved to `docs/icon.svg` with `git mv` (history followed: d1ffffc, 15c8f95, 0067418).
- `icon.png` / `icon@2x.png` re-exported with the 08-RESEARCH F8 pipeline:
  `rsvg-convert -w 2048 -h 2048 --keep-aspect-ratio docs/icon.svg` then
  `magick big.png -trim +repage -resize NxN -background none -gravity center -extent NxN -strip -define png:color-type=6 -interlace PNG`.
- `tests/test_brand.py`: size/mode/interlace/size-gate, trim+centre, no-SVG checks, plus a planted-sample self-check of the trim detector.

## Alpha-bbox measurements (P8: `magick f.png -alpha extract -format %@ info:`)

| File | Before | After | Margins after (L/T/R/B) | Size |
|---|---|---|---|---|
| `brand/icon.png` | 225x203+13+25 | **256x231+0+12** | 0 / 12 / 0 / 13 | 8925 B -> 17018 B |
| `brand/icon@2x.png` | 449x405+26+51 | **512x461+0+25** | 0 / 25 / 0 / 26 | 19717 B -> 43745 B |

Both are RGBA (`png:color-type=6`), Adam7-interlaced, metadata stripped. Matches the F8 prediction exactly.

## Task Commits

1. **Task 1 RED:** `3c526bd` test(08-04): add failing brand icon geometry guard
2. **Task 1 GREEN:** `d1ffffc` feat(08-04): re-export trimmed, centred, interlaced icons and move icon.svg to docs/

No REFACTOR commit (nothing to clean up).

## TDD Gate Compliance

- **RED:** `uv run pytest tests/test_brand.py -q --no-cov -p no:cacheprovider --junitxml=...` -> exit 1, 5 failed / 6 passed.
  Classifier `gsd-tools check tdd-red-evidence` -> `RED_EVIDENCE_OK` (`target_test_failed`, format junit),
  target `tests.test_brand#test_icon_is_trimmed_and_centred[icon.png]`.
  - semanticAssessment: the target executed and failed on the planned assertion
    ("padded on every axis: margins left 13, top 25, right 18, bottom 28 px", alpha bbox (13, 25, 238, 228)).
    The other failures were also the planned behaviour lines (old icons not interlaced; `icon.svg` still in `brand/`).
    The 6 planted-sample helper tests passed, as intended (they test the detector, not the shipped files).
- **GREEN:** after the move and re-export, `tests/test_brand.py` 11 passed.
- **Tracer gate:** `human_verify_mode` end-of-phase, `<verify>` automated only -> re-ran `tests/test_brand.py` after the GREEN commit: 11 passed. Tracer verified end-to-end.

## Quality Gates

| Gate | Result |
|---|---|
| `uv run pytest tests/test_brand.py -q --no-cov` | 11 passed |
| `uv run pytest -q` (dev env, with coverage gate) | 1127 passed, exit 0, no "Lingering" |
| `uv run ruff check custom_components tests` | All checks passed |
| `uv run ruff format --check custom_components tests` | 49 files already formatted |
| `uv run mypy --strict custom_components/traefik_proxy` | no issues in 16 source files |
| HA 2026.11.0 venv (`ha2611-venv`, `-p no:respx`) | 1127 passed, exit 0 |

## Acceptance Criteria

- `test -f docs/icon.svg && test ! -e .../brand/icon.svg` -> PASS
- `magick brand/icon.png -alpha extract -format %@ info:` -> `256x231+0+12` (width 256) -> PASS
- `git log --follow --format=%h -- docs/icon.svg` -> 3 commits (>= 2) -> PASS
- `find brand -name 'icon*.png' -size +499k | wc -l` -> 0 -> PASS

## Worker Decisions

| Decision | Reason | Alternative not taken |
|---|---|---|
| Geometry guard uses Pillow (planner) | Bundled with HA in both test environments; no new dependency | Parse PNG headers by hand |
| Icon and logos share `tests/test_brand.py` (planner) | One writer per wave; 08-05 adds logo tests via the same helpers | One brand plan with 12 files |
| Added a `< 500 KB` file-size assertion to the icon test | The threat model (T-08-32) asks for a size gate in Task 1; the behaviour list did not name it | Rely only on the acceptance `find -size` check |
| Added planted-sample self-checks for the trim detector | Mirrors the 08-03 guard convention (non-vacuous guards); proves the old bbox (13, 25, 238, 228) is rejected | Test only the shipped files |
| RED evidence produced as pytest JUnit XML | The TDD classifier has no pytest-text adapter; JUnit XML is supported | Self-attested RED |

## Deviations from Plan

None - plan executed exactly as written (the size assertion and planted-sample tests are additions inside the planned test module, recorded under Worker Decisions).

## Docker

No Docker used in this plan; no cleanup check needed.

## Known Stubs

None.

## User-visible changes (for CHANGELOG)

- New integration icon: trimmed to the edges and centred, interlaced PNG (256 px and 512 px), so it no longer looks small and off-centre in Home Assistant and the Marketplace.
- `icon.svg` is no longer shipped inside the integration folder (it was never served); the vector source now lives in `docs/icon.svg`.

## Next Phase Readiness

Ready for 08-05 (logo, dark logo, `docs/BRAND.md`), which extends `tests/test_brand.py` with the existing helpers.

## Self-Check: PASSED

- FOUND: tests/test_brand.py, docs/icon.svg, custom_components/traefik_proxy/brand/icon.png, custom_components/traefik_proxy/brand/icon@2x.png
- FOUND commits: 3c526bd, d1ffffc (ancestors of HEAD)
- MISSING: custom_components/traefik_proxy/brand/icon.svg (expected absent)
