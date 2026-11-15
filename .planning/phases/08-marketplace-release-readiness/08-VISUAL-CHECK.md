# Phase 8 — Visual check (M35, D-25) and local brand serving (D-04, REL-02)

Run on 2026-11-15 by the 08-09 executor in a throwaway Home Assistant 2026.11.0
plus the throwaway Traefik v3 harness. No real Home Assistant instance was used.
All containers, the harness network and both HA volumes were removed afterwards
(see "Cleanup").

## Setup

| Component | Image / version | Digest |
|---|---|---|
| Home Assistant | `ghcr.io/home-assistant/home-assistant:2026.11.0` (`/api/config` reports `2026.11.0`) | `sha256:c6c1ca9931036bf3a2c4cc088d8db25dfea3b33935a5ecc83c40349462e2f69e` |
| Traefik | `traefik:v3.7.19` from `tests/traefik/compose.yaml` (`/api/version` reports `3.7.19`, codename `langres`) | `sha256:b7b1b31e6440de0b1f7c4e0f6cf0a0f3f004866761d30c025fe00c80daaf7d9c` |
| whoami | `traefik/whoami:v1.12.0` from the same compose file | `sha256:c4717a8d1f0134a7444e24f881160e033991f23027c6c5a9a3f8fd22e70d1d44` |
| Integration | working tree of `feat/marketplace-polish`, manifest `1.0.0`, mounted read-only | — |

Commands (no secrets; the HA user password and tokens were generated at run time,
kept in a `0600` file in the executor's scratch directory, never printed and
deleted at teardown):

```bash
docker compose -f tests/traefik/compose.yaml up -d whoami traefik-v3   # network traefik-harness_default
docker volume create ha-visual-08-config
docker run -d --name ha-visual-08 --network traefik-harness_default \
  -p 127.0.0.1:18123:8123 -e TZ=Europe/Berlin \
  -v ha-visual-08-config:/config \
  -v "$PWD/custom_components/traefik_proxy":/config/custom_components/traefik_proxy:ro \
  ghcr.io/home-assistant/home-assistant:2026.11.0
```

- `/api/onboarding` answered 200 after 4 s.
- Onboarding through REST: `POST /api/onboarding/users` (throwaway user `visual`,
  random password) -> `auth_code` -> `POST /auth/token` -> `core_config`,
  `analytics`, `integration` (all 200).
- WS `config/core/update {"country": "DE"}` succeeded, so core's
  `country_not_configured` repair did not appear (assumption A1 confirmed).
- Config flow through REST: `POST /api/config/config_entries/flow
  {"handler": "traefik_proxy"}` -> form `user` with fields `url`, `verify_ssl`,
  `auth_type`, `username`, `password`, `token`; submitted with
  `url=http://traefik-v3:8080`, `auth_type=basic` and the harness-only
  credentials from `tests/traefik/capture.py` -> `create_entry`, title
  `traefik-v3`, **151 entities**.
- Repairs (WS `repairs/list_issues`): `insecure_credentials_<entry_id>` only.
- Devices (WS `config/device_registry/list`): `Traefik (traefik-v3)` plus
  `Traefik routers (traefik-v3)`, `Traefik services (traefik-v3)` and
  `Traefik certificates (traefik-v3)`, each with `via_device_id` = the main device.

## Brand serving (D-04)

Each image was requested with the HA Bearer token from
`/api/brands/integration/traefik_proxy/<image>?placeholder=no` (`curl -w
'%{http_code} %{content_type}'`) and the body's sha256 compared with the shipped
file in `custom_components/traefik_proxy/brand/`.

| Image | HTTP | Content type | sha256 vs shipped | sha256 (first 12 hex) |
|---|---|---|---|---|
| icon.png | 200 | image/png | match | e673beb5fb85 |
| icon@2x.png | 200 | image/png | match | e25cb6e1626a |
| logo.png | 200 | image/png | match | f0d7d448d440 |
| logo@2x.png | 200 | image/png | match | 1e63160a40d7 |
| dark_logo.png | 200 | image/png | match | 66228f7fe4ac |
| dark_logo@2x.png | 200 | image/png | match | c37e8caf6661 |

