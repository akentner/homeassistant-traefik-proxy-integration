---
phase: 261113-viw-security-fixes-verify-ssl-single-source-
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - custom_components/traefik_proxy/config_flow.py
  - custom_components/traefik_proxy/__init__.py
  - custom_components/traefik_proxy/button.py
  - custom_components/traefik_proxy/binary_sensor.py
  - custom_components/traefik_proxy/coordinator.py
  - custom_components/traefik_proxy/strings.json
  - custom_components/traefik_proxy/translations/en.json
  - tests/test_config_flow.py
  - tests/test_verify_ssl.py
  - tests/test_init.py
  - tests/test_reconfigure.py
  - hacs.json
  - .github/workflows/validate.yml
  - CLAUDE.md
  - .planning/PROJECT.md
autonomous: true
requirements: [SEC-COMPAT-0, SEC-FIX-P, SEC-FIX-1, SEC-FIX-2, SEC-FIX-5]

estimate:
  tokens: 115000
  raw_tokens: 115000
  tasks: 5
  confidence: low

must_haves:
  truths:
    - "The full test suite passes with 0 failures on both the lock env (HA 2026.10.4) and a throwaway HA 2026.3.0 env, and mypy --strict reports 0 errors, after every commit"
    - "The integration imports and runs on HA 2026.3.0 (voluptuous + voluptuous_serialize, DeviceClass enums in the package __init__) and on HA 2026.10.x (probatio, DeviceClass enums in .const)"
    - "hacs.json requires Home Assistant 2026.3.0, the first HA Core release whose PyPI requires_python is >=3.14 (>=3.14.2). The CI lint and test jobs run on Python 3.14"
    - "A user who sets verify_ssl=False during setup gets a runtime client with verify_ssl=False. After options False followed by a reconfigure with True, the runtime client, entry.data and entry.options all say True. The options form, the reconfigure form and the reauth probe all use the effective value. An options change reaches the running client without a restart"
    - "A non-admin call to traefik_proxy.reload_routers raises Unauthorized; admin calls and the Reload button still work"
    - "The reconfigure form never contains the stored token. An empty or omitted token keeps it (also for the probe), and a non-empty token replaces it"
    - "Reconfigure on the same host succeeds. A host change to an unused host succeeds. Reconfiguring to a host owned by ANOTHER entry aborts with already_configured"
  artifacts:
    - path: "custom_components/traefik_proxy/config_flow.py"
      provides: "probatio/voluptuous fallback import; effective_verify_ssl use; same-host-safe reconfigure; no token prefill"
      contains: "import probatio as vol"
    - path: "custom_components/traefik_proxy/coordinator.py"
      provides: "effective_verify_ssl(entry) + build_api_client(hass, entry)"
      contains: "def effective_verify_ssl"
    - path: "custom_components/traefik_proxy/__init__.py"
      provides: "admin-only reload_routers; options listener rebuilds the API client"
      contains: "async_register_admin_service"
    - path: "tests/test_verify_ssl.py"
      provides: "Fix 1 tests (unit + a-e)"
    - path: "tests/test_reconfigure.py"
      provides: "Fix 5 + same-host reconfigure tests"
    - path: "hacs.json"
      provides: "HA minimum 2026.3.0"
      contains: "2026.3.0"
  key_links:
    - from: "custom_components/traefik_proxy/coordinator.py build_api_client"
      to: "effective_verify_ssl"
      via: "verify_ssl=effective_verify_ssl(entry)"
      pattern: "verify_ssl=effective_verify_ssl\\(entry\\)"
    - from: "custom_components/traefik_proxy/config_flow.py async_step_reconfigure"
      to: "entry.options[verify_ssl]"
      via: "async_update_reload_and_abort(..., options={**entry.options, CONF_VERIFY_SSL: ...})"
      pattern: "options=\\{\\*\\*entry\\.options"
    - from: "custom_components/traefik_proxy/button.py async_press"
      to: "admin-gated reload_routers service"
      via: "hass.services.async_call without user context (user_id None passes the admin gate)"
      pattern: "async_call\\(DOMAIN, \"reload_routers\""
---

<objective>
Five atomic commits on `main`, not pushed, in this order:

- **Task 0, compat:** make the existing suite and `mypy --strict` fully green against the lock env (HA 2026.10.4, probatio), while staying runtime-compatible with HA 2026.3.0. Every later commit then runs with strict gates and no baseline allowances.
- **Task 1, Fix P (revised by the user):** raise the HA minimum to 2026.3.0 instead of adding Python 3.13 compatibility. Run CI on 3.14. Update the stated minimums.
- **Task 2, Fix 1:** one effective `verify_ssl` value (options, then data, then default) in every path, including the running client.
- **Task 3, Fix 2:** `reload_routers` is admin-only, and the Reload button keeps working.
- **Task 4, Fix 5 + N3:** no token prefill in reconfigure, and empty keeps the token. Same-host reconfigure works; only another entry's unique_id aborts.

Purpose: close a MITM token-theft path, a privilege gap and a token disclosure to the frontend. Make the HA minimum honest. Make the test and type gates trustworthy on both supported HA ends.
Output: 5 commits, each with its tests. A SUMMARY with the HA versions tested and their pytest counts.
</objective>

<execution_context>
@~/.claude/gsd-core/workflows/execute-plan.md
@~/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@custom_components/traefik_proxy/config_flow.py
@custom_components/traefik_proxy/coordinator.py
@custom_components/traefik_proxy/__init__.py
@custom_components/traefik_proxy/button.py
@tests/test_coordinator.py
@tests/test_init.py

Authoritative brief: /tmp/akentner/claude-1000/-home-akentner-Projekte-homeassistant-traefik-proxy-integration/ffd65077-887f-4672-b93b-bc8488ba1f2c/scratchpad/sec-fixes-brief.md. Its "Fix P — REVISED" section supersedes the old Fix P. The user's decisions on N2, N3 and N5 were relayed by the coordinator; they are listed in the Decisions section below.

## Verified facts (planning time, HEAD 8849929)

**Brief anchors.** All match HEAD:
- `config_flow.py:166`, `:338`, `:401-408`, `:414`, `:422`
- `coordinator.py:93`
- `__init__.py:151`
- `tls.py:200`

