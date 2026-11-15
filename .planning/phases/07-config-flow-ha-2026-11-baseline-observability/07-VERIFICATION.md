---
phase: 07-config-flow-ha-2026-11-baseline-observability
verified: 2026-11-15T15:50:27Z
status: passed
score: 84/84 must-haves verified (6 roadmap SC + 78 plan truths)
covered_files:
  - ".github/workflows/validate.yml"
  - ".planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-01-PLAN.md"
  - ".planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-01-SUMMARY.md"
  - ".planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-02-PLAN.md"
  - ".planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-02-SUMMARY.md"
  - ".planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-03-PLAN.md"
  - ".planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-03-SUMMARY.md"
  - ".planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-04-PLAN.md"
  - ".planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-04-SUMMARY.md"
  - ".planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-05-PLAN.md"
  - ".planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-05-SUMMARY.md"
  - ".planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-06-PLAN.md"
  - ".planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-06-SUMMARY.md"
  - ".planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-07-PLAN.md"
  - ".planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-07-SUMMARY.md"
  - ".planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-08-PLAN.md"
  - ".planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-08-SUMMARY.md"
  - ".planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-09-PLAN.md"
  - ".planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-09-SUMMARY.md"
  - ".pre-commit-config.yaml"
  - "custom_components/traefik_proxy/__init__.py"
  - "custom_components/traefik_proxy/api.py"
  - "custom_components/traefik_proxy/binary_sensor.py"
  - "custom_components/traefik_proxy/cert_coordinator.py"
  - "custom_components/traefik_proxy/config_flow.py"
  - "custom_components/traefik_proxy/const.py"
  - "custom_components/traefik_proxy/coordinator.py"
  - "custom_components/traefik_proxy/data.py"
  - "custom_components/traefik_proxy/diagnostics.py"
  - "custom_components/traefik_proxy/entity.py"
  - "custom_components/traefik_proxy/entity_manager.py"
  - "custom_components/traefik_proxy/translations/de.json"
  - "custom_components/traefik_proxy/translations/en.json"
  - "hacs.json"
  - "pyproject.toml"
  - "scripts/hassfest_checks.py"
  - "tests/conftest.py"
  - "tests/test_api.py"
  - "tests/test_api_pagination.py"
  - "tests/test_baseline_guards.py"
  - "tests/test_binary_sensor_tls_expiring.py"
  - "tests/test_cert_coordinator.py"
  - "tests/test_cert_entity_state.py"
  - "tests/test_cert_lifecycle.py"
  - "tests/test_certificates_problem.py"
  - "tests/test_config_flow.py"
  - "tests/test_coordinator.py"
  - "tests/test_devices.py"
  - "tests/test_diagnostics.py"
  - "tests/test_entity_manager.py"
  - "tests/test_init.py"
  - "tests/test_migration.py"
  - "tests/test_options_flow.py"
  - "tests/test_platforms_real_fixtures.py"
  - "tests/test_reconfigure.py"
  - "tests/test_repairs.py"
  - "tests/test_sensor_tls.py"
  - "tests/test_translations.py"
  - "tests/test_verify_ssl.py"
covered_digest: "v4:sha256:db60a7ff6a4d86ea9e2e68c643dd6ec86b69322235fbd7d63e085a7161c40845"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 84/84
  gaps_closed:
    - "Human item 1 (three FLOW-08 test-tier prohibitions without a wired regression test): closed by tests/test_baseline_guards.py (be382e4, 9a7ff5d); each of the six guards was shown by the verifier to fail on an injected violation"
    - "Human item 2 (M37 vs I1 wording): recorded as an acknowledged deviation; decision log M37 makes it a notification duty at phase completion, which the orchestrator carries in its final report"
    - "Human item 3 (WR-01 residual: verify_ssl flip on an unchanged scheme+host:port reuses the stored secret): orchestrator decision ACCEPT; also listed in 07-SECURITY.md non-blocking observations"
    - "Human item 4 (visual UI check en/de in a throwaway HA 2026.11): moved to deferred (Phase 8, decision M35)"
  gaps_remaining: []
  regressions: []
