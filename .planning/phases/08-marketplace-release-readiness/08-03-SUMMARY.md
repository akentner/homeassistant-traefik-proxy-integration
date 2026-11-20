---
phase: 08-marketplace-release-readiness
plan: 03
subsystem: migration, entities, release-hygiene
tags: [config-entry-migration, repairs, entity-registry, translations, guard-tests, ast, syntaxwarning]

requires:
  - phase: 05-entity-model-lifecycle
    provides: 1.1 -> 1.2 migration, router replacements, entities_migrated repair (IN-01/IN-06/IN-07 carried)
  - phase: 07-config-flow-ha-2026-11-baseline-observability
    provides: 1.2 -> 1.3 migration (title = host), tests/test_baseline_guards.py helpers (IN-04/IN-05 carried)
provides:
  - entities_migrated repair raised after the last migration step with the final entry title
  - DEVICE -> USER mapping only for entities on disabled legacy devices (generic step and router replacements)
  - en/de entities_migrated text naming the kept IDs of disabled or hidden router sensors
  - cert host normalisation only in the cert coordinator (factory unique_id round-trips through KindSpec.key_of)
  - planning-reference, developer-doc-link, SyntaxWarning-compile and literal-sleep guard tests
affects: [08-06 pyproject/coverage, 08-09 visual check, 08-10 README, 08-11 CHANGELOG, 08-12 review dispositions]

actuals:
  tokens: 11186
  tasks: 3
  commits: 6
plan_head_before: 29342902f9d56b195283da2ca1877994a791d299
plan_head_after: 2ebebcbe6e1f6f97c6d71e3bcd8a2897381a158c

tech-stack:
  added: []
  patterns:
    - "Repair issues that carry the entry title are raised after the last migration step"
    - "Release-hygiene guards check themselves against planted samples (non-vacuous)"
    - "SyntaxWarning gate compiles sources with compile(), independent of .pyc caches"

key-files:
  created: []
  modified:
    - custom_components/traefik_proxy/__init__.py
    - custom_components/traefik_proxy/entity.py
    - custom_components/traefik_proxy/config_flow.py
    - custom_components/traefik_proxy/const.py
    - custom_components/traefik_proxy/translations/en.json
    - custom_components/traefik_proxy/translations/de.json
    - tests/test_migration.py
    - tests/test_entity_manager.py
    - tests/test_baseline_guards.py
    - tests/test_sensor_tls.py
    - tests/test_binary_sensor_tls_expiring.py

key-decisions:
  - "A stale DEVICE disabler is produced in tests through the registry's private _async_update_entity: HA 2026.11 derives DEVICE from the device state on every public write and on registry load"
  - "An existing entities_migrated issue follows a 1.2 -> 1.3 title change and keeps its removed_count; without an existing issue the title change raises none"
  - "The two tls test_host_is_lowercased tests were rewritten (they pinned the removed lowercasing)"
  - "The sleep guard also flags sleep(delay=N) and a bare imported sleep; the doc-link guard skips binary image suffixes"

patterns-established:
  - "Guard detectors as helpers (_planning_refs, _compile_strict, _long_sleeps) with an in-memory self-check in the same test file"

requirements-completed: [REL-06, REL-04]