**Lock env.** `uv.lock` is gitignored and resolved fresh:
- Python 3.14.9
- homeassistant 2026.10.4
- pytest-homeassistant-custom-component (phcc) 0.13.375
- probatio 0.13.0
- ruff 0.17.5

The real `voluptuous` 0.16.0 is also on disk, pulled in by annotatedyaml and hass_nabucasa. At runtime HA's package `__init__` calls `probatio.compat.install_as_voluptuous()`, so `import voluptuous` resolves to probatio's shim. In the lock env, `voluptuous.Schema is probatio.Schema` (checked; the same holds for Optional, Required, All, Range and Invalid). mypy, however, reads the real voluptuous 0.16.0 from disk. That is the cause of the 6 probatio type errors.

**HEAD baseline in the lock env:**
- pytest: 168 passed, 1 failed (`tests/test_config_flow.py::test_user_schema_serializes_for_config_flow_endpoint`, `ModuleNotFoundError: voluptuous_serialize`).
- `mypy --strict`: 8 errors.
  - 6 `probatio` arg-type errors: `config_flow.py` lines 229, 278, 307, 365, 430 and `__init__.py:155`.
  - `button.py:15`: `ButtonDeviceClass` is not explicitly exported.
  - `binary_sensor.py:9`: `BinarySensorDeviceClass` is not explicitly exported.
- ruff is clean.

**HEAD baseline against HA 2026.3.0** (throwaway env, see G5): 169 passed.

**Validation library matrix:**

| HA | voluptuous | voluptuous-serialize | probatio | DeviceClass enums | Serializer used by `helpers/data_entry_flow.py` | Source |
|----|-----------|----------------------|----------|-------------------|--------------------------------------------------|--------|
| 2026.3.0 | 0.15.2 | 2.7.0 | absent | defined in `components/{button,binary_sensor}/__init__.py` | `voluptuous_serialize.convert(schema, custom_serializer=cv.custom_serializer)` (line 52) | tag `2026.3.0`: `pyproject.toml` lines 82-84, `requirements.txt` lines 58-60, `homeassistant/package_constraints.txt` lines 75-77 (raw.githubusercontent.com/home-assistant/core/2026.3.0/...); installed env |
| 2026.4.0 - 2026.8.0 | 0.15.2 | 2.7.0 | absent | package `__init__` | (not checked) | PyPI `requires_dist`, https://pypi.org/pypi/homeassistant/<v>/json |
| 2026.9.0 | dropped | dropped | 0.11.4 | package `__init__` | (not checked) | PyPI `requires_dist` |
| 2026.10.0 / 2026.10.4 | not required (0.16.0 present transitively, shadowed) | absent | 0.13.0 | moved to `.const`, re-exported from `__init__` with `noqa: F401` (not an explicit re-export for mypy) | `probatio.to_field_list(schema, custom_serializer=cv.custom_serializer)` (line 53) | PyPI `requires_dist`; installed venv; tag sources |

**HA minimum for Fix P.** Sources: https://pypi.org/pypi/homeassistant/json, plus `/2026.3.0/json` and `/2026.2.3/json`.
- The first release with `requires_python` >=3.14 is **2026.3.0**: `>=3.14.2` on the wheel and the sdist, uploaded 2026-03-04.
- 2026.2.3 declares `>=3.13.2`.

**phcc for HA 2026.3.0.** No phcc release pins `homeassistant==2026.3.0`:
- 0.13.316 (2026-02-21) pins 2026.2.3 and requires `>=3.13`.
- **0.13.317** (2026-03-07) pins 2026.3.1 and requires `>=3.14`. It is the first phcc release with a 2026.3.x pin.
- Source: https://pypi.org/pypi/pytest-homeassistant-custom-component/0.13.317/json.
- The plan therefore installs phcc 0.13.317 with a uv override `homeassistant==2026.3.0`. Verified at planning time:
  - The install succeeds and `homeassistant.const.__version__ == "2026.3.0"` on Python 3.14.9.
  - The env contains voluptuous 0.15.2 and voluptuous_serialize 2.7.0, and no probatio.
  - HEAD gives 169 passed in it.

**APIs used by the plan.** Each one was checked in both 2026.3.0 (tag source and installed env) and 2026.10.4 (installed env):
- `ConfigFlow.async_update_reload_and_abort(..., options=...)`
- `ConfigFlow._async_current_entries(include_ignore=...)`
- `ConfigFlow._get_reconfigure_entry`
- `homeassistant.helpers.service.async_register_admin_service(hass, domain, service, service_func, schema=..., supports_response=...)`
- `homeassistant.exceptions.Unauthorized`
- `homeassistant.core.Context`
- `homeassistant.data_entry_flow.FlowResultType`
- the phcc fixtures `hass_admin_user` and `hass_read_only_user`
- `MockConfigEntry.start_reconfigure_flow` and `start_reauth_flow`

**Task 0 prototype.** It was applied to a scratch copy of the repo at planning time. Result: ruff check and format clean, `mypy --strict` "no issues found in 11 source files" (so every `type: ignore` below is used), pytest 169 passed on 2026.10.4 and 169 passed on 2026.3.0. The Fix 2 registration on top of it is also mypy-clean.

**Also verified:** `probatio.to_field_list` serializes every form schema in `config_flow.py` (user, yaml, options, reconfigure). The frontend endpoint is therefore not broken, and no production serialization change is needed.

## Gates: run after EVERY task, from the repo root, strict

- G1: `uv run pytest tests/ -q -p no:cacheprovider` must give 0 failed.
- G2: `uv run ruff check custom_components tests`
- G3: `uv run ruff format --check custom_components tests`
- G4: `uv run mypy --strict custom_components/traefik_proxy` must give 0 errors.
- G5 (HA 2026.3.0 throwaway env, outside the repo): `{ V="${HA2603_VENV:-$HOME/.cache/traefik-proxy-integration/ha2603-venv}"; if [ ! -x "$V/bin/python" ]; then uv venv -q --python 3.14 "$V" && printf 'homeassistant==2026.3.0\n' > "$V/ha-override.txt" && uv pip install -q --python "$V/bin/python" pytest-homeassistant-custom-component==0.13.317 --overrides "$V/ha-override.txt"; fi; } && "$V/bin/python" -c 'import homeassistant.const as c; assert c.__version__ == "2026.3.0", c.__version__' && "$V/bin/python" -m pytest tests/ -q -p no:cacheprovider`. It must give 0 failed.
  - G5 is part of every task's automated verify, and of the final verification.
  - If the env cannot be built or HA 2026.3.0 cannot be imported, STOP and report it. Never skip G5 silently.
  - Record the pytest summary line of each G1 and G5 run for the SUMMARY.

