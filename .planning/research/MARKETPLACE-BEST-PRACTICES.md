# HACS Marketplace + HA Integration Best Practices (research, 2026-11-14)

Scope: `custom_components/traefik_proxy` on branch `feat/marketplace-polish`. Min HA 2026.3.0.
Primary sources: hacs.xyz, contributors.home-assistant.io (formerly developers.home-assistant.io, which now
301-redirects there), home-assistant/core source at tag **2026.11.1** (latest release on 2026-11-14), hacs/integration
source (the validators that `hacs/action` runs). The core files were downloaded with `gh api` and read directly.

Confidence: **HIGH** = I read it in a primary source or in core/HACS source code. **MEDIUM** = a secondary source,
or a primary source plus my own inference. **LOW** = not verified.

---

## 1. Summary

1. Since HA 2026.11 (released 2026-11-04), HACS ships inside HA core as the **Marketplace** integration. It uses
   the **same catalog (`hacs/default`) and the same `hacs.json`**, and getting listed still means a PR to `hacs/default`,
   which "works as before". HACS cannot be installed on HA ≥ 2026.11. (HIGH)
2. Gates for the catalog: a public repo with a description, topics, issues enabled and a README; `hacs.json` with `name`;
   a **full GitHub release** (a tag alone is not enough); and **`hacs/action` + hassfest passing with no `ignore`**.
   The repo already meets all of these on paper. The latest release v0.3.0 is from 2026-07-06, so a fresh release is needed. (HIGH)
3. The Marketplace adds **install-time checks** in core: a valid domain, a domain no other repo owns, no
   core-domain replacement, a loadable manifest `version`, and ≤100 MiB/50k files. `traefik_proxy` is unique (the other
   catalog Traefik integration, `AboveColin/HA-Traefik`, uses `traefik`). (HIGH)
4. **Brand**: `custom_components/traefik_proxy/brand/icon.png` (256²) + `icon@2x.png` (512²) is already the correct
   recipe (HA ≥ 2026.3). The Marketplace shows these images **from the latest release before install**. `icon.svg` is
   ignored by core, which serves only 8 PNG names. (HIGH)
5. New optional manifest key **`categories`** (1–3 values). `hacs/action` **warns** when it is missing and **fails** on
   an unknown value. The best fit is `computers_network.monitoring`. (HIGH)
6. **Blocker for HA 2026.12:** the integration registers `entry.add_update_listener(...)` (`__init__.py:263`) **and**
   the reconfigure flow calls `async_update_reload_and_abort` (`config_flow.py:422`). This pattern has been deprecated
   since **2026.6** (log warning, `breaks_in_ha_version="2026.12.0"`). The fix is to drop the listener and use
   `OptionsFlowWithReload`. (HIGH for the code path; MEDIUM that 2026.12 turns it into a hard error, because core
   `dev` still only logs as of today.)
7. A related bug: the update listener is **never unsubscribed**. The core 2026.11.1 `ConfigEntry` does not clear
   `update_listeners` on unload, so every reload adds another listener. (HIGH, read in source)
8. The `reload_routers` handler returns a dict, but it is registered without `supports_response`, so the documented
   response data is unreachable. (HIGH)
9. **Translations:** the Marketplace docs say custom integrations "do not use `strings.json`". Ship a complete
   `translations/en.json`. hassfest validates both files if they exist. (HIGH)
10. Quality scale: `quality_scale.yaml` is **skipped by hassfest for custom integrations** (`validate_iqs_file` returns
    early when `not integration.core`). The manifest `quality_scale` key passes schema validation. Treat the IQS rules
    as a checklist, not as a claim. (HIGH)

---

## 2. Marketplace / HACS catalog requirements checklist

"Status" shows the state of this repo as checked on 2026-11-14.

