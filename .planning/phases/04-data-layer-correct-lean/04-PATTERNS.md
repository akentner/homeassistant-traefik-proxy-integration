# Phase 4: Data layer (correct + lean) - Pattern Map

**Mapped:** 2026-11-14
**Files analyzed:** 22 (4 new modules/harness, 9 modified production, 9 test files/fixture sets)
**Analogs found:** 18 / 22

All paths are relative to the worktree root and are git-tracked.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `custom_components/traefik_proxy/models.py` (NEW) | model / transform | transform (JSON -> frozen dataclass) | `api.py:31,42-62` (`_INTERNAL_ITEM_RE`, `filter_internal_items`); `cert_coordinator.py:204-247` (raw tls.domains parsing) | partial (no dataclass models exist yet) |
| `custom_components/traefik_proxy/api.py` (REWRITE) | service / client | request-response | itself: `api.py:65-180` (`_get`, `reload_routers`) | exact |
| `custom_components/traefik_proxy/data.py` (NEW) | model (runtime container) | n/a | `coordinator.py:266-293` (`TraefikProxyData`, `TraefikProxyConfigEntry` alias) | role-match |
| `custom_components/traefik_proxy/coordinator.py` (REWRITE) | service / coordinator | polling request-response | itself: `coordinator.py:296-362` | exact |
| `custom_components/traefik_proxy/__init__.py` | config/setup | event-driven | itself: `__init__.py:183-262`, reload handler `:49-120` | exact |
| `custom_components/traefik_proxy/entity.py` | component base | read-only | itself: `entity.py:53-98` | exact |
| `custom_components/traefik_proxy/sensor.py` | component | read-only | itself: `sensor.py:49-215, 293-400, 455-510` | exact |
| `custom_components/traefik_proxy/binary_sensor.py` | component | read-only | itself: `binary_sensor.py:59-123, 207-240, 281-405` | exact |
| `custom_components/traefik_proxy/button.py` | component | read-only | itself: `button.py:41-42` | exact |
| `custom_components/traefik_proxy/cert_coordinator.py` | service / coordinator | read from main snapshot | itself: `cert_coordinator.py:178-247` | exact |
| `custom_components/traefik_proxy/config_flow.py` | controller (flow) | request-response | itself: `config_flow.py:149-175` (`_validate_input`) | exact |
| `tests/conftest.py` | test fixture | file-I/O | itself: `conftest.py:30, 42-54` (`FIXTURES_DIR`, `mock_traefik_config_entry`) | exact |
| `tests/test_api.py` | test | request-response | itself: `test_api.py:1-80` (`_MockSession`) — D-22 wants `aioclient_mock` instead, see `test_coordinator.py:39-56` | role-match |
| `tests/test_models.py` (NEW) | test | transform | `tests/test_sensor.py:28-60` (pure unit, no hass) | partial |
| `tests/test_coordinator.py` | test | request-response | itself: `test_coordinator.py:1-75, 133-144` | exact |
| `tests/test_init.py`, `test_reconfigure.py`, `test_verify_ssl.py`, `test_config_flow.py` | test | request-response (`aioclient_mock`) | `test_coordinator.py:39-56` `_stub_all_endpoints` | exact |
| `tests/test_sensor.py`, `test_binary_sensor.py`, `test_sensor_tls.py`, `test_binary_sensor_tls_expiring.py` | test | read-only (MagicMock coordinator) | `test_sensor.py:28-60` (`_entry_with_data`) | exact |
| `tests/test_cert_coordinator.py` | test | read from main snapshot | itself: `test_cert_coordinator.py:60-80, 255-440` | exact |
| `tests/test_fixture_redaction.py` (NEW, D-21) | test | file-I/O scan | none | no analog |
| `tests/traefik/compose.yaml` (NEW) | config (harness) | n/a | none | no analog |
| `tests/traefik/capture.py` (NEW) | utility script | file-I/O + HTTP | none (closest idea: `conftest.py:185-275` subprocess pattern) | no analog |
| `tests/fixtures/<version>/*.json` (NEW), delete `tests/fixtures/traefik_*.json` | fixture | file-I/O | existing `tests/fixtures/traefik_*.json` (6 files) | role-match |

---

## Consumer inventory (every read of `coordinator.data` / `runtime_data` / `cert_coordinator`)