Commit rules:
- One commit per task, English, conventional style.
- Stage only the listed files.
- Do NOT push. Work on `main`.
- Do not mention removed API names in new comments; some gates count them.
</context>

<tasks>

<task type="auto">
  <name>Task 0 (compat): green pytest + mypy on HA 2026.10.4 while staying compatible with HA 2026.3.0</name>
  <files>custom_components/traefik_proxy/config_flow.py, custom_components/traefik_proxy/__init__.py, custom_components/traefik_proxy/button.py, custom_components/traefik_proxy/binary_sensor.py, tests/test_config_flow.py</files>
  <precondition>The HEAD baseline matches the verified facts: 1 failed + 168 passed and 8 mypy errors in the lock env, and G5 reports 169 passed on HA 2026.3.0. If not, stop and report.</precondition>
  <read_first>custom_components/traefik_proxy/config_flow.py (lines 21-45), custom_components/traefik_proxy/__init__.py (lines 1-30), custom_components/traefik_proxy/button.py (lines 10-22), custom_components/traefik_proxy/binary_sensor.py (lines 1-25), tests/test_config_flow.py (lines 97-118)</read_first>
  <action>
Per the user's decision on N2: a separate compat commit, scoped to exactly the 1 test failure and the 8 mypy errors. The runtime must stay compatible with HA 2026.3.0. Approaches, one per issue:

1. **The 6 probatio arg-type errors** (`config_flow.py` lines 229, 278, 307, 365, 430 and `__init__.py:155`). Use a fallback import. In `config_flow.py` (line 28) and `__init__.py` (line 11), replace the single voluptuous import with a try/except block placed at the same spot:
   - try `import probatio as vol`
   - on `ImportError`, `import voluptuous as vol`, with the trailing comment `# type: ignore[no-redef]` on that line
   - add a short comment on the except line saying that HA releases before 2026.9 ship voluptuous only
   - Why this works:
     - HA 2026.9+ requires probatio, and HA core itself imports probatio. In 2026.10.4 `probatio.Schema` is the same class as the runtime voluptuous shim, so runtime behavior is unchanged.
     - HA 2026.3.0 has no probatio, so the fallback loads the real voluptuous 0.15.2.
     - mypy (lock env) types `vol` as probatio, which clears all 6 errors. The ignore is used, because mypy reports `no-redef` on the fallback.
   - The rest of both modules stays unchanged (`vol.Schema/Required/Optional/All/Range/Invalid` all exist in probatio).
2. **`button.py:15` ButtonDeviceClass.** Change the import to `ButtonEntity` only. Add a try/except block directly below it:
   - try `from homeassistant.components.button.const import ButtonDeviceClass` (the 2026.10+ location)
   - on `ImportError`, import `ButtonDeviceClass` from `homeassistant.components.button`, with the trailing comment `# type: ignore[attr-defined]`
   - In HA 2026.3.0, `button/const.py` exists but lacks the class, so the import raises ImportError and the fallback runs.
3. **`binary_sensor.py:9-12` BinarySensorDeviceClass.** Same pattern. Import `BinarySensorEntity` from the package. Then try `homeassistant.components.binary_sensor.const`; on ImportError, fall back to the package, with `# type: ignore[attr-defined]`. `binary_sensor/const.py` does not exist before 2026.10.0, which also raises ImportError.
4. **Test `test_user_schema_serializes_for_config_flow_endpoint`** (`tests/test_config_flow.py` lines 97-117). Match what HA itself uses to serialize config-flow forms (see the matrix above). Replace the voluptuous_serialize import with a try/except:
   - try `from probatio import to_field_list as serialize_schema` (the HA 2026.10 serializer)
   - on `ImportError`, `from voluptuous_serialize import convert as serialize_schema` (HA 2026.3)
   - call `serialize_schema(STEP_USER_DATA_SCHEMA, custom_serializer=cv.custom_serializer)`
   - keep the existing assertions unchanged
   - update the docstring to name both serializers
   - Production serialization is not touched. The endpoint is not broken: `probatio.to_field_list` handles all four form schemas.
5. Ruff accepted the try/except blocks in place; there are no E402 or I001 findings. If `ruff format` reflows anything, accept its output.
6. Do not change anything else: no comment rewording elsewhere, no other modules.
7. Run G1-G5. Expected: G1 169 passed; G4 "Success: no issues found"; G5 169 passed on 2026.3.0.
8. Commit the 5 files with the message `fix(compat): support HA 2026.10 (probatio, const moves) while keeping HA 2026.3`. The body names the version matrix sources.
  </action>
  <verify>
    <automated>grep -q '^    import probatio as vol$' custom_components/traefik_proxy/config_flow.py && grep -q '^    import probatio as vol$' custom_components/traefik_proxy/__init__.py && grep -q 'from homeassistant.components.button.const import ButtonDeviceClass' custom_components/traefik_proxy/button.py && grep -q 'from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass' custom_components/traefik_proxy/binary_sensor.py && grep -q 'from probatio import to_field_list' tests/test_config_flow.py && uv run pytest tests/ -q -p no:cacheprovider && uv run ruff check custom_components tests && uv run ruff format --check custom_components tests && uv run mypy --strict custom_components/traefik_proxy && { V="${HA2603_VENV:-$HOME/.cache/traefik-proxy-integration/ha2603-venv}"; if [ ! -x "$V/bin/python" ]; then uv venv -q --python 3.14 "$V" && printf 'homeassistant==2026.3.0\n' > "$V/ha-override.txt" && uv pip install -q --python "$V/bin/python" pytest-homeassistant-custom-component==0.13.317 --overrides "$V/ha-override.txt"; fi; } && "$V/bin/python" -c 'import homeassistant.const as c; assert c.__version__ == "2026.3.0", c.__version__' && "$V/bin/python" -m pytest tests/ -q -p no:cacheprovider</automated>
  </verify>
  <done>
- Lock env: pytest 169/169 and `mypy --strict` reports 0 errors.
- HA 2026.3.0: pytest 169/169.
- ruff is clean.
- Only the 5 files changed.
- One `fix(compat):` commit exists.
- At HEAD the grep and mypy gates fail, so they really measure this change.
  </done>
