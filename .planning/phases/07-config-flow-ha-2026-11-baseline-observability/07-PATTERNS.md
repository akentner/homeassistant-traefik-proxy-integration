# Phase 7: Config flow, HA 2026.11 baseline, observability - Pattern Map

**Mapped:** 2026-11-15
**Files analyzed:** 27 (production 13, tooling 4, tests 10 groups)
**Analogs found:** 25 / 27

Almost every Phase 7 file is a modification of an existing file, so the closest analog is usually the file itself (the "self" rows below). The only new production module (`diagnostics.py`) has no in-repo analog; RESEARCH.md Pattern 6 is its template. Paths are relative to `custom_components/traefik_proxy/` (prod) or the repo root (tests, tooling). All named analogs are git-tracked.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `config_flow.py` (rewrite: auth selector, visible fields, reauth/reconfigure, options with reload) | controller (flow) | request-response | itself: `_validate_input` (161-195), `async_step_user` (280-308), `async_step_reconfigure` (400-474) | exact (self) |
| `__init__.py` (migration 1.3, listener removal, `-> None`, unload_or_raise, repair) | setup / migration | event-driven | itself: `async_migrate_entry` `< 2` block (93-165), migration issue (147-157), setup (208-286) | exact (self) |
| `coordinator.py` (`auth_from_entry_data` 1.3, translated errors, redirect, `build_api_client` errors) | service (coordinator) | request-response (polling) | itself: `auth_from_entry_data` (437-447), `build_api_client` (450-457), error blocks (514-517, 543-546, 561-568) | exact (self) |
| `cert_coordinator.py` (`_stopping`, translated `UpdateFailed`, `CONF_TLS_WARN_DAYS`, remove `async_set_threshold`/`get_threshold`) | service (coordinator) | batch | itself: `async_shutdown` (487-492), `_async_schedule_day_boundary` (461-476), `__init__` threshold (257-260), errors (304, 351) | exact (self) |
| `api.py` (`allow_redirects=False`, `TraefikProxyRedirectError`, 3xx mapping) | service (client) | request-response | itself: error taxonomy (104-135), `_status_error` (138-145), `_request` (182-210) | exact (self) |
| `entity.py` (`via_device_id=` kwarg) | registry helper | CRUD (device registry) | itself: `async_setup_devices` (100-143) | exact (self) |
| `entity_manager.py` (grace hours from options) | registry helper | event-driven | itself: `per_item_entities_enabled` (93-95), grace checks (254, 333, 349) | exact (self) |
| `const.py` (`CONF_AUTH_TYPE`, grace constants, drop `MISSING_GRACE_PERIOD`, `VERSION`) | config | — | itself: `CONF_PER_ITEM_ENTITIES` block, clamp block (`MIN_/MAX_SCAN_INTERVAL`) | exact (self) |
| `binary_sensor.py` (drop `BinarySensorDeviceClass` shim, lines 16-19) | component | — | RESEARCH confirmation list | trivial |
| `diagnostics.py` (NEW) | utility (platform) | transform (read-only dump) | none in repo; data sources `data.py` `TraefikRuntimeData` (17-30), `HostCertState` (cert_coordinator 142-160) | no analog → RESEARCH Pattern 6 |
| `translations/en.json`, `translations/de.json` | config | — | themselves (current keys listed below) | exact (self) |
| `strings.json` | config | — | DELETE | — |
| `hacs.json`, `pyproject.toml`, `uv.lock` | config (tooling) | — | themselves | exact (self) |
| `.github/workflows/validate.yml` (+`test-min-ha` job) | config (CI) | batch | its `test` job (35-48) | exact |
| `tests/conftest.py` (rename imports, drop `pytest_plugins` + `enable_custom_integrations`, 1.3 entry data) | test fixture | — | itself: `make_traefik_entry` (224-234), `setup_traefik_entry` (237-254), fixture (322-326) | exact (self) |
| `tests/test_config_flow.py` | test | request-response | itself + `test_reconfigure.py` flow-driving style | exact (self) |
| `tests/test_reconfigure.py` | test | request-response | itself: `_make_entry` (36-44), `_probe_auth` (47-57), abort-before-probe test (139-161) | exact (self) |
| `tests/test_migration.py` | test | event-driven | itself: removal test (223-248), direct `async_migrate_entry` (276-298) | exact (self) |
| `tests/test_init.py` (listener test → reload test; repair tests) | test | event-driven | itself: `test_update_listener_registered_once_across_reloads` (147-165) | exact (self, rewrite) |
| `tests/test_verify_ssl.py` (options → reload) | test | request-response | itself: `test_options_change_reaches_running_client` (131-155) | exact (self, rewrite) |
| `tests/test_devices.py` | test | CRUD | itself: via_device assertion (242-251) | exact (unchanged assertion) |
| `tests/test_translations.py` | test | — | itself: `_flatten` (62-70), `_placeholders` (78-79), parity test (112-118) | exact (self) |
| `tests/test_entity_manager.py` (grace from options) | test | event-driven | itself | exact (self) |
| `tests/test_cert_coordinator.py`, `tests/test_cert_entity_state.py` (drop threshold setter/getter tests) | test | — | themselves (1069-1090; `test_cert_entity_state.py` 230, 336, 354) | exact (self) |
| `tests/test_coordinator.py` (translation keys, redirect) | test | — | itself | exact (self) |
| `tests/test_diagnostics.py` (NEW) | test | transform | `tests/test_init.py` setup style + RESEARCH "Code Examples (tests)" | role-match |
| `tests/test_repairs.py` (NEW, optional; or in `test_init.py`) | test | event-driven | `tests/test_migration.py` `_get_issue`/`_own_issues` helpers (51-57) + removal test (223-248) | role-match |

