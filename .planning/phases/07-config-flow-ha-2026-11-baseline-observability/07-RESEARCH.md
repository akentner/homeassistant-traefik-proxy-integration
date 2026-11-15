# Phase 7: Config flow, HA 2026.11 baseline, observability - Research

**Researched:** 2026-11-15
**Domain:** Home Assistant 2026.11 custom-integration APIs (config/options flows, device + issue registries, entry lifecycle, diagnostics, test tooling)
**Confidence:** HIGH. Every R-n answer was checked against the HA 2026.11.0 wheel source and run in scratch probes on HA 2026.11.0 / 2026.11.1.

## Summary

The phase design in CONTEXT.md works on HA 2026.11.0 with **four corrections**. The planner must handle them explicitly, because three of them contradict the literal wording of a locked decision:

1. **R-1 / D-01..D-03: `pytest-homeassistant-custom-component` (phcc) is discontinued and cannot run on HA 2026.11.** Its last release, 0.13.375 (2026-10-25), pins `homeassistant==2026.10.4`. Its README now says the package "is now broken". On top of that, phcc 0.13.375 forced onto HA 2026.11.0 fails at import with `RuntimeError: httpx was already imported; call alias_httpx() before any import httpx`. The official successor is **`pytest-homeassistant`**, built from `home-assistant/core/packages/pytest-homeassistant` and versioned like HA itself (`2026.11.0` pins `homeassistant==2026.11.0`, `2026.11.1` pins `homeassistant==2026.11.1`). Migrating the current suite takes a mechanical rename (`pytest_homeassistant_custom_component` → `pytest_homeassistant` in 12 test files, minus the `pytest_plugins` line). After that, **all 851 tests pass on HA 2026.11.0**, and `uv lock` resolves with `requires-python >=3.14.2` (it picks HA 2026.11.1).
2. **R-2 / D-04: `ChildDeviceInfo` is a different concept from a `via_device` link.** It creates a `ChildDeviceEntry` (a "lightweight logical part of one physical product"). A child entry has no `via_device_id`, `manufacturer`, `entry_type` or `sw_version`, and does not show up in `dr.async_entries_for_config_entry`. In addition, every entity attached to a child must return a `ChildDeviceInfo(parent_device_id=…)`. The 2026.11 replacement for the W33 workaround that keeps D-04's other constraints ("`test_devices.py` keeps asserting `via_device_id == main.id`") is the new **`via_device_id=main.id` keyword of `device_registry.async_get_or_create`**. In 2026.3 only the now-deprecated `via_device` tuple existed. A scratch prototype passes all 851 tests.
3. **D-13: `async_update_reload_and_abort(data_updates=…)` merges and cannot remove keys** (`data = entry.data | data_updates`). It also raises `ValueError` if `data` is passed as well. A reauth that switches from basic to bearer would therefore keep `username`/`password`, which the `Auth` dataclass rejects (`"bearer auth does not use a username"`). Reauth must pass the full new data with `data=` (D-10: "keys of an unused mode are absent").
4. **R-6 / D-11: conditional fields are usable from a custom integration in 2026.11.0.** `homeassistant.data_entry_flow.Required/Optional(…, visible={"field": "auth_type", "value": "basic"})` is serialised to the frontend. `FlowManager._async_configure` strips hidden fields from the input before validation, so tests driving `hass.config_entries.flow.async_configure` get the same behaviour. **Use one form with `visible` conditions instead of a second `credentials` step.**

Everything else resolves cleanly:

- `async_setup_entry` / `async_unload_entry` / `async_migrate_entry` may return `None` on 2026.11.0, with no warning.
- `async_unload_platforms_or_raise` exists.
- Entry-bound issues (`config_entry_id=`) are deleted on entry **removal**, not on unload. Persistent and non-persistent issues behave the same here.
- The central abort reasons need no local keys.
- `OptionsFlowWithReload` reloads only when the options changed, and raises `ValueError` if an update listener exists.
- `import probatio as vol` is mypy-clean on 2026.11. `import voluptuous as vol` produces 5 mypy `arg-type` errors, because the real voluptuous 0.16 is still installed as a dependency of `annotatedyaml`/`hass-nabucasa`.

**Primary recommendation:** make the baseline bump the first plan (wave 1). It switches the test dependency to `pytest-homeassistant>=2026.11.0`, renames the test imports, re-locks, sets `hacs.json` to 2026.11.0, adds the `test-min-ha` CI job, creates the `ha2611-venv`, and drops the probatio and `BinarySensorDeviceClass` shims. Every later plan then builds on 2026.11 APIs and verifies in both environments.

## Architectural Responsibility Map

All capabilities live in one tier: a Home Assistant custom integration (Python, in-process). The table maps capabilities to HA subsystems instead of browser/API/DB tiers.

| Capability | Primary owner | Secondary | Rationale |
|------------|---------------|-----------|-----------|
| Auth selector, conditional fields, errors | `config_flow.py` (ConfigFlow) | HA FlowManager (strips hidden fields, validates schema) | Flow UI is declared server-side and rendered by the frontend from the serialised schema |
| Options + reload | `config_flow.py` (`OptionsFlowWithReload`) | HA `OptionsFlowManager.async_finish_flow` (schedules the reload) | Core reloads when options changed; there is no listener in the integration |
| Entry data 1.2→1.3, unique_id, title | `__init__.py` `async_migrate_entry` | `config_entries.async_update_entry` | Migration runs before setup on every load |
| Sub-device linking | `entity.py` `async_setup_devices` | Device registry | Devices exist before platforms forward |
| Insecure-credentials repair | `__init__.py` setup/unload | Issue registry (`config_entry_id` auto-cleanup on removal) | Re-evaluated each setup |
| Translated errors | coordinators + `__init__.py` | `translations/*.json` `exceptions` | `HomeAssistantError` kwargs |
| Redirect detection | `api.py` (`allow_redirects=False`, 3xx → `TraefikProxyRedirectError`) | flow + coordinator mapping | Transport concern stays in the client |
| Diagnostics | new `diagnostics.py` | `homeassistant.components.diagnostics.async_redact_data` | Platform discovered by the diagnostics integration |
| Minimum-version guarantee | `hacs.json`, `pyproject.toml`/`uv.lock`, CI `test-min-ha`, `ha2611-venv` | — | Build/test tooling |

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

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

### Deferred Ideas (OUT OF SCOPE)

- Phase 6 IN-03 (resolve the probe connect host once per cycle) and IN-04
  (socket-test races) → Phase 8.
- Phase 5 IN-01 (double lowercasing of cert hosts), IN-06 (mixed object_ids /
  repair text), IN-07 → Phase 8 or later.
- Repair fix flow (one-click to reconfigure) for `insecure_credentials` — not
  needed; the text points to Reconfigure.