</task>

<task type="auto">
  <name>Task 1 (Fix P, revised): require Home Assistant 2026.3.0 / Python 3.14, move CI to 3.14, update stated minimums</name>
  <files>hacs.json, .github/workflows/validate.yml, CLAUDE.md, .planning/PROJECT.md</files>
  <read_first>hacs.json, .github/workflows/validate.yml, ruff.toml, pyproject.toml, CLAUDE.md (lines 15-175), .planning/PROJECT.md (lines 113-117)</read_first>
  <action>
Per the user's revision of Fix P, keep Python 3.14 as the runtime baseline and add NO Python 3.13 compatibility.

Do NOT touch these 3.14-only except clauses:
- `tls.py:200`
- `config_flow.py:166`
- `tests/conftest.py:166` and `:173`

Do NOT add a compileall step.

1. `hacs.json`: set the `homeassistant` value to `2026.3.0` (source: the PyPI requires_python facts above). Leave `name` and `hacs` unchanged.
2. `.github/workflows/validate.yml`:
   - Lint job, line 21: the `uv python install` argument becomes `3.14`.
   - Test job, line 39: the matrix `python-version` list becomes `["3.14"]`.
   - Nothing else.
3. Confirm, without editing:
   - `ruff.toml` line 1 is already `target-version = "py314"`.
   - `pyproject.toml` line 27 is already `python_version = "3.14"`.
   - `pyproject.toml` has no `[tool.ruff]` section, so nothing conflicts with `ruff.toml`.
   - If any of these differ, set them to these values.
4. `CLAUDE.md`: change ONLY these version facts. Keep all other wording.
   - Line 21: `Python 3.12+` becomes `Python 3.14+`, and `min version 2025.4.x` becomes `min version 2026.3.x`.
   - Line 43, Python row:
     - `>=3.12` becomes `>=3.14.2`.
     - `(HA 2025.4 ships 3.13)` becomes `(HA 2026.3 ships 3.14)`.
     - `HA 2025.4 bundles CPython 3.13` becomes `HA 2026.3 bundles CPython 3.14`.
   - Line 44: `>=2025.4.0` becomes `>=2026.3.0`.
   - Line 65: `"2025.4.0"` becomes `"2026.3.0"`.
   - Line 125: change only the Recommended cell, `2025.4.0` to `2026.3.0`.
   - Line 144: `HA 2025.4+ ships Python 3.13` becomes `HA 2026.3+ ships Python 3.14`.
   - Line 166:
     - `homeassistant>=2025.4.0` becomes `homeassistant>=2026.3.0`.
     - `Python 3.13+ (HA 2025.4 ships 3.13.3)` becomes `Python 3.14.2+ (HA 2026.3 ships 3.14)`.
   - Line 172: the `Python 3.13` cell becomes `Python 3.14`.
5. `.planning/PROJECT.md` line 115: make the same edit as CLAUDE.md line 21.
6. README.md has no minimum-version statement, and `info.md` does not exist. Make no change to either.
7. Leave the occurrences in Note N8 alone and list them in the SUMMARY.
8. Run G1-G5. Commit the 4 files with the message `build: require Home Assistant 2026.3.0 (Python 3.14 baseline)`. The body cites the PyPI source and says CI now runs on 3.14.
<!-- planner-discipline-allow: 3.13 -->
<!-- planner-discipline-allow: 2025.4.x -->
  </action>
  <verify>
    <automated>python3 -c 'import json; assert json.load(open("hacs.json"))["homeassistant"]=="2026.3.0"' && grep -q 'uv python install 3.14' .github/workflows/validate.yml && grep -q 'python-version: \["3.14"\]' .github/workflows/validate.yml && ! grep -nE '3\.13' .github/workflows/validate.yml && uv run python -c 'import yaml; yaml.safe_load(open(".github/workflows/validate.yml"))' && ! grep -n '2025\.4\.x' CLAUDE.md .planning/PROJECT.md && grep -q 'min version 2026.3.x' CLAUDE.md && grep -q 'min version 2026.3.x' .planning/PROJECT.md && ns=$(git diff --numstat 8849929 -- CLAUDE.md .planning/PROJECT.md) && echo "$ns" | grep -qx $'8\t8\tCLAUDE.md' && echo "$ns" | grep -qx $'1\t1\t.planning/PROJECT.md' && grep -q '^target-version = "py314"' ruff.toml && grep -q '^python_version = "3.14"' pyproject.toml && ! grep -q '^\[tool.ruff' pyproject.toml && grep -q 'except ValueError, TypeError, OSError:' custom_components/traefik_proxy/tls.py && uv run pytest tests/ -q -p no:cacheprovider && uv run ruff check custom_components tests && uv run ruff format --check custom_components tests && uv run mypy --strict custom_components/traefik_proxy && { V="${HA2603_VENV:-$HOME/.cache/traefik-proxy-integration/ha2603-venv}"; if [ ! -x "$V/bin/python" ]; then uv venv -q --python 3.14 "$V" && printf 'homeassistant==2026.3.0\n' > "$V/ha-override.txt" && uv pip install -q --python "$V/bin/python" pytest-homeassistant-custom-component==0.13.317 --overrides "$V/ha-override.txt"; fi; } && "$V/bin/python" -c 'import homeassistant.const as c; assert c.__version__ == "2026.3.0", c.__version__' && "$V/bin/python" -m pytest tests/ -q -p no:cacheprovider</automated>
  </verify>
  <done>
