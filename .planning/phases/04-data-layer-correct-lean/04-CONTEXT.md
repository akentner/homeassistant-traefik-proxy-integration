# Phase 4: Data layer (correct + lean) - Context

**Gathered:** 2026-11-14
**Status:** Ready for planning
**Source:** PRD Express Path (manager brief + decisions log M1–M25, U1–U2 + code audit + marketplace research)

<domain>
## Phase Boundary

Phase 4 replaces the data layer of `custom_components/traefik_proxy` so that it
reads the **real** Traefik v2.11 / v3.x API correctly and cheaply:

- typed, frozen models parsed once at the client boundary (`models.py`);
- an API client with auth modes none/basic/bearer, an explicit error taxonomy
  and one `GET /api/rawdata` per scan cycle (paginated fallback);
- real, redacted fixtures captured from local Docker Traefik containers;
- a typed `TraefikRuntimeData` and a coordinator that returns a
  `TraefikSnapshot` with precomputed aggregates and `always_update=False`.

**In scope:** `api.py`, new `models.py`, `coordinator.py`, new `data.py`
(runtime data), the minimal adaptations every consumer needs to read the new
snapshot (`__init__.py`, `entity.py`, `sensor.py`, `binary_sensor.py`,
`button.py`, `cert_coordinator.py`, `config_flow.py` validation call),
`tests/fixtures/`, a fixture-capture harness, and the test suite migration.

**Out of scope (later phases):** entity manager / dynamic add-remove / grace
period, ENUM router/service sensors, device model, translations, refresh
button (Phase 5); certificate source and probe rewrite (Phase 6); auth
selector in the UI, config-entry migration, `api_disabled` error mapping,
options/reauth/reconfigure rework, diagnostics (Phase 7); docstring sweep,
CI and release work (Phase 8). Entity unique_ids, entity set and platform
types stay exactly as they are in this phase.

</domain>

<decisions>
## Implementation Decisions

### Models (DATA-01)
- **D-01:** New module `custom_components/traefik_proxy/models.py` with frozen
  dataclasses (`@dataclass(frozen=True, slots=True)`): `Router`, `Service`,
  `Middleware`, `Entrypoint`, `TraefikVersion`, `TraefikSnapshot`, plus a
  `Status` `StrEnum`. Parsing from raw JSON lives in this module (pure
  functions / classmethods, no HA imports) and is called only by the client.
- **D-02:** `Status` members: `enabled`, `warning`, `disabled`, `error`.
  Traefik itself reports `enabled` / `warning` / `disabled`; a `disabled` item
  with a non-empty `error[]` list is parsed as `error` (decision M13 needs the
  distinction). An unknown status string is parsed as `warning` and logged once
  at debug level. Verify the observed status strings against the captured
  fixtures; if Traefik emits a literal `error`, map it to `Status.error`.
- **D-03:** Model fields (minimum; executor may add fields present in both
  Traefik generations):
  `Router(name, provider, status, rule, service, entry_points, middlewares,
  tls, tls_domains, errors, using)`;
  `Service(name, provider, status, type, servers_total, servers_up, used_by,
  errors)` — `servers_up/servers_total` come from `serverStatus`
  (`UP` vs. all); **backend URLs/IPs are not stored in the model** (audit S-06);
  `Middleware(name, provider, status, type, used_by, errors)`;
  `Entrypoint(name, address, protocol)` — `protocol` is `udp` when the address
  ends in `/udp`, else `tcp`;
  `TraefikVersion(version, codename, start_date)` with `start_date` a timezone-
  aware `datetime`. Sequences are tuples (hashable, frozen).
- **D-04:** The parser accepts both payload shapes: the `/api/rawdata` map form
  (`{"routers": {"<name>": {...}}, "services": {...}, "middlewares": {...}}`,
  key = name) and the list form of the paginated endpoints (items carry
  `name`). Both fixture generations (v2.11, v3.x) must produce equal model
  semantics for equivalent configuration.
- **D-05:** Items whose name ends in `@internal` are dropped during parsing
  (existing behaviour of `filter_internal_items`); provider-suffixed user items
  (`@file`, `@docker`) are kept. `provider` is the suffix after the last `@`.
  TCP/UDP sections of `/api/rawdata` are ignored (HTTP-only scope).