- Probatio-specific features (`Secret` markers) — not needed.
- `UpdateFailed(retry_after=…)` backoff hints — optional, not planned.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FLOW-01 | Auth selector (none/basic/bearer), `PASSWORD` selectors, `data_description`, 1.2→1.3 migration, "none" clears credentials | R-6 (one form with `visible`, hidden fields stripped server-side); Pitfall 1 (reauth needs `data=`); `CONF_USERNAME/PASSWORD/TOKEN` verified in `homeassistant.const`; `async_update_entry(unique_id=…)` collision only logs an ERROR → D-14's pre-check is required |
| FLOW-02 | No listener; `OptionsFlowWithReload`; `NumberSelector`s; per-item toggle; grace hours | `OptionsFlowWithReload` source + probe (reload only on change; `ValueError` with a listener); `NumberSelector` returns `float` → coerce to `int` |
| FLOW-03 | Reauth/reconfigure via `async_update_reload_and_abort`; unique_id `host:port` follows reconfigure | Helper kwargs verified (`unique_id`, `title`, `data`, `data_updates`, `options`, `reason`, `reload_even_if_entry_is_unchanged`); `data` and `data_updates` are mutually exclusive |
| FLOW-04 | 404 → `api_disabled`; every error path tested; config_flow 100 % | Validation Architecture (coverage command); `InvalidData` for schema-level failures |
| FLOW-05 | Translated `ConfigEntryAuthFailed`/`NotReady`/`UpdateFailed` | `UpdateFailed(*args, retry_after=None, **kwargs)` passes kwargs to `HomeAssistantError`; first-refresh failure copies `translation_*` from the cause into `ConfigEntryNotReady` |
| FLOW-06 | `http://` + credentials repair with `config_entry_id`; deleted when fixed / on unload | R-3: auto-delete on removal only → unload must delete explicitly (D-26 already does); unknown entry id raises `HomeAssistantError` |
| FLOW-07 | `strings.json`/YAML step/dead code gone; en single source; de parity | hassfest custom mode validates `translations/en.json`; `data_description` keys must also be in `data`; `abort` keys are optional |
| FLOW-08 | Min HA 2026.11.0; sub-devices via 2026.11 API; repairs with `config_entry_id`; `async_unload_platforms_or_raise`; no private attribute | R-1 (pytest-homeassistant), R-2 (`via_device_id=` kwarg), R-3, R-4; `_shutdown_requested` still exists (D-07 removes the dependency) |
| DIAG-04 | `diagnostics.py` with `async_redact_data` | Import path verified; `pytest_homeassistant.components.diagnostics.get_diagnostics_for_config_entry` probe passed |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Python 3.14+, `aiohttp` via `async_get_clientsession(hass)` only; no own `ClientSession`. `requirements: []` in the manifest.
- No `quality_scale` key in the manifest. `iot_class: local_polling`, `integration_type: service`.
- API tokens are never logged; self-signed certificates are supported via a user option (`verify_ssl`).
- No external service dependencies or telemetry.
- Use `entry.runtime_data`, not `hass.data[DOMAIN]`; `asyncio.timeout`, not `async_timeout`; modern typing (`int | None`, PEP 695 aliases).
- `uv run --with …` over `pip install`; no global pip installs.
- Code, comments and commits in English; user-facing German text uses the informal "du" (D-30).
- Work goes through GSD workflows; the orchestrator commits. Researchers and executors do not push.
- Worktrees only under `~/Projekte/_worktrees/<repo>/<branch>`.
- Fish is the user's shell. Commands given to the user should be shell-neutral or Fish. The `uv pip install --python <venv>/bin/python …` form below works in every shell.

## Standard Stack

### Core (all bundled with HA, no manifest requirement)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| homeassistant | `2026.11.0` floor; dev lock resolves `2026.11.1` | Runtime | `hacs.json` minimum (D-01) [VERIFIED: PyPI JSON, `requires_python >=3.14.2` for 2026.11.0 and 2026.11.1] |
| probatio | 0.13.0 (HA-bundled) | Schemas (`import probatio as vol`) | HA 2026.11 types every flow API with `probatio.Schema`; `homeassistant/__init__.py` aliases `voluptuous` to probatio at runtime via `install_as_voluptuous()` [VERIFIED: wheel `homeassistant/__init__.py:1-30`] |
| `homeassistant.data_entry_flow.Required/Optional` | 2026.11.0 | Conditional fields (`visible=`) | Official 2026.11 API [VERIFIED: wheel `data_entry_flow.py:64-99`] |

