# Phase 8 — API Coverage Declaration

No external API integration: Phase 8 adds no API surface to the integration. The Traefik API endpoints the integration uses are unchanged from Phases 4–7 (`/api/version`, `/api/entrypoints`, `/api/rawdata` with the paginated list fallback, `/api/certificates`); the only data-path change is that the diagnostics download redacts header/query values of router rules it already receives (08-01). The other API contacts of this phase are release tooling, not integration features: read-only GitHub API calls for the upstream logo source (08-05), by the local `hacs/action` overlay and for the drafts (08-08, 08-13), and the Home Assistant REST/WebSocket API of a throwaway container used only for the visual check (08-09).

This file belongs to phase 08 only; it is not the Phase 4 coverage matrix.
