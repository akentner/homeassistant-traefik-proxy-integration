---
phase: 06-certificates
reviewed: 2026-11-15T09:27:36Z
depth: standard
files_reviewed: 30
files_reviewed_list:
  - custom_components/traefik_proxy/__init__.py
  - custom_components/traefik_proxy/api.py
  - custom_components/traefik_proxy/binary_sensor.py
  - custom_components/traefik_proxy/cert_coordinator.py
  - custom_components/traefik_proxy/const.py
  - custom_components/traefik_proxy/entity.py
  - custom_components/traefik_proxy/entity_manager.py
  - custom_components/traefik_proxy/icons.json
  - custom_components/traefik_proxy/models.py
  - custom_components/traefik_proxy/rules.py
  - custom_components/traefik_proxy/sensor.py
  - custom_components/traefik_proxy/strings.json
  - custom_components/traefik_proxy/tls.py
  - custom_components/traefik_proxy/translations/de.json
  - custom_components/traefik_proxy/translations/en.json
  - tests/certgen.py
  - tests/conftest.py
  - tests/test_api.py
  - tests/test_binary_sensor_tls_expiring.py
  - tests/test_cert_coordinator.py
  - tests/test_cert_entity_state.py
  - tests/test_cert_lifecycle.py
  - tests/test_certificates_problem.py
  - tests/test_coordinator.py
  - tests/test_entity_manager.py
  - tests/test_models.py
  - tests/test_rules.py
  - tests/test_sensor_tls.py
  - tests/test_tls.py
  - tests/test_translations.py
findings:
  critical: 1
  warning: 4
  info: 4
  total: 9
  necessity: 0
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-11-15T09:27:36Z
**Depth:** standard
**Files Reviewed:** 30
**Status:** issues_found

## Summary

Scope: the phase-06 diff (`git diff 5e6c4f7..HEAD`). Production code under `custom_components/traefik_proxy/` came first. Test files were checked only for test-infrastructure reliability (timers, freezer, sockets). Every finding was checked against the binding decision log (`~/.cache/traefik-proxy-integration/decisions.md`, M19, W45–W54) and `06-CONTEXT.md` D-01..D-24. None of the findings below contradicts a logged decision. The suite was run once on the worktree venv (Python 3.14.10, HA 2026.10.4): 831 passed in 25.8 s.

What holds up:
- Error classification order is correct (SSLError and ConnectionRefusedError are checked before OSError).
- CancelledError is never swallowed, and the writer is closed on every path.
- The trust store is built only from memory.
- API error messages carry no URL or credential.
- The cap warning logs counts only.
- The day-count arithmetic is correct: `next_day_change` is always at least `now + 1 s`, and the floor semantics fit the `days < 0` expiry rule.
- The entity manager's "failed cycle adopts orphans as present" change matches D-23.
- The handshake itself uses no thread. `getaddrinfo` for the connect host still goes through the loop's default executor (IN-03).

Main concerns:
- **CR-01:** in probe mode (every Traefik < 3.7), a host Traefik has no certificate for is reported healthy. This is the exact failure the phase designed against for API mode (R-1/W47).
- **WR-01:** IDNA 2003 encoding produces the wrong A-label for German `ß` domains.
- **WR-02:** a cert cycle still running at unload re-arms the day-boundary timer on a dead coordinator. After `runtime_data` is deleted, the same cycle also crashes with an AttributeError.
- **WR-03:** setup waits for the complete probe cycle. Worst case is about 500 s.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Probe mode reports Traefik's default certificate as healthy (`san_mismatch` never makes a problem)

**File:** `custom_components/traefik_proxy/cert_coordinator.py:177-188` (with `tls.py:204-209`)
**Issue:** On Traefik < 3.7 (v2.11 and v3.0–v3.6, the probe path), a router host that Traefik holds no certificate for is served the store's default certificate during the SNI handshake. That covers an ACME order that never succeeded, a typo in `tls.domains`, a missing file-provider cert, or a disabled router. Traefik only refuses the handshake when `sniStrict` is set, and it is off by default. The default certificate is the generated `TRAEFIK DEFAULT CERT` (self-signed, about 365 days) or a user default certificate.

The probe parses that certificate and correctly sets `san_mismatch=True` (`tls.py:208`). `HostCertState.problem()` never reads `san_mismatch`, so:
- `days_left` is about 365, so no `expired` and no `expiring`;
- `failures == 0`, so no `probe_failed`;
- `error is None`, so no `not_found`.

`certificate_expiring` is therefore **off** and `certificates_problem` does not list the host. The timestamp sensor shows a plausible date about a year ahead.

Research R-1 and D-03/W47 name exactly this failure as the reason to report uncovered hosts as `not_found` in API mode ("Probing such a host would therefore report a self-signed certificate valid for about a year with 'expiring = off', which hides a broken host"). Probe mode reaches the same situation and hides it. For users of the probe path, this undermines the project's core value: seeing at a glance which certificates are failing.

