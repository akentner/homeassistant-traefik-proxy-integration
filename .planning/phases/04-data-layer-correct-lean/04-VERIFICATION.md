---
phase: 04-data-layer-correct-lean
verified: 2026-11-14T03:12:48Z
status: human_needed
score: 16/17 must-haves verified
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
covered_digest: "v4:sha256:8dd62b6b2fc95bf7bb3bbe54ca913591909f82ea66ccf45d2e63305d6dbc2bc2"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 15/16
  gaps_closed:
    - "(backstop 04-01) Re-running the capture is byte-identical except time-varying fields: closed by 04-UAT.md (pass, M30), corroborated by the retained run logs"
    - "WR-09 (advisory): rawdata probe starved by post-failure version re-checks: fixed in 293ba84, confirmed by matrix row (15) and verifier scratch tests"
    - "WR-10 (advisory): pagination committed before the pages succeeded: fixed in 1c35145, confirmed by test_failed_fallback_keeps_rawdata_mode and matrix rows (18)-(19)"
  gaps_remaining: []
  regressions: []
advisory:
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
human_verification:
  - test: "Decide on the 04-09 schedule wording superseded by M29: either accept the override below, or reword the D-07 amendment in 04-CONTEXT.md (and the two 04-09 truths) to 'retries /api/rawdata once per VERSION_RECHECK_INTERVAL on a clock of its own (usually in the same cycle as the hourly version re-check)'"
    expected: "The plan contract and the code say the same thing; then re-run verification for status passed"
    why_human: "The code deliberately decouples the probe from the version re-check (M29 fix for WR-09). 04-09 truths 1 and 3, the D-07 amendment and W24 still state the coupling, and no decision formally amended them. Accepting a deviation from a plan must-have is a human governance decision, not something the verifier may grant"
---

# Phase 4: Data layer (correct + lean) Verification Report

**Phase Goal:** The integration reads the **real** Traefik v2.11 / v3.x API shape correctly and cheaply: one `GET /api/rawdata` per scan cycle is parsed once at the client boundary into frozen, typed models, and the coordinator hands every consumer a `TraefikSnapshot` with per-name lookups and precomputed aggregates, proven against fixtures captured from real Traefik containers, not hand-written JSON. User-visible entities keep working unchanged on top of the new data layer (the entity rework is Phase 5).
**Verified:** 2026-11-14T03:12:48Z
**Status:** human_needed
**Re-verification:** Yes. The previous report (15/16, human_needed) was stale because the WR-09/WR-10 fixes changed `api.py`, `coordinator.py`, `tests/test_api.py` and `tests/test_coordinator.py`.

## Goal Achievement

The phase goal is achieved in code. All five ROADMAP success criteria and all seven DATA requirements hold.

Since the previous report:
- Only four files changed: `custom_components/traefik_proxy/api.py`, `coordinator.py`, `tests/test_api.py` and `tests/test_coordinator.py`. They changed in commits 59b301e, 293ba84, afb3650 and 1c35145.
- In the tests, the only removed lines are two docstring lines. No assertion was removed.
- Fixtures and the harness are unchanged since b05c9e5 and since 440ab67.

**WR-09 is resolved.**
- The probe now has its own clock, `_probe_armed_at` (`coordinator.py:115,127,169-175`).
- A post-failure version re-check moves only `_version_checked_at` (`:163`).
- The arming comes after the version re-check. A failing re-check therefore raises before the clock moves.

**WR-10 is resolved.** `self._paginated = True` is set only after `_get_state_paginated()` returns (`api.py:313-321`).

**The UAT closes the last human item (the 04-01 backstop).** I accept the evidence, with one undeclared precondition, the throwaway cert (see below).

