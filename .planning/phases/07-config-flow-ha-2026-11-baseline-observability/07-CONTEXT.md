# Phase 7: Config flow, HA 2026.11 baseline, observability - Context

**Gathered:** 2026-11-15
**Status:** Ready for planning
**Source:** PRD Express Path (ROADMAP Phase 7, REQUIREMENTS FLOW-01..08 + DIAG-04,
audit items, decision log `~/.cache/traefik-proxy-integration/decisions.md` —
user interview I1 + I7 override everything else —, Phase 4/5/6 review
carry-overs, research `MARKETPLACE-BEST-PRACTICES.md` §4.1/§4.2/§4.5/§4.6/§5)

<domain>
## Phase Boundary

Users can set up, re-authenticate and reconfigure the integration with the
authentication Traefik deployments actually use (none / basic / bearer).
Options changes reload the entry without any update listener (HA 2026.12-safe),
and the options form exposes every runtime knob, including the per-item toggle
and the missing-entity grace period. Errors are translated and actionable.
Support data is available as a redacted diagnostics download. Everything is in
English and German. The minimum Home Assistant version becomes **2026.11.0**,
and the code uses the 2026.11 APIs instead of the workarounds that 2026.3
compatibility required.

**In scope:** `config_flow.py` (rewritten flows), `__init__.py` (migration
1.2 → 1.3, listener removal, unload helper, repairs), `coordinator.py` /
`cert_coordinator.py` (translated exceptions, auth mapping, private-attribute
removal, dead code), `api.py` (redirect handling), `entity.py` (device
linking via 2026.11 API), `entity_manager.py` (grace period from options),
`const.py`, new `diagnostics.py`, `translations/en.json` + `translations/de.json`,
removal of `strings.json`, `hacs.json`, `pyproject.toml` / `uv.lock`,
`.github/workflows/validate.yml` (minimum-version test job only), the local
minimum-HA venv, and the migration of every affected test.

**Out of scope (Phase 8):** manifest `categories` / version 1.0.0, brand
re-export, README / CHANGELOG, pre-commit, coverage path + `fail_under`, CI
`schedule` / `workflow_dispatch` / action pinning / release workflow, the
planning-reference sweep in shipped code (M22), Phase 6 IN-03 (DNS once per
cycle) and IN-04 (socket-test races), Phase 5 IN-01/IN-03/IN-06/IN-07, the
visual check in a throwaway HA (M35).

</domain>

<decisions>
## Implementation Decisions

### HA 2026.11 baseline (I1, FLOW-08)
- **D-01:** Minimum HA is **2026.11.0**: `hacs.json` `"homeassistant": "2026.11.0"`;
  `pyproject.toml` raises the `pytest-homeassistant-custom-component` floor to
  the first release that pins HA ≥ 2026.11.0 (research R-1) and `uv.lock` is
  re-locked to a 2026.11.x HA. The 2026.3 compatibility shims are removed: the
  `try: import probatio … except ImportError: import voluptuous` fallback goes
  (probatio/voluptuous alias exists since 2026.9; keep whichever import the
  research confirms works without `type: ignore`), and code comments that
  justify a choice by "2026.3" go.
- **D-02:** Local minimum-version check: a venv pinned to HA **2026.11.0**
  replaces `~/.cache/traefik-proxy-integration/ha2603-venv` (new path
  `~/.cache/traefik-proxy-integration/ha2611-venv`, created by the executor
  with `uv venv` + the pinned phcc version; never committed). Every plan's
  verify runs the suite in the dev env (latest 2026.11.x) **and** in this venv
  once the bump plan has landed; plans before the bump keep the 2026.3 venv run.
- **D-03:** CI gets one extra job `test-min-ha` that installs the phcc
  version pinned to HA 2026.11.0 and runs pytest (Phase 8 owns schedule,
  dispatch, action pinning and the release workflow; ROADMAP Phase 8 SC3 is
  re-worded from 2026.3.x to "the 2026.11.x minimum job added in Phase 7").