## Pattern Assignments

### `config_flow.py` (controller, request-response) — rewrite

**Analog:** itself.

**Imports to change** (lines 32-50): replace the try/except shim with `import probatio as vol`; add `from homeassistant import data_entry_flow`, `OptionsFlowWithReload`, `CONF_USERNAME/CONF_PASSWORD/CONF_TOKEN` from `homeassistant.const`, `SelectSelector*`, `NumberSelector*`. Drop `cv` once the YAML step and `cv.boolean` options fields are gone.
```python
try:
    import probatio as vol
except ImportError:  # HA releases before 2026.9 ship voluptuous only
    import voluptuous as vol  # type: ignore[no-redef]
```

**Keep: sentinel exceptions + error-mapping core** (lines 121-135, 161-195). Add `Redirect` sentinel; catch `TraefikProxyRedirectError` **before** `TraefikProxyApiError` (Pitfall 6). `InvalidUrl` raised without args (IN-09):
```python
    try:
        async with asyncio.timeout(10):
            await client.async_get_version()
    except TraefikProxyAuthError:
        raise InvalidAuth from None
    except TraefikProxyNotFoundError:
        raise ApiDisabled from None
    except TraefikProxyInvalidUrlError:
        raise InvalidUrl(data[CONF_URL]) from None   # -> raise InvalidUrl from None
    except TraefikProxyApiError, TimeoutError:
        raise CannotConnect from None
```
Auth `ValueError` → `InvalidAuth` (lines 174-178) stays; per D-12 it becomes a field error.

**`_check_url_shape`** (lines 141-158): drop `allow_userinfo`; wrap in `try/except ValueError: raise InvalidUrl from None` (IN-10); userinfo now raises a distinct `UrlHasCredentials` (→ `url_has_credentials`, W28).