Each of these lines must change when `runtime_data` becomes `TraefikRuntimeData` and `coordinator.data` becomes `TraefikSnapshot`.

### `entry.runtime_data` treated as the coordinator
| file:line | Current code | New target |
|---|---|---|
| `entity.py:60` | `super().__init__(entry.runtime_data)` | `super().__init__(entry.runtime_data.coordinator)` |
| `__init__.py:74` | `[entry.runtime_data for entry in ... LOADED]` (reload handler) | `entry.runtime_data` -> use `.coordinator` / `.client` |
| `__init__.py:183` | `coordinator: TraefikProxyCoordinator = entry.runtime_data` (options listener) | `rd = entry.runtime_data; rd.coordinator...; rd.client = build_api_client(...)` (D-19: coordinator must read client from runtime data or be updated too) |
| `__init__.py:231` | `entry.runtime_data = coordinator` | `entry.runtime_data = TraefikRuntimeData(client, coordinator, cert_coordinator)` — note cert_coordinator reads runtime_data during its first refresh (`:246`), so runtime_data must be set before that call |
| `sensor.py:49`, `binary_sensor.py:59`, `button.py:41` | `coordinator: TraefikProxyCoordinator = entry.runtime_data` | `entry.runtime_data.coordinator` |
| `cert_coordinator.py:204` | `self.config_entry.runtime_data.data.get("http_routers")` | `self.config_entry.runtime_data.coordinator.data.routers` |

### `cert_coordinator` monkey-attach / getattr (all removed per D-12)
| file:line | Current |
|---|---|
| `coordinator.py:98` (`cert_coordinator: CertCoordinator \| None = None` class attr) + `TYPE_CHECKING` import `:29` | remove |
| `__init__.py:197` | `getattr(coordinator, "cert_coordinator", None)` |
| `__init__.py:238-239` | `coordinator.cert_coordinator = cert_coordinator` |
| `sensor.py:82` | `getattr(entry.runtime_data, "cert_coordinator", None)` |
| `binary_sensor.py:122` | `getattr(entry.runtime_data, "cert_coordinator", None)` |
| `tests/test_sensor_tls.py:308,347-350` | `entry.runtime_data.cert_coordinator = cert_coord`; `assert entity.coordinator is entry.runtime_data` / `.cert_coordinator is cert_coord` |

### `coordinator.data` raw-dict reads
| file:line | Key read | Snapshot replacement |
|---|---|---|
| `entity.py:93-98` `_sw_version` | `data["version"]["Version"]` | `snapshot.version.version` |
| `__init__.py:84-87` `_current_router_names` | `data["http_routers"][*]["name"]` | `set(snapshot.routers)` |
| `binary_sensor.py:64` | `coordinator.data.get("http_routers")` + `filter_internal_items` | `snapshot.routers.values()` (internal already dropped, D-05) |
| `binary_sensor.py:101-104` stale cleanup | `http_routers` names | `set(snapshot.routers)` |
| `binary_sensor.py:207-240` router entity | `router["name"/"status"/"rule"/"service"]` | `Router` fields; entity must re-read its router from `coordinator.data.routers[name]` |
| `binary_sensor.py:281-302` any-router-failing | status != "enabled" | aggregate problem names / counts (D-15) |
| `binary_sensor.py:337-355` any-service-failing | `http_services` | aggregate |
| `binary_sensor.py:387-405` any-middleware-failing | `http_middlewares` | aggregate |
| `binary_sensor.py:490,517` / `sensor.py:637,664,719` | `cert_coordinator.data` dict (host -> CertInfo) | **unchanged** (cert cache is Phase 6) |
| `sensor.py:50-61` setup | `entrypoints`, `http_services` | `snapshot.entrypoints.values()`, `snapshot.services.values()` |
| `sensor.py:180-201` stale cleanup | same | `set(snapshot.entrypoints)`, `set(snapshot.services)` |
| `sensor.py:306-334` entrypoint sensor | `name/address/transport` | `Entrypoint(name,address,protocol)`; `transport` attr dropped or mapped (D-18) |
| `sensor.py:358-397` service sensor | `loadbalancer.status`, `loadbalancer.servers` (never real, A-05) | `Service.status`, `servers_up/servers_total`; no URLs (D-18, S-06) |
| `sensor.py:464-507` aggregate counts | `_DATA_KEY` list + `overview.http/tcp/udp` | aggregate counts; `http_count` from snapshot, `tcp_count`/`udp_count` dropped (D-18) |

