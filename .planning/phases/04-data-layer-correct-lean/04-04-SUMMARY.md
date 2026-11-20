---
phase: 04-data-layer-correct-lean
plan: 04
subsystem: data-layer
tags: [traefik, coordinator, snapshot, pagination, always_update, home-assistant]

requires:
  - phase: 04-01
    provides: "Real v2.11/v3.7 captures incl. paginated pages and the X-Next-Page termination rule (last page sends a value not greater than the current page)"
  - phase: 04-02
    provides: "TraefikRuntimeData (single client owner) and TraefikProxyConfigEntry"
  - phase: 04-03
    provides: "models.py parsers and TraefikSnapshot.build aggregates"
provides:
  - "api.py: TraefikProxyPayloadError, DEFAULT_PAGE_SIZE=500, MAX_PAGES=100, page_size constructor keyword, _get_response/_get_paginated, async_get_version / async_get_entrypoints / async_get_state (paginated list endpoints)"
  - "coordinator.py: DataUpdateCoordinator[TraefikSnapshot] with always_update=False; _async_setup fetches version + entrypoints once"
  - "All consumers (binary_sensor, sensor, entity, cert_coordinator, reload handler) read the snapshot; no raw API dict read remains"
  - "tests/conftest.py: MOCK_URL, make_snapshot, snapshot_from_fixture, stub_traefik_paginated, mock_tls_probe"
  - "tests/test_api_pagination.py: 11 pagination / payload-shape edge tests"
affects: [04-05, 04-06, phase-05-entity-lifecycle, phase-06-certificates, phase-08-changelog]

actuals:
  tokens: 36900
  tasks: 3
  commits: 3
plan_head_before: 20a991b61efcc4a01595f00f7cc0d8f88996a358
plan_head_after: bba194871def00d929980dfeea158b8505fac22d

tech-stack:
  added: []
  patterns:
    - "Per-item entities store only their name (_item_name) plus the construction-time model and resolve the current model from coordinator.data on every read"
    - "Aggregate entities read precomputed StatusCounts / problem tuples from the snapshot (no per-read counting)"
    - "Client wraps parser ValueError/TypeError/KeyError into TraefikProxyPayloadError('<path>: unexpected payload shape')"
    - "Platform unit tests build coordinator.data with make_snapshot / snapshot_from_fixture through the real parsers"

key-files:
  created:
    - tests/test_api_pagination.py
  modified:
    - custom_components/traefik_proxy/api.py
    - custom_components/traefik_proxy/coordinator.py
    - custom_components/traefik_proxy/binary_sensor.py
    - custom_components/traefik_proxy/entity.py
    - custom_components/traefik_proxy/sensor.py
    - custom_components/traefik_proxy/cert_coordinator.py
    - custom_components/traefik_proxy/__init__.py
    - tests/conftest.py
    - tests/test_coordinator.py
    - tests/test_sensor.py
    - tests/test_binary_sensor.py
    - tests/test_cert_coordinator.py
    - tests/test_init.py

key-decisions:
  - "04-04: X-Next-Page loop continues only while the header parses to an int strictly greater than the current page; missing or non-integer header ends the loop; an announced page above MAX_PAGES raises TraefikProxyPayloadError"
  - "04-04: per-item entities fall back to their construction-time model when their name is missing from the current snapshot (stale cleanup removes them; full lifecycle is Phase 5)"
  - "04-04: cert host collection skips routers with Router.tls False; a TLS router with an empty tls object still contributes its Host() rule hosts (on real Traefik such routers carry tls.options and were included before as well)"

patterns-established:
  - "Snapshot consumers: coordinator.data.<kind>.get(self._item_name, <stored model>) for per-item entities, coordinator.data.<kind>_counts / <kind>_problems for aggregates"
  - "Coordinator-level HTTP tests: monkeypatch api.DEFAULT_PAGE_SIZE to the index per_page, stub_traefik_paginated, mock_tls_probe"

requirements-completed: [DATA-01, DATA-06, DATA-02]

