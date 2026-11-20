---
phase: 04-data-layer-correct-lean
verified: 2026-11-14T03:18:00Z
status: passed
score: 17/17 must-haves verified
covered_files:
  - ".planning/phases/04-data-layer-correct-lean/04-01-PLAN.md"
  - ".planning/phases/04-data-layer-correct-lean/04-01-SUMMARY.md"
  - ".planning/phases/04-data-layer-correct-lean/04-02-PLAN.md"
  - ".planning/phases/04-data-layer-correct-lean/04-02-SUMMARY.md"
  - ".planning/phases/04-data-layer-correct-lean/04-03-PLAN.md"
  - ".planning/phases/04-data-layer-correct-lean/04-03-SUMMARY.md"
  - ".planning/phases/04-data-layer-correct-lean/04-04-PLAN.md"
  - ".planning/phases/04-data-layer-correct-lean/04-04-SUMMARY.md"
  - ".planning/phases/04-data-layer-correct-lean/04-05-PLAN.md"
  - ".planning/phases/04-data-layer-correct-lean/04-05-SUMMARY.md"
  - ".planning/phases/04-data-layer-correct-lean/04-06-PLAN.md"
  - ".planning/phases/04-data-layer-correct-lean/04-06-SUMMARY.md"
  - ".planning/phases/04-data-layer-correct-lean/04-07-PLAN.md"
  - ".planning/phases/04-data-layer-correct-lean/04-07-SUMMARY.md"
  - ".planning/phases/04-data-layer-correct-lean/04-08-PLAN.md"
  - ".planning/phases/04-data-layer-correct-lean/04-08-SUMMARY.md"
  - ".planning/phases/04-data-layer-correct-lean/04-09-PLAN.md"
  - ".planning/phases/04-data-layer-correct-lean/04-09-SUMMARY.md"
  - "custom_components/traefik_proxy/__init__.py"
  - "custom_components/traefik_proxy/api.py"
  - "custom_components/traefik_proxy/binary_sensor.py"
  - "custom_components/traefik_proxy/button.py"
  - "custom_components/traefik_proxy/cert_coordinator.py"
  - "custom_components/traefik_proxy/config_flow.py"
  - "custom_components/traefik_proxy/coordinator.py"
  - "custom_components/traefik_proxy/data.py"
  - "custom_components/traefik_proxy/entity.py"
  - "custom_components/traefik_proxy/models.py"
  - "custom_components/traefik_proxy/sensor.py"
  - "tests/conftest.py"
  - "tests/fixtures/v2.11/pages/index.json"
  - "tests/fixtures/v2.11/rawdata.json"
  - "tests/fixtures/v3.7/certificates.json"
  - "tests/fixtures/v3.7/pages/index.json"
  - "tests/fixtures/v3.7/rawdata.json"
  - "tests/test_api.py"
  - "tests/test_api_pagination.py"
  - "tests/test_binary_sensor_tls_expiring.py"
  - "tests/test_cert_entity_state.py"
  - "tests/test_config_flow.py"
  - "tests/test_coordinator.py"
  - "tests/test_fixture_redaction.py"
  - "tests/test_models.py"
  - "tests/test_platforms_real_fixtures.py"
  - "tests/test_reconfigure.py"
  - "tests/test_sensor_tls.py"
  - "tests/traefik/capture.py"
  - "tests/traefik/compose.yaml"
  - "tests/traefik/dynamic/bulk.yml"
  - "tests/traefik/dynamic/scenario.yml"
covered_digest: "v4:sha256:ca4886249aaafc356df587aa80f40729f140fce69cee643628afcb69bbf8947b"
behavior_unverified: 0
overrides_applied: 1
overrides:
  - must_have: "04-09 truths 1 and 3, literal schedule clause: the probe runs in the coordinator cycle that performs the hourly version re-check, and no rawdata probe happens before the re-check interval has elapsed after the last successful version check"
    reason: "Superseded by M29 (WR-09 fix 293ba84): the probe keeps its own hourly clock so post-failure re-checks cannot starve it. Budget (<= 1 probe/h, >= 1 h apart), revocability, no timer and the healthy-case 1 h boundary are unchanged and tested. Contract docs amended per M32 (D-07 in 04-CONTEXT.md, 04-09 truths 1 and 3, W24)"
    accepted_by: "manager (M29/M32)"
    accepted_at: "2026-11-14T03:16:47Z"