Helpers that disappear with the raw dicts: `sensor.py` `_dict_or_empty`, `_list_or_empty`, `_safe_int`, `_count_by_status` (tested in `tests/test_sensor.py:24`); `filter_internal_items` imports in `sensor.py`, `binary_sensor.py`, `cert_coordinator.py`.

---

## Pattern Assignments

### `custom_components/traefik_proxy/api.py` (client, request-response) — REWRITE

**Analog:** current `api.py`.

**Module header / no-HA-imports rule** (lines 1-12) — keep:
```python
"""Async Traefik API client (no HA imports; pure aiohttp wrapper)."""
from __future__ import annotations
import asyncio
import logging
...
import aiohttp
_LOGGER = logging.getLogger(__name__)
```

**Existing exception classes** (lines 34-39) — keep both, add `TraefikProxyNotFoundError`, `TraefikProxyConnectionError`, `TraefikProxyPayloadError` as subclasses of `TraefikProxyApiError` (D-10):
```python
class TraefikProxyApiError(Exception):
    """Raised for non-auth Traefik API failures (5xx, network, parse)."""

class TraefikProxyAuthError(TraefikProxyApiError):
    """Raised on 401/403 — caller maps to ConfigEntryAuthFailed."""
```

**Request core to evolve** (lines 89-109). Keep: per-request headers, `asyncio.timeout`, `ssl=self._verify_ssl`, debug log with path+status only. Change: 404 -> NotFound, broaden `except` to all `aiohttp.ClientError`/`OSError` -> Connection, `json()` ValueError/`ContentTypeError` -> Payload, messages = path+status only (current `str(err)` of `ClientResponseError` includes the full URL — violates D-10):
```python
async def _get(self, path: str) -> Any:
    url = f"{self._base_url}{path}"
    try:
        async with asyncio.timeout(self._request_timeout):
            async with self._session.get(url, headers=self._headers(), ssl=self._verify_ssl) as response:
                _LOGGER.debug("path=%s status=%s", path, response.status)
                if response.status in (401, 403):
                    raise TraefikProxyAuthError(f"Auth failed for {path}: {response.status}")
                response.raise_for_status()
                return await response.json(content_type=None)
    except aiohttp.ClientResponseError as err:
        ...
    except (TimeoutError, aiohttp.ClientConnectorError, aiohttp.InvalidUrlClientError) as err:
        raise TraefikProxyApiError(str(err)) from err
```
For pagination the new `_get` needs to also return `response.headers.get("X-Next-Page")` (separate `_get_page` helper or a tuple return).

**Header builder** (lines 83-87) — replace with `Auth`-driven builder (D-08):
```python
def _headers(self) -> dict[str, str]:
    """Per-request auth header — never default header on session."""
    if self._api_key:
        return {"Authorization": f"Bearer {self._api_key}"}
    return {}
```

**Asserts to remove** (D-10): lines 115, 121, 127, 133, 139, 145 (`assert isinstance(result, dict|list)`).

**Remove:** `get_overview` (142-146), `fetch_all` (183-232), per-endpoint `get_routers/get_http_services/get_http_middlewares` (124-140) in favour of `async_get_state()`.

**Keep unchanged, isolated** (D-06): `reload_routers` lines 149-180 (it duplicates the error block — acceptable until Phase 5; must keep using the auth header builder).

**Internal filter** (lines 31, 42-62): `_INTERNAL_ITEM_RE = re.compile(r"@internal$")` moves into `models.py` parsing (D-05). Keep `filter_internal_items` only if a caller remains (none will after consumers migrate).

---

### `custom_components/traefik_proxy/models.py` (model, transform) — NEW