**One new decision item.** The fix moves the probe off the version re-check cycle by design. Two 04-09 must-have truths and the D-07 amendment still describe the old coupling. That needs a formal sign-off; it is not a gap.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1 / DATA-07: redacted real v2.11 + v3.x captures with full scenario coverage; harness committed; no private host/IP/credential | ✓ VERIFIED (regression) | `git diff b05c9e5..HEAD -- tests/fixtures tests/traefik` is empty. verify.artifacts 04-01 8/8, key-links 3/3. test_fixture_redaction.py is in the green suite |
| 2 | SC2 / DATA-01: frozen models, identical semantics on both generations, no raw-dict isinstance checks in platforms | ✓ VERIFIED (regression) | models.py and platforms are unchanged since the previous verification. verify.artifacts 04-03 3/3, 04-04 7/7 |
| 3 | SC3 / DATA-02: one steady cycle = one `GET /api/rawdata`; version/entrypoints at setup; hourly + post-failure version re-check; entrypoints only on start-date change; 404 fallback follows X-Next-Page without truncation | ✓ VERIFIED | test_request_budget_matrix passes, run by name. Rows (1)-(13) are byte-identical to the previous verification (git diff shows only additions after row 13). Also passes on HA 2026.3.0 / aiohttp 3.13.3 |
| 4 | SC4 / DATA-03: auth none/basic/bearer, per-request header, no credential leaks | ✓ VERIFIED (regression) | `Auth` and `_request` are unchanged. The fix commits touch only `async_get_state` |
| 5 | SC4 / DATA-04: only TraefikProxyApiError subclasses; coordinator maps to ConfigEntryAuthFailed / UpdateFailed; no asserts | ✓ VERIFIED (regression) | The WR-10 change re-raises the page error unchanged (a taxonomy subclass). Coordinator mapping is at `coordinator.py:176-181` |
| 6 | SC5 / DATA-05: typed TraefikRuntimeData; no `getattr(..., None)`; single client owner | ✓ VERIFIED (regression) | data.py and `__init__.py` are unchanged |
| 7 | SC5 / DATA-06: snapshot with aggregates, `always_update=False`, no notifications on equal snapshots | ✓ VERIFIED (regression) | `coordinator.py:109`. test_switch_back_to_rawdata_publishes_no_change is in the green suite |
| 8 | Phase goal / SC5: user-visible entities keep working unchanged, cert entities included | ✓ VERIFIED (regression) | Entity and platform files are unchanged. test_cert_entity_state.py and test_platforms_real_fixtures.py are green |
| 9 | Entity classes, unique_ids, entity_ids, names, entity set unchanged; no backend URL/IP in attributes | ✓ VERIFIED (regression) | Unchanged files |
| 10 | (backstop 04-01) Re-running the capture is byte-identical except time-varying fields | ✓ VERIFIED (coincidental-reliance) | See "Backstop 04-01: UAT evidence" below |
| 11 | (backstop 04-05) Replacing the client during an in-flight refresh never mixes credentials | ✓ VERIFIED (regression of direct observation) | The header path (`_request`, `Auth`) and the listener (`__init__.py`) are unchanged since the observation |
| 12 | (04-07) Cert entities listen to the cert coordinator; availability follows it only; a main cycle never probes TLS | ✓ VERIFIED (regression) | verify.artifacts 04-07 4/4. Tests green |
| 13 | (04-08) User/reconfigure steps reject userinfo URLs; reauth/YAML map the construction error to `invalid_url` | ✓ VERIFIED (regression) | verify.artifacts 04-08 4/4. Tests green |
| 14 | (04-09, M27 as fixed by M29) The paginated fallback is revocable; at most one extra rawdata request per hour; probes at least `VERSION_RECHECK_INTERVAL` apart; no timer; a cycle where rawdata and the pages both fail does not switch modes | ✓ VERIFIED | See "WR-09 / WR-10 re-verification" below. The previous coincidental-reliance flag is lifted: its two undeclared preconditions are now enforced in code |
| 15 | (backstop 04-07) Cert entity state does not depend on listener order | ✓ VERIFIED (regression) | Unchanged files |
| 16 | (backstop 04-08) Concurrent requests cannot mix credentials on a request-construction error | ✓ VERIFIED (regression) | `_request` is unchanged |
| 17 | 04-09 truths 1 and 3, literal schedule clause: the probe runs in "the coordinator cycle that performs the hourly version re-check", and "no rawdata probe happens before the re-check interval has elapsed … after the last successful version check" (same wording in the D-07 amendment and W24) | ? UNCERTAIN (human decision) | Deliberately superseded by the M29 fix but never formally amended. See "Does any must-have depend on the W24 wording?" |