- **D-04:** Sub-devices link to the main device through the 2026.11 device API
  (`ChildDeviceInfo` / the dataclass `DeviceInfo` successor of `via_device`,
  research R-2) instead of the `async_update_device(via_device_id=…)` registry
  workaround (W33). Device identifiers, names and the per-item device removal
  stay unchanged; `test_devices.py` keeps asserting `via_device_id == main.id`.
  No dict-style `DeviceInfo({...})` construction or `info["…"]` access remains
  in code or tests.
- **D-05:** Every repair issue passes `config_entry_id=entry.entry_id`
  (`entities_migrated` from the 1.2 migration and the new FLOW-06 issue).
  `async_remove_entry` drops its manual `ir.async_delete_issue` for the
  migration issue when research R-3 confirms HA deletes entry-bound issues on
  entry removal; it keeps deleting the missing-since Store. `is_persistent=True`
  stays on the migration issue (M34).
- **D-06:** `async_unload_entry` uses
  `hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)`.
  Setup/unload return types follow research R-4: switch to `-> None` (raising
  `ConfigEntry*` exceptions instead of returning `False`) only if HA 2026.11.0
  accepts `None` from custom integrations without a warning; `async_migrate_entry`
  keeps returning `bool` unless R-4 shows the same for migration.
- **D-07:** The WR-02 fix stops reading the private
  `DataUpdateCoordinator._shutdown_requested`: `CertCoordinator` sets its own
  `_stopping` flag at the top of its existing `async_shutdown` override and
  `_async_schedule_day_boundary` checks that flag. The existing WR-02 tests
  stay green unchanged. Grep for `self\._[a-z_]+` attributes defined by HA base
  classes (`_shutdown_requested`, `_listeners`, `_unsub_refresh`, …) returns
  none in `custom_components/`.
- **D-08:** Shared abort reasons are translated centrally since HA 2026.10:
  reauth and reconfigure use the helpers' default reasons
  (`reauth_successful`, `reconfigure_successful`) and the local copies of those
  two keys are removed from en/de, provided research R-5 confirms hassfest and
  the frontend resolve them without a local key. `already_configured` and
  `unique_id_mismatch`-style local reasons stay local.
- **D-09:** No other 2026.11 API is adopted unless research shows a concrete
  benefit for this integration; `UNDEFINED`, `ATTR_*` constants and
  `DeviceEntry.config_entries` are not used today (grep proves it in the plan).

### Auth selector and entry data (FLOW-01, U-03, U-11, S-03)
- **D-10:** Entry data shape 1.3: `url`, `verify_ssl`, `auth_type`
  (`none` | `basic` | `bearer`, the `AuthMode` values), plus `username` +
  `password` (basic) or `token` (bearer), using HA's `CONF_USERNAME`,
  `CONF_PASSWORD`, `CONF_TOKEN` constants. Keys of an unused mode are absent
  (not empty strings). `CONF_API_KEY` is only read by the migration.
  `auth_from_entry_data()` stays the single mapping point to `Auth`.
- **D-11:** User step fields: URL (`TextSelector` URL), verify_ssl
  (`BooleanSelector`), auth type (`SelectSelector`, translated options via
  `translation_key`), username (`TextSelector`), password and token
  (`TextSelector` PASSWORD). Every field has a `data_description` in en + de.
  Whether the credential fields are shown conditionally on the auth type in
  one form (HA 2026.10+ visible-fields feature) or collected in a second step
  (`credentials` step after the auth type is chosen) follows research R-6;
  default if the conditional-field API is not usable from a custom
  integration's schema in 2026.11.0: two steps.
- **D-12:** Missing credentials for the chosen mode produce field errors
  (`username`/`password`/`token` → `required`); a credential the client
  rejects (`ValueError` from `Auth`, e.g. control characters or `:` in the
  username) produces `invalid_auth` on the field.