- hacs.json says 2026.3.0.
- CI installs 3.14 in lint and test.
- CLAUDE.md changes 8 lines and PROJECT.md 1 line, version facts only.
- The except clauses are unchanged.
- G1-G5 pass.
- One `build:` commit exists.
- The hacs.json, 3.13 and 2025.4.x gates fail at HEAD, so they really measure this change.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2 (Fix 1): single effective verify_ssl in every path (setup, options, reconfigure, reauth, running client)</name>
  <files>custom_components/traefik_proxy/coordinator.py, custom_components/traefik_proxy/config_flow.py, custom_components/traefik_proxy/__init__.py, tests/test_verify_ssl.py</files>
  <read_first>custom_components/traefik_proxy/coordinator.py, custom_components/traefik_proxy/config_flow.py (lines 141-235, 322-440), custom_components/traefik_proxy/__init__.py (lines 160-200), tests/test_coordinator.py (entry and endpoint-stub patterns)</read_first>
  <behavior>
    - (unit) effective_verify_ssl, parametrized:
      - data True, options empty: True
      - data False, options empty: False
      - data missing, options empty: True
      - data True, options False: False
      - data False, options True: True
    - (a) User flow with verify_ssl=False:
      - The probe client gets verify_ssl=False. Check this by patching `custom_components.traefik_proxy.config_flow.TraefikProxyApiClient` with `wraps=` the real class and asserting `call_args.kwargs["verify_ssl"] is False`.
      - The entry reaches LOADED, and `entry.runtime_data.client._verify_ssl is False`.
    - (b) Options False, then reconfigure True:
      - Start from a loaded entry with data verify_ssl=True and options {verify_ssl: False}. The runtime client is False.
      - The reconfigure form default is False: `result["data_schema"]({})[CONF_VERIFY_SSL] is False`.
      - Submit url=NEW_URL, api_key="k" and verify_ssl=True. The result is abort `reconfigure_successful`.
      - After `async_block_till_done`: data and options verify_ssl are both True, and the runtime client is True.
    - (c) An entry with data verify_ssl=False and empty options opens the options flow: `result["data_schema"]({})[CONF_VERIFY_SSL] is False`.
    - (d) Start from a loaded entry with data verify_ssl=True. Submit the options flow with scan_interval 30, verify_ssl False and tls_warn_days 14. The entry stays LOADED, and `entry.runtime_data.client._verify_ssl is False` without a reload.
    - (e) Use an entry with data True and options {verify_ssl: False}, started with `entry.start_reauth_flow(hass)`. Submit api_key "new". The probe client (wraps-patch) gets verify_ssl=False.
  </behavior>
  <action>
Per brief Fix 1: one effective value, the last one the user set, in every path. Precedence is options, then data, then DEFAULT_VERIFY_SSL. This holds because reconfigure, the only path that writes `data[verify_ssl]` after setup, now also writes `options[verify_ssl]`.

1. In `coordinator.py`, add two module-level functions next to the `TraefikProxyConfigEntry` alias, each with a short docstring.
   - `effective_verify_ssl(entry: ConfigEntry[Any]) -> bool` implements that precedence.
   - `build_api_client(hass: HomeAssistant, entry: ConfigEntry[Any]) -> TraefikProxyApiClient` builds the client from:
     - `aiohttp_client.async_get_clientsession(hass)`
     - `entry.data[CONF_URL]`
     - `entry.data[CONF_API_KEY]`
     - `verify_ssl=effective_verify_ssl(entry)`
   - In `TraefikProxyCoordinator.__init__`, replace the inline client construction at lines 89-94 (which reads options only, at line 93) with `self.client = build_api_client(hass, entry)`.
2. In `__init__.py` `_async_options_updated`, right after the scan-interval update, assign `coordinator.client = build_api_client(hass, entry)`. This way an options-flow verify_ssl change reaches the running client immediately.
   - Rebuilding is cheap: it uses the shared session and makes no network call.
   - Every caller reads `coordinator.client` at call time.
   - Update the listener docstring and import `build_api_client` from `.coordinator`.
   - The user decided to keep this step (N5).
3. In `config_flow.py`, import `effective_verify_ssl` from `.coordinator`. That import adds no cycle.
   - Options defaults, line 197: the CONF_VERIFY_SSL default becomes `effective_verify_ssl(self.config_entry)`.
   - Reauth probe, line 338: CONF_VERIFY_SSL becomes `effective_verify_ssl(entry)`.
   - Reconfigure defaults, line 415: the CONF_VERIFY_SSL entry becomes `effective_verify_ssl(entry)`.
   - Reconfigure submit, lines 401-408:
     - Store `verify_ssl = user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)` in a local.
     - Use the local in `data_updates`.
     - Pass `options={**entry.options, CONF_VERIFY_SSL: verify_ssl}` to `async_update_reload_and_abort`. `options=` exists in HA 2026.3.0 and 2026.10.4.
     - Keep the CONF_API_KEY line and the unique-id lines as they are; Task 4 changes both.
   - Fix the options-flow class docstring (lines 178-180), which wrongly claims HA reloads on change. Also fix the reconfigure and module docstrings that say verify_ssl is pre-filled from `entry.data`.
   - The line numbers above refer to HEAD. Task 0 shifted the file by about 3 lines. Locate the code by content.
4. Write `tests/test_verify_ssl.py` following `tests/test_coordinator.py`:
   - MockConfigEntry with unique_id `traefik.example.com`.
   - A local `_stub_all_endpoints(aioclient_mock, base_url)` for the six GET endpoints.
   - MOCK_URL `https://traefik.example.com:8080` and NEW_URL `https://traefik-new.example.com:8080`.
   - Test (b) MUST reconfigure to NEW_URL. This task runs BEFORE Task 4, and until then a same-host reconfigure aborts with `already_configured` (the N3 bug). Task 4 adds the same-host variant.
   - Always submit an explicit non-empty `api_key`.
   - Read form defaults by calling `result["data_schema"]({})`.
   - Use only APIs from the verified list. This file must also pass G5 on HA 2026.3.0.
5. Write the tests first (RED), then implement (GREEN).
6. Run G1-G5. Commit the 4 files with the message `fix(config): resolve verify_ssl from one effective value in every path`.
  </action>
  <verify>
    <automated>uv run pytest tests/test_verify_ssl.py -q -p no:cacheprovider && grep -q 'effective_verify_ssl(self.config_entry)' custom_components/traefik_proxy/config_flow.py && grep -q 'effective_verify_ssl(entry)' custom_components/traefik_proxy/config_flow.py && grep -q 'verify_ssl=effective_verify_ssl(entry)' custom_components/traefik_proxy/coordinator.py && grep -q 'options={\*\*entry.options' custom_components/traefik_proxy/config_flow.py && grep -q 'build_api_client(hass, entry)' custom_components/traefik_proxy/__init__.py && ! grep -nE '(entry\.data|current)\.get\(CONF_VERIFY_SSL' custom_components/traefik_proxy/config_flow.py && uv run pytest tests/ -q -p no:cacheprovider && uv run ruff check custom_components tests && uv run ruff format --check custom_components tests && uv run mypy --strict custom_components/traefik_proxy && { V="${HA2603_VENV:-$HOME/.cache/traefik-proxy-integration/ha2603-venv}"; if [ ! -x "$V/bin/python" ]; then uv venv -q --python 3.14 "$V" && printf 'homeassistant==2026.3.0\n' > "$V/ha-override.txt" && uv pip install -q --python "$V/bin/python" pytest-homeassistant-custom-component==0.13.317 --overrides "$V/ha-override.txt"; fi; } && "$V/bin/python" -c 'import homeassistant.const as c; assert c.__version__ == "2026.3.0", c.__version__' && "$V/bin/python" -m pytest tests/ -q -p no:cacheprovider</automated>
  </verify>
  <done>