`verified=False` alone cannot be the signal, because private-CA and self-signed setups are legitimately unverified. `san_mismatch` is the precise signal.

**Fix:** Treat a probed certificate that does not cover the host as a problem. Reusing `not_found` keeps the existing reason set and translations:
```python
def problem(self, threshold_days: int, now: datetime) -> CertProblem | None:
    days = self.days_left(now)
    if days is not None and days < 0:
        return CertProblem.EXPIRED
    if self.failures >= CERT_FAILURES_FOR_PROBLEM:
        return CertProblem.PROBE_FAILED
    # API: no covering certificate; probe: Traefik served a certificate that does not cover the host
    # (its default certificate), which is the same condition.
    if self.error == NOT_FOUND or self.san_mismatch:
        return CertProblem.NOT_FOUND
    if days is not None and days <= threshold_days:
        return CertProblem.EXPIRING
    return None
```
You could add a dedicated `CertProblem.SAN_MISMATCH` with en/de `state_attributes` texts instead. Add a probe-mode test in which the served certificate does not cover the SNI host and assert `reason=not_found` and aggregate on. If this behaviour is intended, record it as a decision and in the CHANGELOG notes, because it is asymmetric to W47.

## Warnings

### WR-01: `normalize_host` uses IDNA 2003, so `ß` domains get the wrong A-label

**File:** `custom_components/traefik_proxy/rules.py:65`
**Issue:** `host.encode("idna")` is Python's built-in IDNA **2003** codec. It maps deviation characters instead of encoding them. Verified on the project venv:
- `normalize_host("straße.de")` returns `strasse.de`.
- IDNA 2008 / UTS-46 non-transitional, which browsers, Go's `idna` package and ACME clients such as lego use, gives `xn--strae-oqa.de`.

The same applies to `ς` and ZWJ/ZWNJ. Results for such a host:
- **API mode:** the certificate carries the 2008 A-label, `match_certificate` finds nothing, and the host is a false `not_found` problem.
- **Probe mode:** SNI `strasse.de` reaches no router, Traefik answers with its default certificate, and the host looks healthy (see CR-01).

The entity's unique_id and name also carry the wrong host. This matters especially for a German user base.
**Fix:** Encode with UTS-46 non-transitional through the `idna` package. HA already ships it as a dependency of `yarl` (`idna>=2.0`), so `requirements: []` stays:
```python
import idna

if not host.isascii():
    try:
        host = idna.encode(host, uts46=True, transitional=False).decode("ascii")
    except idna.IDNAError:
        return None
```
Add `straße.de -> xn--strae-oqa.de` to `tests/test_rules.py`.

### WR-02: A cert cycle still running at unload re-arms the day-boundary timer forever and crashes on the deleted `runtime_data`

**File:** `custom_components/traefik_proxy/cert_coordinator.py:274-275, 358, 443-463, 465-470`
**Issue:** `async_shutdown()` cancels `_unsub_day_boundary`. It does not cancel a cycle that is already running: HA's `DataUpdateCoordinator.async_shutdown` only sets `_shutdown_requested` and unschedules. A probe cycle can run for minutes (`TLS_SEMAPHORE=4`, up to 200 hosts, up to 5 s handshake plus 5 s close each), so an unload or reload during a cycle is realistic, for example through the reconfigure or reauth flow. Two things then go wrong:
1. When the running `_async_update_data` finishes, it calls `_async_schedule_day_boundary(states)` (line 275) after shutdown. The new timer fires on a dead coordinator, and `_async_handle_day_boundary` reschedules itself every day (line 463). It keeps the old coordinator, entry, client and snapshot alive until HA restarts. Each reload during a cycle adds one more such timer chain.
2. HA deletes `entry.runtime_data` after a successful unload (`config_entries.py:1138-1139`). On the 404 path, `_probe_ports` (line 358) runs after the `await async_get_certificates()` and reads `self.config_entry.runtime_data.coordinator.data`. That raises `AttributeError`, and the coordinator logs it as "Unexpected error fetching ... certs data" at ERROR level.

**Fix:** Do not schedule after shutdown, and read the snapshot before the first await:
```python
@callback
def _async_schedule_day_boundary(self, states: dict[str, HostCertState]) -> None:
    if self._unsub_day_boundary is not None:
        self._unsub_day_boundary()
        self._unsub_day_boundary = None
    if self._shutdown_requested:
        return
    ...
```
In `_async_cycle`, capture `snapshot = self.config_entry.runtime_data.coordinator.data` together with the hosts, before the `await`. Pass it to `_probe_ports`, so the cycle never touches `runtime_data` after a suspension point.

### WR-03: `async_setup_entry` waits for the whole first cert cycle, up to about 500 s in probe mode