coverage:
  - id: D1
    description: "Migration repair names the entry title after the last migration step (default title -> URL host, renamed title kept); an existing issue follows a 1.2 -> 1.3 title change"
    requirement: REL-06
    verification:
      - kind: unit
        ref: "tests/test_migration.py#test_migration_issue_names_title_after_migration"
        status: pass
      - kind: unit
        ref: "tests/test_migration.py#test_title_migration_updates_existing_issue"
        status: pass
    human_judgment: false
  - id: D2
    description: "DEVICE -> USER only for entities on disabled legacy devices; a stale DEVICE disabler on an enabled legacy device is not hardened (generic step) and not carried to the router replacement"
    verification:
      - kind: unit
        ref: "tests/test_migration.py#test_device_disabled_mapping_is_scoped_and_idempotent"
        status: pass
      - kind: integration
        ref: "tests/test_migration.py#test_disabled_router_replacement_keeps_disabled_state[device-on-enabled-device]"
        status: pass
    human_judgment: false
  - id: D3
    description: "en/de entities_migrated text says enabled, visible router sensors got new IDs while disabled or hidden ones keep their previous ID under the sensor domain"
    verification:
      - kind: unit
        ref: "tests/test_translations.py (placeholder parity)"
        status: pass
    human_judgment: true
    rationale: "Wording and rendering of the repair text in the HA UI are checked in the visual check (08-09)"
  - id: D4
    description: "Cert hosts normalised only in the cert coordinator; factory-built cert unique_ids round-trip through KindSpec.key_of; cert_hosts returns the data keys unchanged"
    verification:
      - kind: unit
        ref: "tests/test_entity_manager.py#test_cert_factory_unique_id_round_trips_through_key_of"
        status: pass
      - kind: unit
        ref: "tests/test_cert_coordinator.py#test_collect_hosts_lowercases_for_dedup"
        status: pass
    human_judgment: false
  - id: D5
    description: "Defence branches (migration auth-type branch, config-flow re-validation branches) documented, no behaviour change"
    verification:
      - kind: unit
        ref: "tests/test_migration.py#test_migration_1_2_keeps_existing_auth_type"
        status: pass
      - kind: unit
        ref: "tests/test_config_flow.py"
        status: pass
    human_judgment: false
  - id: D6
    description: "No planning references in shipped .py/.json; guard tests for planning references, developer-doc links, SyntaxWarning on compile and literal sleeps >= 1 s, each non-vacuous"
    requirement: REL-04
    verification:
      - kind: unit
        ref: "tests/test_baseline_guards.py#test_shipped_code_has_no_planning_references"
        status: pass
      - kind: unit
        ref: "tests/test_baseline_guards.py#test_planning_reference_detector_is_not_vacuous"
        status: pass
      - kind: unit
        ref: "tests/test_baseline_guards.py#test_developer_doc_links_point_at_contributors"
        status: pass
      - kind: unit
        ref: "tests/test_baseline_guards.py#test_no_syntax_warning_on_compile"
        status: pass
      - kind: unit
        ref: "tests/test_baseline_guards.py#test_no_real_multi_second_sleep_in_tests"
        status: pass
    human_judgment: false

duration: 13min
completed: 2026-11-15
status: complete
---

# Phase 8 Plan 03: Migration/entity carried findings and release-hygiene guards Summary

**The migration notice now names the entry's final title and explains which router IDs were kept. A stale DEVICE disabler is no longer turned into a permanent user-disable. Cert hosts are normalised in one place. Four non-vacuous guard tests keep planning references, old developer-doc links, SyntaxWarnings and real multi-second test sleeps out of the tree.**

## Performance

- **Duration:** about 13 min
- **Started:** 2026-11-15T19:52:27Z
- **Completed:** 2026-11-15T20:05Z
- **Tasks:** 3 (6 commits, TDD: test -> feat per task)
- **Files modified:** 11

## Accomplishments

- `async_migrate_entry` raises `entities_migrated` once, after the last step. A default-titled entry's notice therefore names the URL host, and a renamed entry keeps its own title. If the 1.2 -> 1.3 step changes the title of an entry that already has the issue, the issue is updated with the new title and keeps its count (research F11).
- DEVICE -> USER now applies only to entities on legacy devices that are actually disabled (`device.disabled`). The same rule covers the router replacements (Phase 5 IN-07).
- en/de `entities_migrated` text: enabled, visible router sensors got new entity IDs. Disabled or hidden router sensors keep their previous entity ID under the sensor domain (Phase 5 IN-06).
- `cert_hosts` and `TraefikCertEntity.__init__` no longer lowercase. The cert coordinator is the only place that normalises hosts (Phase 5 IN-01).
- Each of the three defence branches has a comment explaining why it exists, with no behaviour change (Phase 7 IN-04/IN-05):
  - `_migrated_entry_data` auth-type branch
  - `_validate_input` ValueError mapping
  - `_collect_credentials` unknown auth type
- Planning references reworded in `const.py` (7 lines) and `__init__.py:53`. The technical reasons stay.
- New guards in `tests/test_baseline_guards.py`:
  - `PLANNING_REFS` byte scan over every .py/.json file in the package
  - developer-doc link guard
  - `compile()` with SyntaxWarning as error over `custom_components/`, `tests/` and `scripts/`
  - AST guard against literal sleeps >= 1 s in `tests/` (excluding `tests/traefik/`)
  - a self-check on planted samples for each detector

## Task Commits

1. **Task 1 (tracer): migration notice title, kept-ID text, stale device disablers**
   - `c9d1e7e` (test, RED)
   - `c637868` (feat, GREEN)
   - Tracer gate: auto mode. The full `<verify>` was re-run green (dev env, ruff, mypy, HA 2026.11.0), then expansion continued.
