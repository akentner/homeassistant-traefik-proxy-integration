---
phase: 06
review: 06-REVIEW.md
titles: json
findings:
  - id: CR-01
    severity: critical
    disposition: fixed
    title: "Probe mode reports Traefik's default certificate as healthy (`san_mismatch` never makes a problem)"
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "`normalize_host` uses IDNA 2003, so `ß` domains get the wrong A-label"
  - id: WR-02
    severity: warning
    disposition: fixed
    title: "A cert cycle still running at unload re-arms the day-boundary timer forever and crashes on the deleted `runtime_data`"
  - id: WR-03
    severity: warning
    disposition: fixed
    title: "`async_setup_entry` waits for the whole first cert cycle, up to about 500 s in probe mode"
  - id: WR-04
    severity: warning
    disposition: fixed
    title: "TLS tests under `freezer` hang instead of failing; no per-test timeout is configured"
  - id: IN-01
    severity: info
    disposition: open
    title: "`CertCoordinator.get_threshold()` is dead in production"
  - id: IN-02
    severity: info
    disposition: open
    title: "Magic string `\"tls_warn_days\"` instead of `CONF_TLS_WARN_DAYS`"
  - id: IN-03
    severity: info
    disposition: open
    title: "The connect host is resolved once per probe through the default executor"
  - id: IN-04
    severity: info
    disposition: open
    title: "Small races in socket tests"
---

# Phase 06: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| CR-01 | critical | fixed | review-fix 78763cd |
| WR-01 | warning | fixed | review-fix b6e2da7 |
| WR-02 | warning | fixed | review-fix 582fd92 |
| WR-03 | warning | fixed | review-fix 913bec9 |
| WR-04 | warning | fixed | review-fix fbcc346 |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| IN-04 | info | open | - |
