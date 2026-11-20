# Phase 6: Certificates - Research

**Researched:** 2026-11-15
**Domain:** Traefik `/api/certificates` (v3.7), threadless asyncio TLS probe, offline X.509 chain verification (`cryptography.x509.verification`), HA time-based state
**Confidence:** HIGH (all three research questions answered from Traefik source at a pinned tag and from local experiments in both HA venvs)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Source selection (CERT-01, T-01)
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

#### Host set (CERT-03, A-12, P-07, S-07)
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

#### Async probe (CERT-02, P-05, P-06, T-02, S-05)
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

#### Wildcard matching (CERT-04, S-04)
- **D-12:** `_hostname_matches_san` (used for `san_mismatch` and the API host
  mapping) accepts a wildcard for exactly one label: `*.example.com` matches
  `a.example.com`, not `a.b.example.com` and not `example.com`
  (`host.split(".", 1)[1] == entry[2:]`, case- and trailing-dot-insensitive).

#### Live days and problem semantics (CERT-05, U-09, U-10)
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

#### Bounded state, compatibility, tests
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

### Deferred Ideas (OUT OF SCOPE)
- Options-form field for the 200-host cap or the failure count — Phase 7 or
  later (constants this phase).
- "Probe via DNS" option (T-02 alternative) — out of scope (W5).
- RestoreSensor for cert values across HA restarts — not this phase.
- Per-certificate (instead of per-host) entities — rejected for stable
  unique_ids (D-03).
- Empty "Certificates" sub-device on installs without TLS routers (Phase 5
  ENT-03 note) — unchanged.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CERT-01 | Traefik >= 3.7: data from `GET /api/certificates` (`source=api`, no probing); 404 / older falls back to probing (T-01) | R-1, R-2: endpoint added in v3.7.0, absent in v3.6.25 / v2.11.63; schema + pagination below; uncovered hosts → `not_found` (no probe) |
| CERT-02 | Native async probe, one shared CERT_NONE `SSLContext`, DER parse via `cryptography`, connect to entry-URL host on TLS entrypoint port with SNI | R-3: experiment confirms CERT_NONE handshake returns DER leaf + full chain for expired / self-signed / private-CA certs; exception classes measured |
| CERT-03 | `rules.py` `extract_hosts()`; cap 200; no unbounded module cache | No unknowns; covered by CONTEXT D-05/D-06/D-18. Pitfall list below |
| CERT-04 | Wildcard SAN matching = exactly one label (RFC 6125 §6.4.3) | Traefik's own `matchDomain` uses the identical single-label rule (replace first label with `*`), and it also matches the CN — the API host mapping should match `sans ∪ {commonName}` |
| CERT-05 | Live `days_left`; expired / repeatedly unprobeable → problem with `reason`; timestamp keeps last value | Timer: `async_track_point_in_utc_time` + `async_fire_time_changed` verified under `freezer` in both venvs; floor-day boundary formula below |
</phase_requirements>

## Summary

**R-1 (what `/api/certificates` lists).** In Traefik v3.7 the endpoint returns every leaf certificate of the **default TLS store's dynamic certificates** plus a **user-configured default certificate**. It leaves out the generated `TRAEFIK DEFAULT CERT`. ACME certificates are in the list: the ACME provider publishes them as dynamic `tls.certificates` in store `default`. File-provider `tls.certificates` without `stores` are in the list too, because Traefik adds them to `default`. A host that no listed certificate covers by exact or single-label wildcard match (on SAN or CN) gets the store's default certificate at handshake time. That is either the generated `TRAEFIK DEFAULT CERT` (self-signed RSA, 365 days from Traefik start, random SAN) or a user-configured default certificate, which the API **does** list. Probing such a host would therefore report a self-signed certificate valid for about a year with "expiring = off", which hides a broken host. **Recommendation for D-03: report hosts without a covering API certificate as problem `reason=not_found` and do not probe them.**

**R-2 (schema).** `GET /api/certificates` returns a JSON array of `certificateRepresentation`. It is sorted by `commonName` ascending by default and paginated exactly like the router, service and middleware lists (`per_page` default 100, `page`, `X-Next-Page`; on the last page `X-Next-Page` is `1`). It accepts `search`, `status`, `sortBy` (`name`|`cn`|`status`|`issuer`|`validUntil`) and `direction`. `status` is purely expiry-based: `enabled`, `warning` (< 30 days, hard-coded) or `expired`, computed on the Traefik clock at request time. No field means "trusted", so `verified` stays `None` in API mode. The per-certificate endpoint `/api/certificates/{sha256-fingerprint}` exists but is not needed. The endpoint first appeared in **v3.7.0** (2026-05-05). `pkg/api/handler_certificate.go` is absent at v3.6.25 and v2.11.63, so the API returns 404 there. The captured fixture matches the schema.

**R-3 (verification without threads).** One CERT_NONE `asyncio.open_connection` handshake is enough. On Python 3.14, `writer.get_extra_info("ssl_object")` is an `ssl.SSLObject`, and `get_unverified_chain()` works with CERT_NONE. It returns `list[bytes]` (DER, leaf first, server order); typeshed types it as `list[bytes]`. The chain is then checked offline with `cryptography.x509.verification`: `PolicyBuilder().store(Store(roots)).time(now).build_server_verifier(DNSName(host)).verify(leaf, intermediates)`. Trust anchors come from `homeassistant.util.ssl.client_context().get_ca_certs(binary_form=True)`. That context is pre-built at HA import time, the call reads memory only, and HA's blocking-call detector does not flag it. Parsing the 118 certifi roots and building the `Store` takes about 1 ms. Verification takes about 0.2–0.4 ms per host. The same code behaves the same on cryptography 46.0.5 (HA 2026.3) and 50.0.x (HA 2026.10/2026.11). The test seam is a `trust_store` constructor kwarg that takes `Store([test_root])`.