### Dev / test
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest-homeassistant` [WARNING: the legitimacy seam flagged it as suspicious (too-new, no-repository) — verify before using] | `>=2026.11.0` (min venv: `==2026.11.0`) | `hass` fixture, `MockConfigEntry`, `aioclient_mock`, diagnostics/repairs helpers | Replaces phcc; README: "Use the package release that matches your Home Assistant version" [CITED: github.com/home-assistant/core/tree/2026.11.0/packages/pytest-homeassistant/README.md]. PyPI provenance attestation: publisher `{"kind": "GitHub", "repository": "home-assistant/core", "workflow": "builder.yml", "environment": "stable"}`, the same publisher as the `homeassistant` wheel [VERIFIED: pypi.org/integrity provenance API] |
| pytest-cov | ≥7.0.0 (lock: unchanged) | Coverage | Already in dev group |
| mypy / ruff | unchanged | Lint / types | Already in dev group |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `pytest-homeassistant` | phcc 0.13.375 + `override homeassistant==2026.11.0` (the trick the 2026.3 venv used) | **Does not work**: import-time `RuntimeError` (see Pitfall 2). Not an option |
| `via_device_id=` kwarg (sub-devices stay normal devices) | `async_get_or_create_child` / `ChildDeviceInfo` | Child devices drop `manufacturer`/`entry_type`/`sw_version`, are excluded from `async_entries_for_config_entry`, need `ChildDeviceInfo(parent_device_id=…)` on every attached entity, and break D-04's `via_device_id` assertion. Their semantic ("parts of one product assignable to their own area") does not fit "Routers/Services/Certificates" groupings |
| One form with `visible` | Two steps (`user` → `credentials`) | Two steps double the step translations and the test matrix and need flow state; `visible` is native 2026.11 and strips stale secrets server-side |

**Installation (dev env, executed by the bump plan):**
```bash
# pyproject.toml dev group: replace "pytest-homeassistant-custom-component>=0.13.345" by "pytest-homeassistant>=2026.11.0"
uv lock            # resolved to homeassistant 2026.11.1 / pytest-homeassistant 2026.11.1 in a scratch copy
uv sync
```

**Version verification (2026-11-15):**
- `pytest-homeassistant`: 2026.11.0 (2026-11-05), 2026.11.1 (2026-11-09). Each version pins `homeassistant==<same version>` [VERIFIED: PyPI JSON `requires_dist`].
- `homeassistant`: 2026.11.0 (2026-11-04), 2026.11.1 (2026-11-09) is the latest [VERIFIED: PyPI JSON].
- phcc: latest 0.13.375 (2026-10-25), `homeassistant==2026.10.4`. No 2026.11 release exists. Repo commits "Point users to new package (#261)" and "Turn off dependabot (#262)" on 2026-11-03 [VERIFIED: PyPI JSON + `gh api` commits].

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| pytest-homeassistant | PyPI | 10 days (2026.11.0 published 2026-11-05; the name had unrelated 0.1.x releases in 2020) | unknown (seam) | github.com/home-assistant/core (PyPI `project_urls` + trusted-publisher attestation `home-assistant/core` `builder.yml`) | [SUS] (seam: too-new, unknown-downloads, no-repository) | Flagged. The planner adds a `checkpoint:human-verify` before the install. Evidence for a quick confirmation: official core README at tag 2026.11.0, PyPI provenance attestation, phcc README pointing to it |
| pytest-homeassistant-custom-component | PyPI | — | — | MatthewFlamm/… | (removed from the project) | Removed: discontinued, incompatible with HA 2026.11 |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** `pytest-homeassistant`. The planner inserts `checkpoint:human-verify` before the first `uv lock` / venv install that pulls it.
**postinstall:** not applicable (Python wheel, `py3-none-any`).

## Answers to R-1..R-6 and the confirmation list

### R-1: Test package pinning HA 2026.11.0, lock, minimum venv, CI job

**Findings**
- No phcc release pins HA ≥ 2026.11. phcc's final release `0.13.375` has `requires_dist` containing `'homeassistant==2026.10.4'` [VERIFIED: PyPI JSON for 0.13.368…0.13.375]. The phcc README now opens with: "`pytest-homeassistant-custom-component`, this package, is now broken. Custom component developers should move to the centrally managed package." [VERIFIED: `gh api repos/MatthewFlamm/pytest-homeassistant-custom-component/readme`]
- Falsification attempt (phcc 0.13.375 with `--override homeassistant==2026.11.0`, current suite, scratch copy):
  ```
  File ".../pytest_homeassistant_custom_component/patch_json.py", line 13, in <module>
    from homeassistant.helpers import json as json_helper
  File ".../homeassistant/__init__.py", line 12, in <module>
    httpx2.alias_httpx()
  RuntimeError: httpx was already imported; call `alias_httpx()` before any `import httpx`.
  ```
  The same result occurs with `-p no:respx` [VERIFIED: scratch run].
- `pytest-homeassistant==2026.11.0` pins `homeassistant==2026.11.0` exactly; `2026.11.1` pins `2026.11.1` [VERIFIED: PyPI JSON `requires_dist`: `'homeassistant==2026.11.1', … 'pytest==9.0.3', 'pytest-asyncio==1.4.0', 'pytest-freezer==0.4.9', 'pytest-socket==0.8.1', 'respx==0.23.1', 'syrupy==6.1.1'`].
- Migration of this repo's tests (scratch copy):
  - `sed s/pytest_homeassistant_custom_component/pytest_homeassistant/` over the 12 files that import it (`common.MockConfigEntry`, `common.async_fire_time_changed`, `test_util.aiohttp.AiohttpClientMockResponse`);
  - delete `pytest_plugins = ["pytest_homeassistant_custom_component"]` in `tests/conftest.py`.

  Result: **851 passed** on HA 2026.11.0. The local autouse `enable_custom_integrations` override in `conftest.py` can be deleted (still 851 passed): "The `hass` fixture enables custom integrations by default" [CITED: core README].
- `uv lock` with `pytest-homeassistant>=2026.11.0` and `requires-python = ">=3.14.2"` resolves to `homeassistant 2026.11.1` / `pytest-homeassistant 2026.11.1`. It drops `pytest-picked`, `pytest-timeout`, `pytest-unordered`, `rich`, `tqdm` and others; the tests use none of them [VERIFIED: scratch `uv lock` + `uv sync --frozen` + suite run].
- The README asks for `addopts = "-p no:respx"` ("Let Home Assistant install its httpx alias before respx is imported") and `pythonpath = ["."]` [CITED: core README]. The suite also passed without `-p no:respx` in this environment. Follow the README anyway: the flag costs nothing and protects against plugin import-order changes.

**Recommendation (planner)**
- `pyproject.toml`:
  - dev group: `"pytest-homeassistant>=2026.11.0"` replaces the phcc line;
  - `[tool.pytest.ini_options] addopts` gains `-p no:respx` (keep the coverage flags; Phase 8 fixes the coverage path);
  - optional: add `pythonpath = ["."]` and drop `sys.path.insert` in `conftest.py`. Not required: the current `sys.path.insert` works.
- Tests: rename the imports, delete the `pytest_plugins` line and the local `enable_custom_integrations` fixture.
- Local minimum venv (D-02), shell-neutral:
  ```
  uv venv --python 3.14 ~/.cache/traefik-proxy-integration/ha2611-venv
  uv pip install --python ~/.cache/traefik-proxy-integration/ha2611-venv/bin/python "pytest-homeassistant==2026.11.0" "pytest-cov>=7.0.0"
  ~/.cache/traefik-proxy-integration/ha2611-venv/bin/python -m pytest -q -o addopts="-p no:respx" tests
  ```
  Precondition check: `~/.cache/traefik-proxy-integration/ha2611-venv/bin/python -I -c 'import homeassistant.const as c; assert c.__version__ == "2026.11.0"'`.
- CI job (D-03). Add it to `.github/workflows/validate.yml` with the same action versions the file already uses; Phase 8 pins them:
  ```yaml
    test-min-ha:
      name: Tests (minimum HA 2026.11.0)
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v6
        - uses: astral-sh/setup-uv@v5
        - name: Set up Python
          run: uv python install 3.14
        - name: Install the minimum Home Assistant test stack
          run: |
            uv venv --python 3.14 .venv-min-ha
            uv pip install --python .venv-min-ha/bin/python "pytest-homeassistant==2026.11.0" "pytest-cov>=7.0.0"
        - name: Pytest against HA 2026.11.0
          run: .venv-min-ha/bin/python -m pytest -q -o addopts="-p no:respx" tests
  ```
- Ordering: before the bump, the dev env is HA 2026.10.4 / phcc 0.13.375 (current `uv.lock`), and the 2026.3 venv still works for plans that run before it. Put the bump first so no plan has to write code that runs on both 2026.3 and 2026.11.

### R-2: 2026.11 sub-device linking API

**Findings** (HA 2026.11.0 `homeassistant/helpers/device_registry.py`)
- `DeviceInfo` is a `@dataclass(eq=False, repr=False, slots=True)` with `KW_ONLY` fields. Among them: `via_device_id: str | UndefinedType | None = UNDEFINED`; `via_device` is hidden from type checkers and deprecated [VERIFIED: `device_registry.py:282-314`].
- `_DEPRECATED_DEVICE_INFO_PARAMETERS` contains `"via_device": ("2027.8.0", "via_device_id")` [VERIFIED: `device_registry.py:136-144`].
- `DeviceRegistry.async_get_or_create(*, config_entry_id, …, translation_key, translation_placeholders, via_device_id: str | UndefinedType | None = UNDEFINED, **kwargs)`. Its docstring: "To create or update a child device, use async_get_or_create_child. If identifiers overlap with a child device, the method raises." [VERIFIED: `device_registry.py:2447-2475`]
- In HA 2026.3.0, `async_get_or_create` had only `via_device: tuple[str, str] | None | UndefinedType`; it had no `via_device_id` keyword [VERIFIED: ha2603-venv `device_registry.py` signature]. That is why the current code needed `async_update_device(via_device_id=…)` (W33).
- `ChildDeviceInfo` fields: `identifiers` (required), `name`, `parent_device_id` (required), `suggested_area`, `translation_key`, `translation_placeholders`. Docstring: "A child device is a lightweight logical part of a parent device. The parent is referenced by its device id, must already be registered by the same config entry, and must belong to the same config subentry." [VERIFIED: `device_registry.py:317-331`]
- `ChildDeviceEntry` (separate storage) has `parent_device_id` and no `via_device_id`/`manufacturer`/`entry_type`; accessing them from a custom integration logs a deprecation [VERIFIED: `device_registry.py:847-880`]. `async_entries_for_config_entry` returns only `DeviceEntry`; children need `async_child_entries_for_config_entry` [VERIFIED: `device_registry.py:5024-5051`].
- The entity platform registers a child only when `entity.device_info` is a `ChildDeviceInfo`; a `DeviceInfo` whose identifiers match a child raises `DeviceInfoError` [VERIFIED: `entity_platform.py:846-895`, `device_registry.py` "overlap with those of child device"].
- The contributor docs say: "Do not mix this up with `via_device_id`: that is about connectivity between separate products." and "A child device … has no identity of its own." [CITED: contributors.home-assistant.io/core/integrations/device-registry/]
- Probe: converting an existing normal device to a child via `async_get_or_create_child` keeps the id, after which `async_get_device_by_identifier` no longer finds it [VERIFIED: scratch probe `CHILD ChildDeviceEntry True …` / `normal lookup None`].
- Prototype of the recommended change (scratch copy of `entity.py`: `via_device_id=main.id` added to the sub-device `async_get_or_create`, `async_update_device` branch removed): **851 passed**, mypy strict clean apart from the pre-existing shim warning below [VERIFIED: scratch run].

**Recommendation:** register sub-devices with
`device_registry.async_get_or_create(config_entry_id=…, identifiers=…, translation_key=…, translation_placeholders=…, manufacturer="Traefik", entry_type=DeviceEntryType.SERVICE, via_device_id=main.id)` and delete the `if sub.via_device_id != main.id: async_update_device(...)` workaround. Entities keep `DeviceInfo(identifiers=…)` (keyword construction, already dataclass-compatible). Do **not** adopt `ChildDeviceInfo` (see Open Question 2; user confirmation needed because I1 names `ChildDeviceInfo`). Test lookups must use `async_get_device_by_identifier(identifier, config_entry_id)` or `async_entries_for_config_entry`: `async_get_device(identifiers=…)` now **raises `RuntimeError` when called from test code** (deprecated, `breaks_in_ha_version="2027.8.0"`) [VERIFIED: scratch probe traceback]. The current tests do not call it (grep: none).

### R-3: `ir.async_create_issue(config_entry_id=…)` semantics

**Findings** (HA 2026.11.0 `homeassistant/helpers/issue_registry.py`, `config_entries.py`)
- `async_create_issue(hass, domain, issue_id, *, breaks_in_ha_version=None, config_entry_id=None, data=None, is_fixable, is_persistent=False, issue_domain=None, learn_more_url=None, severity, translation_key, translation_placeholders=None)` [VERIFIED: `issue_registry.py:596-630`].
- An unknown entry raises `HomeAssistantError(f"Can't link issue to unknown config entry {config_entry_id}")` [VERIFIED: `issue_registry.py:284-290`]. A test that calls `async_migrate_entry` directly must therefore `entry.add_to_hass(hass)` first; the current tests do.
- **Deleted on entry removal:** `ConfigEntries.async_remove` → `_async_clean_up` → `ir.async_get(hass).async_clear_config_entry(entry_id)`, which deletes every issue with that `config_entry_id` regardless of `is_persistent` [VERIFIED: `config_entries.py:2391-2433`, `issue_registry.py:393-400`]. On registry load, bound issues whose entry no longer exists are also deleted [VERIFIED: `issue_registry.py:540-552`].
- **Not deleted on unload:** `async_unload` does not touch the issue registry. Probe: after `async_unload` the bound issue still exists; after `async_remove` both a persistent and a non-persistent bound issue are gone [VERIFIED: scratch probe `AFTER UNLOAD insecure: True`, `AFTER REMOVE None None`].
- Disabled entry: its issues are hidden from listings (`async_is_hidden`), not deleted [VERIFIED: `issue_registry.py:422-428`].
- `is_persistent=True`: the issue is restored with full data after a restart; a non-persistent issue loads as inactive until re-created [VERIFIED: `issue_registry.py:500-537`]. Re-creating an existing issue keeps `dismissed_version` (the user's ignore) and fires an update only if something changed [VERIFIED: `issue_registry.py:317-348`].
- `ir.async_refresh_issues(hass, domain, *, issue_id_pattern=None, issue_ids=None, config_entry_id=None)` is a context manager that deletes in-scope issues not re-created or kept during the block [VERIFIED: `issue_registry.py:700-730`].

**Recommendation**
- Migration issue: add `config_entry_id=entry.entry_id`, keep `is_persistent=True`, and drop `ir.async_delete_issue` from `async_remove_entry` (HA deletes it; keep the Store deletion). The existing removal test stays green, now proving HA's cleanup.
- `insecure_credentials`: plain `if cond: async_create_issue(…, config_entry_id=…) else: async_delete_issue(…)` in setup, plus `entry.async_on_unload(lambda: ir.async_delete_issue(hass, DOMAIN, issue_id))`. **Do not use `async_refresh_issues`**: with a single issue id, an if/else is clearer and equivalent. Note the side effect that D-26/SC4 accept: the unload delete resets a user's "ignore" on every reload.

### R-4: `None` returns and `async_unload_platforms_or_raise`

**Findings** (HA 2026.11.0 `config_entries.py`)
- `_async_process_entry_method_result(domain, method, result)`:
  - `None` → return;
  - `bool` → `report_usage(…, core_integration_behavior=ReportBehavior.ERROR, custom_integration_behavior=ReportBehavior.IGNORE, …)`, then `True` returns and `False` raises `ConfigEntryError(translation_domain="homeassistant", translation_key=f"{method}_failed")` [VERIFIED: `config_entries.py:356-387`].
  - It is applied to `async_setup_entry` (L1027), `async_unload_entry` (L1173) and `async_migrate_entry` (L1336) [VERIFIED].
  - So on 2026.11.0, `None` is silent for all three, and booleans from custom integrations are silent too.
- Migration: an exception or `False` → `MIGRATION_ERROR` state. HA itself rejects `entry.version > handler.VERSION` before calling the integration (logs and returns `False`) [VERIFIED: `config_entries.py:990-1013`, `1305-1316`]. The integration's own `entry.version > 1` downgrade branch is unreachable as long as `VERSION = 1`.
- `async def async_unload_platforms_or_raise(self, entry, platforms) -> None` raises `ConfigEntryError(translation_domain=HOMEASSISTANT_DOMAIN, translation_key="unload_platforms_failed")` when any platform fails [VERIFIED: `config_entries.py:3083-3090`].
- Blog: "Nothing breaks, and there is no deprecation. Returning a boolean remains supported." [CITED: contributors.home-assistant.io/blog/2026/10/23/config-entry-methods-return-none/]
- Probe: setup `-> None` plus unload via `async_unload_platforms_or_raise` → `LOADED` / `NOT_LOADED`, and no "should return None" / report log [VERIFIED: scratch probe `REPORTS []`].

**Recommendation:** switch all three to `-> None`; R-4 shows migrate behaves the same as setup and unload. In `async_migrate_entry`, replace `return False` in the downgrade branch with `raise ConfigEntryError(translation_domain=DOMAIN, translation_key="downgrade")`, or delete the unreachable branch. Tests that `assert await integration.async_migrate_entry(hass, entry)` (`test_migration.py:283, 290, 476, 494, 604, 620`) become `await …` plus state assertions.

### R-5: Central abort reasons

**Findings**
- `async_update_reload_and_abort`, when `reason` is UNDEFINED, uses `"reconfigure_successful"` for `SOURCE_RECONFIGURE` and `"reauth_successful"` otherwise, with `translation_domain = HOMEASSISTANT_DOMAIN` [VERIFIED: `config_entries.py:3753-3803`]. Probe result: `{'type': ABORT, 'reason': 'reauth_successful', 'translation_domain': 'homeassistant'}` [VERIFIED].
- The `homeassistant` integration ships `config.abort.reauth_successful` / `reconfigure_successful` in `translations/en.json` ("Re-authentication was successful", "Reconfiguration was successful") and in `de.json` ("Die erneute Authentifizierung war erfolgreich") [VERIFIED: wheel].
- Blog: "when an abort uses the central domain, the frontend resolves the reason from that domain and does not use a local key" [CITED: contributors.home-assistant.io/blog/2026/09/28/central-config-flow-abort-reasons/].
- hassfest 2026.11.0 (custom-integration mode) validates `translations/en.json` against a schema where `abort` is `probatio.Optional("abort"): {str: translation_value_validator}`. No key is required [VERIFIED: core `script/hassfest/translations.py@2026.11.0` L269, L737-751].
- `already_configured` comes from `AbortFlow("already_configured")` without a central domain and is not in the `homeassistant` abort list, so it stays local [VERIFIED: `config_entries.py:3210, 3219`; homeassistant `en.json` abort keys].
- `pytest-homeassistant` ships no translation-check fixture, so tests do not enforce flow-result translations [VERIFIED: grep of the package]. The repo's own `test_translations.py` is the guard.

**Recommendation:** remove the local `config.abort.reauth_successful` from en/de. No local `reconfigure_successful` exists today. Keep `already_configured`. Do not pass a custom `reason=`.

### R-6: Conditional fields vs two steps

**Findings**
- `homeassistant.data_entry_flow.Required` / `Optional` subclass `probatio.Required/Optional` and accept `visible: bool | FieldCondition | list[FieldCondition] | None`. Docstring: "Unless the ``visible`` condition matches the other fields, the field is not rendered, is treated as optional, and its value is omitted from the submitted data. A list of conditions is combined with AND." [VERIFIED: `data_entry_flow.py:64-99`]
- Condition schema (verbatim from `homeassistant/helpers/field_visibility.py:11-64`):
  - `ConditionOperator`: `EQ = "eq"`, `NOT_EQ = "not_eq"`, `IN = "in"`, `NOT_IN = "not_in"`, `EXISTS = "exists"`, `NOT_EXISTS = "not_exists"`;
  - `FieldCondition`: `field: str`, `operator: typing.NotRequired[ConditionOperator]`, `value: typing.NotRequired[ConditionValue | list[ConditionValue]]`;
  - `{field, value}` defaults to `eq`.
- Server side: `FlowManager._async_configure` calls `_strip_hidden_fields(data_schema, user_input)` before validation. Hidden fields are dropped from the input and from the validation schema; conditions see schema defaults [VERIFIED: `data_entry_flow.py:395-420`, `1032-1099`].
- Serialisation: `_prepare_result_json` → `probatio.to_field_list(schema, custom_serializer=cv.custom_serializer)` → `add_visible_conditions_to_serialized_schema` [VERIFIED: `helpers/data_entry_flow.py:35-61`]. Probe JSON: `{"name": "token", "required": false, "optional": true, "visible": {"field": "auth_type", "value": "bearer"}, "selector": {"text": {"type": "password", …}}}` and the select carries `"translation_key": "auth_type"` [VERIFIED].
- Probes [VERIFIED, scratch custom integration on HA 2026.11.0]:
  - `auth_type=none` plus a stale `token` → entry data `{'url': …, 'auth_type': 'none'}`;
  - `basic` plus a stale token → no token;
  - `bearer` with no token, plus a code-level check → `errors == {'token': 'required'}`.
- The blog says flows support `visible` "As of Home Assistant Core 2026.11" [CITED: contributors.home-assistant.io/blog/2026/10/21/form-fields-visible/]. That is 2026.11, not 2026.10 as CONTEXT says; it does not matter at a 2026.11.0 minimum.

**Recommendation: one form, `visible` conditions.**
- Mark the credentials with `data_entry_flow.Optional(…, visible={"field": CONF_AUTH_TYPE, "value": "basic"|"bearer"})`, not `Required`. The step code then enforces D-12 (`errors[field] = "required"`), and reconfigure can keep "empty = keep stored secret".
- Give `auth_type` a `default` (`none` in user; the stored value in reauth/reconfigure), so the condition resolves even when the client omits the field.
- Add `config.error.required` (en/de). It is not in D-22's list but follows from D-12.
- Tests: drive `hass.config_entries.flow.async_configure(...)` (the stripping runs there). Assert `getattr(marker, "visible")` on `result["data_schema"].schema` keys to check the declaration. Optionally assert the serialised JSON via `hass_client` POST `/api/config/config_entries/flow` after `async_setup_component(hass, "config", {})`.

### Confirmation list

| Item | Finding | Evidence |
|------|---------|----------|
| `DataUpdateCoordinator._shutdown_requested` | Still exists: set `False` in `__init__` (L101) and `True` in `async_shutdown` (L219). Its private attributes are `_async_unsub_refresh, _async_unsub_shutdown, _debounced_refresh, _last_listener_id, _listeners, _microsecond, _request_refresh_task, _retry_after, _shutdown_requested, _unsub_refresh, _unsub_shutdown, _update_interval, _update_interval_seconds`. **`_stopping` is free** for D-07 | [VERIFIED: 2026.11.0 `update_coordinator.py`] |
| `OptionsFlowWithReload` | `from homeassistant.config_entries import OptionsFlowWithReload`; `automatic_reload: bool = True`. A reload is scheduled only if `async_update_entry(options=…)` changed something. `raise ValueError("Config entry update listeners should not be used with OptionsFlowWithReload")` if `entry.update_listeners` is non-empty. Probe: changed options → setup ran twice; unchanged options → no reload; with a listener → `ValueError` | [VERIFIED: `config_entries.py:4170-4200`, `4285-4294`; probe] |
| `NumberSelector` | `NumberSelectorConfig` keys: `min, max, step, unit_of_measurement, mode, translation_key`. `NumberSelectorMode.BOX = "box"`. `__call__` returns **`float`** and does not enforce the step ("user input is not rounded") → store `int(user_input[...])` in the step | [VERIFIED: `selector.py` NumberSelector; probe config `{'min': 15.0, 'max': 300.0, 'step': 1.0, 'unit_of_measurement': 's', 'mode': 'box'}`] |
| `SelectSelector` translations | `SelectSelectorConfig(options=[...], translation_key="auth_type", mode=SelectSelectorMode.LIST)`; translations at `selector.<translation_key>.options.<value>` (hassfest schema `selector: {slug: {options: {slug: str}}}`) | [VERIFIED: `selector.py`; hassfest `translations.py:457-470`] |
| `async_update_reload_and_abort` kwargs | `(entry, *, unique_id, title, data, data_updates, options, reason, reload_even_if_entry_is_unchanged=True)`. **`data` + `data_updates` → `ValueError("Cannot set both data and data_updates")`**; `data_updates` = `entry.data \| data_updates` (merge only) | [VERIFIED: `config_entries.py:3753-3803`, `__async_update`] |
| `import voluptuous as vol` | Works at runtime (alias), but mypy strict reports 5 × `incompatible type "voluptuous.schema_builder.Schema"; expected "probatio.schema.Schema \| None"` (real voluptuous 0.16 is installed for `annotatedyaml`, `hass-nabucasa`). **`import probatio as vol` is mypy-clean** → keep probatio and drop the try/except | [VERIFIED: scratch mypy runs] |
| `BinarySensorDeviceClass` shim (`binary_sensor.py:16-19`) | Second 2026.3 shim. On 2026.11 mypy reports `Unused "type: ignore" comment` on the fallback import. `homeassistant.components.binary_sensor` re-exports it (`__all__`); `.const` defines it → use one plain `from homeassistant.components.binary_sensor import BinarySensorDeviceClass` | [VERIFIED: scratch mypy; wheel `binary_sensor/__init__.py:15,38`] |
| `async_redact_data` | `from homeassistant.components.diagnostics import async_redact_data` (in `__all__`); `REDACTED = "**REDACTED**"`; empty strings and `None` are not redacted | [VERIFIED: `diagnostics/__init__.py:38-43`, `util.py:20-56`, `const.py`] |
| Diagnostics test helper | `from pytest_homeassistant.components.diagnostics import get_diagnostics_for_config_entry` (`hass`, `hass_client`, `entry`). Probe returned the redacted dict | [VERIFIED: package source; probe] |
| `UpdateFailed` translations | `UpdateFailed(*args, retry_after=None, **kwargs)` → `HomeAssistantError(**kwargs)`; on first refresh `ConfigEntryNotReady` copies `translation_domain/key/placeholders` from the cause; `ConfigEntryAuthFailed` / `ConfigEntryError` raised in `_async_update_data` are re-raised as-is | [VERIFIED: `update_coordinator.py:48-59, 365-380, 530-570`] |
| `CONF_USERNAME/PASSWORD/TOKEN` | `homeassistant.const`: `CONF_PASSWORD: Final = "password"`, `CONF_TOKEN: Final = "token"`, `CONF_USERNAME: Final = "username"` (`CONF_API_KEY: Final = "api_key"` also exists) | [VERIFIED: `const.py:77,191,242,253`] |
| unique_id collision on update | `async_update_entry(unique_id=X)` with X owned by another entry only logs an ERROR ("… which is already in use …") and re-indexes → D-14 must check `async_entry_for_domain_unique_id` first | [VERIFIED: `config_entries.py` `_async_update_entry`] |

## Architecture Patterns

### Data flow (entry lifecycle after Phase 7)

```
User (UI) ──► ConfigFlow.user ──(visible: auth_type → creds)──► FlowManager strips hidden fields
     │                                   │
     │                         _check_url_shape → probe /api/version (allow_redirects=False)
     │                                   │  401/403→invalid_auth  404→api_disabled  3xx→redirect
     │                                   ▼  other→cannot_connect  unexpected→unknown
     │                         async_set_unique_id(host:port) → create_entry(title=host, data 1.3)
     ▼
