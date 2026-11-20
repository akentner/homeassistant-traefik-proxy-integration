# Phase 5: Entity model + lifecycle - Context

**Gathered:** 2026-11-14
**Status:** Ready for planning
**Source:** PRD Express Path (manager brief + decisions log M1–M34, U1–U2, W1–W31 + code audit + marketplace research + Phase 4 review carry-over)

<domain>
## Phase Boundary

Phase 5 rebuilds the entity layer of `custom_components/traefik_proxy` on top of
the Phase 4 `TraefikSnapshot` so that entities follow live Traefik state for the
lifetime of the config entry:

- one entity manager per entry (add new items, mark vanished items `missing`,
  remove after a 24 h grace period, re-bind items that reappear);
- per-item entities that hold only their key and write state only on change;
- routers and services as ENUM sensors, problem aggregates on by default;
- one main device plus Routers / Services / Certificates sub-devices;
- translated entity/device names (en + de), `icons.json`, entity categories,
  `PARALLEL_UPDATES`;
- the never-working reload feature replaced by a "Refresh now" button;
- a config-entry migration for 0.3.0 installs with a repair notice.

**In scope:** `entity.py`, new `entity_manager.py`, `sensor.py`,
`binary_sensor.py`, `button.py`, `__init__.py` (services, migration, device
topology, unload/remove), `data.py` (runtime data gains the manager if needed),
`const.py`, `api.py` (only the removal of `reload_routers`), `services.yaml`
(deleted), `translations/en.json` (+ mirrored `strings.json`), new
`translations/de.json`, new `icons.json`, `config_flow.py` (only
`MINOR_VERSION`), and the migration of every affected test.

**Out of scope (later phases):** certificate source, probe rewrite, `rules.py`,
live `days_left`, problem-on instead of unavailable for certs,
`certificates_problem` aggregate (Phase 6); auth selector, options-flow rework
incl. the per-item toggle field in the form, `OptionsFlowWithReload`, removal
of the update listener, `strings.json` deletion, full de.json parity,
diagnostics, the `http://`+credentials repair (Phase 7); docstring sweep,
README/CHANGELOG, CI (Phase 8). The data layer (`api.py` read path,
`models.py`, `coordinator.py`) is not changed except where an entity need
requires a new snapshot field.

</domain>

<decisions>
## Implementation Decisions

### Entity manager (ENT-01, WR-04, WR-05)
- **D-01:** New module `custom_components/traefik_proxy/entity_manager.py`.
  Exactly one manager instance per config entry (reachable from
  `entry.runtime_data`). Platforms register "kinds" with it: a key source
  (callable returning the current key set, e.g. router names from
  `coordinator.data.routers`, cert hosts from `cert_coordinator.data`), an
  entity factory, and the platform's `async_add_entities`. The manager is the
  only code that adds or removes per-item entities; the five copy-pasted
  stale-cleanup closures and the two cert "create pending" closures in
  `sensor.py` / `binary_sensor.py` are deleted.
- **D-02:** Kinds managed in this phase: routers (sensor), services (sensor),
  entrypoints (sensor), certificate timestamp sensors and certificate expiring
  binary sensors (keyed by host, cert coordinator). Each key is added **once**
  per entity platform for the lifetime of the loaded entry; a key that is
  already known is never passed to `async_add_entities` again (fixes WR-05 —
  no "does not generate unique IDs" ERROR on cert cycles or threshold changes).
- **D-03:** Lifecycle per key: present → live entity; vanished → entity stays
  registered and available with state `missing` (cert entities: unavailable
  while missing, their semantics are redone in Phase 6); vanished for
  `MISSING_GRACE_PERIOD = timedelta(hours=24)` → registry entry removed via
  `er.async_remove`; reappears inside the grace period → the same entity (same
  unique_id, same entity_id, user renames/areas intact) shows live state again.
  A short paginated read that drops an item (WR-04) therefore only produces a
  `missing` state for one cycle and never deletes a registry entry.
- **D-04:** The grace period is wall-clock, not uptime: the "missing since"
  timestamp survives an HA restart and an entry reload. On setup the manager
  reads `er.async_entries_for_config_entry` once and also creates entities for
  registry entries whose key is absent from the first snapshot (state
  `missing`), so orphaned entries are still removed after the grace period.
  Mechanism is planner's choice (recommended: the per-item entity exposes a
  `missing_since` attribute and restores it via `RestoreEntity` /
  `async_get_last_state()`; alternative: a per-entry `helpers.storage.Store`).
