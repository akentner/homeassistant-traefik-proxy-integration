---
phase: 08-marketplace-release-readiness
plan: 12
subsystem: planning
tags: [requirements, review-disposition, housekeeping, traceability]

requires:
  - phase: 08-marketplace-release-readiness
    provides: "resolving commits of 08-02, 08-03, 08-06, 08-07 (and the 08-09 visual check run before this plan)"
provides:
  - "REQUIREMENTS.md: ENT-09 names the HA 2026.11 config_entry_id-bound repair API, Probatio row reflects Phase 7, coverage footer matches the traceability table"
  - "04/05/06-REVIEW-DISPOSITION.md: no open finding left; every row fixed with a commit pointer or skipped/deferred with a reason"
  - "07-REVIEW-FIX.md: every row deferred to Phase 8 points at its Phase 8 commit"
affects: [08-13, gsd-verify-work, milestone-audit]

actuals:
  tokens: 5400       # chars/4 over the realized diff of the two task commits (21529 chars)
  tasks: 2
  commits: 2
plan_head_before: b6fa227e3a13c45627788c58cccdae7387203b02
plan_head_after: 892e04ef1c6ecb4954898179ec1aca2724a10df7

tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - .planning/REQUIREMENTS.md
    - .planning/phases/04-data-layer-correct-lean/04-REVIEW-DISPOSITION.md
    - .planning/phases/05-entity-model-lifecycle/05-REVIEW-DISPOSITION.md
    - .planning/phases/06-certificates/06-REVIEW-DISPOSITION.md
    - .planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-REVIEW-FIX.md

key-decisions:
  - "Phase 4 WR-06, WR-07, IN-03, IN-06 are skipped (accepted for 1.0.0) with a one-line reason instead of fixed: the plan is planning-docs only and none of them changes runtime behaviour"
  - "REL-07 traceability status stays Pending, annotated 'first PR CI run, M43'; no row status changed"

patterns-established: []

requirements-completed: [REL-06]

coverage:
  - id: D1
    description: "REQUIREMENTS.md: ENT-09 wording (config_entry_id), Probatio row (probatio as vol), coverage footer equals the traceability Status column"
    requirement: REL-06
    verification:
      - kind: other
        ref: "grep -q config_entry_id .planning/REQUIREMENTS.md && ! grep -q 'HA 2026.3 API' .planning/REQUIREMENTS.md"
        status: pass
      - kind: other
        ref: "footer recount script from 08-12-PLAN Task 1 <verify> -> footer (87, 78, 76, 2, 9) == table (87, 78, 76, 2, 9)"
        status: pass
      - kind: other
        ref: "grep -n Probatio .planning/REQUIREMENTS.md | grep -q 'probatio as vol'"
        status: pass
    human_judgment: false
  - id: D2
    description: "No open review disposition in Phases 4-6 (table and frontmatter agree, 04 open: 0); every Phase 7 row deferred to Phase 8 carries its Phase 8 commit"
    requirement: REL-06
    verification:
      - kind: other
        ref: "! grep -nE '^\\| [A-Z]{2}-[0-9]{2} \\| [a-z]+ \\| open \\|' 04/05/06-REVIEW-DISPOSITION.md"
        status: pass
      - kind: other
        ref: "! grep -nE '^\\s+disposition: open$' 04/05/06-REVIEW-DISPOSITION.md"
        status: pass
      - kind: other
        ref: "grep -qE '^open: 0$' 04-REVIEW-DISPOSITION.md; ! grep -qi 'deferred to Phase 8 | - |' 07-REVIEW-FIX.md"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-11-15
status: complete
---

# Phase 8 Plan 12: Requirement wording and review dispositions Summary

**REQUIREMENTS.md now names the HA 2026.11 `config_entry_id`-bound repair API for ENT-09, records Probatio as done in Phase 7 and has a coverage footer (76 complete, 2 pending, 9 superseded) that matches the table; all 24 open review findings of Phases 4-6 are closed with a commit pointer or a reason, and every deferred Phase 7 finding points at its Phase 8 commit.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-11-15T21:08Z (approx.)
- **Completed:** 2026-11-15T21:24Z
- **Tasks:** 2 (Task 1 tracer)
- **Files modified:** 5

## Accomplishments

- ENT-09 says "HA 2026.11 issue API bound to the entry via `config_entry_id=entry.entry_id`", quoted from `__init__.py:87`. Home Assistant deletes the notice when the entry is removed. The M34 amendment ("not deleted on unload") is kept.
- The Probatio out-of-scope row says "Done in Phase 7: `config_flow.py` imports `probatio as vol`" (`config_flow.py:30`). No other Out of Scope row was changed.
- The coverage footer was recounted from the Status column: 87 rows, 78 active (76 complete, 2 pending), 9 superseded. The old footer said 36 complete and 42 pending.
- Phase 4 has 0 open findings, down from 16. Phases 5 and 6 have 0, down from 4 each.
- The 8 Phase 7 rows deferred to Phase 8 now carry their commit hashes. The "Deferred (Phase 8)" section has a resolution table.

