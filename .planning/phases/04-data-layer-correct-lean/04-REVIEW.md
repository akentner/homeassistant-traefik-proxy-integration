---
phase: 04-data-layer-correct-lean
reviewed: 2026-11-14T02:39:52Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - custom_components/traefik_proxy/api.py
  - custom_components/traefik_proxy/binary_sensor.py
  - custom_components/traefik_proxy/config_flow.py
  - custom_components/traefik_proxy/coordinator.py
  - custom_components/traefik_proxy/entity.py
  - custom_components/traefik_proxy/sensor.py
  - tests/test_api.py
  - tests/test_binary_sensor_tls_expiring.py
  - tests/test_cert_entity_state.py
  - tests/test_config_flow.py
  - tests/test_coordinator.py
  - tests/test_reconfigure.py
  - tests/test_sensor_tls.py
findings:
  critical: 0
  warning: 2
  info: 4
  total: 6
  necessity: 0
status: issues_found
---

# Phase 4: Code Review Report (gap closure 04-07..04-09)

**Reviewed:** 2026-11-14T02:39:52Z
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

Scope: `git diff b05c9e5..HEAD` (plans 04-07, 04-08, 04-09) plus the code it touches.

- **04-07:** cert entities moved onto the cert coordinator through a generic entity base.
- **04-08:** aiohttp's request-construction `ValueError` is mapped into the error taxonomy, and new URLs with userinfo are rejected.
- **04-09:** the paginated fallback can now be revoked through an hourly rawdata probe.

I read every changed file in full. I also traced `_TraefikProxyBaseEntity` → `CoordinatorEntity`, the cert coordinator's listener path, and the client ↔ coordinator probe arming. The gates pass: `ruff check`, `mypy` (13 files), and the 7 scoped test modules (204 passed).

**Status of the targeted findings from the previous review:**

| Finding | Status | Evidence |
|---|---|---|
| **CR-01** cert entities frozen after `always_update=False` | **Resolved** | `entity.py:120-136` binds `TraefikProxyCertEntity` to `CertCoordinator`. `sensor.py:410,464` and `binary_sensor.py:357,415` pass the cert coordinator to `super().__init__`. `_sw_version` (`entity.py:100-104`) still reads the main snapshot. `tests/test_cert_entity_state.py` proves HA-state propagation for a cert cycle, a threshold change, the `tls_warn_days` option, availability and listener count, with full setup. All pass. |
| **WR-01** sticky pagination after a transient 404 | **Resolved as scoped (not lifetime-sticky any more), with two residual gaps** | `api.py:262-322` plus `coordinator.py:135-171` re-probe rawdata on the hourly re-check. The two gaps are new findings **WR-09** and **WR-10** below. WR-09 is proven: one failed cycle every 50 min gave 0 probes in about 5 h. |
| **WR-02** aiohttp `ValueError` escapes the taxonomy | **Resolved** | `api.py:206-209` and `api.py:361-364` map it to `TraefikProxyInvalidUrlError`. `config_flow.py:141-158` rejects userinfo in the user and reconfigure steps. A real-session test (`test_api.py` `test_userinfo_url_with_bearer_token_raises_invalid_url_error`) and the setup-retry test without a traceback pass. Info-level residuals: IN-09, IN-11. |

**Prior findings that are still deferred** (per manager decision M28; not re-raised here):
- **WR-04:** pagination drift deletes registry entries. Deferred to Phase 5.
- **WR-05:** "does not generate unique IDs" ERROR on every cert notification. Deferred to Phase 5. Still observable, and 04-07-SUMMARY confirms it.
- **IN-01:** redirects drop the token. Deferred to Phase 7.
- **IN-04:** a stored token rejected by `Auth` fails setup instead of starting reauth. Deferred to Phase 7.

**Prior findings that are still open and untouched by 04-07..04-09** (not counted below; their disposition rows stay):
- **WR-03:** `__init__.py:260` still drops the update-listener remover, and `config_flow.py:445` still uses `async_update_reload_and_abort` with an update listener. Tracked as ROADMAP Phase 7 SC2. HA 2026.12.0, which turns the `report_usage` into a hard break, is due next month.
- **WR-06:** redundant outer timeout, `config_flow.py:186`.
- **WR-07:** `api.py:92,98`.
- **WR-08:** `cert_coordinator.py:212`.
- **IN-02**, **IN-03**, **IN-05**, **IN-06**.
- **IN-07:** 04-07 rewrote `entity.py` but left the empty `if TYPE_CHECKING: pass` at `entity.py:16-17` in place.

