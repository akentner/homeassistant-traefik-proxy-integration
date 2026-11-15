---
phase: 08-marketplace-release-readiness
plan: 06
subsystem: tooling, testing, ci-prep
tags: [uv, pip-compile, hashed-lock, pytest-homeassistant, coverage, fail_under, pre-commit, ruff, mypy, makefile, hassfest]

requires:
  - phase: 08-marketplace-release-readiness
    provides: final integration code and brand files (08-01..08-05) on which coverage is measured and pre-commit runs
provides:
  - hashed minimum-HA test lock (.github/requirements-min-ha.in/.txt, 123 packages) and make min-ha-lock / make test-min-ha
  - coverage measured on custom_components.traefik_proxy with fail_under = 99 on every coverage run
  - filterwarnings error::SyntaxWarning
  - pre-commit config on python3.14 targeting traefik_proxy, ruff/mypy via uv run, second --all-files run clean
  - scripts/hassfest_checks.py strings-shape without the `entity` false alarm
  - Makefile command strings lint/typecheck/test/test-min-ha/pre-commit for 08-07 to copy into validate.yml
affects: [08-07 (validate.yml test-min-ha + lint/typecheck/test jobs adopt these commands), 08-08 (Makefile Docker targets), 08-13 (CHANGELOG developer notes)]

actuals:
  tokens: 70000    # chars/4 over the realized diff (280935 chars); 62000 of it is the generated 248 KB lock, hand-written part about 7300
  tasks: 2
  commits: 2
plan_head_before: 72d9f17777b4f9d7040537ad2db33ead51aeb631
plan_head_after: b6116e5e4c8b3647fbf6f817c32ecce82e39f981

tech-stack:
  added: []
  patterns:
    - "Minimum-HA stack = committed hashed uv pip compile lock + uv pip sync --require-hashes into a fresh venv"
    - "pre-commit ruff/mypy as repo: local `uv run` hooks so pre-commit = Makefile = CI"
    - "Every coverage run is gated by [tool.coverage.report] fail_under; partial runs need --no-cov"

