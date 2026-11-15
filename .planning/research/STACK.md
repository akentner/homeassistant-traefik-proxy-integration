# Stack Research — Home Assistant Traefik Proxy Integration

**Domain:** HACS-distributable Home Assistant custom integration (local-polling HTTP client)
**Researched:** 2026-07-05
**Updated:** 2026-11-15 to the shipped 1.0.0 state (Phase 8, plan 08-11): domain `traefik_proxy`, minimum Home Assistant 2026.11.0, no reload service.
**Confidence:** HIGH

## Executive Summary

This stack is the baseline for a polling-type HA custom integration that talks to a local JSON API over HTTP. It matches the user's sibling integrations (`homeassistant-gatus-integration`, `homeassistant-kroki-integration`), follows the current HA conventions, and has **zero third-party pip dependencies** because everything is provided by Home Assistant Core itself.

The headline decisions:

1. **No `aiotraefik` library exists** on PyPI (verified 404). The integration ships its own thin aiohttp client (`custom_components/traefik_proxy/api.py`) on HA's shared `aiohttp.ClientSession` from `async_get_clientsession(hass)`.
2. **No extra HTTP library** — neither `requests` nor `httpx`. HA Core bundles `aiohttp` and provides `aiohttp_client.async_get_clientsession()` for shared, configured sessions.
3. **HA Core minimum: `2026.11.0`** (user decision I1). The shipped code uses its APIs: repairs bound to `config_entry_id`, `async_unload_platforms_or_raise` and `OptionsFlowWithReload`.
4. **Certificate expiry** — on Traefik >= 3.7 the integration reads `GET /api/certificates`; on older versions it runs a threadless asyncio TLS probe (CERT_NONE handshake with SNI, DER parse with the HA-bundled `cryptography`) against the Traefik host. All other entities come straight from the JSON API.

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | `>=3.14.2` (HA 2026.11 ships 3.14) | Runtime | `pyproject.toml` `requires-python`; PEP-695 syntax available |
| Home Assistant Core | `>=2026.11.0` | Framework | User decision I1; `hacs.json` `homeassistant` and the CI `test-min-ha` job pin it |
| `aiohttp` | bundled by HA | HTTP client | HA uses aiohttp everywhere; `async_get_clientsession(hass)` is the shared session |
| `voluptuous` | bundled by HA | Config-flow schema | Already required by HA — no manifest entry |
| `cryptography` | bundled by HA | DER certificate parsing and chain verification in `tls.py` | HA ships it; no manifest entry needed |

> **Rule:** Custom integrations **must not** add to `manifest.json`'s `requirements` anything that HA Core already bundles — [contributors.home-assistant.io/core/integrations/manifest](https://contributors.home-assistant.io/core/integrations/manifest/).

### Manifest (`custom_components/traefik_proxy/manifest.json`)