**Accepted trade-off, not a finding:** W20 / plan 04-08 decision table. A basicAuth-protected Traefik reached through URL credentials cannot be added or reconfigured until the Phase 7 basic-auth selector exists. If the basic password of an existing userinfo entry rotates, the user now has no path back short of the Phase 7 selector: reauth only edits the token, and reconfigure and re-add both refuse userinfo. Phase 7 should carry this explicitly.

New finding IDs continue after the previous review's numbering (WR-09+, IN-08+) so that the deferred disposition rows for WR-04, WR-05, IN-01 and IN-04 are not overwritten by reused IDs.

Necessity review: rubric read from `~/.claude/gsd-core/references/necessity-review.md`. None of the new code qualifies. The guard `_version_checked_at is None` in `_recheck_interval_elapsed` narrows a `datetime | None` type, and `_check_url_shape` sits on a trust boundary.

## Narrative Findings (AI reviewer)

## Warnings

### WR-09: The rawdata probe can be starved indefinitely: every post-failure version re-check resets its clock

**File:** `custom_components/traefik_proxy/coordinator.py:135-139,159-160,164-171`
**Issue:** The probe is armed only when `_recheck_interval_elapsed()` is true, measured from `_version_checked_at`. That timestamp is also refreshed by the post-failure version re-check that `_version_due()` forces on the first cycle after any failed cycle (`coordinator.py:131`, then `:159-160`). So every failed cycle pushes the next probe a full hour past the recovery. The matrix shows this by design: row (10b) re-checks, and row (12) needs another full `VERSION_RECHECK_INTERVAL` (`tests/test_coordinator.py:414-431`).

If at least one cycle fails per hour, the client never probes and stays paginated forever. That is the WR-01 symptom again: about 4× the requests per cycle, plus exposure to the page-shift problem WR-04. Paginated mode itself makes failures more likely: three sequential endpoints with 10 s timeouts each, and a 400/500 on a page when the config changes between reads (WR-04).

Reproduced with a scratch test on an isolated copy of the suite: client paginated, rawdata healthy again, one failing page every 50 min, then a healthy cycle.
```
probes over ~5h: 0 paginated: True
```
Neither the SUMMARY claim "switches back at the next hourly version check" nor the coordinator docstring ("the hourly re-check also retries /api/rawdata once") holds under recurring failures.
**Fix:** Give the probe its own clock, independent of the version re-check timing. For example, in the coordinator:
```python
self._probe_checked_at: datetime | None = None  # __init__

def _probe_due(self) -> bool:
    last = self._probe_checked_at or self._version_checked_at
    return last is not None and dt_util.utcnow() - last >= VERSION_RECHECK_INTERVAL

# _async_update_data, independent of _version_due():
if self._probe_due():
    self.client.request_rawdata_probe()
    self._probe_checked_at = dt_util.utcnow()
```
Alternatively, the client can stamp `_paginated_since` itself and probe once that is an hour old. Either way, `_probe_checked_at` must only advance when a probe was actually armed. Add a matrix row: a failure inside the hour followed by recovery must still probe at `paginated_since + 1h`.

### WR-10: The switch to pagination is committed even when the page reads fail in the same cycle (outage-wide 404)

**File:** `custom_components/traefik_proxy/api.py:311-322`
**Issue:** On a rawdata 404, `self._paginated = True` is set *before* `_get_state_paginated()` runs. When the pages also fail, the mode stays switched even though the fallback never produced a state. `tests/test_api.py` `test_list_endpoint_404_in_paginated_mode_raises_not_found` shows this case: rawdata 404, routers 404. The pages can fail the same way: 404 on everything during a Traefik restart while the API router is not loaded yet, or connection drops.

This is exactly the restart window that WR-01 described. Together with WR-09 it is guaranteed, not a possibility:
1. The failed cycle is followed by a post-failure version re-check, which resets the probe clock.
2. Every Traefik restart where one poll lands in the 404 window therefore costs at least one hour of paginated reads after recovery, and longer if WR-09 starvation applies.