HA start / reload ──► async_migrate_entry (1.1→1.2→1.3: api_key→bearer/none, userinfo→basic, unique_id, title)
                         │ raise ConfigEntryError on failure
                         ▼
                   async_setup_entry (-> None)
                     ├─ build_api_client: invalid URL → ConfigEntryError(invalid_url); Auth ValueError → ConfigEntryAuthFailed(invalid_credentials)
                     ├─ coordinator first refresh: translated UpdateFailed / ConfigEntryAuthFailed (→ reauth)
                     ├─ entity manager (grace hours from options)
                     ├─ async_setup_devices: main + sub-devices (via_device_id=main.id)
                     ├─ forward platforms
                     ├─ insecure_credentials issue (create | delete), async_on_unload(delete)
                     └─ NO update listener
Options flow (OptionsFlowWithReload) ──changed options──► HA schedules reload
Reauth / Reconfigure ──► async_update_reload_and_abort(entry, data=…/unique_id=…/title=…/options=…) ──► HA reload
Unload ──► async_unload_platforms_or_raise + on_unload callbacks (issue delete, timers)
Remove ──► async_remove_entry (Store) ; HA clears entry-bound issues, devices, entities
Diagnostics download ──► diagnostics.async_get_config_entry_diagnostics ──► async_redact_data
```

### Pattern 1: Auth form with conditional credentials
```python
# Source: HA 2026.11.0 data_entry_flow.py:64-99, field_visibility.py; verified by scratch probe
import probatio as vol
from homeassistant import data_entry_flow
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME
from homeassistant.helpers.selector import (
    SelectSelector, SelectSelectorConfig, SelectSelectorMode,
    TextSelector, TextSelectorConfig, TextSelectorType,
)