**Repeated error dispatch** appears 4× (lines 286-293, 319-326, 373-380, 436-443) — collapse into one helper (e.g. `_async_probe(...) -> dict[str, str]` returning `errors`) that adds `Redirect → "redirect"` and a final `except Exception: _LOGGER.exception(...); errors["base"]="unknown"` (do not log `user_input`):
```python
            try:
                await _validate_input(self.hass, user_input)
            except InvalidUrl:
                errors["base"] = "invalid_url"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except ApiDisabled:
                errors["base"] = "api_disabled"
            except CannotConnect:
                errors["base"] = "cannot_connect"
```

**User step unique_id** (lines 295-302) → `host:port` + title = host (D-20):
```python
                host = urlparse(user_input[CONF_URL]).hostname or user_input[CONF_URL]
                await self.async_set_unique_id(host)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=DEFAULT_NAME, data=user_input)
```
The `host:port` helper must be shared with the migration (place in `config_flow.py` or a small module; Claude's discretion). Store only 1.3 keys (`url`, `verify_ssl`, `auth_type`, plus mode credentials) — build data explicitly, never `data=user_input`.

**Reconfigure abort-before-probe** (lines 423-426) — keep shape, compare against `host:port`, run `_check_url_shape` first:
```python
            host = urlparse(user_input[CONF_URL]).hostname or user_input[CONF_URL]
            for other in self._async_current_entries(include_ignore=False):
                if other.entry_id != entry.entry_id and other.unique_id == host:
                    return self.async_abort(reason="already_configured")
```
**"Empty secret keeps stored"** (line 427) generalises to: same `auth_type` + empty password/token → keep stored; changed type → `required`:
```python
            api_key = user_input.get(CONF_API_KEY) or entry.data.get(CONF_API_KEY, "")
```
**Finish** (lines 445-453): switch `data_updates=` → `data=` + `unique_id=` + `title=` (D-21, RESEARCH Pattern 3). Reauth (lines 381-387) currently does manual `async_update_entry` + `async_reload` + `async_abort(reason="reauth_successful")` → replace with `async_update_reload_and_abort(entry, data=new_data)` (no `reason=`, D-08).

**Defaults pre-fill** (lines 455-469): keep "URL + effective verify_ssl pre-filled, secrets never". Add `auth_type` default = stored value.

**Options flow** (lines 198-259): class base `OptionsFlow` → `OptionsFlowWithReload`; delete `STEP_OPTIONS_SCHEMA` (104-118) and the `vol.Invalid` / `scan_interval_out_of_range` branch (229-243); keep the "defaults from current options" dict (222-227) and `effective_verify_ssl` for verify_ssl; add `per_item_entities` (`DEFAULT_PER_ITEM_ENTITIES`) and `missing_grace_hours`; `int(...)` coercion in the step (RESEARCH Pattern 2). `async_get_options_flow` (268-278) unchanged in shape; docstring loses the listener wording.

**Delete:** `STEP_YAML_DATA_SCHEMA` (94-102), `async_step_yaml` (310-339), module docstring references to YAML / listener (1-23). `MINOR_VERSION = 2` → `3` (line 266).

**Form pattern:** RESEARCH Pattern 1 (`_auth_fields(default_auth)` with `data_entry_flow.Optional(..., visible=...)`) reused by user, reauth_confirm and reconfigure.

---

### `__init__.py` (setup/migration, event-driven)

**Analog:** itself.

**Migration block structure to copy for `< 3`** (lines 93, 146, 158-163) — guarded block, ends with `async_update_entry(..., minor_version=N)` and a debug log without secrets:
```python
    if entry.minor_version < 2:
        ...
        hass.config_entries.async_update_entry(entry, minor_version=2)
```
New `< 3` block: `async_update_entry(entry, data=new_data, minor_version=3, unique_id=..., title=...)`; pre-check `hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, uid)` (Pitfall 5) and WARNING that names `entry.entry_id`/title only.

**Repair creation** (lines 147-157) — add `config_entry_id=entry.entry_id`; same call shape for `insecure_credentials` (RESEARCH Pattern 5, non-persistent):
```python
            ir.async_create_issue(
                hass,
                DOMAIN,
                _issue_id(entry.entry_id),
                is_fixable=False,
                is_persistent=True,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_ENTITIES_MIGRATED,
                translation_placeholders={"entry_title": entry.title, "removed_count": str(removed)},
            )
```
Issue-id helper pattern (lines 63-64) — copy for `insecure_credentials_<entry_id>`.

**Downgrade branch** (lines 84-91): unreachable (R-4); delete or `raise ConfigEntryError(translation_domain=DOMAIN, translation_key="downgrade")`. Signature `-> bool` per D-06 (keeps `return True` at the end, line 165) — note RESEARCH R-4 recommends `None`; D-06 locks `bool` for migrate.

**Delete:** `_async_options_updated` (168-205) and `entry.async_on_unload(entry.add_update_listener(...))` (275-279); imports `timedelta`, `CONF_SCAN_INTERVAL`, `CONF_TLS_WARN_DAYS`, defaults, `build_api_client` usage there.

**Setup ordering to keep** (lines 237-273); append repair block after platform forward; `async_on_unload` pattern already used (line 273):
```python
    entry.async_on_unload(async_track_sw_version(hass, entry, main.id))
```
`build_api_client(hass, entry)` (line 237) is where `ConfigEntryError(invalid_url)` / `ConfigEntryAuthFailed(invalid_credentials)` surface (D-15) — wrap there or inside `build_api_client`.

**Unload** (line 296) → `await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)`, `-> None`. **Remove** (lines 299-306): drop `ir.async_delete_issue`, keep `async_remove_missing_store`.

---

### `coordinator.py` (service, polling)

**Analog:** itself.

**Single auth mapping point** (lines 437-447) — rewrite for 1.3 keys, keep it the only `Auth` construction:
```python
def auth_from_entry_data(data: Mapping[str, Any]) -> Auth:
    token = data.get(CONF_API_KEY)
    if isinstance(token, str) and token:
        return Auth(mode=AuthMode.bearer, token=token)
    return Auth()
```
→ `Auth(mode=AuthMode(data.get(CONF_AUTH_TYPE, "none")), username=data.get(CONF_USERNAME), password=..., token=...)`.

**Error blocks to translate** (three identical sites, 514-517, 543-546, 561-566, plus 567-568):
```python
        except TraefikProxyAuthError as err:
            raise ConfigEntryAuthFailed from err
        except TraefikProxyApiError as err:
            raise UpdateFailed(str(err)) from err
```
→ insert `except TraefikProxyRedirectError` before the generic branch; every raise gets `translation_domain=DOMAIN, translation_key=...` (placeholders: `err.path`, `err.status` only). Consider a module helper so the three sites stay identical.

---

### `cert_coordinator.py` (service, batch)

**Analog:** itself.

- Threshold read (257-260): literal `"tls_warn_days"` → `CONF_TLS_WARN_DAYS`.
- `UpdateFailed(f"Reading certificates failed: {err}")` (304) and `UpdateFailed("The Traefik URL has no host ...")` (351) → translated kwargs.
- D-07: set `self._stopping = True` first in `async_shutdown` (487-492); replace `if self._shutdown_requested:` (471) with `if self._stopping:`; init `self._stopping = False` in `__init__`.
```python
    async def async_shutdown(self) -> None:
        """Cancel the day-boundary timer, then shut the coordinator down."""
        if self._unsub_day_boundary is not None:
            self._unsub_day_boundary()
            self._unsub_day_boundary = None
        await super().async_shutdown()
```
- Delete `async_set_threshold` (494-497), `get_threshold` (535-537) and the class-docstring paragraph at 220-222.

---

### `api.py` (client, request-response)

**Analog:** itself.

New class follows the taxonomy (lines 126-131); subclass of `TraefikProxyConnectionError` (D-23):
```python
class TraefikProxyInvalidUrlError(TraefikProxyConnectionError):
    """aiohttp rejected the configured URL or refused to build the request for it."""
```
`_status_error` (138-145): add `if 300 <= status < 400: return TraefikProxyRedirectError(path, detail, status=status)` before the generic return. Detail stays `"HTTP <status>"` — never the Location header (message contract, lines 107-110).
`_request` (187-192): add `allow_redirects=False` to `self._session.get(...)`. Check any other `session.get/post` sites in the file get the same.
Also delete the "older Home Assistant releases" comment justification at 94-96 if it argues by 2026.3 (D-01 comment sweep).

---

### `entity.py` (registry helper, device CRUD)

**Analog:** `async_setup_devices` (lines 100-143). Change only the sub-device call: add `via_device_id=main.id` (RESEARCH Pattern 4) and delete:
```python
        if sub.via_device_id != main.id:
            device_registry.async_update_device(sub.id, via_device_id=main.id)
```
Update docstring lines 106-108 ("the one linking API available on every supported Home Assistant version"). `traefik_device_info` (44-50) already uses keyword `DeviceInfo(identifiers=...)` — no change.

---

### `entity_manager.py` (registry helper, event-driven)

**Analog:** option reader pattern (lines 93-95):
```python
def per_item_entities_enabled(entry: TraefikProxyConfigEntry) -> bool:
    return bool(entry.options.get(CONF_PER_ITEM_ENTITIES, DEFAULT_PER_ITEM_ENTITIES))
```
Add `missing_grace_period(entry) -> timedelta` the same way; store on `self._grace` in `__init__` (lines 169-178) and replace `MISSING_GRACE_PERIOD` at 254, 333, 349 and in the module docstring (14).

---

### `const.py` (config)

Copy the `CONF_PER_ITEM_ENTITIES` / `DEFAULT_…` pair and the `MIN_/MAX_` clamp block style:
```python
CONF_PER_ITEM_ENTITIES: Final = "per_item_entities"
DEFAULT_PER_ITEM_ENTITIES: Final = True
...
MIN_SCAN_INTERVAL: Final = 15
MAX_SCAN_INTERVAL: Final = 300
```
Add `CONF_AUTH_TYPE = "auth_type"`, `CONF_MISSING_GRACE_HOURS`, `DEFAULT_/MIN_/MAX_MISSING_GRACE_HOURS` (24/1/168). Delete `MISSING_GRACE_PERIOD` and `VERSION` (D-29). Keep `CONF_API_KEY` (migration + diagnostics only). Use `homeassistant.const` for username/password/token.

---

### `diagnostics.py` (NEW, transform) — no in-repo analog

Use RESEARCH Pattern 6. Data sources:
- `entry.runtime_data` fields (`data.py` 27-30): `client` (paginated mode flag `_paginated`, api.py 179 — prefer adding a public property over reading a private attr), `coordinator` (`data: TraefikSnapshot`, `last_update_success`, `update_interval`), `cert_coordinator` (`data: dict[str, HostCertState]`, `update_interval`), `entity_manager` (missing-since map; add a read accessor — `_kinds[...].missing` is private).
- `HostCertState` fields (cert_coordinator 152-160) → `dataclasses.asdict` + ISO datetimes.
- Typed entry alias `TraefikProxyConfigEntry` (data.py 33), module header style `from __future__ import annotations` like every module.

---

### Translations (`translations/en.json`, `de.json`; delete `strings.json`)

Current non-entity keys (en): `config.step.{user,yaml,reauth_confirm,reconfigure}`, `config.error.{cannot_connect,invalid_url,invalid_auth,api_disabled,unknown}`, `config.abort.{already_configured,reauth_successful}`, `options.step.init.data.{scan_interval,verify_ssl,tls_warn_days}`, `options.error.scan_interval_out_of_range`, `exceptions.cert_unavailable`, `device.*`, `issues.entities_migrated`.
- Remove: `config.step.yaml`, all `api_key` field keys, `config.abort.reauth_successful`, `options.error.scan_interval_out_of_range`, `exceptions.cert_unavailable`.
- Add: `auth_type/username/password/token` in `data` + `data_description` for user/reauth_confirm/reconfigure; `config.error.{url_has_credentials,redirect,required}`; options `per_item_entities`, `missing_grace_hours` (+ `data_description` for every option); `selector.auth_type.options.{none,basic,bearer}`; `exceptions.*` keys used by D-15/D-25; `issues.insecure_credentials` (`{entry_title}`).
- Pitfall 3: every `data_description` key must also exist under `data`.

---

### `.github/workflows/validate.yml` (CI)

**Analog:** its `test` job (lines 35-48): same `actions/checkout@v6`, `astral-sh/setup-uv@v5`, `uv python install 3.14`. Job body verbatim from RESEARCH R-1 "CI job (D-03)".

### `pyproject.toml` / `uv.lock` / `hacs.json`

- `pyproject.toml` line 16: `pytest-homeassistant-custom-component>=0.13.345` → `pytest-homeassistant>=2026.11.0`; line 24 `addopts` gains `-p no:respx` (leave the wrong `--cov=custom_components.traefik` path for Phase 8).
- `hacs.json`: `"homeassistant": "2026.3.0"` → `"2026.11.0"`.
- `uv lock` after the edit (checkpoint:human-verify before it — SUS package verdict).

---

### Tests

**`tests/conftest.py`** — line 25 import rename (`pytest_homeassistant_custom_component.common` → `pytest_homeassistant.common`); delete autouse `enable_custom_integrations` (322-326) and any `pytest_plugins` line. `make_traefik_entry` (224-234) default data becomes 1.3 and default `minor_version=3`; tests that need a legacy entry pass `data=`/`minor_version=` explicitly (already supported via `**kwargs`):
```python
    params: dict[str, Any] = {
        "domain": DOMAIN,
        "title": "Traefik",
        "data": {CONF_URL: MOCK_URL, CONF_API_KEY: "k", CONF_VERIFY_SSL: True},
        "unique_id": "traefik.example.com",
        "options": options or {},
    }
```
Note: every test that builds an entry at default minor_version would otherwise run the `< 3` migration; decide default deliberately.

**`tests/test_reconfigure.py`** — flow-driving template (139-161): `entry.start_reconfigure_flow(hass)` → `hass.config_entries.flow.async_configure(...)` → assert abort and no request to the other URL. `_probe_auth` (47-57) is the reusable header-assertion helper for basic/bearer probes.

**`tests/test_config_flow.py`** — drop imports `STEP_YAML_DATA_SCHEMA`, YAML tests (414-426), `allow_userinfo` test (195), userinfo-reauth tests (374-412). Add visible-marker and hidden-field stripping tests per RESEARCH "Code Examples (tests)". Coverage gate: RESEARCH Validation Architecture.

**`tests/test_verify_ssl.py`** — `test_options_change_reaches_running_client` (131-155) asserts `entry.runtime_data is runtime` (no reload); invert: after options change + `await hass.async_block_till_done()` a **new** runtime exists with the new client. Options payload must include the new fields. `test_reauth_probe_uses_effective_value` (158-173) payload changes to `{CONF_AUTH_TYPE: "bearer", CONF_TOKEN: "new"}`; `reason == "reauth_successful"` still holds (central domain).

**`tests/test_init.py`** — `test_update_listener_registered_once_across_reloads` (147-165) becomes "no update listener; options change reloads; unchanged options do not". Spy pattern to reuse:
```python
    with patch("custom_components.traefik_proxy.build_api_client", wraps=build_api_client) as spy:
        hass.config_entries.async_update_entry(entry, options={CONF_SCAN_INTERVAL: 45})
        await hass.async_block_till_done()
```

**`tests/test_migration.py`** — `test_issue_survives_reload_and_is_deleted_on_remove` (223-248) stays green unchanged (now proves HA cleanup). Direct-call idiom (276-298) `assert await integration.async_migrate_entry(hass, entry)` stays valid while migrate returns `bool`. New 1.2→1.3 tests copy `make_traefik_entry(entry_id=ENTRY_ID, version=1, minor_version=2, data=...)` + `setup_traefik_entry` (or direct call).

**`tests/test_repairs.py` (NEW)** — copy `_get_issue` / `_own_issues` helpers (test_migration 51-57) and the unload/remove sequence (223-248); use `make_traefik_entry(data={CONF_URL: "http://…", CONF_AUTH_TYPE: "bearer", CONF_TOKEN: "t", ...})`.

**`tests/test_diagnostics.py` (NEW)** — `setup_traefik_entry(hass, aioclient_mock, entry)` + `from pytest_homeassistant.components.diagnostics import get_diagnostics_for_config_entry` (needs `hass_client` fixture), then JSON-dump secret assertion (RESEARCH Code Examples).

**`tests/test_translations.py`** — delete `test_strings_json_equals_en_json` (107-109) and the `STRINGS` constant; widen `test_de_matches_en_keys_and_placeholders` (112-118) from `_phase_strings` (section-limited) to `_flatten(_load(...))` of the whole file; add `data_description ⊆ data` per step. Placeholder helper already exists (78-79).

**`tests/test_cert_coordinator.py`** — delete `test_get_threshold_returns_current_value` (1087-) and `test_async_set_threshold_mutates_and_notifies_listeners` (1069-1085). **`tests/test_cert_entity_state.py`** lines 230, 336, 354 call `async_set_threshold` — rewrite to set `options={CONF_TLS_WARN_DAYS: n}` + reload (or construct the coordinator with `threshold_days=`).

**`tests/test_devices.py`** — assertion at 242-251 stays; only import rename.

## Shared Patterns

### Translated HA exceptions
**Apply to:** `coordinator.py`, `cert_coordinator.py`, `__init__.py`.
```python
raise UpdateFailed(translation_domain=DOMAIN, translation_key="redirect",
                   translation_placeholders={"path": err.path}) from err
```
Never `str(err)` (current sites: coordinator 517, 546, 566, 568; cert_coordinator 304, 351). Every key gets `exceptions.<key>.message` in en + de.

### No secrets in messages / logs
**Source:** `api.py` 104-115 message contract (`"<path>: <detail>"`), `Auth` repr exclusion (62-65).
**Apply to:** migration WARNINGs, `_LOGGER.exception` in the `unknown` branch, `TraefikProxyRedirectError`, diagnostics.

### Option readers
**Source:** `entity_manager.py:93-95`, `coordinator.py:426-434` (`effective_verify_ssl`).
**Apply to:** grace hours, tls_warn_days, scan_interval, per_item — read once at setup (reload applies changes).

### `entry.async_on_unload` for teardown
**Source:** `__init__.py:273`, `entity_manager.py` `async_load` timer.
**Apply to:** `insecure_credentials` delete on unload.

### Test entry factory + setup
**Source:** `tests/conftest.py:224-254` (`make_traefik_entry`, `setup_traefik_entry`, `stub_traefik`).
**Apply to:** every new integration test (repairs, diagnostics, options reload, migration 1.3).

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `diagnostics.py` | platform utility | transform | No diagnostics platform in this repo (or the referenced gatus repo path); use RESEARCH Pattern 6 |
| `tests/test_diagnostics.py` | test | transform | No diagnostics test yet; use RESEARCH Code Examples + conftest setup helpers |

## Metadata

**Analog search scope:** `custom_components/traefik_proxy/`, `tests/`, `.github/workflows/`, `pyproject.toml`, `hacs.json`, `.planning/phases/06-certificates/06-PATTERNS.md` (style)
**Files scanned:** 22
**Pattern extraction date:** 2026-11-15