- **D-05:** Removal must also happen when nothing changes: the main
  coordinator uses `always_update=False`, so a snapshot that stays equal for
  24 h never notifies listeners. The manager therefore schedules its own check
  (e.g. `async_track_time_interval` or `async_call_later` at the earliest
  deadline), registered through `entry.async_on_unload`. No listener or timer
  iterates `registry.entities` (the whole HA registry); the manager uses only
  `er.async_entries_for_config_entry(registry, entry.entry_id)` and only when
  the key set changed or a deadline fired (A-14, P-04).
- **D-06:** Per-item option (ENT-10): new constant
  `CONF_PER_ITEM_ENTITIES = "per_item_entities"`, default `True`, read from
  `entry.options`. When `False`, router and service kinds are not registered,
  and at setup the manager removes this entry's existing router/service
  per-item registry entries immediately (user choice, no grace period).
  Entrypoint, certificate, aggregate and diagnostic entities are unaffected.
  The options-form field for this toggle is added in Phase 7 (FLOW-02 lists
  it); Phase 5 tests set `entry.options` directly.

### Entities (ENT-02, ENT-04, ENT-05, ENT-06, ENT-08)
- **D-07:** Entity bases in `entity.py`: `TraefikEntity` (main coordinator)
  and `TraefikCertEntity` (cert coordinator), both `_attr_has_entity_name =
  True`, sharing one device-info factory (D-13, D-14). Per-item entities store only
  their key and look up the current model in the snapshot (or cert data) on
  every update. They override `_handle_coordinator_update` to call
  `async_write_ha_state` only when their own model object (dataclass equality)
  or derived state changed; aggregates compare their computed state +
  attributes with the last written value. Redundant `available` overrides that
  return `coordinator.last_update_success` are deleted (A-20). The old class
  names `TraefikProxyEntity` / `TraefikProxyCertEntity` may stay as the
  concrete names if renaming costs churn — the requirement is the two bases
  with one factory; record the choice.
- **D-08:** No explicit `self.entity_id = ...` anywhere (deprecated for
  platform-mismatched IDs, HA 2027.5). Existing installs keep their registry
  entity_ids (keyed by unique_id); new installs get `has_entity_name`-derived
  IDs. Static names come from `_attr_translation_key`; per-item entities use
  the Traefik name as `_attr_name` (dynamic); no hard-coded `_attr_icon`.
- **D-09:** Unique IDs keep the existing scheme so existing entities survive:
  router sensor `{entry_id}_http_router_{name}` (now in the `sensor` domain;
  the old `binary_sensor` entries are removed by the migration, D-18), service
  sensor `{entry_id}_http_service_{name}` (unchanged — service entities were
  already sensors, so their entity_ids and customisations are preserved),
  entrypoint `{entry_id}_http_entrypoint_{name}`, counts
  `{entry_id}_overview_{routers|services|middlewares}_count`, problem
  aggregates `{entry_id}_diagnostics_any_{router|service|middleware}_failing`
  (kept so existing automations keep their entity_ids; translation keys are
  `routers_problem` / `services_problem` / `middlewares_problem`), cert
  `{entry_id}_tls_cert_{host}` and `{entry_id}_tls_expiring_{host}`. New:
  `{entry_id}_version`, `{entry_id}_start_time`, `{entry_id}_healthy_ratio`,
  `{entry_id}_refresh`.
- **D-10:** Router and service sensors: `SensorDeviceClass.ENUM`, options
  `enabled`, `warning`, `error`, `disabled`, `missing` (from `Status` plus
  `missing`), translated via `entity.sensor.<key>.state.*`. Router attributes
  (one canonical key each): `rule`, `service`, `provider`, `entry_points`,
  `middlewares`, `tls`, `errors`. Service attributes: `type`, `provider`,
  `servers_up`, `servers_total`, `used_by`, `errors` — never server URLs or
  IPs (S-06). No duplicate `name` / `router_name` / `service_name` /
  `status_breakdown` copies (P-09). A service's state is its Traefik status; a
  DOWN server shows in `servers_up` < `servers_total` and in the
  `services_problem` aggregate (already part of `TraefikSnapshot.service_problems`).