re_verification:
  previous_status: human_needed
  previous_score: 16/17
  gaps_closed:
    - "Truth 17 (04-09 truths 1 and 3 vs. the M29 own-clock probe): closed by the M32 contract amendment (1736e31: D-07 'Amended (M29/M32)', 04-09 truths 1 and 3 reworded, W24 amended) plus the accepted override for the superseded literal clause. The amended wording matches coordinator.py:169-175"
  gaps_remaining: []
  regressions: []
advisory:
  - finding: "Capture determinism depends on the git-ignored throwaway cert; on a fresh clone certificates.json also changes serialNumber (random, not time-varying)"
    category: other
    reason: "capture.py:415-421 creates tests/traefik/certs/secure.crt only when absent. The 04-01 SUMMARY mentions only notAfter. Resolve by declaring the precondition in the harness docs or redacting serialNumber like the fingerprints"
    evidence_status: "code reading + cert identity check (previous run); UAT pass relied on the persisted cert"
  - finding: "04-09-PLAN.md still carries the pre-M29 coupling in non-truth text: key_links[0].via ('after a successful hourly _async_refresh_version'), artifacts[1].provides ('Probe arming on the hourly version re-check only'), and the body at :100 and :191"
    category: other
    reason: "Not must-have truths; the key-link tool checks the code pattern, not the via text (2/2 verified). The body paragraphs are historical execution instructions. The M32 D-07 amendment and the override cover the contract. Optional doc cleanup"
    evidence_status: "grep of 04-09-PLAN.md"
  - finding: "IN-12: the suite does not pin three probe-clock edges: a switch off the probe grid, a probe-due cycle whose version re-check fails, a probe consumed by a failing page cycle"
    category: other
    reason: "All three were directly observed correct by verifier scratch tests (edges a/b/c). A refactor that moves the arming above _async_refresh_version would go unnoticed. Resolve by adding the two matrix rows proposed in 04-REVIEW.md IN-12"
    evidence_status: "verifier scratch tests passed; no committed test"
  - finding: "IN-13: the probe interval reuses VERSION_RECHECK_INTERVAL; shortening it for IN-03 would silently multiply paginated-mode probes"
    category: other
    reason: "Refactor hazard only; current budget holds (min probe gap 60 min across 12 randomized schedules)"
    evidence_status: "code reading (coordinator.py:75-77,169-175)"
  - finding: "IN-14: the committed switch to the pages is no longer logged"
    category: other
    reason: "Debug observability only (api.py:316-321)"
    evidence_status: "code reading"
  - finding: "IN-10: _check_url_shape lets urlparse's ValueError escape into 'unknown'"
    category: other
    reason: "Config-flow path, not the client; DATA-04 contract unaffected"
    evidence_status: "reviewer-verified; not re-run"
  - finding: "IN-11: cert entities keep a redundant self._coordinator alias"
    category: other
    reason: "Refactor hazard only"
    evidence_status: "code reading"
  - finding: "IN-08 / IN-09: stored userinfo URL retries setup forever; InvalidUrl(url) keeps the password in exc.args"
    category: security
    reason: "Tracked: ROADMAP Phase 7 carry-over (ROADMAP.md:403, commit 440ab67, M31). Nothing is logged today"
    evidence_status: "code reading; carry-over confirmed in ROADMAP.md"
coincidental_reliance_items:
  - truth: "(backstop 04-01) Re-running the capture is byte-identical except time-varying fields"
    reason: undeclared-precondition
    harden: "Determinism holds only while the git-ignored throwaway cert in tests/traefik/certs/ persists between runs (capture.py:415-421 creates it only when absent). On a fresh clone the cert is regenerated, and certificates.json changes notAfter/notBefore and also serialNumber (random, not time-varying); the 04-01 SUMMARY mentions only notAfter. Declare the precondition in the harness docs, or redact serialNumber the way the fingerprints are"
---

# Phase 4: Data layer (correct + lean) Verification Report

