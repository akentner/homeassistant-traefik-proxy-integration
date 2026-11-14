---
phase: 05
review: 05-REVIEW.md
titles: json
findings:
  - id: CR-01
    severity: critical
    disposition: open
    title: "Migration re-enables routers the user disabled (the replacement router sensor ignores the old `disabled_by`)"
  - id: WR-01
    severity: warning
    disposition: open
    title: "The update listener is never unsubscribed; the 1.2 migration now forces a reload, so every upgraded entry gets duplicate and stale listeners"
  - id: WR-02
    severity: warning
    disposition: open
    title: "Turning per-item entities off deletes the Routers and Services devices without the reference check used for legacy devices"
  - id: IN-01
    severity: info
    disposition: open
    title: "Already-defended-elsewhere: the cert host is lowercased twice more, and only the factory changes the key"
  - id: IN-02
    severity: info
    disposition: open
    title: "`de.json` has no `config`, `options` or `exceptions` sections"
  - id: IN-03
    severity: info
    disposition: open
    title: "Unused translation `exceptions.cert_unavailable`"
  - id: IN-04
    severity: info
    disposition: open
    title: "The per-item option has a code path but no UI"
---

# Phase 05: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| CR-01 | critical | open | - |
| WR-01 | warning | open | - |
| WR-02 | warning | open | - |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| IN-04 | info | open | - |