- **D-11:** Aggregates and diagnostics:
  - `routers_problem`, `services_problem`, `middlewares_problem`:
    `binary_sensor`, `device_class=problem`, **enabled by default**, no entity
    category, one class plus three entity descriptions (A-13); on when the
    snapshot's problem tuple for the kind is non-empty; attributes
    `problems` (sorted names, at most 50) and `problem_count`.
  - Router / service / middleware count sensors: `EntityCategory.DIAGNOSTIC`,
    `MEASUREMENT`, attributes `enabled`, `warning`, `error`, `disabled` only.
  - `version` sensor (state = Traefik version, attribute `codename`) and
    `start_time` sensor (`device_class=timestamp`, from `version.start_date`):
    diagnostic, enabled by default (ENT-06 lists only entrypoints and healthy
    ratio as disabled by default).
  - `healthy_ratio` sensor (`%`, `MEASUREMENT`, enabled ÷ non-disabled
    routers, 100 % when there is no non-disabled router): diagnostic,
    disabled by default.
  - Entrypoint sensors: diagnostic, disabled by default, attribute `protocol`.
  - Refresh button: diagnostic (D-17).
  The middlewares aggregate is the only middleware entity (per-middleware
  entities stay out of scope).
- **D-12:** Translations and icons: entity names, ENUM states and device names
  go into `translations/en.json`; `strings.json` is kept byte-identical to
  `en.json` until Phase 7 deletes it (FLOW-07). New `translations/de.json`
  covers every key this phase adds (entity, device, issues); existing
  config/options keys get their German text in Phase 7 (HA falls back to
  English for missing keys). `icons.json` provides a default icon per
  translation key and state icons for the router/service ENUM sensors and the
  problem aggregates. Every platform module declares `PARALLEL_UPDATES`
  (`0` for sensor and binary_sensor; button `0` or `1`, planner's choice).

### Devices (ENT-03)
- **D-13:** Device topology: main device identifier `(DOMAIN, entry.entry_id)`,
  name `Traefik (<host>)`, `entry_type=DeviceEntryType.SERVICE`,
  `manufacturer="Traefik"` (current value),
  `configuration_url=<entry url>/dashboard/` (no userinfo in the URL),
  `sw_version` = Traefik version. Sub-devices
  `(DOMAIN, f"{entry_id}_routers")`, `_services`, `_certificates`, with
  translated names that include the host (e.g. en "Traefik routers (<host>)").
  Placement: router sensors → Routers, service sensors → Services, cert
  entities → Certificates, everything else → main device.
- **D-14 (link mechanism, HA-version constraint):** `DeviceInfo(via_device=…)`
  exists on HA 2026.3 but triggers `report_usage` on HA 2026.10+ (deprecated,
  removed 2027.8; HA 2026.10 renamed it `via_device_id`). The only API present
  in both is `DeviceRegistry.async_update_device(device_id, via_device_id=…)`.
  Therefore `async_setup_entry` registers the main device and the sub-devices
  once through `dr.async_get_or_create(config_entry_id=..., identifiers=...,
  ...)` **without** any via argument, then links each sub-device with
  `dr.async_update_device(sub.id, via_device_id=main.id)`. Entity `DeviceInfo`
  carries the identifiers (and may repeat the static fields) but never
  `via_device` / `via_device_id`. The ROADMAP/ENT-03 phrase "via `via_device`"
  means this registry link. A test asserts the sub-devices'
  `via_device_id == main.id` and that no deprecation/`report_usage` message
  from this integration is logged on the dev venv (HA 2026.10).
- **D-15:** `sw_version` stays current: when the snapshot's `version.version`
  changes, the main device is updated with `dr.async_update_device(...,
  sw_version=...)` (once per change, not per cycle). Old per-category devices
  (`{entry_id}_{http_routers|http_routers_tls|http_services|http_entrypoints|overview|diagnostics}`)
  are removed once no entity of this entry references them anymore. Verify
  against the HA 2026.3 and 2026.10 sources which order is safe: removing a
  device also removes the entities attached to it, so entities must be
  re-pointed to the new devices (re-add with new `DeviceInfo`, or
  `er.async_update_entity(device_id=...)`) before the old device is removed.
  Use `dr.async_entries_for_config_entry`, never `DeviceEntry.config_entries`
  (deprecation enforced since HA 2026.9).

### Reload removal + refresh button (ENT-07, IN-02)
- **D-16:** Remove `TraefikProxyApiClient.reload_routers`, the
  `reload_routers` admin service and its handler/schema in `__init__.py`,
  `services.yaml`, the `services` section of the translations (if any) and the
  `TraefikProxyReloadButton`. If `async_setup` has nothing left to do it is
  removed together with `CONFIG_SCHEMA` (hassfest requires `CONFIG_SCHEMA`
  only when `async_setup` exists); keep `CONFIG_SCHEMA` if `async_setup`
  stays. IN-02 (verification loop defeated by the debouncer) is closed by
  this removal.
- **D-17:** New `TraefikRefreshButton` (translation key `refresh`, unique_id
  `{entry_id}_refresh`, `EntityCategory.DIAGNOSTIC`, no device class) on the
  main device. `async_press` refreshes **its own entry's** main coordinator and
  cert coordinator (`async_request_refresh()` on both; reading
  `self._entry.runtime_data`), with no service call and no admin check (S-08
  moot). A test with two loaded entries proves the press touches only its own
  entry.

### Migration + repair (ENT-09, M34)
- **D-18:** `config_flow.py` `MINOR_VERSION` 1 → 2 (Phase 7 will bump to 3).
  New `async_migrate_entry` in `__init__.py`: for `version == 1` and
  `minor_version < 2` it removes this entry's `binary_sensor` registry entries
  with unique_id prefix `{entry_id}_http_router_` and the button entry
  `{entry_id}_diagnostics_reload`, clears `disabled_by` on the three problem
  aggregates only where it is `RegistryEntryDisabler.INTEGRATION` (old
  disabled-by-default; user-disabled entries stay disabled), and sets
  `minor_version=2`. Returns `True`; a `version > 1` entry returns `False`
  (downgrade). New entries are created at minor version 2 and skip it.
- **D-19 (M34):** When the migration removed at least one entry it creates one
  repair issue with `ir.async_create_issue(hass, DOMAIN,
  f"entities_migrated_{entry_id}", is_fixable=False, is_persistent=True,
  severity=IssueSeverity.WARNING, translation_key="entities_migrated",
  translation_placeholders={...})` explaining that router binary sensors were
  replaced by router sensors (new entity IDs) and the reload button/service
  were removed. It is **not** deleted on unload; the user dismisses it, and
  `async_remove_entry` deletes it when the entry is removed. Only HA 2026.3
  APIs (no `config_entry_id` on issues, no `async_refresh_issues`). en + de
  `issues.entities_migrated` strings. Tests: migration from 1.1 with old
  entries → entries gone + issue present; fresh entry → no issue; issue
  survives an entry reload; removing the entry deletes the issue.

### Quality gates
- **D-20:** Every plan leaves `pytest`, `ruff check custom_components tests`,
  `ruff format --check custom_components tests` and
  `mypy --strict custom_components/traefik_proxy` green, and the suite also
  passes on the HA 2026.3.0 venv
  (`~/.cache/traefik-proxy-integration/ha2603-venv/bin/python -m pytest -q -o addopts="" tests`).
  No 2026.11-only API (M4). Tests that assert entity IDs, names, devices or
  the removed reload feature are migrated in the **same task** as the code
  change that breaks them — no intermediate commit leaves the suite red.
- **D-21:** Required integration tests (on the real v2.11 and v3.7 fixtures
  where a fixture fits): router `enabled → error` and service server DOWN
  between two refreshes change the entity state on the next cycle; adding a
  router creates its entity without reload; removing a router shows `missing`
  and keeps the registry entry (with a user-set name/area) until 24 h pass
  (freezer), then it is removed; reappearing inside the grace period re-binds
  the same entity; the grace period survives an entry reload; a change to one
  router writes only the affected entities; cert cycles and threshold changes
  log no "does not generate unique IDs" error; per-item option off → only
  aggregate/diagnostic/cert entities exist.

### Claude's Discretion
- Internal structure of the manager (one generic class with kind records vs.
  small per-kind adapters), the deadline mechanism (D-05), the missing-since
  persistence mechanism (D-04), whether `TraefikRuntimeData` gains an
  `entity_manager` field or the manager hangs off the coordinator.
- Exact entity description layout, icon choices, German wording.
- Plan split and wave layout (tracer-first: lead with one end-to-end slice —
  e.g. router ENUM sensor on its sub-device through the manager with
  add/missing/re-bind — before expanding to the other kinds).
- Whether IN-11 (redundant `_coordinator` alias on cert entities) is removed
  naturally by the cert-entity rewrite; if so, say so in the SUMMARY so the
  Phase 8 carry-over can be closed.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Findings and decisions
- `.planning/research/AUDIT-ARCH-PERF-UX.md` — §2.1 A-01..A-04, A-07..A-09,
  A-13, A-14, A-20, A-21; §2.2 P-03, P-04, P-09; §2.3 U-01, U-02, U-04..U-08,
  U-15; §2.6 S-06, S-08; §3 target architecture; §4 proposed entity model.
- `.planning/research/MARKETPLACE-BEST-PRACTICES.md` — §4.3 (entities), §4.5
  (translations), §4.6 (repairs), §5 (HA 2026.x deprecations: DeviceInfo
  dataclass and `via_device` removal 2027.8, `DeviceEntry.config_entries`,
  entity_id mismatch).
- `.planning/ROADMAP.md` — Phase 5 goal, success criteria, carry-over WR-04 /
  WR-05; cross-phase gates.
- `.planning/REQUIREMENTS.md` — ENT-01..ENT-10; "Out of Scope"; "Audit
  traceability".
- `.planning/phases/04-data-layer-correct-lean/04-CONTEXT.md` — D-15 snapshot
  shape; D-17 (entity set unchanged in Phase 4).
- `.planning/phases/04-data-layer-correct-lean/04-REVIEW-DISPOSITION.md` and
  `git show b05c9e5:.planning/phases/04-data-layer-correct-lean/04-REVIEW.md`
  — WR-04, WR-05, IN-02, IN-07 text.
- `.planning/phases/04-data-layer-correct-lean/04-0[1-9]-SUMMARY.md` "Worker
  Decisions" — notably W21/W22 (cert entities bound to the cert coordinator,
  availability tied to the cert cycle) and W23 (`update_entity` on a cert
  entity triggers a cert refresh).

