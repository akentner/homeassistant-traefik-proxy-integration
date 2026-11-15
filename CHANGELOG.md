# Changelog

All notable changes to this integration are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Every release tag gets an entry, also when it has no user-visible change.

## [1.0.0] - Unreleased

### Breaking changes and required actions

- **Home Assistant 2026.11.0 or later is required.** HACS refuses to install
  1.0.0 on older versions. *Action:* update Home Assistant first.
- **YAML setup is removed.** The `traefik_proxy` block in `configuration.yaml`
  is no longer read. Entries created from YAML earlier stay and are managed in
  the UI. *Action:* remove the block from `configuration.yaml`; add new
  Traefik instances through **Settings → Devices & services**.
- **Router binary sensors are replaced by router sensors.** Every
  `binary_sensor.traefik_http_router_*` entity is removed. Each router now has
  an enum sensor with the states `enabled`, `warning`, `error`, `disabled` and
  `missing`. Enabled, visible routers get new entity IDs such as
  `sensor.traefik_routers_<host>_<router>`. Routers you had disabled or hidden
  keep their previous object ID under the sensor domain (for example
  `sensor.traefik_http_router_<name>` instead of
  `binary_sensor.traefik_http_router_<name>`) and stay disabled or hidden; only
  the disabled/hidden flag is carried over, not names, areas or labels.
  *Action:* update automations, scripts and dashboards that used router
  entities (`on`/`off` becomes the router status). A repair notice "Traefik
  entities were replaced" names the entry and the number of removed entities;
  dismiss it when you are done.
- **Service sensors are enum sensors** with the Traefik status as state
  (`enabled`, `warning`, `error`, `disabled`, `missing`) on the new "Traefik
  services (`<host>`)" device. Their entity IDs are kept. *Action:* update
  templates that used the removed attributes (see "Removed").
- **The reload button and the reload service are removed**
  (`button.traefik_reload` and the `traefik_proxy.reload_routers` action).
  Traefik has no reload API, so they never reloaded anything. *Action:*
  replace them with the new **Refresh now** button (`button.press`), which
  re-reads Traefik and the certificates at once.
- **Authentication type selection.** Setup, re-authentication and reconfigure
  offer "No authentication", "Basic auth (username and password)" and "Bearer
  token". Existing entries are migrated automatically: an entry with a token
  becomes "Bearer token", one without a token "No authentication", and
  credentials embedded in the URL (`user:password@host`) move into the basic
  auth fields. If an entry had both URL credentials and a token, the token is
  kept, the URL credentials are dropped and a warning is logged (such entries
  did not work before). A URL with credentials is no longer accepted in the
  forms. *Action:* none for most entries; check entries that had both.
- **Entries are identified by `host:port`.** The same Traefik instance cannot
  be added twice; two instances on the same host with different ports can.
  Entries are named after their host instead of "Traefik Proxy"; a name you
  chose yourself is kept, also when you reconfigure to a new host. *Action:*
  none.
- **Devices are restructured.** A main device "Traefik (`<host>`)" with the
  sub-devices "Traefik routers", "Traefik services" and "Traefik certificates
  (`<host>`)" replaces the per-category devices ("HTTP Routers", "HTTP
  Services", "Overview", "Diagnostics", …). Old devices are removed once no
  entity uses them; names or areas set on the old devices are not carried
  over, entity customisations are. *Action:* re-assign device areas.
- **Problem aggregates are renamed and enabled.** "Any router/service/middleware
  failing" become "Router problems", "Service problems" and "Middleware
  problems", enabled by default (also on upgrade, unless you had disabled
  them). Their entity IDs are kept. The attributes `problems` (sorted, at most
  50 names) and `problem_count` replace `failing_*_names` and
  `failing_*_count`. *Action:* update templates that read the old attributes.
- **Count sensors are reduced to their status counts.** "Routers", "Services"
  and "Middlewares" are diagnostic entities with the attributes `enabled`,
  `warning`, `error` and `disabled` only. *Action:* update dashboards that
  used the removed attributes (see "Removed").
- **Certificate entities are renamed** to "`<host>` expiry" (timestamp) and
  "`<host>` expiring" (problem) on the device "Traefik certificates
  (`<host>`)". Existing entity IDs are kept.

### Added

- Router and service sensors appear without a reload when Traefik adds an
  item. An item that vanishes stays in state `missing` (attribute
  `missing_since`) for a grace period, also across restarts and reloads, and
  comes back under the same entity ID, name and area if it returns in time.
- Option "Grace period for missing entities" (1–168 h, default 24 h) for
  routers, services, entrypoints and certificate hosts.
- Option "Create router and service entities" (default on). Off removes the
  router and service entities and their devices after the automatic reload and
  keeps the aggregate, diagnostic and certificate entities.
- **Refresh now** button (diagnostic) per entry: re-reads the Traefik data
  and the certificates of that entry at once.