**Phase Goal:** The integration reads the **real** Traefik v2.11 / v3.x API shape correctly and cheaply: one `GET /api/rawdata` per scan cycle is parsed once at the client boundary into frozen, typed models, and the coordinator hands every consumer a `TraefikSnapshot` with per-name lookups and precomputed aggregates, proven against fixtures captured from real Traefik containers, not hand-written JSON. User-visible entities keep working unchanged on top of the new data layer (the entity rework is Phase 5).
**Verified:** 2026-11-14T03:18:00Z
**Status:** passed
**Re-verification:** Yes. The previous report (16/17, human_needed) became stale only because planning docs changed in 1736e31: the D-07 "Amended (M29/M32)" paragraph in `04-CONTEXT.md`, the rewording of 04-09 truths 1 and 3, and the override in this file's frontmatter.

## Goal Achievement

The phase goal is achieved. All five ROADMAP success criteria, all seven DATA requirements and all 17 must-haves hold.

**What changed since the previous run:**
- `git diff --stat 1c35145..HEAD -- custom_components tests` is empty. No source, test, fixture or harness file changed.
- Commit 1736e31 touches only `04-09-PLAN.md`, `04-CONTEXT.md` and `04-VERIFICATION.md`.
- So every code-level piece of evidence from the previous report (truths 1-16, the scratch tests for WR-09/WR-10, the HA 2026.3 run) still applies to HEAD unchanged. I re-ran the full suite once as a regression guard: 523 passed.

**Truth 17 is now resolved.** The contract and the code say the same thing (details below). The override that was carried over covers the superseded literal clause.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1 / DATA-07: redacted real v2.11 + v3.x captures with full scenario coverage; harness committed; no private host/IP/credential | ✓ VERIFIED (regression) | Fixtures/harness unchanged since b05c9e5/440ab67. verify.artifacts 04-01 8/8, key-links 3/3. test_fixture_redaction.py green |
| 2 | SC2 / DATA-01: frozen models, identical semantics on both generations, no raw-dict isinstance checks in platforms | ✓ VERIFIED (regression) | Source unchanged. verify.artifacts 04-03 3/3, 04-04 7/7 |
| 3 | SC3 / DATA-02: one steady cycle = one `GET /api/rawdata`; version/entrypoints at setup; hourly + post-failure version re-check; entrypoints only on start-date change; 404 fallback follows X-Next-Page without truncation | ✓ VERIFIED | test_request_budget_matrix green (part of 523). Previously also green on HA 2026.3.0 / aiohttp 3.13.3; source unchanged since |
| 4 | SC4 / DATA-03: auth none/basic/bearer, per-request header, no credential leaks | ✓ VERIFIED (regression) | `Auth`, `_request` unchanged |
| 5 | SC4 / DATA-04: only TraefikProxyApiError subclasses; coordinator maps to ConfigEntryAuthFailed / UpdateFailed; no asserts | ✓ VERIFIED (regression) | `coordinator.py:176-181` |
| 6 | SC5 / DATA-05: typed TraefikRuntimeData; no `getattr(..., None)`; single client owner | ✓ VERIFIED (regression) | data.py, `__init__.py` unchanged |
| 7 | SC5 / DATA-06: snapshot with aggregates, `always_update=False`, no notifications on equal snapshots | ✓ VERIFIED (regression) | `coordinator.py:109`; test_switch_back_to_rawdata_publishes_no_change green |
| 8 | Phase goal / SC5: user-visible entities keep working unchanged, cert entities included | ✓ VERIFIED (regression) | test_cert_entity_state.py, test_platforms_real_fixtures.py green |
| 9 | Entity classes, unique_ids, entity_ids, names, entity set unchanged; no backend URL/IP in attributes | ✓ VERIFIED (regression) | Unchanged files |
| 10 | (backstop 04-01) Re-running the capture is byte-identical except time-varying fields | ✓ VERIFIED (coincidental-reliance) | 04-UAT.md status complete, result pass (M30). Cert precondition advisory |
| 11 | (backstop 04-05) Replacing the client during an in-flight refresh never mixes credentials | ✓ VERIFIED (regression of direct observation) | Header path and listener unchanged |
| 12 | (04-07) Cert entities listen to the cert coordinator; availability follows it only; a main cycle never probes TLS | ✓ VERIFIED (regression) | verify.artifacts 04-07 4/4; tests green |
| 13 | (04-08) User/reconfigure steps reject userinfo URLs; reauth/YAML map the construction error to `invalid_url` | ✓ VERIFIED (regression) | verify.artifacts 04-08 4/4; tests green |
| 14 | (04-09, M27 as fixed by M29) The paginated fallback is revocable; at most one extra rawdata request per hour; probes at least `VERSION_RECHECK_INTERVAL` apart; no timer; a cycle where rawdata and the pages both fail does not switch modes | ✓ VERIFIED | Matrix rows (14)-(20), test_failed_fallback_keeps_rawdata_mode, verifier scratch edges a/b/c and 12-seed property test (previous run, inputs unchanged) |
| 15 | (backstop 04-07) Cert entity state does not depend on listener order | ✓ VERIFIED (regression) | Unchanged files |
| 16 | (backstop 04-08) Concurrent requests cannot mix credentials on a request-construction error | ✓ VERIFIED (regression) | `_request` unchanged |
| 17 | 04-09 truths 1 and 3 (amended M29/M32): the rawdata probe runs once per `VERSION_RECHECK_INTERVAL` on a clock of its own, usually with the hourly version re-check; a post-failure re-check neither arms nor postpones it; 1 h - 1 s after the last arming a paginated cycle requests the pages only, at exactly 1 h the probe runs | ✓ VERIFIED (amended contract); superseded literal clause PASSED (override) | See "Truth 17 against the amended contract" |

