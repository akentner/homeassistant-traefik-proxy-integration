---
status: complete
phase: 08-marketplace-release-readiness
source: [08-VERIFICATION.md]
started: 2026-11-15T22:00:44Z
updated: 2026-11-15T23:01:34Z
---

## Current Test

[testing complete]

## Tests

### 1. First Draft-PR CI run of validate.yml (REL-07, REL-05)
expected: HACS job green with all 10 checks passed; lint, test, test-min-ha and hassfest green. Precondition: test 2 (push + Draft PR) done.
result: pass
evidence: GitHub Actions run 43769962201 on Draft PR #2 (first PR run of validate.yml), checked by the manager. All 5 jobs green (lint, test, test-min-ha, hassfest, hacs); the hacs/action job reports "All (10) checks passed".

### 2. Push and Draft PR (REL-08, manager action M41)
expected: Manager runs `git ls-remote origin`, pushes feat/marketplace-polish and opens the Draft PR to main with the body from 08-DRAFT-PR.md; no tag, release or hacs/default PR. (Evidence table already refreshed by the orchestrator to 1180 passed / 99.31 % and the review fixes.)
result: pass
evidence: The manager pushed feat/marketplace-polish and opened Draft PR https://github.com/akentner/homeassistant-traefik-proxy-integration/pull/2 to main. No tag, release or hacs/default PR was created.

### 3. Logo trademark decision (A3/A8)
expected: User keeps logo.png/dark_logo.png as shipped (README and docs/BRAND.md state the guidelines were not reviewed and no permission is claimed) or applies the icon-only fallback before the release and the hacs/default PR.
result: pass
resolution: Resolved by user decision 2026-11-16 — keep logo.png / dark_logo.png (and @2x) as shipped. No icon-only fallback; README and docs/BRAND.md keep the statement that the Traefik Labs trademark guidelines were not reviewed and no permission is claimed.

### 4. Flagged prohibitions (tokens, Docker leftovers)
expected: No GitHub or HA token in any 08-08/08-09 log, evidence file or screenshot; no leftover containers/networks/volumes. (Orchestrator note: docker ps -a / network ls / volume ls matched docker-baseline-phase8.txt after 08-09 and again after verification.)
result: pass
evidence: Manager check — no token patterns in tracked files or in the 26 screenshots; no Docker leftovers (containers, networks, volumes).

### 5. Optional local hacs/action run
expected: With HACS_ACTION_TOKEN (fine-grained, read-only, public repos) `make hacs-action` reports 10 checks passed; the negative control (category computers_network.bogus) fails integration_categories with a non-zero exit.
result: skipped
reason: User choice — optional item not run; the official hacs/action validators are covered by the CI run in test 1 (run 43769962201, All (10) checks passed). The local negative control stays unexecuted.

## Summary

total: 5
passed: 4
issues: 0
pending: 0
skipped: 1
blocked: 0

## Gaps

[none]