**No dataclass model exists.** Copy conventions:
- Pure module, no HA imports (same rule as `api.py:1`).
- `from __future__ import annotations`, PEP-604 unions, `StrEnum` (Py 3.14).
- Internal-suffix rule from `api.py:31`: `re.compile(r"@internal$")`; provider = `name.rsplit("@", 1)[1]` when `@` present.
- Raw tls-domain parsing to port into `Router.tls_domains` (from `cert_coordinator.py:213-240`; `sans` may be str or list):
```python
tls_block = router.get("tls")
if not isinstance(tls_block, dict) or not tls_block:
    continue
domains = tls_block.get("domains", [])
...
main = domain.get("main")
sans = domain.get("sans", [])
if isinstance(sans, str) and sans: ...
elif isinstance(sans, list): ...
```
- Shape violations raise `TraefikProxyPayloadError` — to avoid a circular import, either define the exception classes in `models.py` and re-export from `api.py`, or have parsers raise `ValueError`/`TypeError` and let `api.py` wrap them. Planner should pick one; recommended: `api.py` wraps.

---

### `custom_components/traefik_proxy/data.py` (runtime container) — NEW

**Analog:** `coordinator.py:266-293`.
```python
type TraefikProxyConfigEntry = ConfigEntry["TraefikProxyCoordinator"]
```
Becomes `type TraefikProxyConfigEntry = ConfigEntry[TraefikRuntimeData]` in `data.py`. Every module importing `TraefikProxyConfigEntry` from `.coordinator` must switch import (`__init__.py:30`, plus `entity.py`, `sensor.py`, `binary_sensor.py`, `button.py`, `cert_coordinator.py` — grep `TraefikProxyConfigEntry`). Use `TYPE_CHECKING` imports for `TraefikProxyCoordinator`/`CertCoordinator` to avoid cycles (pattern: `coordinator.py:260-261`).

---

### `custom_components/traefik_proxy/coordinator.py` (coordinator, polling) — REWRITE

**Analog:** current file.

**Imports** (lines 237-258) — keep shape; add `ConfigEntryNotReady` not required (first-refresh path handles `_async_setup` errors).

**Keep as-is:** `effective_verify_ssl` (296-304).

**`build_api_client`** (307-314) — adapt to new constructor + `Auth` (D-09):
```python
def build_api_client(hass: HomeAssistant, entry: ConfigEntry[Any]) -> TraefikProxyApiClient:
    return TraefikProxyApiClient(
        session=aiohttp_client.async_get_clientsession(hass),
        base_url=entry.data[CONF_URL],
        api_key=entry.data[CONF_API_KEY],
        verify_ssl=effective_verify_ssl(entry),
    )
```

**Constructor** (332-342) — add `always_update=False` to `super().__init__`; client injected or built here; DataUpdateCoordinator generic becomes `TraefikSnapshot`.

**Error mapping** (353-358) — keep exactly (D-16):
```python
try:
    result = await self.client.fetch_all()
except TraefikProxyAuthError as err:
    raise ConfigEntryAuthFailed from err
except TraefikProxyApiError as err:
    raise UpdateFailed(str(err)) from err
```
Apply the same mapping in `_async_setup()` (version + entrypoints).

**Remove:** `TraefikProxyData` TypedDict (266-290), `cert_coordinator` class attr (330), `# type: ignore[return-value]` (362).

---

### `custom_components/traefik_proxy/__init__.py` (setup)

**Setup order to preserve** (lines 228-262): coordinator first refresh -> runtime_data set -> CertCoordinator built + guarded first refresh with `async_set_updated_data({})` fallback -> forward platforms -> `add_update_listener`. New: build `TraefikRuntimeData(client=coordinator.client, coordinator=..., cert_coordinator=...)`; since `CertCoordinator.__init__` needs the entry and its first refresh reads `runtime_data.coordinator`, assign runtime_data with cert_coordinator before `cert_coordinator.async_config_entry_first_refresh()` (dataclass is mutable — D-12 says plain `@dataclass`).

**Options listener** (183-206): `coordinator.client = build_api_client(hass, entry)` — must also update `runtime_data.client` (or make the coordinator the single owner and have `TraefikRuntimeData.client` mirror it). Replace `getattr(coordinator, "cert_coordinator", None)` with `entry.runtime_data.cert_coordinator`.

**Reload handler** (69-87): `_current_router_names` becomes `set(rd.coordinator.data.routers)`; `coordinator.client.reload_routers()` (line ~94) stays.

---

### `custom_components/traefik_proxy/config_flow.py` (flow)

