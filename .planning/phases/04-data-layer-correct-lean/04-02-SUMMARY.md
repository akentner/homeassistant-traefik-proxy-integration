---
phase: 04-data-layer-correct-lean
plan: 02
subsystem: runtime-data
tags: [home-assistant, runtime-data, dataclass, pep-695, coordinator, config-entry]

requires: []
provides:
  - "custom_components/traefik_proxy/data.py: TraefikRuntimeData(client, coordinator, cert_coordinator) and type TraefikProxyConfigEntry = ConfigEntry[TraefikRuntimeData]"
  - "Single client owner: TraefikProxyCoordinator.client is a read-only property over config_entry.runtime_data.client"
  - "Setup order: client + both coordinators built, entry.runtime_data assigned, then the main and cert first refreshes"
  - "All platforms, the button, the reload handler and the cert coordinator read entry.runtime_data.coordinator / .cert_coordinator / .client directly (no getattr lookups)"
affects: [04-03, 04-04, 04-05, 04-06, phase-05-entity-lifecycle, phase-07-flows]

actuals:
  tokens: 15195
  tasks: 3
  commits: 3
plan_head_before: 0cf4f01085818b34df2d8ae7a4541416574740b9
plan_head_after: b5958e1a93354eb79aaa4c6388fb050fc4689935

tech-stack:
  added: []
  patterns:
    - "Typed runtime container on ConfigEntry (mutable @dataclass) with a PEP-695 config-entry alias in a leaf module (data.py imports local classes under TYPE_CHECKING only)"
    - "Coordinator reads its API client through runtime data (property), so the options listener swaps the client in one assignment"

key-files:
  created:
    - custom_components/traefik_proxy/data.py
  modified:
    - custom_components/traefik_proxy/coordinator.py
    - custom_components/traefik_proxy/__init__.py
    - custom_components/traefik_proxy/entity.py
    - custom_components/traefik_proxy/sensor.py
    - custom_components/traefik_proxy/binary_sensor.py
    - custom_components/traefik_proxy/button.py
    - custom_components/traefik_proxy/cert_coordinator.py
    - tests/test_coordinator.py
    - tests/test_cert_coordinator.py
    - tests/test_sensor_tls.py
    - tests/test_init.py
    - tests/test_verify_ssl.py
    - tests/test_sensor.py
    - tests/test_binary_sensor.py

key-decisions:
  - "04-02: TraefikRuntimeData owns the only API client; TraefikProxyCoordinator.client is a read-only property over runtime_data.client, so an options change replaces the client in one statement and the two can never drift"
  - "04-02: entry.runtime_data is assigned before both first refreshes (also when the main refresh then fails with ConfigEntryNotReady; the next retry reassigns it)"
  - "04-02: the cert coordinator always exists after setup, so the platforms' cert blocks run unconditionally (no None branch)"

patterns-established:
  - "Read runtime state only via entry.runtime_data.<client|coordinator|cert_coordinator>; import TraefikProxyConfigEntry from .data"
  - "Test entries built from MagicMock wire the data-bearing coordinator at entry.runtime_data.coordinator (MagicMock(coordinator=coord))"

requirements-completed: [DATA-05]