coverage:
  - id: D1
    description: "Real v3.7 pages flow through models, the paginated client and the snapshot coordinator into the router binary_sensor with correct on/off states; version and entrypoints are requested once at setup and not on a normal cycle"
    requirement: DATA-06
    verification:
      - kind: integration
        ref: "tests/test_coordinator.py#test_real_fixture_snapshot_reaches_router_entity"
        status: pass
    human_judgment: false
  - id: D2
    description: "always_update=False: equal snapshots do not notify listeners, a changed snapshot does"
    requirement: DATA-06
    verification:
      - kind: integration
        ref: "tests/test_coordinator.py#test_equal_snapshots_do_not_notify_listeners"
        status: pass
    human_judgment: false
  - id: D3
    description: "Pagination follows X-Next-Page without truncation: capture pages, full-page adjacency, repeated names, failing page keeps the previous snapshot, MAX_PAGES cap, non-list page, path-only payload errors"
    requirement: DATA-02
    verification:
      - kind: unit
        ref: "tests/test_api_pagination.py (11 tests)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Sensors and binary sensors read the snapshot (D-18 attribute set, no backend URL, empty-Traefik case all zero / off); cert host collection and reload handler read snapshot routers"
    requirement: DATA-01
    verification:
      - kind: unit
        ref: "tests/test_sensor.py, tests/test_binary_sensor.py, tests/test_cert_coordinator.py, tests/test_init.py"
        status: pass
      - kind: other
        ref: "raw-dict gate grep and filter_internal_items gate grep over the consumer modules print nothing"
        status: pass
    human_judgment: false
  - id: D5
    description: "Full gate green on the dev venv and the HA 2026.3.0 venv"
    verification:
      - kind: unit
        ref: "uv run pytest -q (388 passed); ~/.cache/traefik-proxy-integration/ha2603-venv python -m pytest -q -o addopts='' tests (388 passed)"
        status: pass
      - kind: other
        ref: "uv run ruff check / ruff format --check custom_components tests; uv run mypy --strict custom_components/traefik_proxy (no issues, 13 files)"
        status: pass
    human_judgment: false

duration: 9min
completed: 2026-11-14
status: complete
---

# Phase 4 Plan 04: Snapshot coordinator and consumers Summary

**The coordinator now publishes one frozen `TraefikSnapshot` per cycle (`always_update=False`), built from the typed client's paginated reads with version and entrypoints fetched once at setup. Every entity, the cert host collection and the reload handler read that snapshot instead of raw API dicts.**

## Performance

- **Duration:** 9 min (start 2026-11-14T00:45:38Z, end 2026-11-14T00:54:31Z)
- **Tasks:** 3 of 3 (Task 1 tracer, Tasks 2-3 auto)
- **Files:** 14 (1 created, 13 modified)

## Accomplishments

- **Client (api.py, additive):** `TraefikProxyPayloadError`; `DEFAULT_PAGE_SIZE = 500`, `MAX_PAGES = 100`; constructor keyword `page_size` resolved from the module constant at construction; `_get_response` returns payload plus raw `X-Next-Page`, `_get` delegates; `_get_paginated` implements the captured termination rule; `async_get_version`, `async_get_entrypoints` and `async_get_state` (routers, services, middlewares requested one after another) parse at the boundary. Legacy methods, the `api_key` constructor and `reload_routers` are untouched for 04-05.
- **Coordinator:** `DataUpdateCoordinator[TraefikSnapshot]`, `always_update=False`, `_async_setup` loads `_version` / `_entrypoints`, `_async_update_data` builds `TraefikSnapshot.build(...)`. Auth errors map to `ConfigEntryAuthFailed`, other API errors to `UpdateFailed`. The `TraefikProxyData` TypedDict and its `type: ignore` are gone.
- **binary_sensor.py:** router entities from `coordinator.data.routers`, model resolved per read via `data.routers.get(self._item_name, <stored model>)`, `is_on = status is Status.enabled`. The three any-*-failing sensors read `router_problems` / `service_problems` / `middleware_problems`.
- **sensor.py / entity.py:** entrypoint and service sensors use the same lookup pattern; service attributes are `name, status, type, server_count, servers_up, service_name`; count sensors read `StatusCounts`, keep `filtered_count`, bucket counts, `status_breakdown`, `success_pct`, add `http_count = total` for routers/services. The four raw-dict helpers, the status bucket map and the internal-filter import are deleted. `_sw_version` reads `snapshot.version.version`.
- **cert_coordinator.py / __init__.py:** hosts from `Router.tls`, `tls_domains`, `rule` of `coordinator.data.routers`; reload handler compares `set(coordinator.data.routers)`.
- **Tests:** conftest helpers (`MOCK_URL`, `make_snapshot`, `snapshot_from_fixture`, `stub_traefik_paginated`, `mock_tls_probe`); platform tests rebuilt on parsed snapshots, including both real captures; new `tests/test_api_pagination.py`.

## User-visible changes (for the Phase 8 CHANGELOG)

