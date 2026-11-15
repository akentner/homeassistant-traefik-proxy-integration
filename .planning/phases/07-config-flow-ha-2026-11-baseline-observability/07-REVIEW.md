---
phase: 07-config-flow-ha-2026-11-baseline-observability
reviewed: 2026-11-15T15:20:18Z
depth: standard
files_reviewed: 40
files_reviewed_list:
  - .github/workflows/validate.yml
  - .pre-commit-config.yaml
  - custom_components/traefik_proxy/__init__.py
  - custom_components/traefik_proxy/api.py
  - custom_components/traefik_proxy/binary_sensor.py
  - custom_components/traefik_proxy/cert_coordinator.py
  - custom_components/traefik_proxy/config_flow.py
  - custom_components/traefik_proxy/const.py
  - custom_components/traefik_proxy/coordinator.py
  - custom_components/traefik_proxy/data.py
  - custom_components/traefik_proxy/diagnostics.py
  - custom_components/traefik_proxy/entity.py
  - custom_components/traefik_proxy/entity_manager.py
  - custom_components/traefik_proxy/translations/de.json
  - custom_components/traefik_proxy/translations/en.json
  - hacs.json
  - pyproject.toml
  - scripts/hassfest_checks.py
  - tests/conftest.py
  - tests/test_api.py
  - tests/test_api_pagination.py
  - tests/test_binary_sensor_tls_expiring.py
  - tests/test_cert_coordinator.py
  - tests/test_cert_entity_state.py
  - tests/test_cert_lifecycle.py
  - tests/test_certificates_problem.py
  - tests/test_config_flow.py
  - tests/test_coordinator.py
  - tests/test_devices.py
  - tests/test_diagnostics.py
  - tests/test_entity_manager.py
  - tests/test_init.py
  - tests/test_migration.py
  - tests/test_options_flow.py
  - tests/test_platforms_real_fixtures.py
  - tests/test_reconfigure.py
  - tests/test_repairs.py
  - tests/test_sensor_tls.py
  - tests/test_translations.py
  - tests/test_verify_ssl.py
findings:
  critical: 0
  warning: 7
  info: 7
  total: 14
  necessity: 2
status: issues_found
---

# Phase 07: Code Review Report

**Reviewed:** 2026-11-15T15:20:18Z
**Depth:** standard
**Files Reviewed:** 40
**Status:** issues_found

## Summary

Scope: `git diff 4e4d859..HEAD`. Covered: the config, options, reauth and reconfigure flows, the 1.2 -> 1.3 entry migration, the client's redirect handling, translated exceptions, diagnostics redaction, the repair issue lifecycle, en/de translations, CI and pre-commit. Tests got a lower-priority pass.

What holds up (checked against HA 2026.11.1 in `.venv`):
- **Redirects:** the client never follows them (`api.py:208`). 3xx maps to `TraefikProxyRedirectError` and never reads `Location`.
- **Translations:** `async_update_reload_and_abort` translates `reauth_successful` and `reconfigure_successful` centrally through `translation_domain=homeassistant`, so `en.json` does not need those keys.
- **No secret leakage:** no credential or URL userinfo reaches log messages, exception placeholders, diagnostics or repair placeholders. The invalid-URL cause chain is dropped (`coordinator.py:179`). Diagnostics strip userinfo and redact a URL they cannot parse.
- **Test suite:** 1034 passed in 28.5 s (`-p no:respx`).

No BLOCKER-level defect was found. The main concerns:
- **WR-01:** reconfigure sends stored secrets to a new host or over plain HTTP before the user has re-entered them.
- **WR-02:** duplicate detection misses entries that are still on the legacy host-only unique_id.
- **WR-03:** the `insecure_credentials` notice is missing exactly while a failing setup keeps retrying with credentials over HTTP.
- **WR-04:** the pre-commit gate is broken twice over. Its path regexes never match `traefik_proxy`, and the strings-shape check it would run always fails.
- **WR-05 to WR-07:** CI hygiene (timeouts, unlocked install, unpinned actions).

## Warnings

### WR-01: Reconfigure re-sends stored secrets to a changed host or scheme without re-entry