**Primary recommendation:** API-first with `not_found` for uncovered hosts. Probe mode uses one CERT_NONE handshake per host plus offline `cryptography` verification against HA's pre-built client-context roots. One coordinator-level `async_track_point_in_utc_time` timer handles day boundaries.

## Project Constraints (from CLAUDE.md)

- Python 3.14+, HA min 2026.3.x (stays 2026.3.0 this phase, I1); `aiohttp` via `async_get_clientsession`; HACS-compatible; `requirements: []`.
- One call-set per scan interval; parallel via `asyncio.gather`.
- API tokens never logged; self-signed certs supported via user option.
- No external services/telemetry; talks only to the Traefik API (and, for the probe, the Traefik host).
- Avoid: `requests`, standalone `httpx`, `async_timeout`, `hass.data[DOMAIN]`, per-entity `async_update`, own `aiohttp.ClientSession()`, `quality_scale` key, `asyncio.get_event_loop()`.
- Modern syntax (`int | None`, PEP 695 aliases); ruff + `mypy --strict`.
- GSD workflow: edits only via GSD commands; code/comments/commits English; chat German.
- Tooling: `uv run ...`, no global pip.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Certificate list (>= 3.7) | API client (`api.py` + `models.py`) | — | Same `_request`/`_get_paginated`/error classes as other list endpoints |
| Host set + source selection + host→cert mapping | `cert_coordinator.py` | `rules.py` (`extract_hosts`) | Coordinator owns the cycle; rule parsing is pure |
| TLS probe, DER parse, verification, error classes | `tls.py` (pure async functions, no HA state) | `homeassistant.util.ssl` (roots, read-only) | Keeps probe testable against a local server |
| Live days / problem reason | Entity read path (`entity.py` / `sensor.py` / `binary_sensor.py`) | Coordinator timer (notify only) | Computed from `not_after` + `dt_util.utcnow()` at read time |
| Aggregate `certificates_problem` | `binary_sensor.py` on cert coordinator | — | Same coordinator as per-host entities, so the same notifications |

## R-1: What `/api/certificates` lists (Traefik v3.7.19 source)

Evidence (all `[VERIFIED: github.com/traefik/traefik @ v3.7.19, files read this session]`):

- Handler: `pkg/api/handler_certificate.go` `extractCertificates()` → `h.tlsManager.GetServerCertificates()`; returns `[]` (not 404) only when `tlsManager == nil`. The production builder always passes it: `pkg/server/service/managerfactory.go:46` `api.NewBuilder(staticConfiguration, tlsManager)`.
- `pkg/tls/tlsmanager.go:298-346` `GetServerCertificates()`: comment verbatim *"returns all certificates from the default store, as well as the user-defined default certificate (if it exists)"*. It iterates `defaultStore.DynamicCerts`, then adds `defaultStore.DefaultCertificate` unless `Leaf.Subject.CommonName == generate.DefaultDomain` (comment: *"Excluding the generated Traefik default certificate."*). `pkg/tls/generate/generate.go:18`: `const DefaultDomain = "TRAEFIK DEFAULT CERT"`.
- ACME → default store: `pkg/provider/acme/provider.go` `buildMessage()` emits `conf.Configuration.TLS.Certificates` with `Stores: []string{cert.Store}`; resolution calls pass `traefiktls.DefaultTLSStoreName` (lines 532/538/568/574/640).
- File provider certs without stores → default: `tlsmanager.go:129-134` (`conf.Stores = []string{DefaultTLSStoreName}`).
- `defaultGeneratedCert` (ACME-backed default) is taken from the dynamic certs (`st.GetCertificate(domains)`), so it is listed anyway. A file-configured `tls.stores.default.defaultCertificate` is listed as the user-defined default.
- Not listed: certs in non-default stores (Traefik: *"it actually is the only usable one for now"*, `tlsmanager.go:28-30`), the `tlsalpn-01` challenge store, the generated default cert.

What the client actually gets for a given SNI (`tlsmanager.go:252-293`, `certificate_store.go`):
1. `store.GetBestCertificate`: lowercased SNI, cache, then dynamic certs whose key matches via `matchDomain`: exact, or `labels[0]="*"` (**single-label wildcard**, identical to D-12). Matching uses CN **and** DNS SANs (`parseCertificate` builds the key from lowercased CN + DNSNames + IPs).
2. With no match and `sniStrict` on, the handshake fails. Otherwise `store.GetDefaultCertificate()` is served: the user-defined default certificate, or the generated self-signed `TRAEFIK DEFAULT CERT` (RSA, `NotAfter = now + 365 days` at Traefik start, `generate.go:76-77`).
3. Duplicate SAN sets are dropped (`appendCertificate`: *"Skipping addition of certificate ... as it already exists for this store"*). The API therefore never holds two certs with the same SAN/CN key, and D-03's "latest `not_after` wins" applies only to overlapping (not identical) SAN sets.