| Item | Req/Rec | How to satisfy | Status | Source | Conf |
|---|---|---|---|---|---|
| Public GitHub repo | **Required** | Must be public | ✅ public | https://hacs.xyz/docs/publish/start | HIGH |
| Repo description | **Required** (action `description` check) | Set it in GitHub repo settings | ✅ set | https://contributors.home-assistant.io/marketplace/reference/validation/ ; hacs/integration `validate/description.py` | HIGH |
| Repo topics | **Required** (action `topics` check) | Any topics. Used for search, not shown in the UI | ✅ hacs, hass, home-assistant, integration, traefik | same | HIGH |
| Issues enabled | **Required** (action `issues`) | Enable in settings | ✅ | same | HIGH |
| README / information file | **Required** (action `information`) | `README.md` explaining usage | ✅ exists, but its content is stale (it still says "Phase 2+ planned" and "HACS → Custom repositories" UI paths) | https://contributors.home-assistant.io/marketplace/guides/catalog/ | HIGH |
| README images | Not required for integrations | The `images` validator only runs for `PLUGIN`/`THEME` categories | n/a | hacs/integration `validate/images.py` (`categories = (PLUGIN, THEME)`) | HIGH |
| License | **Required** by `hacs/action` (`license` validator: the repo must have a GitHub-detected SPDX license; popular OSI licenses pass directly) | `LICENSE` with an SPDX-detectable license | ✅ MIT detected | hacs/integration `validate/license.py` (not mentioned on the contributors validation page) | HIGH |
| Not archived | **Required** | — | ✅ | validation page | HIGH |
| `hacs.json` in repo root with `name` | **Required** | `{"name": "Traefik Proxy", ...}` | ✅ | https://contributors.home-assistant.io/marketplace/reference/hacs-json/ | HIGH |
| `hacs.json` `homeassistant` | Recommended | Minimum HA per release, checked only for repos with releases. The Marketplace offers older releases to users on older HA. Raise it in the release that first needs a newer HA | ✅ `2026.3.0`; raise it if 2026.11-only APIs are adopted (see §5) | hacs-json reference; https://contributors.home-assistant.io/marketplace/guides/releases/ | HIGH |
| `hacs.json` `hacs` | Optional | The Marketplace reads it but does not compare it. Classic HACS (HA ≤ 2026.10) still honours it | `2.0.5`, harmless, keep | hacs-json reference | HIGH |
| `hacs.json` `country`, `render_readme`, other keys | Not used | `country` is not used by the Marketplace. Unknown keys are ignored | n/a | hacs-json reference | HIGH |
| One integration per repo in `custom_components/<domain>/` | **Required** | The Marketplace installs the first folder it finds. Everything the integration needs must be inside it | ✅ | https://contributors.home-assistant.io/marketplace/reference/repository-structure/ | HIGH |
| manifest `domain` | **Required** (install check) | Only `[a-z0-9_-]`; must not be owned by another installed repo; must not replace a core domain (the catalog rejects core replacements) | ✅ `traefik_proxy`. No core `traefik`/`traefik_proxy` exists; the other catalog repo uses `traefik` | validation page; `gh api` core 2026.11.1 + AboveColin/HA-Traefik tree | HIGH |
| manifest `version` | **Required** (install refused without a loader-accepted version; hassfest errors for custom integrations) | It "should" match the release tag | ✅ `0.3.0` ↔ tag `v0.3.0` (see Open Q1 on the `v` prefix) | https://contributors.home-assistant.io/marketplace/guides/integrations/ ; core `script/hassfest/manifest.py` `validate_version` | HIGH |
| manifest `documentation`, `issue_tracker`, `codeowners`, `name` | **Required** by HACS/catalog | Already present | ✅ | https://hacs.xyz/docs/publish/integration | HIGH |
| manifest key order | **Required** by hassfest | `domain`, `name`, then alphabetical | ✅ currently sorted; keep it sorted when adding `categories` | core `script/hassfest/manifest.py` `sort_manifest` | HIGH |
| manifest `categories` | **Recommended** (action **warns** if missing, **fails** on an unknown value or duplicates; 1–3 values) | `"categories": ["computers_network.monitoring"]` (alternative: `computers_network.routers_network`) | ❌ missing | https://contributors.home-assistant.io/blog/2026/10/20/integration-categories/ ; https://contributors.home-assistant.io/core/integrations/categories/ ; hacs `validate/integration_categories.py` | HIGH |
| Brand images | **Required** (action `brands`: `<integration>/brand/icon.png` **or** the domain listed under `custom` in home-assistant/brands) | See §3 | ✅ `brand/icon.png` present | hacs `validate/brands.py`; https://hacs.xyz/docs/publish/integration | HIGH |
| No Home Assistant branded images | **Required** | Don't use the HA logo | ✅ (see Open Q4 on the Traefik trademark) | https://contributors.home-assistant.io/core/integrations/brands/ | HIGH |
| hassfest action passing | **Required** for the catalog | `home-assistant/actions/hassfest@master` | ✅ in `validate.yml` (last `main` run on 2026-07-06 passed) | guides/integrations; guides/catalog | HIGH |
| `hacs/action` passing with **no `ignore`** | **Required** for the catalog ("the catalog does not accept ignored checks") | `hacs/action@main`, `category: integration` | ✅ in `validate.yml`, no ignore | validation page | HIGH |
| Action triggers | Recommended | The validation page describes the action running "on every push and pull request, nightly, and on manual start" → add `schedule:` + `workflow_dispatch:` | ⚠️ only push/PR to `main` | validation page | MEDIUM (wording, not a hard rule) |
| Published GitHub **release** (not just a tag) | **Required** for the catalog | `gh release create vX.Y.Z`. The release body becomes the update-entity release notes; put required user actions at the top. Keep old releases, because users can pick older versions | ⚠️ latest is v0.3.0 (2026-07-06). Cut a new release after the polish work, and link it in the `hacs/default` PR | https://contributors.home-assistant.io/marketplace/guides/releases/ | HIGH |
| Catalog submission | Required to be listed for everyone | Fork `hacs/default`, branch from `master`, add `akentner/homeassistant-traefik-proxy-integration` to the `integration` JSON list **in alphabetical order**, and open the PR **from a personal account**. Complete the template with links to the latest release, a passing HACS action run without ignore, and a passing hassfest run. Don't request reviews from individuals (that closes the PR). Review takes **months** | ❌ not in `hacs/default` | https://contributors.home-assistant.io/marketplace/guides/catalog/ | HIGH |
| Without a catalog entry | — | Users can add the repo as a custom repository (a My link works). It must be public, have `hacs.json` and the right layout | ✅ works today | https://next.home-assistant.io/integrations/marketplace/ | HIGH |
| My-link badge in README | Recommended | The README is where the My-link badge goes | ❌ | guides/integrations; https://hacs.xyz/docs/publish/start | MEDIUM |
| Marketplace display | Info | It shows the description, version, author, source and issue links, and stars, plus brand images from the latest release before install. Sorting is by stars or recent activity, and new repos are flagged | — | https://next.home-assistant.io/integrations/marketplace/ ; guides/integrations | HIGH |
| Screenshots | Not a requirement | No source mentions screenshots for integrations | — | — | HIGH (absence) |
| Restart behaviour | Info | A first install of a config-flow integration loads without a restart. Updates and removals of loaded integrations need a restart (the Marketplace raises a repair with a restart button) | — | guides/integrations | HIGH |
| Domain removal / critical | Info | Archiving removes the repo from the catalog. Never delete a catalogued repo, or you are blocked from adding repos in future | — | guides/catalog | HIGH |

