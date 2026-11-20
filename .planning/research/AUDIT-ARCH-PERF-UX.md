# Audit: Architecture, Performance, UX (code as-is)

Branch `feat/marketplace-polish` @ `c8d9919`, integration `custom_components/traefik_proxy`, HA 2026.10.4 dev env.
Read-only audit. Measurements in §0. Traefik facts verified against Traefik source tags v2.11.0 … v3.7.19
(`pkg/api/*.go`).

## 1. Summary

- **The integration does not reflect live Traefik state.** Per-item entities (router, service, entrypoint) cache their
  dict at construction and never refresh. A router flipping `enabled → disabled` stays `on` forever (measured).
  New routers/services are never added, and vanished ones are deleted from the registry. The core value
  ("see which routers are failing") is not met.
- **The reload feature cannot work.** No Traefik version (v2.11 … v3.7.19) has `POST /api/http/routers/refresh`. The
  API is GET-only. Button and service always fail against a real Traefik.
- **Test fixtures are fiction.** Real Traefik uses `loadBalancer` (camelCase) and `serverStatus`, has no `loadbalancer.status`,
  and returns overview counts as `{total,warnings,errors}` objects. On real Traefik, service `servers`/`server_count` and
  the overview `http/tcp/udp_count` attributes are always empty or 0, yet all 188 tests pass.
- **Silent truncation above 100 items.** Traefik paginates list endpoints at 100 by default (`X-Next-Page`). The client ignores this.
- **TLS checks are blind to the certificates that matter most.** The probe runs with `CERT_REQUIRED`, so expired,
  self-signed or private-CA certs fail the handshake. The `expiring` sensor then goes `unavailable` instead of `on`.
  Each 6 h cycle also logs one ERROR per TLS entity ("does not generate unique IDs"). Traefik ≥ 3.7 has `GET /api/certificates`.
- **Performance is not the problem.** 606 entities, no-op refresh ≈ 5 ms, attributes ≈ 300 B. Polling 6 endpoints every 15 s can drop to 1–3 calls.
- **UX:** no `translation_key`, no `icons.json`, no `de.json`, no entity categories, no `configuration_url`.
  Friendly names run to 60+ characters, and the problem aggregates (core value) are disabled by default.
- **Hygiene:** README is stale and contains wrong entity IDs, a YAML setup that does not exist and a private hostname.
  pre-commit and coverage still point at `custom_components/traefik`. 181 planning references sit in shipped code (38 % of lines are docstrings or comments).

| Area | Grade | One-liner |
|---|---|---|
| Architecture / correctness | **D** | Clean module split, but entity lifecycle and data binding are broken; heavy copy-paste |
| Performance | **B+** | Cheap per cycle; wasteful endpoint set, registry-wide scans, no pagination |
| UX | **D+** | Works in English only, raw names, no categories, alarms hidden by default |
| Brand | **B-** | Correct sizes and alpha; logo/dark variants missing; licence/trademark note wrong |
| Repo hygiene | **C-** | CI exists; README, pre-commit, coverage config and fixtures are stale |
| Open security items | **C** | 6 of 7 known items still open; plus a button that bypasses the admin check |

### 0. Measurements (probe test in scratchpad, not committed)

| Metric | Value |
|---|---|
| Entities on `tests/fixtures` | 14 (7 sensor, 6 binary_sensor, 1 button), 5 devices, 3 disabled by default, 0 with `entity_category` |
| Router `my-router` after API status `enabled → disabled` + refresh | state stays **`on`** |
| Service `backend-api` after `loadbalancer.status OK → DOWN` + refresh | state stays **`OK`** |
| New router / new service after refresh | **not created** (`None`) |
| Cert cycle refresh with 2 hosts | **3 ERROR log lines** `Platform traefik_proxy does not generate unique IDs …` |
| Cert entity's `CoordinatorEntity.coordinator` | the **main** coordinator, not the cert coordinator |
| 300 routers + 300 services: setup | 110 ms, 606 states |
| No-change refresh (600 entities) | 4.8–5.3 ms, 0 `state_changed`, `last_reported` bumped every cycle |
| Attribute JSON size | router 287 B, service 305 B, routers-count 362 B |
| `filter_internal_items` calls per cycle (sensor.py) | 10 |
| Test suite | 188 passed in 17 s; 12.5 s of that is two real 6 s sleeps (`test_init.py` reload tests) |
| Coverage | 86 % total, `config_flow.py` 63 % (all error mappings 166-175 uncovered) |
| Planning refs in shipped code (`CONTEXT.md`, `PITFALLS`, `D-xx`, `BLOCKER`, `Phase n`, `spike`) | 181 occurrences; docstrings + comments = 1257 / 3255 lines (38 %) |

## 2. Findings

Severity: **C** = critical (wrong data / broken feature), **H** = high, **M** = medium, **L** = low.
"Breaking?" = affects entity IDs, unique IDs, or attributes users may automate on.

### 2.1 Architecture and correctness