coverage:
  - id: D1
    description: "entry.runtime_data is a TraefikRuntimeData holding the TraefikProxyCoordinator and CertCoordinator created by setup"
    requirement: "DATA-05"
    verification:
      - kind: integration
        ref: "tests/test_coordinator.py#test_setup_creates_coordinator_in_runtime_data"
        status: pass
    human_judgment: false
  - id: D2
    description: "runtime_data is assigned before the cert coordinator's first refresh, which sees the main coordinator's data through it"
    requirement: "DATA-05"
    verification:
      - kind: integration
        ref: "tests/test_coordinator.py#test_runtime_data_set_before_cert_first_refresh"
        status: pass
    human_judgment: false
  - id: D3
    description: "The API client exists once: coordinator.client is runtime_data.client, also after an options verify_ssl change (same container, new client, verify_ssl False)"
    requirement: "DATA-05"
    verification:
      - kind: integration
        ref: "tests/test_coordinator.py#test_single_client_owner"
        status: pass
      - kind: integration
        ref: "tests/test_verify_ssl.py#test_options_change_reaches_running_client"
        status: pass
    human_judgment: false
  - id: D4
    description: "No getattr(..., None) lookup and no monkey-attached cert_coordinator remain; platforms read runtime_data.coordinator / .cert_coordinator"
    requirement: "DATA-05"
    verification:
      - kind: other
        ref: "grep -rnE 'getattr\\([^)]*None\\)' custom_components/traefik_proxy (no output)"
        status: pass
      - kind: unit
        ref: "tests/test_sensor_tls.py, tests/test_cert_coordinator.py, tests/test_binary_sensor_tls_expiring.py (51 passed)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Entity set, unique_ids, names and platforms unchanged; full gate green on dev venv and HA 2026.3.0 venv"
    verification:
      - kind: unit
        ref: "uv run pytest -q (250 passed)"
        status: pass
      - kind: unit
        ref: "~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts='' (250 passed, HA 2026.3.0)"
        status: pass
      - kind: other
        ref: "uv run ruff check custom_components tests && uv run ruff format --check custom_components tests && uv run mypy --strict custom_components/traefik_proxy"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-11-14
status: complete
---

# Phase 4 Plan 02: Typed runtime data Summary

**`entry.runtime_data` is now a typed `TraefikRuntimeData(client, coordinator, cert_coordinator)` assigned before any refresh. The coordinator reads the entry's single API client from it, and every consumer reads it directly (no `getattr` lookups, no monkey-attached cert coordinator).**

## Performance

- **Duration:** 8 min
- **Started:** 2026-11-14T00:22:55Z
- **Completed:** 2026-11-14T00:31:00Z
- **Tasks:** 3 (1 tracer + 2 auto)
- **Files modified:** 15 (1 created, 14 modified)

## Accomplishments

- New `data.py`: plain mutable `@dataclass TraefikRuntimeData` plus `type TraefikProxyConfigEntry = ConfigEntry[TraefikRuntimeData]`. Local classes are imported under `TYPE_CHECKING` only, so the module has no import cycle.
- `TraefikProxyCoordinator` no longer builds or stores a client. `client` is a read-only property returning `config_entry.runtime_data.client`. The old `ConfigEntry["TraefikProxyCoordinator"]` alias and the `cert_coordinator: CertCoordinator | None` attribute are gone. The payload is still the existing dict (04-04 swaps it).
- `async_setup_entry` builds the client and both coordinators, assigns `entry.runtime_data`, and only then runs the main first refresh and the guarded cert first refresh. The options listener updates `update_interval`, replaces the client with one `runtime.client = build_api_client(...)` and calls `runtime.cert_coordinator.async_set_threshold(...)` directly. The reload handler reads the client and coordinator from the runtime data.
- `entity.py`, `sensor.py`, `binary_sensor.py` and `button.py` take `entry.runtime_data.coordinator`. The cert blocks in sensor/binary_sensor read `entry.runtime_data.cert_coordinator` and always run. `CertCoordinator.config_entry` is typed with the alias, and host collection reads `runtime_data.coordinator.data`.
- New tests: a setup-order test (the cert first refresh sees `TraefikRuntimeData` and non-None main data) and single-client tests (identity after setup; after an options change the container is the same, the client is new, its `_verify_ssl` is False, and the coordinator uses that client).

## Task Commits

1. **Task 1: Tracer: setup builds TraefikRuntimeData before any refresh; entity reads coordinator through it** - `ea456b6` (feat)
2. **Task 2: Platforms, button and cert coordinator read runtime data directly** - `f1c4145` (refactor)
3. **Task 3: Remaining test wiring, single-client options test, full gate** - `b5958e1` (test)

**Plan metadata:** recorded in the docs commit that adds this SUMMARY.

