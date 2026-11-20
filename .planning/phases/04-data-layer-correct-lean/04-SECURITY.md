---
phase: "04"
slug: "data-layer-correct-lean"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-14"
---

# Phase 04 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Local Docker harness -> committed repository | Captured API payloads from containers on the developer machine become public test fixtures | IPs, hostnames, container IDs, basicAuth hashes (sensitive until redacted) |
| Docker daemon -> Traefik containers | Traefik's docker provider reads the host's Docker socket | Container metadata (read-only socket) |
| Docker Hub -> developer machine | Third-party images are pulled and executed | Container images (pinned by digest) |
| Integration -> Traefik API over the network | Credentials leave HA in the Authorization header | Basic/Bearer credentials (secret) |
| HA shared aiohttp session | One session object is shared by every integration in the HA process | Default headers (must stay credential-free) |
| Client errors -> HA logs / UI / exception chains | Messages are shown to users and persisted in logs | Error text (must never carry credentials) |
| Config-flow user input -> client | URL and credentials typed by the user | URL, credentials |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-04-01 | Information disclosure | tests/fixtures/** via capture.py | high | mitigate | `Redactor` (tests/traefik/capture.py:118) maps non-documentation IPs to RFC 5737/3849; tests/test_fixture_redaction.py guards IPs/hostnames | closed |
| T-04-02 | Information disclosure | basicAuth config inside rawdata fixtures | high | mitigate | `AUTH_MIDDLEWARE_KEYS` redaction (capture.py:92); test_fixture_redaction.py:128 asserts no password, Basic token or htpasswd hash | closed |
| T-04-03 | Elevation of privilege | Docker socket in tests/traefik/compose.yaml | medium | mitigate | Socket mounted `:ro` (compose.yaml:35), 127.0.0.1-only bindings, `compose down -v` in `finally`, harness not collected by pytest (exit 5) | closed |
| T-04-SC (04-01) | Tampering | Docker image pulls | high | mitigate | All `image:` lines pinned by version tag + sha256 digest (compose.yaml:40,46 and whoami) | closed |
| T-04-05 | Spoofing / Information disclosure | Options listener; coordinator `client` | medium | mitigate | `client` property returns `runtime_data.client` (coordinator.py:111); replaced in one statement (`__init__.py:186`); identity test | closed |
| T-04-06 | Denial of service | Setup order in async_setup_entry | low | mitigate | `entry.runtime_data` assigned (`__init__.py:229`) before first refresh (`__init__.py:235`) | closed |
| T-04-04 | Denial of service / Tampering | models.py parse functions | medium | mitigate | No `assert` in models.py; explicit shape errors; unknown-status log capped (`_MAX_LOGGED_UNKNOWN_STATUSES = 16`) | closed |
| T-04-07 | Information disclosure | sensor.py service attributes | medium | mitigate | Counts only (`servers_up`); test_sensor.py:181-182 asserts no `servers` key and no `://` in attributes | closed |
| T-04-08 | Denial of service | api.py pagination via X-Next-Page | medium | mitigate | `MAX_PAGES = 100` (api.py:35), strictly increasing header rule; tests/test_api_pagination.py | closed |
| T-04-09 | Tampering / Denial of service | Parser errors reaching the coordinator | medium | mitigate | Wrapped into `TraefikProxyPayloadError(path, "unexpected payload shape")` (api.py:226,245), mapped to `UpdateFailed` | closed |
| T-04-10 | Information disclosure | api.py exceptions, logging, Auth repr | high | mitigate | `repr=False` on credentials (api.py:62-63); tests/test_api.py:126,287 scan repr, str(exc), repr(exc), caplog incl. userinfo URL | closed |
| T-04-11 | Information disclosure | Authorization header vs HA shared session | high | mitigate | `Auth.header()` passed per request (api.py:90,187); test_api.py:157 asserts session default headers free of Authorization | closed |
| T-04-12 | Spoofing | TLS verification on API requests | medium | mitigate | `ssl=self._verify_ssl` on every GET and the POST (api.py:188,306) | closed |
| T-04-13 | Elevation of privilege / Spoofing | Config-flow error mapping | low | mitigate | Specific branches first (auth, not found → `api_disabled`, invalid URL) in config_flow.py; parametrized mapping test | closed |
| T-04-14 | Information disclosure | Basic credentials over plain http:// | medium | transfer | Transferred to Phase 7 (ROADMAP Phase 7 SC4: repair issue for http:// + credentials); no UI path to basic auth added in Phase 4 | closed |
| T-04-15 | Denial of service | Request volume against the user's Traefik | medium | mitigate | One rawdata request per steady cycle; `VERSION_RECHECK_INTERVAL` 1 h; `test_request_budget_matrix` (tests/test_coordinator.py:280) | closed |
| T-04-16 | Tampering / Denial of service | Fallback switch on 404 | low | mitigate | Only `TraefikProxyNotFoundError` on /api/rawdata flips to pages; 401/500 propagate; MAX_PAGES kept on paginated path | closed |
| T-04-SC (04-02..04-06) | Tampering | Package installs | low | accept | No new dependencies (see Accepted Risks Log) | closed |
| T-04-17 | Denial of service (alert suppression) | Cert entity state propagation | high | mitigate | `TraefikProxyCertEntity` binds cert entities to the cert coordinator (entity.py:120-136; binary_sensor.py:357,415; sensor.py:410,464); availability from the cert coordinator only (sensor.py:542-571); tests/test_cert_entity_state.py:95,154,173,188 | closed |
| T-04-18 | Denial of service | `update_entity` on a cert entity triggers a cert refresh | low | accept | AR-04-02 | closed |
| T-04-19 | Repudiation (log noise) | Duplicate unique-ID log per cert notification (WR-05) | low | accept | AR-04-03 | closed |
| T-04-20 | Information disclosure | Credentials in a newly entered URL | medium | mitigate | `_check_url_shape` rejects userinfo unless `allow_userinfo` (config_flow.py:157); strict in user step (:285) and reconfigure (:435), opt-out only for yaml (:318) and reauth (:372); tests/test_config_flow.py:189,361; tests/test_reconfigure.py:182 | closed |
| T-04-21 | Denial of service / Repudiation | Bare ValueError from aiohttp request construction | medium | mitigate | `except ValueError` -> `TraefikProxyInvalidUrlError` at both session call sites (api.py:206-209, 361-364); tests/test_coordinator.py:98, tests/test_api.py:239,278 | closed |
| T-04-22 | Information disclosure | Message of the mapped error | low | mitigate | Message is `<path>: ValueError` (api.py:209,364); test_credentials_never_leak[request-construction-*] (tests/test_api.py:345) | closed |
| T-04-23 | Denial of service | Request volume in paginated mode | medium | mitigate | Rawdata re-probe armed only after an elapsed hourly re-check (coordinator.py:168-171), one-shot flag cleared before await (api.py:304-306); test_request_budget_matrix rows (6)-(13), test_one_probe_per_arming_under_overlapping_calls (tests/test_api.py:602) | closed |
| T-04-24 | Tampering | Probe outcome switching the client back | low | mitigate | `_paginated = False` only after `parse_rawdata` succeeds (api.py:286-290); test_rawdata_probe_other_failures_read_pages (tests/test_api.py:589) | closed |
| T-04-25 | Spoofing / Information disclosure | Rejected credentials on the probe | low | mitigate | `TraefikProxyAuthError` re-raised before the broad except (api.py:280-281), no page request; test_rawdata_probe_auth_error_propagates (tests/test_api.py:566) | closed |
| T-04-SC (04-07..04-09) | Tampering | Package installs | low | accept | AR-04-04 | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-04-01 | T-04-SC (04-02, 04-03, 04-04, 04-05, 04-06) | No npm/pip/cargo installs and no new runtime dependencies; aiohttp, cryptography, pytest-freezer are already provided by HA / the dev environment | Plan threat model (plan time) | 2026-11-14 |
| AR-04-02 | T-04-18 | Cert refresh via `update_entity` is bounded by HA's default refresh debouncer (10 s cooldown, no custom debouncer in cert_coordinator.py), `TLS_SEMAPHORE = 4` and a 5 s handshake timeout; only authenticated HA users can call services; main cycles never probe (test_main_cycles_never_probe_certificates) | Plan threat model (plan time), verified by security audit | 2026-11-14 |
| AR-04-03 | T-04-19 | Log noise only; no new add path in 04-07 (2 add calls per platform), listener count stays stable (test_cert_notifications_do_not_grow_listeners); fixed by the Phase 5 entity manager (M28) | Plan threat model (plan time), verified by security audit | 2026-11-14 |
| AR-04-04 | T-04-SC (04-07, 04-08, 04-09) | No package installs; no change to pyproject.toml, uv.lock, manifest.json or hacs.json since fd3bd07 | Plan threat model (plan time), verified by security audit | 2026-11-14 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-14 | 18 | 18 | 0 | execute-phase orchestrator (secure-phase, ASVS L1 grep-depth short-circuit) |
| 2026-11-14 | 10 (gap plans 04-07..04-09: T-04-17..T-04-25, T-04-SC) | 10 | 0 | gsd-security-auditor (ASVS L1, 50 named tests run at a747f59); 3 low accept rows closed via AR-04-02..04 |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-14

## Security Audit 2026-11-14

| Metric | Count |
|---|---|
| Threats found | 10 |
| Closed | 10 |
| Open | 0 |
