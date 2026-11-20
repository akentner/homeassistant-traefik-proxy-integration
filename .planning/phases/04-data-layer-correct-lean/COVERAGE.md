# API Coverage — Traefik HTTP API (v2.11 / v3.x), Phase 4 data layer

> Full coverage by default. Opt-outs are explicit, reasoned decisions.
> Scope: the read surface of Traefik's `api@internal` handler (GET-only in every
> version from v2.11.0 to v3.7.x, verified against `pkg/api/*.go` in the audit) plus
> the auth mechanisms a user can put in front of it. Plans: 04-01 (capture), 04-03 (models),
> 04-04 (typed paginated reads), 04-05 (auth, taxonomy), 04-06 (rawdata + fallback).
> `/api/rawdata` carries HTTP routers, services (incl. `serverStatus`) and middlewares in map form;
> the list endpoints paginate with `per_page` / `page` and the `X-Next-Page` header.

| capability | decision | reason |
|---|---|---|
| `GET /api/rawdata` (HTTP sections, map form) | INTEGRATE | |
| `GET /api/version` | INTEGRATE | |
| `GET /api/entrypoints` | INTEGRATE | |
| `GET /api/http/routers` (paginated) | INTEGRATE | |
| `GET /api/http/services` (paginated) | INTEGRATE | |
| `GET /api/http/middlewares` (paginated) | INTEGRATE | |
| Pagination (`per_page`, `page`, `X-Next-Page`) | INTEGRATE | |
| Auth: none | INTEGRATE | |
| Auth: HTTP Basic (basicAuth middleware) | INTEGRATE | |
| Auth: Bearer token (token middleware / forward auth) | INTEGRATE | |
| `GET /api/certificates` (Traefik >= 3.7) | OPT-OUT | not needed yet: captured as a v3.7 fixture in 04-01 only; consumed by the Phase 6 cert coordinator (CERT-01) |
| Per-certificate GET (if present in v3.7) | OPT-OUT | not needed: the list endpoint carries every certificate; Phase 6 decides |
| `GET /api/overview` | OPT-OUT | explicitly out of scope: counts are computed from the snapshot (D-15, D-18); dropping it is part of the one-request budget (P-01) |
| `GET /api/entrypoints/{name}` | OPT-OUT | not needed: the list endpoint returns every entrypoint in one call |
| Per-item HTTP GETs (`/api/http/<kind>/{name}`) | OPT-OUT | not needed: rawdata and the list pages carry the same per-item data; per-item GETs would multiply requests (P-01) |
| List filters (`search`, `status`, `serviceName`) | OPT-OUT | not needed: aggregation happens client-side over the full state |
| `GET /api/tcp/*` (routers, services, middlewares) | OPT-OUT | explicitly out of scope: HTTP-only (D-05, DATA-02 "TCP/UDP data is ignored") |
| `GET /api/udp/*` (routers, services) | OPT-OUT | explicitly out of scope: HTTP-only (D-05, DATA-02) |
| TCP/UDP sections of `/api/rawdata` | OPT-OUT | explicitly out of scope: the parser ignores them (D-05) |
| `GET /api/support-dump` (v3.x) | OPT-OUT | not needed; it bundles static configuration and is a privacy risk for a polling integration |
| Dashboard UI (`/dashboard/`) | OPT-OUT | not an API; Phase 5 only links it as `configuration_url` |
| `/ping` and `/metrics` | OPT-OUT | explicitly out of scope for v1: separate opt-in Traefik features with no requirement |
| Write endpoints | OPT-OUT | none exist: the Traefik API is GET-only in every supported version (audit A-04) |
| `POST /api/http/routers/refresh` (legacy) | OPT-OUT | does not exist in any Traefik version; the client method stays untouched and isolated until Phase 5 (ENT-07) removes it with its button and service (D-06) |
| Auth: Digest (digestAuth middleware) | OPT-OUT | not needed: no requirement asks for it; challenge-response would complicate the per-request header |
| Auth: mutual TLS client certificates | OPT-OUT | not needed for v1: no requirement; would need certificate storage in the config entry |