## Closure table

| Phase | Finding | Disposition | Pointer / reason |
|---|---|---|---|
| 4 | IN-08 | fixed | 9aabda1 (07-04, `invalid_url` ConfigEntryError, no endless retry) + 5835986 (07-05, userinfo -> basic auth migration) |
| 4 | IN-09 | fixed | 6f1ab67 (07-08, `InvalidUrl` / `UrlHasCredentials` carry no args) |
| 4 | IN-10 | fixed | 58dc998 (07-05, `urlparse` ValueError -> `invalid_url`, reconfigure runs the shape check first) |
| 4 | IN-11 | fixed | 2795b8c (05-05, `_coordinator` alias removed by the cert-entity rewrite, D-22) |
| 4 | IN-12 | fixed | 712c6ec + 595e2e3 (08-02) |
| 4 | IN-13 | fixed | 595e2e3 (08-02, `RAWDATA_PROBE_INTERVAL`, `_probe_clock`) |
| 4 | IN-14 | fixed | 595e2e3 (08-02, switch debug log) |
| 4 | WR-03 | fixed | bc523eb (07-06, M5: `OptionsFlowWithReload`, listener removed) |
| 4 | WR-06 | skipped | Necessity only: outer `asyncio.timeout(10)` (`config_flow.py:228`) still there, harmless, inner request timeout fires first |
| 4 | WR-07 | skipped | Necessity only: `Auth.header()` extra checks (`api.py:93,98`) unreachable for the frozen, validated `Auth` |
| 4 | WR-08 | fixed | d45c008 (06-01, `isinstance(match, str)` gone with the host-extraction rewrite) |
| 4 | IN-02 | fixed | a4df3cf (05-06, M12: reload service and its loop removed) |
| 4 | IN-03 | skipped | Accepted trade-off (W6): hourly version re-check documented in the coordinator docstring; a failing `/api/version` fails the cycle by design |
| 4 | IN-05 | fixed | 58dc998 (07-05, M21: reconfigure moves `unique_id`) |
| 4 | IN-06 | skipped | Dev-only capture script, throwaway harness credentials, check exits 1 and names the file |
| 4 | IN-07 | fixed | ff04249 (05-01, dead `TYPE_CHECKING` removed); sequential paginated reads intended (fallback only) |
| 5 | IN-01 | fixed | 3b6fc0c (08-03, single host-normalisation point) |
| 5 | IN-03 | fixed | 9aabda1 (07-04, `cert_unavailable` removed, D-21) |
| 5 | IN-06 | fixed | c637868 (08-03, en/de repair text on kept entity IDs) |
| 5 | IN-07 | fixed | c637868 (08-03, DEVICE->USER only for disabled legacy devices; defence in depth on HA >= 2026.11) |
| 6 | IN-01 | fixed | f8e0a67 (07-06, `get_threshold()` removed) |
| 6 | IN-02 | fixed | f8e0a67 (07-06, `CONF_TLS_WARN_DAYS` replaces the literal) |
| 6 | IN-03 | fixed | 4cf98b0 (08-02, host resolved once per probe cycle) |
| 6 | IN-04 | fixed | bcff94f (08-02, deterministic socket tests, teardown) |
| 7 | WR-04 | fixed in Phase 8 | b6116e5 (08-06) |
| 7 | WR-05 | fixed in Phase 8 | df061f4 (08-07) |
| 7 | WR-06 | fixed in Phase 8 | a0b0cd8 (08-06 lock) + df061f4 (08-07 CI job) |
| 7 | WR-07 | fixed in Phase 8 | df061f4 (08-07) |
| 7 | IN-03 | fixed in Phase 8 | 4cf98b0 (08-02) |
| 7 | IN-04 | fixed in Phase 8 | 3b6fc0c (08-03) |
| 7 | IN-05 | fixed in Phase 8 | 3b6fc0c (08-03) |
| 7 | IN-07 | fixed in Phase 8 | b6116e5 (08-06) |

Every "fixed" pointer was checked two ways. `git log -S'<snippet>'` was run against the cited file, and the snippet was confirmed absent from, or changed in, the current code. Pointers for this phase come from the 08-02, 08-03, 08-06 and 08-07 SUMMARYs and `git show --stat`. In 07-REVIEW-FIX.md the status column still says "deferred to Phase 8", because that is what the 07 fix pass decided. The commit column now names the resolving commit, which matches the plan's key_link pattern.

## Task Commits