**Recommendation for D-03 (evidence-based): `not_found`, no hybrid probe.**
- Every certificate Traefik can serve for an HTTP router's SNI is in the list, except the generated default cert. A host with no SAN/CN match therefore gets either a user-defined default cert that does not cover it, the generated self-signed cert, or a failed handshake (`sniStrict`). All three are broken for clients, so reporting a problem is the truthful state.
- A hybrid probe would read the generated `TRAEFIK DEFAULT CERT` (valid about 1 year), show a healthy timestamp, and keep `certificate_expiring` off. That hides exactly the failure the user cares about.
- The success criterion "v3.7 fixture → zero TLS connections" holds either way, because the fixture's two hosts are both covered. `not_found` keeps API mode connection-free by construction.
- Known false-positive window: a router added shortly before a cycle whose ACME order is still pending shows `not_found` until the next cycle (≤ 6 h) or a "Refresh now". That is acceptable, because at that moment clients really do get the default cert. Record it as a user-visible behaviour in the SUMMARY.
- Matching for the mapping: candidates = `sans ∪ {common_name}` (lowercased, trailing dot stripped, IP SANs compare literally); exact match beats wildcard; tie → latest `not_after` (D-03).

## R-2: `/api/certificates` schema and behaviour (v3.7.0–v3.7.19, unchanged in v3.8.0-rc.3)

`[VERIFIED: traefik pkg/api/certificate.go:14-40 @ v3.7.19]`. Status constants verbatim:
```go
certStatusEnabled = "enabled"
certStatusWarning = "warning"
certStatusExpired = "expired"
```
Struct fields verbatim (JSON tags):
```go
Name                 string    `json:"name"` // SHA-256 fingerprint of the DER-encoded certificate.
SANs                 []string  `json:"sans"`
NotAfter             time.Time `json:"notAfter"`
NotBefore            time.Time `json:"notBefore"`
SerialNumber         string    `json:"serialNumber"`
CommonName           string    `json:"commonName"`
IssuerOrg            string    `json:"issuerOrg,omitempty"`
IssuerCN             string    `json:"issuerCN,omitempty"`
IssuerCountry        string    `json:"issuerCountry,omitempty"`
Organization         string    `json:"organization,omitempty"`
Country              string    `json:"country,omitempty"`
Version              string    `json:"version"`
KeyType              string    `json:"keyType"`
KeySize              int       `json:"keySize,omitempty"`
SignatureAlgorithm   string    `json:"signatureAlgorithm"`
CertFingerprint      string    `json:"certFingerprint"`
PublicKeyFingerprint string    `json:"publicKeyFingerprint"`
Status               string    `json:"status"`
```