This conflicts with the CLAUDE.md constraint "API polling must not exceed one call-set per scan interval". The fallback is only justified once the pages are known to work.
**Fix:** Commit the switch only after the pages succeed:
```python
if not self._paginated:
    try:
        payload, _ = await self._request(_RAWDATA_PATH)
    except TraefikProxyNotFoundError:
        _LOGGER.debug("path=%s not found, trying the paginated list endpoints", _RAWDATA_PATH)
        state = await self._get_state_paginated()   # raises -> mode unchanged
        self._paginated = True
        return state
    ...
```
Add a test: rawdata 404 plus routers 404 leaves `client._paginated is False`, and the next call requests `/api/rawdata` first.

## Info

### IN-08: Request-construction errors on a stored entry retry setup forever with an unactionable reason

**File:** `custom_components/traefik_proxy/api.py:206-209`, `custom_components/traefik_proxy/coordinator.py:120-123`
**Issue:** The 04-08 mapping makes `TraefikProxyInvalidUrlError` a `TraefikProxyConnectionError`, so a stored entry with a userinfo URL plus a token ends in `UpdateFailed` and then `ConfigEntryNotReady`. HA then retries with backoff indefinitely. That is the intended "quiet retry", but the failure is permanent: the stored data can never succeed without user action. The only reason the user sees is `/api/version: ValueError`, which does not point to the URL credentials or to the reconfigure flow. This was a deliberate decision in the 04-08 key-decisions, recorded here so Phase 7 can revisit it together with IN-04.
**Fix:** In `_async_setup`, map `TraefikProxyInvalidUrlError` to `ConfigEntryError` with a translation key such as `url_has_credentials`, so the entry shows a clear, non-retrying error that tells the user what to do. Alternatively, keep the retry and use a descriptive `UpdateFailed` translation key.

### IN-09: `InvalidUrl` now routinely carries a credential-bearing URL in its exception args

**File:** `custom_components/traefik_proxy/config_flow.py:156,158,193`
**Issue:** `_check_url_shape` raises `InvalidUrl(url)`, and `_validate_input` raises `InvalidUrl(data[CONF_URL])`. Since 04-08, rejecting URLs *because* they contain `user:pass@` is the main purpose of this exception, so the password now sits in `exc.args[0]`. Every current call site catches `InvalidUrl` and logs nothing, so this does not leak today. It is still a latent leak: a future step that forgets the `except InvalidUrl`, or a debug log of the exception, would print the password. This conflicts with the project rule "API tokens never logged" and with the client's own design, whose errors carry only a path and a type name.
**Fix:** Raise without the URL: `raise InvalidUrl from None` (or `InvalidUrl("url rejected")`). No caller reads the argument.

### IN-10: `_check_url_shape` lets `urlparse`'s `ValueError` escape (pre-existing, function changed in 04-08)

**File:** `custom_components/traefik_proxy/config_flow.py:154`, `custom_components/traefik_proxy/config_flow.py:423`
**Issue:** `urlparse("http://[::1")` raises `ValueError: Invalid IPv6 URL` (verified on the project venv's Python 3.14). `_check_url_shape` does not catch it, although its docstring promises `InvalidUrl` for malformed input. The user step therefore aborts with HA's generic "Unknown error" and logs a traceback. The reconfigure step calls `urlparse(user_input[CONF_URL]).hostname` (`:423`) before `_validate_input`, so it crashes the same way. The pattern is pre-existing, but 04-08 extended this function and its contract.
**Fix:**
```python
try:
    parsed = urlparse(url)
except ValueError:
    raise InvalidUrl from None
```
In `async_step_reconfigure`, run `_check_url_shape` before computing `host`, or wrap the host extraction the same way.

### IN-11: Cert entities keep a redundant `_coordinator` alias of `self.coordinator`

**File:** `custom_components/traefik_proxy/sensor.py:466`, `custom_components/traefik_proxy/binary_sensor.py:417`
**Issue:** After 04-07, `self.coordinator` (from `CoordinatorEntity`) and `self._coordinator` are the same `CertCoordinator`, and `tests/test_sensor_tls.py:347-348` asserts both. Every property still reads `self._coordinator`. Keeping two names for one binding invites the CR-01 class of bug again: a future refactor that rebinds one name but not the other would make listening and reading diverge.
**Fix:** Drop `self._coordinator` and read `self.coordinator` (now typed `CertCoordinator` through the generic base) in `native_value`, `is_on`, `available` and `extra_state_attributes`. Adjust the tests that assert `_coordinator`.

---

_Reviewed: 2026-11-14T02:39:52Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
