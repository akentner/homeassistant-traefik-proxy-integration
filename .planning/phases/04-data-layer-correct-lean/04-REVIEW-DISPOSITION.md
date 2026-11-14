---
phase: 04
review: 04-REVIEW.md
titles: json
findings:
  - id: CR-01
    severity: critical
    disposition: open
    title: "Cert entities no longer update after a cert cycle or threshold change (regression from `always_update=False`)"
  - id: WR-01
    severity: warning
    disposition: open
    title: "A transient 404 on `/api/rawdata` switches the client to pagination for its whole lifetime"
  - id: WR-02
    severity: warning
    disposition: open
    title: "aiohttp `ValueError` escapes the error taxonomy (URL with userinfo plus token)"
  - id: WR-03
    severity: warning
    disposition: open
    title: "Update listener leaks across reloads; reconfigure plus update listener breaks in HA 2026.12.0"
  - id: WR-04
    severity: warning
    disposition: open
    title: "Paginated reads can silently drop items, and the stale-entity cleanup then deletes their registry entries"
  - id: WR-05
    severity: warning
    disposition: open
    title: "Every cert cycle and options save logs ERROR \"does not generate unique IDs\" per host and platform"
  - id: WR-06
    severity: warning
    disposition: open
    title: "Already-defended-elsewhere: redundant 10 s timeout around the version probe"
  - id: WR-07
    severity: warning
    disposition: open
    title: "Impossible-state guard: `Auth.header()` re-checks credentials that `__post_init__` guarantees"
  - id: WR-08
    severity: warning
    disposition: open
    title: "Impossible-state guard: `isinstance(match, str)` on single-group `findall` results"
  - id: IN-01
    severity: info
    disposition: open
    title: "Redirects: http-to-https redirects drop the token and surface as `invalid_auth` / reauth (known open question, Phase 7/8)"
  - id: IN-02
    severity: info
    disposition: open
    title: "Reload service verification loop is defeated by the refresh debouncer (deferred to Phase 5)"
  - id: IN-03
    severity: info
    disposition: open
    title: "A quick Traefik restart is detected up to 1 h late; a failing `/api/version` takes down the whole cycle"
  - id: IN-04
    severity: info
    disposition: open
    title: "A stored token the new `Auth` rejects fails setup instead of starting reauth"
  - id: IN-05
    severity: info
    disposition: open
    title: "Reconfigure to a new host keeps the old `unique_id` (pre-existing)"
  - id: IN-06
    severity: info
    disposition: open
    title: "The capture script writes fixtures before checking them for secrets"
  - id: IN-07
    severity: info
    disposition: open
    title: "Dead `TYPE_CHECKING` block; sequential paginated reads contradict the stated constraint"
open: 16
total: 16
recorded: 2026-11-14T01:26:55.869Z
---

# Phase 04: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| CR-01 | critical | open | - |
| WR-01 | warning | open | - |
| WR-02 | warning | open | - |
| WR-03 | warning | open | - |
| WR-04 | warning | open | - |
| WR-05 | warning | open | - |
| WR-06 | warning | open | - |
| WR-07 | warning | open | - |
| WR-08 | warning | open | - |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| IN-04 | info | open | - |
| IN-05 | info | open | - |
| IN-06 | info | open | - |
| IN-07 | info | open | - |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