### Code being replaced or adapted
- `custom_components/traefik_proxy/entity.py` — current generic base
  `_TraefikProxyBaseEntity`, per-category devices.
- `custom_components/traefik_proxy/sensor.py`, `binary_sensor.py` — per-item
  entities, aggregates, cert entities, cleanup closures.
- `custom_components/traefik_proxy/button.py`, `__init__.py`,
  `services.yaml`, `api.py` (`reload_routers`) — reload feature.
- `custom_components/traefik_proxy/models.py` — `TraefikSnapshot`, `Status`,
  `StatusCounts`, problem tuples.
- `custom_components/traefik_proxy/cert_coordinator.py` — cert data shape
  (`dict[str, CertInfo | CertError]`).
- `custom_components/traefik_proxy/translations/en.json`, `strings.json`.
- `tests/test_binary_sensor.py`, `tests/test_sensor.py`, `tests/test_init.py`,
  `tests/test_platforms_real_fixtures.py`, `tests/test_sensor_tls.py`,
  `tests/test_binary_sensor_tls_expiring.py`, `tests/test_cert_entity_state.py`,
  `tests/conftest.py`.

### HA API sources (verify before relying on behaviour)
- Dev venv (HA 2026.10.4): `.venv/lib/python3.14/site-packages/homeassistant/helpers/{device_registry,entity_registry,entity_platform,issue_registry}.py`
- Minimum-version venv (HA 2026.3.0): `~/.cache/traefik-proxy-integration/ha2603-venv/lib/python3.14/site-packages/homeassistant/helpers/...`