**Only change** (lines 157-175):
```python
client = TraefikProxyApiClient(
    session=async_get_clientsession(hass),
    base_url=data[CONF_URL],
    api_key=data.get(CONF_API_KEY, ""),
    verify_ssl=data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
)
try:
    async with asyncio.timeout(10):
        await client.get_overview()
except InvalidUrlClientError as err:
    raise InvalidUrl(data[CONF_URL]) from err
except TraefikProxyAuthError:
    raise InvalidAuth from None
except ClientResponseError as err:
    if err.status == 404:
        raise ApiDisabled from err
    raise CannotConnect from err
except TimeoutError, ClientConnectorError, TraefikProxyApiError:
    raise CannotConnect from None
```
- Constructor gets `Auth` (bearer if key, else none — same mapping as `build_api_client`; consider a shared `auth_from_entry_data()` helper in `coordinator.py`).
- `get_overview()` -> `async_get_version()`.
- Note: after the rewrite the client no longer leaks `ClientResponseError`/`InvalidUrlClientError`; the 404 -> `ApiDisabled` branch becomes dead. D-11 says NotFound maps to `cannot_connect` in this phase — **check `tests/test_config_flow.py` for a 404 -> `api_disabled` assertion** before deciding; if one exists, D-11 conflicts with "tests stay green unchanged" and needs a planner decision. Invalid URL: client must either re-raise a distinguishable error or `_check_url_shape` (line 156) must cover it.

---

### Platforms (`entity.py`, `sensor.py`, `binary_sensor.py`, `button.py`)

Minimal adaptation only (D-17). Pattern for reading per-item state: the existing router entity stores the dict at construction (`binary_sensor.py:207-240`, `self._router`) — keep the same constructor signature but take a model; property reads should prefer `self.coordinator.data.routers.get(self._router_name)` so state updates per cycle.

Aggregate pattern to replace (`binary_sensor.py:281-290`):
```python
data = self.coordinator.data
if not isinstance(data, dict):
    return None
routers = data.get("http_routers")
...
failing = [r for r in routers if isinstance(r, dict) and r.get("status") != "enabled"]
return bool(failing)
```
-> `return bool(self.coordinator.data.router_problems)` (name per aggregate shape chosen by planner). Keep `None` when `coordinator.data is None` only if the coordinator can be dataless (it cannot after first refresh).

---

### `custom_components/traefik_proxy/cert_coordinator.py`

Only `_collect_hosts_from_main_coordinator` (lines 178-247) changes: iterate `self.config_entry.runtime_data.coordinator.data.routers.values()`, read `router.tls_domains` and `router.rule`; keep `_HOST_FROM_RULE` regex and lowercase normalisation. Drop `filter_internal_items` import and isinstance guards. `__init__` (reads `config_entry`) unchanged.

---

## Test patterns

### HTTP mocking with `aioclient_mock` (D-22 target pattern)
**Source:** `tests/test_coordinator.py:23-56` (`MOCK_URL`, `_make_entry`, `_stub_all_endpoints`):
```python
MOCK_URL = "https://traefik.example.com:8080"

def _make_entry(**kwargs) -> MockConfigEntry:
    defaults = {"domain": DOMAIN, "title": "Traefik",
                "data": {CONF_URL: MOCK_URL, CONF_API_KEY: "k", CONF_VERIFY_SSL: True},
                "unique_id": "traefik.example.com"}
    defaults.update(kwargs)
    return MockConfigEntry(**defaults)

def _stub_all_endpoints(aioclient_mock, *, routers: list | None = None) -> None:
    aioclient_mock.get(f"{MOCK_URL}/api/version", json={"Version": "3.1.4", ...})
    aioclient_mock.get(f"{MOCK_URL}/api/entrypoints", json=[])
    aioclient_mock.get(f"{MOCK_URL}/api/http/routers", json=...)
    ...
```
Duplicated stub helpers exist in `test_init.py:45-80`, `test_reconfigure.py`, `test_verify_ssl.py`, `test_config_flow.py` (counts of `aioclient_mock.get`: init 12, coordinator 9, reconfigure 6, verify_ssl 6, config_flow 2). Consolidate into one conftest helper, e.g. `stub_traefik(aioclient_mock, version="v3.7", base=MOCK_URL)` loading `tests/fixtures/<version>/*.json` (D-22). Request-count assertions (D-24): `aioclient_mock.mock_calls` is a list of `(method, url, data, headers)` tuples; assert the URL set per phase and use `aioclient_mock.clear_requests()` between cycles. For pages, register with `params={"page": "2", "per_page": ...}` or full URL with query, and `headers={"X-Next-Page": "..."}`.

