# Phase 7 — API Coverage Declaration

No external API integration: Phase 7 integrates no new external API. The Traefik API
surface the integration uses is unchanged from Phases 4–6 (`/api/version`,
`/api/entrypoints`, `/api/rawdata` with the paginated list fallback, `/api/certificates`).
The only client-side change is transport behaviour on the existing requests:
`allow_redirects=False` and a new `TraefikProxyRedirectError` for 3xx answers
(07-04-PLAN.md, D-23). Everything else in this phase is Home Assistant–internal
(config/options flows, entry migration, issue and device registries, diagnostics).

This file belongs to phase 07 only; it is not the Phase 4 coverage matrix.
