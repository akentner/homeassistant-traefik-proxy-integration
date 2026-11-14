# Phase 6: Certificates - Context

**Gathered:** 2026-11-15
**Status:** Ready for planning
**Source:** PRD Express Path (ROADMAP Phase 6, REQUIREMENTS CERT-01..05, audit
items, decision log `~/.cache/traefik-proxy-integration/decisions.md` M19 +
Phase-6 carry-over, Phase 4/5 artefacts)

<domain>
## Phase Boundary

Users see correct expiry data for the certificates Traefik actually serves —
including expired, self-signed and private-CA certificates. On Traefik ≥ 3.7
the data comes from `GET /api/certificates`; otherwise (404) from a threadless
async TLS probe against the Traefik host with SNI = router host. An expired or
repeatedly unprobeable certificate is reported as a **problem** (binary sensor
on, with a `reason`), never as "unavailable". Days left are computed live.

**In scope:** `cert_coordinator.py` (source selection, host set, probe
orchestration, per-host state), `tls.py` (rewritten: async probe, DER parsing,
verification, error classification), new `rules.py` (`extract_hosts`),
`api.py` + `models.py` (certificates endpoint + parsed model), `sensor.py` /
`binary_sensor.py` / `entity.py` (cert entity semantics, new
`certificates_problem` aggregate), `const.py`, `translations/en.json` +
`translations/de.json` + `strings.json` mirror (as long as it exists) +
`icons.json` for the new entity, and the migration of every affected test.

**Out of scope (later phases):** options-form fields (cap, grace period,
per-item toggle — Phase 7), minimum-HA bump and 2026.11 APIs (Phase 7, I1),
config-flow error texts, diagnostics (Phase 7), README/CHANGELOG/CI (Phase 8),
"probe via DNS" option (W5 out of scope), restoring cert values across an HA
restart (see D-16).

</domain>

<decisions>
## Implementation Decisions

### Source selection (CERT-01, T-01)
- **D-01:** Every cert cycle first calls `GET /api/certificates` through a new
  `TraefikProxyApiClient.async_get_certificates()` (pagination handled like the
  other list endpoints if the endpoint paginates — see research question R-2)
  and parses it with a new `models.parse_certificates()` into a frozen
  dataclass (e.g. `TraefikCertificate`: `common_name`, `sans`, `not_after`
  (UTC), `not_before`, `issuer_cn`, `status`, `serial_number`). Payload errors
  raise `TraefikProxyPayloadError` like the other parsers.
- **D-02:** `TraefikProxyNotFoundError` (404, Traefik < 3.7 / v2.11) → probe
  mode for this cycle (`source=probe`). The API is tried again every cycle (one
  cheap GET per 6 h; it picks up a Traefik upgrade without a reload). Any other
  API error (connection, auth, 5xx, payload) fails the cert cycle
  (`UpdateFailed`) — the integration is offline then and cert entities follow
  the main entities into unavailable; a failing *certificate* is never
  reported that way (D-09).
- **D-03:** Certificate entities stay keyed **per host** (unique_ids
  `{entry_id}_tls_cert_{host}` / `{entry_id}_tls_expiring_{host}` unchanged,
  W34) in both modes — no per-certificate entities, no registry migration. In
  API mode each host is mapped to the API certificate that covers it (exact
  SAN/CN match preferred over a single-label wildcard match per D-12; among
  equal matches the latest `not_after` wins). Every entity exposes a `source`
  attribute (`api` | `probe`). How hosts without a covering API certificate
  are treated (problem `not_found` vs. probing them) is decided from research
  question R-1; default if R-1 stays inconclusive: probe those hosts (hybrid,
  `source=probe` on them).
- **D-04:** Cert cycle cadence stays `DEFAULT_TLS_CERT_COOLDOWN` (6 h) for both
  sources; the "Refresh now" button and `homeassistant.update_entity` keep
  refreshing the cert coordinator (W23).

### Host set (CERT-03, A-12, P-07, S-07)
- **D-05:** New module `custom_components/traefik_proxy/rules.py` with
  `extract_hosts(rule: str) -> tuple[str, ...]`: handles ``Host(`a`)``, the v2
  multi-argument form ``Host(`a`, `b`)`` and v3 `||` / `&&` combinations;
  never matches `HostRegexp`, `HostSNI`, `HostSNIRegexp` or `HostHeader…`
  prefixes as `Host`; skips names containing `*`, `{` or other regex/template
  syntax; returns lowercase, de-duplicated names in first-seen order. Every
  `_HOST_FROM_RULE` regex copy (cert_coordinator.py and any other) is deleted.
