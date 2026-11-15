---
phase: 07-config-flow-ha-2026-11-baseline-observability
fixed_at: 2026-11-15T16:30:00Z
review_path: .planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
deferred: 8
status: all_fixed
---

# Phase 07: Code Review Fix Report

**Fixed at:** 2026-11-15T16:30:00Z
**Source review:** `.planning/phases/07-config-flow-ha-2026-11-baseline-observability/07-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (selected by the orchestrator: WR-01, WR-02, WR-03, IN-01, IN-02, IN-06)
- Fixed: 6
- Skipped: 0
- Deferred to Phase 8: 8 (WR-04, WR-05, WR-06, WR-07, IN-03, IN-04, IN-05, IN-07)

| Finding | Status | Commit | Regression test (failed before the fix) |
|---|---|---|---|
| WR-01 | fixed: requires human verification | `79a08fd` | `test_changed_target_requires_secret_again[changed-host/changed-port/https-to-http]`, `test_changed_host_requires_basic_credentials_again`, `test_unusable_stored_url_requires_secret_again` (5 RED). Unchanged URL: `test_same_host_empty_token_keeps_stored_token`, `test_same_target_with_explicit_default_port_keeps_stored_token` |
| WR-02 | fixed: requires human verification | `c915c15` | `test_user_step_legacy_unique_id_owner_aborts_without_request[same-url/host-case-trailing-slash]`, `test_reconfigure_to_legacy_unique_id_owner_aborts` (3 RED); `test_user_step_legacy_entry_on_other_port_is_no_owner` (guard against over-matching) |
| WR-03 | fixed: requires human verification | `b0a8aff` | `test_failing_setup_still_raises_issue[not-ready/auth-failed]` (2 RED); `test_failing_setup_over_https_raises_no_issue` |
| IN-01 | fixed | `120e1f0` | `test_user_step_rejected_credentials_mark_their_field` (4 cases), `test_flow_error_keys_have_texts[en/de]`, `test_local_credential_rejection_does_not_blame_traefik[en/de]` (8 RED) |
| IN-02 | fixed | `13bf364` | Comment only, so no test can fail first. The behaviour is already pinned by `test_incomplete_userinfo_becomes_none_and_warns` |
| IN-06 | fixed | `8d9dd22` | Test-only fix. Mutation check: with `config_entry_id=` dropped locally, both new assertions fail |
| WR-04 | deferred to Phase 8 | - | Out of scope (07-CONTEXT "Out of scope (Phase 8)" / ROADMAP Phase 8 SC3) |
| WR-05 | deferred to Phase 8 | - | Out of scope |
| WR-06 | deferred to Phase 8 | - | Out of scope |
| WR-07 | deferred to Phase 8 | - | Out of scope |
| IN-03 | deferred to Phase 8 | - | Out of scope |
| IN-04 | deferred to Phase 8 | - | Out of scope (necessity) |
| IN-05 | deferred to Phase 8 | - | Out of scope (necessity) |
| IN-07 | deferred to Phase 8 | - | Out of scope (already a Phase 8 carry-over) |

## Fixed Issues

### WR-01: Reconfigure re-sends stored secrets to a changed host or scheme without re-entry

**Files modified:** `custom_components/traefik_proxy/config_flow.py`, `custom_components/traefik_proxy/translations/en.json`, `custom_components/traefik_proxy/translations/de.json`, `tests/test_reconfigure.py`, `tests/test_repairs.py`
**Commit:** 79a08fd
**Applied fix:**
- New helper `_same_target(old_url, new_url)`: true only when the scheme and `url_unique_id` (host:port) are equal. A stored URL without a usable host:port is never the same target.
- The stored-credential fallback now needs an unchanged auth type and the same target. Otherwise every empty credential field is `required`, which is the flow's existing pattern.
- en/de field hints now say "while the address (scheme, host and port) and the authentication type stay the same".
- `test_reconfigure_fix_deletes_issue[to-https]` now submits the token. http to https is a scheme change, so the token must be entered again.
- Not changed: the review also mentions a `verify_ssl` flip. The orchestrator's scope names only scheme and host:port, so a `verify_ssl` flip on the same target still uses the stored secret.

### WR-02: Duplicate detection misses entries that still have a legacy host-only unique_id

**Files modified:** `custom_components/traefik_proxy/config_flow.py`, `tests/test_config_flow.py`, `tests/test_reconfigure.py`
**Commit:** c915c15
**Applied fix:**
- New helper `_owns_target(entry, unique_id)` returns true in two cases:
  - the entry's unique_id equals the new `host:port`;
  - the entry is on the legacy format (unique_id equals the bare host of its stored URL) and its stored URL resolves to the same `host:port`. That is the id its migration would move it to.
- The user step checks it after `_abort_if_unique_id_configured()`. The reconfigure loop uses it in place of the plain equality check.
- Deviation from the review snippet: the snippet aborts whenever `unique_id == bare host`. That would wrongly block a second Traefik on another port of the same host, which M21 allows. The port-aware check keeps M21 semantics.

### WR-03: insecure_credentials notice is absent while a failing setup keeps sending credentials over HTTP

**Files modified:** `custom_components/traefik_proxy/__init__.py`, `tests/test_repairs.py`
**Commit:** b0a8aff
**Applied fix:**
- `_async_check_insecure_credentials` now runs right after `build_api_client(...)`, before the first refresh.
- Deviation from the review: the review claimed that `async_on_unload` callbacks survive a failed setup. They do not. HA 2026.11 `config_entries.py` runs `_async_process_on_unload` in the `finally` of a failed `async_setup_entry`. I confirmed this by applying only the review's move: the RED tests stayed red.
- The issue deletion therefore moved from `entry.async_on_unload` to `async_unload_entry`, after `async_unload_platforms_or_raise`. The unload cleanup is kept.
- The `config_entry_id=` binding is kept: removal clears the issue and disabling hides it.
- A reload of a retrying entry re-evaluates the issue in the next setup. The setup and unload docstrings were updated.

### IN-01: Field-level `invalid_auth` says "Traefik rejected the credentials" when Traefik was never contacted

**Files modified:** `custom_components/traefik_proxy/config_flow.py`, `custom_components/traefik_proxy/translations/en.json`, `custom_components/traefik_proxy/translations/de.json`, `tests/test_config_flow.py`
**Commit:** 120e1f0
**Applied fix:**
- New error key `invalid_credential_format` (en and de), for a credential rejected locally (a colon in the username, or a control character). It names the cause and does not blame Traefik.
- `invalid_auth` stays for a 401/403 from Traefik.
- Not changed: the unknown-`auth_type` branch (`{auth_type: "invalid_auth"}`) is unreachable behind the SelectSelector. Removing it is IN-05, which is deferred to Phase 8.

### IN-02: Migration comment overstates "aiohttp refused such URLs"

**Files modified:** `custom_components/traefik_proxy/__init__.py`
**Commit:** 13bf364
**Applied fix:** The comment now says two things:
- aiohttp refused a token next to URL credentials;
- incomplete URL credentials, which aiohttp sent as basic auth with an empty password, cannot be mapped to basic auth.

### IN-06: `test_removal_leaves_no_issue` does not test the `config_entry_id` binding it is meant to cover

**Files modified:** `tests/test_repairs.py`
**Commit:** 8d9dd22
**Applied fix:**
- The test now removes an entry in setup retry. Since WR-03, the issue is raised before the first refresh.
- It asserts that `async_unload_entry` is not called and that the issue carries `config_entry_id`, then asserts that removal leaves no issue behind.
- Mutation check: with `config_entry_id=` dropped, both the binding assertion and the final assertion fail.

## Deferred (Phase 8)

WR-04, WR-05, WR-06, WR-07, IN-03, IN-04, IN-05 and IN-07 are not changed here. They belong to Phase 8 per 07-CONTEXT "Out of scope (Phase 8)" and ROADMAP Phase 8 SC3.

## Verification

All gates ran in the main checkout of the linked worktree (`feat/marketplace-polish`). No temporary review-fix worktree was created: sequential executor rules and the user's worktree rule. All gates ran once, with no reruns (M39).

| Gate | Result |
|---|---|
| `uv run pytest -q` | 1050 passed |
| HA 2026.11.0 venv `python -m pytest -q -o addopts="-p no:respx" tests` | 1050 passed |
| `uv run ruff check custom_components tests` | clean |
| `uv run ruff format --check custom_components tests` | 47 files already formatted |
| `uv run mypy --strict custom_components/traefik_proxy` | no issues (16 files) |
| config_flow coverage, 07-08 gate (4 flow test modules, `--fail-under=100`) | 100 % (213 stmts, 0 missed) |
| config_flow coverage, orchestrator command (3 modules, `--cov-fail-under=100`) | 100 %, exit 0 |

---

_Fixed: 2026-11-15T16:30:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