- Tests (unit and a-e) pass on both HA versions.
- Every verify_ssl read goes through `effective_verify_ssl`.
- Reconfigure syncs options.
- The listener rebuilds the client.
- G1-G5 pass.
- One `fix(config):` commit exists.
- The negative grep finds 3 hits at HEAD, so it really measures this change.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3 (Fix 2): register reload_routers as an admin-only service; Reload button keeps working</name>
  <files>custom_components/traefik_proxy/__init__.py, custom_components/traefik_proxy/button.py, tests/test_init.py</files>
  <read_first>custom_components/traefik_proxy/__init__.py (async_setup), custom_components/traefik_proxy/button.py (async_press), tests/test_init.py</read_first>
  <behavior>
    - Non-admin:
      - After `async_setup(hass, {})` and loading the entry, `hass.services.async_call(DOMAIN, "reload_routers", {}, blocking=True, context=Context(user_id=hass_read_only_user.id))` raises `homeassistant.exceptions.Unauthorized`.
      - The `client.reload_routers` spy has 0 calls.
    - Admin:
      - The same call with `Context(user_id=hass_admin_user.id)` succeeds, and the spy is awaited once.
      - Stub `coordinator.async_request_refresh` with an AsyncMock whose side_effect sets `coordinator.data` to a copy with an extra router in `http_routers`. The handler then exits verified on attempt 1, not after the 5s budget.
    - The existing `test_reload_button_async_press_calls_service` stays unchanged and green. That proves the button, which has no user context, still passes the admin gate.
  </behavior>
  <action>
Per brief Fix 2:

1. In `__init__.py` `async_setup`, replace the service-registry registration call (brief anchor `__init__.py:151`) with `async_register_admin_service(hass, DOMAIN, "reload_routers", _async_handle_reload_routers, schema=RELOAD_ROUTERS_SCHEMA)`.
   - Import it from `homeassistant.helpers.service`. It exists in 2026.3.0 and 2026.10.4.
   - Keep the same schema object.
   - Update the `async_setup` docstring: the service is admin-only.
   - Planning-time prototype on top of Task 0: mypy is clean.
2. In `button.py`, add one docstring sentence to `async_press`: the button calls the service without a user context, so it is not subject to the admin check. This is intended per the brief. Do not change behavior.
3. In `tests/test_init.py`, add the two tests from the behavior block. Use:
   - the phcc fixtures `hass_read_only_user` and `hass_admin_user`
   - `Context` from `homeassistant.core`
   - `Unauthorized` from `homeassistant.exceptions`
   - the module's `_make_entry` and `_stub_all_endpoints` helpers
   - the async_setup-then-entry-setup pattern from `test_reload_button_async_press_calls_service`
   - Update the module docstring's coverage list.
4. Write the tests first (RED), then implement (GREEN).
5. Run G1-G5. Commit the 3 files with the message `fix(services): restrict reload_routers service to admin users`.
  </action>
  <verify>
    <automated>uv run pytest tests/test_init.py -q -p no:cacheprovider && grep -q 'async_register_admin_service(' custom_components/traefik_proxy/__init__.py && test "$(grep -c 'hass.services.async_register(' custom_components/traefik_proxy/__init__.py)" -eq 0 && uv run pytest tests/ -q -p no:cacheprovider && uv run ruff check custom_components tests && uv run ruff format --check custom_components tests && uv run mypy --strict custom_components/traefik_proxy && { V="${HA2603_VENV:-$HOME/.cache/traefik-proxy-integration/ha2603-venv}"; if [ ! -x "$V/bin/python" ]; then uv venv -q --python 3.14 "$V" && printf 'homeassistant==2026.3.0\n' > "$V/ha-override.txt" && uv pip install -q --python "$V/bin/python" pytest-homeassistant-custom-component==0.13.317 --overrides "$V/ha-override.txt"; fi; } && "$V/bin/python" -c 'import homeassistant.const as c; assert c.__version__ == "2026.3.0", c.__version__' && "$V/bin/python" -m pytest tests/ -q -p no:cacheprovider</automated>
  </verify>
  <done>
- A non-admin call raises Unauthorized, and an admin call works.
- The button test passes.
- G1-G5 pass.
- One `fix(services):` commit exists.
- The registration gate counts 1 at HEAD, so it really measures this change.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 4 (Fix 5 + N3): no token prefill in reconfigure, empty keeps it; same-host reconfigure allowed, only another entry's host aborts</name>
  <files>custom_components/traefik_proxy/config_flow.py, custom_components/traefik_proxy/strings.json, custom_components/traefik_proxy/translations/en.json, tests/test_reconfigure.py</files>
  <read_first>custom_components/traefik_proxy/config_flow.py (async_step_reconfigure as left by Task 2), custom_components/traefik_proxy/strings.json, custom_components/traefik_proxy/translations/en.json, tests/test_verify_ssl.py (helpers)</read_first>
  <behavior>
    Use an entry A with url MOCK_URL, api_key `test-secret` and unique_id `traefik.example.com`. Stub the endpoints for every URL used.

    - Form:
      - `entry.start_reconfigure_flow(hass)` returns a FORM with step_id `reconfigure`.
      - `validated = result["data_schema"]({})` has `validated[CONF_URL] == MOCK_URL` and `CONF_API_KEY not in validated`.
      - For every marker in `result["data_schema"].schema`, `"test-secret"` does not appear in `repr(getattr(marker, "description", None))`.
    - Same host, empty token. Parametrize over api_key `""` and over omitting the key.
      - Submit url MOCK_URL and verify_ssl True. The result is abort `reconfigure_successful`, and `entry.data[CONF_API_KEY] == "test-secret"`.
      - The first `/api/overview` request in `aioclient_mock.mock_calls` (tuple index 3 is the headers) carries `Authorization: Bearer test-secret`.
    - Same host, new token: submit `new-token`. Then `entry.data[CONF_API_KEY] == "new-token"`, and the probe header is `Bearer new-token`.
    - Same host, verify_ssl flip (the natural variant of Fix 1 (b)):
      - Start from a loaded entry with options {verify_ssl: False}.
      - A same-host reconfigure with verify_ssl True gives `reconfigure_successful`.
      - The runtime client and entry.options verify_ssl are then True.
    - Conflict: a second entry B (url `https://other.example.com:8080`, unique_id `other.example.com`) is added.
      - Reconfiguring A to B's URL aborts with reason `already_configured`.
      - A's data is unchanged.
    - Host change to an unused host (NEW_URL) still succeeds with `reconfigure_successful`, and `entry.data[CONF_URL] == NEW_URL`. This keeps the current behavior.
  </behavior>
  <action>
