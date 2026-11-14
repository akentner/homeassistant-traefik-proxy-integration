---
phase: 04-data-layer-correct-lean
reviewed: 2026-11-14T01:25:13Z
depth: standard
files_reviewed: 30
files_reviewed_list:
  - custom_components/traefik_proxy/api.py
  - custom_components/traefik_proxy/models.py
  - custom_components/traefik_proxy/coordinator.py
  - custom_components/traefik_proxy/data.py
  - custom_components/traefik_proxy/__init__.py
  - custom_components/traefik_proxy/cert_coordinator.py
  - custom_components/traefik_proxy/config_flow.py
  - custom_components/traefik_proxy/entity.py
  - custom_components/traefik_proxy/sensor.py
  - custom_components/traefik_proxy/binary_sensor.py
  - custom_components/traefik_proxy/button.py
  - tests/conftest.py
  - tests/test_api.py
  - tests/test_api_pagination.py
  - tests/test_coordinator.py
  - tests/test_models.py
  - tests/test_platforms_real_fixtures.py
  - tests/test_fixture_redaction.py
  - tests/test_init.py
  - tests/test_config_flow.py
  - tests/test_sensor.py
  - tests/test_binary_sensor.py
  - tests/test_cert_coordinator.py
  - tests/test_sensor_tls.py
  - tests/test_verify_ssl.py
  - tests/test_reconfigure.py
  - tests/traefik/capture.py
  - tests/traefik/compose.yaml
  - tests/traefik/dynamic/scenario.yml
  - .gitignore
findings:
  critical: 1
  warning: 8
  info: 7
  total: 16
  necessity: 3
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-11-14T01:25:13Z
**Depth:** standard
**Files Reviewed:** 30
**Status:** issues_found

## Summary

I reviewed the Phase 4 data-layer rework (`git diff 1d41e87..HEAD`): the typed models, the snapshot coordinator, `/api/rawdata` with its paginated fallback, the `Auth` modes, the error taxonomy and the `TraefikRuntimeData` split. I read each file in full and checked it against the installed Home Assistant 2026.10.4 and aiohttp 3.14.5 sources in `.venv`. The models and the parser layer are solid: shape errors are wrapped, `@internal` items are filtered and the parsers are deterministic. The tests for the request budget, the error matrix and the pagination are thorough.

The most serious defect is a regression with a large impact. Phase 4 set `always_update=False` on the main coordinator. The TLS cert entities are still subscribed to the main coordinator instead of the cert coordinator. As a result, cert-cycle results and `tls_warn_days` changes no longer reach the HA state machine while the Traefik snapshot stays unchanged. An isolated scratch test confirmed this: after a cert cycle reported 3 days left, the entity stayed `off` with `days_until_expiry=30`. That breaks the project's core value ("which TLS certificates are expiring soon").

Other issues:
- The rawdata-to-pagination switch is sticky and can be triggered by a transient 404, for example while Traefik restarts.
- A `ValueError` from aiohttp escapes the error taxonomy.
- The update listener leaks across reloads. Confirmed: 1 listener became 2 after one reload. Combined with `async_update_reload_and_abort`, the reconfigure flow is scheduled to break in HA 2026.12.0.
- Pagination can silently drop items when the configuration changes between page reads.

Known or deferred items are marked as such: the reload service and button (Phase 5), entity creation for new items (Phase 5), and redirects (Phase 7/8).

Necessity review: rubric read from `~/.claude/gsd-core/references/necessity-review.md`. Three necessity findings.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Cert entities no longer update after a cert cycle or threshold change (regression from `always_update=False`)

**File:** `custom_components/traefik_proxy/coordinator.py:501`, `custom_components/traefik_proxy/entity.py:62`, `custom_components/traefik_proxy/sensor.py:410-471`, `custom_components/traefik_proxy/binary_sensor.py:357-422`, `custom_components/traefik_proxy/cert_coordinator.py:440-452`
**Issue:** `TraefikProxyCertTimestampSensor` and `TraefikProxyCertExpiryBinarySensor` inherit from `TraefikProxyEntity`. Its `__init__` calls `super().__init__(entry.runtime_data.coordinator)`, so they are `CoordinatorEntity` listeners of the **main** coordinator. They read `self._coordinator` (the cert coordinator) only inside their properties. The cert coordinator's only listeners are the create/cleanup closures (`sensor.py:146`, `binary_sensor.py:186`), and those never write entity state.