**Score:** 16/17 truths verified (0 present-but-behavior-unverified, 1 open human decision, 0 failed)

### WR-09 / WR-10 re-verification (truth 14)

**Committed tests, run by name:**
- `tests/test_coordinator.py::test_request_budget_matrix` passes. Rows (14)-(20) are new:
  - (15) A page fails every 50 minutes. Probes still run at minutes 60, 120, 180 and 240.
  - (16) The switch back happens with a version check that is only 50 minutes old.
  - (18) An all-404 restart cycle fails without switching modes.
  - (19) The recovery cycle requests `["/api/version", "/api/rawdata"]`.
- `tests/test_api.py::test_failed_fallback_keeps_rawdata_mode` passes for 404, 500 and a connection error. `_paginated` stays False.

**Verifier scratch tests:** an isolated `git archive HEAD` copy with real `TraefikProxyCoordinator` cycles and freezer time. No repository file was modified.

| Check | Schedule | Observed | Status |
|---|---|---|---|
| Edge (a): switch off the probe grid | Rawdata 404 at minute 59 | Probe at minute 60 (`version, rawdata, pages`). Pages only at 119:59. Probe at 120:00 | ✓ PASS |
| Edge (b): probe due, version re-check fails | `/api/version` 500 in the probe-due cycle | Cycle requests `["/api/version"]` only. `_probe_armed_at` is unchanged and `_rawdata_probe_due` is False. The recovery cycle probes and switches back (`["/api/version", "/api/rawdata"]`) | ✓ PASS |
| Edge (c): probe consumed, page fails | Rawdata 404 + routers 500 in the probe cycle | `["/api/version", "/api/rawdata", "/api/http/routers"]`. Still paginated, flag cleared. The next cycle does not probe again | ✓ PASS |
| Property: 12 random seeds | Cycle 1/5/10/15 min, 30 h, 10-50 % failing cycles mixing page 500, version 500 and all-404; rawdata 404 until hour 2-20, healthy afterwards | Minimum gap between probes was 60 min in every seed. Every seed ended in rawdata mode. Switch-back took 0-180 min after rawdata recovered. Every delay over 60 min was traced to probes that landed in cycles where rawdata really answered 404 (all-404), and each was retried exactly one hour later | ✓ PASS |

**Result:**
- Revocation no longer depends on how often failures occur.
- A spurious switch during a restart window no longer happens.
- The budget of at most one probe per hour, with probes at least 1 h apart, holds under adversarial schedules.
- `create_task|call_later|async_track_time` does not occur in `api.py` or `coordinator.py` (grep exit 1), so there is no timer and no background probing.

### Does any must-have depend on the W24 wording? (truth 17)

**Yes, literally, but no goal-level must-have does.**

**Which statements still state the coupling:**
- 04-09 truth 1: "the coordinator cycle that performs the hourly version re-check retries GET /api/rawdata exactly once".
- 04-09 truth 3: "No rawdata probe happens before the re-check interval has elapsed: 1 h - 1 s after the last successful version check …".
- The D-07 amendment in `04-CONTEXT.md:89-94`.
- Worker decision W24.

**What the code does now:**
- After a post-failure re-check, the two clocks diverge. Committed matrix row (16) asserts a probe 50 minutes after the last successful version check, in a cycle without a version re-check.
- So the literal clause is false in the post-failure case, by design.
- In every failure-free schedule the clocks still coincide: rows (3), (5), (9) and (12) are byte-identical.

**Why I do not mark it FAILED:**
- The code behaviour is the remedy M29 ordered for WR-09, whose defect statement is "the retry shares its clock with the post-failure re-check". The previous verification recommended exactly this remedy.
- Every invariant behind those clauses holds and is now proven under adversarial schedules (truth 14):
  - revocability
  - at most one extra rawdata request per hour
  - probes at least 1 h apart
  - the 1 h boundary in the healthy case (rows 8-9)
  - fixed request order when both run
  - no timer