**Score:** 17/17 truths verified (0 present-but-behavior-unverified, 1 override applied, 0 failed)

### Truth 17 against the amended contract

**The amended text matches the code clause by clause.**

| Amended clause | Code | Test evidence |
|---|---|---|
| "on a clock of its own" | `_probe_armed_at`, armed only in `_async_setup` (`coordinator.py:127`) and in `_async_update_data` (`:169-175`) | Matrix row (16): probe 50 min after the last successful version check |
| "usually in the same cycle as the hourly version re-check" | Both clocks start together at setup (`:127`) and both use `_interval_elapsed` with `>=` (`:75-77`); they diverge only after a post-failure re-check | Rows (3), (5), (9), (12): failure-free schedules |
| "a re-check after a failed cycle neither arms nor postpones the probe" | `_async_refresh_version` moves only `_version_checked_at` (`:163`). The arming follows the version step, so a failing re-check raises before the clock moves | Row (15): probes at 60/120/180/240 min despite a page failure every 50 min. Scratch edge (b) |
| Truth 3: "1 h - 1 s after the last probe arming … pages only; at exactly 1 h the probe runs" | `dt_util.utcnow() - since >= VERSION_RECHECK_INTERVAL` | Rows (8)-(9): 1 h boundary in a healthy run |
| D-07 M29/M32: budget unchanged, probes at least one interval apart, no timer | Arming resets `_probe_armed_at` every time it fires | Truth 4 of 04-09 / prohibition: 12-seed property test (minimum gap 60 min); timer grep empty |

**Contract documents (checked in 1736e31 and the decision log):**
- `04-CONTEXT.md:95-101` adds the "Amended (M29/M32, 2026-11-14, WR-09 fix 293ba84)" paragraph below the M27 amendment. It overrides the M27 wording ("the coordinator cycle that performs the hourly version re-check") and keeps it as history.
- In `04-09-PLAN.md`, truths 1 and 3 (`:25,:27`) now state the own clock explicitly.
- In the decision log, W24 reads "einmal pro `VERSION_RECHECK_INTERVAL` auf eigener Uhr, meist im selben Zyklus wie der …" and is marked as changed by M29/M32. M32 records the decision itself: amend the docs and add the override, accepted_by manager.
- `verify.artifacts 04-09`: 5/5. `verify.key-links 04-09`: 2/2.

**Why the override still counts.** The override's `must_have` names the superseded literal clause, not the amended truths. It records the formal acceptance that M29 replaced the M27 coupling. I count it once in `overrides_applied`. Truth 17 holds directly against the amended text, so the score does not depend on the override.

**Residual wording (advisory, not a must-have).** Some non-truth text in `04-09-PLAN.md` still describes the old coupling:
- the `key_links[0].via` text "after a successful hourly `_async_refresh_version`" (`:60`)
- the `artifacts[1].provides` text "Probe arming on the hourly version re-check only" (`:46`)
- the historical task body (`:100`, `:191`)