---

## 3. Brand icon — exact recipe

Source: https://contributors.home-assistant.io/core/integrations/brands/ (section "Brand images for custom
integrations"), blog https://contributors.home-assistant.io/blog/2026/02/24/brands-proxy-api/, core source
`homeassistant/components/brands/const.py` + `__init__.py` @ 2026.11.1. All HIGH.

- **Location:** `custom_components/traefik_proxy/brand/` (inside the integration folder, **not** the repo root, unless
  `content_in_root`). Supported since **HA 2026.3**, which matches our minimum version.
- **Allowed file names** (core `ALLOWED_IMAGES`; anything else returns 404 from the brands proxy):
  `icon.png`, `icon@2x.png`, `logo.png`, `logo@2x.png`, `dark_icon.png`, `dark_icon@2x.png`, `dark_logo.png`,
  `dark_logo@2x.png`. **PNG only. SVG is not served**, so `brand/icon.svg` is dead weight. It does no harm, so keep it
  as a source asset or move it out of the shipped folder.
- **Sizes:** icon is square, **256×256**; `@2x` is **512×512**. Logo keeps the brand's aspect ratio (landscape preferred),
  with the shortest side 128–256 px (`@2x`: 256–512 px). If the brand logo is square, ship **only the icon**.
- **Style:** a transparent background is preferred. Trim it: no empty space, borders or padding. Compress properly for
  the web; lossless and interlaced are preferred. `dark_*` images are only for when the light image fails on a dark
  background.
- **Fallbacks** (core `IMAGE_FALLBACKS`): `logo→icon`, `icon@2x→icon`, `dark_icon→icon`,
  `dark_logo→dark_icon→logo→icon`, and so on. So `icon.png` alone is enough.
- **Precedence:** for installed custom integrations, local `brand/` images win over the brands CDN. For the Marketplace
  view of a **not yet installed** integration, core tries local files, then the brands repo, then the cached
  `marketplace/{domain}/{image}` CDN path (taken from the latest release).
- **home-assistant/brands PR:** no longer needed for custom integrations. `hacs/action` still accepts it as a fallback.
  Remove `brand/` only if the integration ever moves into core.
- **Current state:** `icon.png` 256×256 RGBA and `icon@2x.png` 512×512 RGBA are ✅ correct. The teal mark on a
  transparent background also reads well on dark, so no `dark_icon` is needed. Possible polish: trim the residual
  padding and interlace the PNGs (optional).