_SECRET = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

def _auth_fields(default_auth: str) -> dict[vol.Marker, object]:
    return {
        vol.Required(CONF_AUTH_TYPE, default=default_auth): SelectSelector(
            SelectSelectorConfig(options=[m.value for m in AuthMode], translation_key=CONF_AUTH_TYPE,
                                 mode=SelectSelectorMode.LIST)
        ),
        data_entry_flow.Optional(CONF_USERNAME, visible={"field": CONF_AUTH_TYPE, "value": AuthMode.basic.value}): TextSelector(),
        data_entry_flow.Optional(CONF_PASSWORD, visible={"field": CONF_AUTH_TYPE, "value": AuthMode.basic.value}): _SECRET,
        data_entry_flow.Optional(CONF_TOKEN, visible={"field": CONF_AUTH_TYPE, "value": AuthMode.bearer.value}): _SECRET,
    }
```
`CONF_AUTH_TYPE` is a new const (`"auth_type"`, D-10). `AuthMode` values verbatim from `api.py:42-47`: `none = "none"`, `basic = "basic"`, `bearer = "bearer"` [VERIFIED: Read this session]. Translations: `selector.auth_type.options.{none,basic,bearer}`.

### Pattern 2: Options flow with reload, int coercion
```python
# Source: config_entries.py:4285-4294 (OptionsFlowWithReload); selector.py NumberSelector returns float
from homeassistant.config_entries import OptionsFlowWithReload
from homeassistant.helpers.selector import NumberSelector, NumberSelectorConfig, NumberSelectorMode

