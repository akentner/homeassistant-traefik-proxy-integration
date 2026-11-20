---
phase: 05-entity-model-lifecycle
plan: 06
subsystem: entities
tags: [home-assistant, button, services, read-only-api, translations, traefik]
status: complete

requires:
  - phase: 05-entity-model-lifecycle
    provides: "05-01 TraefikEntity base, identifiers-only device factory, _state_token write-on-change contract, conftest helpers (make_traefik_entry, setup_traefik_entry, entity_id_for, mock_tls_probe); 05-05 last other entity moved off the old bases"
provides:
  - "button.py: TraefikRefreshButton (translation_key refresh, unique_id {entry_id}_refresh, EntityCategory.DIAGNOSTIC, no device class, main device) refreshing its own entry's coordinator and cert_coordinator; PARALLEL_UPDATES = 1"
  - "translations: entity.button.refresh.name 'Refresh now' (strings.json identical)"
  - "removed: TraefikProxyApiClient.reload_routers + _REFRESH_PATH, reload_routers admin service + handler + schema, module-level async_setup, CONFIG_SCHEMA, services.yaml, TraefikProxyReloadButton"
affects: [05-07, phase-08-changelog]

actuals:
  tokens: 9800
  tasks: 1
  commits: 2
plan_head_before: 46a72d7574c8c14033d73700065df65a29d7d96a
plan_head_after: a4df3cfa695251467864418a70cc0ff049860e44

tech-stack:
  added: []
  patterns:
    - "Entry-scoped actions read self._entry.runtime_data; no domain service, no cross-entry lookup"
    - "The API client is GET-only; a test asserts every recorded aioclient_mock request is a GET"

key-files:
  created:
    - .planning/phases/05-entity-model-lifecycle/deferred-items.md
  modified:
    - custom_components/traefik_proxy/api.py
    - custom_components/traefik_proxy/__init__.py
    - custom_components/traefik_proxy/button.py
    - custom_components/traefik_proxy/const.py
    - custom_components/traefik_proxy/translations/en.json
    - custom_components/traefik_proxy/strings.json
    - tests/test_init.py
    - tests/test_api.py
  deleted:
    - custom_components/traefik_proxy/services.yaml

key-decisions:
  - "Button PARALLEL_UPDATES = 1: serializes presses on top of the request-refresh debouncers - plan decision"
  - "Refresh button keeps the inherited CoordinatorEntity availability (unavailable while the main coordinator's last update failed) - worker decision"

requirements-completed: []

coverage:
  - id: D1
    description: "No service for the domain after setup; the package module has neither async_setup nor CONFIG_SCHEMA (D-16, IN-02)"
    requirement: ENT-07
    verification: "tests/test_init.py::test_no_service_registered, ::test_package_module_has_no_setup_or_config_schema"
  - id: D2
    description: "Refresh button registry entry: unique_id {entry_id}_refresh, translation_key refresh, diagnostic, no device class, on the main device, only button of the entry, name 'Refresh now'"
    requirement: ENT-08
    verification: "tests/test_init.py::test_refresh_button_registry_entry"
  - id: D3
    description: "Two loaded entries: pressing A's button awaits A's coordinator and cert coordinator async_request_refresh once each and B's not at all (T-05-09)"
    requirement: ENT-07
    verification: "tests/test_init.py::test_press_refreshes_only_own_entry"
  - id: D4
    description: "Setup, refreshes and a real press send only GET requests; the press reaches Traefik (T-05-11, P-ENT-07)"
    requirement: ENT-07
    verification: "tests/test_init.py::test_only_get_requests_reach_traefik"
  - id: D5
    description: "button.py declares PARALLEL_UPDATES = 1; no explicit entity_id left in the integration"
    requirement: ENT-08
    verification: "tests/test_init.py::test_button_module_serializes_presses; grep gate '! grep -rn \"self\\.entity_id = \" custom_components/traefik_proxy'"

duration: 13min
completed: 2026-11-14
---

# Phase 5 Plan 06: Refresh now button replaces the reload feature Summary

**The never-working reload feature is gone: no `reload_routers` service, no `services.yaml`, no `CONFIG_SCHEMA`/`async_setup`, no refresh POST in the client. A diagnostic "Refresh now" button on the main device requests a refresh of exactly its own entry's main and cert coordinators. The integration now registers no service and sends only GET requests to Traefik.**

## Performance