### Project rules
- `./CLAUDE.md` — stack, "What NOT to use".

</canonical_refs>

<specifics>
## Specific Ideas

- Measured today (audit §0): router `enabled → disabled` stays `on` after
  refresh; new routers/services never created; a cert cycle with 2 hosts logs
  3 "does not generate unique IDs" errors; 600 entities refresh in ~5 ms, so
  correctness, not speed, is the goal.
- Verified in this planning session (dev venv 2026.10.4 vs. ha2603-venv):
  2026.3 `DeviceInfo` has `via_device`, 2026.10 has `via_device_id`;
  `DeviceRegistry.async_get_or_create` accepts `via_device` (2026.3) /
  `via_device_id` (2026.10, `via_device` reported as deprecated);
  `async_update_device(via_device_id=...)` exists in both;
  `ir.async_create_issue` has the same keyword set in both (no
  `config_entry_id`). `ChildDeviceInfo` exists only in 2026.10.
- Large installs: ~150 routers + 150 services produce ~300 per-item entities;
  the per-item option (D-06) keeps them out.

</specifics>

<deferred>
## Deferred Ideas

- `certificates_problem` aggregate, cert ENUM/problem semantics, live
  `days_left`, per-certificate (not per-host) entities — Phase 6.
- Options-form field for the per-item toggle, update-listener removal, full
  German translation of config/options strings, `strings.json` deletion —
  Phase 7.
- `ChildDeviceInfo` / `parent_device_id` once the minimum HA reaches 2026.10+
  (out of scope while the minimum stays 2026.3.0, M4).
- Optional per-service "backend down" binary sensor (audit U-08) — not
  required by ENT-04; the aggregate covers it.

</deferred>

---

*Phase: 05-entity-model-lifecycle*
*Context gathered: 2026-11-14 via PRD Express Path*