Before Phase 4, the main coordinator ran with the default `always_update=True`, so every 15 s cycle re-wrote the cert entities' state as a side effect. Phase 4 added `always_update=False` (`coordinator.py:501`). Now the main coordinator notifies listeners only when the snapshot changes. On a stable homelab that can be days or weeks. Consequences:
- A 6 h cert cycle that finds a cert inside the warning window does not flip `binary_sensor.traefik_<host>_expiring` to `on`.
- `days_until_expiry`, `not_after` and `available` stay frozen at the value from setup.
- `async_set_threshold` (`cert_coordinator.py:451-452`) calls `async_update_listeners()` on the cert coordinator, which reaches no entity. A `tls_warn_days` change from the Options flow is never reflected.

Verified with an isolated scratch test (full `async_setup` with `stub_traefik`, then `cert_coordinator.async_set_updated_data({"a.example.com": CertInfo(days_until_expiry=3)})`, then an unchanged main refresh and `async_set_threshold(60)`):
```
initial off 30
after cert cycle off 30
after unchanged main refresh off 30
after threshold 14
```
No existing test covers state propagation from the cert coordinator to the entity. `test_cert_coordinator.py:221` only asserts that `async_update_listeners` was called on a MagicMock.
**Fix:** Bind the cert entities to the cert coordinator. Let `TraefikProxyEntity` accept the coordinator to listen to:
```python
# entity.py
class TraefikProxyEntity(CoordinatorEntity[DataUpdateCoordinator[Any]]):
    def __init__(self, entry, category, *, description_key=None, coordinator=None) -> None:
        super().__init__(coordinator or entry.runtime_data.coordinator)
        ...
    def _sw_version(self) -> str | None:
        data = self._entry.runtime_data.coordinator.data
        return data.version.version if isinstance(data, TraefikSnapshot) else None

# sensor.py / binary_sensor.py (cert entities)
super().__init__(entry, category="http_routers_tls", description_key=host, coordinator=coordinator)
```
Alternatively, keep the base class and add `self.async_on_remove(self._coordinator.async_add_listener(self.async_write_ha_state))` in `async_added_to_hass` of both cert entity classes. Add an integration test that asserts the HA state changes after `cert_coordinator.async_set_updated_data(...)` and after `async_set_threshold(...)`.

## Warnings

### WR-01: A transient 404 on `/api/rawdata` switches the client to pagination for its whole lifetime

**File:** `custom_components/traefik_proxy/api.py:264-269`
**Issue:** `async_get_state` sets `self._paginated = True` on the first `TraefikProxyNotFoundError` from `/api/rawdata` and never probes rawdata again. `/api/rawdata` exists on every supported Traefik (v2.0+), so a 404 there almost always means the API router is not routable *at that moment*. A common case is a restart where the API is exposed through a dynamic router with `api.insecure=false`, exactly as in the project's own harness (`tests/traefik/dynamic/scenario.yml:106-112`): until the file or docker provider loads, Traefik answers its default 404 for every path. One poll landing in that window permanently triples the request count per cycle (routers + services + middlewares, plus extra pages), which breaks the "one call-set per scan interval" budget. It also exposes the cycle to the page-shift problem in WR-04, until HA restarts or the user saves the options (which rebuilds the client, `__init__.py:186`). The paginated endpoints themselves 404 in the same cycle, so the switch never even helped in that scenario.
**Fix:** Make the fallback decision only when the API is demonstrably up, and make it revocable. For example:
```python
except TraefikProxyNotFoundError:
    # Only fall back when the API itself answers; a 404 on everything is an outage.
    await self.async_get_version()          # raises NotFound/Connection -> propagate
    self._paginated = True
    self._paginated_since = time.monotonic()
...
# and re-probe rawdata periodically (e.g. on the coordinator's hourly version re-check)
if self._paginated and time.monotonic() - self._paginated_since > 3600:
    self._paginated = False
```
Add a test: rawdata 404 together with version 404 must not flip the mode.

### WR-02: aiohttp `ValueError` escapes the error taxonomy (URL with userinfo plus token)

**File:** `custom_components/traefik_proxy/api.py:182-203`, `custom_components/traefik_proxy/config_flow.py:141-151,173-183`
**Issue:** `_request` / `reload_routers` catch only `InvalidUrlClientError`, `ClientError`, `TimeoutError` and `OSError`. aiohttp raises a plain `ValueError` when credentials are encoded in the URL and an `Authorization` header is also passed. Verified against the bundled aiohttp 3.14.5: `ValueError: Cannot combine AUTHORIZATION header with AUTH argument or credentials encoded in URL`. `_check_url_shape` accepts `https://user:pass@traefik:8080` (it checks only scheme and netloc), so this is reachable from the UI:
- **Config flow:** `_validate_input` does not catch `ValueError`, so the flow aborts with "Unknown error" and a traceback.
- **Runtime:** `_async_setup` raises a bare `ValueError`. HA's `__wrap_async_setup` logs it via `logger.exception` and turns it into `ConfigEntryNotReady`, so the entry retries forever with a traceback each time.

