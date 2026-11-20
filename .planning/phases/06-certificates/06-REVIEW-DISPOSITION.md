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
    disposition: fixed
    title: "`CertCoordinator.get_threshold()` is dead in production"
  - id: IN-02
    severity: info
    disposition: fixed
    title: "Magic string `\"tls_warn_days\"` instead of `CONF_TLS_WARN_DAYS`"
  - id: IN-03
    severity: info
    disposition: fixed
    title: "The connect host is resolved once per probe through the default executor"
  - id: IN-04
    severity: info
    disposition: fixed
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
| IN-01 | info | fixed | Phase 7: f8e0a67 (07-06, `get_threshold()` removed, threshold read once at construction) |
| IN-02 | info | fixed | Phase 7: f8e0a67 (07-06, `CONF_TLS_WARN_DAYS` replaces the literal) |
| IN-03 | info | fixed | Phase 8: 4cf98b0 (08-02, connect host resolved once per probe cycle) |
| IN-04 | info | fixed | Phase 8: bcff94f (08-02, deterministic socket tests, `tls_server` teardown always closes) |
