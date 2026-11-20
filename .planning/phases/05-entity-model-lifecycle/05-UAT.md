---
status: complete
phase: 05-entity-model-lifecycle
source: [05-VERIFICATION.md]
started: 2026-11-14T23:26:36Z
updated: 2026-11-14T23:27:37Z
---

## Current Test

[testing complete]

## Tests

### 1. Judgment-tier prohibition ENT-01 (05-02): no registry deletion outside grace expiry, per-item opt-out, 0.3.0 migration, entry removal
expected: Verifier verdict HOLDS (entity_manager.py:268, :335; __init__.py:116, :119; device removal guarded at entity.py:95)
result: pass (manager sign-off; override in 05-VERIFICATION.md)

### 2. Judgment-tier prohibition ENT-07 (05-06): no non-GET request to the Traefik API
expected: Verifier verdict HOLDS (api.py:185 only HTTP call; test_only_get_requests_reach_traefik green on both HA versions)
result: pass (manager sign-off; override in 05-VERIFICATION.md)

### 3. Judgment-tier prohibition ENT-09 (05-07): migration/legacy cleanup never re-enables a user-disabled entity, never renames/re-IDs a survivor, never touches another entry
expected: Verifier verdict HOLDS on all three clauses after 05-08 + review fix (CR-01, CR-02, IN-05); covered by green test-tier prohibitions of 05-08
result: pass (manager sign-off; override in 05-VERIFICATION.md)

### 4. Optional visual check in a real HA (2026.3 and 2026.10+), German and English, upgraded 0.3.0 entry
expected: Device "Traefik (<host>)" with nested Routers/Services/Certificates sub-devices; translated ENUM state labels and icons; repair notice text; "Refresh now" under Diagnostic
result: skipped (deferred by manager: visual check later, Phase 8 or before release)

## Summary

total: 4
passed: 3
issues: 0
pending: 0
skipped: 1
blocked: 0

## Gaps