- **Duration:** about 13 min
- **Started:** 2026-11-14T21:32Z (approx.)
- **Completed:** 2026-11-14T21:45:29Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 9 (8 modified, 1 deleted) plus the new phase `deferred-items.md`

## Accomplishments

- `api.py`: `reload_routers` and `_REFRESH_PATH` are deleted, so the client has no `.post(` left. Traefik has no refresh endpoint (A-04).
- `__init__.py`: `CONFIG_SCHEMA`, `RELOAD_ROUTERS_SCHEMA`, `_async_handle_reload_routers` and the module-level `async_setup` are deleted. So are the imports only they used: `asyncio`, `time`, `typing.Any`, the probatio/voluptuous shim, `ConfigEntryState`, `ServiceCall`, `HomeAssistantError`, `cv`, `async_register_admin_service` and `DOMAIN`. The module docstring now names setup, unload and removal. hassfest needs no config schema without `async_setup`.
- `services.yaml` is removed with `git rm`. The translations never had a `services` section.
- `button.py` is rewritten (D-17). `TraefikRefreshButton(TraefikEntity, ButtonEntity)` has `_attr_translation_key = "refresh"`, `EntityCategory.DIAGNOSTIC`, unique_id `{entry_id}_refresh` and no device class, and it sits on the main device. `_state_token()` returns `None`. `async_press` awaits `runtime.coordinator.async_request_refresh()` and then `runtime.cert_coordinator.async_request_refresh()` on `self._entry.runtime_data`. There is no hass constructor argument, no service call, no admin check (S-08 moot) and no `ButtonDeviceClass` shim. `PARALLEL_UPDATES = 1`.
- `entity.button.refresh.name` "Refresh now" is in en.json, and strings.json is byte-identical (`cmp` passes).
- **IN-02 is closed.** The verification loop that the debouncer defeated is gone together with the service.
- With the reload button gone, `self.entity_id =` no longer appears in the integration (ENT-08 button part). The button was the last entity on the old per-category base. The old base classes stay without users until 05-07 deletes them.

## Task Commits

1. **Task 1 RED: failing tests for the refresh button and the removed reload service** - `5975e11` (test, module-level strict xfail)
2. **Task 1 GREEN: replace the reload feature with a per-entry Refresh now button** - `a4df3cf` (feat)

## Verification (end of plan)

- `uv run pytest -q`: 541 passed. The baseline was 542 passed + 6 xfailed = 548 after RED. Seven refresh cases were deleted by plan: four refresh tests (one of them with 3 status cases, so 6 cases) and the refresh case of the request-construction test. 548 - 7 = 541.
- HA 2026.3.0 venv (`~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`): 541 passed
- `uv run ruff check custom_components tests`: all checks passed. `ruff format --check`: 35 files already formatted
- `uv run mypy --strict custom_components/traefik_proxy`: no issues in 14 source files
- Acceptance greps, all 8 pass: `services.yaml` absent. Zero hits for `reload_routers` in custom_components/tests, for `CONFIG_SCHEMA|async def async_setup\(` in `__init__.py`, for `.post(` in api.py, for `ButtonDeviceClass` in button.py and for `self.entity_id = ` in the integration. `PARALLEL_UPDATES == 1`. `cmp strings.json en.json` reports identical files.
- During the test run the fresh-install entity_id is `button.traefik_traefik_example_com_refresh_now`.

## TDD Gate Compliance

- RED: `5975e11`. The evidence is a pytest `--junitxml` run with `--runxfail` on an export of the RED commit's tree, checked with `gsd_run check tdd-red-evidence`. Verdict: `RED_EVIDENCE_OK`, reason `target_test_failed`, with target `test_press_refreshes_only_own_entry` (6 tests, 6 failed, 0 passed).
- Semantic assessment: each test failed on its planned assertion.
  - No-service test: `traefik_proxy: {reload_routers}` was present.
  - Module test: `async_setup` existed.
  - PARALLEL_UPDATES test: `AttributeError`.
  - Registry, two-entry and GET-only tests: "no button entity with unique_id `…_refresh`".
- The RED commit marks the module `xfail(strict=True)`, so the commit stays green (542 passed, 6 xfailed). GREEN `a4df3cf` removes the marker.
- REFACTOR: none needed. The evidence record and XML were deleted after classification and not committed, following 05-01/05-05.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug, test-only] Deprecated device lookup in the RED registry test**
- **Found during:** Task 1 GREEN
- **Issue:** The RED test looked up the main device with `device_registry.async_get_device(identifiers=…)`. In the dev HA this raises a deprecation `RuntimeError`. At RED the test failed earlier, at the missing button, so the problem stayed hidden.
- **Fix:** Look the device up with `dr.async_entries_for_config_entry` and filter by identifier. This is the same pattern as `tests/test_cert_entity_state.py` and works on HA 2026.3 and on later releases.
- **Files modified:** tests/test_init.py
- **Commit:** a4df3cf