- Service sensor: state is the Traefik service status (`enabled` / `warning` / `error` / `disabled`), no longer the non-existent `loadbalancer.status`. Attribute `servers` (backend URL list) removed; new attribute `servers_up`; `server_count` now counts the servers in Traefik's health status.
- Routers / Services count sensors: `tcp_count` and `udp_count` removed; `http_count` now equals the snapshot total instead of the `/api/overview` value.
- Entrypoint sensor: attribute `transport` now carries the protocol (`tcp` or `udp`, from the address suffix) instead of Traefik's nested transport object.
- Items Traefik reports as `disabled` with a non-empty `error[]` show status `error` (router `status` attribute, service state, `error_count` bucket).
- Any-router/service/middleware-failing aggregates no longer consider Traefik-internal (`@internal`) items.
- Any-service-failing now turns on for an `enabled` service with at least one server `DOWN`.
- Entities now follow their item's current status on every cycle (before, router/service/entrypoint entities kept the payload they were created with).

## Task Commits

1. **Task 1 (tracer): real v3.7 pages -> models -> client -> snapshot coordinator -> router binary_sensor** - `ed0200e` (feat)
2. **Task 2: entity base and sensor platform on the snapshot; platform tests on parsed snapshots** - `f4bf7d7` (feat)
3. **Task 3: cert host collection and reload handler on the snapshot; pagination edge tests; full gate** - `bba1948` (feat)

Tracer gate: auto mode (`workflow.auto_advance: true`), Task 1 `<verify>` (`uv run pytest tests/test_coordinator.py -q`, 10 passed) re-run green before expanding.

## Verification

- `uv run pytest -q`: 388 passed (368 before the plan)
- HA 2026.3.0 venv (`~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`): 388 passed
- `uv run ruff check custom_components tests`: all checks passed
- `uv run ruff format --check custom_components tests`: 31 files already formatted
- `uv run mypy --strict custom_components/traefik_proxy`: no issues in 13 source files
- Raw-dict gate (`.get("http_routers"|...)` over sensor/binary_sensor/entity/cert_coordinator/__init__): no output
- Internal-filter gate (`filter_internal_items` over sensor/binary_sensor/cert_coordinator): no output
- Acceptance greps: `always_update=False` 1 line, `async def _async_setup` 1 line, `X-Next-Page` 3 lines in api.py, `TraefikProxyData` no output, `def stub_traefik_paginated` / `def mock_tls_probe` 1 line each, helper-name grep over sensor.py + test_sensor.py no output, `"servers"|tcp_count|udp_count` in sensor.py no output, `servers_up` 2, `make_snapshot|snapshot_from_fixture` in test_sensor.py 28, `coordinator.data.routers` in cert_coordinator.py 1, `tests/test_api_pagination.py` 11 tests
- No Docker containers, networks or volumes were started.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Reload admin test wrote a dict into coordinator.data**
- **Found during:** Task 3
- **Issue:** The plan said "no other changes" to tests/test_init.py, but `test_reload_service_allows_admin_user` simulated a refresh by copying `coordinator.data` as a dict and appending to `http_routers`; that fails on a snapshot.
- **Fix:** The refresh stub now assigns `make_snapshot(routers=[{"name": "new@docker"}])`.
- **Files modified:** tests/test_init.py
- **Commit:** bba1948

**2. [Ordering] Task 1 / Task 2 acceptance greps that depend on later tasks**
- **Found during:** Tasks 1 and 2
- **Issue:** Task 1's `grep -rn 'TraefikProxyData' custom_components/traefik_proxy` still matched one docstring of the raw-dict helper in sensor.py that Task 2 deletes. Task 2's `mypy --strict` exits 0 criterion still failed on cert_coordinator.py / __init__.py, which Task 3 changes.
- **Fix:** None needed beyond the planned later tasks; both criteria pass after Task 2 (grep) and Task 3 (mypy). Not forced earlier, to keep each commit inside its task's file list.
- **Verification:** Re-run after Task 3: grep no output, mypy no issues.

**3. [Rule 2 - Docs] Stale comments and docstrings next to touched code**
- **Found during:** Tasks 2 and 3
- **Issue:** Comments and docstrings around the rewritten code still described `http_routers` dicts, `filter_internal_items`, `fetch_all` or planning IDs.
- **Fix:** Rewrote the ones directly attached to changed code (sensor module docstring and stale-cleanup comment, binary_sensor aggregate docstrings, cert_coordinator module/class/method docstrings, reload handler docstring, legacy stub docstrings in test_coordinator/test_init). The broader sweep stays Phase 8.
- **Commits:** f4bf7d7, bba1948