### Client (DATA-02, DATA-03, DATA-04)
- **D-06:** `TraefikProxyApiClient` is rewritten. Constructor takes the shared
  HA `aiohttp.ClientSession`, base URL, an `Auth` value object, `verify_ssl`
  and a request timeout. Public coroutines: `async_get_version()`,
  `async_get_entrypoints()`, `async_get_state()` (routers + services +
  middlewares as models). No `fetch_all`, no `get_overview`. The
  `reload_routers` method and its button/service stay untouched in this phase
  (removal is Phase 5, ENT-07) — the client keeps that method unchanged until
  then, isolated from the new read path.
- **D-07:** `async_get_state()` issues `GET /api/rawdata`. On
  `TraefikProxyNotFoundError` for `/api/rawdata` the client switches to the
  paginated fallback (`/api/http/routers`, `/api/http/services`,
  `/api/http/middlewares` with `per_page=<large>` and `page=N`, following the
  `X-Next-Page` header) and remembers the choice for the client's lifetime.
  The termination rule for `X-Next-Page` must be taken from the captured
  headers (do not guess); add a hard page cap (e.g. 100 pages) as a loop guard.
  **Amended (M27, 2026-11-14, plan 04-09):** while paginated, the coordinator
  cycle that performs the hourly version re-check retries `GET /api/rawdata`
  once; success switches back to rawdata, a 404 or any other non-auth failure
  keeps the pages, an auth failure propagates. At most one extra rawdata
  request per hour. This replaces the rule that the client keeps the
  paginated choice for good.
- **D-08:** `Auth` is a frozen dataclass with `mode: AuthMode`
  (`StrEnum`: `none`, `basic`, `bearer`) and optional `username`, `password`,
  `token`. The `Authorization` header is built per request (`Basic` via
  `aiohttp.BasicAuth(...).encode()`, `Bearer <token>`), never set as a session
  default header. `repr()` of `Auth` must not contain secrets
  (`field(repr=False)` for secrets).
- **D-09:** Until Phase 7 adds the auth selector, `build_api_client()` maps the
  existing entry data: non-empty `CONF_API_KEY` → `bearer`, empty → `none`.
  Basic auth is fully implemented and tested at client level in this phase.
- **D-10:** Error taxonomy: keep `TraefikProxyApiError` as the base class and
  `TraefikProxyAuthError` (401/403); add `TraefikProxyNotFoundError` (404),
  `TraefikProxyConnectionError` (every `aiohttp.ClientError` that is not a
  response-status error, `TimeoutError`, `OSError`) and
  `TraefikProxyPayloadError` (invalid JSON — `ValueError`/`aiohttp.ContentTypeError`
  — or an unexpected top-level shape). `TraefikProxyInvalidUrlError` is a
  subclass of `TraefikProxyConnectionError` (see D-11). To avoid an import
  cycle, `models.py` parsers raise `ValueError`/`TypeError`/`KeyError` and the
  client wraps them into `TraefikProxyPayloadError`. Other non-2xx statuses raise
  `TraefikProxyApiError` with the status code. Every `assert` in production
  code is replaced by an explicit shape check raising
  `TraefikProxyPayloadError`. Exception messages contain path and status only —
  never headers, credentials or the full URL with userinfo.
- **D-11:** `config_flow.py` validation switches from `get_overview()` to
  `async_get_version()` and maps the new taxonomy so no existing branch goes
  dead: `TraefikProxyAuthError` → `invalid_auth`, `TraefikProxyNotFoundError`
  → the existing `ApiDisabled`/`api_disabled` branch (this re-wires the branch
  the old code intended; the full error-path test matrix and the translated
  text stay Phase 7, FLOW-04), `TraefikProxyInvalidUrlError` (a subclass of
  `TraefikProxyConnectionError`, raised for `aiohttp.InvalidUrlClientError`) →
  `invalid_url`, every other `TraefikProxyApiError` → `cannot_connect`.
  Existing config-flow tests keep passing; adjust only their mocks to the new
  exception types.

### Runtime data + coordinator (DATA-05, DATA-06)
- **D-12:** New `custom_components/traefik_proxy/data.py` with
  `@dataclass class TraefikRuntimeData: client, coordinator, cert_coordinator`
  and `type TraefikProxyConfigEntry = ConfigEntry[TraefikRuntimeData]`.
  `entry.runtime_data` becomes this dataclass; every
  `getattr(..., "cert_coordinator", None)` and `coordinator.cert_coordinator`
  monkey-attach is removed. `CoordinatorEntity` subclasses receive the
  coordinator explicitly (`entry.runtime_data.coordinator`). Setup order:
  build client and both coordinators, assign `entry.runtime_data` **before**
  the cert coordinator's first refresh (it reads the main snapshot). The
  client exists once: the coordinator reads it from `TraefikRuntimeData`
  (or both reference the same object and the options listener replaces it in
  one place), so `runtime_data.client` can never drift from the client the
  coordinator uses.