The key-link tool checks the code pattern, which is present. This is an optional doc cleanup only.

### Backstop 04-01: UAT evidence (truth 10)

The evidence is unchanged from the previous report. `04-UAT.md` has `status: complete` with result `pass` (M30): two runs, only `startDate` differs, `bulk.yml` unchanged, clean teardown. The retained logs corroborate it, and so do the sorted-key writer (`capture.py:463`) and the cert identity with `tests/fixtures/v3.7/certificates.json`. The undeclared cert precondition stays recorded as coincidental-reliance and as an advisory. It is non-blocking.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `custom_components/traefik_proxy/coordinator.py` | Probe arming on its own hourly clock | ✓ VERIFIED | `_probe_armed_at`, `_interval_elapsed`; wired to `client.request_rawdata_probe()` |
| `custom_components/traefik_proxy/api.py` | `request_rawdata_probe`, `_probe_rawdata`; mode switch only after the pages succeed | ✓ VERIFIED | `api.py:262-326` |
| `tests/test_coordinator.py` | Budget matrix incl. rows (14)-(20) | ✓ VERIFIED | Green |
| `tests/test_api.py` | Probe unit tests + `test_failed_fallback_keeps_rawdata_mode` | ✓ VERIFIED | Green |
| `04-CONTEXT.md` | D-07 amendments (M27, M29/M32) | ✓ VERIFIED | `:89-101` |
| Plans 01-09 artifacts | as declared | ✓ VERIFIED | `verify.artifacts`: 01 8/8, 02 3/3, 03 3/3, 04 7/7, 05 4/4, 06 5/5, 07 4/4, 08 4/4, 09 5/5 (09 re-run on the amended plan) |

### Key Link Verification

gsd-tools `verify.key-links`: 01 3/3, 06 3/3, 09 2/2 (09 re-run on the amended plan). The 04-07 and 04-08 links are unchanged.

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| coordinator.py | api.py | `client.request_rawdata_probe()` once `_probe_armed_at` is 1 h old, after the version step | ✓ WIRED | `coordinator.py:169-175` |
| api.py | `/api/rawdata` | `_rawdata_probe_due` consumed and cleared before the await | ✓ WIRED | `api.py:305-311` |
| api.py | paginated pages | rawdata 404 → `_get_state_paginated()` → then `_paginated = True` | ✓ WIRED | `api.py:313-321` |
| coordinator.py | api.py | `async_get_state` every cycle; version/entrypoints when due | ✓ WIRED | Unchanged |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| Router / service / entrypoint / count entities | `coordinator.data.*` | `/api/rawdata` (or pages) → parse → `TraefikSnapshot` | Yes (captured fixtures) | ✓ FLOWING |
| Cert entities | `cert_coordinator.data[host]`, `threshold_days` | TLS probe cache, options | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| No source/test change since last source commit | `git diff --stat 1c35145..HEAD -- custom_components tests` | Empty | ✓ PASS |
| Full suite (run once, this run) | `.venv/bin/pytest -q` | 523 passed in 23.97 s | ✓ PASS |
| 04-09 artifacts/key-links on the amended plan | `verify.artifacts`, `verify.key-links` | 5/5, 2/2 (exit 0) | ✓ PASS |
| Lint/types, HA 2026.3 run, scratch edge + property tests | carried from the previous run | Inputs unchanged (empty diff) | ✓ PASS (carried) |

### Probe Execution

Step 7c is not applicable. No `scripts/*/tests/probe-*.sh` exists, and the phase declares no probes.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DATA-01 | 04-03, 04-04 | Parse once into frozen models; platforms never inspect raw dicts | ✓ SATISFIED | Truth 2 |
| DATA-02 | 04-04, 04-06, 04-09 | One rawdata request per cycle; setup/hourly/restart rules; paginated fallback | ✓ SATISFIED | Truths 3, 14, 17 |
| DATA-03 | 04-05 | Auth none/basic/bearer; per-request header; no leaks | ✓ SATISFIED | Truths 4, 11 |
| DATA-04 | 04-05, 04-08 | Only TraefikProxyApiError subclasses; no assert | ✓ SATISFIED | Truth 5 |
| DATA-05 | 04-02 | Typed TraefikRuntimeData | ✓ SATISFIED | Truth 6 |
| DATA-06 | 04-04, 04-07 | TraefikSnapshot with aggregates; `always_update=False` | ✓ SATISFIED | Truths 7, 8 |
| DATA-07 | 04-01, 04-05, 04-06 | Real, redacted, regenerable fixtures | ✓ SATISFIED | Truths 1, 10 (cert precondition advisory) |