**File:** `custom_components/traefik_proxy/config_flow.py:499-505`
**Issue:** If the auth type is unchanged, an empty secret field falls back to the stored credential: `stored = entry.data if auth_type == entry.data.get(CONF_AUTH_TYPE) else None`. That fallback ignores whether the URL changed. Two consequences:
- A reconfigure to a different host sends the stored password or token to that host during the probe. A typo or a hostile host is enough.
- A reconfigure from `https://` to `http://` sends the stored secret in cleartext.

In both cases the user never typed the secret. The `insecure_credentials` repair appears only after the fact, and only if the probe succeeded. The same applies to the `verify_ssl` flip in the same form: the stored secret goes to an unverified TLS peer.
**Fix:** Allow the stored-credential fallback only when the security-relevant part of the URL is unchanged:
```python
old = urlsplit(entry.data[CONF_URL])
new = urlsplit(url)
same_target = (old.scheme, url_unique_id(entry.data[CONF_URL])) == (new.scheme, unique_id)
stored = entry.data if same_target and auth_type == entry.data.get(CONF_AUTH_TYPE) else None
```
Also update the `data_description` texts ("Leave empty to keep … while the authentication type stays the same") in en.json and de.json to say "and the address stays the same".

### WR-02: Duplicate detection misses entries that still have a legacy host-only unique_id

**File:** `custom_components/traefik_proxy/config_flow.py:421-422`, `custom_components/traefik_proxy/config_flow.py:495-498`, `custom_components/traefik_proxy/__init__.py:289`
**Issue:** Before 1.3 the unique_id was the bare host (`urlparse(url).hostname`). The new format is `host:port`, but `async_migrate_entry` rewrites it only when an entry is set up. Three cases leave an entry on the old format:
- an entry that is **disabled** during the upgrade (HA never sets up or migrates it);
- an entry that failed before migration;
- an entry whose migration kept the old id because of a collision (`_migrated_unique_id` returns None).

`async_step_user` (`_abort_if_unique_id_configured`) and the reconfigure loop compare only against `host:port`. So a second entry for the same Traefik is accepted. When the disabled entry is later enabled, its migration finds the new owner and keeps the legacy id, and two entries poll the same Traefik. This defeats M21 ("one entry per Traefik").
**Fix:** In both flows, also treat entries whose `unique_id` equals the bare host (legacy format) as owners:
```python
legacy = url_host(url)
for other in self._async_current_entries(include_ignore=False):
    if other.entry_id != current_id and other.unique_id in {unique_id, legacy}:
        return self.async_abort(reason="already_configured")
```
Alternatively, migrate unique_ids for every entry of the domain in `async_setup` (component level), independent of whether the entry is enabled.

### WR-03: insecure_credentials notice is absent while a failing setup keeps sending credentials over HTTP

**File:** `custom_components/traefik_proxy/__init__.py:343`, `custom_components/traefik_proxy/__init__.py:371`
**Issue:** `_async_check_insecure_credentials` runs as the last setup step, after `coordinator.async_config_entry_first_refresh()`. The issue is deleted on unload (`__init__.py:106`). Sequence:
1. A reload or restart deletes the issue.
2. The first refresh raises `ConfigEntryNotReady` (Traefik 5xx, payload error, timeout after connect) or `ConfigEntryAuthFailed`.
3. Setup never reaches the check, so the issue is never raised.

Meanwhile every `ConfigEntryNotReady` retry sends the `Authorization` header over plain HTTP. The security notice therefore disappears exactly when the entry is in a retry loop.
**Fix:** Evaluate the issue right after `build_api_client(...)` succeeds. It depends only on `entry.data`, not on Traefik being reachable:
```python
client = build_api_client(hass, entry)
_async_check_insecure_credentials(hass, entry)
coordinator = TraefikProxyCoordinator(hass, entry)
...
```
`entry.async_on_unload` callbacks registered before a failed setup still run on the next unload or retry, so the lifecycle stays the same.

### WR-04: Pre-commit hooks never fire for the integration, and strings-shape would always fail