- **D-13:** `TraefikProxyCoordinator` is a
  `DataUpdateCoordinator[TraefikSnapshot]` with `always_update=False`.
  `_async_setup()` fetches version and entrypoints once (errors there surface
  as `ConfigEntryNotReady` / `ConfigEntryAuthFailed` through the normal
  first-refresh path). Each cycle calls `async_get_state()` (one request).
- **D-14:** Restart detection: `/api/rawdata` does not carry `StartDate`, so the
  coordinator re-checks `/api/version` at most once per hour and on the first
  successful cycle after a failed one; when `start_date` (or `version`) changed
  it re-fetches `/api/entrypoints`. With default options and no failures, a
  cycle makes exactly one HTTP request.
- **D-15:** `TraefikSnapshot` fields: `version: TraefikVersion`,
  `entrypoints: dict[str, Entrypoint]`, `routers: dict[str, Router]`,
  `services: dict[str, Service]`, `middlewares: dict[str, Middleware]`, and
  aggregates computed once in the coordinator: per kind a status count object
  (`total`, `enabled`, `warning`, `error`, `disabled`) and the tuple of problem
  names (status ≠ enabled; for services also any server DOWN). Dataclass
  equality drives `always_update=False`; the snapshot must not be mutated after
  construction.
- **D-16:** Error mapping in the coordinator: `TraefikProxyAuthError` →
  `ConfigEntryAuthFailed`; every other `TraefikProxyApiError` → `UpdateFailed`.
  Translated messages are Phase 7 (FLOW-05).

### Consumers keep working (no behaviour change for users)
- **D-17:** Existing platforms (`sensor.py`, `binary_sensor.py`, `button.py`,
  `entity.py`, `__init__.py`) and `cert_coordinator.py` are adapted **minimally**
  to read from `TraefikSnapshot` / `TraefikRuntimeData` instead of raw dicts.
  Entity classes, unique_ids, names, platforms and the entity set stay as they
  are; the deep rework is Phase 5. Their isinstance-based raw-dict defences go
  away together with the raw dicts.
- **D-18:** Attributes that were sourced from `/api/overview` or from fields
  that do not exist on real Traefik (`loadbalancer.status`, `servers` URLs,
  overview `tcp/udp` counts) are recomputed from the snapshot where the
  snapshot has the data (HTTP counts, service `servers_up/servers_total`) and
  dropped otherwise. No backend URL is exposed. These attributes never worked
  on real Traefik (audit A-05), so this is not treated as a breaking change;
  it is recorded for the CHANGELOG (Phase 8).
- **D-19:** The options-update listener in `__init__.py` must keep working with
  the new client constructor (it rebuilds the client via `build_api_client`);
  its removal is Phase 7 (FLOW-02).

### Fixtures (DATA-07)
- **D-20:** A capture harness lives in `tests/traefik/`: a `compose.yaml`
  running pinned Traefik **v2.11.x** and **v3.x** (latest v3.7 line, so Phase 6
  can use `/api/certificates` from the same capture), a `whoami` backend, file-
  provider dynamic config and docker-provider labels, plus a capture script.
  The scenario must include: `@file`, `@docker` and `@internal` items; a router
  with `error[]` (e.g. reference to a missing service); a router in `warning`
  if Traefik produces one (e.g. missing middleware); a load-balanced service
  with one server UP and one DOWN (health check on an unreachable address);
  a TLS router with `tls.domains`; more than 100 generated routers for the
  paginated path; the API behind a `basicAuth` middleware for a live auth check.
- **D-21:** The capture script writes per version
  `tests/fixtures/<version>/{rawdata,version,entrypoints}.json`, the paginated
  pages incl. their `X-Next-Page` header values, and (v3.7) `certificates.json`.
  Redaction is applied in the script: IPs → RFC 5737 addresses (`192.0.2.x`),
  hostnames → `*.example.com`/`example.org`, container IDs/random names
  normalised. Fixtures are committed; tests never start Docker. A test fails
  if any fixture contains a private-range IP, a non-example hostname or the
  basic-auth credentials.
