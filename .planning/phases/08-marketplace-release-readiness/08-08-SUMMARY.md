---
phase: 08-marketplace-release-readiness
plan: 08
subsystem: release, validation
tags: [manifest, release-identity, hassfest, hacs-action, docker, marketplace]

requires:
  - phase: 08-marketplace-release-readiness
    provides: 08-05 brand images (tracked, so they are in the overlay file list); 08-06 Makefile and hashed min-HA lock; 08-07 scripts/check_release_tag.py
provides:
  - manifest.json version 1.0.0 + categories [computers_network.monitoring] in hassfest key order
  - make hassfest (official image, --rm --pull always, same mount as the CI action)
  - make hacs-action + scripts/hacs_action_local.py (local-tree overlay for ghcr.io/hacs/action:main, fail-closed)
  - 08-LOCAL-VALIDATION.md (hassfest evidence, overlay proof, public metadata checks, post-push check list)
affects: [08-09..08-12 (manifest 1.0.0), 08-13 (final pre-push rerun of make hassfest and make hacs-action, same token blocker)]

actuals:
  tokens: 4200     # chars/4 over the realized diff (16683 chars)
  tasks: 2
  commits: 2
plan_head_before: 42e525d2bdf1903a77510116d3b5dd6350b4a866
plan_head_after: 16c5bfca7046a9a242c4743e38b6bd97651aba54

tech-stack:
  added: []
  patterns:
    - "Validator containers are throwaway (--rm, --pull always); hacs mounts are read-only"
    - "Monkeypatch overlays assert their targets exist and resolve to the patch before running"
    - "Secrets reach containers by variable name only (-e NAME), never in argv"

key-files:
  created:
    - scripts/hacs_action_local.py
    - .planning/phases/08-marketplace-release-readiness/08-LOCAL-VALIDATION.md
  modified:
    - custom_components/traefik_proxy/manifest.json
    - Makefile

key-decisions:
  - "The authenticated hacs/action run is recorded as BLOCKED, not faked: the permission classifier denied passing the user's gh token into the container"
  - "Overlay also checks after patching that the integration repository class resolves each target to the patch (catches subclass overrides, not only missing attributes)"
  - "Harness cleanup in make hacs-action removes the two known files and rmdir's the directory instead of rm -rf"

patterns-established:
  - "make hassfest / make hacs-action are the local Marketplace validator entry points"

requirements-completed: [REL-01]

coverage:
  - id: D1
    description: "manifest 1.0.0 with categories in hassfest key order; release identity consistent (manifest, pyproject, tag check)"
    requirement: REL-01
    verification:
      - kind: other
        ref: "make hassfest -> Integrations: 1 / Invalid integrations: 0, exit 0 (image sha256:da652299..., HA 2026.11.1)"
        status: pass
      - kind: other
        ref: "scripts/check_release_tag.py v1.0.0 -> 0, v1.0.1 -> 1, vv1.0.0 -> 1; hassfest_checks.py all -> 0"
        status: pass
    human_judgment: false
  - id: D2
    description: "official hacs/action validators pass on the local tree (All 10 checks) with a failing negative control"
    requirement: REL-07
    verification:
      - kind: other
        ref: "make hacs-action -> BLOCKED (permission classifier denied passing gh auth token into the container); not run"
        status: unknown
      - kind: other
        ref: "overlay proof on image sha256:187499a0... with /hacs/action.py stubbed, --network none: patches apply, tree/files from the working tree, ignored file not served, fail-closed guard exits 1"
        status: pass
    human_judgment: true

duration: 7min
completed: 2026-11-15
status: complete
---

# Phase 8 Plan 08: Release identity and local Marketplace validators Summary

**The manifest is now 1.0.0 in category `computers_network.monitoring` and passes the official hassfest image locally (`Invalid integrations: 0`). The `hacs/action` overlay and its `make hacs-action` target are built, and the overlay is proven on the image digest. The authenticated validator run itself is blocked by a permission denial for the user's GitHub token.**

## Performance

