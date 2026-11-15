---
phase: 08
review: 08-REVIEW.md
titles: json
findings:
  - id: CR-01
    severity: critical
    disposition: fixed
    title: "`make hacs-action` hands the developer's full `gh` token to a mutable third-party image"
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "Diagnostics leak secret-bearing `HeaderRegexp`/`QueryRegexp` values through router `errors`"
  - id: WR-02
    severity: warning
    disposition: open
    title: "Probe mode connects only to the first resolved address (regression for IPv6-first or multi-address hosts)"
  - id: WR-03
    severity: warning
    disposition: fixed
    title: "SHA pins of `hacs/action` and `home-assistant/actions/hassfest` do not pin the executed code"
  - id: WR-04
    severity: warning
    disposition: open
    title: "CI lint and test jobs install dev dependencies without a lock (`uv.lock` is git-ignored)"
  - id: IN-01
    severity: info
    disposition: open
    title: "README promises redacted rule values, but router sensor attributes expose them verbatim"
  - id: IN-02
    severity: info
    disposition: open
    title: "The migration repair issue now depends on the 1.3 step completing"
  - id: IN-03
    severity: info
    disposition: open
    title: "`UnicodeError` from `getaddrinfo` escapes the probe cycle"
  - id: IN-04
    severity: info
    disposition: open
    title: "The release check runs after publication and fires twice"
  - id: IN-05
    severity: info
    disposition: open
    title: "`_download` URL parsing in the local HACS overlay is fragile"
  - id: IN-06
    severity: info
    disposition: open
    title: "Coverage gate and x86-only lock make partial and non-x86 local runs fail"
open: 8
total: 11
recorded: 2026-11-15T21:51:39.312Z
---

# Phase 08: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| CR-01 | critical | fixed | 08-REVIEW-FIX.md |
| WR-01 | warning | fixed | 08-REVIEW-FIX.md |
| WR-02 | warning | open | - |
| WR-03 | warning | fixed | 08-REVIEW-FIX.md |
| WR-04 | warning | open | - |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| IN-04 | info | open | - |
| IN-05 | info | open | - |
| IN-06 | info | open | - |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