**File:** `.pre-commit-config.yaml:36,38,47,58,65`, `scripts/hassfest_checks.py:75`
**Issue:**
- **Regexes never match.** Every integration regex uses `custom_components/traefik/`, but the package is `custom_components/traefik_proxy/`. Verified: `^custom_components/traefik/translations/.*\.json$` does not match `custom_components/traefik_proxy/translations/en.json`. `^(custom_components/traefik|tests)/.*\.py$` does not match `custom_components/traefik_proxy/config_flow.py`. So ruff-check, ruff-format, mypy, manifest-order and strings-shape never run on integration files. Phase 7 edited line 65 and kept the wrong path.
- **strings-shape would always fail.** Phase 7 also changed `check_strings_shape` to scan only `translations/*.json`. That script forbids a top-level `entity` key (`scripts/hassfest_checks.py:75`). `entity` is a valid and required top-level key in translation files, and both en.json and de.json have it. Running `scripts/hassfest_checks.py strings-shape` now exits 1 on HEAD.

Taken together, the gate is silently off. Fixing the regex alone would turn it into a hook that always fails. The decision log lists the false alarm for Phase 8, but the Phase 7 change made it unconditional.
**Fix:**
```yaml
files: ^custom_components/traefik_proxy/translations/.*\.json$
# likewise for the ruff/mypy/manifest hooks:
files: ^(custom_components/traefik_proxy|tests)/.*\.py$
```
```python
forbidden_top = {"reauth", "reconfigure"}  # "entity" is a valid translations key
```

### WR-05: CI jobs have no job-level timeout

**File:** `.github/workflows/validate.yml:12,35,50,65,71`
**Issue:** None of the jobs (`lint`, `test`, `test-min-ha`, `hassfest`, `hacs`) set `timeout-minutes`. This includes the `test-min-ha` job added in this phase. The certificate tests open real sockets (`tls_server` fixture). A hung test or a stuck dependency resolution holds the runner for GitHub's 6-hour default.
**Fix:** Add `timeout-minutes: 15` (or similar) to each job, at least to `test` and `test-min-ha`.

### WR-06: test-min-ha installs an unlocked dependency set

**File:** `.github/workflows/validate.yml:59-61`
**Issue:** `uv pip install "pytest-homeassistant==2026.11.0" "pytest-cov>=7.0.0"` resolves every transitive and test dependency fresh on each run, without a lock. Examples are pytest-asyncio, pytest plugins and `cryptography` for `tests/certgen`. A re-run of the same commit can resolve a different set and pass or fail differently. That works against the stated goal of deterministic CI and release gates (M39). The `-o addopts="-p no:respx"` workaround also suggests that plugin drift already occurs.
**Fix:** Use a lock for the minimum stack, for example a committed `requirements-min-ha.txt` from `uv pip compile` installed with `uv pip sync`. Or use `uv sync --locked` with a dependency-group override that pins `pytest-homeassistant==2026.11.0`.

### WR-07: Third-party actions on moving branches

**File:** `.github/workflows/validate.yml:69`, `.github/workflows/validate.yml:76`
**Issue:** `home-assistant/actions/hassfest@master` and `hacs/action@main` change between two runs of the same commit. `hacs/action` also receives `GITHUB_TOKEN`. This predates Phase 7, but the file is in scope, and M24 requires pinned actions.
**Fix:** Pin both to a full commit SHA, with a trailing comment naming the version, and let Dependabot or Renovate bump them.

## Info

### IN-01: Field-level `invalid_auth` says "Traefik rejected the credentials" when Traefik was never contacted

**File:** `custom_components/traefik_proxy/config_flow.py:292`, `custom_components/traefik_proxy/config_flow.py:306`, `custom_components/traefik_proxy/translations/en.json:64`, `custom_components/traefik_proxy/translations/de.json:64`
**Issue:** `_collect_credentials` sets `errors[<field>] = "invalid_auth"` for a credential that is rejected locally, such as a `:` in the username or a control character. HA renders field errors from `config.error.<key>`, so the field shows "Traefik rejected the credentials…". No request was sent. The trailing sentence hints at the real cause, but the message leads the user to debug the Traefik middleware first.
**Fix:** Add a separate key, for example `invalid_credential_format` ("Contains a character that cannot be sent: a colon in the username or a control character"), for the local rejection. Keep `invalid_auth` for 401/403.

### IN-02: Migration comment overstates "aiohttp refused such URLs"