This breaks the documented contract in `TraefikProxyApiError`: "Base class of every error the client raises."
**Fix:** Reject userinfo up front and map aiohttp's request-construction `ValueError` inside the network block:
```python
# config_flow._check_url_shape
if parsed.scheme not in _ALLOWED_URL_SCHEMES or not parsed.hostname or parsed.username or parsed.password:
    raise InvalidUrl(url)

# api._request / reload_routers, after the InvalidUrlClientError clause
except ValueError as err:  # aiohttp request-construction error (e.g. URL credentials + header)
    raise TraefikProxyInvalidUrlError(path, type(err).__name__) from err
```
JSON decoding stays outside the block as it is now, so the two `ValueError` sources stay distinct.

### WR-03: Update listener leaks across reloads; reconfigure plus update listener breaks in HA 2026.12.0

**File:** `custom_components/traefik_proxy/__init__.py:260,273-276`, `custom_components/traefik_proxy/config_flow.py:430-438`
**Issue:**
1. `entry.add_update_listener(_async_options_updated)` discards the returned remover. HA does not clear `entry.update_listeners` on unload: it is reset only in `ConfigEntry.__init__` (`.venv/.../config_entries.py:552`). The docstring at `__init__.py:273-274` ("HA removes the update listener automatically") is wrong. Verified: `len(entry.update_listeners)` went from 1 to 2 after one `async_reload`. Every reload (reauth, reconfigure, manual) adds another copy. Each options save then rebuilds the client N times, and a leaked listener can run against the dead `runtime_data` of a `SETUP_RETRY` entry.
2. `async_update_reload_and_abort` is called while the entry has an update listener. HA 2026.10 already logs `report_usage("has an update listener and should use it for scheduling a reload", breaks_in_ha_version="2026.12.0")` (`config_entries.py:3716-3722`), and the subentry variant already raises `ValueError("Cannot update and reload entry with update listeners")` (`config_entries.py:4016-4017`). The reconfigure flow is therefore expected to fail on the HA release due next month.

Both lines predate Phase 4, but Phase 4 rewrote both functions and kept the pattern.
**Fix:**
```python
# __init__.py
entry.async_on_unload(entry.add_update_listener(_async_options_updated))

# config_flow.py reconfigure: update without reload; let the listener schedule it
return self.async_update_and_abort(
    entry,
    data_updates={...},
    options={**entry.options, CONF_VERIFY_SSL: verify_ssl},
)

# __init__._async_options_updated: reload when connection data changed
if (entry.data[CONF_URL], entry.data.get(CONF_API_KEY)) != runtime.connection_key:
    hass.config_entries.async_schedule_reload(entry.entry_id)
    return
```
Alternatively, switch to `OptionsFlowWithReload` and drop the listener entirely.

### WR-04: Paginated reads can silently drop items, and the stale-entity cleanup then deletes their registry entries

**File:** `custom_components/traefik_proxy/api.py:212-236,277-288`; consumers `binary_sensor.py:91-111`, `sensor.py:154-183`
**Issue:** `_get_paginated` reads pages sequentially from a live, sorted list with no consistency check. If Traefik's dynamic configuration changes between two page requests (a docker container stops, or a file provider reload), items shift across the page boundary. One item is then skipped, or Traefik answers 400 for a page beyond the new end. The skipped case produces a "successful" snapshot that lacks an existing router or service. `_remove_stale_routers` / `_remove_stale_services` gate only on `last_update_success`, so they call `registry.async_remove(...)` for that item and the user's entity customisations are lost. Entities for items that reappear are not recreated until the entry reloads (entity creation stays setup-only until Phase 5). The three kinds are also read one after another (`_get_state_paginated`), so routers, services and middlewares can come from different config generations. The worst case is 3 × `MAX_PAGES` sequential requests at 10 s each with no overall cycle timeout.
**Fix:** At minimum, detect inconsistency and fail the cycle instead of publishing a partial set. For example, compare the `len(payload) < per_page` signal with `X-Next-Page` on every page, re-read page 1 at the end and require the first name to be unchanged, or (cheapest) treat any page-count change between consecutive cycles as `UpdateFailed` once. Also wrap the whole `async_get_state` in an overall `asyncio.timeout(...)` derived from the scan interval. Long term, rely on rawdata (see WR-01) and keep pagination as an exceptional path.