deferred:
  - truth: "Pre-commit hooks actually run on custom_components/traefik_proxy and scripts/hassfest_checks.py strings-shape passes (review WR-04; strings-shape still exits 1 on the valid top-level 'entity' key)"
    addressed_in: "Phase 8"
    evidence: "ROADMAP Phase 8 SC3: 'pre-commit hooks target custom_components/traefik_proxy on Python 3.14 and actually run'; REQUIREMENTS REL-04; deferred-items.md rows 1-2"
  - truth: "CI hygiene: job timeouts (WR-05), locked minimum-HA install (WR-06), actions pinned by SHA (WR-07)"
    addressed_in: "Phase 8"
    evidence: "REQUIREMENTS REL-05: 'pins all actions by tag or SHA'; ROADMAP Phase 8 SC3 (CI); 07-REVIEW-FIX.md Deferred section"
  - truth: "pyproject coverage target points at custom_components.traefik_proxy (IN-07; the dev run currently reports 'Module custom_components.traefik was never imported')"
    addressed_in: "Phase 8"
    evidence: "ROADMAP Phase 8 SC3: 'pyproject.toml coverage points at custom_components.traefik_proxy with a fail_under gate'"
  - truth: "Cert-cycle failure chain consistency (IN-03), impossible-state branches (IN-04, IN-05)"
    addressed_in: "Phase 8"
    evidence: "07-REVIEW-FIX.md: deferred to Phase 8 per 07-CONTEXT 'Out of scope (Phase 8)'"
  - truth: "Visual check of the Add Integration / Re-authenticate / Reconfigure / Options dialogs and the insecure_credentials repair in a throwaway HA 2026.11 (en and de): conditional fields render per auth type, secrets masked, labels/help texts and s/d/h units render"
    addressed_in: "Phase 8"
    evidence: "Decision log M35: 'visueller Check in einer Wegwerf-HA 2026.11 (de/en ...) wird in Phase 8 nachgeholt'; Carry-over overview Phase 8: 'visueller Check (M35)'. Serialized schema, 'visible' conditions and en/de key parity are covered by tests in Phase 7"
advisory:
  - finding: "The 'requirement text' slice of the 07-03 FLOW-08 prohibition has no wired test: 9a7ff5d removed the REQUIREMENTS/ROADMAP check because PR branches are cut without .planning/"
    category: other
    reason: "The code-path and comment slices are test-enforced. The planning-doc slice is clean at HEAD (verifier grep: no '2026.3.0/2026.3.x' or 'would raise min HA' in REQUIREMENTS.md, 'homeassistant: 2026.11.0' present, no '2026.3' in ROADMAP Phase 8; the only REQUIREMENTS hit is ENT-09 history, which 07-03-PLAN explicitly keeps). Planning docs are not shipped. A skip-if-.planning-absent variant would restore enforcement if wanted"
    evidence_status: "none provided (no failing state exists; scope note only)"
---

# Phase 7: Config flow, HA 2026.11 baseline, observability — Verification Report

**Phase Goal:** Users can set up, re-authenticate and reconfigure the integration with the authentication Traefik deployments actually use (none / basic / bearer), options changes reload the entry without any update listener (HA 2026.12-safe), errors are translated and actionable, and support data is available as a redacted diagnostics download — fully in English and German, on HA 2026.11.0+.
**Verified:** 2026-11-15T15:50:27Z
**Status:** passed
**Re-verification:** Yes — after the guard tests (be382e4, 9a7ff5d) and the security audit (9b926c0); previous run at HEAD `4ceef76` was `human_needed`

The verifier produced all automated evidence below at HEAD `9a7ff5d`. It used no SUMMARY claim as evidence.

## What changed since the first run (4ceef76 → 9a7ff5d)

`git diff --stat 4ceef76..HEAD` touches only two files:
- `tests/test_baseline_guards.py` (new, 182 lines);
- `07-SECURITY.md` (new).

No production file changed, so every first-run truth is carried over after a regression check: both full suites, ruff and mypy were re-run (see the gates below).

## Gates run by the verifier (this run)

| Gate | Result |
|---|---|
| `uv run pytest -q` (dev, HA 2026.11.1) | 1056 passed (1050 + 6 new guards), exit 0 |
| `~/.cache/traefik-proxy-integration/ha2611-venv` `python -m pytest -q -o addopts="-p no:respx" tests` (`homeassistant.const.__version__` = 2026.11.0) | 1056 passed, exit 0 |
| `uv run ruff check custom_components tests scripts` | All checks passed |
| `uv run ruff format --check custom_components tests` | 48 files already formatted |
| `uv run mypy --strict custom_components/traefik_proxy` | no issues in 16 source files |

The first run's gates (hassfest 0 invalid, `config_flow.py` 100 % line coverage, M39 20/20) depend on files that have not changed since `4ceef76`, so those results still hold.

## FLOW-08 guard verification (closes first-run human item 1)

`tests/test_baseline_guards.py` has six AST and filesystem guards. They need no HA fixture and read no planning docs. The verifier read the file, then injected one violation at a time and reverted each with `git checkout --`. The working tree was clean afterwards.