## Files Created/Modified

- `custom_components/traefik_proxy/data.py`: runtime container + config-entry alias (new)
- `custom_components/traefik_proxy/coordinator.py`: client property, alias/cert attribute removed, docstrings updated
- `custom_components/traefik_proxy/__init__.py`: new setup order, single-place client swap, direct cert threshold call, reload handler on runtime data
- `custom_components/traefik_proxy/entity.py`: subscribes to `runtime_data.coordinator`
- `custom_components/traefik_proxy/sensor.py`, `binary_sensor.py`: coordinator/cert coordinator from runtime data; getattr + None guard removed, cert block dedented
- `custom_components/traefik_proxy/button.py`: coordinator from runtime data
- `custom_components/traefik_proxy/cert_coordinator.py`: alias typing, reads `runtime_data.coordinator.data`, docstrings updated
- `tests/test_coordinator.py`: runtime-data type assertions, setup-order and single-client tests
- `tests/test_cert_coordinator.py`, `tests/test_sensor_tls.py`, `tests/test_init.py`, `tests/test_verify_ssl.py`, `tests/test_sensor.py`, `tests/test_binary_sensor.py`: wiring moved to `runtime_data.coordinator` / `.client`

## Decisions Made

- The client has a single owner (runtime data) and the coordinator reads it through a property. This is the first of the two options D-12 allowed. It removes the risk that the options listener updates one reference and forgets the other.
- `runtime_data` is assigned before the main first refresh, as the plan requires. If that refresh raises `ConfigEntryNotReady`, the entry keeps a runtime container from the failed attempt; HA's retry calls `async_setup_entry` again and reassigns it. Coordinator constructors have no side effects (checked in HA's `DataUpdateCoordinator.__init__`), so building the cert coordinator earlier than before costs nothing.

## Worker Decisions

- Narrowed `CertCoordinator.__init__`'s `entry` parameter to `TraefikProxyConfigEntry` too, not only the `config_entry` class attribute. Reason: consistent typing, and the runtime `ConfigEntry` import becomes unnecessary. Alternative: keep `entry: ConfigEntry`.
- `entity.py` and `__init__.py` import the alias from `.data` at runtime (not under `TYPE_CHECKING`). Reason: `data.py` is a leaf module with no local runtime imports, so no cycle is possible. Alternative: `TYPE_CHECKING` imports everywhere (as in sensor/binary_sensor/button, which already used that pattern).
- In `tests/test_sensor_tls.py` I also replaced the second assertion `entity.coordinator.cert_coordinator is cert_coord` with `entity._coordinator is cert_coord`. Reason: the monkey-attached path no longer exists, and the entity keeps its cert coordinator in `_coordinator`. Alternative: drop the assertion.
- The setup-order test replaces `CertCoordinator._async_update_data` via `patch.object` with a recording coroutine and also asserts `LOADED`. Reason: it checks the real setup path end to end. Alternative: an `AsyncMock` side effect.
- `test_options_change_reaches_running_client` also asserts `runtime.client is not old_client`. Reason: this proves the listener actually replaced the client, rather than the old client happening to satisfy the check. Alternative: only the identity and verify_ssl assertions the plan listed.
- I removed planning references (Phase/PITFALLS/BLOCKER wording about the old sibling attach) only in the docstrings and comments I had to touch (coordinator, `__init__` setup docstring, cert_coordinator module docstring/comment, platform cert-block comments). Reason: those references were now wrong. Alternative: the full M22 sweep, which is Phase 8.
- The pre-existing `SyntaxWarning` in `tests/test_binary_sensor.py:35` (invalid `\w` escape in a docstring) is logged in `deferred-items.md`, not fixed. Reason: scope rule (not caused by this plan). Alternative: a one-character fix now.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Second assertion in test_sensor_tls also needed rewiring**
- **Found during:** Task 2
- **Issue:** The plan only named `entity.coordinator is entry.runtime_data`. The following `entity.coordinator.cert_coordinator is cert_coord` relied on the removed monkey-attach and would fail against a `MagicMock` runtime container.
- **Fix:** Assert `entity._coordinator is cert_coord` (the cert coordinator the entity was given).
- **Files modified:** tests/test_sensor_tls.py
- **Verification:** `uv run pytest tests/test_cert_coordinator.py tests/test_sensor_tls.py tests/test_binary_sensor_tls_expiring.py -q`: 51 passed
- **Committed in:** f1c4145