Plans claim all 7 IDs, and none is orphaned. REQUIREMENTS.md (`:439-445`) still lists them as "Pending", per W26, until phase.complete. I did not edit it.

### Prohibitions

| Prohibition | Tier | Enforcement evidence | Disposition |
|-------------|------|----------------------|-------------|
| 04-01: no private IP/hostname/credential in fixtures; no test starts Docker | test | test_fixture_redaction.py; fixtures unchanged | verified |
| 04-04 / 04-05: no backend URL/IP; no credential in log/exception/repr; no session default Authorization | test | Unchanged code paths; suite green | verified |
| 04-07: cert alarm not hidden behind main-coordinator state; no TLS probe from main cycles | test | Unchanged; tests green | verified |
| 04-08: no userinfo accepted in newly entered URLs; no URL/credential in the construction error message | test | Unchanged; tests green (IN-09 flow-level args tracked for Phase 7) | verified |
| 04-09: at most one extra rawdata request per hour per client; no background or timer probing | test | Matrix rows (8)-(20); test_one_probe_per_arming_under_overlapping_calls; verifier property test (minimum gap 60 min); timer grep empty | verified |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| .planning/phases/04-data-layer-correct-lean/04-09-PLAN.md | 46, 60, 100, 191 | Non-truth text still describes the pre-M29 coupling | ℹ️ Info | Doc consistency only; the truths and D-07 are amended |
| tests/test_coordinator.py | 444-447 | Row (15) comment over-claims (IN-12) | ℹ️ Info | Misleading comment |
| custom_components/traefik_proxy/api.py | 316-321 | Committed switch to the pages not logged (IN-14) | ℹ️ Info | Observability |
| custom_components/traefik_proxy/coordinator.py | 113-115 | `_probe_armed_at` also moves in rawdata mode; the comment understates this (IN-13) | ℹ️ Info | Readability |

The modified files have no TBD/FIXME/XXX markers (checked in the previous run, source unchanged).

### Advisory (non-blocking)

| # | Finding | Category | Why advisory |
|---|---------|----------|--------------|
| 1 | Capture determinism relies on the persisted throwaway cert; `serialNumber` changes on a fresh clone | other | Precondition undeclared; the UAT passed with the persisted cert |
| 2 | Stale coupling wording in non-truth text of 04-09-PLAN.md | other | Doc cleanup |
| 3 | IN-12: probe-clock edges a/b/c not pinned by committed tests | other | Observed correct; regression hazard |
| 4 | IN-13: probe interval tied to `VERSION_RECHECK_INTERVAL` | other | Refactor hazard |
| 5 | IN-14: switch to the pages not logged | other | Debug observability |
| 6 | IN-10: `urlparse` ValueError in `_check_url_shape` | other | Config-flow path |
| 7 | IN-11: redundant `_coordinator` alias | other | Refactor hazard |
| 8 | IN-08 / IN-09 | security | Tracked as a Phase 7 carry-over (ROADMAP.md:403) |

### Human Verification Required

None. The truth-17 decision was resolved by M32: the contract was amended and the override was accepted with `accepted_by: manager (M29/M32)`. The Docker determinism backstop is closed by 04-UAT.md.

### Gaps Summary

There are no gaps.
- The data layer reads `/api/rawdata` once per cycle and parses it into frozen models.
- Consumers get a `TraefikSnapshot`.
- The paginated fallback is revocable within the request budget.
- Fixtures come from real v2.11 and v3.7 containers.
- Entities are unchanged.

The only open item from the previous run was a gap between the contract and the code, and it is resolved. Every remaining item is advisory.

---

_Verified: 2026-11-14T03:18:00Z_
_Verifier: Claude (gsd-verifier)_
