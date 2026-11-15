# Phase 8: Marketplace + release readiness - Pattern Map

**Mapped:** 2026-11-15
**Files analyzed:** 16 (code/tooling; docs/brand files follow RESEARCH.md recipes)
**Analogs found:** 14 / 16

Package path is `custom_components/traefik_proxy/` (not `traefik`).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `.github/workflows/validate.yml` (mod) | config/CI | batch | itself (lines 1-80) + RESEARCH §"validate.yml skeleton" (l.657) | exact |
| `.github/workflows/release.yml` (new) | config/CI | event-driven | `.github/workflows/validate.yml` | role-match |
| `.github/dependabot.yml` (new) | config | — | none in repo; RESEARCH l.729 | no analog |
| `.github/requirements-min-ha.txt` (new, generated) | config/lock | — | `uv.lock` (concept only) | partial |
| `scripts/hacs_action_local.py` (new) | utility/CLI | file-I/O | `scripts/hassfest_checks.py` | exact |
| `scripts/hassfest_checks.py` (mod) | utility/CLI | file-I/O | itself | exact |
| `Makefile` (mod) | config | batch | itself (`hassfest-sanity` target) | exact |
| `.pre-commit-config.yaml`, `pyproject.toml` (mod) | config | — | themselves | exact |
| `custom_components/traefik_proxy/diagnostics.py` (mod, D-17) | service | transform | itself: `_safe_url` (l.46-53) | exact |
| `custom_components/traefik_proxy/rules.py` (optional home for redactor) | utility | transform | `rules.py` `extract_hosts`/`_is_negated` (l.78-86) | exact |
| `custom_components/traefik_proxy/cert_coordinator.py` (mod, D-18/D-20) | service | request-response | `coordinator.py` `_logged_cause` (l.172-179) | exact |
| `custom_components/traefik_proxy/tls.py` (mod, D-20) | utility | request-response | itself `async_probe_certificate` (l.225-244) | exact |
| `custom_components/traefik_proxy/coordinator.py` (mod, IN-13) | service | polling | itself (l.182-185, 222-284) | exact |
| `tests/test_baseline_guards.py` (mod, D-16) | test | file-I/O | itself `_grep`/`_files` (l.55-81, 176-182) | exact |
| `tests/test_diagnostics.py` (mod, rule redaction tests) | test | transform | itself (imports l.1-25) | exact |
| `README.md`, `CHANGELOG.md`, `docs/`, brand PNGs | docs/assets | — | RESEARCH F8, F11 | no code analog |

## Pattern Assignments

### `scripts/hacs_action_local.py` (utility, file-I/O)
**Analog:** `scripts/hassfest_checks.py` lines 1-40. Copy: shebang + module docstring with usage block, `from __future__ import annotations`, `ROOT = Path(__file__).resolve().parent.parent`, `INTEGRATION = ROOT / "custom_components" / "traefik_proxy"`, subcommand via `sys.argv`, exit code 0 clean / 1 failure.
```python
#!/usr/bin/env python3
"""Local hassfest-style sanity checks.
...
Exit code 0 = clean, 1 = one or more checks failed.
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
INTEGRATION = ROOT / "custom_components" / "traefik_proxy"
```
Body: take verbatim from RESEARCH.md §"scripts/hacs_action_local.py" (l.534-625, verified). Wire into Makefile like `hassfest-sanity:` (`uv run python scripts/...`), using the `## help` comment convention.

### `.github/workflows/validate.yml` (CI)
Current state (lines 1-80): `permissions: {}`, jobs `lint`, `test`, `test-min-ha`, `hassfest`, `hacs`; floating tags `actions/checkout@v6`, `astral-sh/setup-uv@v5`, `hassfest@master`, `hacs/action@main`; no `timeout-minutes`.
Changes: SHA pins from RESEARCH §"Action pins" (l.295) with `# vX.Y.Z` comment; `timeout-minutes: 15` per job; add `schedule` + `workflow_dispatch`; replace lines 58-61 (`uv pip install "pytest-homeassistant==2026.11.0"`) with `uv pip sync .github/requirements-min-ha.txt` (RESEARCH F4 / P7). Keep line 63 invocation `-o addopts="-p no:respx"`. Skeleton: RESEARCH l.657-696.

### `.github/workflows/release.yml` (CI, event-driven)
**Analog:** `validate.yml` job shape (top-level `permissions: {}`, `runs-on: ubuntu-latest`, checkout step). Content: RESEARCH l.697-728 (tag minus `v` vs `manifest.json` version, fail on mismatch, no assets).

