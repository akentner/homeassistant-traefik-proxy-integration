---
phase: 04-data-layer-correct-lean
plan: 03
subsystem: data-layer
tags: [traefik, models, dataclasses, parsing, fixtures, tdd]

requires:
  - phase: 04-01
    provides: "Real redacted v2.11 / v3.7 captures (rawdata, version, entrypoints, paginated pages + index)"
provides:
  - "custom_components/traefik_proxy/models.py: frozen HA-free models, Status StrEnum, parsers for both payload shapes, TraefikSnapshot.build aggregates"
  - "tests/conftest.py: single fixture loader FIXTURE_VERSIONS / load_fixture / load_paginated"
  - "tests/test_models.py: 118 model tests over both real generations"
affects: [04-04, 04-05, 04-06, phase-05-entities, phase-06-certificates]

actuals:
  tokens: 10800
  tasks: 2
  commits: 4
plan_head_before: e23474fe13d6565074f581f559283de5e3a32780
plan_head_after: 3f5a845117b3d97cbd098752ce4744dc5a9b818c

tech-stack:
  added: []
  patterns:
    - "Frozen, slotted dataclasses with tuple sequences; dicts keyed by full Traefik name, built in sorted name order"
    - "One private item iterator for every HTTP kind (rawdata map or list page), @internal dropped, TypeError/KeyError on shape violations"
    - "Interface-stub RED commits: declarations plus trivial bodies so RED fails on assertions, not on import"

key-files:
  created:
    - custom_components/traefik_proxy/models.py
    - tests/test_models.py
  modified:
    - tests/conftest.py

key-decisions:
  - "ALLOWED_GENERATION_DIFFERENCES is empty: v2.11.63 and v3.7.19 agree on every projected router, service and middleware field"
  - "Service/Middleware type: list-form type string, else the lowercased single non-meta key of the rawdata item (generic, superset of loadBalancer/weighted/mirroring/failover)"
  - "parse_version: start-date key startDate (StartDate accepted); missing Version/start date raises KeyError, non-string TypeError, unparsable ValueError; naive date treated as UTC"
  - "RED commits carry an interface stub of models.py so the tdd.md RED classifier accepts the evidence (import faults are INVALID_RED)"

patterns-established:
  - "Model tests load captures only via tests.conftest (FIXTURE_VERSIONS, load_fixture, load_paginated) and parametrize over FIXTURE_VERSIONS"

requirements-completed: [DATA-01]

coverage:
  - id: D1
    description: "Router parsing: both payload shapes, both generations, D-02 status semantics, @internal drop, provider split, TLS tolerance, shape errors, sorted order, immutability"
    requirement: DATA-01
    verification:
      - kind: unit
        ref: "tests/test_models.py#test_routers_map_form_equals_list_form"
        status: pass
      - kind: unit
        ref: "tests/test_models.py#test_router_projection_equal_across_generations"
        status: pass
      - kind: unit
        ref: "tests/test_models.py#test_unknown_status_is_warning_and_logged_once"
        status: pass
      - kind: unit
        ref: "tests/test_models.py#test_parse_routers_shape_errors"
        status: pass
    human_judgment: false
  - id: D2
    description: "Services, middlewares, entrypoints, version, TraefikState and TraefikSnapshot.build aggregates on both real generations"
    requirement: DATA-01
    verification:
      - kind: unit
        ref: "tests/test_models.py#test_rawdata_equals_paginated_state"
        status: pass
      - kind: unit
        ref: "tests/test_models.py#test_services_store_no_backend_url_or_ip"
        status: pass
      - kind: unit
        ref: "tests/test_models.py#test_snapshot_aggregates_from_capture"
        status: pass
      - kind: unit
        ref: "tests/test_models.py#test_every_model_is_frozen"
        status: pass
    human_judgment: false
  - id: D3
    description: "Single conftest fixture loader for the committed captures"
    requirement: DATA-01
    verification:
      - kind: unit
        ref: "tests/test_models.py (every real-fixture case loads via tests.conftest.load_fixture / load_paginated)"
        status: pass
    human_judgment: false