| ID | Sev | file:line | Finding | Impact | Proposal | Effort | Breaking? |
|---|---|---|---|---|---|---|---|
| A-01 | C | `binary_sensor.py:211,217-236`; `sensor.py:308,314-335,360,366-398` | Router, entrypoint and service entities store the item dict in `__init__` and read only that copy. Coordinator updates never reach them (measured). | Router/service state frozen at setup. Core value not met. | Entities hold only their **key** (name) and look up `coordinator.data[kind][key]` on each `_handle_coordinator_update`. Pre-index data as `dict[name, item]` in the coordinator. | S | No |
| A-02 | C | `binary_sensor.py:64-80`; `sensor.py:56-75` | Per-item entities are created only in `async_setup_entry`. No listener adds new routers, services or entrypoints. | New Traefik routers are invisible until the integration reloads or HA restarts. | Shared "dynamic entity manager": on each coordinator update, diff known keys against current keys and `async_add_entities(new)`. | M | No |
| A-03 | C | `binary_sensor.py:91-115`; `sensor.py:176-213` | Stale cleanup deletes registry entries as soon as an item is missing from one successful poll. Together with A-02 the entity never comes back. | A `docker restart` of a backend permanently deletes its router/service entity, including user renames, area and dashboard references. | Mark missing items `unavailable` and remove only after a grace period (e.g. N cycles or 24 h), or let users delete via `async_remove_config_entry_device`. Re-add when the item reappears (A-02). | M | No |
| A-04 | C | `api.py:149-180`; `__init__.py:48-128,155-161`; `button.py:302-342`; `services.yaml` | `POST /api/http/routers/refresh` does not exist in any Traefik version (API routes are GET-only in v2.11.0 … v3.7.19). | Reload button and service always raise. The 5 s polling loop is dead code. | Remove the reload service, button and client method. Optionally replace with a **"Refresh now" button** (`coordinator.async_request_refresh()` plus cert re-probe). | S | **Yes**: `button.traefik_reload` and `traefik_proxy.reload_routers` disappear |
| A-05 | C | `tests/fixtures/traefik_services.json`, `traefik_overview.json`, `traefik_entrypoints.json`; `sensor.py:369-398,504-507` | Fixtures do not match the real API. Real: `loadBalancer` (camelCase), top-level `serverStatus{url: UP/DOWN}`, `error[]`, `usedBy[]`, `provider`. Overview `http.routers` = `{total,warnings,errors}`. Entrypoint `transport` = object. | On real Traefik the service state falls back to `status`, `server_count` is always 0, `servers` is None, overview `http/tcp/udp_count` are always 0, and the entrypoint `transport` attribute is a nested dict. | Capture real responses from v2.11 and v3.x (redacted) as fixtures. Parse into typed models (`models.py`). Read `serverStatus` for backend health. | M | Attribute semantics change (they never worked on real Traefik) |
| A-06 | H | `api.py:89-102,124-140` | Pagination ignored. Traefik returns 100 items per page (`defaultPerPage = 100`, `X-Next-Page` header). | More than 100 routers or services are silently truncated. A-03 then deletes entities beyond page 1, and the cert coordinator misses hosts. | Use `GET /api/rawdata` (unpaginated: routers, services incl. `serverStatus`, middlewares, plus tcp/udp in one call), or follow `X-Next-Page` with `per_page=1000`. | S | No |
| A-07 | H | `entity.py:422`; `sensor.py:619-621`; `binary_sensor.py:471-473` | TLS entities subclass `TraefikProxyEntity`, so `CoordinatorEntity` subscribes them to the **main** coordinator. The cert coordinator is stored as `self._coordinator` without a listener. | TLS entities write state every 15 s for nothing and update on cert cycles only by side effect. Design is confusing. | Separate base `TraefikCertEntity(CoordinatorEntity[CertCoordinator])`. | S | No |
| A-08 | H | `sensor.py:86-125`; `binary_sensor.py:125-150` | Every cert cycle calls `async_add_entities` for **all** hosts again. HA rejects the existing ones with an ERROR (measured: 3 errors for 2 hosts). The docstring's claim that HA "REPLACES the defunct instance" is false (`entity_platform.py:995-1019`). | Log spam: 2 errors per TLS host every 6 h. | Track known hosts in a set; add only new ones (same manager as A-02). | S | No |
| A-09 | H | `__init__.py:72-78`; `button.py:342` | `reload_routers` acts on `coordinators[0]`. The button on entry B goes through the service and therefore acts on entry A. | Wrong instance with more than one Traefik. | Moot once A-04 removes it. Any future service gets a `config_entry_id` field; buttons call their own coordinator directly. | S | — |
| A-10 | M | `coordinator.py:266-293`; `sensor.py:216-241`; all platforms | Untyped `dict[str, Any]` everywhere with defensive `isinstance` on every access (≈ 60 checks). `TypedDict(total=False)` plus `# type: ignore` at the boundary. | Noise; bugs like A-05 hide behind the defensive code. | `models.py` with frozen dataclasses (`Router`, `Service`, `Middleware`, `Entrypoint`, `Cert`, `Status` StrEnum). Parse once in the client. The coordinator returns `TraefikSnapshot` with `dict[name, Model]` and precomputed aggregates. | M | No |
| A-11 | M | `coordinator.py:317-330`; `__init__.py:207-212` | `runtime_data` is the main coordinator with `cert_coordinator` monkey-attached as an optional attribute. The code reads it via `getattr(..., None)` in three places. | Implicit coupling; `None` paths are dead in practice. | `@dataclass class TraefikRuntimeData: client, coordinator, cert_coordinator`, typed as `ConfigEntry[TraefikRuntimeData]`. | S | No |
| A-12 | M | `binary_sensor.py:29`; `cert_coordinator.py:51-56` | `_HOST_FROM_RULE` is duplicated, and the circular-import comment is wrong (`cert_coordinator` is only TYPE_CHECKING-imported). The regex misses the v2 multi-arg form ``Host(`a`,`b`)`` and ignores `HostRegexp`/`HostSNI`. | Missed probe hosts on v2 configs. | Single `rules.py: extract_hosts(rule)` handling v2 multi-arg and v3 `||`, skipping regex/wildcard hosts. | S | No |
| A-13 | M | `binary_sensor.py:243-410` | Three near-identical `Any*FailingBinarySensor` classes (≈ 170 lines). | Copy-paste drift. | One class plus `EntityDescription(kind=…)`. | S | No |
| A-14 | M | `sensor.py:127-150,176-213`; `binary_sensor.py:91-115,152-175` | Five copy-pasted stale-cleanup closures, each scanning the **entire** HA entity registry by unique_id prefix. | Duplication; see P-04. | Part of the dynamic entity manager (A-02/A-03); use `er.async_entries_for_config_entry`. | S | No |
| A-15 | M | `config_flow.py:166-175` vs `api.py:103-107` | `ApiDisabled` is unreachable. The client already converts `ClientResponseError` to `TraefikProxyApiError`, so a 404 becomes `cannot_connect`. | Wrong error message for the most common setup mistake. | Client raises `TraefikProxyNotFoundError(status=404)`; the flow maps it to `api_disabled`. Add flow tests. | S | No |
| A-16 | M | `api.py:103-109,115-145` | Only `ClientResponseError`, `ClientConnectorError`, `InvalidUrlClientError` and `TimeoutError` are caught. `ServerDisconnectedError`, `ClientOSError` and JSON decode errors escape. `assert isinstance(...)` is used for shape checks (stripped under `-O`, `AssertionError` otherwise). | Unexpected-error tracebacks in the coordinator; "Unknown error" in the config flow. | Catch `aiohttp.ClientError` and `ValueError`; explicit shape check that raises `TraefikProxyApiError`. | S | No |
| A-17 | M | `__init__.py:229`; HA `config_entries.py:3297-3302` | `add_update_listener` together with reconfigure triggers `report_usage(... breaks_in_ha_version="2026.12.0")`. The listener also mutates the coordinator live (interval, client, threshold). | Breaks in HA 2026.12. | `OptionsFlowWithReload` and drop the listener. A reload is cheap (one poll); live mutation is not worth the complexity. | S | No |
| A-18 | L | `entity.py:375-376,425-429`; `cert_coordinator.py:119-121,247-254`; `sensor.py:728-735`; `const.py:43`; `strings.json:65-69`; `config_flow.py:290-317` | Dead code: `if TYPE_CHECKING: pass`, `_router_name` "back-compat alias", `_host_port`, `_reset` "test seam", `get_threshold` (duplicates the attribute), public alias `cert_cache_availability`, `VERSION="1.0.0"` (manifest says 0.3.0), unused `exceptions.cert_unavailable`, unreachable `async_step_yaml` plus its strings. | Noise, misleading docs. | Delete. Keep `tls._fetch_cert_raw(sni=…)`: it becomes production in T-03. | S | No |
| A-19 | L | all modules (181 refs) | Docstrings full of `CONTEXT.md D-xx`, `PITFALLS #n`, `BLOCKER #2 fix`, `v0.2.1 fix`, `plan 03-01 Task 3 step 3d(iii)`, `.claude/skills/...` paths (`tls.py:3-29`). | Unreadable for contributors; dangling references in shipped code. | Strip to one-line "what/why" docstrings; history belongs in git and CHANGELOG. | M | No |
| A-20 | L | `binary_sensor.py:238-240,305-307,358-360,408-410`; `sensor.py:337-339,400-402,453-455` | `available` overrides return `coordinator.last_update_success`, which is exactly the `CoordinatorEntity` default. | Noise. | Delete (per-item `available` becomes "item present" after A-03). | S | No |
| A-21 | L | `entity.py:431-452` | `device_info` is a property recomputed per call. `_url_host()` returns the string `"None"` when the host is missing. `sw_version` is frozen at entity add (no update after a Traefik upgrade). | Cosmetic. | Build `DeviceInfo` once. Update `sw_version` via `dr.async_update_device` when `version` changes. | S | No |
| A-22 | L | `config_flow.py:276-282` | `unique_id` = hostname only (two Traefik instances on one host with different ports collide). Entry title is always "Traefik Proxy". | Multi-instance UX. | unique_id = `host:port`; title = host. Migration: config entry `MINOR_VERSION` bump. | S | unique_id of the config entry changes (entity unique_ids are entry_id-based, so unaffected) |