- ROADMAP SC3, DATA-02 and the 04-09 prohibition do not mention the coupling.

**Why it is not simply VERIFIED:**
- M27 changed D-07 through a formal amendment. M29 changed the same rule without amending D-07 or the 04-09 truths. The plan contract and the code now disagree.
- Accepting a deviation from a plan must-have needs a human decision.
- If the human rejects M29's precedence, this truth becomes FAILED and the status becomes gaps_found.

**This looks intentional.** To accept it, add this to the VERIFICATION.md frontmatter and re-run verification:

```yaml
overrides:
  - must_have: "04-09 truths 1 and 3, literal schedule clause: the probe runs in the coordinator cycle that performs the hourly version re-check, and no rawdata probe happens before the re-check interval has elapsed after the last successful version check"
    reason: "Superseded by M29 (WR-09 fix): the probe keeps its own hourly clock so post-failure re-checks cannot starve it. Budget (<= 1 probe/h, >= 1 h apart), revocability, no timer and the healthy-case 1 h boundary are unchanged and tested"
    accepted_by: "{name}"
    accepted_at: "{ISO timestamp}"
```

The alternative is to reword the D-07 amendment and the two 04-09 truths. This is a planning-doc edit only; the code does not change.

### Backstop 04-01: UAT evidence (truth 10)

`04-UAT.md` records a pass, executed by the worker under M30 in an isolated copy at 440ab67:
- two runs
- only `startDate` in both `version.json` files differs
- `bulk.yml` unchanged
- clean teardown

I could not re-run it, because the verifier must not start containers. I checked what can be checked:
- **Retained logs.** The run logs survive in the session scratchpad (`capture1.log`, `capture2.log`, 02:53Z). Both runs wrote 17 fixture files and observed identical content: 129 routers over 2 pages, `X-Next-Page ['2','1']`, the same error and warning routers. The logs differ only in the order of Docker container events. Teardown removed the containers and the network.
- **Inputs unchanged.** Fixtures and harness are unchanged since 440ab67, so the result applies to HEAD.
- **Deterministic writer.** `capture.py` writes JSON with `sort_keys=True` (`:463`), traverses in sorted order (`:153,212,392,460`), and generates `bulk.yml` from a fixed template (`:397-412`).
- **Same cert.** The cert in the worktree (`tests/traefik/certs/secure.crt`, serial 455146…955, notAfter 2027-02-12) matches `tests/fixtures/v3.7/certificates.json` exactly. A re-run in this checkout reuses the cert the fixtures were captured with.

**Judgement: the human item is closed.**

**Precondition flagged as coincidental-reliance (advisory):**
- Byte-identity holds only while the git-ignored cert persists, because `capture.py` creates it only when absent.
- On a fresh clone, `certificates.json` also changes `serialNumber`, which is random, not time-varying.
- The 04-01 SUMMARY mentions only `notAfter`.

The UAT's "run 1 vs committed: only startDate" result is only possible if the worker's copy carried that cert. That is consistent with the cert identity above.

### Advisory (new scope, unevidenced)

| # | Finding | Category | Why advisory |
|---|---------|----------|--------------|
| 1 | IN-12: probe-clock edges a/b/c not pinned by committed tests | other | Behaviour observed correct by the verifier. Regression hazard only |
| 2 | IN-13: probe interval tied to `VERSION_RECHECK_INTERVAL` | other | Refactor hazard. The budget holds today |
| 3 | IN-14: switch to the pages not logged | other | Debug observability |
| 4 | IN-10: `urlparse` ValueError in `_check_url_shape` | other | Config-flow path, not the client |
| 5 | IN-11: redundant `_coordinator` alias | other | Refactor hazard |
| 6 | IN-08 / IN-09 | security | Tracked in the ROADMAP Phase 7 carry-over (ROADMAP.md:403) |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `custom_components/traefik_proxy/coordinator.py` | Probe arming on its own hourly clock | ✓ VERIFIED | `_probe_armed_at`, `_interval_elapsed`. Wired to `client.request_rawdata_probe()` |
| `custom_components/traefik_proxy/api.py` | `request_rawdata_probe`, `_probe_rawdata`; mode switch only after the pages succeed | ✓ VERIFIED | `api.py:262-326` |
| `tests/test_coordinator.py` | Budget matrix incl. rows (14)-(20) | ✓ VERIFIED | Passes |
| `tests/test_api.py` | Probe unit tests + `test_failed_fallback_keeps_rawdata_mode` | ✓ VERIFIED | Passes |
| `04-CONTEXT.md` | D-07 amendment (M27) | ✓ VERIFIED (present), text stale | See truth 17 |
| Plans 01-09 artifacts | as declared | ✓ VERIFIED | gsd-tools `verify.artifacts`: 01 8/8, 02 3/3, 03 3/3, 04 7/7, 05 4/4, 06 5/5, 07 4/4, 08 4/4, 09 5/5 |