**Total deviations:** 3 (1 blocking test fix, 1 ordering note, 1 docs). **Impact:** none on scope; no production behaviour beyond the plan.

## Worker Decisions

- `_get_paginated` treats a missing or non-integer `X-Next-Page` as "last page" (not as an error). Reason: the capture shows the header on every page, and a missing header can only mean no further page is announced. Alternative: raise TraefikProxyPayloadError on a non-integer header.
- `_get_paginated` jumps to the announced page number (not `page + 1`). Reason: follows the header literally; with real Traefik both are the same. Alternative: always `page + 1` and use the header only as a stop signal.
- MAX_PAGES check is `announced > MAX_PAGES` before requesting, so exactly MAX_PAGES requests happen before the error. Reason: matches the plan's "would request page MAX_PAGES + 1" wording and the (e) test of exactly 3 requests. Alternative: count requests.
- `async_get_state` wraps parser errors and JSON `ValueError`s of the list endpoints into TraefikProxyPayloadError naming the path being processed; `async_get_version` / `async_get_entrypoints` wrap parser errors only. Reason: minimal change; invalid-JSON handling for every path is the 04-05 taxonomy rewrite. Alternative: add the JSON wrap to `_get_response` now.
- Debug log line is `path=%s page=%s status=%s` (page `None` for non-paginated requests). Reason: one log format for both request kinds. Alternative: separate log calls.
- `_async_setup` fetches version and entrypoints sequentially, not with `asyncio.gather`. Reason: one-time setup cost, simpler error mapping, and 04-06 restructures the restart re-check. Alternative: gather both.
- Per-item entities fall back to the construction-time model when the item is missing from the snapshot (plan wording), and the router `is_on` returns a plain `bool`. Reason: a snapshot-built entity always has a model; `None` (unknown) was only reachable with raw dicts. Alternative: return `None` / unavailable when the item is missing (Phase 5 "missing" state).
- Aggregate count sensor subclasses implement a `_counts()` method; the base raises `NotImplementedError`. Reason: typed selector per subclass, no string keys. Alternative: a class-level attribute name looked up with `getattr`.
- `make_snapshot(version=...)` takes a raw `/api/version` payload dict. Reason: keeps every snapshot input going through the parsers. Alternative: accept a `TraefikVersion`.
- `mock_tls_probe` uses an `AsyncMock(side_effect=...)` that returns a CertError dict carrying the probed host and port, so cache rows stay realistic. Alternative: a fixed `return_value`.
- Listener test adds a positive control (changed router set notifies exactly once) so the "no notification" assertion cannot pass on a broken listener. Alternative: only the negative assertion.
- `tests/test_api_pagination.py` has 11 tests: the six planned cases (a-f) plus the coordinator-level concurrency case, a missing/non-integer header case, a path-only parser-error case, a version/entrypoints shape-error case and a page-size-default case. Reason: covers the D-07 rule and the D-10 path-only message the must-haves name. Alternative: only the planned six plus the coordinator case.
- `filter_internal_items` stays in api.py with no remaining caller. Reason: the plan keeps api.py legacy code untouched for 04-05. Alternative: delete it now.
- Removing the two `filter_internal_items` tests from tests/test_binary_sensor.py (as planned) also removes the docstring that caused the deferred `SyntaxWarning` (`deferred-items.md`). The deferred entry is now obsolete; I left the file unchanged for the verifier to close.

## Known Stubs

None. (`_TraefikProxyAggregateCountSensor._counts` raising `NotImplementedError` is an abstract hook; all three subclasses implement it.)

## Issues Encountered

- `tests/test_init.py` takes about 13 s because `test_reload_service_verified_false_when_no_change_within_budget` waits the handler's 5 s budget; pre-existing, unchanged.
- Pre-existing: coverage addopts points at the old package name ("No data to report"); untouched.

## Next Phase Readiness

- 04-05 replaces `_get_response` / `_get` with `_request` and the `api_key` constructor with `Auth`; `tests/test_api_pagination.py` builds the client in one `_client(hass, page_size)` helper for that.
- 04-06 puts `/api/rawdata` in front of `async_get_state` and extends `_async_setup` / `_async_update_data` with the restart re-check; `stub_traefik_paginated` and the tracer test are the starting point.

## Self-Check: PASSED

- FOUND: tests/test_api_pagination.py, custom_components/traefik_proxy/api.py, custom_components/traefik_proxy/coordinator.py, tests/conftest.py
- FOUND commits: ed0200e, f4bf7d7, bba1948 (ancestors of HEAD)
- All task acceptance criteria and the plan-level verification commands re-run after Task 3 and passing