### 2.2 Performance

| ID | Sev | file:line | Finding | Impact | Proposal | Effort | Breaking? |
|---|---|---|---|---|---|---|---|
| P-01 | M | `api.py:183-232` | 6 GETs every 15 s. `/api/version` and `/api/entrypoints` are static (change only on Traefik restart). `/api/overview` is used only for attributes that are broken anyway (A-05). | 34 560 requests/day per instance instead of ~5 800. | One `GET /api/rawdata` per cycle (all HTTP/TCP/UDP objects, unpaginated, includes `serverStatus`). Fetch `version` and `entrypoints` at setup and when `version.StartDate` changes. Fallback: 3 list calls with `per_page`. | S | No |
| P-02 | L | `sensor.py:457-508`; `binary_sensor.py:279-303,335-356,385-406` | Aggregates recompute `filter_internal_items` and status buckets on every property read (10 filter passes per cycle, 2 passes per binary aggregate). | Negligible today (5 ms per 600 entities) but O(items × aggregates). | Compute aggregates once in the coordinator snapshot (`TraefikSnapshot.counts`). | S | No |
| P-03 | M | All coordinator entities | Every entity calls `async_write_ha_state` on every cycle even if unchanged (`last_reported` bumps). The recorder does not store `state_reported`, but bus/websocket traffic scales with entity count × 4/min. | Load on large setups. | Override `_handle_coordinator_update` to write only when the entity's model object changed (dataclass equality). | S | No |
| P-04 | M | `sensor.py:143,185,203`; `binary_sensor.py:106,168` | Five listeners iterate `registry.entities.values()` (all entities of the whole HA install, often 2-5 k) every 15 s. | ~1 M dict iterations per hour for nothing. | `er.async_entries_for_config_entry` once per cycle in the manager; or skip cleanup when the key set is unchanged. | S | No |
| P-05 | M | `tls.py:289-291` | New `SSLContext` plus `load_default_certs()` (reads the CA bundle from disk) per probe. | ~2-10 ms CPU and I/O per host per cycle, in threads. | Module-level context (or HA `homeassistant.util.ssl.client_context()`), created once in the executor. | S | No |
| P-06 | M | `cert_coordinator.py:135-162`; `tls.py:386-399` | `asyncio.timeout(5)` wraps `to_thread`. On timeout the semaphore is released but the thread keeps running (connect and handshake each have their own 5 s socket timeout), so more than 4 blocking threads can pile up in HA's default executor. | Executor starvation with many dead hosts. | Native async: `asyncio.open_connection(host, port, ssl=ctx, server_hostname=sni)` (spike 005 confirmed it as a drop-in) plus `getpeercert(binary_form=True)`. No threads at all. | M | No |
| P-07 | M | `cert_coordinator.py:178-245` | Unbounded probe host count; wildcard hosts (`*.example.com` from `tls.domains`) are probed and fail DNS; port is always 443. | 2 entities and 1 handshake per host; failure noise. | Cap (e.g. 200, option), skip `*.` names, derive port from the router's `entryPoints` → entrypoint `address`. With T-01 (`/api/certificates`) no probing is needed at all on Traefik ≥ 3.7. | S | No |
| P-08 | L | `tls.py:250-261` | Module-global `_parse_log_cooldown` dict grows with every host ever seen. | Tiny leak. | Bound it, or drop the throttle (parse failures are already logged at debug level). | S | No |
| P-09 | L | `sensor.py:388-397`; `binary_sensor.py:226-236`; `sensor.py:483-508` | Duplicate attributes (`name` = `router_name` = `entrypoint_name` = `service_name`; `success_count` … plus the `status_breakdown` dict carrying the same numbers; `filtered_count` = state). | Recorder stores attributes on every change; ~40 % redundant. | One canonical key each; drop the `status_breakdown` dict or the flat keys. | S | **Yes** (attributes) |

