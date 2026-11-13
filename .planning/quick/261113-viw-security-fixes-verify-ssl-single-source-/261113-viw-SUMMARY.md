---
phase: 261113-viw-security-fixes-verify-ssl-single-source-
plan: 01
subsystem: config_flow / coordinator / services / distribution
tags: [security, verify_ssl, admin-service, reconfigure, compat, ha-minimum]
status: complete
requires: []
provides:
  - effective_verify_ssl(entry) + build_api_client(hass, entry) in coordinator.py
  - admin-only traefik_proxy.reload_routers
  - reconfigure without token prefill; same-host reconfigure
  - HA minimum 2026.3.0 (Python 3.14), CI on 3.14
affects:
  - custom_components/traefik_proxy (config_flow, coordinator, __init__, button, binary_sensor, strings)
  - hacs.json, .github/workflows/validate.yml, CLAUDE.md, .planning/PROJECT.md
tech-stack:
  added: []
  patterns:
    - "try probatio / except ImportError voluptuous fallback import"
    - "DeviceClass enums imported from .const with package fallback"
    - "single effective option value: options -> data -> default"
key-files:
  created:
    - tests/test_verify_ssl.py
    - tests/test_reconfigure.py
  modified:
    - custom_components/traefik_proxy/config_flow.py
    - custom_components/traefik_proxy/coordinator.py
    - custom_components/traefik_proxy/__init__.py
    - custom_components/traefik_proxy/button.py
    - custom_components/traefik_proxy/binary_sensor.py
    - custom_components/traefik_proxy/strings.json
    - custom_components/traefik_proxy/translations/en.json
    - tests/test_config_flow.py
    - tests/test_init.py
    - hacs.json
    - .github/workflows/validate.yml
    - CLAUDE.md
    - .planning/PROJECT.md
decisions:
  - "verify_ssl precedence is options -> data -> DEFAULT_VERIFY_SSL; reconfigure mirrors verify_ssl into options"
  - "reload_routers registered via async_register_admin_service; Reload button (no user context) still passes"
  - "Reconfigure aborts only when another entry owns the new host; check runs before the probe"
  - "HA minimum raised to 2026.3.0 (first HA with requires_python >=3.14.2); no Python 3.13 compat"
metrics:
  duration: ~15min
  completed: 2026-11-13
actuals:
  tokens: 11656
  tasks: 5
  commits: 5
plan_head_before: 88499295876fef40b1a16ad29d4b6348fa7e467e
plan_head_after: 1a07f14a0d1d25c70d6cd411edf1d2d423e61483
---

# Quick 261113-viw Plan 01: Security fixes (verify_ssl single source, admin reload, reconfigure token) Summary

Five local commits on `main`, none pushed:
- `verify_ssl` now comes from one effective value (options, then data, then default) in every path, including the running client.
- `reload_routers` is admin-only.
- The reconfigure form no longer sends the stored token to the frontend, and a reconfigure on the same host now works.
- HA minimum is honestly 2026.3.0 / Python 3.14.
- Strict pytest/mypy gates pass on HA 2026.10.4 and HA 2026.3.0.

## Commits

| # | Task | Hash | Subject |
|---|------|------|---------|
| 0 | Compat | b69eb97 | fix(compat): support HA 2026.10 (probatio, const moves) while keeping HA 2026.3 |
| 1 | Fix P (revised) | 0d1365e | build: require Home Assistant 2026.3.0 (Python 3.14 baseline) |
| 2 | Fix 1 | 5f091da | fix(config): resolve verify_ssl from one effective value in every path |
| 3 | Fix 2 | 77da5b9 | fix(services): restrict reload_routers service to admin users |
| 4 | Fix 5 + N3 | 1a07f14 | fix(config_flow): no token prefill in reconfigure; allow same-host reconfigure |

## Gate results per task

Environments:
- **G1-G4 (lock env):** HA 2026.10.4, Python 3.14.9, probatio 0.13.0.
- **G5:** HA 2026.3.0 (asserted via `homeassistant.const.__version__`), Python 3.14.9.
  - Installed as phcc 0.13.317 with uv override `homeassistant==2026.3.0`.
  - Venv: `/home/akentner/.cache/traefik-proxy-integration/ha2603-venv`, built during the precondition check without errors.