| Injected violation | Failing test (only this one failed, 5 others passed) |
|---|---|
| `getattr(object(), "_shutdown_requested", None)` in `coordinator.py` | `test_shipped_code_reads_no_private_base_class_attribute` |
| `# needed for HA 2026.3` in `const.py` | `test_no_text_for_releases_before_the_minimum` |
| `try: import foo_mod / except ModuleNotFoundError` in `tests/conftest.py` | `test_no_import_shim_in_integration_or_tests` |
| `from homeassistant.const import MAJOR_VERSION` in `api.py` | `test_no_home_assistant_version_gate` |
| `import voluptuous as vol2` in `config_flow.py` | `test_no_import_of_pre_baseline_modules` |
| `# pytest-homeassistant-custom-component` in `pyproject.toml` | `test_no_old_test_package_or_helper` |
| (all reverted) | 6 passed |

Scope notes:
- The private-attribute guard checks a fixed list of 10 private `DataUpdateCoordinator` attributes. It catches both attribute access and name strings such as `getattr(..., "_x")`. This covers the base class named in 07-02 and T-07-01.
- Shipped code reaches the HA base class only through the coordinators, so this list is enough for the prohibition as written.

## Goal Achievement

### Observable Truths — Roadmap Success Criteria

| # | Truth | Status | Evidence |
|---|---|---|---|
| SC1 | User step offers auth selector (none/basic/bearer) with PASSWORD selectors and per-field `data_description`; 0.3.0 entries migrate (token → bearer, empty → none) to unique_id `host:port`, title = host; "none" clears credentials | ✓ VERIFIED | `config_flow.py:96-130` SelectSelector + `data_entry_flow.Optional(..., visible=...)`, `TextSelectorType.PASSWORD`; en/de `config.step.{user,reauth_confirm,reconfigure}` key parity; `__init__.py` 1.2→1.3 migration; migration/auth-switch tests pass (regression: unchanged files, suites green) |
| SC2 | No `add_update_listener`; `OptionsFlowWithReload` with NumberSelectors (s/d/h, box), per-item toggle, grace period 1–168 h default 24 h; reauth/reconfigure via `async_update_reload_and_abort`; reconfigure moves unique_id; no `report_usage` | ✓ VERIFIED | `test_options_form_selectors`, `test_changed_options_reload_with_new_values` (`entry.update_listeners == []`), `test_changed_grace_period_applies_after_options_reload`, `test_reconfigure_moves_unique_id_and_host_title` — green in this run |
| SC3 | Every flow error path tested, `config_flow.py` 100 % line coverage; `ConfigEntryAuthFailed`/`NotReady`/`UpdateFailed` carry translation keys from `exceptions` | ✓ VERIFIED | 100 % coverage measured in run 1 (`config_flow.py` unchanged since); translated raises and `error_reason_translation_key` tests green |
| SC4 | Diagnostics return entry data, options and snapshot with password/token/username redacted; `http://` + credentials raises a repair that disappears when fixed or on unload/remove, using `config_entry_id` | ✓ VERIFIED | `diagnostics.py` (`async_redact_data`, `TO_REDACT`, `_safe_url`); `tests/test_diagnostics.py`, `tests/test_repairs.py` green |
| SC5 | `hacs.json` + test floor require 2026.11.0; CI job pinned to 2026.11.0; sub-devices via 2026.11 device API; every repair has `config_entry_id`; unload uses `async_unload_platforms_or_raise`; no private HA attribute read | ✓ VERIFIED | `hacs.json` 2026.11.0; `pytest-homeassistant>=2026.11.0`; `validate.yml` `test-min-ha`; `entity.py` `via_device_id=main.id` (M37, see dispositions); no private attribute read, now test-enforced; suite green on exactly 2026.11.0 |
| SC6 | `strings.json`, YAML import step and strings, A-18 dead code removed; en.json single source; de.json full key parity (tested); hassfest translation validation passes; tests/ruff/mypy green | ✓ VERIFIED | `strings.json` absent; `test_translations.py` parity green; hassfest result from run 1 (translation files unchanged); gates green this run |

### Observable Truths — Plan must_haves (78)