class TraefikProxyOptionsFlow(OptionsFlowWithReload):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={
                **user_input,
                CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                CONF_TLS_WARN_DAYS: int(user_input[CONF_TLS_WARN_DAYS]),
                CONF_MISSING_GRACE_HOURS: int(user_input[CONF_MISSING_GRACE_HOURS]),
            })
        schema = vol.Schema({
            vol.Required(CONF_SCAN_INTERVAL, default=...): NumberSelector(NumberSelectorConfig(
                min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL, step=1,
                unit_of_measurement="s", mode=NumberSelectorMode.BOX)),
            ...
        })
        return self.async_show_form(step_id="init", data_schema=schema)
```
The test must `await hass.async_block_till_done()` after `async_configure`: the reload is *scheduled*. An out-of-range number now raises `homeassistant.data_entry_flow.InvalidData` from `async_configure` (schema validation) instead of returning an error form. Tests for `scan_interval_out_of_range` become `pytest.raises(InvalidData)`.

### Pattern 3: Reauth / reconfigure finish
```python
# Source: config_entries.py:3753-3803; data and data_updates are mutually exclusive, data_updates only merges
new_data = {CONF_URL: entry.data[CONF_URL], CONF_VERIFY_SSL: ..., CONF_AUTH_TYPE: auth_type, **credentials}
return self.async_update_reload_and_abort(entry, data=new_data)          # reauth (D-13, corrected)
return self.async_update_reload_and_abort(
    entry, unique_id=new_uid, title=new_title, data=new_data,
    options={**entry.options, CONF_VERIFY_SSL: verify_ssl},
)                                                                          # reconfigure (D-21)
```

### Pattern 4: Sub-device link (replaces W33)
```python
# Source: device_registry.py:2447-2512 (via_device_id kwarg; 2026.3 had only via_device)
device_registry.async_get_or_create(
    config_entry_id=entry.entry_id,
    identifiers={device_identifier(entry.entry_id, device)},
    translation_key=device.value,
    translation_placeholders=placeholders,
    manufacturer="Traefik",
    entry_type=DeviceEntryType.SERVICE,
    via_device_id=main.id,
)
```

### Pattern 5: Lifecycle returns, unload, repair
```python
# Source: config_entries.py:356-387, 3083-3090; issue_registry.py:596-630
async def async_setup_entry(hass: HomeAssistant, entry: TraefikProxyConfigEntry) -> None:
    ...
    issue_id = f"insecure_credentials_{entry.entry_id}"
    if urlsplit(entry.data[CONF_URL]).scheme == "http" and entry.data[CONF_AUTH_TYPE] != AuthMode.none:
        ir.async_create_issue(hass, DOMAIN, issue_id, is_fixable=False, severity=ir.IssueSeverity.WARNING,
                              translation_key="insecure_credentials", config_entry_id=entry.entry_id,
                              translation_placeholders={"entry_title": entry.title})
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
    entry.async_on_unload(lambda: ir.async_delete_issue(hass, DOMAIN, issue_id))

async def async_unload_entry(hass: HomeAssistant, entry: TraefikProxyConfigEntry) -> None:
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
```

### Pattern 6: Diagnostics
```python
# Source: homeassistant/components/diagnostics/__init__.py:38-43, util.py:20-56
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY, CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME

TO_REDACT = {CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME, CONF_API_KEY, "users", "authorization"}

async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: TraefikProxyConfigEntry) -> dict[str, Any]:
    return async_redact_data({...}, TO_REDACT)
```
Use `CONF_API_KEY` from the integration's own `const.py` or from `homeassistant.const`; both are `"api_key"`. Serialise datetimes to ISO strings before returning (`dataclasses.asdict` keeps `datetime`; the diagnostics view's JSON encoder handles `datetime`, but D-27 asks for explicit ISO strings).

### Anti-Patterns to Avoid
- **`async_update_reload_and_abort(entry, data_updates=…)` when credential keys may disappear:** stale keys survive. Use `data=`.
- **`ChildDeviceInfo` for the Routers/Services/Certificates sub-devices:** changes the device type, breaks `async_entries_for_config_entry`-based code and tests, and drops `manufacturer`/`entry_type`.
- **`device_registry.async_get_device(identifiers=…)` in new tests:** raises `RuntimeError` from test code on 2026.11.
- **`import voluptuous as vol`:** mypy `arg-type` errors against probatio-typed HA APIs.
- **`vol.All(NumberSelector(...), vol.Coerce(int))` in the schema:** wrapping a selector can break frontend serialisation. Coerce in the step instead.
- **`vol.Required` (not `data_entry_flow.Required`) with a `visible` kwarg:** plain probatio markers have no `visible`; only the `homeassistant.data_entry_flow` markers are stripped and serialised.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Show/hide credential fields | Second flow step + flow state | `data_entry_flow.Optional(visible=…)` | Native; server strips hidden values (no stale token survives a switch to `none`) |
| Reload after options change | Update listener | `OptionsFlowWithReload` | Listener + reload helpers is deprecated (2026.12); listener raises `ValueError` with this class |
| Delete repairs on entry removal | `ir.async_delete_issue` in `async_remove_entry` | `config_entry_id=` | Core cleans up on removal and on registry load |
| Redacting secrets | Custom recursive scrubber | `async_redact_data` | Handles nested dicts/lists, `DeviceInfo` |
| Shutdown flag | Reading `_shutdown_requested` | Own `_stopping` set in the `async_shutdown` override | Private base attribute (D-07) |
| Unload failure handling | `return await async_unload_platforms(...)` | `async_unload_platforms_or_raise` | Translated `ConfigEntryError` |
| HA test fixtures | phcc / copied fixtures | `pytest-homeassistant` | Official; versioned with HA |

## Common Pitfalls

### Pitfall 1: Reauth keeps stale credential keys
**What goes wrong:** basic → bearer reauth with `data_updates={...}` leaves `username`/`password`; setup then fails because `Auth(mode=bearer, username=…)` raises `"bearer auth does not use a username"` (`api.py` `Auth.__post_init__`).
**How to avoid:** build the full 1.3 data and pass `data=`. Test: a basic entry reauths to bearer → `entry.data` has no `username`/`password`.

### Pitfall 2: Test package mismatch
**What goes wrong:** keeping phcc while locking HA 2026.11 → import-time `RuntimeError` (httpx alias). Installing both phcc and `pytest-homeassistant` gives overlapping fixtures ("Do not install it together with `pytest-homeassistant-custom-component`").
**How to avoid:** one atomic bump commit: dependency, lock, imports, `pytest_plugins` removal. Warning sign: `RuntimeError: httpx was already imported`.

### Pitfall 3: `data_description` keys without a `data` key
**What goes wrong:** hassfest's `data_description_validator` raises `data_description key X is not in data` [VERIFIED: hassfest `translations.py:290-300`].
**How to avoid:** every field gets both a `data` label and a `data_description`. The key-parity test can also assert `data_description ⊆ data` per step.

### Pitfall 4: NumberSelector stores floats
**What goes wrong:** `scan_interval` is stored as `60.0`; `timedelta(seconds=60.0)` works, but D-17 requires `int` and option round-trips compare unequal.
**How to avoid:** `int(...)` in the step; a test asserts `type(entry.options[...]) is int`.

### Pitfall 5: unique_id collision is only logged
**What goes wrong:** the migration sets `unique_id=host:port` that another entry owns → HA logs ERROR "already in use" and indexes both.
**How to avoid:** `hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, uid)` check first (D-14 WARNING + skip); in reconfigure, abort `already_configured` before probing (D-21).

### Pitfall 6: Redirect error ordering
**What goes wrong:** `TraefikProxyRedirectError` subclasses the connection-error family (D-23). If the flow's `except TraefikProxyApiError` branch comes first, the redirect maps to `cannot_connect`.
**How to avoid:** catch `TraefikProxyRedirectError` before the generic branches in `_validate_input` and in the coordinator; map 300–399 in `_status_error` before the generic case. `aioclient_mock.get(url, status=302, headers={"Location": ...})` works; the mock accepts and ignores `allow_redirects`.

### Pitfall 7: Issue ignore resets on reload
**What goes wrong:** the `insecure_credentials` issue is deleted on unload (SC4), so every options change or reload re-creates it and clears a user's "ignore".
**How to avoid:** accepted by SC4; mention it in the issue text or README (Phase 8). Not a defect.

### Pitfall 8: Pre-existing flaky test
**What goes wrong:** `tests/test_cert_entity_state.py` (`test_cert_cycle_updates_timestamp_sensor_state`, `test_cert_availability_follows_cert_coordinator_only`) failed 1–2 tests in about 1 of 3–6 isolated runs on **HA 2026.10.4 (current dev env)** and on 2026.11.1 ("no sensor entity with unique_id …_tls_cert_secure.example.com") [VERIFIED: scratch reruns]. It is not caused by Phase 7.
**How to avoid:** a plan verify that sees this failure re-runs the file once before treating it as a regression. Record it as a Phase 8 candidate (next to Phase 6 IN-04).

### Pitfall 9: Abort-reason translation in options flows
Central abort reasons work only in config/subentry flows; options flows look in `options.abort` [CITED: central-abort-reasons blog]. The options flow here has no aborts, so nothing changes.

## Code Examples (tests)

```python
# Hidden fields are stripped by the FlowManager (verified probe)
result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
visible = {str(k): getattr(k, "visible", None) for k in result["data_schema"].schema}
assert visible[CONF_TOKEN] == {"field": "auth_type", "value": "bearer"}
result = await hass.config_entries.flow.async_configure(
    result["flow_id"], {CONF_URL: URL, CONF_AUTH_TYPE: "none", CONF_TOKEN: "stale"})