### 2.3 UX

| ID | Sev | file:line | Finding | Impact | Proposal | Effort | Breaking? |
|---|---|---|---|---|---|---|---|
| U-01 | H | `binary_sensor.py:267,323,373` | `any_router/service/middleware_failing` are **disabled by default**, yet they are the core-value alarm. | New users see no alarm. | Enabled by default; they replace the 3 count sensors as the primary signal. | S | No (existing registry entries keep their disabled flag) |
| U-02 | H | `strings.json` (no `entity` section); all `_attr_name = "…"` | No `translation_key`; names hard-coded in English; no `icons.json`; `_attr_icon` hard-coded (`sensor.py:606`, `binary_sensor.py:455`). | No German UI; icons cannot depend on state. | `translation_key` per description, `strings.json` `entity.*`, `icons.json` with state icons (e.g. router `mdi:routes` / `mdi:routes-clock`), `translations/de.json`. Per-item entities keep `name=<traefik name>` (dynamic), with a translated `translation_placeholders` suffix where needed. | M | No (friendly names change; entity_ids do not) |
| U-03 | H | `strings.json:5-9,20`; `api.py:83-87` | The flow talks about a "Bearer token from Traefik static config (api.dashboard / api.insecure)". Traefik's API has **no token auth**; protection is a middleware in front (`basicAuth` is the documented pattern, or `forwardAuth`). Only Bearer is supported. | Users with the standard `basicAuth`-protected `api@internal` cannot authenticate (or are confused). | Auth selector: none / basic (username + password) / bearer header. Rewrite descriptions; `data_description` per field. | M | Config entry data migration (minor version) |
| U-04 | H | `entity.py:432-443` | Six devices per entry named e.g. `traefik.example.com Traefik Proxy — HTTP Routers`. The entity name is appended, giving `traefik.example.com Traefik Proxy — HTTP Routers TLS a.example.com certificate expiring` (≈ 80 characters). No `configuration_url`. No `via_device`. | Dashboards are unreadable; no one-click link to the Traefik dashboard. | One main device `Traefik (<host>)` with `configuration_url=<url>/dashboard/`, `sw_version`, `entry_type=SERVICE`. Optional sub-devices "Routers", "Services", "Certificates" with `via_device=main`, short names. | S | Device identifiers change → devices are re-created (entity_ids stay) |
| U-05 | M | `sensor.py:290-339` | Entrypoint sensors: state `":443"` (static config) shown as a primary entity. | Clutter. | `entity_category=DIAGNOSTIC`, disabled by default, or attributes on the main device. | S | No |
| U-06 | M | none set | No `entity_category` anywhere. Counts, version and entrypoints → `DIAGNOSTIC`; refresh button → `CONFIG`/`DIAGNOSTIC`. | Device page mixes alarms and diagnostics. | See §4. | S | No |
| U-07 | M | `binary_sensor.py:199,217-222` | Router `binary_sensor` with `device_class=RUNNING` collapses `warning`/`error`/`disabled` into `off`. A `warning` router still serves traffic, yet shows "Not running". | Misleading. | Router = `sensor` with `device_class=ENUM`, options `enabled/warning/error/disabled` (translated), plus a `problem` binary per router only if needed. Or keep the binary as `PROBLEM` (on = status ∉ {enabled}) with a `status` attribute. Planner's choice; ENUM is the most dashboard-friendly. | M | **Yes** if the platform changes (new entity_ids) |
| U-08 | M | `sensor.py:365-398` | Service state: a free-text string (from fake `loadbalancer.status`). No backend health. | No "is my backend up?" signal. | ENUM state from `status`; attributes `servers_up`, `servers_total` from `serverStatus`; optional `binary_sensor` "backend down" (PROBLEM) when any server is `DOWN`. Never expose raw server URLs (internal IPs) as attributes. | S | Attributes change |
| U-09 | M | `sensor.py:697-725`; `binary_sensor.py:490-506` | A cert probe error (`unreachable`, expired, …) makes both cert entities `unavailable`. | "Certificate broken" is shown the same way as "integration offline". | Keep the entity available; the `expiring` problem binary = `on` with `reason` when the cert is expired **or** the probe fails N times; the timestamp sensor keeps its last known value. | S | No |
| U-10 | M | `tls.py:330`; `binary_sensor.py:496` | `days_until_expiry` is computed at probe time and frozen for up to 6 h. | Threshold crossing detected up to 6 h late; the attribute is off by one around midnight. | Compute from `not_after` at read time (and in the coordinator update). | S | No |
| U-11 | M | `config_flow.py:366-370` | Reauth token field uses `cv.string` (plain text, visible). | Token shown in clear in the UI. | `TextSelector(PASSWORD)`. | S | No |
| U-12 | M | `config_flow.py:105-111,218-221,227-234` | Options use raw `vol.All(int, Range)` (no `NumberSelector`, no unit). The error key `scan_interval_out_of_range` ("Polling interval must be …") is also used for `tls_warn_days`. | Wrong error text; plain number boxes. | `NumberSelector(min,max,unit_of_measurement="s"/"d", mode=box)`; HA validates the range itself, so the custom error handling goes away. | S | No |
| U-13 | M | `services.yaml:3-7` | YAML folded scalar contains the literal `—` (escapes are not processed in `>-`), so the UI shows "—". The service also has no `strings.json` `services` entry (cannot be translated). | Cosmetic bug. | Goes away with A-04; any future service gets translations in `strings.json`. | S | — |
| U-14 | L | `strings.json:12-15` | Strings for a non-existent YAML step; `reauth_confirm` says "leave empty to clear auth". | Confusing. | Delete yaml strings; reword reauth. | S | No |
| U-15 | L | `sensor.py:434` | Count sensors are `MEASUREMENT` without a unit. Long-term statistics are fine, but `success_pct` is buried in attributes. | Gauges need templates. | Optional `% healthy` sensor (`PERCENTAGE`, MEASUREMENT, diagnostic). | S | No |
| U-16 | L | — | No `diagnostics.py` (ROADMAP 04-01). | Support burden. | `async_get_config_entry_diagnostics` with `async_redact_data` (token, password, URL host optional). | S | No |