---

## 4. Best-practice checklist (HA 2025–2026, custom-integration relevant)

The IQS rule list was read at https://contributors.home-assistant.io/core/quality-scale/rules/ (Bronze 20, Silver 10,
Gold 21, Platinum 3). Rule IDs are given in `code`. "Status" is a quick scan of the current code, not a full audit.

### 4.1 Config / options / reconfigure / reauth flows

| Item | Req/Rec | How to satisfy | Status | Source | Conf |
|---|---|---|---|---|---|
| **Update listener + reloading helper conflict** | **Required before 2026.12** | Core logs `report_usage("has an update listener and should use it for scheduling a reload", breaks_in_ha_version="2026.12.0")` when `entry.update_listeners` is non-empty and the flow calls `async_update_reload_and_abort(...)` or `_abort_if_unique_id_configured(updates=..., reload_on_update=True)`. The blog post gives three fixes: (1) remove the listener and rely on the flow reload helpers; (2) replace `async_update_reload_and_abort` with `async_update_and_abort` (the listener then does the reload); (3) pass `reload_on_update=False`. **Recommended for this repo:** option 1. Delete `entry.add_update_listener(_async_options_updated)`, make `TraefikProxyOptionsFlow(OptionsFlowWithReload)`, which reloads only when the options changed, and keep `async_update_reload_and_abort` in reconfigure. Trade-off: a scan-interval change now does a full reload instead of mutating the interval live (design decision D-08). That is acceptable because the setup is cheap. Note that `OptionsFlowWithReload` **raises `ValueError`** if any update listener is still registered | ❌ `__init__.py:263` + `config_flow.py:422` | https://contributors.home-assistant.io/blog/2026/05/07/config-entry-listener-together-with-reloading-methods/ ; https://github.com/home-assistant/core/pull/169198 ; core `config_entries.py` @2026.11.1 L3368, L3793, L4183, L4285 ; example fix https://github.com/golles/ha-knmi/pull/502 | HIGH |
| Listener lifecycle | Required (`config-entry-unloading`) | Any listener must be wrapped: `entry.async_on_unload(entry.add_update_listener(...))`. Core does **not** clear `update_listeners` on unload: the list is only initialised in `ConfigEntry.__init__`, and the entry object survives reloads. The current code leaks one listener per reload. Moot if the listener is removed (row above) | ❌ docstring at `__init__.py:275` wrongly claims HA removes it | core `config_entries.py` L583, L1347-1348 | HIGH |
| Reauth step | Rec | Replace the manual `async_update_entry` + `async_reload` + `async_abort("reauth_successful")` (`config_flow.py:~357`) with `return self.async_update_reload_and_abort(entry, data_updates={CONF_API_KEY: ...})` once the listener is gone. The helper sets the reason and uses the central translation domain | ⚠️ manual | core `config_entries.py` L3753ff | HIGH |
| Centrally translated abort reasons | Rec (HA ≥ 2026.10) | `reauth_successful` and `reconfigure_successful` (plus the OAuth/general ones) are translated by the `homeassistant` domain when the helper's default reason is used. **Keep the local keys while `hacs.json.homeassistant` < 2026.10**, then drop them | info | https://contributors.home-assistant.io/blog/2026/09/28/central-config-flow-abort-reasons/ | HIGH |
| `step_id` on every form/menu/progress | **Required by 2027.5** (warning now) | Pass `step_id=` explicitly to `async_show_form/menu/progress/external_step` | ✅ all `async_show_form` calls pass `step_id` | https://contributors.home-assistant.io/blog/2026/10/23/flow-results-require-step-id/ | HIGH |
| `config-flow`, `test-before-configure`, `unique-config-entry`, `reauthentication-flow`, `reconfiguration-flow` | IQS B/B/B/S/G | Already implemented | ✅ (by code scan) | IQS rules | MEDIUM |
| Conditional form fields | Optional (new) | Fields can show or hide based on other fields (2026.10+). Raises the minimum version | — | https://contributors.home-assistant.io/blog/2026/10/21/form-fields-visible/ | HIGH |
| Advanced mode | Avoid | `show_advanced_options` / advanced-mode checks are deprecated | ✅ not used (grep) | https://contributors.home-assistant.io/blog/2026/05/26/advanced-mode-config-flow-deprecation/ | HIGH (title only) |

### 4.2 Setup, runtime data, coordinator