- **D-13:** Reauth (`reauth_confirm`) offers the same auth selector +
  credentials for the stored URL (the URL is not editable there) and finishes
  with `async_update_reload_and_abort(entry, data_updates=…)`. Reconfigure
  offers URL, verify_ssl, auth selector + credentials. Secrets are never
  pre-filled; in reconfigure an empty password/token **with an unchanged auth
  type** keeps the stored secret, a changed auth type requires the new
  secret(s), and choosing `none` removes username/password/token from the
  entry data (S-03).

### Entry migration 1.2 → 1.3 (FLOW-01, FLOW-03, A-22, IN-08)
- **D-14:** `MINOR_VERSION` 2 → 3 (W44). `async_migrate_entry` runs the
  existing `< 2` block and then a new `< 3` block, so a 1.1 entry reaches 1.3
  in one setup. The `< 3` block:
  - `api_key` non-empty → `auth_type=bearer`, `token=<api_key>`; empty/absent →
    `auth_type=none`; `api_key` is removed.
  - URL userinfo (IN-08): userinfo without a token → `auth_type=basic` with the
    percent-decoded username/password, URL rewritten without userinfo;
    userinfo **plus** a token → the token wins (bearer), the userinfo is
    dropped from the URL, and one WARNING is logged that names the entry but no
    credential (such an entry never worked: aiohttp refused the request). A
    401 afterwards starts reauth, where the user can pick basic.
  - unique_id → `host:port` (host lowercased, IPv6 in brackets, port from the
    URL or 80/443 by scheme), via `async_update_entry(unique_id=…)`; skipped
    with a WARNING if another entry of the domain already owns that unique_id.
  - title → host only if the title still equals `DEFAULT_NAME`
    ("Traefik Proxy"); a user-renamed title is kept.
  - Entity and device unique_ids are entry_id-based and unchanged.
- **D-15:** A stored URL that still fails construction at runtime
  (`TraefikProxyInvalidUrlError`) raises `ConfigEntryError` with translation
  key `invalid_url` (setup stops, no endless retry); a stored credential the
  new `Auth` rejects (`ValueError` in `build_api_client`) raises
  `ConfigEntryAuthFailed` with translation key `invalid_credentials`, which
  starts reauth (Phase 4 IN-04, IN-08).

### Options flow (FLOW-02, A-17, S-01, U-12, I7, W36)
- **D-16:** `entry.add_update_listener` and `_async_options_updated` are
  deleted; `TraefikProxyOptionsFlow` subclasses `OptionsFlowWithReload` (reload
  only when options changed). `CertCoordinator.async_set_threshold` and any
  other code path that only the listener used is removed (A-18 rule).
- **D-17:** Options form fields, all with en + de label and
  `data_description`:
  - `scan_interval`: `NumberSelector` min 15, max 300, step 1, unit `s`, box.
  - `verify_ssl`: `BooleanSelector` (default: effective value; reconfigure
    keeps mirroring it into options as today).
  - `tls_warn_days`: `NumberSelector` min 1, max 90, unit `d`, box.
  - `per_item_entities`: `BooleanSelector`, default `True` (W36, Phase 5 IN-04).
  - `missing_grace_hours` (new, I7): `NumberSelector` min 1, max 168
    (7 days), step 1, unit `h`, box, default 24. Constant
    `CONF_MISSING_GRACE_HOURS` / `DEFAULT_MISSING_GRACE_HOURS = 24` /
    `MIN_…= 1` / `MAX_…= 168` replace `MISSING_GRACE_PERIOD`.
  The `scan_interval_out_of_range` error key and the manual `vol.Range`
  handling go (the selectors validate the range); values are stored as `int`.
- **D-18:** The grace period is read from options at setup by the entity
  manager and applies to every kind it manages (routers, services,
  certificates). After a change (reload) existing missing-since times are kept
  and the new period applies to them: an item whose new deadline has already
  passed is removed at the first check after setup (at most
  `MISSING_CHECK_INTERVAL` later). `MISSING_CHECK_INTERVAL` stays 5 min.