duration: 7min
completed: 2026-11-14
status: complete
---

# Phase 4 Plan 03: Typed Traefik models Summary

**Stdlib-only `models.py` parses the real v2.11.63 and v3.7.19 captures, rawdata map and paginated list form alike, into equal frozen `Router` / `Service` / `Middleware` / `Entrypoint` / `TraefikVersion` models. It drops `disabled` + `error[]` → `error` and `@internal` items, and `TraefikSnapshot.build` computes per-kind counts and sorted problem tuples.**

## Performance

- **Duration:** 7 min (start 2026-11-14T00:35:24Z, end 2026-11-14T00:41:52Z)
- **Tasks:** 2 of 2 (Task 1 tracer, Task 2 expansion)
- **Files:** 3 (2 created, 1 modified)

## Accomplishments

- `models.py` is the single HA-free parse boundary (D-01..D-05). It has no `assert` and no import of `.api` or `homeassistant`.
- Map form equals list form for routers, services and middlewares in both generations (D-04). The router, service and middleware projections are equal across generations, with no allowed differences.
- `TraefikSnapshot.build` computes the D-15 aggregates that 04-04's coordinator will publish.
- `tests/conftest.py` holds the single fixture loader (D-22). The existing fixtures in conftest are untouched.

## Public API of `models.py` (04-04 reads this)

| Name | Kind | Notes |
|---|---|---|
| `Status` | `StrEnum` | members/values `enabled`, `warning`, `disabled`, `error` |
| `TlsDomain(main, sans)` | frozen dataclass | `sans: tuple[str, ...]` |
| `Router(name, provider, status, rule, service, entry_points, middlewares, tls, tls_domains, errors, using)` | frozen dataclass | `tls` True for any JSON object incl. `{}`; `service` is unqualified as Traefik reports it (`file-ok-svc`) |
| `Service(name, provider, status, type, servers_total, servers_up, used_by, errors)` | frozen dataclass | counts from `serverStatus` (`"UP"` vs all); no URL/IP stored |
| `Middleware(name, provider, status, type, used_by, errors)` | frozen dataclass | |
| `Entrypoint(name, address, protocol)` | frozen dataclass | `protocol` `"udp"` iff address ends in `/udp`, else `"tcp"` |
| `TraefikVersion(version, codename, start_date)` | frozen dataclass | `start_date` tz-aware |
| `StatusCounts(total, enabled, warning, error, disabled)` | frozen dataclass | classmethod `of(statuses)` |
| `TraefikState(routers, services, middlewares)` | frozen dataclass | dicts keyed by full name |
| `TraefikSnapshot(version, entrypoints, routers, services, middlewares, router_counts, service_counts, middleware_counts, router_problems, service_problems, middleware_problems)` | frozen dataclass | classmethod `build(*, version, entrypoints, state)` |
| `parse_routers / parse_services / parse_middlewares(payload)` | function | rawdata map or list page → `dict[str, Model]`, sorted, `@internal` dropped |
| `parse_entrypoints(payload)` | function | list of `{name, address}` → sorted `dict[str, Entrypoint]` |
| `parse_version(payload)` | function | `/api/version` → `TraefikVersion` |
| `parse_rawdata(payload)` | function | `/api/rawdata` → `TraefikState`; omitted/null sections → `{}`; tcp/udp ignored |
| `provider_from_name(name)`, `is_internal(name)` | function | provider = text after the last `@` (`""` if none); internal = ends in `@internal` |

**Errors raised (the client wraps them into `TraefikProxyPayloadError`, D-10):** `TypeError` for a wrong top-level type, a non-object item, a non-string key/name or a non-string required field. `KeyError` for a missing list-form `name`, entrypoint `name`/`address`, version `Version` or start date. `ValueError` for an unparsable start date. Never `AssertionError`.

**Hashing:** `TraefikState` and `TraefikSnapshot` compare by value but are not hashable (dict fields). Equality is what `always_update=False` needs.

## Status strings handled

