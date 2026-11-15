---
phase: 06-certificates
plan: 01
subsystem: certificates
tags: [traefik-rules, host-parsing, idna, cert-coordinator, dos-cap]

requires:
  - phase: 05
    provides: "models.Router / TlsDomain snapshot read by the cert coordinator"
provides:
  - "rules.extract_hosts(rule) -> tuple[str, ...] (literal Host() names, v2 multi-argument + v3 ||/&&)"
  - "rules.normalize_host(name) -> str | None (strip, lowercase, trailing dot, IDNA A-label, charset, IP literals)"
  - "const.MAX_CERT_HOSTS = 200"
  - "CertCoordinator._collect_hosts() -> sorted, capped tuple (replaces _collect_hosts_from_main_coordinator)"
affects: [06-02, 06-03, 06-04, 06-05]

actuals:
  tokens: 7000
  tasks: 2
  commits: 4
plan_head_before: 5e6c4f7f69eb86a57385c55f102d402339e76c81
plan_head_after: 3850a6914631040d260aa123766ba32c35e5707c

tech-stack:
  added: []
  patterns:
    - "Pure stdlib rule parser module (rules.py) next to models.py; precompiled module-level regexes, no growing state"
    - "One host normalizer for rule names and tls.domains so later SAN/API matching is a plain string comparison"

key-files:
  created:
    - custom_components/traefik_proxy/rules.py
    - tests/test_rules.py
  modified:
    - custom_components/traefik_proxy/cert_coordinator.py
    - custom_components/traefik_proxy/const.py
    - tests/test_cert_coordinator.py

key-decisions:
  - "HostHeader is not treated as Host; negated !Host() contributes no host (W52)"
  - "Cert host set capped at MAX_CERT_HOSTS = 200, first 200 in sorted order, one WARNING per cycle with counts only"
  - "normalize_host also rejects names with an empty label and scoped IPv6 (%zone) literals"

patterns-established:
  - "Host names reach the cert coordinator only through rules.normalize_host"

requirements-completed: []  # CERT-03 partly delivered; P-08 (no unbounded module cache) is owned by 06-05

coverage:
  - id: D1
    description: "Literal Host() names from v2 multi-argument and v3 ||/&& rules; regex/SNI/header/wildcard/template/negated names skipped"
    requirement: "CERT-03"
    verification:
      - kind: unit
        ref: "tests/test_rules.py#test_extract_hosts_literal_names, test_extract_hosts_skips_non_literal_names"
        status: pass
    human_judgment: false
  - id: D2
    description: "Host normalization (lowercase, trailing dot, IDNA A-label, charset, IP literals)"
    requirement: "CERT-03"
    verification:
      - kind: unit
        ref: "tests/test_rules.py#test_normalize_host_accepts, test_normalize_host_rejects"
        status: pass
    human_judgment: false
  - id: D3
    description: "Cert host set = sorted union of tls.domains main/sans and rule hosts of TLS routers; full setup registers cert entities for alt.example.com"
    requirement: "CERT-03"
    verification:
      - kind: unit
        ref: "tests/test_cert_coordinator.py#test_collect_hosts_multi_host_rules_and_domains"
        status: pass
      - kind: integration
        ref: "tests/test_cert_coordinator.py#test_full_setup_registers_cert_entities_for_alt_host"
        status: pass
    human_judgment: false
  - id: D4
    description: "At most 200 hosts probed per cert cycle, one WARNING per cycle with counts only"
    requirement: "CERT-03"
    verification:
      - kind: unit
        ref: "tests/test_cert_coordinator.py#test_collect_hosts_cap_not_reached, test_collect_hosts_cap_201_drops_last_sorted, test_cert_cycle_cap_250_probes_200, test_cert_cycle_cap_warns_once_per_cycle"
        status: pass
    human_judgment: false

duration: 10min
completed: 2026-11-15
status: complete
---

# Phase 6 Plan 01: Rule Host Extraction and Cert Host Cap Summary