- **D-19:** Turning per-item entities off or on takes effect through the
  reload (purge path and sub-device handling from Phase 5 unchanged). Tests
  cover option change → reload → purge.

### Reauth / reconfigure / unique_id (FLOW-03, A-22, S-02)
- **D-20:** User step: `async_set_unique_id(host:port)` +
  `_abort_if_unique_id_configured()`; title = host.
- **D-21:** Reconfigure: run the URL shape check first (IN-10), compute
  `host:port`; another entry owning it → abort `already_configured` before any
  probe; otherwise validate and finish with
  `async_update_reload_and_abort(entry, unique_id=<new>, title=<new host if the
  current title equals the old host or DEFAULT_NAME>, data=<new data>,
  options={**entry.options, verify_ssl: …})`.

### Flow errors (FLOW-04, A-15, IN-01, IN-09, IN-10, W28)
- **D-22:** Error keys: `invalid_url`, `url_has_credentials` (new, W28: a
  newly entered URL with userinfo — text tells the user to remove it and use
  the authentication fields), `invalid_auth`, `cannot_connect`, `api_disabled`
  (404), `redirect` (new, IN-01), `unknown` (new code path: any unexpected
  exception is caught, logged with `_LOGGER.exception`, shown as `unknown`).
  Abort: `already_configured`. Every path is tested; `config_flow.py` has
  100 % line coverage (measured with `--cov=custom_components.traefik_proxy`
  on the command line; the `pyproject` default path is fixed in Phase 8).