- "Certificate problems" binary sensor on the main device, enabled by default:
  on while any certificate is expired, expiring within the warning threshold,
  missing from Traefik, or failed to be read twice in a row. Attributes
  `problems`, `problem_count` and `reasons`.
- Diagnostic sensors "Traefik version" (attribute `codename`), "Start time" and
  "Healthy routers" (percentage of enabled among non-disabled routers; disabled
  by default).
- The main device links to the Traefik dashboard and shows the Traefik version,
  which follows Traefik upgrades without a reload.
- On Traefik 3.7 and later, certificate data comes from Traefik's
  `/api/certificates`; no TLS connection is opened (`source: api`).
- Certificate attributes `source` (`api` or `probe`), `verified` (in probe mode:
  the presented chain validates against Home Assistant's trust store) and
  `reason` on "`<host>` expiring" (`expired`, `probe_failed`, `not_found`,
  `expiring`), translated in English and German.
- Calling `homeassistant.update_entity` on a certificate entity starts a
  certificate refresh.
- Diagnostics download per entry with the entry settings, polling status,
  parsed Traefik state, certificate state per host and missing items.
- Repair notice when credentials are sent to Traefik over plain HTTP.
- Specific form errors: redirect, credentials in the address, credentials that
  cannot be sent, a required credential missing, and a detailed hint for 404
  (API not enabled) and rejected logins.
- German translation of all forms, entities, devices, states, errors and repair
  notices; state-dependent icons for router and service sensors and the
  problem sensors.
- New landscape logo and a dark-theme logo with a white wordmark; the icon is
  trimmed and centred.
- Marketplace category "Monitoring".

### Changed

- One `GET /api/rawdata` per polling cycle replaces several list requests. If
  Traefik answers 404 there, the paginated list endpoints are used and
  `/api/rawdata` is retried once per hour. The version is re-read at most once
  per hour and after a failed cycle; entrypoints only when Traefik restarted or
  was upgraded. Only GET requests are sent to Traefik.
- An item Traefik reports as `disabled` with errors counts as `error`.
  Traefik-internal (`@internal`) items no longer count as problems. "Service
  problems" also turns on for an enabled service with a server that is down.
- Entities follow their item's current state on every cycle and write a new
  state only when something changed.
- Entrypoint sensors are diagnostic and disabled by default on new installs;
  their only attribute is `protocol`.
- Service sensor attributes are `type`, `provider`, `servers_up`,
  `servers_total`, `used_by` and `errors`.
- A host that Traefik has no certificate for is a `not_found` problem at once
  and is not probed (a probe would read Traefik's default certificate and look
  healthy). A pending ACME order therefore shows a problem for up to 6 h, or
  until you press **Refresh now** after the certificate was issued.
- Before Traefik 3.7, a probed certificate that does not cover the host (for
  example Traefik's default certificate) is also reported as `not_found`.
- A wildcard SAN covers exactly one label: `a.b.example.com` behind a
  `*.example.com` certificate reports `san_mismatch: true`.
- Probes (Traefik before 3.7) connect to the Traefik host of the integration
  URL with the router host as SNI name, on the TLS entrypoint port of the
  host's routers, so routers on ports other than 443 work. The Traefik host is
  resolved once per cycle; router host names are never resolved through DNS.
  No worker threads are used.
- Certificate hosts are collected from every host of multi-host rules
  (``Host(`a`, `b`)`` and `||` rules) and the TLS domains. `HostRegexp`,
  `HostSNI`, `HostHeader`, wildcard, template and negated names are skipped;
  internationalised names are checked in their IDNA form. At most 200 hosts
  are checked per cycle; a warning states how many were skipped.
- A failed probe no longer makes certificate entities unavailable:
  "`<host>` expiring" turns on with `probe_failed` after two consecutive
  failures, and "`<host>` expiry" keeps its last value.
- `days_until_expiry` is computed live; expiry, threshold crossings and the
  daily countdown update at the moment they happen instead of at the next
  6-hourly certificate check.
- `subject` and `issuer` hold common names. `last_error` values are `timeout`,
  `ssl`, `dns`, `refused`, `oserror`, `parse`, `empty`, `unknown` and
  `not_found`.
- The first certificate cycle runs in the background after setup; certificate
  entities and "Certificate problems" are unavailable until it has finished.
  A failed certificate cycle makes them unavailable, is logged once as ERROR
  and is retried after 5 minutes instead of 6 hours.
- A certificate host that disappears keeps its entities (unavailable) for the
  grace period instead of being deleted at once.
- Saving the options reloads the integration only when a value changed; a
  changed warning threshold or TLS verification starts a new certificate
  cycle. Polling interval (15–300 s), warning threshold (1–90 d) and grace
  period are number boxes with units.
- A redirect from the Traefik API shows a "redirect" error; redirects are never
  followed.
- An unusable stored URL stops the setup with a "correct the URL via
  Reconfigure" message instead of retrying forever. Stored credentials that
  cannot be sent open the re-authentication dialog.
- Error messages in the log and the UI are translated.

### Removed

- YAML configuration and the YAML import.
- The reload button and the `traefik_proxy.reload_routers` action.
- Router binary sensors (replaced by router sensors).
- Count sensor attributes `filtered_count`, `success_count`, `warning_count`,
  `error_count`, `disabled_count`, `status_breakdown`, `success_pct`,
  `http_count`, `tcp_count` and `udp_count`.
- Service sensor attributes `name`, `status`, `server_count`, `service_name`
  and `servers` (the backend URL list).
- Entrypoint sensor attributes `name`, `address`, `transport` and
  `entrypoint_name`.
- The `unreachable` value of `last_error`.
- `icon.svg` inside the integration folder (it was never served).

### Fixed

- Service sensors show the real Traefik service status instead of a value
  that does not exist in the API.
- Options changes are no longer applied twice after a reload.
- No more "does not generate unique IDs" errors on certificate cycles,
  threshold changes or options changes.
- Existing certificate entities are no longer marked missing because the first
  certificate check after a restart failed.
- Turning off router and service entities keeps a device that another
  integration's entity still uses.
- A stale device-disabled state of an enabled 0.3.0 device is no longer turned
  into a permanent user disable on upgrade.
- A URL with embedded credentials and a token no longer logs a traceback on
  every retry.

### Security

- Diagnostics redact user name, password, token, credentials in the URL and the
  values of header and query matchers in router rules, also in router errors
  that repeat the rule. A router error that may quote such a value elsewhere
  (for example the regexp error of an invalid `HeaderRegexp`) is redacted
  whole.
- Redirects are never followed, so credentials never reach a redirect target.
- Credentials are never logged; error chains of an invalid URL contain neither
  the URL nor credentials.
- Backend server URLs are no longer exposed as entity attributes.
- Credentials with a control character, or a user name with a colon, are
  rejected before they are sent.

## [0.3.0] - 2026-07-06

### Changed

- Renamed to "Traefik Proxy": the domain changes from `traefik` to
  `traefik_proxy` and the folder to `custom_components/traefik_proxy`. Home
  Assistant treats it as a new integration; entities get `traefik_proxy`
  entity IDs. Re-add the integration after the update.

## [0.2.1] - 2026-07-06

### Fixed

- Certificate entities no longer stay unavailable for up to 6 hours after a
  Home Assistant restart.

## [0.2.0] - 2026-07-06

### Added

- Status breakdown attributes on the router, service and middleware count
  sensors (`success_count`, `warning_count`, `error_count`, `disabled_count`,
  `status_breakdown`, `success_pct`) to rebuild the Traefik dashboard charts.
- "Any service failing" and "Any middleware failing" binary sensors (disabled
  by default).

## [0.1.6] - 2026-07-06

### Fixed

- Routers, services and middlewares with a provider suffix such as `@file` or
  `@docker` are no longer hidden; only Traefik-internal `@internal` items are.
  Version 0.1.5 was never tagged; this fix ships in 0.1.6.

## [0.1.4] - 2026-07-06

### Fixed

- The router, service and middleware count sensors update on every polling
  cycle instead of keeping the value from startup.

### Changed

- Refreshed brand images.

## [0.1.3] - 2026-07-06

### Fixed

- The setup and reconfigure forms open again; 0.1.1 made the URL field
  unserialisable.

## [0.1.2] - 2026-07-06

No user-visible changes (fixes for Home Assistant's manifest validation and
developer tooling).

## [0.1.1] - 2026-07-06

### Fixed

- A malformed URL shows "invalid URL" in the setup form instead of an unknown
  error.

### Changed

- The bearer token is optional, for a Traefik API without authentication.

## [0.1.0] - 2026-07-06

### Added

- First release: UI setup (and YAML), one binary sensor per Traefik HTTP
  router, service and entrypoint sensors, router, service and middleware count
  sensors and an "Any router failing" binary sensor.
- Options for the polling interval and the certificate warning threshold,
  re-authentication and reconfigure.
- TLS certificate expiry per router host (timestamp sensor and expiring binary
  sensor), checked every 6 hours.
- A reload button and service.

[1.0.0]: https://github.com/akentner/homeassistant-traefik-proxy-integration/compare/v0.3.0...v1.0.0
[0.3.0]: https://github.com/akentner/homeassistant-traefik-proxy-integration/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/akentner/homeassistant-traefik-proxy-integration/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/akentner/homeassistant-traefik-proxy-integration/compare/v0.1.6...v0.2.0
[0.1.6]: https://github.com/akentner/homeassistant-traefik-proxy-integration/compare/v0.1.4...v0.1.6
[0.1.4]: https://github.com/akentner/homeassistant-traefik-proxy-integration/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/akentner/homeassistant-traefik-proxy-integration/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/akentner/homeassistant-traefik-proxy-integration/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/akentner/homeassistant-traefik-proxy-integration/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/akentner/homeassistant-traefik-proxy-integration/releases/tag/v0.1.0
