# Traefik Proxy for Home Assistant

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=akentner&repository=homeassistant-traefik-proxy-integration&category=integration)

A custom Home Assistant integration that reads the API of a
[Traefik](https://traefik.io) reverse proxy and shows its state as entities:
which HTTP routers and services are healthy, which have problems, and which
TLS certificates expire soon. It only reads; it never changes Traefik.

## Features

- One sensor per Traefik HTTP router and per HTTP service with the Traefik
  status (`enabled`, `warning`, `error`, `disabled`) or `missing` when the item
  vanished from Traefik.
- Problem binary sensors for routers, services, middlewares and certificates,
  enabled by default, with the names of the affected items as attributes.
- Certificate expiry per TLS host: a timestamp sensor and an "expiring" problem
  sensor with a configurable warning threshold. On Traefik 3.7 and later the
  data comes from Traefik's certificate list; on older versions the
  integration reads the certificate Traefik presents for each host.
- Diagnostic sensors: router, service and middleware counts, Traefik version,
  start time and the share of healthy routers.
- A "Refresh now" button that re-reads Traefik and the certificates at once.
- Setup, re-authentication and reconfiguration through the UI, with no
  authentication, basic auth or a bearer token, matching how your Traefik API
  is protected.
- Diagnostics download with credentials and sensitive rule values redacted.
- English and German translations.

## Prerequisites

- **Home Assistant 2026.11.0 or later.**
- **Traefik v2.11 or later, or v3.x**, with the API enabled. Traefik v1 is not
  supported.
- The Home Assistant host must reach the Traefik API over HTTP or HTTPS.

### Enable and protect the Traefik API

Traefik's API has no credentials of its own. Enable it in the static
configuration and route it to the `api@internal` service through a router that
is protected by a middleware.

Static configuration (one of):

```yaml
# traefik.yml
api: {}
```

```text
--api=true
```

Dynamic configuration (file provider) with a basicAuth middleware:

```yaml
http:
  routers:
    traefik-api:
      rule: Host(`traefik.example.com`) && (PathPrefix(`/api`) || PathPrefix(`/dashboard`))
      entryPoints:
        - websecure
      service: api@internal
      middlewares:
        - traefik-api-auth
      tls: {}
  middlewares:
    traefik-api-auth:
      basicAuth:
        users:
          # Generate with: htpasswd -nB homeassistant
          - "homeassistant:$2y$05$replace-with-your-own-hash"
```

With Docker labels, write every `$` of the hash as `$$`.

- **Basic auth** (username and password) is the usual setup and works with the
  basicAuth middleware above.
- **Bearer token** works only if a forwardAuth middleware or a Traefik plugin
  in front of `api@internal` validates the `Authorization: Bearer <token>`
  header. Traefik itself does not check bearer tokens.
- **No authentication** fits an API that is only reachable from a trusted
  network (for example `api.insecure=true` on the `traefik` entrypoint, port
  8080).
- **Self-signed certificate on the Traefik API**: turn off "Verify TLS
  certificate" when you add the integration or later in the options.

Prefer HTTPS. With plain HTTP the credentials travel unencrypted; the
integration then raises a repair notice until you switch to HTTPS or remove the
authentication.

## Installation

### HACS

1. Click the badge at the top of this page, or open HACS and search for
   "Traefik Proxy". If HACS does not list it, add
   `https://github.com/akentner/homeassistant-traefik-proxy-integration` as a
   custom repository of type "Integration".
2. Download the integration and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and choose
   **Traefik Proxy**.

### Manual

1. Download the latest release from the
   [releases page](https://github.com/akentner/homeassistant-traefik-proxy-integration/releases).
2. Copy the folder `custom_components/traefik_proxy` into the
   `custom_components` folder of your Home Assistant configuration directory
   (the folder that contains `configuration.yaml`), so that the result is
   `<config>/custom_components/traefik_proxy/manifest.json`.
3. Restart Home Assistant and add the integration as in step 3 above.

Setup is UI-only; there is no YAML configuration.

## Removal

1. Go to **Settings → Devices & services → Traefik Proxy**, open the menu
   (⋮) of each entry and choose **Delete**. This removes the entry's devices,
   entities, repair notices and stored data.
2. Remove the integration in HACS (**HACS → Traefik Proxy → ⋮ → Remove**), or
   delete `<config>/custom_components/traefik_proxy` after a manual install.
3. Restart Home Assistant.

## Configuration

Added through **Settings → Devices & services → Add integration → Traefik
Proxy**. One entry per Traefik instance; an instance is identified by host and
port, so two Traefik instances on the same host with different ports can both
be added.

| Field | Label | Default | Notes |
|---|---|---|---|
| `url` | Traefik API URL | — (required) | Scheme (`http` or `https`), host, optional port and path prefix, for example `https://traefik.example.com`. The address of the dashboard without `/dashboard/`. No user name or password in the URL. |
| `verify_ssl` | Verify TLS certificate | on | Turn off only for a self-signed certificate on the Traefik API. |
| `auth_type` | Authentication | No authentication | "No authentication", "Basic auth (username and password)" or "Bearer token". Only the fields of the chosen type are shown. |
| `username` | Username | — | Basic auth only. Must not contain a colon. |
| `password` | Password | — | Basic auth only. |
| `token` | Bearer token | — | Bearer token only; sent as `Authorization: Bearer <token>`. |

The integration checks the connection before it creates the entry. The entry
is named after the Traefik host.

- **Re-authentication**: when Traefik rejects the stored credentials, Home
  Assistant asks for new ones (authentication type and credentials).
- **Reconfigure**: the entry menu offers **Reconfigure** to change the URL, TLS
  verification and authentication. A password or token left empty keeps the
  stored one while scheme, host, port and authentication type stay the same.
  A name you gave the entry yourself is kept.

Credentials are stored in the config entry and are never written to the log.

## Options

**Settings → Devices & services → Traefik Proxy → Configure**. Saving changed
values reloads the integration automatically.

| Option | Label | Default | Range | Notes |
|---|---|---|---|---|
| `scan_interval` | Polling interval | 15 s | 15–300 s | Seconds between two polls of the Traefik API. |
| `verify_ssl` | Verify TLS certificate | value from setup (on) | on / off | Same switch as in the setup form. |
| `tls_warn_days` | Certificate warning threshold | 14 d | 1–90 d | A certificate that expires within this many days counts as expiring. |
| `per_item_entities` | Create router and service entities | on | on / off | Off keeps the aggregate, diagnostic and certificate entities and removes the router and service entities and their devices after the reload. Useful for very large installations. |
| `missing_grace_hours` | Grace period for missing entities | 24 h | 1–168 h | How long a router, service or certificate that vanished from Traefik is kept (as `missing` or unavailable) before its entity is removed. Survives restarts. |

To change the URL or the credentials, use **Reconfigure** instead.

## Entities

Each entry creates a main device **Traefik (`<host>`)** and three sub-devices
linked to it: **Traefik routers (`<host>`)**, **Traefik services (`<host>`)** and
**Traefik certificates (`<host>`)**. `<host>` is the host of the Traefik API URL.
The main device links to the Traefik dashboard and shows the Traefik version.

| Platform | Translation key | Name | Device | States | Attributes | Enabled by default |
|---|---|---|---|---|---|---|
| sensor (enum) | `router` | router name, e.g. `nextcloud@docker` | Routers | `enabled`, `warning`, `error`, `disabled`, `missing` | `rule`, `service`, `provider`, `entry_points`, `middlewares`, `tls`, `errors`; only `missing_since` while missing | yes |
| sensor (enum) | `service` | service name, e.g. `nextcloud@docker` | Services | `enabled`, `warning`, `error`, `disabled`, `missing` | `type`, `provider`, `servers_up`, `servers_total`, `used_by`, `errors`; only `missing_since` while missing | yes |
| sensor (diagnostic) | `entrypoint` | entrypoint name, e.g. `websecure` | main | listening address, e.g. `:443`, or `missing` | `protocol`; only `missing_since` while missing | no |
| sensor (diagnostic) | `routers_count` | Routers | main | number of routers | `enabled`, `warning`, `error`, `disabled` | yes |
| sensor (diagnostic) | `services_count` | Services | main | number of services | `enabled`, `warning`, `error`, `disabled` | yes |
| sensor (diagnostic) | `middlewares_count` | Middlewares | main | number of middlewares | `enabled`, `warning`, `error`, `disabled` | yes |
| sensor (diagnostic) | `version` | Traefik version | main | Traefik version, e.g. `3.7.19` | `codename` | yes |
| sensor (diagnostic, timestamp) | `start_time` | Start time | main | time Traefik started | — | yes |
| sensor (diagnostic, %) | `healthy_ratio` | Healthy routers | main | enabled ÷ (enabled + warning + error) routers in %, 100 without such routers | — | no |
| sensor (timestamp) | `certificate_expiry` | `<host> expiry` | Certificates | certificate end of validity (`notAfter`), unknown without a certificate | `days_until_expiry`, `subject`, `issuer`, `san`, `san_mismatch`, `verified`, `source`, `host`, `port`, `fetched_at`, `last_error` | yes |
| binary_sensor (problem) | `routers_problem` | Router problems | main | on while any router is not `enabled` | `problems` (up to 50 names), `problem_count` | yes |
| binary_sensor (problem) | `services_problem` | Service problems | main | on while any service is not `enabled` or has a server that is down | `problems` (up to 50 names), `problem_count` | yes |
| binary_sensor (problem) | `middlewares_problem` | Middleware problems | main | on while any middleware is not `enabled` | `problems` (up to 50 names), `problem_count` | yes |
| binary_sensor (problem) | `certificates_problem` | Certificate problems | main | on while any certificate host has a problem | `problems` (up to 50 hosts), `problem_count`, `reasons` (host → reason) | yes |
| binary_sensor (problem) | `certificate_expiring` | `<host> expiring` | Certificates | on with a `reason`: `expired`, `probe_failed`, `not_found` or `expiring` | `reason`, `days_until_expiry`, `threshold_days`, `not_after`, `last_error`, `verified`, `source`, `san_mismatch`, `host`, `fetched_at` | yes |
| button (diagnostic) | `refresh` | Refresh now | main | time of the last press | — | yes |

Notes:

- **Item status.** `enabled`, `warning`, `error` and `disabled` are Traefik's
  own status values. An item Traefik reports as `disabled` with errors shows
  `error`; an unknown status shows `warning`. Traefik-internal items (names
  ending in `@internal`) are not shown.
- **Certificate hosts** come from the `Host()` names in the rules and the TLS
  domains of TLS routers. `<host>` in the certificate entity names is that
  host. Wildcard, regex, `HostSNI` and template names are not checked.
- **`reason` of `<host> expiring`.** `expired`: the certificate has expired.
  `probe_failed`: reading the certificate failed twice in a row. `not_found`:
  Traefik has no certificate for the host, or the certificate it presents does
  not cover the host. `expiring`: the certificate expires within the warning
  threshold.
- **`source`** is `api` (Traefik 3.7 and later, certificate list) or `probe`
  (older versions, TLS handshake). **`verified`** is only set in probe mode:
  true when the presented chain validates against Home Assistant's trust
  store.
- **Missing items.** A router, service or entrypoint that disappears from
  Traefik keeps its entity in state `missing` (attribute `missing_since`) for
  the grace period, then the entity is removed. Certificate entities of a host
  that disappeared are unavailable for the grace period. An item that comes
  back within the grace period keeps its entity ID, name and area.
- **Per-item option.** With "Create router and service entities" off, there
  are no router and service sensors and no Routers and Services devices; all
  other entities stay.
- **Entity IDs.** New installations derive entity IDs from the device name and
  the entity name, for example `sensor.traefik_routers_traefik_example_com_nextcloud_docker`
  for router `nextcloud@docker` on `https://traefik.example.com`. Installations
  upgraded from 0.x keep some older IDs; look up the actual ID under
  **Settings → Entities**.

## Data updates

- **Main cycle**: every 15 s by default (Polling interval option, 15–300 s).
  One cycle reads routers, services and middlewares with a single
  `GET /api/rawdata`. If Traefik answers 404 there, the integration reads the
  paginated list endpoints (`/api/http/routers`, `/api/http/services`,
  `/api/http/middlewares`) instead and retries `/api/rawdata` once per hour.
- **Version and entrypoints**: read at setup. The version is re-read at most
  once per hour and after a failed cycle; the entrypoints are re-read when the
  version or the start time changes (Traefik was restarted or upgraded).
- **Certificate cycle**: every 6 hours, independent of the main cycle. The
  first cycle runs in the background after setup; until it finishes, the
  certificate entities and "Certificate problems" are unavailable. After a
  failed cycle the next one runs after 5 minutes. On Traefik 3.7 and later the
  cycle reads `/api/certificates`; on older versions it opens one TLS handshake
  per host (at most 4 at a time, 5 s timeout each) to the Traefik host of the
  URL, with the router host as SNI name. `days_until_expiry`, expiry and
  threshold crossings update at the moment they happen, without a new cycle.
- **Refresh now**: pressing the button runs the main cycle and the certificate
  cycle of its entry at once (Home Assistant debounces repeated presses).
- **`homeassistant.update_entity`**: on a certificate entity it starts a
  certificate cycle; on any other entity of the integration it starts a main
  cycle.
- Entities only write a new state when their value or attributes changed.

## Example automations

Replace the entity IDs with yours (see **Settings → Entities**).

Notify when a router goes to `error`:

```yaml
automation:
  - alias: "Traefik router in error"
    triggers:
      - trigger: state
        entity_id: sensor.traefik_routers_traefik_example_com_nextcloud_docker
        to: "error"
    actions:
      - action: notify.notify
        data:
          title: "Traefik"
          message: >-
            Router {{ trigger.to_state.name }} is in error:
            {{ state_attr(trigger.entity_id, 'errors') | join(', ') }}
```

Notify when any router has a problem:

```yaml
automation:
  - alias: "Traefik router problems"
    triggers:
      - trigger: state
        entity_id: binary_sensor.traefik_traefik_example_com_router_problems
        to: "on"
        for: "00:02:00"
    actions:
      - action: notify.notify
        data:
          title: "Traefik"
          message: >-
            Routers with problems:
            {{ state_attr('binary_sensor.traefik_traefik_example_com_router_problems', 'problems') | join(', ') }}
```

Notify when a certificate is expiring:

```yaml
automation:
  - alias: "Traefik certificate expiring"
    triggers:
      - trigger: state
        entity_id: binary_sensor.traefik_certificates_traefik_example_com_www_example_com_expiring
        to: "on"
    actions:
      - action: notify.notify
        data:
          title: "Traefik certificate"
          message: >-
            {{ state_attr(trigger.entity_id, 'host') }}:
            {{ state_attr(trigger.entity_id, 'reason') }},
            {{ state_attr(trigger.entity_id, 'days_until_expiry') }} days left
```

For all hosts at once, trigger on
`binary_sensor.traefik_traefik_example_com_certificate_problems` and read its
`reasons` attribute.

## Troubleshooting

### Errors in the setup, re-authentication and reconfigure forms

| Error | Meaning and fix |
|---|---|
| `invalid_auth` | Traefik answered 401 or 403. Check the basicAuth or forwardAuth middleware in front of `api@internal` and the authentication type you chose. |
| `redirect` | Traefik answered with a redirect, which the integration never follows (credentials must not reach another address). Enter the address it redirects to, usually the HTTPS address. |
| `url_has_credentials` | The URL contains a user name or password. Remove them and use the authentication fields. |
| `api_disabled` | Traefik answered 404: the API is not enabled or not routed at this address. Enable the `api` section and route it to `api@internal`, or correct the URL (including any path prefix). |
| `cannot_connect` | Traefik is unreachable: check address, port, network and that Traefik runs. For a self-signed certificate turn off TLS verification. |
| `invalid_url` | Use `http` or `https`, a host name and an optional port. |
| `invalid_credential_format` | A user name with a colon, or a credential with a control character (line break, tab), cannot be sent. |
| `unknown` | Unexpected error; details are in the Home Assistant log. |

### Diagnostics

**Settings → Devices & services → Traefik Proxy → ⋮ → Download diagnostics**
downloads the entry settings, the polling status, the parsed Traefik state, the
certificate state per host and the items marked missing. User name, password,
token and any credentials in the URL are redacted, and the values of `Header`,
`HeaderRegexp`, `Query` and similar matchers in router rules are replaced by
`**REDACTED**`. Review the file before you attach it to an issue.

### Debug logging

On the integration page choose **Enable debug logging**, reproduce the problem,
then **Disable debug logging** to download the log. Alternatively, in
`configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.traefik_proxy: debug
```

Credentials are never logged.

### Repair notices

- **Traefik credentials are sent unencrypted**: the entry uses plain HTTP with
  credentials. Switch the URL to HTTPS through **Reconfigure** or remove the
  authentication.
- **Traefik entities were replaced**: shown once after an upgrade from 0.x. See
  [CHANGELOG.md](CHANGELOG.md) for what changed; dismiss it after updating your
  automations and dashboards.

## Known limitations

- Only HTTP routers, services and middlewares; TCP and UDP are not covered.
- At most 200 certificate hosts per entry are checked (the first 200 in sorted
  order); a warning in the log states how many were skipped.
- A wildcard certificate covers exactly one label: `a.b.example.com` is not
  covered by a `*.example.com` certificate and reports `not_found` (in probe
  mode also `san_mismatch: true`).
- On Traefik before 3.7 certificates are read with a TLS handshake to the
  Traefik host of the URL, using the router host as SNI name. The result is the
  certificate Traefik itself serves, not what a CDN or another proxy in front
  of it serves.
- A host Traefik has no certificate for is a `not_found` problem at once. A
  pending ACME order therefore shows a problem for up to 6 hours, or until you
  press **Refresh now** after the certificate was issued.
- Certificate entities and "Certificate problems" are unavailable until the
  first certificate cycle after setup or restart has finished, and while the
  last certificate cycle failed.
- Problem attributes list at most 50 names; `problem_count` has the full
  number.
- Redirects from the Traefik API are not followed.
- Traefik instances are not discovered automatically; add each one by URL.

## FAQ

**Can the integration edit Traefik routes or configuration files?**
No. It only reads the Traefik API. Changing dynamic configuration files from
Home Assistant would race with Traefik's providers; use your configuration
files or the Traefik dashboard.

**Can it request or renew certificates (ACME / Let's Encrypt)?**
No. Traefik owns the certificate lifecycle; the integration only shows expiry
and problems.

**Does it support Traefik v1?**
No. Traefik v1 is end of life; only v2.11+ and v3.x are supported.

**Are TCP or UDP routers and services supported?**
No, only HTTP. TCP and UDP use a different API surface.

**Why is there no entity per middleware?**
Middlewares have no runtime state beyond their status. The "Middlewares" count
sensor and "Middleware problems" binary sensor cover them.

**Is there a service action, for example to reload Traefik?**
No. The Traefik API is read-only and has no reload endpoint; the integration
registers no actions. Use the **Refresh now** button to re-read Traefik at once.

**Can it read `acme.json` instead of probing?**
No. That would tie the integration to Traefik's internal file layout and need
file access. Traefik 3.7 and later provide the certificate list through the
API; older versions are probed through Traefik.

**Does it work with Traefik Enterprise or a cloud-managed Traefik?**
Not supported. The integration targets the open-source Traefik Proxy API.

**Can certificates be probed through DNS, directly at the router host names?**
No. Probing through the Traefik host with SNI is the only reliable path behind
CDNs and split DNS; a DNS mode would check the wrong server.

**Can the integration draw the router → middleware → service graph?**
Not yet. It reads `/api/rawdata`, but has no graph view.

## Trademark

Traefik is a trademark of Traefik Labs. This project is not affiliated with or
endorsed by Traefik Labs. The integration uses the name only to say which
software it connects to.

The icon and logo shipped in `custom_components/traefik_proxy/brand/` are
exported from the logo components of the Traefik Proxy dashboard source code
(`traefik/traefik`, MIT licence); the logo is the horizontal "traefik proxy"
lockup as used by that dashboard. The MIT licence covers the copyright of the
artwork, not the trademark. Traefik Labs' trademark guidelines have not been
reviewed for this use, and no permission from Traefik Labs is claimed. If
Traefik Labs objects to the use of the logo, please open an issue so that it
can be replaced. Source, licence text and export commands are in
[docs/BRAND.md](docs/BRAND.md).

## License

See [LICENSE](LICENSE).