1. **Task 1 (tracer): REQUIREMENTS ENT-09, Probatio row, coverage footer** - `f889b6e` (docs). Tracer gate: auto mode, both `<verify>` commands re-run green before expansion.
2. **Task 2: close open review dispositions of Phases 4-7** - `892e04e` (docs)

## Files Created/Modified

- `.planning/REQUIREMENTS.md`: ENT-09, the Probatio row, the audit-traceability Probatio note, a REL-07 annotation, the footer and the last-updated line.
- `.planning/phases/04-data-layer-correct-lean/04-REVIEW-DISPOSITION.md`: 16 rows closed; frontmatter, table and `open: 0` agree.
- `.planning/phases/05-entity-model-lifecycle/05-REVIEW-DISPOSITION.md`: 4 rows closed.
- `.planning/phases/06-certificates/06-REVIEW-DISPOSITION.md`: 4 rows closed.
- `.planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-REVIEW-FIX.md`: commit per deferred row, plus a Phase 8 resolution table.

## Decisions Made

See the Worker decisions below.

## Worker decisions

| Decision | Reason | Alternative not taken |
|---|---|---|
| Phase 4 WR-06, WR-07, IN-03 and IN-06 are `skipped` with a reason, not fixed | The plan is planning-docs only (no code). All four are necessity or info items with no user-visible effect. | Fix them in code now (out of this plan's scope) or mark them `deferred` (there is no later milestone to defer to) |
| Already-`deferred` Phase 4 rows (WR-04, WR-05, IN-01, IN-04) were left unchanged | They already carry a reason. The plan and its gates only require closing `open` rows. | Re-verify them and flip them to `fixed` (extra scope, not needed by D-08) |
| REL-07 traceability row annotated "Pending (first PR CI run, M43)" | Orchestrator hint and decision M43 (deferred to CI). The status stays Pending, so the footer count is unaffected. | Leave it as a bare "Pending" |
| The audit-traceability "Out of scope" row's "§4.7 Probatio — no action" became "adopted in Phase 7 (`import probatio as vol`)" | The same stale statement as the Probatio Out of Scope row, in the same file. Only the Probatio part changed. | Leave the second stale mention (it would contradict the corrected row) |
| PROJECT.md "asyncio.gather" constraint not reworded | PROJECT.md is outside this plan's files (08-11 hint: reword only if in scope). Phase 4 IN-07 records the sequential paginated reads as intended. | Edit PROJECT.md and regenerate CLAUDE.md (08-11 owns them) |
| 05/06 disposition files got no `open:` key | Neither file had one. Their frontmatter and table agree with 0 open rows. | Add `open: 0` (a format change the gate tool does not write there) |
| 07-REVIEW-FIX rows keep the status "deferred to Phase 8" and the hash goes in the Commit column without backticks | This matches the plan's key_link pattern `deferred to Phase 8 \| [0-9a-f]{7}`. | Change the status to "fixed" (breaks the pattern and rewrites the 07 fix decision) |

## Deviations from Plan

None. The plan was executed as written. The extra REQUIREMENTS.md touches (REL-07 annotation, audit-traceability Probatio note, last-updated line) are listed under Worker decisions. They change no row status.

## Issues Encountered

- 04-REVIEW-DISPOSITION.md frontmatter and table disagreed before this plan: IN-08 and IN-09 were `open` in the frontmatter and `deferred` in the table. Both are now `fixed` in both places, and a script confirmed that the frontmatter and table dispositions are equal in all three files.

## Quality gates (no code touched)

| Gate | Result |
|---|---|
| `uv run pytest -q` | 1152 passed, coverage 99.29 % (fail_under 99) |
| HA 2026.11.0 venv `python -m pytest -q -o addopts="-p no:respx" tests` | 1152 passed |
| `uv run ruff check custom_components tests` | All checks passed |
| `uv run ruff format --check custom_components tests` | 50 files already formatted |
| `uv run mypy --strict custom_components/traefik_proxy` | no issues (16 files) |

All gates ran once, with no reruns. No Docker step, push, tag or PR (REL-08 prohibition held). REL-07 is still pending until the first PR CI run.

## User-visible changes

None.

## User Setup Required

None. No external service configuration is required.

## Next Phase Readiness

- 08-13 can close the deferred-items files and prepare push readiness.
- REL-07 is still pending until the first PR CI run (M43). REL-08 is the manager's push.

---
*Phase: 08-marketplace-release-readiness*
*Completed: 2026-11-15*

## Self-Check: PASSED

- Task commits f889b6e and 892e04e and all 19 cited pointer commits are ancestors of HEAD.
- Plan gates re-run after the commits: both Task 1 `<verify>` commands, both Task 2 `<verify>` commands and all three acceptance criteria pass.