Per brief Fix 5 and the user's decision on N3:

1. Token handling in `config_flow.py` `async_step_reconfigure`:
   - Remove CONF_API_KEY from the defaults dict (brief anchor line 414).
   - Declare the CONF_API_KEY field (anchor line 422) as `vol.Optional(CONF_API_KEY)` with the same PASSWORD TextSelector and NO `default=`. Add no suggested_value.
   - On submit, compute `api_key = user_input.get(CONF_API_KEY) or entry.data.get(CONF_API_KEY, "")`.
   - Pass `_validate_input` a `probe_data` dict built from:
     - the submitted URL
     - `api_key`
     - the `verify_ssl` local from Task 2
   - Do not pass it the raw `user_input`.
   - Use `api_key` for CONF_API_KEY in `data_updates`.
2. Unique-id handling (N3, user decision): the step may abort only when ANOTHER entry already owns the new host. A same host is allowed, and a host change to an unused host stays allowed. That rules out `_abort_if_unique_id_mismatch`, which would block host changes.
   - Replace the flow-level `async_set_unique_id(host)` plus the abort-if-configured call in this step with a manual check.
   - Compute `host = urlparse(user_input[CONF_URL]).hostname or user_input[CONF_URL]`.
   - If any entry in `self._async_current_entries(include_ignore=False)` has `entry_id != entry.entry_id` and `unique_id == host`, return `self.async_abort(reason="already_configured")`. `_async_current_entries` exists in 2026.3.0 and 2026.10.4, and the `already_configured` key already exists in strings.json.
   - Run this check BEFORE the probe, so a conflicting host is not probed.
   - Replace the comment at old lines 397-399 with one that describes the other-entry rule.
   - Leave `async_step_user` and `async_step_yaml` unchanged; they keep their abort-if-configured calls.
3. Update the reconfigure and module docstrings: no token prefill, empty keeps the token, and only another entry's host aborts.
4. In both `strings.json` and `translations/en.json`, change `config.step.reconfigure`:
   - Set the `data.api_key` label to `Bearer token`. The old label described empty as "no api auth", which is now wrong.
   - Add `"data_description": {"api_key": "Leave empty to keep the current token."}`.
   - Keep each file's escaping style. Change no other keys.
5. Write `tests/test_reconfigure.py` with the behaviors above, reusing the stub-helper pattern from `tests/test_verify_ssl.py`. These tests must also pass G5 on HA 2026.3.0.
6. Write the tests first (RED), then implement (GREEN).
7. Run G1-G5 and `uv run python scripts/hassfest_checks.py strings-shape`.
8. Commit the 4 files with the message `fix(config_flow): no token prefill in reconfigure; allow same-host reconfigure`. The body mentions both brief Fix 5 and the same-host bug.
  </action>
  <verify>
    <automated>uv run pytest tests/test_reconfigure.py tests/test_verify_ssl.py -q -p no:cacheprovider && uv run python scripts/hassfest_checks.py strings-shape && ! grep -n 'defaults\[CONF_API_KEY\]' custom_components/traefik_proxy/config_flow.py && grep -q '_abort_if_unique_id_configured()' custom_components/traefik_proxy/config_flow.py && ! awk '/async def async_step_reconfigure/{f=1} f && /_abort_if_unique_id_configured\(\)/{found=1} END{exit !found}' custom_components/traefik_proxy/config_flow.py && grep -q '_async_current_entries(include_ignore=False)' custom_components/traefik_proxy/config_flow.py && python3 -c 'import json,sys; fs=["custom_components/traefik_proxy/strings.json","custom_components/traefik_proxy/translations/en.json"]; sys.exit(any(json.load(open(f))["config"]["step"]["reconfigure"].get("data_description",{}).get("api_key")!="Leave empty to keep the current token." for f in fs))' && uv run pytest tests/ -q -p no:cacheprovider && uv run ruff check custom_components tests && uv run ruff format --check custom_components tests && uv run mypy --strict custom_components/traefik_proxy && { V="${HA2603_VENV:-$HOME/.cache/traefik-proxy-integration/ha2603-venv}"; if [ ! -x "$V/bin/python" ]; then uv venv -q --python 3.14 "$V" && printf 'homeassistant==2026.3.0\n' > "$V/ha-override.txt" && uv pip install -q --python "$V/bin/python" pytest-homeassistant-custom-component==0.13.317 --overrides "$V/ha-override.txt"; fi; } && "$V/bin/python" -c 'import homeassistant.const as c; assert c.__version__ == "2026.3.0", c.__version__' && "$V/bin/python" -m pytest tests/ -q -p no:cacheprovider</automated>
  </verify>
  <done>
- No token value is in the reconfigure form.
- An empty or omitted token keeps the stored one for the probe and storage, and a new token replaces it.
- A same-host reconfigure succeeds, another entry's host aborts, and a change to an unused host succeeds.
- Both translation files are updated.
- strings-shape passes and G1-G5 pass.
- One `fix(config_flow):` commit exists.
- At HEAD the gates find `defaults[CONF_API_KEY]` twice, and the awk gate finds the abort-if-configured call inside `async_step_reconfigure` (line 400), so they really measure this change. The user and yaml steps keep theirs.
  </done>
</task>

</tasks>

<notes>
## Decisions (user, relayed by the coordinator)