### Key Link Verification

gsd-tools `verify.key-links`: 01 3/3, 06 3/3, 09 2/2. The 04-07 and 04-08 links are unchanged since the previous report, which checked the two 04-08 tool parse misses by hand.

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| coordinator.py | api.py | `client.request_rawdata_probe()` once `_probe_armed_at` is 1 h old, after the version step | ✓ WIRED | `coordinator.py:169-175`. Edge (b) proves the ordering |
| api.py | `/api/rawdata` | `_rawdata_probe_due` consumed and cleared before the await | ✓ WIRED | `api.py:305-311` |
| api.py | paginated pages | rawdata 404 → `_get_state_paginated()` → then `_paginated = True` | ✓ WIRED | `api.py:313-321` |
| coordinator.py | api.py | `async_get_state` every cycle; version/entrypoints when due | ✓ WIRED | Unchanged |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| Router / service / entrypoint / count entities | `coordinator.data.*` | `/api/rawdata` (or pages) → parse → `TraefikSnapshot` | Yes (captured fixtures) | ✓ FLOWING |
| Cert entities | `cert_coordinator.data[host]`, `threshold_days` | TLS probe cache, options | Yes | ✓ FLOWING (unchanged) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full suite (run once) | `.venv/bin/pytest -q` | 523 passed | ✓ PASS |
| Lint / format / types | `ruff check`, `ruff format --check`, `mypy --strict custom_components` | Clean, 33 files formatted, 13 files no issues | ✓ PASS |
| WR-09/WR-10 named tests | `pytest tests/test_api.py::test_failed_fallback_keeps_rawdata_mode tests/test_coordinator.py::test_request_budget_matrix` | 4 passed | ✓ PASS |
| HA 2026.3 compatibility (changed modules) | ha2603-venv `pytest tests/test_api.py tests/test_coordinator.py` | 106 passed (HA 2026.3.0, aiohttp 3.13.3) | ✓ PASS |
| Probe-clock edges + randomized budget/revocation | Verifier scratch suite on an isolated HEAD copy | 15 passed (3 edges + 12 seeds) | ✓ PASS |
| Timer / background guard | grep `create_task\|call_later\|async_track_time` in api.py, coordinator.py | No match | ✓ PASS |

The scratch files are in the verifier scratchpad (`proj2/tests/test_zz_verify.py`), outside the repository.

### Probe Execution

Step 7c is not applicable. No `scripts/*/tests/probe-*.sh` exists, and the phase declares no probes.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DATA-01 | 04-03, 04-04 | Parse once into frozen models; platforms never inspect raw dicts | ✓ SATISFIED | Truth 2 |
| DATA-02 | 04-04, 04-06, 04-09 | One rawdata request per cycle; setup/hourly/restart rules; paginated fallback | ✓ SATISFIED | Truths 3, 14. DATA-02 does not contain the truth-17 wording |
| DATA-03 | 04-05 | Auth none/basic/bearer; per-request header; no leaks | ✓ SATISFIED | Truths 4, 11 |
| DATA-04 | 04-05, 04-08 | Only TraefikProxyApiError subclasses; no assert | ✓ SATISFIED | Truth 5 |
| DATA-05 | 04-02 | Typed TraefikRuntimeData | ✓ SATISFIED | Truth 6 |
| DATA-06 | 04-04, 04-07 | TraefikSnapshot with aggregates; `always_update=False` | ✓ SATISFIED | Truths 7, 8 |
| DATA-07 | 04-01, 04-05, 04-06 | Real, redacted, regenerable fixtures | ✓ SATISFIED | Truths 1, 10 (cert precondition advisory) |