### 2.4 Brand (`custom_components/traefik_proxy/brand/`)

| ID | Sev | file | Finding | Impact | Proposal | Effort | Breaking? |
|---|---|---|---|---|---|---|---|
| B-01 | — | `icon.png` 256×256 RGBA, `icon@2x.png` 512×512 RGBA | Correct names and sizes for HA's local brand serving (`homeassistant/components/brands/const.py` `ALLOWED_IMAGES`); transparent background (73 % transparent px); single brand colour `#2AA2C1`. | OK. | Keep. | — | — |
| B-02 | M | `brand/` | Not trimmed or centred: alpha bbox x 13-238 / y 25-228 (left 13, right 18, top 25, bottom 28 px). HA brands guidelines want trimmed, centred square icons. | Looks slightly small and off-centre in the integrations grid. | Re-export from the SVG, trimmed to the content, centred, ≤ 5 % padding. | S | No |
| B-03 | L | `brand/` | No `logo.png` / `logo@2x.png` (falls back to the icon; fine) and no `dark_*` variants. The teal reads fine on dark backgrounds. | Logo slot shows only the mark. | Optional landscape `logo.png` (mark + "Traefik Proxy" wordmark, max 256 px tall) and `logo@2x.png`. | S | No |
| B-04 | M | `README.md:62-64`; `brand/*` | The artwork is the official Traefik Labs mark. The README says "logo under the Apache License 2.0". Traefik's code is **MIT**, and the logo is a trademark that the code licence does not cover. | Legal and wording risk for a public HACS listing. | Check the Traefik Labs brand/press-kit terms. Write "Traefik and the Traefik logo are trademarks of Traefik Labs; used for identification only". Not affiliated. | S | No |
| B-05 | L | `icon.svg` | Not used by HA (PNG only) and shipped in the integration folder. | Harmless; 3.7 KB. | Move to `docs/` or keep as source. | S | No |
| B-06 | M | — | Local brand serving exists in the dev env (HA 2026.10.4). Not verified for the minimum version **2026.3.0**. | On older HA the icon may fall back to the brands CDN placeholder. | Check that `homeassistant/components/brands` exists in 2026.3.0; otherwise raise the minimum version or also submit to `home-assistant/brands`. | S | No |