**Precondition baseline at 8849929** (matched the plan):
- G1: `1 failed, 168 passed` (voluptuous_serialize).
- G4: `Found 8 errors in 4 files`.
- G5: `169 passed`.

| Task | G1 pytest (HA 2026.10.4) | G2 ruff check | G3 ruff format | G4 mypy --strict | G5 pytest (HA 2026.3.0) |
|------|--------------------------|---------------|----------------|------------------|-------------------------|
| 0 | `169 passed in 15.84s` | All checks passed! | 23 files already formatted | Success: no issues found in 11 source files | `169 passed in 15.18s` |
| 1 | `169 passed in 15.79s` | All checks passed! | 23 files already formatted | Success: no issues found in 11 source files | `169 passed in 15.05s` |
| 2 | `179 passed in 16.27s` | All checks passed! | 24 files already formatted | Success: no issues found in 11 source files | `179 passed in 15.34s` |
| 3 | `181 passed in 16.00s` | All checks passed! | 24 files already formatted | Success: no issues found in 11 source files | `181 passed in 15.37s` |
| 4 | `188 passed in 16.28s` | All checks passed! | 25 files already formatted | Success: no issues found in 11 source files | `188 passed in 15.65s` |

Additional checks:
- Task 4: `scripts/hassfest_checks.py strings-shape` passed.
- Every task-specific grep/awk gate in the plan's `<verify>` passed.
- RED was observed before GREEN for each TDD task:
  - Task 2: ImportError on `effective_verify_ssl`.
  - Task 3: the non-admin test failed, with no Unauthorized raised.
  - Task 4: 6 of 7 failed. The conflict test failed because the old code probed the other host before aborting.

The 3.14-only except clauses are unchanged:
- `tls.py:200`
- `config_flow.py` (now line 174)
- `tests/conftest.py:166` and `:173`

**G5 venv:** kept at `/home/akentner/.cache/traefik-proxy-integration/ha2603-venv`, not removed.

## Deviations from Plan

**1. [Process] Commits made on `main` despite the protected-branch guard**
- The executor's pre-commit guard reports `main` as protected (`git.base-branch --is-protected main` returns `true`).
- I committed there anyway, for three reasons:
  - The plan explicitly requires "Five atomic commits on `main`, not pushed".
  - The orchestrator stated the same.
  - `.planning/config.json` has `git.branching_strategy: "none"`.
- The config was not changed. Nothing was pushed.

There were no code deviations; every task was executed as written.

## Notes from execution

- **N4:** with HA 2026.10.4, the reconfigure tests produce no failing deprecation, and all pass. The `async_update_reload_and_abort` + update-listener usage report is still a follow-up, as planned.

## N8: version mentions left unchanged

CLAUDE.md:
- Lines 45, 143 and 167: aiohttp versions.
- Line 145: a Python deprecation fact.
- Lines 149 and 171: format examples.
- Line 159: "PEP-695 works on 3.13".
- Line 188: a source citation.
- Line 125: the Alternative and rationale cells.

Elsewhere:
- `.planning/research/{STACK,SUMMARY,ARCHITECTURE}.md`: research. A future CLAUDE.md regeneration from STACK.md could bring 2025.4 back.
- `.planning/phases/**`: history.
- `.planning/REQUIREMENTS.md:122` (DIST-02): a completed requirement.
- `.planning/ROADMAP.md:214`: the Phase 4 criterion "pytest on Python 3.13". Flag it for Phase 4.
- `.pre-commit-config.yaml:11` (`python3.13`): the hook interpreter. The file also has stale `custom_components/traefik` paths.
- `.claude/skills/**`.

## Known Stubs

None.

## Threat Flags

None. No new network endpoints or auth paths beyond the plan's threat model:
- T-261113-01, -02, -03, -05 and -06 are mitigated as planned.
- T-261113-04 and -07 are accepted.

## Self-Check: PASSED

- Files found:
  - `tests/test_verify_ssl.py`
  - `tests/test_reconfigure.py`
  - all modified files listed above
- Commits found in the HEAD ancestry: b69eb97, 0d1365e, 5f091da, 77da5b9, 1a07f14.
- `git rev-list --count 8849929..HEAD` = 5.
