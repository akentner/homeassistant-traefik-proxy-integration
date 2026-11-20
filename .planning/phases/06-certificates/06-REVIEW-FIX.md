---
phase: 06-certificates
fixed_at: 2026-11-15T10:30:00Z
review_path: .planning/phases/06-certificates/06-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 6: Code Review Fix Report

**Fixed at:** 2026-11-15T10:30:00Z
**Source review:** .planning/phases/06-certificates/06-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (fix scope `critical_warning`: CR-01, WR-01..WR-04)
- Fixed: 5
- Skipped: 0
- Out of scope, still open in REVIEW.md: IN-01..IN-04 (Info)

Each fix was written test-first: the new test failed on the old code, then passed with the fix. Test and fix share one commit, because D-19 forbids red intermediate commits.

## Fixed Issues

### CR-01: Probe mode reports Traefik's default certificate as healthy

**Files modified:** `custom_components/traefik_proxy/cert_coordinator.py`, `custom_components/traefik_proxy/binary_sensor.py`, `tests/test_cert_coordinator.py`
**Commit:** 78763cd
**Status:** fixed: requires human verification (problem semantics changed)
**Applied fix:**
- `HostCertState.problem()` now returns `not_found` when `error == NOT_FOUND` **or** `san_mismatch` is true. Precedence is unchanged: expired > probe_failed > not_found > expiring.
- The existing `not_found` reason is reused ("No certificate found" / "Kein Zertifikat gefunden"). The `CertProblem` set and the en/de translations stay unchanged, so the key-set test and strings.json == en.json still hold.
- This matches D-03/W47 for API mode: a host Traefik has no certificate for is a problem in both modes.
- New tests:
  - precedence cases with `san_mismatch`;
  - a real handshake against a local server that answers an unknown SNI with a self-signed "default" certificate valid for about a year. Result: `reason=not_found`, `is_problem` true.
- One existing history test now expects `not_found` after one failed probe, because the SAN mismatch of the last known certificate carries over.

**User-visible change (for the Phase 8 CHANGELOG):** on Traefik < 3.7, a host that is served a certificate that does not cover it is now `certificate_expiring` on with `reason=not_found`, and it is listed in `certificates_problem`.

### WR-01: `normalize_host` uses IDNA 2003, so `ß` domains get the wrong A-label

**Files modified:** `custom_components/traefik_proxy/rules.py`, `tests/test_rules.py`
**Commit:** b6e2da7
**Applied fix:**
- Non-ASCII hosts are now encoded with `idna.encode(host, uts46=True, transitional=False)` (IDNA 2008 / UTS-46 non-transitional). Errors are still caught as `UnicodeError`, which `idna.IDNAError` subclasses.
- `idna` 3.20 ships with HA through `yarl` and is present in both venvs. The manifest `requirements: []` is unchanged.
- The module docstring no longer claims "stdlib only".
- New cases:
  - `straße.de` / `Straße.de` become `xn--strae-oqa.de`, and `ς.example` becomes `xn--3xa.example`;
  - ZWJ and emoji labels are rejected.

### WR-02: A cert cycle running at unload re-arms the day-boundary timer and crashes on the deleted `runtime_data`

**Files modified:** `custom_components/traefik_proxy/cert_coordinator.py`, `tests/test_cert_coordinator.py`
**Commit:** 582fd92
**Status:** fixed: requires human verification (lifecycle/state handling)
**Applied fix:**
- `_async_schedule_day_boundary` returns without scheduling once `_shutdown_requested` is set. That attribute exists in HA 2026.3 and 2026.10.
- `_async_cycle` reads `runtime_data` (client and snapshot) only before its first await.
- `_probe_ports` is now a staticmethod that takes the snapshot, and `_async_probe_states` passes it on.
- New tests:
  - a cycle gated in the probe finishes after `async_shutdown()` and leaves no timer, and a due day-boundary callback does not re-arm it;
  - a 404 path in which `runtime_data` is deleted during the API call still probes on the port from the earlier snapshot.

### WR-03: `async_setup_entry` waits for the whole first cert cycle