- **D-22:** The old synthetic fixtures (`traefik_*.json`) are deleted once all
  tests are migrated; tests load fixtures through one conftest helper and mock
  HTTP with `aioclient_mock` (keyed by URL incl. query string for pages).

### Quality gates
- **D-23:** Every plan leaves `pytest`, `ruff check`, `ruff format --check`
  and `mypy --strict custom_components/traefik_proxy` green. Minimum HA stays
  2026.3.0 (M4): no 2026.11-only API (`DataUpdateCoordinator._async_setup`
  exists since 2024.8 and is allowed).
- **D-24:** Request-count assertions are part of the tests: one setup-plus-cycle
  scenario asserts the exact set of URLs requested (setup: version,
  entrypoints, rawdata; steady cycle: rawdata only; hourly / post-failure:
  + version; restart detected: + entrypoints).

- **D-25:** The capture harness must not be collected by pytest (file name
  without `test_` prefix, or `tests/traefik` in `norecursedirs`).

### Claude's Discretion
- Internal helper layout inside `models.py` / `api.py` (classmethods vs. module
  functions), exact `per_page` value, the hourly re-check mechanism
  (timestamp vs. counter), and the shape of the aggregate object.
- Plan split and wave layout (tracer-first: lead with an end-to-end slice from
  fixture → model → client → coordinator → one existing entity).
- Whether to keep `filter_internal_items` as a public helper (only if a caller
  still needs it after D-05).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Findings and decisions
- `.planning/research/AUDIT-ARCH-PERF-UX.md` — §2.1 A-05, A-06, A-10, A-11,
  A-15, A-16; §2.2 P-01, P-02; §2.5 H-11; §3 target architecture; §0 measurements.
- `.planning/research/MARKETPLACE-BEST-PRACTICES.md` — §4.2 (runtime data,
  `_async_setup`, `always_update=False`, `UpdateFailed`), §5 (HA 2026.x
  deprecations; keep min HA 2026.3.0).
- `.planning/ROADMAP.md` — Phase 4 goal and success criteria; cross-phase gates.
- `.planning/REQUIREMENTS.md` — DATA-01..DATA-07; "Audit traceability".

### Code being replaced or adapted
- `custom_components/traefik_proxy/api.py` — current client (6 parallel GETs,
  asserts, partial exception handling).
- `custom_components/traefik_proxy/coordinator.py` — `TraefikProxyData`
  TypedDict, `build_api_client`, `effective_verify_ssl`.
- `custom_components/traefik_proxy/__init__.py` — setup, runtime_data,
  options listener, reload service.
- `custom_components/traefik_proxy/sensor.py`, `binary_sensor.py`,
  `button.py`, `entity.py`, `cert_coordinator.py`, `config_flow.py` —
  consumers of `coordinator.data` / `runtime_data`.
- `tests/conftest.py`, `tests/fixtures/*.json`, `tests/test_api.py`,
  `tests/test_coordinator.py` and the platform tests.

### Project rules
- `./CLAUDE.md` — stack, "What NOT to use" (shared session, no
  `hass.data`, no `async_timeout`, no token logging).

</canonical_refs>

<specifics>
## Specific Ideas

- Real Traefik facts from the audit (verified in Traefik source v2.11.0 …
  v3.7.19): service key is `loadBalancer` (camelCase); backend health is the
  top-level `serverStatus: {url: "UP"|"DOWN"}`; items carry `error[]`,
  `usedBy[]`, `provider`; overview counts are `{total, warnings, errors}`
  objects; list endpoints paginate at 100 (`defaultPerPage`, `X-Next-Page`);
  the API is GET-only; `/api/certificates` exists from v3.7.
- Measured today: 6 GETs per 15 s cycle (34 560 requests/day per instance);
  target is 1 GET per cycle (~5 800/day at 15 s).
- Docker 29.9.3 is available locally for the capture harness (M20).

</specifics>

<deferred>
## Deferred Ideas

- Entity lifecycle, ENUM sensors, device model, translations, refresh button —
  Phase 5.
- `/api/certificates` consumption and the async probe — Phase 6 (the v3.7
  capture in D-21 provides its fixture).
- `api_disabled` mapping, auth selector UI, config-entry migration — Phase 7.
- Docstring / planning-reference sweep of touched modules beyond what the
  rewrite naturally removes — Phase 8 (A-19).

</deferred>

---

*Phase: 04-data-layer-correct-lean*
*Context gathered: 2026-11-14 via PRD Express Path*