| Item | Req/Rec | How to satisfy | Status | Source | Conf |
|---|---|---|---|---|---|
| `runtime-data` | IQS Bronze | `entry.runtime_data` + typed `type XConfigEntry = ConfigEntry[...]` | ✅ | IQS rules | HIGH |
| Setup/unload return value | Rec | Core integrations return `None` since 2026.11. For custom integrations booleans are **not deprecated**: `False` becomes a generic `ConfigEntryError`. **Do NOT switch to `-> None` while the minimum HA is < 2026.11**, because 2026.3.0 logs "did not return boolean" and fails setup (verified in 2026.3.0 `config_entries.py:771`). Prefer raising `ConfigEntryNotReady` / `ConfigEntryAuthFailed` / `ConfigEntryError` with `translation_key` over returning `False` | ✅ returns `True` | https://contributors.home-assistant.io/blog/2026/10/23/config-entry-methods-return-none/ ; core 2026.3.0 vs 2026.11.1 source | HIGH |
| Unload helper | Rec (2026.11+) | `await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)` (2026.11 API, so it raises the minimum version) | info | same blog | HIGH |
| Coordinator `config_entry=` kwarg | Rec | Pass it explicitly (not enforced for custom integrations) | ✅ both coordinators | core `update_coordinator.py` L102-115 | HIGH |
| `_async_setup` | Rec | Override for one-time loading on the first refresh (for example the `/api/version` probe). Errors in it raise `ConfigEntryNotReady` | optional | core `update_coordinator.py` L420 | HIGH |
| `always_update=False` | Rec | Listeners fire only when the data `__eq__` changes. Suits dict/list JSON payloads and cuts state writes | optional | core `update_coordinator.py` L74-79, L91 | HIGH |
| `UpdateFailed(retry_after=...)` | Optional | Backoff hint. During first refresh it is passed to `ConfigEntryNotReady` | optional | core `update_coordinator.py` L48-59, L516 | HIGH |
| Translated `UpdateFailed` | Rec (`exception-translations`, Gold) | `raise UpdateFailed(translation_domain=DOMAIN, translation_key="...", translation_placeholders=...)` + `exceptions` section in `en.json` | ❌ `coordinator.py:126` uses `str(err)` | IQS rules | MEDIUM (rule read; kwargs from HomeAssistantError base) |
| `appropriate-polling`, `test-before-setup`, `entity-unavailable`, `log-when-unavailable` | IQS B/B/S/S | Coordinator pattern covers most of this | ✅ mostly | IQS rules | MEDIUM |
| `inject-websession`, `async-dependency` | Platinum | `async_get_clientsession` / `async_create_clientsession(verify_ssl=...)` | ✅ by design (STACK.md) | IQS rules | MEDIUM |

### 4.3 Entities

| Item | Req/Rec | How to satisfy | Status | Source | Conf |
|---|---|---|---|---|---|
| `has-entity-name` + `entity-translations` | IQS Bronze / Gold | `_attr_has_entity_name = True`. Static names via `_attr_translation_key` + `entity.<platform>.<key>.name` in `en.json` instead of `_attr_name = "Reload"`. Dynamic names (router or service names) may stay `_attr_name` | ⚠️ `button.py:71`, `binary_sensor.py:277/333/383` use hard-coded English names | IQS rules | HIGH (rule) |
| `icon-translations` | Gold | `icons.json` with `entity.<platform>.<translation_key>.default` / `state`, and `services.<action>` icons | ❌ no `icons.json` | IQS rules; https://developers.home-assistant.io/blog/2024/08/27/changed-icon-translations-schema | HIGH |
| `entity-category` | Gold | `EntityCategory.DIAGNOSTIC` for "any_*_failing", version and reload button | ⚠️ grep found no `EntityCategory` usage (the code uses a custom device "category" concept) → verify | IQS rules | MEDIUM |
| `entity-disabled-by-default` | Gold | `_attr_entity_registry_enabled_default = False` for noisy entities | ✅ used | IQS rules | HIGH |
| `entity-device-class` | Gold | Use `BinarySensorDeviceClass.PROBLEM` / `SensorDeviceClass.TIMESTAMP` where they fit | ✅ partly (PROBLEM used) | IQS rules | MEDIUM |
| `entity-unique-id` | Bronze | — | ✅ | IQS rules | HIGH |
| `parallel-updates` | Silver | Module-level `PARALLEL_UPDATES = 0` in each read-only coordinator platform (sensor, binary_sensor). Set `PARALLEL_UPDATES = 1` (or 0 if safe) on `button.py` | ❌ not set anywhere | IQS rules | HIGH (rule) / MEDIUM (values) |
| `devices` | Gold | `DeviceInfo(...)` keyword construction, `entry_type=DeviceEntryType.SERVICE` | ✅ `entity.py:74` uses kwargs, so it is compatible with the 2026.11 dataclass | https://contributors.home-assistant.io/blog/2026/10/13/device-info-class/ | HIGH |
| `dynamic-devices` / `stale-devices` | Gold | Routers and services appear and disappear between polls. Add new entities from a coordinator listener (diff the known set). Remove stale ones via `async_remove_config_entry_device` and/or entity-registry cleanup | ⚠️ verify: sensor platforms add once at setup, and the cert platform has a listener (`sensor.py:152`) | IQS rules | MEDIUM |
| Don't set `entity_id` manually | Required by 2027.5 if mismatched | Let HA generate it | ✅ not set (grep) | https://contributors.home-assistant.io/blog/2026/04/07/entity-id-mismatched-domain-deprecated/ | HIGH |

