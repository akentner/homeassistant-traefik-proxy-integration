---
status: testing
phase: 04-data-layer-correct-lean
source: [04-VERIFICATION.md]
started: 2026-11-14T02:51:24Z
updated: 2026-11-14T02:51:24Z
---

## Current Test

number: 1
name: Fixture re-capture is deterministic (04-01 backstop truth)
expected: |
  With Docker available, run `uv run python tests/traefik/capture.py` twice, then
  `git diff --stat tests/fixtures tests/traefik/dynamic/bulk.yml`.
  Only time-varying fields (startDate and similar) differ; bulk.yml is unchanged.
  Stop and remove every container/network the harness started; restore the fixtures afterwards if only time-varying fields changed.
awaiting: user response

## Tests

### 1. Fixture re-capture is deterministic (04-01 backstop truth)
expected: Only time-varying fields (startDate and similar) differ after two capture runs; tests/traefik/dynamic/bulk.yml is unchanged
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