**New pure `rules.py` turns v2 multi-argument and v3 `||`/`&&` Traefik rules into normalized literal host names (IDNA A-labels, no regex/SNI/wildcard/negated names), and the cert coordinator probes the sorted union capped at 200 hosts per cycle.**

## Performance

- **Duration:** about 10 min
- **Started:** 2026-11-15T07:54Z (approx.)
- **Completed:** 2026-11-15T08:04Z
- **Tasks:** 2 (both TDD: RED commit + GREEN commit, no refactor needed)
- **Files modified:** 5

## Accomplishments

- `rules.extract_hosts`: `Host(`a`, `b`)`, `Host(`a`) || Host(`b`)`, `Host(`A`) && PathPrefix(`/x`) || Host(`b`)` all give `('a…', 'b…')`; backtick and double-quoted arguments; `HostRegexp`, `HostSNI`, `HostSNIRegexp`, `HostHeader`, `*`/`{…}` names, `!Host(...)` (also `! Host`) and malformed matchers give nothing.
- `rules.normalize_host`: strip, lowercase, one trailing dot, `[...]` IPv6 literals, IP compressed form, IDNA A-labels (`Bücher.example` -> `xn--bcher-kva.example`), charset whitelist `[a-z0-9._-]`.
- `CertCoordinator._collect_hosts()` replaces `_collect_hosts_from_main_coordinator()`; returns a sorted tuple; old Host-rule regex constant and its test removed (no copy left in `custom_components` or `tests`).
- `MAX_CERT_HOSTS = 200`: sorted host set cut at 200, one WARNING per cycle "Certificate host limit of 200 reached; N hosts are not checked" without host names.

## Task Commits

1. **Task 1 (tracer): v2 multi-argument Host rule reaches the cert host set**
   - RED `9b813ee` test(06-01): add failing tests for literal Host() extraction and host normalization
   - GREEN `d45c008` feat(06-01): extract literal Host() names from v2/v3 rules for the cert host set
   - Tracer gate (auto mode): all `<verify>` commands re-run green -> expanded to Task 2
2. **Task 2: Cap the host set at MAX_CERT_HOSTS**
   - RED `a7e4fef` test(06-01): add failing tests for the MAX_CERT_HOSTS cap
   - GREEN `3850a69` feat(06-01): cap the cert host set at MAX_CERT_HOSTS (200) per cycle

## TDD Gate Compliance

| Task | RED evidence | Verdict | Semantic assessment |
|------|--------------|---------|---------------------|
| 1 | `pytest tests/test_rules.py tests/test_cert_coordinator.py --junitxml`, exit 1, 27 failed / 39 passed; target `test_extract_hosts_literal_names[Host(`a.example.com`, `b.example.com`)-expected0]` | `RED_EVIDENCE_OK` (target_test_failed) | Target ran and failed on its assertion (`() != ('a.example.com', 'b.example.com')`) against a throwaway uncommitted stub `rules.py` that returned `()`/`None`; the full-setup test failed on `"alt.example.com" in probed`. Coordinator collect-host tests failed with `AttributeError` (method not yet renamed), as expected. |
| 2 | `pytest tests/test_cert_coordinator.py --junitxml`, exit 1, 3 failed / 24 passed; target `test_cert_cycle_cap_250_probes_200` | `RED_EVIDENCE_OK` (target_test_failed) | Target failed on `assert 250 == 200` (probe call count, no cap yet). `MAX_CERT_HOSTS` was present uncommitted in `const.py` for the RED run so the module imported; it was committed with GREEN. |

The RED commits are test-only, so the tree at each RED commit does not import (`rules` module / `MAX_CERT_HOSTS` absent). The GREEN commit after each one restores a green tree.

## Verification

- `uv run pytest -q`: 630 passed (HA dev venv)
- `~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`: **630 passed on HA 2026.3.0**
- `uv run ruff check custom_components tests`: all checks passed
- `uv run ruff format --check custom_components tests`: 40 files already formatted
- `uv run mypy --strict custom_components/traefik_proxy`: no issues in 15 source files
- `tests/test_rules.py`: 45 passed (criterion >= 25); `-k "collect_hosts or alt"`: 7 passed (>= 6); `-k "cap or limit or 199 or 200 or 201 or 250"`: 6 passed (>= 4)
- `! grep -rn "_HOST_FROM_RULE\|_collect_hosts_from_main_coordinator" custom_components tests`: no match