### 4.4 Service actions

| Item | Req/Rec | How to satisfy | Status | Source | Conf |
|---|---|---|---|---|---|
| `action-setup` | Bronze | Register in `async_setup`, not per entry | ✅ `__init__.py:159` | IQS rules | HIGH |
| Response data | Bug fix | The handler returns `dict[str, Any]`, but `async_register_admin_service(...)` has no `supports_response=SupportsResponse.OPTIONAL`, so callers cannot get the response. Add it, and document the response in `services.yaml` / README | ❌ | core `helpers/service.py` @2026.11.1 L1018-1030 | HIGH |
| `action-exceptions` | Silver | Raise `ServiceValidationError` (bad input) / `HomeAssistantError` (API failure) with `translation_domain` + `translation_key` | ⚠️ `HomeAssistantError("No loaded Traefik config entry…")` has an untranslated literal message | IQS rules | HIGH |
| Service name/description translations | Rec | Move `name`/`description`/fields from `services.yaml` into `en.json` `services.<action>`. Keep only the schema (fields/selectors) in `services.yaml`. Icon in `icons.json` `services` | ⚠️ `services.yaml` holds the English text inline | https://developers.home-assistant.io/blog/2023/07/11/translating-services | MEDIUM (older post, still current practice) |
| `docs-actions` | Bronze | Document the action in the README | ⚠️ check the README | IQS rules | HIGH |

### 4.5 Translations / strings