**File:** `custom_components/traefik_proxy/__init__.py:251`
**Issue:** `await cert_coordinator.async_refresh()` runs a complete probe cycle before the entity manager loads, before the platforms are forwarded and before any entity exists. Each probe is bounded by `handshake_timeout` for the connection and again for the close (`tls.py:243-252`), so one host can take up to 10 s. With 200 hosts and 4 concurrent probes, an unreachable or filtered TLS port on the connect host gives 50 × 10 s, about 500 s. A filtered port happens easily, for example when the entry URL points at an internal API address whose 443 is firewalled, or when the entrypoint `:443` is published on a different host port.

During that time:
- the integration and all main entities are missing;
- HA warns that setup is taking a long time, and bootstrap stage 2 times out and moves on;
- the main coordinator is already polling, but nothing shows it.

This is not a new pattern (the previous code awaited `async_config_entry_first_refresh`), but phase 6 rewrote this exact block and kept the blocking await.
**Fix:** Run the first cert cycle in the background and treat "no data yet" like a failed cycle:
- `entry.async_create_background_task(hass, cert_coordinator.async_refresh(), "traefik_proxy first cert cycle")`;
- in `TraefikEntityManager.async_add_kind`, compute `failed = not coordinator.last_update_success or coordinator.data is None`, because before the first refresh `last_update_success` is still `True`;
- keep the D-23 semantics: orphans are adopted as present, nothing is stamped missing, and the cert entities become available when the cycle finishes.

### WR-04: TLS tests under `freezer` hang instead of failing; no per-test timeout is configured

**File:** `tests/conftest.py:353-363` (also `tests/test_tls.py:264-470`, `tests/test_cert_coordinator.py:408-456, 705-763`)
**Issue:** Many real-handshake tests take the `freezer` fixture. As the conftest docstring at 355-358 notes, the loop clock is frozen there, so `asyncio.timeout(handshake_timeout)` in `async_probe_certificate` and in `_close_writer` never expires. If the local `tls_server` stalls (a handshake regression, a server-side exception in `_handle`, a CI scheduling hiccup), the test hangs indefinitely rather than failing. `pyproject.toml [tool.pytest.ini_options]` has no `timeout`, and `pytest-timeout` is not configured. `wait_connections` is a busy loop of 10 000 `asyncio.sleep(0)` with no wall-clock bound. That count is fine locally but is not an upper bound in time on a loaded CI runner.
**Fix:** Add `pytest-timeout` to the dev dependencies with `timeout = 60` (thread method) in `[tool.pytest.ini_options]`. Alternatively, freeze only `dt_util.utcnow` for these tests rather than the loop clock, for example by moving the clock just before the assertion and passing `now=` explicitly. The probe API already takes `now`, so most of these tests need no frozen loop at all.

## Info

### IN-01: `CertCoordinator.get_threshold()` is dead in production

**File:** `custom_components/traefik_proxy/cert_coordinator.py:513-515`
**Issue:** No production caller exists (`grep` finds only `tests/test_cert_coordinator.py`). Production code reads `threshold_days` directly (`binary_sensor.py:163, 205, 211`).
**Fix:** Remove it and its test, or use it consistently.

### IN-02: Magic string `"tls_warn_days"` instead of `CONF_TLS_WARN_DAYS`

**File:** `custom_components/traefik_proxy/cert_coordinator.py:251`
**Issue:** `entry.options.get("tls_warn_days", ...)` duplicates the key that `const.CONF_TLS_WARN_DAYS` defines and that `__init__.py:203` uses. A rename in Phase 7's options work would silently break the initial threshold.
**Fix:** Import and use `CONF_TLS_WARN_DAYS`.

### IN-03: The connect host is resolved once per probe through the default executor

**File:** `custom_components/traefik_proxy/tls.py:244`
**Issue:** `asyncio.open_connection(connect_host, ...)` calls `loop.getaddrinfo` for every probe, up to 200 per cycle, and asyncio runs that in the default thread pool. The event loop is not blocked, but D-07's "no executor" is not literally met. With round-robin DNS for the Traefik host, probes in one cycle may also reach different Traefik instances.
**Fix:** Resolve `connect_host` once per cycle in `_async_probe_states` (`await loop.getaddrinfo(connect_host, None, type=socket.SOCK_STREAM)`, or skip this for IP literals) and pass the address to every probe, with SNI unchanged.

### IN-04: Small races in socket tests

**File:** `tests/test_tls.py:549-559, 666-684`; `tests/test_cert_coordinator.py:783-818`
**Issue:**
- `test_probe_closed_port_is_refused` binds a port, closes it, then connects. Another process may take the port in between, which would make the test flaky.
- The cancellation tests wait with a fixed `asyncio.sleep(0.2)` for the connection to be accepted. If accept takes longer on a slow runner, `server.eof` / `eof` never fires and the 1 s guard fails the test.

**Fix:** Keep the listening socket bound without `listen()` (connect is then refused deterministically on Linux). In the cancellation tests, set an `asyncio.Event` when the server accepts and cancel only after awaiting it.

---

_Reviewed: 2026-11-15T09:27:36Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