2. **Task 2: one cert host normalisation point, defence branches documented**
   - `9bc1ff3` (test, RED)
   - `3b6fc0c` (feat, GREEN)
3. **Task 3: planning references reworded, release-hygiene guards**
   - `2fdedc3` (test, RED)
   - `2ebebcb` (feat, GREEN)

## TDD Gate Compliance

- **Task 1 RED:**
  - `test_migration_issue_names_title_after_migration[default-name]` failed on its assertion: `'Traefik Proxy' != 'traefik.example.com'`.
  - The device tests failed on `USER is not DEVICE` / `USER is not None`.
  - JUnit evidence -> `gsd-tools check tdd-red-evidence`: `RED_EVIDENCE_OK`.
  - Semantic assessment: all four failed for the intended reason.
- **Task 2 RED:**
  - `test_cert_factory_unique_id_round_trips_through_key_of[Mixed.Example.com-expiry]` failed: the unique_id was lowercased (`..._mixed.example.com`), so it does not map back to the key. `RED_EVIDENCE_OK`.
  - The lowercase-host parameters passed already at RED. They pin the plan's `secure.example.com` behaviour line.
- **Task 3 RED:**
  - `test_shipped_code_has_no_planning_references` failed with exactly the 8 expected hits (`const.py:35,58,60,63,70,75,86`, `__init__.py:53`). `RED_EVIDENCE_OK`.
  - The doc-link, SyntaxWarning and sleep guards passed at RED, as the plan expected (the tree is already clean; they are regression guards). Their own self-checks show the detectors are not vacuous. For example, `_long_sleeps` flags `tests/traefik/capture.py:304` when it is not excluded.

## Verification (after the last task)

| Gate | Result |
|---|---|
| `uv run pytest -q` | 1116 passed, no "Lingering" |
| `uv run ruff check custom_components tests` | All checks passed |
| `uv run ruff format --check custom_components tests` | 48 files already formatted |
| `uv run mypy --strict custom_components/traefik_proxy` | no issues in 16 source files |
| HA 2026.11.0 venv `pytest -q -o addopts="-p no:respx" tests` | 1116 passed |
| `uv run pytest tests/test_baseline_guards.py -q --no-cov` | 11 passed |

The same gates were green after Tasks 1 and 2 (1107 and 1111 tests, on both environments).

Acceptance criteria:
- `disabled or hidden` (en) PASS
- `deaktivierte oder ausgeblendete` (de) PASS
- `device.disabled` PASS
- `-k "title or disabled"` 15 passed
- `.lower()` count in entity.py 0
- `hand-edited` count 2
- coordinator `-k lower` 1 passed
- planning grep empty
- 4 guards passed
- SyntaxWarning count 7

## Files Created/Modified

- `custom_components/traefik_proxy/__init__.py`:
  - `_async_raise_migrated_issue`, raised after the last step
  - title-change update of an existing issue
  - `disabled_legacy_device_ids` used for both DEVICE mappings
  - defence comment; reworded constant comment
- `custom_components/traefik_proxy/entity.py` - `cert_hosts` and `TraefikCertEntity.__init__` use keys unchanged
- `custom_components/traefik_proxy/config_flow.py` - two defence comments
- `custom_components/traefik_proxy/const.py` - comments reworded without planning references
- `custom_components/traefik_proxy/translations/en.json`, `de.json` - `entities_migrated` text
- `tests/test_migration.py`:
  - `_legacy_device(..., disabled=)`
  - `_stale_device_disabler`
  - title tests
  - extended device tests
- `tests/test_entity_manager.py` - cert factory round-trip test
- `tests/test_baseline_guards.py` - four guards, one detector self-check, release-hygiene docstring
- `tests/test_sensor_tls.py`, `tests/test_binary_sensor_tls_expiring.py` - `test_host_is_lowercased` -> `test_host_key_is_used_unchanged`

## User-visible changes (for the CHANGELOG)

- The migration notice after upgrading from 0.3.0 names the entry's current title, for example the host for an entry that used the default title "Traefik Proxy".
- The notice now says that disabled or hidden router sensors keep their previous entity ID (under `sensor.` instead of `binary_sensor.`), while enabled, visible ones get new IDs.
- A stale device-disabled state on an enabled 0.3.0 device is no longer turned into a permanent user-disable.

## Decisions Made