- **D-06:** Host set per cycle = TLS routers of the main snapshot:
  `tls_domains[].main` + `tls_domains[].sans` + `extract_hosts(router.rule)`,
  lowercased, wildcard (`*.`) names skipped, sorted. Capped at
  `MAX_CERT_HOSTS = 200` (constant in `const.py`, not an option): the first 200
  in sorted order are kept; when the cap cuts hosts, one WARNING per cycle
  names the dropped count (not every host).

### Async probe (CERT-02, P-05, P-06, T-02, S-05)
- **D-07:** The probe is native async: `asyncio.open_connection(connect_host,
  port, ssl=<shared ctx>, server_hostname=<router host>)` under
  `asyncio.timeout(TLS_HANDSHAKE_TIMEOUT)` and the existing
  `asyncio.Semaphore(TLS_SEMAPHORE)`; no `asyncio.to_thread`, no executor, no
  blocking socket. The writer is closed (with `wait_closed` under the same
  timeout guard) on every path. The certificate is read with
  `ssl_object.getpeercert(binary_form=True)` and parsed with
  `cryptography.x509.load_der_x509_certificate` (`not_valid_after_utc`,
  subject, issuer, SAN DNS names). `requirements: []` stays — `cryptography`
  is bundled with HA.
- **D-08:** One shared `SSLContext` for all probes: `PROTOCOL_TLS_CLIENT`,
  `check_hostname=False`, `verify_mode=CERT_NONE`, built once (module-level
  lazily or per coordinator) with no disk I/O in the event loop. An expired,
  self-signed or private-CA certificate therefore handshakes successfully.
- **D-09:** Connect address = hostname of the config entry's URL (the Traefik
  host), not the router hostname via DNS (T-02). Port = the TLS entrypoint of
  the router: resolve the router's `entry_points` through
  `snapshot.entrypoints[name].address` (forms `:443`, `0.0.0.0:443`,
  `[::]:443`; skip `/udp`); prefer 443 when several, otherwise the lowest
  port; fall back to 443 when nothing resolves. A host reached by several
  routers is probed once.
- **D-10:** `verified: bool | None` attribute. Probe mode: `True` only when the
  presented chain validates against HA's trust store at the current time and
  the leaf covers the SNI host; `False` otherwise (expired, self-signed,
  private CA, mismatch). Exact mechanism (cryptography `x509.verification`
  with `ssl_object.get_unverified_chain()` and the CA certificates of HA's
  pre-built client context vs. a second verifying handshake) comes from
  research question R-3; constraint: no blocking I/O in the event loop and no
  thread for the probe. API mode: `None` unless research R-2 shows a field
  that means "trusted".
- **D-11:** Error classification is a closed set and ordered correctly:
  `ssl.SSLError` is caught **before** `OSError` (S-05), `ConnectionRefusedError`
  before `OSError`, `socket.gaierror` → `dns`, timeout → `timeout`, DER parse
  failure → `parse`, no peer certificate → `empty`, anything else → `unknown`.
  The old notAfter string parsing (`parse_not_after`, `NOTAFTER_FORMATS`,
  `CertDict`, the blocking `fetch_cert_info*` / `_open_tls_connection`) is
  removed.

### Wildcard matching (CERT-04, S-04)
- **D-12:** `_hostname_matches_san` (used for `san_mismatch` and the API host
  mapping) accepts a wildcard for exactly one label: `*.example.com` matches
  `a.example.com`, not `a.b.example.com` and not `example.com`
  (`host.split(".", 1)[1] == entry[2:]`, case- and trailing-dot-insensitive).

### Live days and problem semantics (CERT-05, U-09, U-10)
- **D-13:** `days_until_expiry` is no longer stored at probe time; it is
  computed from `not_after` at read time (`dt_util.utcnow()`, signed floor
  days). A threshold crossing / expiry / day change is written without a new
  probe: the cert coordinator (or entity) schedules a point-in-time callback
  at the earliest upcoming day boundary (`not_after - k days`) across hosts and
  notifies listeners; write-on-change entities then write only when their
  computed state changed. Mechanism is Claude's discretion; the observable
  truth is fixed (see specifics).
- **D-14:** Per-host coordinator state replaces the bare
  `CertInfo | CertError` value: last known certificate (if any), last error
  (if any), consecutive failure count, `source`. Hosts that leave the host set
  are dropped from every per-host dict in the same cycle (no unbounded growth).
