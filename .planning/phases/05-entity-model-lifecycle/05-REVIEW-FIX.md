---
phase: 05-entity-model-lifecycle
fixed_at: 2026-11-14T23:12:30Z
review_path: .planning/phases/05-entity-model-lifecycle/05-REVIEW.md
iteration: 1
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 5: Code Review Fix Report

**Fixed at:** 2026-11-14T23:12:30Z
**Source review:** .planning/phases/05-entity-model-lifecycle/05-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 2. Scope was set by the orchestrator: CR-02, plus IN-05, because IN-05 is in the same migration code.
- Fixed: 2
- Skipped: 0
- Already resolved before this run: CR-01, WR-01, WR-02.
- Out of scope, untouched: IN-01, IN-02, IN-03, IN-04, IN-06.

Both fixes followed TDD. First came a RED commit with `xfail(strict=True)` tests, confirmed failing with `--runxfail` on behaviour assertions. Then came the GREEN commit, which removes the markers. Every commit is green on both venvs.

## Fixed Issues

### CR-02: Entities the user disabled through a 0.3.0 device are re-enabled by the next update of their new device

**Status:** fixed: requires human verification (registry state-handling logic; covered by the tests below)
**Files modified:** `custom_components/traefik_proxy/__init__.py`, `custom_components/traefik_proxy/entity.py`, `tests/test_migration.py`
**Commits:** `4e1aee1` (RED tests), `80e1902` (fix)
**Applied fix:**
- New `entity.async_legacy_devices(hass, entry)`. It returns this entry's 0.3.0 per-category devices.
  - It finds them only through `dr.async_entries_for_config_entry`.
  - A device counts when it carries exactly one `(DOMAIN, f"{entry_id}_{suffix}")` identifier from `LEGACY_DEVICE_SUFFIXES` and none of the current identifiers.
  - `async_remove_legacy_devices` now uses the same helper. Its behaviour is unchanged, and there is still only one definition of "legacy device".
- In `async_migrate_entry` (the 1.1→1.2 block), a new step runs after the removal loop and before the router replacements are pre-created.
  - It re-reads `er.async_entries_for_config_entry(registry, entry.entry_id)`, so removed router binary sensors are skipped.
  - It changes `disabled_by=DEVICE` to `USER` for every entry whose `device_id` is one of those legacy devices.
- What the step never does:
  - It never touches other entries' entities or devices.
  - It never re-enables anything.
  - It never renames or re-IDs an entity.
- It is idempotent: a second run finds no `DEVICE` entries on legacy devices.
- Docstring and comment updated.

**Regression tests (`tests/test_migration.py`):**
- `test_device_disabled_entities_stay_disabled_after_device_updates` covers the end-to-end case through setup.
  - Setup: a service sensor, the routers aggregate and a cert entity, each `DEVICE`-disabled on a user-disabled legacy device (`http_services`, `diagnostics`, `http_routers_tls`).
  - After setup, all three are `USER`-disabled, have no state, and are re-pointed to Services, main and Certificates. The three legacy devices are gone.
  - Then a Traefik version change runs (`3.7.99`, `VERSION_RECHECK_INTERVAL` tick plus a refresh), so `async_track_sw_version` updates the main device. The Services and Certificates devices are renamed too.
  - All three stay `USER`-disabled without state.
  - RED on the old code: `AssertionError: service`, `DEVICE is not USER`.
- `test_device_disabled_mapping_is_scoped_and_idempotent` calls `async_migrate_entry` directly, twice. These entries keep `DEVICE`:
  - an entity of this entry on a disabled device with the current main identifier (an install older than 0.3.0);
  - a second config entry's entity on this entry's legacy device;
  - a second config entry's entity on that entry's own legacy device.
  - Only this entry's service sensor on its legacy device becomes `USER`.
  - The second run leaves the registry entries of both entries unchanged. The other entry stays at minor version 1, and no issue is raised because nothing was removed.
  - RED on the old code: the service sensor stayed `DEVICE`.
- The test helper `_disabled_legacy_routers_device` became `_disabled_legacy_device(hass, entry, suffix="http_routers")`. Its two existing call sites behave the same. New helpers: `_device` and `_entries`.

### IN-05: The migration keeps "disabled" but drops "hidden" for router sensors

**Status:** fixed: requires human verification (registry state-handling logic; covered by the tests below)
**Files modified:** `custom_components/traefik_proxy/__init__.py`, `tests/test_migration.py`
**Commits:** `c71cf6c` (RED test), `5ea22e5` (fix)
**Applied fix:**
- The migration now pre-creates a replacement for a router binary sensor when it has a mapped `disabled_by` or any `hidden_by`.
  - The replacement gets the same unique_id, the mapped `disabled_by` (or `None`), the old `hidden_by` and the old object id.
  - `hidden_by` carries over unchanged: `USER` stays `USER`, `INTEGRATION` stays `INTEGRATION`.
  - This also applies to enabled routers.