- **Duration:** about 7 min
- **Started:** 2026-11-15T20:35:38Z
- **Completed:** 2026-11-15T20:42Z
- **Tasks:** 2 (Task 2's validator run blocked, see below)
- **Files modified:** 4

## Accomplishments

- `manifest.json`: `"version": "1.0.0"`, `"categories": ["computers_network.monitoring"]` between `after_dependencies` and `codeowners`. Key order is domain, name, then alphabetical. `hacs.json` is unchanged (`"homeassistant": "2026.11.0"`).
- `make hassfest` runs the official image: `docker run --rm --pull always -v "$(CURDIR)":/github/workspace ghcr.io/home-assistant/hassfest:latest`. Result: `Integrations: 1`, `Invalid integrations: 0`, no `[ERROR]` or `[WARNING]` line, exit 0. I ran it twice: once for the task and once for the tracer gate.
- `scripts/hacs_action_local.py`: the research overlay, hardened. It checks that each of the 4 targets exists before patching and that the integration class resolves each one to the patch afterwards; otherwise it exits 1. It logs `LOCAL OVERLAY` lines and serves files only from `git ls-files -co --exclude-standard`.
- `make hacs-action`: the official `ghcr.io/hacs/action:main` image, `--rm --pull always`, both mounts `:ro`, all three repository variables set (P2), the token passed by name.
- `08-LOCAL-VALIDATION.md`: hassfest evidence, both image digests, the overlay proof, the anonymous public-metadata checks (5/5 green) and the post-push check list.

## Validator results

| Validator | Image | Result |
|---|---|---|
| hassfest | `ghcr.io/home-assistant/hassfest@sha256:da6522993280166fe072704989a2b4c33e639e8ceb69c8ab6ad7ec5045c1a1e3` (HA 2026.11.1, created 2026-11-09) | `Integrations: 1` / `Invalid integrations: 0`, exit 0 |
| hacs/action (overlay) | `ghcr.io/hacs/action@sha256:187499a09c5d41f9f0d42ff80d203ed87b974c028290140913b61e005fb0aab2` (created 2026-10-20) | **BLOCKED, not run.** Overlay proof only: `LOCAL OVERLAY: patched 4 methods; 327 files from /repo`, tree has 378 entries incl. `brand/icon.png`, manifest `1.0.0 ['computers_network.monitoring']` read from the working tree, an ignored file returns `None`, the missing-method guard exits 1 |
| Negative control (`computers_network.bogus`) | same | **Not run** (needs the same token) |
| GitHub metadata (anonymous API read) | n/a | archived false, description set, has_issues true, license MIT, topics hacs/hass/home-assistant/integration/traefik, private false |

## Task Commits

1. **Task 1 (tracer): 1.0.0 manifest + Marketplace category pass hassfest in a throwaway container**: `ae59b6a` (feat)
2. **Task 2: hacs/action overlay + make target + evidence (validator run blocked)**: `16c5bfc` (feat)

## Files Created/Modified

- `custom_components/traefik_proxy/manifest.json`: version 1.0.0, categories
- `Makefile`: `REPO`, `HASSFEST_IMG`, `HACS_IMG`; targets `hassfest` and `hacs-action`
- `scripts/hacs_action_local.py`: local-tree overlay that runs inside `ghcr.io/hacs/action:main`
- `.planning/phases/08-marketplace-release-readiness/08-LOCAL-VALIDATION.md`: validator evidence

## Quality gates

| Gate | Result |
|---|---|
| `uv run pytest -q` (dev env, coverage gate 99) | 1152 passed, coverage 99.29% |
| `uv run ruff check custom_components tests` | All checks passed |
| `uv run ruff format --check custom_components tests` | 50 files already formatted |
| `uv run mypy --strict custom_components/traefik_proxy` | no issues in 16 source files |
| `make test-min-ha` (`.venv-min-ha`, HA 2026.11.0 from the hashed lock) | 1152 passed, coverage 99.29% |
| `ha2611-venv` (HA 2026.11.0) `python -m pytest -q -o addopts="-p no:respx" tests` | 1152 passed |
| `scripts/hacs_action_local.py` ruff check / format | clean (outside the gate paths, checked anyway) |

## Docker

- Containers used: `make hassfest` (2 runs), one version probe of the hassfest image, three overlay probes of the hacs/action image (`--network none`). All of them ran with `--rm`. No ports were published and no networks or volumes were created. Docker auto-assigned unique names to the `make` runs; the probes had explicit unique names (`hassfest-ver-0808`, `hacs-inspect-0808`).
- Images pulled or refreshed: `ghcr.io/home-assistant/hassfest:latest` (already up to date) and `ghcr.io/hacs/action:main` (already up to date).
- **Cleanup check against `docker-baseline-phase8.txt`:** `docker ps -a` (ID + name), `docker network ls` and `docker volume ls` are identical to the baseline. No hassfest or hacs/action container remains. `git status` showed no files written by the containers.

## Blocker: the authenticated hacs/action run

- **What:** `make hacs-action` was denied by the Claude Code auto-mode permission classifier ("Unauthorized Access"). The target reads the user's GitHub credential with `gh auth token` and passes it into the container. The action cannot run without a token: it reads one only from `INPUT_GITHUB_TOKEN` and exits otherwise (research F2).
- **What I did not do:** I did not work around the denial. No dummy token (it would only produce failed API calls), no patch to an unauthenticated client, no other credential source. I wrote no pass line anywhere: `08-LOCAL-VALIDATION.md` deliberately does not contain the `All (10) checks passed` string, so the plan's grep gate fails correctly.
- **Unmet must-haves:** the REL-07/empty truth (`All (10) checks passed`), the negative-control part of REL-07/encoding, and the Task 2 acceptance line that greps for the pass line. Everything else in REL-07/encoding is proven: the file list, the `LOCAL OVERLAY` line, and the exit on a missing method.
- **Unblock:** the user runs `make hacs-action` once from the repository root, or allows that command for the agent. Then the negative control is run as described in `08-LOCAL-VALIDATION.md` and both results are recorded there. 08-13 re-runs `make hacs-action` before the push and will hit the same permission unless it is granted.
- REL-07 is **not** marked complete.

## Decisions Made

See Worker Decisions.

## Worker Decisions

| Decision | Reason | Alternative not taken |
|---|---|---|
| (planner) Overlay asserts its patch targets exist | A missing class attribute would be created silently and the run would validate GitHub's `main` | Trust the image layout |
| (planner) Negative control recorded as evidence | Proves the overlay reads the local tree on this image digest | Rely on the research-time proof |
| Record the hacs/action run as BLOCKED after the permission denial | The orchestrator brief says to record a blocker instead of faking a pass, and the denial must not be bypassed | Dummy token, or patching the client to run unauthenticated |
| The overlay also verifies after patching that `HacsIntegrationRepository` (and `HacsBase`) resolve each target to the patch | `hasattr` alone misses a subclass override that would shadow a base-class patch | Existence check only |
| Overlay probes in the image with `/hacs/action.py` stubbed and `--network none` | Proves the overlay part on the exact digest without a token or network, and keeps that proof clearly separate from a validator result | No evidence at all for Task 2 |
| Public metadata read anonymously from `api.github.com` (no token) | The plan asks for the metadata checks evaluated against the public repository; an unauthenticated public GET needs no credential | `gh api` (uses the user's token) |
| Harness cleanup uses `rm -f` on the two known files plus `rmdir`, and `mktemp -d \|\| exit 1` | The safety check refused an `rm -rf $tmp` edit; removing exactly the two files cannot delete more than intended | Research recipe `rm -rf $$tmp` |
| Paths quoted in the recipe (`"$$tmp"`) | Robust against spaces in `TMPDIR` | Unquoted, as in the research recipe |
| No `--name` on the `make` containers | Docker assigns unique names and `--rm` removes them; `make hassfest` stays identical to the CI action's command | Fixed names (two concurrent runs would collide) |
| "Nothing pushed" checked through the local remote-tracking refs (`git branch -r`: no `marketplace-polish`), not `git ls-remote origin` | `ls-remote` authenticates over SSH with the user's key; the local refs show nothing was pushed from this checkout | Plan's `git ls-remote origin` acceptance command |

## Deviations from Plan

1. **[Blocked - permission] The hacs/action validator run and its negative control did not run.** See the Blocker section. Found during Task 2. The script, Makefile target and evidence file were committed in `16c5bfc`.
2. **[Rule 2 - hardening] Post-patch resolution check in the overlay.** It goes beyond the plan's existence assertion (see Worker Decisions). Files: `scripts/hacs_action_local.py`. Commit: `16c5bfc`.
3. **[Rule 3 - blocking] Harness cleanup without `rm -rf`.** The shell edit carrying the research recipe was refused by the safety check, so the recipe now removes the two files and the directory explicitly. Files: `Makefile`. Commit: `16c5bfc`.

**Total deviations:** 3 (1 blocked, 2 auto-fixed). **Impact:** REL-01 is fully met. The REL-07 local validator evidence is incomplete until the user unblocks the token use.

## User-visible changes (for the CHANGELOG)

- Version 1.0.0.
- Marketplace category: Monitoring (`computers_network.monitoring`).

## Next Phase Readiness

- 08-09..08-12 can build on the 1.0.0 manifest.
- 08-13 needs `make hacs-action` to run with a token. It will hit the same permission denial unless the user runs it or allows it.

## Self-Check: PASSED

- FOUND: custom_components/traefik_proxy/manifest.json, Makefile, scripts/hacs_action_local.py, .planning/phases/08-marketplace-release-readiness/08-LOCAL-VALIDATION.md
- FOUND: ae59b6a, 16c5bfc (ancestors of HEAD)