assert CONF_TOKEN not in result["data"]

# Diagnostics redaction (verified probe)
from pytest_homeassistant.components.diagnostics import get_diagnostics_for_config_entry
diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)
dump = json.dumps(diag)
for secret in (USERNAME, PASSWORD, TOKEN):
    assert secret not in dump

# Entry-bound issue survives unload, disappears on removal (verified probe)
assert await hass.config_entries.async_unload(entry.entry_id)
await hass.config_entries.async_remove(entry.entry_id)
assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None

# No report_usage for this integration (existing repo pattern)
assert "Detected that custom integration 'traefik_proxy'" not in caplog.text
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `pytest-homeassistant-custom-component` | `pytest-homeassistant` (core-built, HA-versioned) | 2026.11 (phcc broken since) | Dependency + import rename |
| `via_device=(domain, id)` / registry update | `via_device_id=` kwarg on `async_get_or_create`; `ChildDeviceInfo` for product parts | `via_device` removed 2027.8 | One-line change |
| Two-step credential flows | `visible` conditions on markers | 2026.11 | One form |
| `return True/False` from entry methods | `-> None` + raise `ConfigEntry*` | 2026.11 (core mandatory; custom optional) | Cleaner, translated failures |
| Local `reauth_successful` | Central `homeassistant` domain | 2026.10 | Drop local key |
| Delete issues manually on removal | `config_entry_id=` auto-cleanup | 2026.11 | Less code |