| Aspect | Behaviour | Parser consequence |
|--------|-----------|--------------------|
| `sans` | `DNSNames` + IP SANs as strings, `sort.Strings`; always an array (`make(...,0,...)`) | `_str_tuple`; may be empty |
| `commonName` | `cert.Subject.CommonName`, may be `""` (CN-less certs) | optional string; include in host matching only when non-empty |
| `issuerCN` / `issuerOrg` | `omitempty`, so they can be **absent** | `issuer_cn: str | None` (do not use `_required_str`) |
| `notAfter`/`notBefore` | Go `time.Time` RFC 3339; x509 times are UTC second precision, e.g. `"2027-02-12T00:17:40Z"` | `datetime.fromisoformat()` (3.11+ accepts `Z`); reject naive → `TraefikProxyPayloadError` |
| `serialNumber` | decimal big-int string | keep `str` |
| `status` | `getCertificateStatus`: `< 0` → `expired`, `< 30*24h` → `warning`, else `enabled`; Traefik clock at request time | store only; never use it for `reason` (threshold is the user's, days are live) |
| `name` / fingerprints | SHA-256 hex; **zeroed in our redacted fixture** | do not dedupe on `name` (all fixture rows would collide); duplicates are harmless for mapping |
| Trust field | none | `verified = None` in API mode (D-10) |
| Default sort | `sortCertificates` default → `sortByName` on **CN**, `sort.Slice` (not stable) | ties (empty CN) can reorder between pages; keep `DEFAULT_PAGE_SIZE` (500) so typical installs fit one page |
| Pagination | `pkg/api/criterion.go:12-17,90-114`: `defaultPerPage = 100`, `nextPageHeader = "X-Next-Page"`; last page → header `1`; `page` beyond the end → **400**; invalid / `<=0` params → 400; empty list page 1 → `[]` + header `1` | reuse `_get_paginated` unchanged (stops when announced `<=` current) |
| Filters | `search` (substring over CN, issuerOrg, issuerCN, SANs), `status` (case-insensitive), `sortBy` (`name`/`cn`/`status`/`issuer`/`validUntil`), `direction` | not needed |
| Per-cert | `GET /api/certificates/{certificateID}` (fingerprint), 404 if unknown | not needed |
| Availability | Added in v3.7.0 (release 2026-05-05, PR #12628 "Add certificates menu and overview"); `pkg/api/handler_certificate.go` returns GitHub 404 at tags v3.6.25 and v2.11.63, so gorilla/mux has no route and Traefik answers 404 | `TraefikProxyNotFoundError` → probe mode |

Our fixture `tests/fixtures/v3.7/certificates.json` `[VERIFIED: Read, lines 1-21]` contains exactly these keys: `"certFingerprint"`, `"commonName": "secure.example.com"`, `"issuerCN": "secure.example.com"`, `"keySize": 256`, `"keyType": "ECDSA"`, `"name"`, `"notAfter": "2027-02-12T00:17:40Z"`, `"notBefore": "2026-11-13T00:17:40Z"`, `"publicKeyFingerprint"`, `"sans": ["secure.example.com", "www.secure.example.com"]`, `"serialNumber": "455146371953818928500261042643525613849885038955"`, `"signatureAlgorithm": "ECDSA-SHA256"`, `"status": "enabled"`, `"version": "v3"`. No `issuerOrg` appears (self-signed throwaway cert without an O), which shows the omitempty behaviour in practice.

## R-3: Verification without threads or blocking I/O (local experiments)

Environment `[VERIFIED: local venvs]`: dev `.venv`: Python 3.14.10, OpenSSL 3.5.9, HA 2026.10.4, cryptography 50.0.1. `ha2603-venv`: Python 3.14.10, HA 2026.3.0, cryptography 46.0.5. HA pins `[VERIFIED: home-assistant/core package_constraints.txt]`: 2026.3.0 `cryptography==46.0.5`; 2026.11.0 and `dev` `cryptography==50.0.2`.

Experiment (`asyncio.start_server` TLS server on 127.0.0.1 with an SNI callback; client CERT_NONE `PROTOCOL_TLS_CLIENT`; certs generated with `cryptography`). Results were identical in both venvs:

| Case (SNI) | `type(ssl_object)` | `get_unverified_chain()` | Verify vs `Store([test_root])` | Verify vs HA roots |
|-----------|-----------------|--------------------------|--------------------------------|--------------------|
| valid leaf + intermediate | `SSLObject` | 2 × `bytes`, leaf first == `getpeercert(True)` | OK (0.2–0.3 ms) | `VerificationError: ... candidates exhausted` |
| expired leaf | `SSLObject` | 2 × bytes | `... cert is not valid at validation time` | same |
| self-signed leaf | `SSLObject` | 1 × bytes | `candidates exhausted` | same |
| leaf without intermediate sent | `SSLObject` | 1 × bytes | `candidates exhausted` (no AIA fetching) | same |
| wildcard `*.example.test`, SNI `other.example.test` | `SSLObject` | 2 | OK | candidates exhausted |
| wildcard, SNI `a.b.example.test` | — | 2 | `leaf certificate has no matching subjectAltName` | same |
| leaf without SAN | — | 2 | `missing required extension: leaf server certificate has no subjectAltName` | same |

Facts established:
- `get_unverified_chain()` is reachable through the asyncio transport, works under CERT_NONE, and returns DER `bytes`. mypy reveals `list[bytes]`. At C level it can return `None` when no chain exists, so use `chain or []`.
- An expired, self-signed or private-CA certificate always handshakes under CERT_NONE, and the DER leaf parses (D-08 confirmed).
- Every `cryptography` failure raises a single `VerificationError` whose message distinguishes expiry, untrusted, hostname mismatch and missing SAN. `verified` is a plain bool, so catching `VerificationError` → `False` is enough. Log the message at debug level only.
- Test-cert requirements for the cryptography verifier (minimal experiment): the leaf **must** carry `AuthorityKeyIdentifier` (else `invalid extension: 2.5.29.35: Certificate is missing required extension`) and a SAN. The CA must have `BasicConstraints(ca=True)` (critical) and `KeyUsage(key_cert_sign=True)`.
- Trust anchors: `homeassistant.util.ssl` pre-warms all client contexts at module import (`ha2603 util/ssl.py:137-144`, comment *"creating SSL contexts loads certificates from disk, which is blocking I/O that must not happen in the event loop"*). `client_context()` returns the cached object. `get_ca_certs(binary_form=True)` only reads memory and returned 118 DER roots. Parse + `Store` took about 1 ms.
- HA blocking-call detection (`homeassistant/block_async_io.py`, 2026.3) patches `SSLContext.load_default_certs`, `load_verify_locations` (allowed only with `cadata=` alone), `load_cert_chain`, `set_default_verify_paths`, `builtins.open`, `Path.*`, `time.sleep`, etc. It does **not** patch `get_ca_certs` or the `SSLContext(...)` constructor. All entries have `skip_for_tests=True`, so tests will **not** catch a regression. Use a grep gate instead (see Pitfalls).
- certifi roots with serial number 0 (GoDaddy G2, Starfield G2 ×2, SECOM RootCA2, HARICA 2015 ×2) raise `CryptographyDeprecationWarning: Parsed a serial number which wasn't positive ... will cause an exception in a future release` on load, in both 46.0.5 and 50.0.1. Suppress that warning category during the root load, and catch `ValueError` per root (skip the root) for the future version.
- HA 2026.11 adds `homeassistant/util/ca_certs.py` `certifi_ca_data()` (concatenated DER, built from `get_ca_certs`). It is **not** usable while the minimum is 2026.3; `client_context().get_ca_certs()` works on both.
- `cryptography` ships `py.typed`. A probe module using `PolicyBuilder`, `Store`, `VerificationError`, `load_der_x509_certificate`, `SubjectAlternativeName.get_values_for_type(DNSName)` and `SSLObject.get_unverified_chain()` passed `mypy --strict` (mypy 2.4.1) with no ignores.

**Mechanism recommendation (D-10):** a single CERT_NONE handshake plus offline `cryptography` verification. Rejected alternative: a second verifying handshake with `client_context()`. It doubles connections and needs a second error path to tell "untrusted" apart from "failed". Its hostname semantics differ (OpenSSL vs. RFC 6125 strict), and the decision log forbids blocking I/O anyway. Keep it only as a fallback if a future cryptography version rejects too many real roots.

**Exception classes of `asyncio.open_connection(..., ssl=CERT_NONE ctx)` on Python 3.14 (measured):**

| Situation | Exception | Note |
|-----------|-----------|------|
| refused, IP literal | `ConnectionRefusedError` | |
| refused, name with v4+v6 (e.g. `localhost`) | plain `OSError("Multiple exceptions: ...")` | classified `oserror`, not `refused`; acceptable, document |
| peer closes during handshake | `ConnectionResetError` | `oserror` |
| non-TLS port (HTTP) | `ssl.SSLError [SSL: WRONG_VERSION_NUMBER]` | `ssl` (needs SSLError before OSError) |
| hang | `TimeoutError` (from `asyncio.timeout`) | **`TimeoutError` is an `OSError` subclass**, so catch it before `OSError` |
| unresolvable | `socket.gaierror` | `dns` |
| Traefik `sniStrict` without a cert | TLS alert → `ssl.SSLError` | `ssl` |

`ssl.SSLError` and `socket.gaierror` are both `OSError` subclasses. Required order: `TimeoutError` → `ssl.SSLError` → `socket.gaierror` → `ConnectionRefusedError` → `OSError` → `Exception` (`unknown`).

## Recommendations for the planner (R → decision)

| Research | Decision | Recommendation |
|----------|----------|----------------|
| R-1 | D-03, D-15 | API mode: uncovered host → `reason=not_found` (no probe, `source=api`, no `not_after`). Keep `not_found` in the D-15 precedence (`expired` > `probe_failed` > `not_found` > `expiring`). Match on `sans ∪ {common_name}` |
| R-2 | D-01, D-10 | `async_get_certificates()` = `_get_paginated("/api/certificates")` + `parse_certificates()`; `issuer_cn` optional; `not_after` via `fromisoformat` (aware UTC); `status` stored but unused for semantics; `verified=None` in API mode; 404 → probe |
| R-3 | D-07, D-08, D-10, D-11 | Shared bare `ssl.SSLContext(PROTOCOL_TLS_CLIENT)` (`check_hostname=False`, `CERT_NONE`) at module level. Read `getpeercert(True)` + `get_unverified_chain()`. Verify with `cryptography.x509.verification` against a `Store` built lazily once per coordinator from `ha_ssl.client_context().get_ca_certs(binary_form=True)`. Seam: `CertCoordinator(..., trust_store: Store | None = None)` and probe kwarg `trust_store`. Pass `.time(dt_util.utcnow())` explicitly |
| CERT-05 | D-13 | One coordinator timer via `async_track_point_in_utc_time(hass, cb, next_boundary)`; reschedule after each cycle and each fire; cancel in overridden `async_shutdown()` (the coordinator already registers `config_entry.async_on_unload(self.async_shutdown)`, `update_coordinator.py:151` in 2026.3 / `:156` in 2026.10) |

## Standard Stack

No new packages. Everything is bundled with HA or in the stdlib.

| Library | Version (HA 2026.3 / 2026.11) | Purpose |
|---------|------------------------------|---------|
| `cryptography` | 46.0.5 / 50.0.2 `[VERIFIED: HA package_constraints.txt]` | `x509.load_der_x509_certificate`, `x509.verification.{PolicyBuilder, Store, VerificationError}` (API identical in both, verified by running) |
| stdlib `ssl` / `asyncio` | Python 3.14 | CERT_NONE handshake, `SSLObject.get_unverified_chain()` (3.13+) |
| `homeassistant.util.ssl` | HA | `client_context()` pre-built trust anchors |
| `homeassistant.helpers.event` | HA | `async_track_point_in_utc_time(hass, action, point_in_time) -> CALLBACK_TYPE` (same signature in 2026.3 and 2026.10) |
| `pytest-freezer` (`freezer`) | 0.4.9 (dep of phcc) | already used in `tests/test_devices.py`, `tests/test_coordinator.py` |

## Package Legitimacy Audit

No external packages are installed by this phase (`requirements: []` stays; `cryptography` comes with HA; no new dev dependency).

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none) | — | — | — | — | — | — |

**Packages removed due to [SLOP] verdict:** none. **Packages flagged [SUS]:** none.

## Architecture Patterns

### Data flow (cert cycle)
```
cert cycle (6h | Refresh now | update_entity)
   │
   ├─ host set  ← main snapshot TLS routers (tls_domains + rules.extract_hosts) → sort → cap 200
   │
   ├─ GET /api/certificates (paginated)
   │     ├─ 200 → parse → per host: best SAN/CN match ──┬─ match   → state(cert, source=api, verified=None)
   │     │                                               └─ none    → state(error=not_found, source=api)
   │     ├─ 404 → probe mode
   │     └─ other API error → UpdateFailed (entities unavailable)
   │
   └─ probe mode: per host (Semaphore 4, timeout 5s)
         connect(entry-URL host, TLS entrypoint port, SNI=host, CERT_NONE)
           ├─ ok  → DER leaf + chain → parse → verify(Store, now, host) → state(cert, verified=bool, failures=0)
           └─ err → classify → state(last cert kept, last_error, failures+1)
   │
   └─ schedule day-boundary timer (min over hosts) → async_update_listeners()
entities: days = (not_after - utcnow()) // 1 day; reason by precedence; write on change
```

### Pattern: threadless probe + offline verification
```python
# Source: experiments in this session (both venvs); names are proposals
import asyncio, ssl, warnings
from collections.abc import Sequence
from datetime import datetime
from cryptography import x509
from cryptography.utils import CryptographyDeprecationWarning
from cryptography.x509.verification import PolicyBuilder, Store, VerificationError
from homeassistant.util import ssl as ha_ssl

_PROBE_CONTEXT = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # no disk I/O: no load_*_certs
_PROBE_CONTEXT.check_hostname = False
_PROBE_CONTEXT.verify_mode = ssl.CERT_NONE

def default_trust_store() -> Store:
    roots: list[x509.Certificate] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CryptographyDeprecationWarning)  # serial-0 roots
        for der in ha_ssl.client_context().get_ca_certs(binary_form=True):
            try:
                roots.append(x509.load_der_x509_certificate(der))
            except ValueError:
                continue
    return Store(roots)

def chain_verified(chain: Sequence[bytes], host: str, store: Store, now: datetime) -> bool:
    leaf = x509.load_der_x509_certificate(chain[0])
    inters = [x509.load_der_x509_certificate(d) for d in chain[1:]]
    verifier = PolicyBuilder().store(store).time(now).build_server_verifier(x509.DNSName(host))
    try:
        verifier.verify(leaf, inters)
    except VerificationError:
        return False
    return True

async def read_chain(connect_host: str, port: int, sni: str, timeout: float) -> tuple[bytes, list[bytes]] | None:
    async with asyncio.timeout(timeout):
        _reader, writer = await asyncio.open_connection(connect_host, port, ssl=_PROBE_CONTEXT, server_hostname=sni)
    try:
        ssl_obj = writer.get_extra_info("ssl_object")
        if not isinstance(ssl_obj, ssl.SSLObject):
            return None
        der = ssl_obj.getpeercert(binary_form=True)
        return (der, list(ssl_obj.get_unverified_chain() or [])) if der else None
    finally:
        writer.close()
        try:
            async with asyncio.timeout(timeout):
                await writer.wait_closed()
        except (TimeoutError, OSError):
            writer.transport.abort()
```
Wrap the whole probe in the `except` order from R-3. A DER parse `ValueError` → `parse`, `None` → `empty`. If `chain` is empty but the leaf exists, verify with `[der]`.

### Pattern: live days + day-boundary timer
```python
# floor days, signed: timedelta // timedelta is floor division (negative-safe)
days = (not_after - dt_util.utcnow()) // timedelta(days=1)
# next change of `days` for one host: floor((na-now)/1d) == k changes at na - k*1d
k = (na - now) // timedelta(days=1)
boundary = na - k * timedelta(days=1)
if boundary <= now:
    boundary += timedelta(days=1)  # only at exact equality
# schedule min(boundary) over hosts with a not_after; covers threshold crossing, expiry, daily change
self._unsub_timer = async_track_point_in_utc_time(self.hass, self._handle_boundary, min(boundaries))
```
`_handle_boundary` → `self.async_update_listeners()` and reschedule. Cancel the old unsub before rescheduling, after every cycle, and in `async_shutdown`. Verified: `async_track_point_in_utc_time` fires under `freezer.move_to(...)` + `async_fire_time_changed(hass, dt_util.utcnow())` in both venvs.

### Anti-patterns to avoid
- `ssl.create_default_context()` or `load_default_certs()` for the probe context: blocking disk I/O in the loop (flagged by HA at runtime, **not** in tests).
- Using the API `status` field for `expiring`/`expired`: its 30-day window is fixed and the value was computed at fetch time.
- Probing API-uncovered hosts: you read `TRAEFIK DEFAULT CERT` (≈1 year valid) and hide the problem.
- `cryptography` verification without `.time(...)`: it then uses the real system clock, which `freezer` does not affect, so tests become non-deterministic.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Chain / expiry / hostname validation | own issuer-walk, date checks, SAN logic for `verified` | `cryptography.x509.verification` `build_server_verifier` | Path building, name constraints, wildcard rules, EKU, validity windows |
| Trust anchors | reading certifi/system bundle files | `homeassistant.util.ssl.client_context().get_ca_certs(binary_form=True)` | pre-built at import; no disk I/O; respects HA's `REQUESTS_CA_BUNDLE` |
| DER parsing | `getpeercert()` dict / notAfter strings | `x509.load_der_x509_certificate` (`not_valid_after_utc`, SAN extension) | locale-free, typed |
| Pagination | new loop | existing `TraefikProxyApiClient._get_paginated` | identical Traefik pagination contract |
| Point-in-time scheduling | `asyncio.sleep` loops / `call_later` | `async_track_point_in_utc_time` | freezer / `async_fire_time_changed`-testable, cancel handle |

## Common Pitfalls

### P1: `TimeoutError` caught as `oserror`
**What goes wrong:** with `except OSError` before `except TimeoutError`, every timeout is classified `oserror`. **Why:** `TimeoutError` subclasses `OSError` (measured). **Avoid:** use the order from R-3. **Detect:** a test against a hanging server asserts `timeout` (without `freezer`, see P3).

### P2: Multi-address refused shows up as plain `OSError`
`open_connection("localhost", 1)` raises `OSError("Multiple exceptions: ...")`, not `ConnectionRefusedError`. In tests, use `127.0.0.1` for the `refused` case and document that names with v4+v6 may report `oserror`.

### P3: `freezer` freezes the loop clock
Under phcc's `freezer`, `time.monotonic()` and `loop.time()` do not advance (measured `0.0`). `asyncio.sleep()` hung forever in the experiment, and `asyncio.timeout` never fires. **Avoid:** timeout tests must not use `freezer`. Real TLS handshakes under `freezer` work (measured: probe OK). Advance wall time only via `freezer.move_to/tick` + `async_fire_time_changed`.

### P4: pytest-socket and DNS in tests
phcc allows sockets only to `127.0.0.1` and only with the `socket_enabled` fixture; `getaddrinfo` for names raises `RuntimeError("DNS resolution disabled in tests")`, which would classify as `unknown`. **Avoid:** connect to `127.0.0.1` with SNI = test host. For `dns`, monkeypatch `socket.getaddrinfo` to raise `socket.gaierror` (existing pattern in `tests/test_tls.py:233-250`).

### P5: Test certificates rejected by the cryptography verifier
The leaf needs `AuthorityKeyIdentifier` + SAN; the CA needs critical `BasicConstraints(ca=True)` + `KeyUsage(key_cert_sign, crl_sign)`. Without them, "valid" test certs verify `False`. Put one cert factory in `tests/conftest.py` with these defaults, valid relative to `dt_util.utcnow()` (frozen time).

### P6: Serial-0 certifi roots
Loading HA's roots emits `CryptographyDeprecationWarning` (6 roots), and a future cryptography raises. Suppress the category during the load, skip per-root `ValueError`. Do not drop the warning filter.

### P7: Blocking-call regressions are invisible in tests
`block_async_io` entries carry `skip_for_tests=True`. Add a grep gate: none of `to_thread|run_in_executor|create_connection|load_default_certs|load_verify_locations|create_default_context|set_default_verify_paths` appear in `tls.py` / `cert_coordinator.py`.

### P8: `wait_closed()` can hang on SSL shutdown
asyncio's SSL shutdown waits for close_notify (default `ssl_shutdown_timeout` 30 s). Guard `wait_closed` with the timeout and `transport.abort()` on failure, or pass `ssl_shutdown_timeout=` to `open_connection`.

### P9: First-refresh catch-all marks the cert coordinator successful
`__init__.py:253-261` catches any first-refresh error and calls `cert_coordinator.async_set_updated_data({})`, which sets `last_update_success=True`. With D-02 (non-404 API error → `UpdateFailed`) and D-15 (availability = last cycle succeeded), that path must not fake success, or must set the new empty per-host state type. Revisit it in the coordinator task.

### P10: Unstable pagination order
Certificates are sorted by CN with an unstable sort. With many CN-less certs and more than one page, items may repeat or be skipped across pages. Keep `DEFAULT_PAGE_SIZE = 500` (`api.py:32`, verbatim `DEFAULT_PAGE_SIZE = 500`, `MAX_PAGES = 100`) and do not dedupe on `name` (zeroed in the fixture).

### P11: IP-literal hosts
`Host(\`192.168.1.10\`)` passes `extract_hosts`. For verification, use `x509.IPAddress(ipaddress.ip_address(host))` instead of `DNSName` when the host is an IP. Python's ssl sends no SNI for IP `server_hostname`, so Traefik then matches on the local address. LOW impact; one branch.

## Code Examples

### Parse one API certificate (shape)
```python
# Source: traefik pkg/api/certificate.go @ v3.7.19 (JSON tags quoted in R-2)
not_after = datetime.fromisoformat(_required_str(item, "notAfter"))  # "2027-02-12T00:17:40Z"
if not_after.tzinfo is None:
    raise ValueError("naive notAfter")
cert = TraefikCertificate(
    common_name=_str(item, "commonName"),
    sans=_str_tuple(item, "sans"),
    not_after=not_after.astimezone(UTC),
    not_before=...,  # same as notAfter
    issuer_cn=item.get("issuerCN") or None,  # omitempty
    status=_str(item, "status"),  # "enabled" | "warning" | "expired"
    serial_number=_str(item, "serialNumber"),
)
```

### Test seam for a trusted test CA
```python
coordinator = CertCoordinator(hass, entry, trust_store=Store([test_root]))  # proposed kwarg
# chain served by the local server = [leaf(AKI, SAN=host), intermediate]; SNI=host → verified True
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `asyncio.to_thread(socket + ssl.wrap_socket)` + `getpeercert()` dict | `asyncio.open_connection` CERT_NONE + DER + `cryptography` | Phase 6 | no threads; expired/self-signed readable |
| Probe only | `/api/certificates` on Traefik >= 3.7 | Traefik v3.7.0 (2026-05-05) | zero handshakes on modern Traefik |
| `SSLSocket.getpeercert` leaf only | `SSLObject.get_unverified_chain()` | Python 3.13 | offline chain verification possible |
| certifi file loaded per context | `certifi_ca_data()` (DER, cached) | HA 2026.11 | available only after the minimum moves past 2026.3 (Phase 7) |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | A future cryptography release turns serial-0 roots from warning into `ValueError` (per the warning text) and HA would pin it | R-3 / P6 | Six roots are skipped, so GoDaddy/Starfield-chained hosts verify `False`; mitigation: fall back to a verifying handshake |
| A2 | Python sends no SNI for IP-literal `server_hostname` | P11 | IP hosts may map differently; LOW impact |
| A3 | Traefik answers a `sniStrict` miss with a TLS alert that Python raises as `ssl.SSLError` (inferred from the Go comments in `tlsmanager.go:258-266`, not run) | R-3 table | Could surface as `ConnectionResetError` → `oserror`; both are failures counted toward `probe_failed` |

## Open Questions (RESOLVED)

1. **Should `not_found` require 2 consecutive cycles (like `probe_failed`)?**
   - Known: an ACME-pending new router shows `not_found` until the next cycle. Clients really get the default cert meanwhile.
   - Recommendation: no, report it immediately (truthful). The "Refresh now" button re-checks. Note it in the SUMMARY.
   - **RESOLVED:** reported immediately, no failure count. Locked by CONTEXT D-03 ("`not_found` does not wait for the failure count") and D-15. Implemented in 06-05 Task 1 (API mode maps an uncovered host to `not_found`, no probe) on the `HostCertState.problem` precedence of 06-04; the SUMMARY records the pending-ACME behaviour as a user-visible change.
2. **Fixture for the v2.11 404.** No `certificates.json` exists for v2.11 (the capture harness only fetches it for v3.7, `tests/traefik/capture.py:67,374`). Use `aioclient_mock` with `status=404` for `/api/certificates`. No re-capture needed.
   - **RESOLVED:** no re-capture. 06-02 Task 2 makes `stub_traefik` / `stub_traefik_paginated` answer `/api/certificates` with the capture's `certificates.json` when it exists (v3.7) and HTTP 404 otherwise (v2.11); 06-05 Task 1 drives the source-selection tests with it (D-21).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | all | ✓ | 3.14.10 (both venvs) | — |
| cryptography | DER parse, verify | ✓ | 50.0.1 (dev), 46.0.5 (ha2603) | — |
| OpenSSL | TLS | ✓ | 3.5.9 | — |
| pytest-freezer | D-20 | ✓ | 0.4.9 | — |
| phcc | tests | ✓ | 0.13.375 (dev), 0.13.317 (ha2603) | — |
| mypy | D-19 | ✓ (dev venv) | 2.4.1 | — |
| Docker / real Traefik | not needed | — | — | source reading replaced it |

## Test Harness Notes (nyquist validation disabled; kept short)

- Real-handshake tests: `socket_enabled` fixture, server on `127.0.0.1:0`, server `SSLContext.load_cert_chain` from `tmp_path` files, `sni_callback` swapping `sslobj.context` per SNI (spike 003 pattern). Chain files contain leaf + intermediate PEM.
- Cases: valid (test CA trusted → `verified=True`), expired, self-signed, private CA (CA not trusted → `False`), wildcard single label, missing intermediate, non-TLS port (`ssl`), closed port on `127.0.0.1` (`refused`), hanging server (`timeout`, no freezer), `gaierror` monkeypatch (`dns`).
- Source selection: `aioclient_mock` serving `tests/fixtures/v3.7/certificates.json` (assert zero probe calls) and 404 (assert probe path, `source=probe`).
- Timer: `freezer.move_to(not_after - threshold days + 1s)` + `async_fire_time_changed` → `reason=expiring`; past `not_after` → `expired`; no probe calls in between.

## Security Domain

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | `parse_certificates` rejects non-list / naive dates / wrong types → `TraefikProxyPayloadError`; DER parse errors → `parse` |
| V6 Cryptography | yes | No custom crypto: `cryptography` verifier; CERT_NONE is used **only** to read certificates, never to send data (the probe sends nothing and closes) |
| V7 Errors/Logging | yes | Never log API token; `VerificationError` text at debug level only; one WARNING per cycle for the cap |
| V2/V3/V4 | no | No auth/session changes |

| Threat | STRIDE | Mitigation |
|--------|--------|------------|
| Hostile config with thousands of hosts | DoS | cap 200, Semaphore 4, 5 s timeout, bounded per-host dicts (D-06/D-14/D-18) |
| MITM on probe path | Spoofing | Probe data is only informational; `verified` reflects trust honestly; no credentials are sent over the probe connection |
| Oversized API payload | DoS | `MAX_PAGES = 100` guard in `_get_paginated` |

## Sources

### Primary (HIGH)
- github.com/traefik/traefik @ v3.7.19 (sparse clone, read): `pkg/api/certificate.go`, `pkg/api/handler_certificate.go`, `pkg/api/handler.go:66-90,132-133`, `pkg/api/criterion.go`, `pkg/api/sort.go:355-419`, `pkg/tls/tlsmanager.go`, `pkg/tls/certificate_store.go`, `pkg/tls/generate/generate.go`, `pkg/provider/acme/provider.go`, `pkg/server/service/managerfactory.go:46`
- GitHub API: `handler_certificate.go` 404 at v3.6.25 and v2.11.63; present at v3.7.0; `certificate.go` identical v3.7.0 / v3.7.19 / v3.8.0-rc.3; v3.7.0 release notes (2026-05-05, PR #12628)
- home-assistant/core `homeassistant/package_constraints.txt` @ 2026.3.0, 2026.11.0, dev; `homeassistant/util/ssl.py` + `util/ca_certs.py` @ 2026.11.0
- Local: `homeassistant/util/ssl.py`, `block_async_io.py`, `helpers/update_coordinator.py`, `helpers/event.py` in both venvs; phcc `plugins.py:205-250`
- Experiments (scratchpad, run in both venvs): CERT_NONE probe + chain + verification matrix; minimal-extension test; exception classification; freezer + timer + real TLS under freezer; `mypy --strict` typing probe

### Secondary
- Spike skill `.claude/skills/spike-findings-homeassistant-traefik-integration/` (spike 003 SNI-callback pattern, 005 `open_connection` drop-in)

## Metadata

**Confidence breakdown:**
- R-1 / R-2: HIGH, read from pinned Traefik source; endpoint absence confirmed per tag.
- R-3: HIGH, executed in both target venvs; only A1–A3 are assumptions.
- Pitfalls: HIGH for P1–P8 (measured); MEDIUM for P11.

**Research date:** 2026-11-15
**Valid until:** 2026-12-15 (re-check if Traefik v3.8 final changes `pkg/api/certificate.go` or HA bumps cryptography past 50.x)