Setup entry pattern (`test_coordinator.py:58-73`):
```python
entry = _make_entry(); entry.add_to_hass(hass)
assert await hass.config_entries.async_setup(entry.entry_id)
await hass.async_block_till_done()
assert entry.state is ConfigEntryState.LOADED
assert isinstance(entry.runtime_data, TraefikProxyCoordinator)   # -> TraefikRuntimeData
assert entry.runtime_data.data["version"]["Version"] == "3.1.4"  # -> .coordinator.data.version.version
```
`test_coordinator.py:144` pokes `entry.runtime_data.client._verify_ssl` — becomes `entry.runtime_data.client._verify_ssl`.

### Fixture loading
**Source:** `tests/conftest.py:30` `FIXTURES_DIR = Path(__file__).parent / "fixtures"`; `tests/test_api.py:20-25`:
```python
FIXTURES = Path(__file__).parent / "fixtures"
def _load(name: str) -> object:
    return json.loads((FIXTURES / name).read_text())
```
Move into conftest as the single helper (D-22), parameterised by version dir.

### Client unit tests
`tests/test_api.py:27-80` uses a hand-rolled `_MockSession` (queue per path, records `headers`/`ssl`). D-22 says HTTP is mocked with `aioclient_mock`; `aioclient_mock` also records headers (`mock_calls[i][3]`), so the header/ssl/no-token-leak assertions can be ported. Client tests then need `hass` only for `async_get_clientsession(hass)`; alternatively keep `_MockSession` for pure client tests — planner decision (D-22 wording favours `aioclient_mock`).

### Platform unit tests (MagicMock coordinator)
**Source:** `tests/test_sensor.py:28-60`:
```python
def _coordinator_with(data): coord = MagicMock(); coord.data = data; coord.last_update_success = True; return coord
def _entry_with_data(data):
    entry = _entry(); coord = _coordinator_with(data); entry.runtime_data = coord; return entry, coord
```
Change to `entry.runtime_data = MagicMock(coordinator=coord, cert_coordinator=...)` and `data` = a real `TraefikSnapshot` built from a fixture via the model parser (gives real-shape coverage). Same in `test_binary_sensor.py`, `test_sensor_tls.py:302-350`, `test_cert_coordinator.py:60-80` (`entry.runtime_data.data = {...}` at 67, 261, 305, 355, 365, 390, 430 -> `entry.runtime_data.coordinator.data = snapshot`).

---

## Shared Patterns

### Error mapping (client -> HA)
**Source:** `coordinator.py:353-358`. Apply to `_async_update_data`, `_async_setup`, and the restart re-check path.

### Secrets / logging
**Source:** `api.py:83-87, 98` — auth header per request, never on session; debug log only `path` and `status`. Apply to all new request helpers and to `Auth.__repr__` (`field(repr=False)`).

### Shared session
**Source:** `coordinator.py:307-314` / `config_flow.py:157-162` — always `async_get_clientsession(hass)`.

### Typed entry alias
**Source:** `coordinator.py:293` PEP-695 `type` alias — reuse in `data.py`.

### Quality gates
`pyproject.toml` ruff/mypy config is the gate (D-23); existing code uses Py3.14 `except A, B:` syntax (`config_flow.py:174`, `conftest.py:166`) — ruff format keeps that.

## No Analog Found

| File | Role | Data Flow | Reason / guidance |
|---|---|---|---|
| `tests/traefik/compose.yaml` | harness config | n/a | No docker assets in repo. Follow D-20 scenario list; pin image tags. |
| `tests/traefik/capture.py` | script | HTTP + file-I/O | No capture tooling exists. Must not be collected by pytest (name it not `test_*`, or add `tests/traefik` to `norecursedirs`). Redaction rules D-21. Use stdlib/aiohttp; run via `uv run`. |
| `tests/test_fixture_redaction.py` | test | file-I/O scan | Use `ipaddress.ip_address(...).is_private` over regex-extracted IPs; hostname allow-list `example.com/org`. |
| `models.py` dataclasses | model | transform | No dataclasses in codebase; follow D-01..D-05 directly. |

## Metadata

**Analog search scope:** `custom_components/traefik_proxy/`, `tests/`
**Files scanned:** 26
**Pattern extraction date:** 2026-11-14