**File:** `custom_components/traefik_proxy/__init__.py:280-281`
**Issue:** The comment holds for userinfo combined with a token: aiohttp refuses an `Authorization` header together with URL credentials. It does not hold for incomplete userinfo without a token (`http://user@host`). Pre-1.3 code sent `Auth()` with no header, and aiohttp built `BasicAuth(user, "")` from the URL. Such an entry did send credentials, and the migration silently changes it to `none`. The behaviour is acceptable, but the comment misleads future maintainers.
**Fix:** Reword the comment to: "a token next to URL credentials was refused by aiohttp; incomplete URL credentials cannot be mapped to basic auth".

### IN-03: Cert-cycle failure keeps the full client exception chain, unlike the main coordinator

**File:** `custom_components/traefik_proxy/cert_coordinator.py:307-313`
**Issue:** The main coordinator drops the cause of a `TraefikProxyInvalidUrlError` (`_logged_cause`, `coordinator.py:172-179`), because the underlying aiohttp error text can contain the URL. The cert coordinator always chains `from err`. HA logs that chain at DEBUG ("Full error:", `exc_info=True`). With current 1.3 data, no URL with userinfo can reach the client, so this is a consistency gap rather than a live leak.
**Fix:** Reuse the same helper: `raise UpdateFailed(...) from _logged_cause(err)` (import it from `.coordinator`).

### IN-04: Impossible-state guard: `auth_type` branch in `_migrated_entry_data`

**File:** `custom_components/traefik_proxy/__init__.py:120-124`
**Category:** necessity
**Issue:** The 1.2 -> 1.3 step only runs for `minor_version < 3`. No code before this phase wrote `auth_type`: `const.py` at `4e4d859` has no `CONF_AUTH_TYPE`, and the old flows stored `url`, `api_key` and `verify_ssl` only. `async_update_entry(data=…, minor_version=3)` is atomic, so a half-migrated entry cannot exist either. This rests on judgment: the data comes from persisted storage, and a user could hand-edit `core.config_entries`.
**Fix:** Remove the branch together with `test_migration_1_2_keeps_existing_auth_type`, or keep it and document it as hand-edit tolerance.

### IN-05: Already defended elsewhere: credential and auth-type re-validation inside the probe

**File:** `custom_components/traefik_proxy/config_flow.py:213-217`, `custom_components/traefik_proxy/config_flow.py:289-292`
**Category:** necessity
**Issue:**
- `_validate_input` catches `ValueError` from `auth_from_entry_data` and maps it to `InvalidAuth`. All three callers (user, reauth, reconfigure) pass credentials that `_collect_credentials` has already run through the same `Auth(...)` constructor (`config_flow.py:303-306`).
- `_collect_credentials` maps an unknown `auth_type` to an error. The `SelectSelector` (`config_flow.py:95-101`) already rejects values outside the `AuthMode` options during schema validation.

Neither branch can be reached from the flows.
**Fix:** Keep `_collect_credentials` as the single validation point and drop the two branches. Alternatively, mark them as deliberate defense in depth in a comment.

### IN-06: `test_removal_leaves_no_issue` does not test the `config_entry_id` binding it is meant to cover

**File:** `tests/test_repairs.py:130-138`
**Issue:** Removing an entry unloads it first, and the unload callback (`__init__.py:106`) already deletes the `insecure_credentials` issue. The test therefore passes whether or not `config_entry_id=` is passed to `ir.async_create_issue`. (The migration issue is covered properly by `test_issue_survives_reload_and_is_deleted_on_remove`.)
**Fix:** Remove an entry that is not loaded but has the issue, for example one created through `ir.async_create_issue(..., config_entry_id=entry.entry_id)` before setup. Or assert on the registry's per-entry cleanup directly.

### IN-07: Coverage target still points at a non-existent package

**File:** `pyproject.toml:24`
**Issue:** `--cov=custom_components.traefik` measures nothing, because the package is `custom_components.traefik_proxy`. This phase edited the line (adding `-p no:respx`) without fixing the path. The fix is already tracked as a Phase 8 carry-over in the decision log.
**Fix:** `--cov=custom_components.traefik_proxy`.

---

_Reviewed: 2026-11-15T15:20:18Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