- In HA 2026.3, `async_get_or_create` on an existing entry never touches `hidden_by` (`entity_registry.py:1120-1137`). So when the platform adds the router, the replacement keeps its hidden flag and is moved to the Routers sub-device.
- Updated: the replacement tuple type, the comments, the docstring and the debug log line ("disabled or hidden routers re-created"). The log line still contains counts only.

**Regression test:** `tests/test_migration.py::test_hidden_router_replacement_stays_hidden`, with three cases: `enabled-user`, `disabled-user` and `enabled-integration`.
- The replacement is `sensor.traefik_http_router_file_ok_file`, keeps `hidden_by`, keeps the disabled state, and sits on the Routers sub-device.
- It has a state only when it is enabled.
- A visible enabled router next to it still gets the platform's new-style id, with `hidden_by=None`.
- `removed_count` is 2.
- RED on the old code: the enabled cases got the platform id (no pre-created entry), and `disabled-user` had `hidden_by=None`.

## Decisions not covered by the review or the decisions file

| Decision | Reason | Alternative |
|---|---|---|
| Fixes were made directly in the existing `feat/marketplace-polish` worktree, without a nested `.claude/worktrees/rf-*` worktree. | Binding executor rules: sequential executor on this branch, no further worktrees. The user's CLAUDE.md allows worktrees only under `~/Projekte/_worktrees/…`. The gates need the root `.venv`. This is the same path the 04 fixer took. | Nested worktree with a fast-forward merge. That conflicts with the rules and has no venv. |
| The CR-02 step uses the same legacy-device predicate as the cleanup (exactly one legacy identifier, no current identifier), through a new shared `async_legacy_devices` helper. | One definition of "legacy device" for both the mapping and the removal. A disabled device that carries the current main identifier is left alone, because HA correctly clears `DEVICE` there when the user re-enables it. | The reviewer's looser `device.identifiers & legacy_identifiers`. It behaves the same on every real 0.3.0 registry. |
| An enabled router that is hidden is now pre-created with the old object id, like a disabled one. | "The same way `disabled_by` is carried" (orchestrator). The only other way to keep the flag is to pre-create the entry. Without `suggested_object_id`, HA would generate `sensor.traefik_proxy_<unique_id>`, which is worse than the old id. | Pre-create without an object id (bad id), or carry the flag only for disabled routers (leaves IN-05 half open). |
| `hidden_by=INTEGRATION` is carried over unchanged. | The orchestrator asked for INTEGRATION to be carried "as the review suggests". 0.3.0 never set `entity_registry_visible_default`, so this case cannot occur from 0.3.0 code, and the choice changes nothing in practice. | Map INTEGRATION to `None` (visible). |
| The new DEVICE→USER step runs before the router replacements are pre-created. | Replacements are created without a `device_id`, so the order does not matter. Running the step first keeps it limited to entries that already existed. | Run it after the replacements. Same result. |

**Interaction with IN-06 (left open):** hidden enabled routers now also keep the old object id under `sensor.`. The repair text "Router binary sensors were replaced by router sensors with new entity IDs" is therefore inaccurate for hidden routers as well as disabled ones. If IN-06 is fixed by dropping `suggested_object_id`, both cases change together.

## Verification

All gates ran in the main checkout (the `feat/marketplace-polish` worktree root), not in an isolated worktree, so you can reproduce them from this tree:

- `uv run pytest -q`: 577 passed (572 before: 2 CR-02 tests and 3 IN-05 cases added)
- `~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`: 577 passed
- `uv run ruff check custom_components tests`: all checks passed
- `uv run ruff format --check custom_components tests`: 38 files already formatted
- `uv run mypy --strict custom_components/traefik_proxy`: no issues in 14 source files
- Guards:
  - `grep -rn xfail tests/` finds nothing.
  - Planning references in `__init__.py` / `entity.py`: still 4 / 0, none added.
  - No HA API newer than 2026.3.0 is used: `async_get_or_create(hidden_by=…)`, `dr.async_entries_for_config_entry` and `er.async_entries_for_config_entry` all exist in 2026.3.0.
- The root pin (`pin.sh`) passed before the first edit and before each of the 4 commits.

I did not touch IN-01..IN-04, IN-06, REQUIREMENTS.md, ROADMAP.md or STATE.md. The uncommitted change to `.planning/config.json` and the untracked `.planning/state.json` were already there before this run. This fixer did not create them and did not commit them.

---

_Fixed: 2026-11-14T23:12:30Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