### WR-05: Every cert cycle and options save logs ERROR "does not generate unique IDs" per host and platform

**File:** `custom_components/traefik_proxy/sensor.py:65-104`, `custom_components/traefik_proxy/binary_sensor.py:118-143`
**Issue:** `_create_pending_cert_*` call `async_add_entities` for **every** cached host on every cert-coordinator notification. That includes the 6 h cycle and every `async_set_threshold` call, which uses `async_update_listeners`. HA does not replace an existing entity: `EntityPlatform` logs `ERROR ... Platform traefik_proxy does not generate unique IDs. ID ... is already used by ... - ignoring`, which was observed in the scratch run. The docstring claim (`sensor.py:77-86`) that `async_add_entities` "REPLACES the defunct instance" is false. This produces recurring ERROR-level log noise that users will report as a bug, and the "restore re-bind" problem it claims to solve is not solved this way. This predates Phase 4 but is in the reviewed files and interacts with CR-01.
**Fix:** Track the hosts this platform instance already added and add only new ones:
```python
added: set[str] = set()
def _create_pending_cert_sensor_entities() -> None:
    new = [TraefikProxyCertTimestampSensor(entry, cert_coordinator, h, i)
           for h, i in cache.items() if not is_error(i) and h.lower() not in added]
    added.update(e._host for e in new)
    if new:
        async_add_entities(new)
```
Restored entities re-bind automatically once the platform adds an entity with the same unique_id for the first time after the restart. Discard the host from `added` when stale cleanup removes it.

### WR-06: Already-defended-elsewhere: redundant 10 s timeout around the version probe

**File:** `custom_components/traefik_proxy/config_flow.py:173-175`
**Category:** necessity
**Issue:** `async with asyncio.timeout(10): await client.async_get_version()` wraps exactly one request. `TraefikProxyApiClient._request` already enforces `asyncio.timeout(self._request_timeout)` around it (`api.py:183`, default `request_timeout=10.0` at `api.py:166`) and converts the expiry into `TraefikProxyConnectionError`. The outer timeout cannot fire before the inner one. Its `TimeoutError` branch (`config_flow.py:182`) is effectively dead.
**Fix:** Drop the outer `asyncio.timeout(10)` and the `TimeoutError` in the except tuple, or pass `request_timeout=` explicitly if the flow needs a different budget.

### WR-07: Impossible-state guard: `Auth.header()` re-checks credentials that `__post_init__` guarantees

**File:** `custom_components/traefik_proxy/api.py:92,98`
**Category:** necessity
**Issue:** `Auth` is `frozen=True` (`api.py:53`). `__post_init__` raises when basic mode lacks a username or password, or bearer mode lacks a token (`api.py:68-78`). So `self.username and self.password` and `self.token` in `header()` are always truthy for their mode. The extra conditions can only make a malformed `Auth` silently send no header at all, which would turn a programming error into a confusing 401.
**Fix:** Branch on `self.mode` only. If a guard is wanted, use `assert self.token is not None` for mypy narrowing.

### WR-08: Impossible-state guard: `isinstance(match, str)` on single-group `findall` results

**File:** `custom_components/traefik_proxy/cert_coordinator.py:487-489`
**Category:** necessity
**Issue:** `_HOST_FROM_RULE` (`cert_coordinator.py:332`) has exactly one capture group, and `router.rule` is typed `str` and always a `str` after `models._str` (`models.py:255-257,308`). `re.findall` with one group always returns `list[str]`, so the `isinstance` check can never be false. `[^`]+` also guarantees non-empty matches, so `and match` is redundant as well.
**Fix:** `hosts.update(m.lower() for m in _HOST_FROM_RULE.findall(router.rule))`.

## Info

### IN-01: Redirects: http-to-https redirects drop the token and surface as `invalid_auth` / reauth (known open question, Phase 7/8)

**File:** `custom_components/traefik_proxy/api.py:184-189,303-307`
**Issue:** aiohttp follows redirects by default and strips `Authorization` whenever the origin changes, including a scheme change on the same host (`.venv/.../aiohttp/client.py:1028-1031`). A user who enters `http://traefik:8080` in front of a redirect-to-https middleware therefore gets 401 and sees "invalid_auth" in the config flow, or a reauth loop at runtime, even though the token is correct. The POST to `/api/http/routers/refresh` would also follow a 301/302 as GET. As noted in the brief, this is a known open question.
**Fix:** Pass `allow_redirects=False` and map 3xx to a dedicated error (for example a `redirect` translation key telling the user to enter the final URL).