All 7 IDs are claimed by plans, and none is orphaned. REQUIREMENTS.md lists all seven as `[ ]` / "Pending". That matches W26, which keeps them Pending until phase.complete. I did not edit REQUIREMENTS.md.

### Prohibitions

| Prohibition | Tier | Enforcement evidence | Disposition |
|-------------|------|----------------------|-------------|
| 04-01: no private IP/hostname/credential in fixtures; no test starts Docker | test | test_fixture_redaction.py; fixtures unchanged | verified |
| 04-04 / 04-05: no backend URL/IP; no credential in log/exception/repr; no session default Authorization | test | Unchanged code paths; suite green | verified |
| 04-07: cert alarm not hidden behind main-coordinator state; no TLS probe from main cycles | test | Unchanged; tests green | verified |
| 04-08: no userinfo accepted in newly entered URLs; no URL/credential in the construction error message | test | Unchanged; tests green (IN-09 flow-level args tracked for Phase 7) | verified |
| 04-09: at most one extra rawdata request per hour per client; no background or timer probing | test | Matrix rows (8)-(20); test_one_probe_per_arming_under_overlapping_calls; verifier property test (minimum gap 60 min over 12 adversarial schedules); timer grep empty | verified |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| .planning/phases/04-data-layer-correct-lean/04-CONTEXT.md | 89-94 | D-07 amendment describes the pre-M29 coupling | ⚠️ Warning | Spec/code drift (truth 17) |
| tests/test_coordinator.py | 444-447 | Row (15) comment over-claims "first one an hour after the switch, never in a failing cycle" (IN-12) | ℹ️ Info | Misleading comment |
| custom_components/traefik_proxy/api.py | 316-321 | Committed switch to the pages not logged (IN-14) | ℹ️ Info | Observability |
| custom_components/traefik_proxy/coordinator.py | 113-115 | `_probe_armed_at` also moves in rawdata mode; name and comment understate this (IN-13) | ℹ️ Info | Readability |

There are no TBD/FIXME/XXX/TODO/HACK markers in the four changed files (grep exit 1).

### Human Verification Required

#### 1. Accept or re-word the M29 probe-schedule change (truth 17)

**Test:** Choose one of two options:
- Add the override shown above to this file's frontmatter.
- Reword the D-07 amendment in `04-CONTEXT.md` and 04-09 truths 1 and 3. Suggested wording: "while paginated, /api/rawdata is retried once per `VERSION_RECHECK_INTERVAL` on a clock of its own, usually in the same cycle as the hourly version re-check; a post-failure re-check neither arms nor postpones it".

Then re-run verification.
**Expected:** The plan contract matches the code, and the status becomes `passed`.
**Why human:** This accepts a deliberate deviation from a written plan must-have. The behaviour itself is verified (truth 14).

The previous human item (Docker re-capture determinism) is closed by 04-UAT.md (truth 10).

### Gaps Summary

There are no gaps. Behaviour and wiring are fully verified:
- Both advisory weaknesses from the previous report (WR-09, WR-10) are fixed. Committed tests and verifier scratch tests under adversarial schedules confirm the fixes.
- The fixture determinism backstop is closed by the UAT run.
- All ROADMAP success criteria and DATA requirements are satisfied, and the suite is green on HA 2026.3 and on current HA.

What keeps the status at `human_needed` is a contract issue, not a behaviour issue. The WR-09 fix moved the probe off the version re-check cycle by design, but the 04-09 truths and the D-07 amendment were not updated. One override or one doc edit resolves it.

Non-blocking follow-ups:
- IN-12: add committed tests for the three probe-clock edges.
- Declare the cert precondition of the capture harness, or redact `serialNumber`.

---

_Verified: 2026-11-14T03:12:48Z_
_Verifier: Claude (gsd-verifier)_
