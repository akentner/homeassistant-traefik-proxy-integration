---
phase: 04
review: 04-REVIEW.md
titles: json
findings:
  - id: IN-08
    severity: info
    disposition: fixed
    title: "Request-construction errors on a stored entry retry setup forever with an unactionable reason (carried into Phase 7)"
  - id: IN-09
    severity: info
    disposition: fixed
    title: "`InvalidUrl` carries a credential-bearing URL in its exception args (carried into Phase 7)"
  - id: IN-10
    severity: info
    disposition: fixed
    title: "`_check_url_shape` lets `urlparse`'s `ValueError` escape"
  - id: IN-11
    severity: info
    disposition: fixed
    title: "Cert entities keep a redundant `_coordinator` alias of `self.coordinator`"
  - id: IN-12
    severity: info
    disposition: fixed
    title: "Matrix row (15) and the fix report over-claim the probe timing; three probe-clock edges are untested"
  - id: IN-13
    severity: info
    disposition: fixed
    title: "The probe interval is hard-wired to `VERSION_RECHECK_INTERVAL`, and `_probe_armed_at` is moved when nothing was armed"
  - id: IN-14
    severity: info
    disposition: fixed
    title: "The committed switch to the pages is no longer logged"
  - id: WR-09
    severity: warning
    disposition: fixed
    title: "The rawdata probe can be starved indefinitely: every post-failure version re-check resets its clock"
  - id: WR-10
    severity: warning
    disposition: fixed
    title: "The switch to pagination is committed even when the page reads fail in the same cycle (outage-wide 404)"
  - id: CR-01
    severity: critical
    disposition: fixed
    title: "Cert entities no longer update after a cert cycle or threshold change (regression from `always_update=False`)"
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "A transient 404 on `/api/rawdata` switches the client to pagination for its whole lifetime"
  - id: WR-02
    severity: warning
    disposition: fixed
    title: "aiohttp `ValueError` escapes the error taxonomy (URL with userinfo plus token)"
  - id: WR-03
    severity: warning
    disposition: fixed
    title: "Update listener leaks across reloads; reconfigure plus update listener breaks in HA 2026.12.0"
  - id: WR-04
    severity: warning
    disposition: deferred
    title: "Paginated reads can silently drop items, and the stale-entity cleanup then deletes their registry entries"
  - id: WR-05
    severity: warning
    disposition: deferred
    title: "Every cert cycle and options save logs ERROR \"does not generate unique IDs\" per host and platform"
  - id: WR-06
    severity: warning
    disposition: skipped
    title: "Already-defended-elsewhere: redundant 10 s timeout around the version probe"
  - id: WR-07
    severity: warning
    disposition: skipped
    title: "Impossible-state guard: `Auth.header()` re-checks credentials that `__post_init__` guarantees"
  - id: WR-08
    severity: warning
    disposition: fixed
    title: "Impossible-state guard: `isinstance(match, str)` on single-group `findall` results"
  - id: IN-01
    severity: info
    disposition: deferred
    title: "Redirects: http-to-https redirects drop the token and surface as `invalid_auth` / reauth (known open question, Phase 7/8)"
  - id: IN-02
    severity: info
    disposition: fixed
    title: "Reload service verification loop is defeated by the refresh debouncer (deferred to Phase 5)"
  - id: IN-03
    severity: info
    disposition: skipped
    title: "A quick Traefik restart is detected up to 1 h late; a failing `/api/version` takes down the whole cycle"
  - id: IN-04
    severity: info
    disposition: deferred
    title: "A stored token the new `Auth` rejects fails setup instead of starting reauth"
  - id: IN-05
    severity: info
    disposition: fixed
    title: "Reconfigure to a new host keeps the old `unique_id` (pre-existing)"
  - id: IN-06
    severity: info
    disposition: skipped
    title: "The capture script writes fixtures before checking them for secrets"
  - id: IN-07
    severity: info
    disposition: fixed
    title: "Dead `TYPE_CHECKING` block; sequential paginated reads contradict the stated constraint"
open: 0
total: 25
recorded: 2026-11-14T03:05:35.009Z
---

