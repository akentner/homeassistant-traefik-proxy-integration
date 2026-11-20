<!--
DRAFT for the GitHub release v1.0.0 (created by the user, not by an agent).
Paste everything below the "----- cut -----" line as the release body.
Before publishing:
  1. Push first: the tagged commit must exist on GitHub, and its manifest.json
     version must be 1.0.0. The tag v1.0.0-rc1 carries 1.0.0-rc1 and fails the
     release check, so do not tag 22902d9 as v1.0.0.
  2. Release title: "Traefik Proxy 1.0.0", tag `v1.0.0` (the release workflow
     compares the tag without `v` with manifest.json version 1.0.0).
  3. In the GitHub release form, do not tick "Set as a pre-release", and tick
     "Set as the latest release" (0.3.0 stays the latest release until then;
     v1.0.0-rc1 remains a pre-release).
  4. CHANGELOG.md is dated `## [1.0.0] - 2026-11-20`, and the change-list link
     below uses its anchor `#100---2026-11-20`. If you publish on another day,
     change the CHANGELOG date and this anchor together.
This file is a planning draft; it is not shipped and not part of the integration.
----- cut -----
-->

# Traefik Proxy 1.0.0

1.0.0 is a major rework of the integration. It changes entity types, entity IDs
and devices. Read the required actions before you update.

1.0.0 contains the same integration code as the release candidate 1.0.0-rc1,
which was tested before this release; only the version number differs. If you
already run 1.0.0-rc1, update through HACS; nothing else is needed. The required
actions below apply when you update from 0.3.x.

## Required actions

1. **Update Home Assistant to 2026.11.0 or later first.** 1.0.0 does not install
   on older versions.
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

See the [1.0.0 section of CHANGELOG.md](https://github.com/akentner/homeassistant-traefik-proxy-integration/blob/v1.0.0/CHANGELOG.md#100---2026-11-20)
for every breaking change, addition, change, removal, fix and security
improvement in this release.

Traefik is a trademark of Traefik Labs. This project is not affiliated with or
endorsed by Traefik Labs.