### `custom_components/traefik_proxy/diagnostics.py` (D-17)
**Analog:** `_safe_url` (lines 46-53) — fail-closed helper returning `REDACTED`:
```python
def _safe_url(url: Any) -> Any:
    """Return ``url`` without userinfo; a URL that cannot be parsed is redacted as a whole."""
    if not isinstance(url, str):
        return url
    try:
        return split_url_userinfo(url)[0]
    except ValueError:
        return REDACTED
```
Apply the new rule redactor where the snapshot is dumped (line 81: `_jsonable(dataclasses.asdict(snapshot))`) — walk router dicts and replace `rule`. `REDACTED` already imported (line 16). Redactor regex body: RESEARCH l.739-762 (16/16 verified). If placed in `rules.py`, follow its stdlib-`re` + `_private` helper style (`_is_negated`, l.78).

### `custom_components/traefik_proxy/cert_coordinator.py` (D-18, D-20)
**D-18 analog:** `coordinator.py` lines 172-179:
```python
def _logged_cause(err: TraefikProxyApiError) -> TraefikProxyApiError | None:
    return None if isinstance(err, TraefikProxyInvalidUrlError) else err
```
Target: `cert_coordinator.py` lines 307-313, change `) from err` to `) from _logged_cause(err)` (import from `.coordinator`, or move helper to a shared module).
**D-20:** `_connect_host()` (l.355) is already called once per cycle in `_async_probe_states` (l.407); DNS still happens per probe inside `asyncio.open_connection(connect_host, ...)` (`tls.py` l.244). Resolve once per cycle (e.g. `loop.getaddrinfo` in `_async_probe_states`) and pass the address down through `_async_probe_host` (l.420-426); keep `server_hostname=sni`.

### `custom_components/traefik_proxy/coordinator.py` (IN-13)
Current lines 182-185:
```python
def _interval_elapsed(since: datetime | None) -> bool:
    return since is not None and dt_util.utcnow() - since >= VERSION_RECHECK_INTERVAL
```
-> `_interval_elapsed(since, interval)`; add `RAWDATA_PROBE_INTERVAL = timedelta(hours=1)` in `const.py`; rename `_probe_armed_at` at lines 222, 234, 272, 278 to `_probe_clock`. Call sites: 247 (version), 272 (probe).

### `tests/test_baseline_guards.py` (D-16 full-tree guard)
**Analog:** `test_no_text_for_releases_before_the_minimum` (lines 176-182) + helpers `_files`/`_grep` (55-81):
```python
OLD_RELEASE = re.compile(rb"2026\.3")
def test_no_text_for_releases_before_the_minimum() -> None:
    hits = _grep(OLD_RELEASE, *_files(PACKAGE.parent, ROOT / "tests", ROOT / "scripts"))
    assert not hits, f"reference to Home Assistant 2026.3: {hits}"
```
New: module-level `PLANNING_REFS = re.compile(rb"CONTEXT\.md|PITFALLS|D-[0-9]|BLOCKER|Phase [0-9]|\.planning/|\.claude/|spike", re.IGNORECASE)`, scan `_files(PACKAGE)` only. Update module docstring (lines 1-14) to mention Phase 8. Guard file must not read `.planning/` (docstring l.12). Note: the guard itself contains these words, but it is excluded via `THIS_FILE` and scans only `PACKAGE`.

### `tests/test_diagnostics.py`
Imports pattern lines 1-25 (`from custom_components.traefik_proxy.diagnostics import _jsonable, _safe_url` — add the redactor import); parametrized unit tests for the 16 rule cases from RESEARCH, plus one integration assertion via `get_diagnostics_for_config_entry`.

## Shared Patterns
- **Fail closed:** unparseable input -> `REDACTED` (`diagnostics.py` l.46-53). Apply to rule redactor.
- **Exception chaining without secrets:** `raise UpdateFailed(translation_domain=DOMAIN, translation_key=..., translation_placeholders=...) from _logged_cause(err)` (`coordinator.py` l.237/264/282).
- **Script conventions:** `ROOT` from `__file__`, exit 0/1, invoked via `uv run python scripts/X.py` from a Makefile target with `## help` text.
- **CI:** `permissions: {}` top-level, `uv python install 3.14`, `uv sync`.

## No Analog Found
| File | Reason |
|---|---|
| `.github/dependabot.yml` | none exists; use RESEARCH l.729-738 |
| brand PNGs / docs / CHANGELOG | assets/docs; use RESEARCH F8, F11 and D-04..D-06 |

## Metadata
**Search scope:** `custom_components/traefik_proxy/`, `tests/`, `scripts/`, `.github/`, `Makefile`
**Files scanned:** ~12
