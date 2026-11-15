---
status: testing
phase: 08-marketplace-release-readiness
source: [08-VERIFICATION.md]
started: 2026-11-15T22:00:44Z
updated: 2026-11-15T22:00:44Z
---

## Current Test

number: 1
name: First Draft-PR CI run of validate.yml (REL-07, REL-05)
expected: |
  HACS job green with all 10 hacs/action checks passed (a report of 5 checks is a failure); lint, test (uv sync --locked), test-min-ha (hashed install) and hassfest jobs green.
awaiting: user response

## Tests

### 1. First Draft-PR CI run of validate.yml (REL-07, REL-05)
expected: HACS job green with all 10 checks passed; lint, test, test-min-ha and hassfest green. Precondition: test 2 (push + Draft PR) done.
result: [pending]

### 2. Push and Draft PR (REL-08, manager action M41)
expected: Manager runs `git ls-remote origin`, pushes feat/marketplace-polish and opens the Draft PR to main with the body from 08-DRAFT-PR.md; no tag, release or hacs/default PR. (Evidence table already refreshed by the orchestrator to 1180 passed / 99.31 % and the review fixes.)
result: [pending]

### 3. Logo trademark decision (A3/A8)
expected: User keeps logo.png/dark_logo.png as shipped (README and docs/BRAND.md state the guidelines were not reviewed and no permission is claimed) or applies the icon-only fallback before the release and the hacs/default PR.
result: [pending]

### 4. Flagged prohibitions (tokens, Docker leftovers)
expected: No GitHub or HA token in any 08-08/08-09 log, evidence file or screenshot; no leftover containers/networks/volumes. (Orchestrator note: docker ps -a / network ls / volume ls matched docker-baseline-phase8.txt after 08-09 and again after verification.)
result: [pending]

### 5. Optional local hacs/action run
expected: With HACS_ACTION_TOKEN (fine-grained, read-only, public repos) `make hacs-action` reports 10 checks passed; the negative control (category computers_network.bogus) fails integration_categories with a non-zero exit.
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