### 2.5 Repo hygiene

| ID | Sev | file:line | Finding | Impact | Proposal | Effort | Breaking? |
|---|---|---|---|---|---|---|---|
| H-01 | H | `README.md:6-14,46-54,291-312` | Stale: "Phase 1 / Phase 2+ planned" feature list; documents a YAML setup that does not exist (`CONFIG_SCHEMA` is empty); entity IDs `binary_sensor.traefik_proxy_any_router_failing` and `sensor.traefik_proxy_<host>_cert` do not match the code (`traefik_any_router_failing`, `traefik_<host>_cert`); mentions an "HTTP Middlewares" device that does not exist. | Users copy broken YAML and cards. | Rewrite: features, prerequisites (Traefik API enabled and how to protect it), install (HACS button badge), config, entity table (from §4), example automations and cards, FAQ, screenshots. | M | No |
| H-02 | H | `README.md:25-32` | The manual-install section names the user's private host `haos-op3050-1` and the private `ha` alias. | Private infrastructure detail in a public repo. | Generic `scp`/Samba instructions. | S | No |
| H-03 | H | `.pre-commit-config.yaml:9-10,34-58` | `python3.13`; every `files:` filter is `^custom_components/traefik/…`, so the ruff, mypy and hassfest hooks **never run**. | False sense of safety. | Python 3.14, path `traefik_proxy`. | S | No |
| H-04 | M | `pyproject.toml:2,24` | Project name `homeassistant-traefik-integration`; `addopts --cov=custom_components.traefik` (CoverageWarning "never imported"; plain `pytest` measures nothing). | Coverage gate meaningless. | `--cov=custom_components.traefik_proxy`, `fail_under`. | S | No |
| H-05 | M | `.github/workflows/validate.yml` | Tests only on resolved HA 2026.10.x. The compatibility shims (`probatio` vs `voluptuous` in `__init__.py:11-14`, `config_flow.py:32-35`; `binary_sensor.py:11-14`; `button.py:274-277`) are never exercised on the declared minimum 2026.3.0. `hassfest@master` and `hacs/action@main` are unpinned. No release workflow (tag vs `manifest.version` check). | Min-version claim untested; drifting CI. | Matrix job pinned to `pytest-homeassistant-custom-component` for HA 2026.3.x; pin actions by SHA or tag; release workflow that checks the tag against the manifest and attaches a zip. | M | No |
| H-06 | M | — | No `CHANGELOG.md` (tags v0.1.4 … v0.3.0 exist); no `info.md` (optional for HACS 2.x; `hacs.json` has no `render_readme`). | Marketplace polish. | `CHANGELOG.md` (Keep a Changelog); `hacs.json` `"render_readme": true` or `info.md`. | S | No |
| H-07 | M | `CLAUDE.md` "Skill Auto-Routing" vs `.claude/skills/spike-findings-homeassistant-traefik-integration/` | CLAUDE.md routes to `spike-findings-homeassistant-traefik-proxy-integration`, but the directory and `name:` are `…-traefik-integration`. CLAUDE.md stack section still says `custom_components/traefik`, domain `traefik`. | Skill never auto-loads; stale guidance. | Rename the skill to `…-traefik-proxy-integration`; update the CLAUDE.md stack table. | S | No |
| H-08 | M | `tls.py:3-29` | Shipped code references `.claude/skills/...` and `.planning/spikes/...` paths. | Dangling references for HACS users. | Covered by A-19. | S | No |
| H-09 | L | `tests/test_binary_sensor.py:35` | `SyntaxWarning: "\w" is an invalid escape sequence` in a docstring. | Becomes an error in a future Python. | Raw string. | S | No |
| H-10 | L | `tests/test_init.py` (2 tests) | Real 6.2 s sleeps each (74 % of suite runtime). | Slow feedback. | Goes away with A-04; otherwise patch `asyncio.sleep` or use the freezer. | S | No |
| H-11 | M | `tests/fixtures/*` | Synthetic shapes (see A-05); no TCP/UDP, no `error[]`, no pagination, no `@docker`/`@file` providers, no TLS `domains`. | Tests validate fiction. | Real captures from Traefik v2.11 and v3.7 (docker-compose in `tests/traefik/` or recorded once), redacted. | M | No |
| H-12 | L | `Makefile:41` | `typecheck` runs `mypy --strict custom_components` (whole namespace), unlike CI. | Minor drift. | Align. | S | No |

