---
phase: 08-marketplace-release-readiness
fixed_at: 2026-11-15T23:30:00Z
review_path: .planning/phases/08-marketplace-release-readiness/08-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 08: Code Review Fix Report

**Fixed at:** 2026-11-15T23:30:00Z
**Source review:** .planning/phases/08-marketplace-release-readiness/08-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (CR-01, WR-01..WR-04; fix scope `critical_warning`)
- Fixed: 5
- Skipped: 0
- Out of scope (left for the disposition ledger): IN-01..IN-06

Execution mode: sequential, directly in the pinned project root
(`feat/marketplace-polish` linked worktree). No temporary review-fix worktree
was created, as the orchestrator instructed. The root-pin guard ran before the
first edit and before every commit. `.planning/config.json` and
`.planning/state.json` were not staged. No `git stash` was used.

## Fixed Issues

### CR-01: `make hacs-action` hands the developer's full `gh` token to a mutable third-party image

**Files modified:** `Makefile`, `scripts/hacs_action_local.py`, `.planning/phases/08-marketplace-release-readiness/08-LOCAL-VALIDATION.md`, `.planning/phases/08-marketplace-release-readiness/08-DRAFT-PR.md`
**Commit:** 407b55f
**Applied fix:**
- The target no longer calls `gh auth token`. It reads the opt-in variable
  `HACS_ACTION_TOKEN` and passes it to the container by name only
  (`INPUT_GITHUB_TOKEN="$$HACS_ACTION_TOKEN" docker run -e INPUT_GITHUB_TOKEN`).
  If the variable is unset, the target exits 2 with a hint: "fine-grained,
  read-only, public repositories".
- `HACS_IMG` is pinned by digest:
  `ghcr.io/hacs/action@sha256:187499a09c5d41f9f0d42ff80d203ed87b974c028290140913b61e005fb0aab2`.
  This is the current `:main` digest and the same digest the 08-08 overlay
  probes used. It was resolved read-only through the anonymous ghcr.io token
  endpoint (no credentials). `--pull always` is dropped.
- An `EXIT` trap removes the harness temp directory, also when
  `git ls-files`, `cp` or `docker run` fails. The trap uses `rm -f` on the two
  known files plus `rmdir`, not `rm -rf`. A shell check confirmed that the
  trap keeps the exit status.
- The help text, the harness docstring, the token paragraph and "To unblock"
  in 08-LOCAL-VALIDATION.md, and the manual follow-up step in 08-DRAFT-PR.md
  now describe `HACS_ACTION_TOKEN`.

**Verification:** `make -n hacs-action` (dry run) and `make help`. Per the
binding rule, `make hacs-action` was not executed, and no credential was read.

**Decision:** an empty or anonymous token is not supported. The target fails
fast when the token is unset.
- Reason: research F2 and 08-LOCAL-VALIDATION show that the action refuses to
  run without `INPUT_GITHUB_TOKEN` ("No GitHub token found"). The reviewer's
  "anonymous run" would fail inside the container with a less clear message.
- Alternative: patch anonymous GitHub access into the overlay. Rejected,
  because it changes what the official validators run.

### WR-01: Diagnostics leak secret-bearing `HeaderRegexp`/`QueryRegexp` values through router `errors`

**Files modified:** `custom_components/traefik_proxy/rules.py`, `custom_components/traefik_proxy/diagnostics.py`, `tests/test_rules.py`, `tests/test_diagnostics.py`, `README.md`, `CHANGELOG.md`
**Commit:** dd4e3f4
**Status:** fixed: requires human verification (redaction logic)
**Applied fix (test-first; the new tests failed before the change):**
- `rules.rule_secret_values(rule)` returns the unquoted values that
  `redact_rule` hides. For a v2 `Query(`key=value`)` it returns the value
  only. It returns `frozenset()` for an empty rule and `None` for an
  unparsable rule. `_redact_tokens` now collects these values during the
  existing single parse.