- **D-23:** IN-01: the client sends every request with `allow_redirects=False`;
  a 3xx answer raises a new `TraefikProxyRedirectError` (subclass of the
  connection-error family, message without the Location URL's userinfo). The
  flow maps it to `redirect`; the coordinator maps it to `UpdateFailed` with
  translation key `redirect`. This also enforces the host-pinning prohibition
  from Phase 4 against a redirecting server.
- **D-24:** IN-09: `InvalidUrl` is raised without arguments (no URL in
  `exc.args`). IN-10: `_check_url_shape` wraps `urlparse` / `.port` access in
  `try/except ValueError: raise InvalidUrl from None`; reconfigure runs it
  before computing the host. The YAML-only `allow_userinfo` parameter is
  removed together with the YAML step (reauth no longer needs it: the URL is
  migrated free of userinfo, D-14).

### Translated exceptions (FLOW-05, research §4.2)
- **D-25:** Every `ConfigEntryAuthFailed`, `ConfigEntryNotReady`,
  `ConfigEntryError` and `UpdateFailed` raised in `coordinator.py`,
  `cert_coordinator.py` and `__init__.py` uses
  `translation_domain=DOMAIN, translation_key=…` (placeholders only for
  non-secret values such as the endpoint name or HTTP status); no
  `str(err)` messages. Keys live in `exceptions` in en + de. The unused
  `exceptions.cert_unavailable` is removed (A-18, Phase 5 IN-03 is the same
  finding).

### Repair for http:// + credentials (FLOW-06, research §4.6)
- **D-26:** Issue id `insecure_credentials_<entry_id>`, translation key
  `insecure_credentials`, severity WARNING, `is_fixable=False`,
  `config_entry_id=entry.entry_id`, placeholder `entry_title`; the text points
  to Reconfigure (switch to https). Created in `async_setup_entry` when the
  URL scheme is `http` and `auth_type` is not `none`; deleted in setup when
  the condition no longer holds and on unload (`entry.async_on_unload`). Uses
  the 2026.11 issue-registry APIs (I1 supersedes M4's "2026.3 APIs only").

### Diagnostics (DIAG-04, U-16)
- **D-27:** New `diagnostics.py` with `async_get_config_entry_diagnostics`
  returning `entry` (data, options, version/minor_version, unique_id, title),
  the main snapshot (parsed models only, serialised via `dataclasses.asdict`
  with datetimes as ISO strings — never raw API payloads), the cert states
  (source, per-host state incl. `last_error`), coordinator status
  (`last_update_success`, update intervals, rawdata/paginated mode) and the
  entity manager's missing-since map. Redacted through `async_redact_data`
  with `{CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME, CONF_API_KEY, "users",
  "authorization"}`; URL userinfo (if any) is stripped. A test serialises the
  dump to JSON and asserts that none of the fixture's username, password or
  token values occur anywhere in it.

### Translations and dead code (FLOW-07, A-18, U-13, U-14, M7, Phase 5 IN-02, Phase 6 IN-01/IN-02)
- **D-28:** `strings.json` is deleted; `translations/en.json` is the single
  source. `translations/de.json` gets every key in `en.json` (config, options,
  selector, exceptions, issues, plus the existing device/entity keys). A test
  asserts recursive key parity en ↔ de (both directions) and that every
  placeholder `{…}` in an en string also appears in its de string.
  `test_translations.py`'s strings.json mirror check is removed.
- **D-29:** Removed: `async_step_yaml`, `STEP_YAML_DATA_SCHEMA`, its strings,
  the reauth "leave empty to clear auth" wording (U-14), and every A-18 item
  still present (grep each: `if TYPE_CHECKING: pass`, `_router_name` alias,
  `_host_port`, `_reset` test seam, `cert_cache_availability` alias,
  `const.VERSION`), plus `CertCoordinator.get_threshold()` and its test
  (Phase 6 IN-01). `cert_coordinator.py` reads `CONF_TLS_WARN_DAYS` instead of
  the literal `"tls_warn_days"` (Phase 6 IN-02). Items already gone are
  recorded as such, not re-implemented.
- **D-30:** Flow texts describe Traefik's real auth model: the API has no own
  token; it is protected by a middleware in front of `api@internal`
  (basicAuth documented pattern, or a bearer-checking forwardAuth). German
  text uses the informal "du" imperative, as the existing de.json and HA's
  German translations do ("nutze", "passe … an").

### Roadmap / requirements housekeeping
- **D-31:** ROADMAP Phase 7 is renamed "Config flow, HA 2026.11 baseline,
  observability" (directory `07-config-flow-ha-2026-11-baseline-observability`);
  its goal/SC mention 2026.11.0 instead of 2026.3.0, list FLOW-08, and carry
  the Phase 5/6 carry-overs and I1/I7. REQUIREMENTS gets FLOW-08 (baseline) and
  FLOW-02/FLOW-06 wording aligned with I7/I1. Phase 8 SC3 refers to the
  2026.11.x minimum job.

### Claude's Discretion
- Plan split, wave order and task granularity (coarse granularity configured).
- Internal helper names (e.g. `_url_host_port()`), module placement of the
  migration helpers, test file layout.
- Exact English/German wording within D-22/D-25/D-26/D-30 constraints.
- Whether diagnostics include the Traefik version/codename (non-secret: yes
  preferred).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Binding decisions
- `~/.cache/traefik-proxy-integration/decisions.md` — I1, I7 (override), M5, M7,
  M15, M21, M24, M25, M34, W33, W36, W44, Phase 6 carry-over (WR-02, rename)
- `.planning/ROADMAP.md` § Phase 7 — goal, SC, audit items, carry-overs
- `.planning/REQUIREMENTS.md` — FLOW-01..08, DIAG-04

### Research
- `.planning/research/MARKETPLACE-BEST-PRACTICES.md` §4.1 (flows, listener
  deprecation), §4.2 (setup/unload, translated `UpdateFailed`), §4.5
  (translations), §4.6 (diagnostics, repairs), §5 (2026.x deprecations)
- `.planning/research/AUDIT-ARCH-PERF-UX.md` rows A-15, A-17, A-18, A-22,
  U-03, U-11..U-14, U-16, S-01..S-03
- `07-RESEARCH.md` (this phase) — answers R-1..R-6 below

### Review carry-overs
- `.planning/phases/04-data-layer-correct-lean/04-REVIEW.md` (IN-08, IN-09, IN-10)
  and `04-REVIEW-DISPOSITION.md` (IN-01 redirects, IN-04 rejected token)
- `.planning/phases/04-data-layer-correct-lean/deferred-items.md` (invalid_url text, W28)
- `.planning/phases/05-entity-model-lifecycle/05-REVIEW.md` (IN-02 de strings, IN-04 per-item UI)
- `.planning/phases/06-certificates/06-REVIEW.md` (IN-01 get_threshold, IN-02 literal key)
- `.planning/STATE.md` Blockers (WR-02 `_shutdown_requested`)

### Code
- `custom_components/traefik_proxy/config_flow.py`, `__init__.py`,
  `coordinator.py` (`auth_from_entry_data`, `build_api_client`), `api.py`
  (`Auth`, `AuthMode`, error classes), `entity.py` (`async_setup_devices`),
  `entity_manager.py`, `cert_coordinator.py`, `const.py`, `translations/*.json`
- Tests: `tests/test_config_flow.py`, `test_reconfigure.py`, `test_migration.py`,
  `test_init.py`, `test_devices.py`, `test_translations.py`, `test_verify_ssl.py`,
  `test_entity_manager.py`, `test_cert_coordinator.py`

</canonical_refs>

<specifics>
## Specific Ideas

### Research questions (R-n) for 07-RESEARCH.md
- **R-1:** Which `pytest-homeassistant-custom-component` version pins HA
  2026.11.0 exactly, and which is the latest for 2026.11.x? Does `uv lock`
  resolve with Python 3.14.2 floor?
- **R-2:** Exact 2026.11 API for linking a sub-device to a parent
  (`ChildDeviceInfo` fields, `DeviceInfo` dataclass, registry
  `async_get_or_create(via_device=…)` status) and what a custom integration
  should use to register sub-devices before platforms set up.
- **R-3:** `ir.async_create_issue(config_entry_id=…)` semantics in 2026.11:
  deleted on entry removal only, or also on unload? Behaviour with
  `is_persistent=True`. Is `ir.async_refresh_issues` useful here?
- **R-4:** Does HA 2026.11.0 accept `None` from a custom integration's
  `async_setup_entry` / `async_unload_entry` / `async_migrate_entry` without a
  warning? `async_unload_platforms_or_raise` signature and behaviour.
- **R-5:** Central abort reasons since 2026.10: does hassfest (custom
  integration mode) or the frontend need local `reauth_successful` /
  `reconfigure_successful` keys?
- **R-6:** Conditional form fields (2026.10 blog "form-fields-visible"): API
  shape, whether `voluptuous_serialize` / the custom-integration schema path
  supports it in 2026.11.0, and how tests drive it — versus a two-step flow.
- Also confirm: `DataUpdateCoordinator._shutdown_requested` still exists in
  2026.11 (only for the record; D-07 removes the dependency anyway);
  `OptionsFlowWithReload` import path and behaviour with no listener;
  `NumberSelector` unit/mode config; `SelectSelector` translation_key for
  options.

### Test environment
- Dev env (`uv run pytest -q`) runs latest 2026.11.x after the bump.
- Minimum venv `~/.cache/traefik-proxy-integration/ha2611-venv` (D-02).
- No real HA instance; hassfest may run in a local throwaway Docker container
  (removed afterwards) to validate translations.

</specifics>

<deferred>
## Deferred Ideas

- Phase 6 IN-03 (resolve the probe connect host once per cycle) and IN-04
  (socket-test races) → Phase 8.
- Phase 5 IN-01 (double lowercasing of cert hosts), IN-06 (mixed object_ids /
  repair text), IN-07 → Phase 8 or later.
- Repair fix flow (one-click to reconfigure) for `insecure_credentials` — not
  needed; the text points to Reconfigure.
- Probatio-specific features (`Secret` markers) — not needed.
- `UpdateFailed(retry_after=…)` backoff hints — optional, not planned.

</deferred>

---

*Phase: 07-config-flow-ha-2026-11-baseline-observability*
*Context gathered: 2026-11-15 via PRD Express Path*