- **D-15:** `certificate_expiring` (per host, PROBLEM, enabled by default):
  **on** with `reason` = `expired` (days < 0), `probe_failed` (≥
  `CERT_FAILURES_FOR_PROBLEM = 2` consecutive failed probes),
  `not_found` (only if D-03/R-1 chooses that), or `expiring` (days ≤
  threshold); precedence in that order. **off** with `reason: None`. Unknown
  (`None`) only while there is no certificate yet and fewer than 2 failures.
  Cert entities are **available** whenever the last cert cycle succeeded and
  the host is in the host set — a failed probe no longer makes them
  unavailable (missing hosts keep the Phase 5 manager behaviour).
- **D-16:** `certificate_expiry` (timestamp) keeps the last known `not_after`
  while probes fail and stays available; attributes carry `last_error`,
  `verified`, `source`, live `days_until_expiry`. Last known values live in
  coordinator memory only; after an HA restart a host whose probe fails has
  no value until the first success (accepted; no RestoreSensor this phase).
- **D-17:** New `certificates_problem` aggregate binary sensor (PROBLEM,
  enabled by default, main device, unique_id `{entry_id}_certificates_problem`
  via a new `UID_CERTIFICATES_PROBLEM` constant, translation key
  `certificates_problem`, icon in `icons.json`, en + de names). Bound to the
  cert coordinator; on while any host's `certificate_expiring` is on;
  attributes `problems` (sorted hosts, at most `MAX_PROBLEM_NAMES`),
  `problem_count` (all) and `reasons` (`{host: reason}` for the listed hosts).
  The `reason` values get `state_attributes` translations in en + de.

### Bounded state, compatibility, tests
- **D-18:** No module-level dict that grows with hosts: `_parse_log_cooldown`
  is deleted (P-08); parse failures log at debug level without throttling.
- **D-19:** Every plan keeps `uv run pytest -q`, `uv run ruff check
  custom_components tests`, `uv run ruff format --check custom_components
  tests`, `uv run mypy --strict custom_components/traefik_proxy` green and the
  suite green on the HA 2026.3 venv
  (`~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o
  addopts="" tests`) — the minimum stays 2026.3.0 until Phase 7 (I1). Tests are
  migrated in the same task as the code change (no red intermediate commits).
- **D-20:** Carry-over: every test that depends on the v3.7
  `certificates.json` `notAfter` (2027-02-12T00:17:40Z) or on generated
  certificates freezes time (`freezer` fixture) — a regenerated throwaway
  certificate changes `notAfter`.
- **D-21:** Probe tests use real TLS handshakes against a local asyncio TLS
  server on 127.0.0.1 with certificates generated in the test by
  `cryptography` (valid, expired, self-signed, private-CA-signed, wildcard);
  no mocking of `ssl` for those cases. Real fixtures (v3.7 certificates /
  v2.11 404) drive the source-selection tests. No real HA instance; local
  throwaway Docker only if needed, containers removed afterwards.
- **D-22:** User-visible changes are recorded in each plan SUMMARY ("User-
  visible changes") for the Phase 8 CHANGELOG: `last_error` values (`ssl` now
  reachable), problem-on instead of unavailable, live days, `verified` /
  `source` / `reason` attributes, new aggregate.

### Claude's Discretion
- Internal shape of the per-host state (dataclass names), where the shared
  `SSLContext` lives, the day-boundary timer mechanism (D-13), how the
  aggregate binds to the cert coordinator (own small base class vs. reuse),
  plan/wave structure (tracer-first).
- Whether `HostHeader` (v2 alias of `Host`) is treated as `Host` in
  `extract_hosts` (state the choice in the SUMMARY).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and requirements
- `.planning/ROADMAP.md` § "Phase 6: Certificates" — goal, success criteria,
  audit items.
- `.planning/REQUIREMENTS.md` — CERT-01..05 (and superseded TLS-01..05 notes).
- `.planning/research/AUDIT-ARCH-PERF-UX.md` — rows A-12, P-05..P-08, U-09,
  U-10, S-04, S-05, S-07, T-01, T-02 (problem, impact, fix).
- `.planning/research/MARKETPLACE-BEST-PRACTICES.md` — entity/attribute and
  translation conventions.
- `~/.cache/traefik-proxy-integration/decisions.md` — I1 (minimum HA stays
  2026.3 until Phase 7), M19 (certificate design), carry-over "Phase 6".