- `diagnostics._redact_error` now fails closed. It redacts the whole error in
  any of these cases:
  - the rule is unparsable (its secrets are unknown);
  - text outside the verbatim rule holds a matcher call (the old behaviour);
  - the rule hides values, and text outside the verbatim rule holds one of
    them or any backtick or double quote.

  Go regexp errors quote the whole value or a fragment of it in backticks, so
  checking for quote characters also catches fragments.
- Tests:
  - The reviewer's case end-to-end: `HeaderRegexp` with
    `missing closing ): `^s3cr3t-(``. The download contains `["**REDACTED**"]`
    and no `s3cr3t`, while the entity attribute keeps the raw error (D-29).
  - A 10-case table for `_redact_error` and an 11-case table for
    `rule_secret_values`.
- README (Diagnostics) and CHANGELOG (Security) state that an error which may
  quote such a value is replaced as a whole. Entity attributes are unchanged
  (D-29/W76).

**Decision:** for routers whose rule hides values, any quoted text outside
the rule also redacts the error. This includes harmless text such as
`the service "x@docker" does not exist`.
- Reason: fail closed. Go/Traefik may quote only a fragment of the value
  (for example `invalid character class range: `z-a``), and substring checks
  on full values miss fragments.
- Cost: less diagnostic detail, and only for routers with Header/Query
  values. Errors of host/path-only routers stay readable.
- Alternative: an allow-list of known-safe Traefik error forms. Rejected as
  brittle across Traefik v2 and v3.

### WR-02: Probe mode connects only to the first resolved address (regression for IPv6-first or multi-address hosts)

**Files modified:** `custom_components/traefik_proxy/cert_coordinator.py`, `tests/test_cert_coordinator.py`, `CHANGELOG.md`
**Commit:** ca1f5eb
**Status:** fixed: requires human verification (connection fallback logic)
**Applied fix (test-first; 4 of the 6 new tests failed before the change):**
- `_async_resolve_connect_host` is renamed to
  `_async_resolve_connect_addresses`. It still resolves once per cycle
  (08-02 intent) and returns every address de-duplicated, in getaddrinfo
  order (RFC 6724). An IP literal is a one-element list.
- `_async_probe_host` tries the addresses in order, as
  `asyncio.open_connection(<name>)` did before phase 08:
  - It moves on to the next address only after `REFUSED`, `TIMEOUT` or
    `OSERROR`.
  - Any other result ends the probe, for example an SSL or parse failure or
    a certificate.
  - If no address connects, the last failure is the result.
- Tests:
  - IPv6-first stub: `2001:db8::80` is refused and `192.0.2.80` works. All
    hosts get certificates, and each new cycle resolves again and starts in
    resolver order.
  - All addresses fail (parametrized over refused, timeout and oserror): the
    result is the last failure.
  - An SSL failure does not fall back.
  - Duplicate addresses are tried once.
- The CHANGELOG probe entry mentions the fallback.

**Decision:** an address that connects after an earlier one failed moves to
the front of the cycle's shared address list.
- Reason: without this, every host of the cycle would first wait out a
  black-holed AAAA address, up to `TLS_SEMAPHORE`-bounded batches × the
  handshake timeout.
- The reordering is per cycle only; the next cycle resolves again.
- Each address attempt has its own handshake timeout, as each
  `open_connection` attempt had before. The worst case per host is
  N addresses × timeout.
- Alternatives:
  - Prefer the address family that aiohttp reached. Rejected because aiohttp
    does not expose that family.
  - A single overall timeout. Rejected because a first black-holed address
    would use up the whole budget.

### WR-03: SHA pins of `hacs/action` and `home-assistant/actions/hassfest` do not pin the executed code

**Files modified:** `.github/workflows/validate.yml`, `Makefile`, `.planning/phases/08-marketplace-release-readiness/08-LOCAL-VALIDATION.md`
**Commit:** b17dda4
**Applied fix:**
- validate.yml: the header and a comment at each of the two action steps now
  say exactly what is frozen. The SHA pin freezes only the action wrapper.
  hassfest runs `ghcr.io/home-assistant/hassfest:latest`, hacs/action runs
  `ghcr.io/hacs/action:main`, and every job has `permissions: {}`. The CI
  actions were not replaced, as instructed.
- Makefile: `HASSFEST_IMG` is pinned by digest:
  `ghcr.io/home-assistant/hassfest@sha256:da6522993280166fe072704989a2b4c33e639e8ceb69c8ab6ad7ec5045c1a1e3`.
  This is the current `:latest` digest, the same image (HA 2026.11.1) that
  08-08 and 08-13 ran. It was resolved anonymously.
- `make hassfest` mounts the tree read-only (`:ro`) and no longer uses
  `--pull always`. The comments next to both image variables say that CI runs
  the moving tags.

**Verification:** `make hassfest` ran once in a throwaway `--rm` container in
the main checkout. Exit 0, `Integrations: 1` / `Invalid integrations: 0`, so
hassfest needs no write access. `git status` was clean apart from the
pre-existing files. Docker cleanup: `docker ps -a`, `docker network ls` and
`docker volume ls` match `docker-baseline-phase8.txt` exactly (7 containers;
networks bridge, host, none and winboat_default; 6 volumes). The re-run is
recorded in 08-LOCAL-VALIDATION.md.

### WR-04: CI lint and test jobs install dev dependencies without a lock (`uv.lock` is git-ignored)

**Files modified:** `.gitignore`, `uv.lock`, `.github/workflows/validate.yml`, `Makefile`, `.pre-commit-config.yaml`
**Commit:** 759874c
**Applied fix:**
- `uv.lock` is removed from `.gitignore` and committed. Before committing,
  `uv lock --check` passed. The lock has 146 packages, including
  `homeassistant` and `pytest-homeassistant` 2026.11.1, `ruff` 0.17.5,
  `mypy` 2.4.1 and `pytest` 9.0.3.
- CI: the lint and test jobs run `uv sync --locked`, and the workflow-level
  `env: UV_LOCKED: "1"` makes every `uv run` refuse a stale lock.
- Makefile: `export UV_LOCKED := 1` makes `make test`, `make lint` and the
  other targets behave like CI. The `run:` command strings stay identical to
  the Makefile's.
- `UV_LOCKED` was checked on a scratch copy: a stale lock fails with
  "To update the lockfile, run `uv lock`".
- `check-added-large-files` excludes `^uv\.lock$`, because the lock is
  560 KB and the limit is 500 KB.

**Decision check:** no recorded decision conflicts with this.
- 08-RESEARCH F4 ("use the requirements-file approach") applies only to the
  minimum-HA lock, which stays unchanged.
- The Phase 01 plan ignored `uv.lock` only "until releases begin", which is
  now.
- The project CLAUDE.md already lists `uv.lock` as committed.
- The reviewer's optional separate `uv sync --upgrade` nightly job was not
  added. Reason: it is not in scope, and Dependabot or a manual `uv lock -U`
  covers upgrades.
- Alternative: drop `schedule:`. Rejected, because the nightly run (M9) still
  catches HA-side breakage in the min-HA job and in the moving validator
  images.

## Gates after all fixes (main checkout, not a worktree)

| Gate | Result |
|---|---|
| `uv run pytest -q` | 1180 passed, 5 warnings; coverage 99.31 % (gate 99 % reached) |
| `uv run ruff check custom_components tests` | All checks passed |
| `uv run ruff format --check custom_components tests` | 50 files already formatted |
| `uv run mypy --strict custom_components/traefik_proxy` | Success: no issues found in 16 source files |
| `make test-min-ha` (hashed lock, HA 2026.11.0, `UV_LOCKED=1` exported) | 1180 passed, coverage 99.31 % |
| `uvx pre-commit run --all-files` | exit 0, 13 hooks passed |
| `make hassfest` (digest-pinned, read-only mount) | exit 0, Invalid integrations: 0 |
| `make hacs-action` | not run (REL-07 deferred to CI by user decision) |

Before the fixes, the 08-13 run had 1152 tests; the 28 new tests come from
WR-01 (22) and WR-02 (6).

---

_Fixed: 2026-11-15T23:30:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