No fallback answered (F6: fallbacks apply to local files too, so the bytes were
compared): served `logo.png` != `icon.png`, `dark_logo.png` != `logo.png`,
`logo@2x.png` != `icon@2x.png`, `dark_logo@2x.png` != `logo@2x.png`,
`dark_logo.png` != `icon.png`. Home Assistant 2026.11.0 therefore serves exactly
the brand images the repository ships (REL-02).

## Tool provenance

| Tool | Version | Source / author | How it ran |
|---|---|---|---|
| Playwright (Python) | 1.65.2 | PyPI `playwright`, author "Microsoft Corporation", licence Apache-2.0, homepage https://github.com/Microsoft/playwright-python | ephemeral `uv run --no-project --with playwright --with pillow --with websockets` (D-32); never added to the project |
| Browser | `chromium_headless_shell-1254` | `~/.cache/ms-playwright` (matches Playwright 1.65.2; passed as `executable_path`) | headless, against `127.0.0.1` only |
| websockets | latest from PyPI (ephemeral) | — | WS API calls (device/entity registry, repairs, core config) |
| Pillow | latest from PyPI (ephemeral) | — | PNG -> JPEG q75 conversion of the screenshots |

The helper scripts lived in the executor's scratch directory and were not committed.
Tracer screenshot: `visual/en-10-integration-light.jpg` (51 KB).

## Screenshots

All shots: headless Chromium, viewport 1280x1200, JPEG q75, `visual/<lang>-<NN>-<slug>.jpg`.
The frontend language was set through `localStorage.selectedLanguage`, the theme
through `localStorage.selectedTheme` plus the browser colour scheme.

Entity and device names are rendered by the Home Assistant **backend** in the
system language (`config/core/update {"language": …}`), states and forms by the
frontend in the user's language. The German shots were therefore taken with the
HA system language set to `de` and the English shots with `en` (each followed by
a container restart, so the registry names are re-translated); otherwise the
device page would mix German UI chrome with English entity names. This is Home
Assistant's design, not a finding.

For every shot the page text (including shadow DOM and `label` / `placeholder` /
`aria-label` / `title` attributes) was read and checked for `component.traefik_proxy.`
and `[%key:`: **0 hits in all 24 shots of Task 2** (and in the two Task 3 shots, see
"Migration"). Every image was also inspected by eye.

