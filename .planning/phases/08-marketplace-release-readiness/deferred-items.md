# Phase 8 — Deferred items (outside this repository)

| ID | Source | Upstream component | Evidence | Why it cannot be fixed here |
|---|---|---|---|---|
| F-02 | 08-09 visual check | Home Assistant core 2026.11.0, `homeassistant.helpers.translation` | No screenshot (container log of the throwaway HA, 2026-11-15 21:50:23 local time, right after WS `config/core/update {"language": "de"}`): `Failed to load integration for translation: Invalid domain backup.sensor`, the same for `sun.sensor`, `energy.sensor`, `marketplace.update`, `traefik_proxy.sensor` / `.binary_sensor` / `.button` and others | Core reloads translations for `<domain>.<platform>` component names after a language change and treats them as integration domains. It hits core integrations the same way; the integration has no part in that code path. Harmless: after the restart all names were translated correctly. |
