<!--
DRAFT for the GitHub pre-release v1.0.0-rc1 (created by the user, not by an agent).
Paste everything below the "----- cut -----" line as the release body.
Before publishing:
  1. Push first: the tagged commit must exist on GitHub, and its manifest.json
     version must be 1.0.0-rc1.
  2. Release title: "Traefik Proxy 1.0.0-rc1", tag `v1.0.0-rc1` (the release
     workflow strips the `v` and compares the tag with manifest.json).
  3. In the GitHub release form, tick "Set as a pre-release" and do not tick
     "Set as the latest release".
  4. The CHANGELOG is already dated (`## [1.0.0-rc1] - 2026-11-18`); the change
     list link below needs no anchor edit.
For the final 1.0.0: set manifest.json and pyproject.toml back to 1.0.0, run
`uv lock`, date the [1.0.0] heading and use 08-RELEASE-NOTES-v1.0.0.md.
This file is a planning draft; it is not shipped and not part of the integration.
----- cut -----
-->

# Traefik Proxy 1.0.0-rc1 (release candidate)

This is a pre-release for testing before 1.0.0. It contains every 1.0.0 change
described below. Feedback is welcome.

## Before you upgrade from 0.3.x

- **Make a full Home Assistant backup** (Settings → System → Backups) or a
  snapshot of the VM or container first.
- This release migrates the config entry and replaces entities: the router
  binary sensors are removed, and the old devices are replaced by a main device
  with sub-devices. Going back to 0.3.x does not restore them; restoring the
  backup is the way back.
- Home Assistant 2026.11.0 or later is required; HACS refuses older versions.
- Read "Required actions" below before you update.

## Install the release candidate with HACS

- **Already installed:** HACS creates a switch entity for each downloaded
  repository that includes pre-releases in update checks. The switch is
  disabled by default. Enable it under Settings → Devices & services →
  Entities, then turn it on, and HACS offers 1.0.0-rc1 as an update.
  Alternatively, open Traefik Proxy in HACS, choose **Redownload** and pick
  `v1.0.0-rc1` under "Need a different version?".
- **New install:** if HACS does not list the repository, add
  `https://github.com/akentner/homeassistant-traefik-proxy-integration` as a
  custom repository of type "Integration". In the download dialog, pick
  `v1.0.0-rc1` under "Need a different version?". If it is not listed there,
  download the integration, then enable the pre-release switch and update.
- Restart Home Assistant after the download.
- When 1.0.0 is released, HACS offers it as an update to 1.0.0-rc1. Turn the
  pre-release switch off again if you do not want future pre-releases.

## Feedback

- Open an issue at
  https://github.com/akentner/homeassistant-traefik-proxy-integration/issues
  and say that you run 1.0.0-rc1.
- Include the Home Assistant version and the Traefik version.
- Attach the diagnostics download. Credentials and secret router-rule values
  are redacted, but review the file before you post it.

---

1.0.0 is a major rework of the integration. It changes entity types, entity IDs
and devices. Read the required actions before you update.

## Required actions

1. **Update Home Assistant to 2026.11.0 or later first.** This release does not
   install on older versions.
2. **Update automations, scripts and dashboards that used router binary
   sensors.** Every `binary_sensor.traefik_http_router_*` entity is removed. Each
   router is now an enum sensor with the states `enabled`, `warning`, `error`,
   `disabled` and `missing` (for example `sensor.traefik_routers_<host>_<router>`).
   Service sensors are enum sensors too; their entity IDs are kept, but several
   attributes were removed. `on`/`off` checks become checks on the status.
3. **Dismiss the repair notice "Traefik entities were replaced"** (Settings →
   System → Repairs) once your automations and dashboards are updated. It names
   the entry and the number of removed entities.
4. **Replace the reload button and the `traefik_proxy.reload_routers` action with
   the new "Refresh now" button** (`button.press`). Traefik has no reload API, so
   the old ones never reloaded anything; "Refresh now" re-reads Traefik and the
   certificates at once.
5. **YAML users: re-add the integration through the UI.** The `traefik_proxy`
   block in `configuration.yaml` is no longer read. Entries created from YAML
   earlier stay and are managed in the UI; remove the block and add new
   instances through **Settings → Devices & services**.
6. **Check the repair notice "Traefik credentials are sent unencrypted"** if it
   appears. It means an entry sends credentials to Traefik over plain HTTP.
   Switch the URL to HTTPS through **Reconfigure** or remove the authentication.
7. **Re-assign device areas.** The old per-category devices are replaced by a
   main device "Traefik (`<host>`)" with sub-devices for routers, services and
   certificates. Names or areas set on the old devices are not carried over.

## Highlights

- **Router and service status at a glance:** enum sensors with state-dependent
  icons, plus "Router problems", "Service problems", "Middleware problems" and
  the new "Certificate problems" sensors, enabled by default.
- **One request per polling cycle** (`GET /api/rawdata`) instead of several list
  requests; only GET requests are ever sent to Traefik.
- **Certificates from Traefik itself on 3.7 and later** (`/api/certificates`),
  a TLS probe to the Traefik host on older versions; live days-until-expiry and
  clear problem reasons (`expired`, `expiring`, `not_found`, `probe_failed`).
- **Entities that come and go:** new routers and services appear without a
  reload; vanished ones stay `missing` for a configurable grace period
  (default 24 h) and come back under the same entity ID.
- **Authentication choice:** no authentication, basic auth or bearer token;
  existing entries are migrated automatically. Redirects are never followed
  and credentials are never logged.
- **Diagnostics download** with credentials and secret router-rule values
  redacted, ready to attach to an issue.
- **Full German translation** of forms, entities, states, errors and repair
  notices.
- **Marketplace-ready:** category "Monitoring", new icon, landscape logo and a
  dark-theme logo.

## Full change list

See the [1.0.0 section of CHANGELOG.md](https://github.com/akentner/homeassistant-traefik-proxy-integration/blob/v1.0.0-rc1/CHANGELOG.md#100---unreleased)
for every breaking change, addition, change, removal, fix and security
improvement in this release. 1.0.0-rc1 contains all of it.

Traefik is a trademark of Traefik Labs. This project is not affiliated with or
endorsed by Traefik Labs.