**Deprecated/outdated:**
- `device_registry.async_get_device(identifiers=…)`: deprecated (breaks 2027.8), raises from non-integration code. Use `async_get_device_by_identifier(identifier, config_entry_id)`.
- `DeviceInfo({...})` construction: `TypeError` on 2026.11 (dataclass).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The `test_cert_entity_state.py` flake is timing-related and pre-existing, not a Phase 7 concern | Pitfall 8 | Low. Verify gates may flap; reruns cover it |
| A2 | The frontend at 2026.11.0 renders `visible` (the blog states it; not checked in a real UI, and M35's visual check is Phase 8) | R-6 | Medium. If the frontend ignored it, all credential fields would show, but the server-side stripping still keeps data correct |
| A3 | hassfest via Docker accepts the new translations. Not run locally: the Docker daemon is not running and running hassfest from source was not permitted in this session; only the 2026.11.0 schema source was read | R-5, FLOW-07 | Low. CI `hassfest` job runs on the PR |

## Open Questions (RESOLVED)

All five were resolved on 2026-11-15; the decisions are recorded in `07-CONTEXT.md`.

1. **D-01/D-02/D-03 name phcc, which cannot satisfy them.**
   - What we know: no phcc release supports HA 2026.11; phcc itself declares it is broken; the official successor works with a mechanical rename (851/851).
   - Recommendation: implement D-01..D-03 with `pytest-homeassistant` (floor `>=2026.11.0`, venv/CI pinned `==2026.11.0`), record it as a deviation, and confirm with the user at the `checkpoint:human-verify` the SUS verdict already requires.
   - **RESOLVED:** manager decision 2026-11-15, CONTEXT D-01/D-02/D-03 (`pytest-homeassistant`, no human checkpoint; plan 07-01 runs an automated provenance assertion instead).
2. **D-04 names `ChildDeviceInfo` but requires `via_device_id == main.id` assertions.**
   - What we know: these exclude each other (child entries have no `via_device_id`). The `via_device_id=` keyword is the 2026.11 replacement for the registry workaround and keeps every other D-04 constraint.
   - Recommendation: `via_device_id=` (Pattern 4). If the user insists on child devices, that is a larger plan: entity `device_info` → `ChildDeviceInfo(parent_device_id=…)`, removal via child APIs, test helpers via `async_child_entries_for_config_entry`, loss of `manufacturer`/`entry_type` on sub-devices.
   - **RESOLVED:** manager decision 2026-11-15, CONTEXT D-04 (`via_device_id=`).
3. **D-13 says reauth finishes with `data_updates=…`.**
   - What we know: `data_updates` cannot remove keys, so D-10's "keys of an unused mode are absent" fails on an auth-type change.
   - Recommendation: `data=` (Pattern 3). The intent of D-13 is unchanged.
   - **RESOLVED:** CONTEXT D-13 (`data=`).
4. **D-12 needs a `required` error key that D-22's list lacks.** Recommendation: add `config.error.required` (en/de).
   - **RESOLVED:** CONTEXT D-12/D-22.
5. **`async_migrate_entry` downgrade branch.** It is unreachable (HA rejects newer versions first). Recommendation: with `-> None`, delete it or raise `ConfigEntryError`. Planner's call; the existing downgrade test exercises the HA path either way.
   - **RESOLVED:** CONTEXT D-06 (migration keeps returning `bool`; the `False` downgrade branch stays and stays tested).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | venvs, lock, CI parity | ✓ | 0.13.4 | — |
| Python 3.14 | runtime/tests | ✓ | 3.14.10 (`/usr/bin/python3.14`) | — |
| PyPI access | `uv lock`, venv install | ✓ | — | — |
| `gh` CLI | source lookups | ✓ | — | — |
| Docker daemon | local hassfest | ✗ (client 29.9.3 present, daemon not running) | — | CI `hassfest` job (already in `validate.yml`); the user can start Docker and run `docker run --rm -v "$PWD":/github/workspace ghcr.io/home-assistant/hassfest` |
| `~/.cache/traefik-proxy-integration/ha2611-venv` | D-02 min-version runs | ✗ (to be created by the bump plan) | — | Command in R-1 |
| `~/.cache/traefik-proxy-integration/ha2603-venv` | pre-bump plans | ✓ | HA 2026.3.0 / phcc 0.13.317 + override | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** Docker daemon (use CI hassfest).

## Validation Architecture

> `workflow.nyquist_validation` is `false` in `.planning/config.json`. This section is included because the orchestrator asked for it.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio 1.4.0 (`asyncio_mode = "auto"`), HA fixtures from phcc 0.13.375 (pre-bump) → `pytest-homeassistant` 2026.11.x (post-bump) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (post-bump `addopts` gains `-p no:respx`) |
| Quick run command | `uv run pytest -q` |
| Lint/type gate | `uv run ruff check custom_components tests && uv run ruff format --check custom_components tests && uv run mypy --strict custom_components/traefik_proxy` |
| Min-HA suite (pre-bump) | `~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests` |
| Min-HA suite (post-bump) | `~/.cache/traefik-proxy-integration/ha2611-venv/bin/python -m pytest -q -o addopts="-p no:respx" tests` |
| config_flow coverage gate | `uv run pytest -q -o addopts="-p no:respx" --cov=custom_components.traefik_proxy --cov-report=term-missing tests && uv run coverage report --include='custom_components/traefik_proxy/config_flow.py' --fail-under=100` |
| Baseline | 851 tests pass at HEAD `d18f96a` in scratch copies (HA 2026.10.4 dev env; HA 2026.11.0 after the rename) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FLOW-01 | auth selector, `visible`, hidden-field stripping, `required` errors, none clears creds, 1.2→1.3 migration incl. userinfo/unique_id/title | integration (flow + migration) | `uv run pytest -q tests/test_config_flow.py tests/test_reconfigure.py tests/test_migration.py` | ✅ (to rewrite/extend) |
| FLOW-02 | no listener; `OptionsFlowWithReload`; reload on change only; ints stored; grace hours applied after reload; per-item purge | integration | `uv run pytest -q tests/test_config_flow.py tests/test_entity_manager.py tests/test_init.py` | ✅ (extend) |
| FLOW-03 | reauth/reconfigure via helper; unique_id/title follow; `already_configured` before probe | integration | `uv run pytest -q tests/test_reconfigure.py tests/test_config_flow.py` | ✅ |
| FLOW-04 | `invalid_url`, `url_has_credentials`, `invalid_auth`, `cannot_connect`, `api_disabled`, `redirect`, `unknown`, `already_configured`; 100 % lines | integration + coverage | coverage gate above | ✅ (extend) |
| FLOW-05 | translated exceptions; keys exist in en/de | unit + translations | `uv run pytest -q tests/test_coordinator.py tests/test_cert_coordinator.py tests/test_init.py tests/test_translations.py` | ✅ |
| FLOW-06 | issue created/deleted on fix, unload, removal; `config_entry_id` set | integration | `uv run pytest -q tests/test_init.py` (or new `tests/test_repairs.py`) | ❌ new tests |
| FLOW-07 | `strings.json` gone; en↔de recursive key parity; placeholder parity; `data_description ⊆ data` | unit | `uv run pytest -q tests/test_translations.py` | ✅ (rewrite) |
| FLOW-08 | min HA 2026.11.0 suite green; `via_device_id == main.id`; no `report_usage`; no private attrs (grep) | integration + grep | min-HA suite + `uv run pytest -q tests/test_devices.py` + `! grep -rnE 'self\._(shutdown_requested\|listeners\|unsub_refresh\|update_interval\|debounced_refresh\|request_refresh_task\|retry_after)\b' custom_components/` | ✅ |
| DIAG-04 | redacted diagnostics; secrets absent from JSON dump | integration | `uv run pytest -q tests/test_diagnostics.py` | ❌ new |

### Sampling Rate
- **Per task commit:** quick run + lint/type gate.
- **Per plan:** quick run, lint/type gate, and the min-HA suite of the current baseline (ha2603 before the bump, ha2611 after).
- **Phase gate:** all of the above, the config_flow coverage gate, and the CI `hassfest` + `test-min-ha` jobs on the PR.

### Wave 0 Gaps
- [ ] Bump plan: `pytest-homeassistant` switch (dependency, lock, imports, `pytest_plugins`/fixture removal, `addopts -p no:respx`); create `ha2611-venv`; CI `test-min-ha`.
- [ ] `tests/test_diagnostics.py`: DIAG-04.
- [ ] Repair tests (FLOW-06), in `tests/test_init.py` or a new `tests/test_repairs.py`.

## Security Domain

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (client-side credentials to Traefik) | `Auth` dataclass validation; `PASSWORD` selectors; secrets never pre-filled (D-13) |
| V3 Session Management | no | — |
| V4 Access Control | no (HA admin owns flows) | — |
| V5 Input Validation | yes | probatio schemas + selectors; `_check_url_shape` with `ValueError` → `InvalidUrl` (IN-10); `Auth` rejects control chars / `:` in username |
| V6 Cryptography | partial | TLS via aiohttp/`ssl`; `verify_ssl` option; no hand-rolled crypto |
| V7 Error handling / logging | yes | No URL/userinfo in exception args (IN-09); `_LOGGER.exception` for `unknown` must not log credentials (do not log `user_input`) |
| V8 Data protection | yes | `async_redact_data` in diagnostics; repair for `http://` + credentials (FLOW-06) |

### Known Threat Patterns
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Credentials leaking via redirect to another host | Information disclosure | `allow_redirects=False` + `redirect` error (D-23) |
| Credentials over plain HTTP | Information disclosure | Repair issue `insecure_credentials` (D-26) |
| Secrets in diagnostics / logs / exception args | Information disclosure | Redact set (D-27); `InvalidUrl()` without args; JSON-dump assertion test |
| Stale secret kept after switching to `none` | Information disclosure | Server-side hidden-field stripping + build data without unused keys; `data=` in helpers |
| Header injection via credentials | Tampering | `Auth` control-character check (existing) |

## Sources

### Primary (HIGH confidence)
- HA 2026.11.0 wheel source (scratch venv, `homeassistant==2026.11.0`): `config_entries.py`, `data_entry_flow.py`, `helpers/data_entry_flow.py`, `helpers/field_visibility.py`, `helpers/device_registry.py`, `helpers/entity_platform.py`, `helpers/issue_registry.py`, `helpers/update_coordinator.py`, `helpers/selector.py`, `components/diagnostics/*`, `components/homeassistant/translations/{en,de}.json`, `const.py`, `homeassistant/__init__.py`
- HA 2026.3.0 source (`~/.cache/traefik-proxy-integration/ha2603-venv`): `device_registry.async_get_or_create` signature
- `pytest-homeassistant` 2026.11.0 package source and README (`github.com/home-assistant/core/tree/2026.11.0/packages/pytest-homeassistant`)
- core `script/hassfest/translations.py` @ 2026.11.0
- PyPI JSON for `homeassistant`, `pytest-homeassistant`, `pytest-homeassistant-custom-component`; PyPI provenance attestations
- Scratch probes (custom demo integration + full suite runs) on HA 2026.11.0 and 2026.11.1

### Secondary (MEDIUM–HIGH, official docs/blog)
- https://contributors.home-assistant.io/blog/2026/10/13/device-info-class/
- https://contributors.home-assistant.io/core/integrations/device-registry/
- https://contributors.home-assistant.io/blog/2026/10/21/form-fields-visible/
- https://contributors.home-assistant.io/blog/2026/10/23/config-entry-methods-return-none/
- https://contributors.home-assistant.io/blog/2026/09/28/central-config-flow-abort-reasons/
- phcc README and issue #260 (`github.com/MatthewFlamm/pytest-homeassistant-custom-component`)

### Tertiary
- none relied upon

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH. PyPI metadata plus a full suite run on the target versions.
- Architecture/APIs: HIGH. Read in the 2026.11.0 source and exercised by probes.
- Pitfalls: HIGH, except Pitfall 8 (observed flake, root cause not analysed).

**Research date:** 2026-11-15
**Valid until:** 2026-12-03 (the HA 2026.12 release may change deprecations; re-check `pytest-homeassistant` and the listener deprecation then)