| Plan | Truths | Status | Notes for this run |
|---|---|---|---|
| 07-01 (FLOW-08) | 6 | ✓ 6/6 | Shim, version-gate and old-test-package checks are now test-enforced |
| 07-02 (FLOW-08) | 7 | ✓ 7/7 | Private-attribute read is now test-enforced |
| 07-03 (FLOW-07, FLOW-08) | 5 | ✓ 5/5 | `2026.3` and "older Home Assistant" text in cc/tests/scripts are now test-enforced |
| 07-04 (FLOW-04, FLOW-05) | 7 | ✓ 7/7 | unchanged code; tests green |
| 07-05 (FLOW-01, FLOW-03) | 16 | ✓ 16/16 | unchanged code; tests green |
| 07-06 (FLOW-02) | 9 | ✓ 9/9 | unchanged code; tests green |
| 07-07 (FLOW-02) | 9 | ✓ 9/9 | unchanged code; tests green |
| 07-08 (FLOW-04, FLOW-07) | 9 | ✓ 9/9 | unchanged code; tests green |
| 07-09 (DIAG-04, FLOW-06, FLOW-07) | 10 | ✓ 10/10 | unchanged code; tests green |

The first run (HEAD `4ceef76`) holds the detailed evidence per truth. No production file changed since then, and the regression gates pass.

**Score:** 84/84 truths verified (0 present, behavior-unverified).

### Prohibitions

| Req | Prohibition | Tier | Disposition |
|---|---|---|---|
| FLOW-08 (07-01) | No import shim / helper for HA < 2026.11.0 | test | ✓ enforced: `test_no_import_shim_in_integration_or_tests`, `test_no_import_of_pre_baseline_modules`, `test_no_home_assistant_version_gate`, `test_no_old_test_package_or_helper` (fail-first shown by the verifier) |
| FLOW-08 (07-02) | No read of an HA-private base-class attribute | test | ✓ enforced: `test_shipped_code_reads_no_private_base_class_attribute` (fail-first shown) |
| FLOW-08 (07-03) | No code path/comment/requirement text only for HA < 2026.11.0 | test | ✓ enforced for code and comments: `test_no_text_for_releases_before_the_minimum` (fail-first shown). The planning-doc slice is clean at HEAD by grep, see the advisory note |
| FLOW-04 | Never follow a redirect | test | ✓ enforced |
| FLOW-05 | No URL/header/credential in exception message or placeholder | test | ✓ enforced |
| FLOW-01 ×2 | No unused-mode credential kept; no stored secret sent to the form | test | ✓ enforced |
| FLOW-03 | No overwrite of a renamed title; no takeover of another entry's unique_id | test | ✓ enforced |
| FLOW-02 ×2 | No update listener; no removal before the configured grace | test | ✓ enforced |
| FLOW-04 ×2 | No logging of form input; no own-key error reported as unknown/cannot_connect | test | ✓ enforced |
| DIAG-04 | No credential or raw payload in diagnostics | test | ✓ enforced |
| FLOW-06 | No leftover insecure_credentials repair | test | ✓ enforced |

No flagged prohibitions remain.

### Dispositions of the first-run human items

| # | Item | Disposition | Basis |
|---|---|---|---|
| 1 | Three FLOW-08 prohibitions without a wired test | **Closed** | Six guard tests; the verifier showed fail-first by injection (table above) |
| 2 | M37: `via_device_id=` instead of `ChildDeviceInfo` (I1 wording) | **Acknowledged deviation** (notification duty, not an open verification) | Decision log M37 ("präzisiert I1 … beim Abschluss dem User als Abweichung vom Wortlaut von I1 nennen"). The orchestrator reports it in its final report to the user. ROADMAP SC5 ("sub-devices link via the 2026.11 device API") is met |
| 3 | WR-01 residual: a `verify_ssl` flip on an unchanged scheme+host:port and auth type reuses the stored secret | **Accepted residual** (orchestrator decision ACCEPT) | The options flow (07-06) deliberately lets the user turn verification off without re-entering credentials. Requiring re-entry only in reconfigure would be inconsistent. T-07-06 covers scheme, host:port and auth-type changes, and `test_changed_target_requires_secret_again` covers those. The residual is listed in `07-SECURITY.md` non-blocking observations |
| 4 | Visual UI check en/de in a throwaway HA 2026.11 | **Deferred to Phase 8** | Decision M35 and Carry-over Phase 8 "visueller Check (M35)". Tests already cover the serialized schema, the `visible` conditions and en/de parity |

### Security cross-check

`07-SECURITY.md` (9b926c0): `status: verified`, `threats_open: 0`. It lists the WR-01 `verify_ssl` residual and the HTTP-only scope of the `insecure_credentials` repair as non-blocking observations. Both are consistent with the dispositions above.

### Required Artifacts

| Artifact | Status | Details |
|---|---|---|
| `pyproject.toml`, `hacs.json`, `.github/workflows/validate.yml` | ✓ VERIFIED | unchanged since run 1 |
| `custom_components/traefik_proxy/*` (13 files) | ✓ VERIFIED | unchanged since run 1; mypy strict clean |
| `custom_components/traefik_proxy/translations/{en,de}.json` | ✓ VERIFIED | parity test green |
| `tests/test_baseline_guards.py` (new) | ✓ VERIFIED | 182 lines, 6 substantive guards, collected and run by both suites, fail-first shown |