| File | Language | Screen | What it shows |
|---|---|---|---|
| de-01-flow-auth-none.jpg | de | Add flow, auth none | "Mit Traefik verbinden": URL, "TLS-Zertifikat prüfen", radio list "Keine Authentifizierung" (selected) / "Basic Auth (Benutzername und Passwort)" / "Bearer-Token"; no credential fields |
| de-02-flow-auth-basic.jpg | de | Add flow, auth basic | Basic selected; conditional fields "Benutzername" and "Passwort" (with reveal icon) appear |
| de-03-flow-auth-bearer.jpg | de | Add flow, auth bearer | Bearer selected; only the "Bearer-Token" field is shown (empty, nothing typed) |
| de-04-options.jpg | de | Options form | "Traefik-Optionen": Abfrageintervall 15 **s**, TLS-Zertifikat prüfen, Warnschwelle 14 **d**, "Entitäten für Router und Dienste anlegen", "Karenzzeit für fehlende Entitäten" 24 **h**, with ranges in the help texts |
| de-05-repair-insecure-credentials.jpg | de | Repair dialog | "Traefik-Zugangsdaten werden unverschlüsselt gesendet", text names the entry „traefik-v3“ and the Reconfigure path |
| de-06-device-main.jpg | de | Main device | "Traefik (traefik-v3)", Version 3.7.19, problem aggregates (Dienst-/Middleware-/Router-/Zertifikatsprobleme), Diagnose sensors, "Jetzt aktualisieren", "Verbundene Geräte": Traefik-Dienste / Traefik-Router / Traefik-Zertifikate (traefik-v3); light logo top right |
| de-07-device-routers.jpg | de | Routers sub-device | "Verbunden über Traefik (traefik-v3)"; router sensors with states "Fehler" (alert icon) and "Aktiviert" (signpost icon) |
| de-08-device-certificates.jpg | de | Certificates sub-device | per-host "… läuft ab" = OK (lock-check icon) and "… Ablauf" = "In 3 Monaten" (certificate icon) |
| de-09-refresh-pressed.jpg | de | Refresh now after press | More-info of "Jetzt aktualisieren": "Vor 3 Sekunden", activity "Gedrückt" |
| de-10-integration-light.jpg | de | Integration page, light | Brand icon, "Version 1.0.0", "Benutzerdefinierte Integration", entry `traefik-v3` with main + 3 sub-devices |
| de-11-integration-dark.jpg | de | Integration page, dark | Same page in the dark theme; the page header uses `icon.png` (HA shows no logo on this page) |
| de-13-device-main-dark.jpg | de | Main device, dark | Device page in the dark theme: top right shows `dark_logo.png` (light lettering) — the D-28 dark logo in use |
| en-01-flow-auth-none.jpg | en | Add flow, auth none | "Connect to Traefik", "No authentication" selected, no credential fields |
| en-02-flow-auth-basic.jpg | en | Add flow, auth basic | "Basic auth (username and password)" selected; "Username" and "Password" fields shown |
| en-03-flow-auth-bearer.jpg | en | Add flow, auth bearer | "Bearer token" selected; only the "Bearer token" field (empty) |
| en-04-options.jpg | en | Options form | "Traefik options": Polling interval 15 s, Verify TLS certificate, Certificate warning threshold 14 d, "Create router and service entities", "Grace period for missing entities" 24 h |
| en-05-repair-insecure-credentials.jpg | en | Repair dialog | "Traefik credentials are sent unencrypted", names "traefik-v3" |
| en-06-device-main.jpg | en | Main device | Problem aggregates, diagnostics, "Refresh now", "Connected devices" with the three sub-devices |
| en-07-device-routers.jpg | en | Routers sub-device | "Connected via Traefik (traefik-v3)"; "Error" / "Enabled" router states with icons |
| en-08-device-certificates.jpg | en | Certificates sub-device | "… expiring" = OK, "… expiry" = "In 3 months" |
| en-09-refresh-pressed.jpg | en | Refresh now after press | More-info: "3 seconds ago", activity "Pressed" |
| en-10-integration-light.jpg | en | Integration page, light | Brand icon, "Version 1.0.0", "Custom integration", 4 services / 151 entities |
| en-11-integration-dark.jpg | en | Integration page, dark | Dark theme of the same page |
| en-13-device-main-dark.jpg | en | Main device, dark | Dark theme; `dark_logo.png` top right |

Both add flows were closed with the dialog's close action; WS
`config_entries/flow/progress` listed no open `traefik_proxy` flow afterwards, and
no second entry was created. The options flow was also closed without submitting.

## Findings

| ID | Language | Screen | Finding | Cause | Resolution |
|---|---|---|---|---|---|
| F-01 | de, en | 08 certificates sub-device | Long certificate entity names ("www.secure.example.com expiring" / "… läuft ab") are cut with an ellipsis in the device page's Sensors card; the full name is in the tooltip, the activity list and more-info | cosmetic | listed |
| F-02 | — (log) | system language change de | Switching the HA system language through `config/core/update` logged `WARNING homeassistant.helpers.translation: Failed to load integration for translation: Invalid domain <domain>.<platform>` for core and custom integrations alike (`backup.sensor`, `sun.sensor`, `traefik_proxy.sensor`, …); nothing visible, entity names were correct after the restart | upstream | deferred-items F-02 |

No finding has a cause in this repository, so no `fix(08-09)` commit was needed.
Observations that are Home Assistant's design and not findings: the unit symbols
`s`, `d`, `h` in the options form are the language-neutral `UnitOfTime` symbols;
the integration page shows the icon (not the logo) in both themes; on the main
device the "Download diagnostics" action sits in the overflow menu because the
device has a `configuration_url` ("Visit"), while the sub-devices show it inline.
