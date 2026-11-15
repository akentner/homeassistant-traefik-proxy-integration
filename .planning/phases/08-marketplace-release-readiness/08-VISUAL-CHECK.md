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