- **D-N2 (baseline).** A separate compat commit, Task 0, before Fix P, so every later commit runs with strict gates (pytest fully green, mypy 0 errors). The runtime stays compatible with HA 2026.3.0 through fallback imports, and the tests run on 2026.3.0 too (G5).
- **D-N3 (same-host reconfigure).** Fixed inside Fix 5 (Task 4, same commit): abort only when another entry owns the host. Fix 1 (Task 2) runs before this fix, so its test (b) keeps the host-change workaround. Task 4 adds the same-host variant.
- **D-N5 (options path).** Keep the client rebuild in `_async_options_updated` and test (d) in Fix 1.

## Remaining notes

- **N1.** Fix P was revised by the user: raise the HA minimum to 2026.3.0, drop the 3.13 compileall check, keep the except clauses unparenthesized.
- **N4 (pre-existing HA deprecation).** In HA 2026.10.4, `async_update_reload_and_abort` on an entry with an update listener logs `report_usage(..., breaks_in_ha_version="2026.12.0")`. HA 2026.3.0 does not have this check. The call is kept; the listener's client rebuild keeps the runtime correct even if HA stops reloading there. Follow-up: `async_update_and_abort` plus a listener-driven reload.
- **N6 (accepted per brief).** The Reload button dispatches without a user context and so bypasses the admin gate.
- **N7 (consequence of Fix 5).** Reconfigure can no longer clear a token, because empty means keep. The reauth flow still accepts an empty token.
- **N8 (version mentions left unchanged):**
  - CLAUDE.md:
    - Lines 45, 143 and 167: aiohttp versions.
    - Line 145: a Python deprecation fact.
    - Lines 149 and 171: format examples.
    - Line 159: "PEP-695 works on 3.13", which is still true.
    - Line 188: a source citation.
    - The Alternative and rationale cells of line 125.
  - `.planning/research/{STACK,SUMMARY,ARCHITECTURE}.md`: research. A future CLAUDE.md regeneration from STACK.md could bring back 2025.4.
  - `.planning/phases/**`: history.
  - `.planning/REQUIREMENTS.md:122` (DIST-02): a completed requirement.
  - `.planning/ROADMAP.md:214`: the Phase 4 criterion "pytest on Python 3.13"; flag it for Phase 4.
  - `.pre-commit-config.yaml:11` (`python3.13`): the hook interpreter, not a stated minimum. The file also has stale `custom_components/traefik` paths.
  - `.claude/skills/**`.
- **N9 (out of scope).** A reconfigure with a host change does not update the entry's unique_id. The flow never passes `unique_id=` to `async_update_reload_and_abort`, so a later user flow for the new host is not blocked. Also, strings.json has no `reconfigure_successful` abort text.
- **N10 (compat coverage).** Tested ends are HA 2026.3.0 (G5) and 2026.10.4 (lock env). HA 2026.9.x (probatio 0.11.4, enums still in `__init__`) is covered by the same fallbacks but not tested. The probatio-first import assumes probatio is not installed next to an HA older than 2026.9, which no HA release does.
</notes>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| HA to Traefik API (network) | The bearer token crosses this boundary. TLS verification decides whether a MITM can read it. |
| HA frontend to config flow | Form schemas, including defaults, are serialized to the browser. |
| HA user to service registry | Any authenticated user can call services unless they are admin-gated. |
| HACS to HA runtime | HACS installs only on HA versions that satisfy hacs.json. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-261113-01 | Information disclosure | client build, reconfigure/options paths | medium | mitigate | Task 2: `effective_verify_ssl` single source; reconfigure syncs options; the listener rebuilds the client. Tests unit, a-e. |
| T-261113-02 | Elevation of privilege | `traefik_proxy.reload_routers` | low | mitigate | Task 3: `async_register_admin_service`; non-admin test expects Unauthorized. |
| T-261113-03 | Information disclosure | reconfigure form schema default | low | mitigate | Task 4: no default or suggested_value on api_key; empty keeps the token server-side. Schema test. |
| T-261113-04 | Elevation of privilege | Reload button (no user context) | low | accept | Required by the brief. A reload is a non-destructive refresh (N6). |
| T-261113-05 | Denial of service | install on HA below 2026.3 (Python 3.13 SyntaxError) | medium | mitigate | Task 1: hacs.json 2026.3.0, from PyPI requires_python. |
| T-261113-06 | Tampering | reconfigure unique-id check | low | mitigate | Task 4: abort only for another entry's host. Conflict test plus same-host tests. |
| T-261113-07 | Tampering | fallback imports pick the wrong validation engine | low | accept | Probatio-first only when probatio is importable, which is the case from HA 2026.9 on. Verified identical classes in 2026.10.4; G5 covers 2026.3.0 (N10). |
| T-261113-SC | Tampering | npm/pip/cargo installs | high | accept | No new dependencies. G5 installs only the official phcc 0.13.317 and homeassistant 2026.3.0 from PyPI into a throwaway env outside the repo. |
</threat_model>

<verification>
After Task 4:
1. Run G1-G4 in the lock env and G5 against HA 2026.3.0 once more. Both pytest runs must give 0 failed.
2. `git log --oneline -5` shows, in order: fix(compat), build, fix(config), fix(services), fix(config_flow).
3. Nothing is pushed. `git status` is clean apart from planning artifacts.
4. The 3.14-only except clauses are unchanged.
5. The SUMMARY records:
   - The HA versions actually tested, with their pytest summary lines (lock env 2026.10.4, and 2026.3.0 via phcc 0.13.317 with an override).
   - The G5 venv path.
   - Any G5 setup failure, verbatim.
   - The N8 list.
6. The throwaway G5 venv may be removed afterwards. Say in the SUMMARY whether it was.
</verification>

<success_criteria>
- Task 0: lock env 169/169 and mypy 0 errors; HA 2026.3.0 169/169. Only the import and test-serializer compat changes.
- Fix P: hacs.json 2026.3.0; CI on 3.14; stated minimums updated; ruff and mypy targets confirmed.
- Fix 1: one effective verify_ssl value in setup, options, reconfigure, reauth and the running client.
- Fix 2: the service is admin-gated, and the button still works.
- Fix 5 + N3: no token prefill; empty keeps the token; same-host reconfigure works; a conflict with another entry aborts.
- 5 atomic commits, not pushed. Every commit passes G1-G5.
</success_criteria>

<output>
Create `.planning/quick/261113-viw-security-fixes-verify-ssl-single-source-/261113-viw-SUMMARY.md` when done
</output>