### Prior phase decisions this phase builds on
- `.planning/phases/05-entity-model-lifecycle/05-CONTEXT.md` — entity manager
  (D-01..D-04), cert kinds keyed by host, devices, deferred Phase-6 items.
- `.planning/phases/05-entity-model-lifecycle/05-05-SUMMARY.md` — cert
  entities on `TraefikCertEntity` through the manager (Worker Decisions).
- `.planning/phases/04-data-layer-correct-lean/04-01-SUMMARY.md` — fixture
  capture, certificates.json redaction, frozen-time note.
- `.planning/phases/04-data-layer-correct-lean/COVERAGE.md` — endpoint
  coverage (`/api/certificates` reserved for Phase 6).

### Code
- `custom_components/traefik_proxy/cert_coordinator.py`, `tls.py`,
  `entity.py` (`TraefikCertEntity`, `cert_hosts`), `sensor.py`
  (`TraefikCertExpirySensor`), `binary_sensor.py`
  (`TraefikCertExpiringBinarySensor`, problem aggregates), `entity_manager.py`,
  `api.py` (`_get_paginated`, error classes), `models.py` (parse pattern,
  `Router.entry_points`, `Entrypoint.address`), `const.py`,
  `translations/*.json`, `icons.json`.
- `tests/fixtures/v3.7/certificates.json`, `tests/fixtures/v2.11/`,
  `tests/traefik/` (capture harness, throwaway cert).
- `.claude/skills/spike-findings-homeassistant-traefik-integration/` — spike
  005 (`asyncio.open_connection` drop-in), 003 (SNI routing), 006 (SAN
  mismatch).

</canonical_refs>

<specifics>
## Specific Ideas

- Observable truths the plans must prove:
  - v3.7 fixture → cert data from `/api/certificates`, zero TLS connections,
    `source=api`; v2.11 (404) → probe, `source=probe`.
  - Probe of an expired and of a self-signed certificate both return a
    certificate (not an error) with `verified=false`; a private-CA chain is
    read; a publicly-trusted-style chain built from a test CA injected as
    trusted yields `verified=true` (test seam for the trust store).
  - `asyncio.to_thread` / `run_in_executor` / `socket.create_connection` do not
    appear in `tls.py` / `cert_coordinator.py`.
  - The probe connects to the entry URL host on the router's TLS entrypoint
    port with SNI = router host.
  - ``Host(`a`,`b`)``, ``Host(`a`) || Host(`b`)``, `HostRegexp`, `HostSNI`,
    `*.example.com` cases in `extract_hosts` tests; 250 hosts → 200 probed.
  - `*.example.com` matches `a.example.com`, not `a.b.example.com`.
  - An `ssl.SSLError` is classified `ssl`, not `oserror`.
  - With frozen time, moving the clock past `not_after - threshold` flips
    `certificate_expiring` on (`reason=expiring`) without a new probe; past
    `not_after` → `reason=expired`; `days_until_expiry` decreases daily.
  - Two consecutive failed probes → `certificate_expiring` on
    (`reason=probe_failed`), timestamp sensor available with its last value;
    `certificates_problem` on with that host in `problems`.

## Research questions (real technical unknowns)
- **R-1:** Does Traefik 3.7 `/api/certificates` list ACME (Let's Encrypt /
  resolver) certificates, file-provider certificates, the default certificate?
  What happens for a host Traefik would serve with the default cert?
- **R-2:** Exact response schema and behaviour of `/api/certificates` in 3.7
  (pagination `per_page`/`page`/`X-Next-Page`, `status` values and meaning,
  per-certificate endpoint, query/search params) from `pkg/api` source.
- **R-3:** How to compute `verified` without threads/blocking I/O: availability
  of `SSLObject.get_unverified_chain()` on Python 3.14 via asyncio transports;
  cryptography (HA-bundled version) `x509.verification` API with a store built
  from HA's client context `get_ca_certs(binary_form=True)`; behaviour for
  expired leaf, self-signed, missing intermediates.

</specifics>

<deferred>
## Deferred Ideas

- Options-form field for the 200-host cap or the failure count — Phase 7 or
  later (constants this phase).
- "Probe via DNS" option (T-02 alternative) — out of scope (W5).
- RestoreSensor for cert values across HA restarts — not this phase.
- Per-certificate (instead of per-host) entities — rejected for stable
  unique_ids (D-03).
- Empty "Certificates" sub-device on installs without TLS routers (Phase 5
  ENT-03 note) — unchanged.

</deferred>

---

*Phase: 06-certificates*
*Context gathered: 2026-11-15 via PRD Express Path*