| Item | Req/Rec | How to satisfy | Status | Source | Conf |
|---|---|---|---|---|---|
| `translations/en.json` complete | **Required** | Custom integrations "do not use `strings.json` and are not translated on Lokalise". Ship the finished `translations/en.json`. hassfest validates both `strings.json` and `translations/en.json` against the same schema | ✅ both exist and are identical. Decide: drop `strings.json`, or keep it as the source plus a sync check | https://contributors.home-assistant.io/marketplace/guides/integrations/ ; core `script/hassfest/translations.py` L746-751 | HIGH |
| Additional languages | Rec | `translations/de.json` (the user's locale) | ❌ | — | MEDIUM |
| Sections to add | Rec | `entity.*` (names), `exceptions.*` (translated errors), `services.*`, `issues.*` (repairs) | ❌ partly | IQS rules | MEDIUM |

### 4.6 Diagnostics, repairs, observability

| Item | Req/Rec | How to satisfy | Status | Source | Conf |
|---|---|---|---|---|---|
| `diagnostics` | Gold | `diagnostics.py` with `async_get_config_entry_diagnostics` returning `async_redact_data(..., {CONF_API_KEY, CONF_URL?})` plus coordinator data | ❌ no `diagnostics.py` | IQS rules | HIGH (rule) |
| `repair-issues` | Gold | For example: an HTTP (non-TLS) URL with a token, or a Traefik API that is unreachable for a long time. Since **2026.11**, pass `config_entry_id=entry.entry_id` to `ir.async_create_issue` (auto-cleanup on entry removal; an unknown entry raises `HomeAssistantError`), and use `ir.async_refresh_issues(...)` as a context manager instead of delete-and-recreate. Both are 2026.11 APIs, so they raise the minimum HA | ❌ | https://contributors.home-assistant.io/blog/2026/10/28/issue-registry-refresh/ | HIGH |
| `strict-typing` | Platinum | `mypy --strict` in CI | ✅ in `validate.yml` | IQS rules | HIGH |
| `test-coverage` | Silver | > 95 % per module; `config-flow-test-coverage` (Bronze) means 100 % of flows incl. error recovery | ⚠️ verify the numbers | IQS rules | HIGH |
| `quality_scale.yaml` | Optional, ignored | hassfest returns early for non-core integrations (`if not integration.core: return`). The manifest key `quality_scale` passes the schema, and only the "Silver+ needs codeowners" check applies. Putting the file in-tree for self-tracking is harmless. Keep **omitting** the manifest key (no benefit; the IQS docs only describe core) | ✅ omitted | core `script/hassfest/quality_scale.py` L2038-2041 ; `manifest.py` L325, L562-570 | HIGH |
| Docs rules (`docs-*`) | Bronze to Gold | README sections: high-level description, installation (Marketplace + manual), removal, configuration parameters, data update cadence, known limitations, troubleshooting, use cases/examples, supported functions | ⚠️ README is outdated | IQS rules | HIGH |

### 4.7 Validation / schema

| Item | Req/Rec | How to satisfy | Status | Source | Conf |
|---|---|---|---|---|---|
| voluptuous → Probatio | **No action required** | Since 2026.9, `import voluptuous as vol` resolves to Probatio (module alias); voluptuous is no longer installed. No deprecation and no removal date. Only core bans the import. Optional: `import probatio` for `Secret` markers (redacted errors), `DataclassSchema`, and structured errors. **Tests that assert on voluptuous error text may break** | ✅ `config_flow.py` uses `vol`/`cv`, which keeps working | https://contributors.home-assistant.io/blog/2026/09/30/probatio-validation-engine/ | HIGH |
| Dev dependency | Check | If tests import `voluptuous` directly while running against HA ≥ 2026.9, the module comes from HA's alias. Keep `pytest-homeassistant-custom-component` pinned to the min-HA-compatible floor | info | same | MEDIUM |

---

## 5. Deprecations / breaking changes in HA 2026.x relevant to a 2025-era integration

| HA version | Change | Replacement | Affects us? | Source | Conf |
|---|---|---|---|---|---|
| 2026.3 | Custom integrations ship their own `brand/` images (local wins over CDN); brands served via `/api/brands/...` | `brand/icon.png` etc. | ✅ done | blog 2026-02-24 brands-proxy-api | HIGH |
| 2026.6 dep. → **2026.12 error** | Update listener + `async_update_reload_and_abort` / `_abort_if_unique_id_configured(updates, reload_on_update=True)` | Remove the listener + `OptionsFlowWithReload`, **or** `async_update_and_abort`, **or** `reload_on_update=False` | **YES**, must fix | blog 2026-05-07; core PR #169198; 2026.11.1 source | HIGH (dep.) / MEDIUM (error in 2026.12: not yet on core `dev` today) |
| 2026.6–2026.7 | Device registry: devices restricted to a single config entry and at most one subentry | — | No (one device per entry) | blog 2026-07-21 | MEDIUM (title only) |
| 2026.9 | voluptuous replaced by Probatio (aliased) | Optional `import probatio` | No code change; error texts may differ in tests | blog 2026-09-30 | HIGH |
| 2026.9 (enforced) | `DeviceEntry.config_entries` multi-entry deprecation enforced | `DeviceEntry.config_entry_id` | Check whether the tests use it | blog 2026-09-15 | MEDIUM (title only) |
| 2026.10 | Shared abort reasons translated centrally (`reauth_successful`, `reconfigure_successful`, …) | Use the helpers' default reason; drop local keys once min HA ≥ 2026.10 | Later | blog 2026-09-28 | HIGH |
| 2026.10 | `RestoreStateData.last_states` removed | Indexed by entity registry ID | No | blog 2026-10-06 | MEDIUM (title only) |
| 2026.11 | `DeviceInfo` / `ChildDeviceInfo` are dataclasses. `DeviceInfo({...})` dict construction raises `TypeError`; subscript/`.get()` is a compat layer to be deprecated later; `via_device` removed 2027.8; `default_*`, `created_at`, `modified_at` removed 2027.9 | Keyword construction + attribute access; `UNDEFINED` for unset fields | ✅ kwargs already. Avoid `info["..."]` in the code and tests | blog 2026-10-13 | HIGH |
| 2026.11 | `async_setup_entry` / `async_unload_entry` / `async_migrate_entry` return `None` in core | Raise `ConfigEntry*` exceptions. Custom integrations: bools still OK; don't return `None` while min HA < 2026.11 | Optional | blog 2026-10-23 | HIGH |
| 2026.11 | Repairs: `config_entry_id` on issues, `ir.async_refresh_issues` | — | When repairs are added | blog 2026-10-28 | HIGH |
| 2026.11 | HACS replaced by the Marketplace; templates using `integration_entities('hacs')` → `'marketplace'`; `hass.data["hacs"]` / `hacs_dispatch_*` gone | — | No (we don't touch HACS internals) | https://next.home-assistant.io/integrations/marketplace/ | HIGH |
| 2026.11 | `UNDEFINED`/`UndefinedType` deprecated in favour of `Undefined` | `homeassistant.helpers.typing.Undefined` | Only if imported (check `grep UNDEFINED`: none in our code) | blog 2026-11-01 | MEDIUM (title only) |
| 2026.12 dep. → 2027.12 removal | `homeassistant.const.ATTR_IDENTIFIERS`, `ATTR_MANUFACTURER`, `ATTR_MODEL`, `ATTR_SW_VERSION`, `ATTR_CONFIGURATION_URL`, … | `DeviceInfo` field names | ✅ not imported (grep) | blog 2026-11-10 | HIGH |
| warn now → **2027.5** | Flow results without `step_id` | Pass `step_id=` | ✅ | blog 2026-10-23 | HIGH |
| warn now → **2027.5** | Entity IDs whose domain mismatches the platform | Don't set `entity_id` | ✅ | blog 2026-04-07 | HIGH |
| 2026.5 | Advanced mode in data entry flows deprecated | — | ✅ not used | blog 2026-05-26 | MEDIUM (title only) |

---

## 6. Open questions / unverifiable items

1. **`v` tag prefix vs manifest `version`.** The releases guide says "use the same version in `manifest.json` as in the
   tag", but our tags are `v0.3.0` and the manifest says `0.3.0`. No source says the `v` prefix is a problem; HACS has
   historically handled it via AwesomeVersion. **Unverified.** Either keep it, or switch to un-prefixed tags to be safe.
2. **Does 2026.12 really hard-fail the listener pattern?** The blog post and the PR discussion say "error from 2026.12",
   but core `dev` (checked 2026-11-14) still uses `report_usage(..., core_behavior=LOG)`. `report_usage` for custom
   integrations defaults to a log warning. Fix it anyway: it is cheap, and it removes the listener leak.
3. **Catalog review checks beyond the published table.** The validation page says the catalog review "runs more checks
   than the action" and points to the catalog guide. The catalog guide's table is what I listed. Any hidden
   reviewer-discretion criteria are unknown.
4. **Trademark:** the brand icon appears to be the Traefik (Traefik Labs) product mark. The rules only forbid **Home
   Assistant** branded images. Whether using a third-party trademark is acceptable in the catalog is not addressed in
   any source I read. Brands-repo practice for core integrations is to use the vendor logo, so it is most likely fine
   (LOW).
5. **Exact `hacs/action` failure vs warning per check.** From source: `brands`, `description`, `topics`, `issues`,
   `license`, `archived`, `hacsjson`, `information`, and an unknown `categories` value raise (fail). A missing
   `categories` key only logs a warning. I did not run the action against the current branch. Recommend running it via
   a PR before submitting.
6. **Quality-scale rule detail pages** were not individually fetched (only the rule index). The implementation
   specifics in §4 (for example the `PARALLEL_UPDATES` values and the translated-exception kwargs) are standard patterns,
   marked MEDIUM.
7. **`contributors.home-assistant.io` vs `developers.home-assistant.io`.** All developer docs and the blog moved
   (301). Old links in STACK.md and CLAUDE.md still work via the redirect, but should be updated.
8. **Marketplace README rendering / info.md.** The sources describe the Marketplace showing the description, version,
   author and links. Neither README rendering nor `info.md` is mentioned. `info.md` appears obsolete (it is not in the
   hacs.json reference and `render_readme` is not listed). The project constraint "HACS default repository structure
   (`hacs.json`, `info.md`, …)" is outdated (MEDIUM).

### Suggested phase split (input for the planner)

- **P-A: 2026.12 compatibility (blocker).** Remove the update listener, add `OptionsFlowWithReload`, move reauth to
  `async_update_reload_and_abort`, update tests. Fixes the listener leak.
- **P-B: Marketplace metadata.** Add the manifest `categories`, update the CI triggers (schedule + dispatch), optionally
  trim or interlace the brand PNGs and decide about `icon.svg`, rewrite the README (Marketplace install, My-link badge,
  docs-* sections), decide on `strings.json`.
- **P-C: Entity/UX polish (IQS Gold).** `translation_key` names, `icons.json`, `EntityCategory.DIAGNOSTIC`,
  `PARALLEL_UPDATES`, `de.json`.
- **P-D: Observability.** `diagnostics.py` with redaction, translated exceptions (`UpdateFailed`, service errors),
  service `supports_response`, repairs (needs a decision on raising the minimum HA to 2026.11).
- **P-E: Dynamic and stale devices/entities** for routers and services that appear or disappear.
- **P-F: Release + `hacs/default` PR.** Bump the version, publish a GitHub release, run the HACS action and hassfest
  without ignore, then open the PR from the personal account.