## Worker Decisions

| Decision | Reason | Alternative not taken |
|---|---|---|
| `HostHeader` is not treated as `Host` (planner decision, W52) | D-05 lists `HostHeader` among the prefixes that never match; removed in Traefik v3 | Treat `HostHeader(` like `Host(` |
| Negated `!Host(...)` contributes no host; detection walks back over whitespace from the matcher (linear, no slicing per matcher) | The router does not serve that name | Ignore negation |
| `normalize_host` additionally rejects names with an empty label (`..`, leading dot) | Not covered by the plan; `[a-z0-9._-]+` alone would accept `..`, which is no valid SNI value | Plain charset check only |
| `normalize_host` does not accept scoped IPv6 literals (`fe80::1%eth0`) as IP; they fail the charset check | A zone id is meaningless as SNI / probe target | Return `ipaddress` compressed form including `%zone` |
| A bracketed name that is not a valid IP literal (`[not-an-ip]`) is skipped | Brackets only make sense around IPv6 literals | Strip the brackets and treat it as a DNS name |
| CERT-03 left open in REQUIREMENTS.md (checkbox and traceability) | 06-05 lists CERT-03 for P-08 (no unbounded module cache); marking it now would claim a part not yet delivered | Mark CERT-03 complete after this plan |
| RED stubs (`rules.py` returning `()`/`None`, `MAX_CERT_HOSTS` in `const.py`) were kept out of the RED commits | RED commits stay test-only; the stub only made the RED run assertion-based instead of an import error | Commit stubs with the tests |
| Removed planning references (BLOCKER #1, D-06) only from the class and method docstrings this plan touched; the planning references in the module docstring of `cert_coordinator.py` stay | Plan step 2 scopes M22 cleanup to class and method docstrings; the module docstring is rewritten by later plans that change the probe | Rewrite the whole module docstring now |

## Deviations from Plan

None - plan executed as written. The extra normalization rules above are recorded as worker decisions (they tighten, never loosen, the plan's skip rules).

## Requirement status

CERT-03 is **not** marked complete in REQUIREMENTS.md: this plan delivers the `extract_hosts` and the 200-host cap parts (A-12, P-07, S-07); the "no module-level cache grows without bound" part (P-08) belongs to plan 06-05, which also lists CERT-03. `requirements.mark-complete CERT-03` was run and then reverted for this reason; 06-05 should mark it.

## Assumptions (carried from the plan)

- A grouped negation such as ``!(Host(`a`) || Host(`b`))`` is not detected; those hosts stay in the set.

## User-visible changes (for the Phase 8 CHANGELOG)

- Certificate entities are now created for every host of a Traefik v2 multi-argument rule (``Host(`a`, `b`)``) and of v3 `||` rules, not only for single-host rules.
- `HostRegexp`, `HostSNI`, `HostHeader`, wildcard, template and negated rule names are no longer probed. Internationalized host names are probed in their IDNA (`xn--`) form.
- At most 200 hosts are checked per certificate cycle; when the limit cuts hosts, one warning per cycle states how many hosts are not checked.

## Known Stubs

None.

## Threat Flags

None. T-06-01 (cap) and T-06-02 (literal Host() only, charset + IDNA, precompiled regexes, no growing state) are mitigated as planned; no new network, auth or file surface.

## Next Phase Readiness

- 06-02 can rely on `rules.normalize_host` for API certificate names (same normalization as the probe host set).
- `_collect_hosts()` returns `tuple[str, ...]`; the probe call and port 443 are unchanged for 06-02..06-05.

## Self-Check: PASSED

- FOUND: custom_components/traefik_proxy/rules.py, tests/test_rules.py
- FOUND commits: 9b813ee, d45c008, a7e4fef, 3850a69 (ancestors of HEAD)