### Key Link Verification

Unchanged since run 1. All 14 links are WIRED. One link is new:

| From | To | Via | Status |
|---|---|---|---|
| `tests/test_baseline_guards.py` | `custom_components/traefik_proxy`, `tests/`, `scripts/`, `pyproject.toml` | `ROOT`/`PACKAGE` paths, `ast.parse`, byte grep | ✓ WIRED (runs in the default `uv run pytest` and in the `test-min-ha` job's `tests` path) |

### Data-Flow Trace (Level 4)

Unchanged since run 1: the diagnostics snapshot, the diagnostics certificates and the options form defaults are all FLOWING.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full suite on dev HA 2026.11.1 | `uv run pytest -q` | 1056 passed | ✓ PASS |
| Full suite on minimum HA 2026.11.0 | ha2611-venv pytest | 1056 passed | ✓ PASS |
| FLOW-08 guards fail on regression | 6 injections, one at a time | each failed exactly its own test; 6 passed after revert | ✓ PASS |

### Probe Execution

Not applicable. No `scripts/*/tests/probe-*.sh` exists, and no plan declares a probe.

### Requirements Coverage

| Requirement | Source Plan | Status | Evidence |
|---|---|---|---|
| FLOW-01 | 07-05 | ✓ SATISFIED | SC1 |
| FLOW-02 | 07-06, 07-07 | ✓ SATISFIED | SC2 |
| FLOW-03 | 07-05 | ✓ SATISFIED | reauth/reconfigure via `async_update_reload_and_abort`; unique_id follows reconfigure |
| FLOW-04 | 07-04, 07-08 | ✓ SATISFIED | full error matrix; 100 % coverage |
| FLOW-05 | 07-04 | ✓ SATISFIED | translated HA exceptions |
| FLOW-06 | 07-09 | ✓ SATISFIED | repair lifecycle with `config_entry_id` |
| FLOW-07 | 07-03, 07-08, 07-09 | ✓ SATISFIED | single en source, de parity, hassfest translations |
| FLOW-08 | 07-01, 07-02, 07-03 | ✓ SATISFIED | SC5; prohibitions now test-enforced |
| DIAG-04 | 07-09 | ✓ SATISFIED | SC4 |

No requirement is orphaned.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `tests/test_baseline_guards.py` | — | TBD/FIXME/XXX/TODO/HACK | — | none |
| `scripts/hassfest_checks.py` | 75 | strings-shape forbids the valid top-level `entity` key (exit 1) | ⚠️ Warning (deferred) | Phase 8 REL-04 / SC3 |
| `pyproject.toml` | 24 | `--cov=custom_components.traefik` measures nothing | ℹ️ Info (deferred) | Phase 8 SC3 |
| `const.py` | 54-75 | pre-existing planning references | ℹ️ Info | not added in this phase; Phase 8 REL-06 |
| `.planning/REQUIREMENTS.md` | 245 | ENT-09 "HA 2026.3 API" (history, explicitly kept by 07-03-PLAN) | ℹ️ Info | documentation only |
| `diagnostics.py` | 81 | router `rule` strings dumped verbatim | ℹ️ Info | edge case, not a must-have |

### Advisory (New Scope, Unevidenced)

| # | Finding | Category | Why Advisory |
|---|---|---|---|
| 1 | No test covers the "requirement text" slice of the 07-03 prohibition; 9a7ff5d dropped the `.planning/` check so that PR branches stay green | other | The slice is clean at HEAD, planning docs do not ship, and no failing state exists. A skip-if-absent variant would restore it |

### Human Verification Required

None. All four first-run items are resolved (see Dispositions):
- item 1 is closed by tests;
- item 2 is an acknowledged deviation, reported by the orchestrator;
- item 3 is an accepted residual;
- item 4 is deferred to Phase 8 (M35).

### Gaps Summary

No gaps. All 6 roadmap success criteria and all 78 plan truths hold at `9a7ff5d`:
- Both suites pass with 1056 tests, on HA 2026.11.1 and on exactly HA 2026.11.0.
- ruff and mypy --strict are clean.
- The three FLOW-08 prohibitions now have regression tests, and the verifier showed that each one fails on an injected violation.

Deferred to Phase 8:
- WR-04..07 and IN-03/04/05/07;
- the visual UI check (M35).

---

_Verified: 2026-11-15T15:50:27Z_
_Verifier: Claude (gsd-verifier)_