key-files:
  created:
    - .github/requirements-min-ha.in
    - .github/requirements-min-ha.txt
  modified:
    - Makefile
    - .gitignore
    - pyproject.toml
    - .pre-commit-config.yaml
    - scripts/hassfest_checks.py
    - scripts/pre-commit
    - README.md (end-of-file newline only)
    - hacs.json (end-of-file newline only)
    - docs/icon.svg (end-of-file newline only)
    - .claude/skills/spike-findings-homeassistant-traefik-integration/** (14 files, end-of-file newline only)

key-decisions:
  - "fail_under = 99: measured 2123 statements / 15 missed = 99.29 % line coverage on custom_components.traefik_proxy, floored (D-10/D-32)"
  - "SyntaxWarning filter kept global: no third-party collection error in the fresh min-HA venv, so no scoping needed (P3)"
  - "pre-commit end-of-file fixes committed together with the config in the Task 2 commit (17 files, final newline only)"

patterns-established:
  - "Partial pytest runs: use --no-cov, otherwise the coverage gate fails them by design"

requirements-completed: [REL-04]

coverage:
  - id: D1
    description: "make test-min-ha builds a fresh .venv-min-ha from the committed hashed lock and passes the suite on HA 2026.11.0"
    requirement: REL-04
    verification:
      - kind: integration
        ref: "rm -rf .venv-min-ha && make test-min-ha (1144 passed, coverage 99.29 % reached)"
        status: pass
      - kind: other
        ref: "grep -c '^pytest-homeassistant==2026.11.0' .github/requirements-min-ha.txt == 1; 2832 hashes; 248217 bytes"
        status: pass
    human_judgment: false
  - id: D2
    description: "Coverage measured on custom_components.traefik_proxy with fail_under = 99; a partial run fails the gate"
    requirement: REL-04
    verification:
      - kind: other
        ref: "uv run pytest -q (Required test coverage of 99.0% reached. Total coverage: 99.29%)"
        status: pass
      - kind: other
        ref: "uv run pytest -q tests/test_rules.py exits 1 (FAIL Required test coverage of 99.0% not reached. 32.36%)"
        status: pass
    human_judgment: false
  - id: D3
    description: "pre-commit on python3.14 targeting traefik_proxy runs and is idempotent; hassfest_checks all exits 0"
    requirement: REL-04
    verification:
      - kind: other
        ref: "uvx pre-commit run --all-files (2nd run: all Passed, rc 0) && git diff --exit-code -- ':!.planning'"
        status: pass
      - kind: other
        ref: "uv run python scripts/hassfest_checks.py all (rc 0)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Makefile carries the CI-aligned command strings (lint, typecheck, test, test-min-ha, min-ha-lock, pre-commit)"
    requirement: REL-04
    verification:
      - kind: other
        ref: "grep acceptance criteria Task 1 + Task 2 (all PASS)"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-11-15
status: complete
---

# Phase 8 Plan 06: Release-grade local tooling Summary

**Hashed `uv pip compile` lock for the HA 2026.11.0 test stack behind `make test-min-ha`, coverage gate `fail_under = 99` on `custom_components.traefik_proxy`, SyntaxWarning-as-error, and pre-commit hooks on Python 3.14 that actually check the integration with the same `uv run` ruff/mypy as CI.**

## Performance

- **Duration:** about 8 min
- **Started:** 2026-11-15T20:19:40Z
- **Completed:** 2026-11-15T20:27:30Z
- **Tasks:** 2 (both committed)
- **Files modified:** 25 (8 tooling/config files + 17 end-of-file-newline fixes)

## Accomplishments

- `.github/requirements-min-ha.in` (`pytest-homeassistant==2026.11.0`, `pytest-cov>=7.0.0`) and the hashed lock `.github/requirements-min-ha.txt`.
- `make min-ha-lock` (compile for 3.14.2 / x86_64-manylinux_2_28, `UV_HTTP_TIMEOUT=300`) and `make test-min-ha` (`uv venv --clear` -> `uv pip sync --require-hashes` -> `pytest -q tests`, no addopts override). `.venv-min-ha/` ignored.
- `pyproject.toml`: project name `homeassistant-traefik-proxy-integration` (version stays 1.0.0), `--cov=custom_components.traefik_proxy` (IN-07 fixed, the "No data to report" warning is gone), `fail_under = 99`, `filterwarnings = ["error::SyntaxWarning"]`.
- `.pre-commit-config.yaml`: python3.14, top-level `exclude: ^(\.planning/|tests/fixtures/)`, pre-commit-hooks v6.0.0, ruff-check/ruff-format/mypy as `repo: local` `uv run` hooks, hassfest hooks via `uv run python`, all `files:` on `custom_components/traefik_proxy` (WR-04 fixed).
- `scripts/hassfest_checks.py`: forbidden top-level keys only `{"reauth", "reconfigure"}`; `all` exits 0 on HEAD.
- `scripts/pre-commit`: mypy on `custom_components/traefik_proxy`, ruff only on staged files under `custom_components/traefik_proxy/` or `tests/`.
- Makefile: `lint`, `typecheck`, `test`, `test-min-ha`, `min-ha-lock`, `pre-commit` with the CI command strings; `test-cov` dropped; `install-pre-commit` uses `uv tool install` only.

## Lock statistics

| Item | Value |
|---|---|
| Packages | 123 |
| Lines / size | 3210 lines / 248217 bytes (limit 512000) |
| `--hash=sha256:` lines | 2832 |
| Key pins | homeassistant 2026.11.0, pytest-homeassistant 2026.11.0, pytest 9.0.3, pytest-cov 7.1.0, coverage 7.17.3, respx 0.23.1 |
| `make min-ha-lock` | about 2.5 s (uv cache warm) |
| `make test-min-ha` (fresh venv) | 35 s total, 123 packages installed, Python 3.14.2, 1144 passed, coverage 99.29 % reached |

## Coverage

- Measured: `TOTAL 2123 15 99%` = 99.29 % line coverage on `custom_components.traefik_proxy`.
- `fail_under = 99` (floor; matches D-32).
- Gate bites: `uv run pytest -q tests/test_rules.py` exits 1 with "FAIL Required test coverage of 99.0% not reached. Total coverage: 32.36%".

## Task Commits

1. **Task 1 (tracer): hashed minimum-HA lock + make test-min-ha** - `a0b0cd8` (build)
2. **Task 2: coverage gate, SyntaxWarning filter, project name, pre-commit on traefik_proxy** - `b6116e5` (build)

Tracer feedback gate: `end-of-phase` mode with automated-only `<verify>`; re-ran `make test-min-ha` and `uv run pytest -q`, both green, then expanded to Task 2.

## Quality Gates (after Task 2)

| Gate | Result |
|---|---|
| `uv run pytest -q` (dev env, HA 2026.11.1) | 1144 passed, coverage 99.29 % reached, no "Lingering" |
| `uv run ruff check custom_components tests` | All checks passed |
| `uv run ruff format --check custom_components tests` | 49 files already formatted |
| `uv run mypy --strict custom_components/traefik_proxy` | no issues in 16 source files |
| `uv run python scripts/hassfest_checks.py all` | passed (rc 0) |
| `uvx pre-commit run --all-files` (2nd run) | all hooks Passed, rc 0, no diff |
| `rm -rf .venv-min-ha && make test-min-ha` (HA 2026.11.0 lock) | 1144 passed, coverage reached, no SyntaxWarning collection error |
| `ha2611-venv/bin/python -m pytest -q -o addopts="-p no:respx" tests` (HA 2026.11.0) | 1144 passed |

After Task 1 (before the gate existed): `make test-min-ha` 1144 passed (36 s) and `uv run pytest -q` 1144 passed.

## Acceptance Criteria

- Task 1: pin count 1; 2832 hashes (>100); size 248217 < 512000; `uv pip sync ... --require-hashes` string in Makefile; `min-ha-lock:` and `test-min-ha:` targets; `.venv-min-ha/` line in `.gitignore` - all PASS.
- Task 2: name/cov/fail_under; `error::SyntaxWarning`; `custom_components/traefik_proxy` count 7 (>=4), `custom_components/traefik/` count 0; `python: python3.14`; `mypy --strict custom_components/traefik_proxy` in `scripts/pre-commit`; `uv run pytest -q tests` and typecheck string in Makefile - all PASS.

## pre-commit provenance (D-32)

- `uvx pre-commit` = pre-commit **4.7.0**, homepage github.com/pre-commit/pre-commit. Ephemeral tool run, nothing installed; `pre-commit install` was NOT run (hooks dir shared with the main checkout).
- Remote hook repo: `github.com/pre-commit/pre-commit-hooks` `v6.0.0` (pre-commit's own hook collection).

## Worker Decisions

| Decision | Reason | Alternative not taken |
|---|---|---|
| ruff/mypy pre-commit hooks as `repo: local` with `uv run` (planner) | Same tool versions as CI and Makefile (P5) | Bump ruff-pre-commit `rev` by hand |
| pre-commit excludes `.planning/` and `tests/fixtures/` (planner) | Planning docs not shipped; fixtures byte-stable | Let fixers rewrite them |
| `aioresponses` stays in the dev group (planner) | Dead but outside D-01..D-32; post-1.0 cleanup | Remove now |
| Local tooling and CI are separate plans (planner) | 08-07 copies these Makefile strings into validate.yml | One plan |
| End-of-file fixes from the first pre-commit run go into the Task 2 commit (worker) | Plan step 6 says commit them in this task; one commit per task keeps the plan atomic | Separate `style(08-06)` commit |
| `.claude/skills/...` files are not excluded from pre-commit (worker) | Only `.planning/` and `tests/fixtures/` are named in the plan; the fixes are trailing-newline only and harmless | Add `.claude/` to the top-level exclude |
| SyntaxWarning filter left unscoped (worker) | The fresh min-HA venv produced no third-party collection error, so the plan's scoping fallback was not needed | Scope to project modules |
| `install-hooks` target left as is (worker) | It copies into `.git/hooks/`, which is a file in a linked worktree; out of scope here and not run | Rewrite it to use `git rev-parse --git-path hooks` |

## Deviations from Plan

None - plan executed as written. The only extra file changes are the end-of-file-fixer results the plan anticipated (P6): a final newline added to `README.md`, `hacs.json`, `docs/icon.svg` and 14 files under `.claude/skills/spike-findings-homeassistant-traefik-integration/`.

**Total deviations:** 0.

## Docker

No Docker used in this plan; no containers, networks or volumes created (cleanup check not applicable).

## Known Stubs

None.

## Threat Flags

None. T-08-15 mitigated (hashed lock + `--require-hashes` in a fresh venv), T-08-33 mitigated (exclude + clean second run), T-08-SC mitigated (ephemeral `uvx pre-commit`, provenance above, no package added to the integration or pyproject).

## User-visible changes (for CHANGELOG)

None for end users. Developer-facing:
- The minimum-HA test stack (HA 2026.11.0) is a committed, hash-checked lock; `make test-min-ha` reproduces the CI job.
- Every full test run enforces 99 % line coverage on `custom_components.traefik_proxy`; a SyntaxWarning fails collection.
- pre-commit hooks now actually check the integration (Python 3.14, same ruff/mypy as CI); `make pre-commit` runs them without installing anything.

## Next Phase Readiness

- 08-07 can copy these strings into validate.yml: `uv run ruff check custom_components tests`, `uv run ruff format --check custom_components tests`, `uv run mypy --strict custom_components/traefik_proxy`, `uv run pytest -q tests`, and the three test-min-ha commands (drop the old `-o addopts="-p no:respx"` override and the unlocked install).
- Partial pytest runs (e.g. in later plans' verify steps) need `--no-cov`.

## Self-Check: PASSED

- FOUND: .github/requirements-min-ha.in, .github/requirements-min-ha.txt, Makefile, .pre-commit-config.yaml, pyproject.toml, scripts/hassfest_checks.py, scripts/pre-commit
- FOUND commits: a0b0cd8, b6116e5 (ancestors of HEAD); `git rev-list --count 72d9f17..HEAD` = 2

---
*Phase: 08-marketplace-release-readiness*
*Completed: 2026-11-15*