**2. [Rule 1 - Stale comment] `const.py` PLATFORMS comment**
- **Found during:** Task 1 GREEN (repo-wide grep for reload leftovers)
- **Issue:** The comment said "button (reload)".
- **Fix:** It now says "button (refresh)". This is a comment-only change in a file that is not in `files_modified`.
- **Commit:** a4df3cf

**3. [Process] RED evidence was classified after the GREEN commit**
- RED failed on the planned assertions (`--runxfail` run) before any implementation was written. The machine classification (`check tdd-red-evidence`) ran after `a4df3cf`, on a `git archive` export of `5975e11`. The verdict applies to the RED tree only.

Otherwise the plan was executed as written.

## Worker Decisions

- The refresh button keeps the inherited `CoordinatorEntity` availability, so it is unavailable while the main coordinator's last update failed. Reason: this is the HA convention for coordinator entities and matches the `TraefikEntity` base the plan names. Alternative: override `available` to always be True, so a press can retry while Traefik is down. HA's own scheduled retry covers that case today.
- The second entry in the two-entry test is set up inline (`stub_traefik(base_url=SECOND_URL)` + `async_setup`), not through a new `base_url` parameter on `setup_traefik_entry`. Reason: conftest is not in `files_modified`. Alternative: extend the helper.
- The GET-only test also asserts that the press added requests, which proves the press reached Traefik. Reason: without it, a press that does nothing would pass the GET-only check. Alternative: check only the methods.
- The registry test also asserts that the entry's only button is the refresh button and that its friendly name ends in "Refresh now". Reason: this proves the reload button is gone and the translation is wired. Alternative: check only the plan's fields.
- The request-construction test went from a one-case parametrize to a plain test after the refresh case was removed. Reason: a single-case parametrize is noise. Alternative: keep `@pytest.mark.parametrize` with one param.
- The test_api module docstring drops "and the router refresh POST". Reason: the docstring listed what the file covers. Alternative: leave it stale.
- RED marks the whole new test_init module `xfail(strict=True)` through `pytestmark`, not each test. Reason: every test in the replaced module was new and RED. Alternative: one marker per test (05-01..05-05 style).
- The README.md:14 "reload service" mention and the CLAUDE.md:99 stack row for `POST /api/http/routers/refresh` are logged in the new phase `deferred-items.md` and not edited. Reason: both are outside `files_modified` (docs belong to Phase 8, and CLAUDE.md is generated). Alternative: edit them now.

## User-visible changes (Phase 8 CHANGELOG)

- **Removed:** the "Reload" button (`button.traefik_reload`, unique_id `{entry_id}_diagnostics_reload`) and the `traefik_proxy.reload_routers` service. Traefik has no refresh endpoint, so the feature never worked. Automations that call the service will fail. The 05-07 repair notice announces this.
- **Added:** a "Refresh now" diagnostic button per Traefik entry, on the Traefik device. A press immediately fetches the Traefik data and re-probes the certificates of that entry only. HA's 10 s request-refresh cooldown applies.
- The integration now sends only GET requests to Traefik and registers no services.

## Known Stubs

None.

## Threat Flags

None. The plan's register covers the change: T-05-09 by the two-entry test, T-05-10 by PARALLEL_UPDATES = 1 and the debouncers, and T-05-11 by the GET-only test and the `.post(` grep gate.

## Issues Encountered

- None blocking. IN-02 is closed here.

## Next Phase Readiness

- 05-07 can delete `_TraefikProxyBaseEntity`, `TraefikProxyEntity`, `TraefikProxyCertEntity` and `_CATEGORY_TO_MODEL`, which no entity uses any more. It adds the German name and the icon for `entity.button.refresh` (de.json, icons.json), the repair notice for the removed reload button and service, and the registry migration of the old `{entry_id}_diagnostics_reload` entry.

## Self-Check: PASSED

- FOUND: button.py, api.py, __init__.py, tests/test_init.py, tests/test_api.py, deferred-items.md; services.yaml deleted
- FOUND commits: 5975e11, a4df3cf (ancestors of HEAD)