### IN-02: Reload service verification loop is defeated by the refresh debouncer (deferred to Phase 5)

**File:** `custom_components/traefik_proxy/__init__.py:104-112`
**Issue:** `coordinator.async_request_refresh()` uses HA's debouncer (cooldown 10 s, `immediate=True`). Only the first call refreshes. Calls 2 to N inside the 5 s budget return immediately without refreshing, so the loop re-reads the same snapshot, and `verified` is effectively decided by the single refresh issued right after the POST. The handler also picks `runtimes[0]` arbitrarily when several entries are loaded. The service and button are slated for removal in Phase 5, so this is recorded only.
**Fix:** Phase 5 removal. If kept, call `await coordinator.async_refresh()` directly in the loop.

### IN-03: A quick Traefik restart is detected up to 1 h late; a failing `/api/version` takes down the whole cycle

**File:** `custom_components/traefik_proxy/coordinator.py:523-566`
**Issue:**
- **Late detection:** A restart that completes between two polls (shorter than the 15 s scan interval) produces no failed cycle. The new start date, the entrypoints and `sw_version` are only picked up at the next hourly re-check.
- **Version failure blocks the cycle:** When `/api/version` fails during a due re-check (hourly, or after any failed cycle), `_async_refresh_version` raises `UpdateFailed` before `/api/rawdata` is attempted. A persistent `/api/version` failure (for example an ACL change) keeps every entity unavailable, even though the state endpoint works.

Both are acceptable trade-offs but are not documented as such.
**Fix:** Document the trade-off in the class docstring. Optionally, if the version re-check fails with a non-auth error, log it, keep the previous version and still fetch the state.

### IN-04: A stored token the new `Auth` rejects fails setup instead of starting reauth

**File:** `custom_components/traefik_proxy/coordinator.py:451-471`, `custom_components/traefik_proxy/__init__.py:186,226`
**Issue:** `auth_from_entry_data` builds `Auth(mode=bearer, token=...)`, which now raises `ValueError` for control characters (`api.py:85-88`). The config flows guard this (`config_flow.py:162-166`), but entries stored before Phase 4 were never validated. A token with a stray tab from a paste worked before and now fails `async_setup_entry` with a raw traceback (`SETUP_ERROR`), or crashes the options listener, instead of starting the reauth flow that would fix it.
**Fix:** In `async_setup_entry`, wrap `build_api_client` with `except ValueError as err: raise ConfigEntryAuthFailed("stored credential is invalid") from err`. In the listener, log and keep the old client.

### IN-05: Reconfigure to a new host keeps the old `unique_id` (pre-existing)

**File:** `custom_components/traefik_proxy/config_flow.py:408-438`
**Issue:** The reconfigure flow checks other entries against the new host but never passes `unique_id=host` to `async_update_reload_and_abort`. After moving an entry from `a` to `b`, adding `b` again is not detected as a duplicate, while `a` is wrongly reported as `already_configured`.
**Fix:** Pass `unique_id=host` in the update call (together with the WR-03 change).

### IN-06: The capture script writes fixtures before checking them for secrets

**File:** `tests/traefik/capture.py:501-511`
**Issue:** `write_fixtures` writes every redacted file into the tracked `tests/fixtures/` tree, and only afterwards does `verify_no_secrets` scan them. On failure, the offending files stay on disk ready to be committed, and the script only prints a message. The credentials are harness-only, so the impact is low, but the guard is ordered backwards.
**Fix:** Redact into memory, run the forbidden-string check on the serialised text, then write. Or unlink the written files on failure.

### IN-07: Dead `TYPE_CHECKING` block; sequential paginated reads contradict the stated constraint

**File:** `custom_components/traefik_proxy/entity.py:15-16`, `custom_components/traefik_proxy/api.py:277-288`
**Issue:**
- `if TYPE_CHECKING: pass` in `entity.py` is a leftover with no effect.
- `_get_state_paginated` reads the three list endpoints sequentially, while CLAUDE.md requires "multiple endpoints fetched in parallel via `asyncio.gather`". This may be a deliberate request-budget decision, but it is not recorded in the code.
**Fix:**
- Delete the empty block in `entity.py`.
- Either gather the three `_get_paginated` calls or add a one-line rationale next to `_get_state_paginated`.

---

_Reviewed: 2026-11-14T01:25:13Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