| Field | Value | Rationale |
|-------|-------|-----------|
| `domain` | `traefik_proxy` | Matches the folder `custom_components/traefik_proxy/`. Underscore-style only (no hyphens). |
| `name` | `Traefik Proxy` | Display name in HA. |
| `categories` | `["computers_network.monitoring"]` | Marketplace category; hassfest requires sorted keys. |
| `integration_type` | `service` | One Traefik instance per config entry; the gateway itself *is* the integration. |
| `iot_class` | `local_polling` | Traefik runs on the user's homelab; the integration talks to it directly. **Not** `cloud_polling`. |
| `after_dependencies` | `["http"]` | Ensures HA's shared `aiohttp.ClientSession` is set up before `async_setup_entry`. |
| `requirements` | `[]` | Everything needed is bundled in HA. |
| `version` | `1.0.0` | HACS validates an [AwesomeVersion](https://github.com/ludeeus/awesomeversion) string; the release workflow compares it with the tag. |
| `codeowners` | `["@akentner"]` | GitHub usernames; required by HACS. |
| `documentation` | GitHub repository URL | Required by HACS. **Do NOT point at home-assistant.io** — that's for core integrations. |
| `issue_tracker` | GitHub issues URL | Required by HACS. |
| **No `quality_scale`** | — | Custom integrations trigger a `hassfest` warning if this is set. |

### `hacs.json` (repository root)

| Field | Value | Rationale |
|-------|-------|-----------|
| `name` | `"Traefik Proxy"` | Display name in HACS UI. Required. |
| `homeassistant` | `"2026.11.0"` | Minimum HA (user decision I1); HACS refuses older installs. |
| `hacs` | `"2.0.5"` | HACS minimum; matches the `gatus` integration. |
| **No `filename` / `zip_release`** | — | Standard folder-based distribution; HACS reads `custom_components/traefik_proxy/`. |
| **No `country`** | — | Not a regional integration. |
| **No `info.md`** | — | `README.md` is the information file HACS renders. |

### Repository Layout (shipped)

| Path | Purpose |
|------|---------|
| `custom_components/traefik_proxy/__init__.py` | Entry setup/unload, migrations, repairs |
| `custom_components/traefik_proxy/api.py` | Traefik HTTP client (aiohttp wrapper, auth modes, error taxonomy) |
| `custom_components/traefik_proxy/coordinator.py` | Snapshot `DataUpdateCoordinator` with precomputed aggregates |
| `custom_components/traefik_proxy/cert_coordinator.py` | Certificate cycle (6 h cadence, bounded concurrency) |
| `custom_components/traefik_proxy/tls.py` | Threadless asyncio TLS probe and certificate matching |
| `custom_components/traefik_proxy/entity_manager.py` | Add / missing / grace period / re-add of dynamic entities |
| `custom_components/traefik_proxy/sensor.py`, `binary_sensor.py`, `button.py` | Platforms (`PLATFORMS = ["binary_sensor", "sensor", "button"]`) |
| `custom_components/traefik_proxy/config_flow.py` | Config, options, reauth and reconfigure flows |
| `custom_components/traefik_proxy/diagnostics.py` | Redacted diagnostics download |
| `custom_components/traefik_proxy/brand/` | Local brand images (`icon`, `logo`, `dark_logo`, each with `@2x`) |
| `custom_components/traefik_proxy/translations/` | `en.json`, `de.json` |
| `tests/` | pytest suite with real Traefik fixtures |
| `hacs.json`, `README.md`, `CHANGELOG.md`, `LICENSE` | Distribution files |
| `pyproject.toml`, `ruff.toml`, `uv.lock`, `Makefile` | Dev tooling |
| `.github/workflows/validate.yml`, `release.yml` | CI (lint, test, minimum-HA test, hassfest, HACS) and tag check |

### Supporting Libraries (all from `homeassistant.*` — no `pip install`)

| Library | Import | Purpose | Notes |
|---------|--------|---------|-------|
| `DataUpdateCoordinator` | `homeassistant.helpers.update_coordinator` | Single polling point; fans updates to entities | One call-set per scan interval. |
| `CoordinatorEntity` | `homeassistant.helpers.update_coordinator` | Base class for entities reading from coordinator | Sets `should_poll=False`, wires availability. |
| `ConfigFlow` | `homeassistant.config_entries` | UI setup wizard (CORE-01), reauth, reconfigure | Subclass; `domain=` class keyword. |
| `OptionsFlowWithReload` | `homeassistant.config_entries` | Scan interval, TLS warning threshold, grace period, per-item toggles (CFG-01) | Reloads the entry on change; no manual update listener. |
| `SensorEntity` / `BinarySensorEntity` / `ButtonEntity` | `homeassistant.components.{sensor,binary_sensor,button}` | Entity base classes | The `refresh` button ("Refresh now") polls Traefik on demand. |
| `DeviceInfo` | `homeassistant.helpers.device_registry` | Main "Traefik Proxy" device plus sub-devices | Sub-devices are bound with `config_entry_id`. |
| `DeviceEntryType.SERVICE` | `homeassistant.helpers.device_registry` | Marker for service-type devices | Matches `integration_type: "service"`. |
| `async_get_clientsession` | `homeassistant.helpers.aiohttp_client` | Shared aiohttp session | **Always** use this; never create `aiohttp.ClientSession()` yourself. |
| `ConfigEntryNotReady` | `homeassistant.exceptions` | First-refresh failure → HA auto-retries | For transient errors only. |
| `ConfigEntryAuthFailed` | `homeassistant.exceptions` | 401/403 → triggers reauth flow | For bad credentials. |
| `UpdateFailed` | `homeassistant.helpers.update_coordinator` | Coordinator update error | Wraps any exception from `_async_update_data()`. |
| `issue_registry` | `homeassistant.helpers.issue_registry` | Repairs (`entities_migrated`, `insecure_credentials`) | Created with `config_entry_id` so HA removes them with the entry. |
| `selector` | `homeassistant.helpers.selector` | Type-safe config-flow form fields | `TextSelector`, `NumberSelector`, `BooleanSelector`, `SelectSelector`. |
| `voluptuous` | re-exported via `homeassistant.helpers.config_validation` as `cv` | Schema validation | Use `cv.string`, `cv.url` etc. |

### Traefik API Client (built-in, not a PyPI package)

**Decision: the client lives inside the integration (`api.py`); no `aiotraefik`.**

- `aiotraefik` on PyPI → **404 not found**. Verified directly.
- `traefik` on PyPI → also not found.
- Authentication modes: none, basic auth (username and password), bearer token.
- The integration only reads the Traefik API; it calls no mutating endpoint, registers no service action and ships no services file.

The Traefik API endpoints actually used:

| Endpoint | Returns | Used for |
|----------|---------|----------|
| `GET /api/version` | `{Version, Codename, StartDate}` | Version / start-time sensors; credential check in the config flow |
| `GET /api/entrypoints` | `[{name, address, ...}]` | Entrypoint data |
| `GET /api/rawdata` | routers, services, middlewares in one document | One request per scan cycle (Phase 4) |
| `GET /api/http/routers`, `/api/http/services`, `/api/http/middlewares` | paginated lists | Fallback only when `/api/rawdata` answers 404 |
| `GET /api/certificates` | certificates with `notAfter` and SANs | Certificate expiry on Traefik >= 3.7 |

Certificate expiry on Traefik < 3.7 uses the threadless probe in `custom_components/traefik_proxy/tls.py` (asyncio stream, CERT_NONE, SNI per router host, DER parse); `tls.py` is authoritative over the Phase 3 spike skill.

### Dev / Test Toolchain

| Tool | Version | Purpose | Notes |
|------|---------|---------|-------|
| `pytest` | `>=9.0.0` | Test runner | |
| `pytest-asyncio` | `>=1.4.0` | Async tests | `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "function"`. |
| `pytest-homeassistant` | `>=2026.11.0` (minimum-HA lock pins `==2026.11.0`) | HA-specific fixtures: `hass`, `MockConfigEntry`, `aioclient_mock`, `snapshot` | Tracks HA Core releases. |
| `pytest-cov` | `>=7.0.0` | Coverage | `fail_under = 99` on `custom_components.traefik_proxy`. |
| `aioresponses` | `>=0.7.9` | Mock aiohttp requests in unit tests | |
| `ruff` | `>=0.15.15` | Lint + format | Config in `ruff.toml` (`target-version = "py314"`). |
| `mypy` | `>=2.1.0` | Strict type checking | `uv run mypy --strict custom_components/traefik_proxy`. |
| `pre-commit` | latest | Run ruff + checks locally | `make install-hooks` / `make pre-commit`. |
| `uv` | latest | Python dep manager | Replaces `pip`/`venv`; `uv.lock` committed. |

---

## Alternatives Considered

| Layer | Recommended | Alternative | Why Not |
|-------|-------------|-------------|---------|
| HTTP client | `aiohttp` (via HA shared session) | `httpx` | HA core standardizes on aiohttp; aiohttp is already bundled. |
| HTTP client | `aiohttp` (via HA shared session) | `requests` | Synchronous; blocks the event loop. |
| Traefik client | **Custom wrapper in `api.py`** | `aiotraefik` PyPI package | **Does not exist** (404 verified). |
| Certificate source | `/api/certificates` (Traefik >= 3.7), else threadless asyncio probe | Thread-based probe (`asyncio.to_thread`) | `tests/test_tls.py` forbids `to_thread` / `run_in_executor` in `tls.py`; the asyncio stream probe needs no executor. |
| Certificate parsing | HA-bundled `cryptography` (DER) | `ssl.getpeercert()` | `getpeercert()` returns nothing under CERT_NONE; DER parsing works for untrusted and self-signed chains. |
| Async timeout | `asyncio.timeout()` (stdlib) | `async_timeout` PyPI package | HA Core deprecated `async_timeout`; replaced with stdlib. |
| Runtime data storage | `entry.runtime_data` (`TraefikRuntimeData`) | `hass.data[DOMAIN][entry_id]` | Deprecated; runtime_data is type-safe with PEP-695 aliases. |
| Quality scale | **Omit** | Set `quality_scale: "silver"` | hassfest **warns** if a custom integration sets this. |
| Min HA version | `2026.11.0` | Older 2026.x releases | User decision I1: the shipped code uses 2026.11 APIs (`OptionsFlowWithReload`, `async_unload_platforms_or_raise`, repairs with `config_entry_id`). |
| Manual refresh | "Refresh now" button (polls Traefik again) | Reload service / router refresh endpoint | Removed by user decision (M12/I3); the button re-polls instead of asking Traefik to reload. |
| Discovery | **None** | `zeroconf` / `dhcp` | Traefik doesn't advertise itself; users configure manually. |
| Architecture (no TLS file access) | API certificates or TLS handshake via the Traefik host | Read `acme.json` from disk | Requires filesystem access — out of scope ("integration talks only to the Traefik API"). |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `requests` / `requests-cache` | Sync; blocks the event loop | `async_get_clientsession(hass)` + aiohttp |
| `httpx` (standalone) | Not the HA integration pattern | aiohttp |
| `aiotraefik` | Does not exist on PyPI | Custom aiohttp wrapper in `api.py` |
| `async_timeout` (PyPI) | Deprecated; replaced by stdlib | `asyncio.timeout()` |
| `asyncio.to_thread` / executor jobs for TLS probes | Blocking work in threads; forbidden by `tests/test_tls.py` | The asyncio stream probe in `tls.py` |
| `hass.data[DOMAIN][entry_id]` | Deprecated | `entry.runtime_data` (typed via PEP-695 alias) |
| Per-entity `async_update()` | N×N HTTP calls, defeats the coordinator | `DataUpdateCoordinator` + `CoordinatorEntity` |
| `"quality_scale": "silver"` in manifest | hassfest warns for custom integrations | Omit the key |
| `"iot_class": "cloud_polling"` | Traefik is the user's own homelab proxy | `"iot_class": "local_polling"` |
| Creating `aiohttp.ClientSession()` in our code | Breaks HA's shared session | `async_get_clientsession(hass)` |
| Reading Traefik's `acme.json` from disk | Requires filesystem access the integration does not have | `/api/certificates` or the TLS probe |
| Logging tokens or passwords | Leaks secrets | Never log credentials; diagnostics are redacted |
| Pinning `requirements: ["aiohttp==..."]` | HA bundles aiohttp; pinning causes dep conflicts | `requirements: []` |
| Old typing syntax (e.g. `Optional[int]`) | Python 3.14 has modern syntax | `int | None`, `type MyConfigEntry = ConfigEntry[...]` |
| `asyncio.get_event_loop()` | Deprecated | `asyncio.timeout()` / the running loop |
| `async_create_clientsession` | Per-integration sessions; we want the shared one | `async_get_clientsession(hass)` |

---

## HACS / Distribution Specifics

### `hacs.json` schema (verified at hacs.xyz/docs/publish/start)

- `homeassistant` uses [AwesomeVersion](https://github.com/ludeeus/awesomeversion) — accepts CalVer (`2026.11.0`) and SemVer (`1.0.0`).
- `hacs: "2.0.5"` is the HACS minimum.
- Without `zip_release: true`, HACS reads from the default branch (or the latest GitHub release if releases are published).
- No `info.md`: HACS renders `README.md`.

### Brand assets

- Shipped locally in `custom_components/traefik_proxy/brand/`: `icon.png`, `icon@2x.png`, `logo.png`, `logo@2x.png`, `dark_logo.png`, `dark_logo@2x.png`.
- HACS `brands` checks `brand/icon.png`; HA serves the local brand images (verified in the 08-09 visual check).

### GitHub releases

- Tags keep the `v` prefix (`v1.0.0`); HACS compares with AwesomeVersion (`v1.0.0 == 1.0.0`).
- `release.yml` checks that the tag without `v` equals the `manifest.json` version.

---

## QA / Lint / CI Stack

| Tool | Where | Notes |
|------|-------|-------|
| `ruff check` + `ruff format --check` | `make lint`, pre-commit, `validate.yml` lint job | `select = ["B","E","F","I","UP","ASYNC","SIM","RUF"]` |
| `mypy --strict` | `make typecheck`, `validate.yml` lint job | `uv run mypy --strict custom_components/traefik_proxy` |
| `pytest` + coverage | `make test`, `validate.yml` test job | `fail_under = 99` |
| Minimum-HA test | `make test-min-ha`, `validate.yml` test-min-ha job | Hashed lock `.github/requirements-min-ha.txt` (HA 2026.11.0) |
| `hassfest` | `make hassfest`, `validate.yml` hassfest job | `home-assistant/actions/hassfest`, pinned by commit |
| HACS Action | `validate.yml` hacs job | `hacs/action` with category `integration`, pinned by commit; proven by the first PR CI run (REL-07) |

---

## Version Compatibility

| Component | Compatible With | Notes |
|-----------|-----------------|-------|
| `homeassistant>=2026.11.0` | Python >= 3.14.2 | Use PEP-695 syntax (`type X = ...`, `int | None`) |
| `aiohttp` (bundled) | HA Core's pinned version | Don't pin in manifest |
| `pytest-homeassistant>=2026.11.0` | HA Core 2026.11.x | Minimum-HA lock pins `==2026.11.0` |
| `pytest-asyncio>=1.4.0` | `asyncio_mode = "auto"` | `asyncio_default_fixture_loop_scope = "function"` |
| Traefik API client | Traefik v2.11+ and v3.x | `/api/certificates` only on Traefik >= 3.7 |
| `awesomeversion` (HACS validates) | `2026.11.0`, `1.0.0` | Both CalVer and SemVer accepted |
| `ruff>=0.15.15` | Python 3.14 | Enables `UP` rules targeting modern syntax |

---

## Roadmap Implications (historical, as planned on 2026-07-05)

The original research proposed four phases (foundation, core entities, TLS, quality). The shipped roadmap diverged: reload support was removed in Phase 5 (replaced by the "Refresh now" button), the data layer moved to one `GET /api/rawdata` per cycle (Phase 4), certificates moved to `/api/certificates` plus a threadless probe (Phase 6), and the minimum HA moved to 2026.11.0 (Phase 7). See `.planning/ROADMAP.md` for the authoritative history.

**Dependencies that informed phase ordering:**
- TLS features needed the isolated certificate helper first (`tls.py`).
- Config Flow came **before** Options Flow (Options Flow requires an existing config entry).
- HACS brand assets had to land before the first public release.

---

## Sources

### HIGH confidence (official documentation)

- [contributors.home-assistant.io/core/integrations/manifest](https://contributors.home-assistant.io/core/integrations/manifest/) — manifest schema
- [contributors.home-assistant.io/core/integrations/config-flow](https://contributors.home-assistant.io/core/integrations/config-flow/) — ConfigFlow API
- [contributors.home-assistant.io/core/integrations/file-structure](https://contributors.home-assistant.io/core/integrations/file-structure/) — integration file structure
- [hacs.xyz/docs/publish/start](https://hacs.xyz/docs/publish/start) — hacs.json schema (verified)
- [hacs.xyz/docs/publish/integration](https://hacs.xyz/docs/publish/integration) — repository layout (verified)
- [doc.traefik.io/traefik/reference/install-configuration/api-dashboard](https://doc.traefik.io/traefik/reference/install-configuration/api-dashboard/) — API endpoints (verified Jul 2026)
- [doc.traefik.io/traefik/reference/install-configuration/entrypoints](https://doc.traefik.io/traefik/reference/install-configuration/entrypoints/) — Entrypoint schema (verified)
- [github.com/home-assistant/core/blob/dev/requirements.txt](https://github.com/home-assistant/core/blob/dev/requirements.txt) — HA Core pinned deps

### HIGH confidence (HA core reference code)

- `homeassistant/components/faa_delays/coordinator.py` — minimal DataUpdateCoordinator pattern with `aiohttp_client.async_get_clientsession` and `asyncio.timeout`
- `homeassistant/components/gios/coordinator.py` — same pattern with `aiohttp.client_exceptions` handling and `UpdateFailed` with translation keys

### HIGH confidence (user's own prior integrations — local filesystem)

- `/home/akentner/Projects/homeassistant-gatus-integration/` — pattern reference; manifest.json, hacs.json, pyproject.toml
- `/home/akentner/Projects/homeassistant-kroki-integration/` — custom aiohttp wrapper pattern; `after_dependencies: ["http"]` pattern

### NEGATIVE results (404 verified)

- `pypi.org/pypi/aiotraefik` — **does not exist** (404). Use custom aiohttp wrapper.
- `doc.traefik.io/traefik/routing-configuration/http/routing/observability/` — 404; route changed.

### MEDIUM confidence

- Quality scale — HA quality scale docs at [contributors.home-assistant.io/core/quality-scale](https://contributors.home-assistant.io/core/quality-scale/); custom integrations omit `quality_scale` from the manifest.

---

*Stack research for: homeassistant-traefik-proxy-integration*
*Researched: 2026-07-05; updated to the shipped 1.0.0 state on 2026-11-15*
*Confidence: HIGH — verified against official HA + HACS + Traefik docs, the shipped code and the user's sibling custom integrations.*