# Phase 04: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| IN-08 | info | fixed | Phase 7: 9aabda1 (07-04, invalid stored URL ends in ConfigEntryError `invalid_url`, no endless retry) + 5835986 (07-05, URL userinfo migrated to basic auth) |
| IN-09 | info | fixed | Phase 7: 6f1ab67 (07-08, `InvalidUrl` / `UrlHasCredentials` carry no args) |
| IN-10 | info | fixed | Phase 7: 58dc998 (07-05, `urlparse` ValueError becomes `invalid_url`; reconfigure runs the shape check before deriving the host) |
| IN-11 | info | fixed | Phase 5: 2795b8c (05-05, cert entities rebuilt on TraefikCertEntity; the `_coordinator` alias is gone, D-22) |
| IN-12 | info | fixed | Phase 8: 712c6ec + 595e2e3 (08-02, matrix row 15 reworded, probe-clock edge tests) |
| IN-13 | info | fixed | Phase 8: 595e2e3 (08-02, `RAWDATA_PROBE_INTERVAL` and `_probe_clock`, armed only when a probe is requested) |
| IN-14 | info | fixed | Phase 8: 595e2e3 (08-02, debug line on the committed switch to the paginated endpoints) |
| WR-09 | warning | fixed | 04-REVIEW-FIX.md (not in the current review) |
| WR-10 | warning | fixed | 04-REVIEW-FIX.md (not in the current review) |
| CR-01 | critical | fixed | Plan 04-07 (a845757..90af13a); confirmed resolved by re-review cc26dfc (not in the current review) |
| WR-01 | warning | fixed | Plan 04-09 (87061f6..a93762a); confirmed resolved as scoped by re-review cc26dfc, follow-ups WR-09/WR-10 (not in the current review) |
| WR-02 | warning | fixed | Plan 04-08 (6890f51..73986d3); confirmed resolved by re-review cc26dfc, follow-ups IN-08/IN-09 (not in the current review) |
| WR-03 | warning | fixed | Phase 7 (M5): bc523eb (07-06, `OptionsFlowWithReload`, update listener removed) (not in the current review) |
| WR-04 | warning | deferred | Phase 5 (M28): entity manager with grace period (not in the current review) |
| WR-05 | warning | deferred | Phase 5 (M28): entity manager adds only new unique_ids (not in the current review) |
| WR-06 | warning | skipped | Necessity only, accepted for 1.0.0: the outer `asyncio.timeout(10)` in `_validate_input` is still there but harmless; the client's own 10 s request timeout fires first (not in the current review) |
| WR-07 | warning | skipped | Necessity only, accepted for 1.0.0: `Auth` is frozen and validated in `__post_init__`, so the extra truthiness checks in `header()` are unreachable and change no behaviour (not in the current review) |
| WR-08 | warning | fixed | Phase 6: d45c008 (06-01, host extraction from rules rewritten; the `isinstance(match, str)` guard is gone) (not in the current review) |
| IN-01 | info | deferred | Phase 7 (M28): config flow / redirect handling (not in the current review) |
| IN-02 | info | fixed | Phase 5 (M12): a4df3cf (05-06, reload service and its verification loop removed) (not in the current review) |
| IN-03 | info | skipped | Accepted trade-off for 1.0.0 (W6): the version is re-read at most hourly and after a failed cycle, as the coordinator docstring states; a failing `/api/version` fails the cycle by design (not in the current review) |
| IN-04 | info | deferred | Phase 7 (M28): rejected stored token starts reauth (not in the current review) |
| IN-05 | info | fixed | Phase 7 (M21): 58dc998 (07-05, reconfigure moves `unique_id` to the new host:port) (not in the current review) |
| IN-06 | info | skipped | Accepted for 1.0.0: dev-only capture script with throwaway harness credentials; the check exits 1 and names the file (not in the current review) |
| IN-07 | info | fixed | Phase 5: ff04249 (05-01, dead `TYPE_CHECKING` block removed); the sequential paginated reads are intended (fallback path only, docstring says so) and stay (not in the current review) |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