**2. [Rule 1 - Bug, test only] Reload-button test stubbed refresh on the wrong object**
- **Found during:** Task 3
- **Issue:** `test_init.py`'s button test set `async_request_refresh = AsyncMock` on `entry.runtime_data`. Once runtime data became the container, the stub no longer reached the coordinator, and `test_reload_service_allows_admin_user` failed because it wrote `coordinator.data` on the container.
- **Fix:** As the plan specified, use `runtime.coordinator` for coordinator/data access and `runtime.client` for the `reload_routers` stub. The button test's refresh stub now hits the real coordinator.
- **Files modified:** tests/test_init.py
- **Verification:** full suite 250 passed
- **Committed in:** b5958e1

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 test-only bug). `tests/test_binary_sensor_tls_expiring.py` passed unchanged, as the plan expected.
**Impact on plan:** None on production behaviour. No scope creep.

## Issues Encountered

- A single "1 warning" shows up on the first pytest run after `tests/test_binary_sensor.py` changes. It is a pre-existing Python 3.14 `SyntaxWarning` from a docstring escape and does not appear on later runs, because the cached bytecode is reused. It is logged in `deferred-items.md`.
- Pre-existing: `addopts = --cov=custom_components.traefik` points at the old package name, so coverage reports "no data". Not touched (out of scope).

## Verification Results

- `uv run pytest -q`: 250 passed (baseline before the plan: 248; +2 new tests)
- HA 2026.3.0 venv (`~/.cache/traefik-proxy-integration/ha2603-venv`, `-o addopts=""`): 250 passed
- `uv run ruff check custom_components tests`: all checks passed
- `uv run ruff format --check custom_components tests`: 28 files already formatted
- `uv run mypy --strict custom_components/traefik_proxy`: no issues in 12 source files
- `grep -rnE 'getattr\([^)]*None\)' custom_components/traefik_proxy`: no output
- `grep -rn 'from .coordinator import TraefikProxyConfigEntry' custom_components/traefik_proxy`: no output
- `grep -rn 'entry.runtime_data is coordinator' tests`: no output
- In `__init__.py`, `entry.runtime_data = TraefikRuntimeData(` is at line 233, before `coordinator.async_config_entry_first_refresh()` at line 239
- No Docker containers, networks or volumes were started by this plan

## Flagged assumption (from the plan, still open)

- Edge probe DATA-05 / "review manually" stays UNRESOLVED by rule. Covered here: setup order and client identity across options changes. A human should confirm that other runtime-data lifecycle edges (for example unload while a cert refresh is running) can wait for Phase 7, where `OptionsFlowWithReload` replaces the listener.

## User Setup Required

None. No external service configuration required.

## Next Phase Readiness

- 04-03 (models) and 04-04 (client + snapshot) can rely on `entry.runtime_data.coordinator` / `.client` / `.cert_coordinator` and on `TraefikProxyConfigEntry` from `.data`. `tests/conftest.py` was not touched.
- 04-04 needs to change `cert_coordinator._collect_hosts_from_main_coordinator` (`runtime_data.coordinator.data.get("http_routers")`) and the reload handler's `_current_router_names` when the payload becomes `TraefikSnapshot`.

---
*Phase: 04-data-layer-correct-lean*
*Completed: 2026-11-14*

## Self-Check: PASSED

- FOUND: custom_components/traefik_proxy/data.py
- FOUND commits: ea456b6, f1c4145, b5958e1 (ancestors of HEAD)
- All task acceptance criteria and plan-level verification commands re-run and passing (see Verification Results)