- Observed in both captures: `enabled`, `warning`, `disabled`. No literal `error`.
- `disabled` with a non-empty `error[]` becomes `Status.error`. Captured cases are routers `broken-missing-service@file`, `chain-router@file` and middleware `broken-chain@file`.
- `warning` with errors stays `warning` (captured: `warn-unknown-entrypoint@file`).
- A literal `"error"` maps to `Status.error`.
- Missing or unknown values become `Status.warning`. Each distinct value is logged once at debug level, through a module set capped at 16 entries.

## Start-date key

`startDate` (lowerCamel, as captured from both generations). `StartDate` is also accepted. `datetime.fromisoformat` parses the nanosecond `Z` timestamps on Python 3.14 and in the HA 2026.3 venv; a naive value is treated as UTC.

## ALLOWED_GENERATION_DIFFERENCES

**Empty.** No projected field differs between v2.11 and v3.7:

- Router: name, provider, status, rule, service, entry_points, middlewares, tls, tls_domains, bool(errors)
- Service: name, provider, status, type, servers_total, servers_up
- Middleware: name, provider, status, type

Some raw generation differences exist outside the models and are deliberately not stored:

- v3.7 routers carry `priority` and `observability`; v2.11 rawdata emits `priority` only for internal routers.
- v3.7 list routers add `priorityStr`; v3.7 internal routers add `ruleSyntax`.
- v3.7 `loadBalancer` adds `responseForwarding` / `strategy`.

## Captured aggregate values (both generations, for 04-04 assertions)

- `router_counts`: total 128, warning 1, error 2, disabled 0, enabled 125. That is 129 rawdata routers minus `ping@internal`.
- `router_problems`: `("broken-missing-service@file", "chain-router@file", "warn-unknown-entrypoint@file")`
- `service_problems`: `("lb-mixed@file",)` (enabled, 1 of 2 servers UP)
- `middleware_counts`: `StatusCounts(total=2, enabled=1, warning=0, error=1, disabled=0)`; `middleware_problems`: `("broken-chain@file",)`
- Services after the `@internal` drop: `bulk-svc@file`, `file-ok-svc@file`, `lb-mixed@file`, `whoami@docker`

## Task Commits

1. **Task 1 RED:** router tests + conftest loader + interface stub: `e40d9a9` (test)
2. **Task 1 GREEN:** router parsing: `9fe0d19` (feat)
3. **Task 2 RED:** service/middleware/entrypoint/version/snapshot tests + stubs: `e7edc25` (test)
4. **Task 2 GREEN:** full models and aggregates: `3f5a845` (feat)

No REFACTOR commit (nothing to clean up).

Tracer gate: auto mode, so Task 1 `<verify>` was re-run after `9fe0d19` (49 passed, ruff, format and mypy clean). The plan then expanded to Task 2.

## TDD Gate Compliance

- RED before GREEN for both tasks (`test(04-03)` → `feat(04-03)`, twice).
- Task 1 RED: `uv run pytest tests/test_models.py -q -o addopts= -p no:cacheprovider --junitxml=…` exited 1 with 44 failed and 5 passed. `gsd tdd-red-evidence` returned `RED_EVIDENCE_OK` (`target_test_failed`, format junit) for target `test_secure_router_tls_domains[v3.7]`. Semantic assessment: the target ran and failed on `assert "secure@file" in routers` (the stub returned `{}`), which is the planned behaviour. It was not an import or collection fault.
- Task 2 RED: same command; it exited 1 with 63 failed and 55 passed. Verdict `RED_EVIDENCE_OK` for target `test_rawdata_equals_paginated_state[v3.7]`. Semantic assessment: the target ran and failed on the non-empty-state assertion (the stub `parse_rawdata` returned an empty `TraefikState`), which is the planned behaviour.
- The evidence records were kept in the session scratchpad and not committed.

## Verification