Worker decisions:

| Decision | Reason | Alternative not taken |
|---|---|---|
| Tests create the stale DEVICE disabler through the registry's private `_async_update_entity` | HA 2026.11 re-derives DEVICE from the device state on every public write (`async_get_or_create`, `async_update_entity`) and on registry load. The first version of the router test (public API) passed vacuously because HA stored `None` | Public API only; that test cannot reach the state |
| An existing issue follows a 1.2 -> 1.3 title change and keeps its `removed_count`. Without an existing issue, no issue is raised | Plan action 1 ("raised again with the new title"); the count comes from the stored placeholders | Delete and re-create the issue (would reset a dismissed state) |
| Enabled-and-hidden routers are covered by the wording "enabled, visible router sensors got new entity IDs" | Hidden enabled routers keep their old ID too (Phase 5 IN-05 fix); "enabled router sensors have new IDs" would be wrong for them | Plan's shorter wording "enabled router sensors" |
| The `_collect_credentials` comment says "out-of-band value" instead of "hand-edited core.config_entries" | `_stored_auth_type` maps an unknown stored type to `none` before `_collect_credentials`, so a hand-edited stored value cannot reach this branch | Same wording at all three sites (would be factually wrong there) |
| Sleep guard: also `sleep(delay=N)` and a bare imported `sleep`. Doc-link guard: skips binary image suffixes in the package/docs | Closes obvious bypasses; image bytes cannot produce a meaningful link | First positional argument of `asyncio.sleep`/`time.sleep` only |
| Separate `test_planning_reference_detector_is_not_vacuous` test next to the scan | Self-check failures are told apart from scan hits | Self-check inside the scan test |

Planner decisions (from the plan, applied as written): pre-migration title fixed in code, not accepted as cosmetic; the router replacement follows the "device actually disabled" rule; the sleep guard excludes `tests/traefik/`; the planning guard scans .py/.json only.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Two TLS tests pinned the removed host lowercasing**
- **Found during:** Task 2
- **Issue:** `tests/test_sensor_tls.py::test_host_is_lowercased` and `tests/test_binary_sensor_tls_expiring.py::test_host_is_lowercased` asserted that the entity lowercases `API.Example.COM`. The plan removes exactly that, and both files are in the task's `<verify>` command but not in its `<files>` list.
- **Fix:** Rewrote both as `test_host_key_is_used_unchanged`. The unique_id and placeholder keep the key. The state is None because the coordinator data holds only the normalised host.
- **Files modified:** tests/test_sensor_tls.py, tests/test_binary_sensor_tls_expiring.py
- **Verification:** Task 2 verify set (256 passed), full suite green on both environments
- **Committed in:** 3b6fc0c

**2. [Rule 1 - Test correctness] The stale DEVICE disabler could not be built through the public registry API**
- **Found during:** Task 1 RED
- **Issue:** `async_get_or_create(disabled_by=DEVICE)` on an enabled device stores `None` on HA 2026.11, so the new `device-on-enabled-device` case passed before the fix.
- **Fix:** Added the `_stale_device_disabler` helper, which uses the private `_async_update_entity` and asserts that the stale state was stored.
- **Files modified:** tests/test_migration.py
- **Committed in:** c9d1e7e

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 test correctness)
**Impact on plan:** No scope creep. Test files outside `files_modified` were touched only where they pinned behaviour this plan removes.

## Issues Encountered

- Finding for the review dispositions (08-12): on the HA 2026.11 minimum, a stale DEVICE disabler cannot survive. The entity registry re-derives DEVICE from the device state when it loads, before any migration runs, and on every public write. So the IN-07 fix is defence in depth and has no reachable effect on supported Home Assistant versions. It stays because the plan requires it and it is harmless.
- `uv run pytest -q` prints `CovReportWarning: No data to report`: pyproject still measures `custom_components.traefik`. This was already the case before this plan and belongs to 08-06 (D-10 coverage path), so it was not changed here.

## Next Phase Readiness

- Ready for 08-04.
- CHANGELOG (08-11) can take the "User-visible changes" above.
- The visual check (08-09) should confirm the en/de repair text and the post-migration title.

## Self-Check: PASSED

- Commits found on this branch: c9d1e7e, c637868, 9bc1ff3, 3b6fc0c, 2fdedc3, 2ebebcb
- Modified files exist: all 11 listed files

---
*Phase: 08-marketplace-release-readiness*
*Completed: 2026-11-15*