### 2.6 Open items from the last security pass (status)

| ID | Sev | file:line | Status | Proposal | Effort | Breaking? |
|---|---|---|---|---|---|---|
| S-01 | H | `__init__.py:229` | **Open.** Update listener plus reconfigure → `report_usage` breaks in 2026.12.0. | A-17 (`OptionsFlowWithReload`, drop listener). | S | No |
| S-02 | M | `config_flow.py:395-430` | **Open.** Reconfigure to a new host keeps the old `unique_id`. | `await self.async_set_unique_id(new_host)` plus pass `unique_id=` to `async_update_reload_and_abort` (or `_abort_if_unique_id_mismatch` if a host change should be disallowed). | S | No |
| S-03 | M | `config_flow.py:404` | **Open.** An empty token keeps the stored one, so a token can never be cleared via reconfigure. | Explicit auth-mode selector (U-03) with "none"; or a "clear token" checkbox. | S | No |
| S-04 | M | `tls.py:236-241` | **Open.** Wildcard match allows multiple labels (`*.example.com` matches `a.b.example.com`), contradicting its own docstring and RFC 6125 §6.4.3. | Exactly one label: `host.split(".",1)[1] == entry[2:]`. | S | No |
| S-05 | M | `tls.py:355-358` | **Open.** `ssl.SSLError` is a subclass of `OSError`, so the `ssl` branch is unreachable and every TLS failure (including `SSLCertVerificationError`) becomes `oserror`. | Order `SSLError` before `OSError`; better still, T-03 (no verification in the probe). | S | `last_error` attribute values change |
| S-06 | L | `sensor.py:393-396` | **Open but moot on real Traefik** (the key is `loadBalancer`, so the attribute is always `None`). If fixed naively it would expose internal backend URLs/IPs. | U-08: counts only (`servers_up/total`), never URLs. | S | Attribute removed |
| S-07 | M | `cert_coordinator.py:204-245` | **Open.** Unbounded probe host count. | P-07 cap plus T-01. | S | No |
| S-08 | M | `button.py:342` | **New.** The admin-only service is reached via the button with a fresh context (no user), so any user allowed to press the button bypasses the admin check. | Moot with A-04. A refresh button needs no admin. | S | — |
| T-01 | H | `tls.py:289-293` | **New, functional.** `PROTOCOL_TLS_CLIENT` + `CERT_REQUIRED` + system CAs: **expired**, self-signed and private-CA certs fail the handshake. The "expiring" binary goes `unavailable` exactly when the cert is expired, and homelab certs from a private CA are never shown. | Prefer `GET /api/certificates` on Traefik ≥ 3.7 (gives `notAfter`, `sans`, `status`, issuer per cert; verified in `pkg/api/certificate.go`). Fallback probe: `CERT_NONE` + `getpeercert(binary_form=True)` + `cryptography.x509` (bundled with HA). Add a separate `verified: bool` attribute. | M | `last_error` semantics |
| T-02 | M | `tls.py:292` | **New.** The probe connects to the router hostname via DNS. Behind Cloudflare or another CDN it reads the CDN edge cert, not Traefik's; with split DNS it may hit a different host. | Connect to the Traefik host from the entry URL on the TLS entrypoint port with `SNI=router host` (the `_fetch_cert_raw(host, port, sni=…)` seam already exists). Option: "probe via DNS". | S | No |

## 3. Proposed target architecture