- `uv run pytest tests/test_models.py tests/test_fixture_redaction.py -q`: 178 passed (118 model tests plus 60 redaction tests)
- `uv run pytest -q`: 368 passed (250 before this plan, plus 118)
- HA 2026.3.0 venv (`~/.cache/traefik-proxy-integration/ha2603-venv`, `python -m pytest -q -o addopts="" tests`): 368 passed
- `uv run ruff check custom_components tests`: all checks passed
- `uv run ruff format --check custom_components tests`: 30 files already formatted
- `uv run mypy --strict custom_components/traefik_proxy`: no issues in 13 source files
- `frozen=True, slots=True` count: 9; `parse_*` function count: 5 + 1; AST `assert` count in models.py: 0; no `homeassistant` import
- No Docker containers, networks or volumes were started

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] RED commits include an interface stub of models.py**
- **Found during:** Task 1 RED (and again in Task 2 RED)
- **Issue:** The plan says "see it fail on the missing module". The canonical tdd.md, which the orchestrator mandated, treats import and collection faults as `INVALID_RED`, and that verdict blocks GREEN.
- **Fix:** Each RED commit adds the declarations (enum, dataclasses, function signatures) with trivial bodies (`{}` / empty state / `NotImplementedError`). The target tests then fail on their planned assertions, and the classifier returns `RED_EVIDENCE_OK`. The GREEN commits replace the stubs completely. `grep -n stub models.py` finds nothing.
- **Files modified:** custom_components/traefik_proxy/models.py
- **Commits:** e40d9a9, e7edc25

**Total deviations:** 1 (process only). **Impact:** none on the delivered code or scope.

## Worker Decisions

- Service type fallback uses the generic "single non-meta key, lowercased" rule, the same as middlewares (meta keys: name, provider, type, status, error, usedBy, serverStatus). Reason: it covers future service kinds and agrees with the four named keys; the map-vs-list test proves it on real data. Alternative: a fixed list of loadBalancer/weighted/mirroring/failover.
- A list-form `type` that is present but not a string gives `type ""`; it does not fall back to the config key. Reason: present-but-wrong-typed optional fields count as absent. Alternative: fall back to key derivation.
- `parse_version` raises `KeyError` for a missing `Version` or start date and `TypeError` for a non-string. Reason: the plan only specified `ValueError` for unparsable dates, and the start date is required for the W6 restart detection. Alternative: `start_date: datetime | None`.
- `parse_entrypoints` returns a dict sorted by name and rejects a mapping payload with `TypeError`. Reason: `/api/entrypoints` is a list, and sorted order matches the other parsers. Alternative: accept both shapes.
- A `tls.domains` entry with neither `main` nor `sans` is dropped, and a non-string `main` becomes `""`. Reason: nothing to probe. Alternative: keep empty `TlsDomain` entries.
- The unknown-status log key is the raw string, `None` for a missing status, or `repr()` for non-strings. Reason: one bounded set for all cases. Alternative: skip logging for a missing status.
- Duplicate names in a list page: the last item wins, no error. Reason: Traefik names are unique per kind, so this is not worth a failure path. Alternative: raise `ValueError`.
- `parse_rawdata` treats a falsy section value (`None`, `[]`, `{}`) as empty; a non-empty wrong type raises `TypeError`. Reason: Traefik omitempty/null semantics. Alternative: only `None` and missing count as empty.
- The list form accepts `list` only, not `tuple`. Reason: JSON decoding only yields lists. Alternative: any sequence except `str`.
- Added the public helper `StatusCounts.of(statuses)`. Reason: one counting path for three kinds. Alternative: a private module function.
- The test-side IP check uses an IPv4 plus IPv6-shaped regex over every flattened `Service` field value, plus a field-name denylist (`url`, `servers`, `address`, ...). Reason: proves S-06 structurally and on data. Alternative: only the `http://` substring check.

## Known Stubs

None.

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness

Ready for 04-04, which wraps these parser errors into `TraefikProxyPayloadError`, builds `TraefikSnapshot` once per cycle and asserts the captured aggregate values listed above. `tests.conftest.load_fixture` / `load_paginated` are the loaders for the client tests (the `x_next_page` values come back as the second tuple element).

## Self-Check: PASSED

- FOUND: custom_components/traefik_proxy/models.py, tests/test_models.py, tests/conftest.py
- FOUND commits: e40d9a9, 9fe0d19, e7edc25, 3f5a845
