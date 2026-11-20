---
phase: "07"
slug: "config-flow-ha-2026-11-baseline-observability"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
block_on: high
created: "2026-11-15"
---

# Phase 07 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time (07-01..07-09 `<threat_model>` blocks: 30 rows, IDs T-07-01..T-07-21 plus one
> T-07-SC per plan); verified at ASVS L1 by gsd-security-auditor at HEAD 4ceef76, including the code-review fixes
> 79a08fd (WR-01), c915c15 (WR-02) and b0a8aff (WR-03). Threat test modules: 465 passed.
> Paths: `cc/` = `custom_components/traefik_proxy/`.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| PyPI → dev/test environment and CI | A new test dependency is installed into the dev env, the minimum venv and the CI job | `pytest-homeassistant` and its transitive packages |
| Home Assistant base classes → integration | The integration relies on public APIs only | Coordinator shutdown state |
| Config entry lifecycle → issue registry | Repair issues follow their entry | Entry id, issue ids, entry title |
| Requirements text → release metadata | The documented minimum equals the minimum HACS enforces | Minimum HA version string |
| Traefik HTTP answer → client | A misconfigured or hostile answer decides whether credentials travel further | HTTP status, `Location` header (never read), JSON payloads |
| Client error → HA exception / log / UI | Error details cross into logs, the UI and translations | Request path, HTTP status, exception type name |
| HA frontend form → config flow (user / reauth / reconfigure) | Untrusted input; errors and logs flow back to the user and the log file | URL, auth type, username, password, token; error keys |
| Stored entry data → migration → client | Legacy data is rewritten and later sent as an Authorization header | `api_key`, URL userinfo, unique_id, title |
| Config flow → frontend | Form defaults must never carry stored secrets | URL and auth-type defaults (no secrets) |
| Options form → entry.options → runtime | User-chosen numbers drive polling cadence, cert threshold and entity removal | scan_interval, tls_warn_days, missing_grace_hours, per_item_entities, verify_ssl |
| Integration state → diagnostics download | Data leaves Home Assistant as a file the user shares publicly | Redacted entry data, parsed snapshot, cert states, missing-since times |
| Entry configuration → network | Credentials sent over plain HTTP are readable on the path | Authorization header |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-07-SC (07-01) | Tampering | `pytest-homeassistant` install (dev/test) | medium | mitigate | Trusted publisher home-assistant/core verified (Project-URL, `homeassistant==<own version>`); old package removed; `manifest.json` `requirements: []` | closed |
| T-07-01 | Tampering | private base-class attribute read (cert_coordinator) | low | mitigate | Own `_stopping` flag cc/cert_coordinator.py:272/:480/:498; no private DataUpdateCoordinator attribute read; `test_stopping_flag_blocks_the_boundary_timer_after_unload` | closed |
| T-07-02 | Repudiation | migration repair issue lifecycle | low | mitigate | `config_entry_id=entry.entry_id` cc/__init__.py:262-270; `test_issue_survives_reload_and_is_deleted_on_remove` | closed |
| T-07-SC (07-02) | Tampering | npm/pip/cargo installs | low | accept | AR-07-01 | closed |
| T-07-20 | Repudiation | REQUIREMENTS/ROADMAP minimum vs `hacs.json` | low | mitigate | REQUIREMENTS REL-01 and ROADMAP Phase 8 SC1 name 2026.11.0 = `hacs.json`; negative greps for 2026.3 pass | closed |
| T-07-SC (07-03) | Tampering | npm/pip/cargo installs | low | accept | AR-07-02 | closed |
| T-07-03 | Information Disclosure | `api._request` redirect handling | high | mitigate | Only session call passes `allow_redirects=False` (cc/api.py:203-208); 3xx → `TraefikProxyRedirectError`, `Location` never read; `test_every_request_disables_redirects`, `test_redirect_is_not_followed_and_hides_location` | closed |
| T-07-04 | Information Disclosure | exception messages, translation placeholders | medium | mitigate | Placeholders only `path`/`status`/`detail`; no `str(err)` in cc/; AST test `test_every_exception_key_is_raised_and_translated`, `test_placeholders_match`, `test_credentials_never_leak` | closed |
| T-07-05 | Denial of Service | setup retry loop | low | mitigate | `ConfigEntryError(invalid_url)`, `ConfigEntryAuthFailed(invalid_credentials)` stop futile retries; tests in tests/test_coordinator.py:113/:152 | closed |
| T-07-SC (07-04) | Tampering | npm/pip/cargo installs | low | accept | AR-07-03 | closed |
| T-07-06 | Information Disclosure | entry data after an auth switch / target change | high | mitigate | `_entry_data` writes only the chosen type's keys; stored-secret fallback only for same auth type, scheme and host:port (`_same_target`, WR-01); reauth/reconfigure switch tests + `test_changed_target_requires_secret_again` | closed |
| T-07-07 | Information Disclosure | migration and flow logging | medium | mitigate | WARNINGs name entry ids/title only; flow logs one fixed message; `test_userinfo_with_token_keeps_bearer_and_warns`, `test_unknown_error_log_has_no_basic_credentials` | closed |
| T-07-08 | Spoofing | URL userinfo moved into credential fields | medium | mitigate | `split_url_userinfo` (cc/coordinator.py:81-94) cuts only the userinfo; `_migrated_entry_data`; migration tests incl. IPv6 host spelling | closed |
| T-07-09 | Information Disclosure | reauth/reconfigure forms | medium | mitigate | `_auth_fields` gives secrets no default/suggested value; `_assert_auth_markers`, `test_reconfigure_form_does_not_contain_token` | closed |
| T-07-10 | Tampering | unique_id migration / reconfigure | medium | mitigate | Pre-check + skip/WARNING in migration; `_owns_target` owner check before the probe in user and reconfigure, incl. legacy bare-host ids (WR-02); four abort/keep tests | closed |
| T-07-11 | Tampering | credentials sent as a header | low | mitigate | `Auth.__post_init__` rejects `:` in username and control characters; field error `invalid_credential_format` without a request (IN-01) | closed |
| T-07-SC (07-05) | Tampering | npm/pip/cargo installs | low | accept | AR-07-04 | closed |
| T-07-12 | Denial of Service | options values (scan interval, TLS warning days) | low | mitigate | NumberSelector ranges (cc/const.py:64-67), stored as int; range tests in tests/test_options_flow.py | closed |
| T-07-SC (07-06) | Tampering | npm/pip/cargo installs | low | accept | AR-07-05 | closed |
| T-07-13 | Tampering | entity removal timing | medium | mitigate | Grace read once per setup, stored missing-since times reused; grace-period boundary, reload and survive-reload tests | closed |
| T-07-21 | Denial of Service | option `missing_grace_hours` | low | mitigate | Selector 1-168, stored as int; bound and truncation tests | closed |
| T-07-SC (07-07) | Tampering | npm/pip/cargo installs | low | accept | AR-07-06 | closed |
| T-07-14 | Information Disclosure | `InvalidUrl` args, `unknown` log record | medium | mitigate | `raise InvalidUrl` without arguments; fixed-message `_LOGGER.exception`; `test_check_url_shape_raises_on_bad_urls`, `test_unknown_error_is_logged_once_without_input` | closed |
| T-07-15 | Information Disclosure | credentials typed into the URL | medium | mitigate | `UrlHasCredentials` checked before any client is built in user/reconfigure/reauth; tests assert 0 requests | closed |
| T-07-16 | Spoofing | redirect during the flow probe | high | mitigate | Client never follows redirects (T-07-03); `redirect` error in all three flows; tests assert 1 request and the Location host never contacted | closed |
| T-07-SC (07-08) | Tampering | npm/pip/cargo installs | low | accept | AR-07-07 | closed |
| T-07-17 | Information Disclosure | `diagnostics.py` credentials | high | mitigate | `TO_REDACT` (username/password/token/api_key/users/authorization), `_safe_url` strips userinfo or redacts unparsable URLs, `async_redact_data`; four redaction tests | closed |
| T-07-18 | Information Disclosure | `diagnostics.py` payload scope | medium | mitigate | Only `dataclasses.asdict` of parsed models; no backend URLs; closed-set cert error codes; `test_diagnostics_contain_no_raw_payload` | closed |
| T-07-19 | Information Disclosure | credentials over `http://` | medium | mitigate | `insecure_credentials` repair (WARNING, entry-bound) raised before the first refresh (WR-03), deleted on unload; six tests in tests/test_repairs.py | closed |
| T-07-SC (07-09) | Tampering | npm/pip/cargo installs; optional hassfest container | low | accept | AR-07-08 | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-07-01 | T-07-SC (07-02) | No package installs and no new dependencies in this plan | plan threat model; verified by gsd-security-auditor | 2026-11-15 |
| AR-07-02 | T-07-SC (07-03) | Same; only tooling edit renamed a local pre-commit hook (no new repo/rev) | plan threat model; verified by gsd-security-auditor | 2026-11-15 |
| AR-07-03 | T-07-SC (07-04) | No package installs and no new dependencies in this plan | plan threat model; verified by gsd-security-auditor | 2026-11-15 |
| AR-07-04 | T-07-SC (07-05) | No package installs and no new dependencies in this plan | plan threat model; verified by gsd-security-auditor | 2026-11-15 |
| AR-07-05 | T-07-SC (07-06) | No package installs and no new dependencies in this plan | plan threat model; verified by gsd-security-auditor | 2026-11-15 |
| AR-07-06 | T-07-SC (07-07) | No package installs and no new dependencies in this plan | plan threat model; verified by gsd-security-auditor | 2026-11-15 |
| AR-07-07 | T-07-SC (07-08) | No package installs and no new dependencies in this plan | plan threat model; verified by gsd-security-auditor | 2026-11-15 |
| AR-07-08 | T-07-SC (07-09) | No new dependencies; hassfest ran as a throwaway `--rm` container of the official image (digest in 07-09-SUMMARY.md) | plan threat model; verified by gsd-security-auditor | 2026-11-15 |

*Accepted risks do not resurface in future audit runs.*

### Non-blocking observations (for Phase 8 planners)

- CI `uv sync` has no committed lock and `test-min-ha` pins only the top-level package; actions are on moving refs (review WR-06/WR-07, Phase 8 SC3).
- cc/cert_coordinator.py still chains `from err` unlike the main coordinator's `_logged_cause` (IN-03, Phase 8); no userinfo URL can reach the cert cycle today.
- A legacy URL that `urlsplit` cannot parse is kept as stored including any userinfo; setup stops with `invalid_url`, diagnostics redact it, but the reconfigure form pre-fills it as default (narrow edge case).
- A `verify_ssl` flip on the same scheme and host:port still reuses the stored secret (WR-01 scope: scheme + host:port).
- The `insecure_credentials` repair covers plain HTTP only, not HTTPS with `verify_ssl` off.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-15 | 30 | 30 | 0 | gsd-security-auditor (ASVS L1, HEAD 4ceef76) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-15