```
custom_components/traefik_proxy/
├── __init__.py        setup/unload only; builds TraefikRuntimeData; no services
├── const.py           domain, conf keys, defaults (no planning refs)
├── models.py          frozen dataclasses + StrEnum: Status, Router, Service(servers_up/total),
│                      Middleware, Entrypoint, Certificate, TraefikSnapshot(routers/services/
│                      middlewares: dict[name, Model], counts, version)
├── api.py             TraefikClient: auth (none|basic|bearer), GET /api/rawdata (fallback: paginated
│                      lists), /api/version, /api/entrypoints, /api/certificates (≥3.7, 404 → None);
│                      parses into models; error taxonomy Auth/NotFound/Connection/Payload
├── rules.py           extract_hosts(rule) for v2 multi-arg + v3 syntax; skips regex/wildcards
├── coordinator.py     TraefikCoordinator → TraefikSnapshot (1 call/cycle; version+entrypoints on
│                      setup and on StartDate change); aggregates computed once
├── cert_coordinator.py CertCoordinator(6h, own listeners): source = API certificates if available,
│                      else async probe (tls.py) to Traefik host:tls-port with SNI; cap + skip wildcards
├── tls.py             async probe, CERT_NONE + DER parse (cryptography), shared SSLContext, RFC6125 match
├── data.py            @dataclass TraefikRuntimeData(client, coordinator, cert_coordinator)
├── entity.py          TraefikEntity / TraefikCertEntity bases, one DeviceInfo factory
│                      (main device + optional via_device sub-devices), write-on-change
├── entity_manager.py  generic add-new / mark-missing / remove-after-grace per kind (routers,
│                      services, middlewares?, certs); replaces 5 closures + A-02/A-03/A-08
├── sensor.py          EntityDescriptions only (router/service ENUM, counts, version, cert timestamp)
├── binary_sensor.py   EntityDescriptions only (any_*_problem, cert_expiring, optional backend_down)
├── button.py          "Refresh now" (main + cert coordinator)
├── diagnostics.py     redacted config entry + snapshot dump
├── config_flow.py     user (auth selector) / reauth / reconfigure (unique_id update) /
│                      OptionsFlowWithReload with NumberSelectors
├── strings.json, translations/{en,de}.json, icons.json
└── brand/icon.png, icon@2x.png (+ logo.png, logo@2x.png)
```

Principles: parse once at the boundary, entities hold keys not data, one manager for the entity lifecycle,
no live-mutation listeners, no planning references in code.

## 4. Proposed entity model

Per config entry. "Main" = `Traefik (<host>)` device with `configuration_url`. Sub-devices (optional, `via_device`)
are marked in brackets. Translation keys in `snake_case`.

| Entity (translation_key) | Platform | Device | Category | Enabled by default | Device class | Unit / state class | State / key attributes |
|---|---|---|---|---|---|---|---|
| `routers_problem` | binary_sensor | Main | — | **yes** | `problem` | — | on if any user router ∉ enabled; attrs `problem_routers` (names), `count` |
| `services_problem` | binary_sensor | Main | — | **yes** | `problem` | — | same for services (incl. any `serverStatus` DOWN) |
| `middlewares_problem` | binary_sensor | Main | — | yes | `problem` | — | same for middlewares |
| `certificates_problem` | binary_sensor | Main | — | **yes** | `problem` | — | on if any cert expiring, expired or unprobeable; attrs `hosts` |
| `routers_total` / `services_total` / `middlewares_total` | sensor | Main | diagnostic | yes | — | count, `measurement` | attrs `enabled/warning/error/disabled` |
| `healthy_ratio` | sensor | Main | diagnostic | no | — | `%`, `measurement` | enabled ÷ non-disabled routers |
| `version` | sensor | Main | diagnostic | no | — | — | Traefik version; attr `codename`, `start_date` |
| `last_reload` (from `StartDate`) | sensor | Main | diagnostic | no | `timestamp` | — | Traefik process start |
| `refresh` | button | Main | diagnostic | yes | — | — | refreshes both coordinators |
| `router` (name = Traefik router name) | sensor | [Routers] | — | yes | `enum` (`enabled`, `warning`, `error`, `disabled`, `missing`) | — | attrs `rule`, `host`, `service`, `provider`, `entry_points`, `tls`, `errors` |
| `service` (name = Traefik service name) | sensor | [Services] | — | yes | `enum` (same set) | — | attrs `type`, `provider`, `servers_up`, `servers_total`, `used_by`, `errors` (no URLs) |
| `entrypoint` (name) | sensor | Main | diagnostic | **no** | — | — | address; attrs `protocol` (derived from `address` `/udp`) |
| `certificate_expiry` (name = host or CN) | sensor | [Certificates] | — | yes | `timestamp` | — | `not_after`; attrs `issuer`, `sans`, `days_left` (computed live), `source` (`api` / `probe`), `verified` |
| `certificate_expiring` (name = host or CN) | binary_sensor | [Certificates] | — | yes | `problem` | — | on if `days_left ≤ threshold`, expired, or probe failed N× (`reason` attr) |

Notes for the planner:
- **Entity IDs:** drop explicit `self.entity_id = …`. Existing installs keep their registry `entity_id`s, which are keyed by
  unique_id, so this does not break them. New installs get `has_entity_name`-derived IDs.
- **Unique IDs:** keep the `{entry_id}_{kind}_{name}` scheme. Changing platforms for routers/services (binary_sensor →
  ENUM sensor, U-07) creates new entities; offer a one-time cleanup of the old binary_sensors via
  `async_migrate_entry` plus a repairs notice.
- **Large Traefik** (e.g. 150 routers, 150 services, 120 TLS hosts): today ≈ 150 + 150 + 3 + 240 + 7 ≈ 550 entities.
  With per-certificate entities from `/api/certificates` (one wildcard cert covers many hosts), the certificate part
  typically shrinks to < 20. An option "create per-router/per-service entities" (default on, off for aggregates only)
  keeps big installs lean.
