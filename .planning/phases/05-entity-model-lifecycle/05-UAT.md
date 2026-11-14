---
status: testing
phase: 05-entity-model-lifecycle
source: [05-VERIFICATION.md]
started: 2026-11-14T23:26:36Z
updated: 2026-11-14T23:26:36Z
---

## Current Test

number: 1
name: Judgment-tier prohibition ENT-01 (registry deletions only on allowed paths)
expected: |
  Verifier verdict HOLDS: entity-registry removals only in async_purge (per-item opt-out), grace expiry and the 0.3.0 migration; device removal only through _async_remove_device_if_unreferenced.
awaiting: user response

## Tests

### 1. Judgment-tier prohibition ENT-01 (05-02): no registry deletion outside grace expiry, per-item opt-out, 0.3.0 migration, entry removal
expected: Verifier verdict HOLDS (entity_manager.py:268, :335; __init__.py:116, :119; device removal guarded at entity.py:95)
result: [pending]

### 2. Judgment-tier prohibition ENT-07 (05-06): no non-GET request to the Traefik API
expected: Verifier verdict HOLDS (api.py:185 only HTTP call; test_only_get_requests_reach_traefik green on both HA versions)
result: [pending]

### 3. Judgment-tier prohibition ENT-09 (05-07): migration/legacy cleanup never re-enables a user-disabled entity, never renames/re-IDs a survivor, never touches another entry
expected: Verifier verdict HOLDS on all three clauses after 05-08 + review fix (CR-01, CR-02, IN-05); covered by green test-tier prohibitions of 05-08
result: [pending]

### 4. Optional visual check in a real HA (2026.3 and 2026.10+), German and English, upgraded 0.3.0 entry
expected: Device "Traefik (<host>)" with nested Routers/Services/Certificates sub-devices; translated ENUM state labels and icons; repair notice text; "Refresh now" under Diagnostic
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