**Files modified:** `custom_components/traefik_proxy/__init__.py`, `custom_components/traefik_proxy/entity.py`, `custom_components/traefik_proxy/entity_manager.py`, `tests/conftest.py`, `tests/test_cert_lifecycle.py`, `tests/test_cert_coordinator.py`, `tests/test_entity_manager.py`
**Commit:** 913bec9
**Status:** fixed: requires human verification (setup ordering, D-23)
**Applied fix:**
- The first cert cycle now runs as `entry.async_create_background_task(hass, cert_coordinator.async_refresh(), ...)`. It starts after the platforms are forwarded, and unload cancels it.
- `TraefikEntityManager.async_add_kind` treats `coordinator.data is None` like a failed cycle: orphans without a stored time are adopted as present and not marked missing.
- `TraefikCertCoordinatorEntity.available` now also requires `coordinator.data is not None`. Without that, the `certificates_problem` aggregate would show a false "off" while the first cycle runs.

**How D-23 still holds:**
- A failed first cycle leaves the cert entities unavailable.
- Registry-restored hosts are not marked missing.
- The entry never raises `ConfigEntryNotReady` because of certificates.
- The 5-minute retry is unchanged.
- The existing D-23 tests pass unchanged. Their setup helpers now wait with `async_block_till_done(wait_background_tasks=True)`.

**New tests:**
- setup with a probe that hangs on a gate finishes within 5 s on the wall clock. While the cycle runs, the restored host is unavailable and not missing, and the aggregate is unavailable. After the gate opens, real values appear and the aggregate turns "off";
- unload while the first cycle hangs cancels it and leaves no timer.

**User-visible change:** the integration and its main entities appear right away. Cert entities and the aggregate stay unavailable until the first cert cycle ends.

### WR-04: TLS tests under `freezer` hang instead of failing

**Files modified:** `tests/conftest.py`, `tests/test_tls.py`
**Commit:** fbcc346
**Applied fix:**
- New `wall_clock_watchdog(loop, seconds)` context manager. It uses a `threading.Timer`, which the frozen clock does not affect. When it fires, it cancels every task of the loop through `call_soon_threadsafe`.
- The `tls_server` fixture arms it for 60 s (`TLS_TEST_WALL_CLOCK_LIMIT`) and fails the test with a clear message when it fired.
- `TlsServer.wait_connections` is now bounded by wall-clock time (default 10 s) instead of 10 000 loop turns.
- No runtime or dev dependency was added (`pytest-timeout` was not added, so `uv.lock` and the min-HA venv are unchanged).
- New tests:
  - the watchdog cancels a hang under `freezer`;
  - the watchdog stays quiet when the block finishes in time;
  - `wait_connections` gives up after its limit.
- Checked once by hand with a throwaway test (deleted afterwards): a `tls_server` test hanging under `freezer` with a 0.5 s limit failed after 0.67 s with "test exceeded the tls_server wall-clock limit".

## Verification

All gates ran in the **main checkout of this worktree** (`/home/akentner/Projekte/_worktrees/homeassistant-traefik-proxy-integration/feat/marketplace-polish`, branch `feat/marketplace-polish`), after the last commit fbcc346.

- No nested review-fix worktree was created. The project rules pin all work to this worktree, and the user's CLAUDE.md allows worktrees only under `~/Projekte/_worktrees/` and only on request.
- Results reproduce from this tree.

| Gate | Result |
|------|--------|
| `uv run pytest -q` (HA 2026.10.4, Python 3.14) | 851 passed |
| `uv run ruff check custom_components tests` | All checks passed |
| `uv run ruff format --check custom_components tests` | 43 files already formatted |
| `uv run mypy --strict custom_components/traefik_proxy` | no issues in 15 source files |
| `~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests` (HA 2026.3.0) | 851 passed |

The full suite (worktree venv) was also run three times in a row after the WR-03 change: 847 passed each time, which was the count at that point.

The pre-existing uncommitted `.planning/config.json` change and the untracked `.planning/state.json` were left alone. Nothing was pushed or tagged.

---

_Fixed: 2026-11-15T10:30:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
