---
phase: 05
review: 05-REVIEW.md
titles: json
findings:
  - id: CR-01
    severity: critical
    disposition: fixed
    title: "Migration re-enables routers the user disabled (the replacement router sensor ignores the old `disabled_by`)"
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "The update listener is never unsubscribed; the 1.2 migration now forces a reload, so every upgraded entry gets duplicate and stale listeners"
  - id: WR-02
    severity: warning
    disposition: fixed
    title: "Turning per-item entities off deletes the Routers and Services devices without the reference check used for legacy devices"
  - id: IN-01
    severity: info
    disposition: open
    title: "Already-defended-elsewhere: the cert host is lowercased twice more, and only the factory changes the key"
  - id: IN-02
    severity: info
    disposition: deferred
    title: "`de.json` has no `config`, `options` or `exceptions` sections"
  - id: IN-03
    severity: info
    disposition: open
    title: "Unused translation `exceptions.cert_unavailable`"
  - id: IN-04
    severity: info
    disposition: deferred
    title: "The per-item option has a code path but no UI"
  - id: CR-02
    severity: critical
    disposition: fixed
    title: "Entities the user disabled through a 0.3.0 device are re-enabled by the next update of their new device"
  - id: IN-05
    severity: info
    disposition: fixed
    title: "The migration keeps \"disabled\" but drops \"hidden\" for router sensors"
  - id: IN-06
    severity: info
    disposition: open
    title: "Disabled replacements keep the old object id, while the repair text says router sensors get new entity IDs"
---

# Phase 05: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| CR-01 | critical | fixed | Plan 05-08 (50bcc4c..c265fa5) |
| WR-01 | warning | fixed | Plan 05-08 (98602c2..c265fa5) |
| WR-02 | warning | fixed | Plan 05-08 (6ba969e..db2762c) |
| IN-01 | info | open | - |
| IN-02 | info | deferred | Phase 7 (FLOW-07: German config/options strings) |
| IN-03 | info | open | - |
| IN-04 | info | deferred | Phase 7 (W36: per-item option form field) |
| CR-02 | critical | fixed | 05-REVIEW-FIX.md (4e1aee1..80e1902) |
| IN-05 | info | fixed | 05-REVIEW-FIX.md (c71cf6c..5ea22e5) |
| IN-06 | info | open | - |
