# Phase 5: Entity model + lifecycle - Pattern Map

**Mapped:** 2026-11-14
**Files analyzed:** 20 (14 source/config, 6+ test files)
**Analogs found:** 18 / 20 (entity_manager.py and de.json have no in-repo analog)

HA versions referenced: dev venv = HA 2026.10 (`.venv/lib/python3.14/site-packages/homeassistant`, abbreviated **N**), minimum venv = HA 2026.3 (`~/.cache/traefik-proxy-integration/ha2603-venv/lib/python3.14/site-packages/homeassistant`, abbreviated **O**). All in-repo analog paths below are git-tracked.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `custom_components/traefik_proxy/entity_manager.py` (new) | service (lifecycle manager) | event-driven (coordinator listener + timer) | `sensor.py:59-191` (cert create/cleanup closures being replaced) | partial (replaces it) |
| `custom_components/traefik_proxy/entity.py` | model/base entity | event-driven | itself `entity.py:42-136` | exact (rewrite) |
| `custom_components/traefik_proxy/sensor.py` | component (entities) | event-driven | itself; HA `sfr_box/sensor.py:38-50` (descriptions + translation_key) | exact |
| `custom_components/traefik_proxy/binary_sensor.py` | component | event-driven | itself `binary_sensor.py:242-356` (3 aggregates to merge) | exact |
| `custom_components/traefik_proxy/button.py` | component | request-response | itself `button.py:31-86` | exact |
| `custom_components/traefik_proxy/__init__.py` | setup/migration | lifecycle | itself `__init__.py:207-276`; HA `niko_home_control/__init__.py:40-67`, `airvisual/__init__.py:290-345` | exact |
| `custom_components/traefik_proxy/data.py` | model | - | itself `data.py:16-30` | exact |
| `custom_components/traefik_proxy/const.py` | config | - | itself `const.py:7-47` | exact |
| `custom_components/traefik_proxy/api.py` | client | - | removal only (`api.py:341` `reload_routers`) | n/a |
| `custom_components/traefik_proxy/config_flow.py` | config flow | - | `config_flow.py:265-266` | exact (one-line) |
| `custom_components/traefik_proxy/services.yaml` | config | - | deleted | n/a |
| `custom_components/traefik_proxy/translations/en.json` + `strings.json` | config (i18n) | - | itself; HA `sfr_box/strings.json` (entity state block) | exact |
| `custom_components/traefik_proxy/translations/de.json` (new) | config (i18n) | - | `translations/en.json` (mirror structure) | role-match |
| `custom_components/traefik_proxy/icons.json` (new) | config | - | HA `sfr_box/icons.json` | exact (HA) |
| `tests/test_platforms_real_fixtures.py` | test | full setup | itself | exact |
| `tests/test_entity_manager.py` / lifecycle tests (new) | test | full setup + freezer | `tests/test_coordinator.py:284-320` + `tests/test_platforms_real_fixtures.py:28-44` | exact |
| `tests/test_init.py` (migration, refresh button, repair) | test | full setup | `tests/test_platforms_real_fixtures.py:28-44` | role-match |
| `tests/test_binary_sensor.py`, `test_sensor.py`, `test_sensor_tls.py`, `test_binary_sensor_tls_expiring.py`, `test_cert_entity_state.py`, `conftest.py` | test | migrate in place | themselves | exact |

## Pattern Assignments

### `entity.py` (base entities, D-07, D-13, D-14)

**Current analog:** `custom_components/traefik_proxy/entity.py`

Generic base to keep (lines 42-75) - PEP-695 generic over the coordinator, `_attr_has_entity_name = True`:
```python
class _TraefikProxyBaseEntity[CoordinatorT: DataUpdateCoordinator[Any]](CoordinatorEntity[CoordinatorT]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: CoordinatorT, entry: TraefikProxyConfigEntry, category: str, *, description_key: str | None = None) -> None:
        super().__init__(coordinator)
        self._entry = entry
```
Two concrete subclasses (lines 107-136) `TraefikProxyEntity` (main coordinator from `entry.runtime_data.coordinator`) and `TraefikProxyCertEntity` (cert coordinator). Keep this shape; replace the `category` argument with a device selector (`main | routers | services | certificates`).

What to replace:
- `device_info` (lines 77-89) builds per-category identifiers `(DOMAIN, f"{entry_id}_{category}")` and a name string. New factory returns `DeviceInfo(identifiers={(DOMAIN, entry_id)})` for main and `{(DOMAIN, f"{entry_id}_routers")}` etc. for sub-devices; never `via_device`/`via_device_id` (D-14).
- `_url_host` (lines 91-98) uses a function-local `urlparse` import and bare `except Exception` - move to module scope; reuse for device names (`Traefik (<host>)`) and `configuration_url` (strip userinfo).
- `_sw_version` (lines 100-104) - keep only for the main device / initial registration; D-15 updates it via `dr.async_update_device`.
- `_router_name` back-compat alias (lines 71-76) - delete.

Change-only write pattern (new, no in-repo analog; HA `CoordinatorEntity._handle_coordinator_update` is the hook to override):
```python
@callback
def _handle_coordinator_update(self) -> None:
    model = self.coordinator.data.routers.get(self._key)
    if model == self._last_model and ...:  # dataclass equality
        return
    self._last_model = model
    self.async_write_ha_state()
```

### `entity_manager.py` (new, D-01..D-06)

**No direct analog.** The code it replaces shows the pieces and the anti-patterns:

Anti-pattern to delete - full-registry scan (`sensor.py:155-167`, same in `sensor.py:106-129`, `binary_sensor.py:91-109`, `145-168`):
```python
for reg_entry in list(registry.entities.values()):      # iterates the whole HA registry (A-14/P-04)
    unique_id = reg_entry.unique_id or ""
    if not unique_id.startswith(prefix):
        continue
    ...
    registry.async_remove(reg_entry.entity_id)           # immediate removal, no grace (WR-04)
```
Replace with `er.async_entries_for_config_entry(registry, entry.entry_id)` (O `helpers/entity_registry.py:1996`, N `:2689`).

Anti-pattern to delete - re-adding known keys every cert cycle (`sensor.py:65-104`, docstring 77-86 explicitly relies on re-adding; this is the WR-05 "does not generate unique IDs" source, raised at O `helpers/entity_platform.py:855-861`, N `:1001-1007`).

Listener registration pattern to keep (`sensor.py:146`, `191`):
```python
entry.async_on_unload(cert_coordinator.async_add_listener(_cert_update_listener))
entry.async_on_unload(coordinator.async_add_listener(_remove_stale_services))
```
Same `entry.async_on_unload(...)` wrapper for the deadline timer (`async_track_time_interval` / `async_call_later`, D-05).

`last_update_success` gate to keep (`sensor.py:154-155`): do not mark keys missing when the cycle failed.

Missing-since persistence (D-04) - HA analog `components/iperf3/sensor.py:40,74-76` (present in both versions):
```python
class Iperf3Sensor(RestoreEntity, SensorEntity):
    ...
        if not (state := await self.async_get_last_state()):
            return
        self._attr_native_value = state.state
```
Read `state.attributes.get("missing_since")` the same way in `async_added_to_hass`.

### `sensor.py` (router/service ENUM, entrypoints, counts, version, start_time, healthy_ratio, cert timestamp)

**Analog:** itself.

Imports (lines 12-31) - keep style (`from __future__ import annotations`, `TYPE_CHECKING` imports of coordinator/data). Drop `slugify` (only used for `self.entity_id`) and `er` (moves to manager).

Per-item key lookup (lines 204-213, 239-247):
```python
self._item_name = service_name
self._attr_unique_id = f"{entry.entry_id}_http_service_{service_name}"
self.entity_id = f"sensor.traefik_http_service_{slugify(service_name)}"   # DELETE (D-08)
self._attr_name = service_name

@property
def _service(self) -> Service:
    return self.coordinator.data.services.get(self._item_name, self._initial_service)
```
New: drop `_initial_service`; a `None` lookup means state `missing`.

Delete redundant availability (lines 232-234, 270-272, 307-309; same in binary_sensor 238, 278, 316, 353):
```python
@property
def available(self) -> bool:
    return self.coordinator.last_update_success
```

Attribute duplication to drop (lines 222-230, 259-268): `name`, `entrypoint_name`, `service_name`, `status`, `server_count`. New service attrs per D-10.

Aggregate count base (lines 275-309, subclasses 380-405) - keep the `_counts()` template-method shape but convert to entity descriptions with `translation_key`, `EntityCategory.DIAGNOSTIC`, `SensorStateClass.MEASUREMENT`.

Entity-description + translation_key HA analog (`components/sfr_box/sensor.py:38-45`):
```python
SFRBoxSensorEntityDescription[DslInfo](
    key="linemode",
    entity_category=EntityCategory.DIAGNOSTIC,
    entity_registry_enabled_default=False,
    translation_key="dsl_linemode",
    value_fn=lambda x: x.linemode,
),
```
ENUM router/service sensor: `_attr_device_class = SensorDeviceClass.ENUM`, `_attr_options = [*(str(s) for s in Status), "missing"]`, `_attr_translation_key = "router"` / `"service"`; `_attr_name = <traefik name>` overrides the translated name (D-08).

Cert timestamp sensor (lines 410-530): drop `_attr_icon = "mdi:certificate"` (icons.json), drop `self.entity_id = ...` (line ~460), drop `self._coordinator` alias (IN-11; use `self.coordinator`).

### `binary_sensor.py` (problem aggregates, cert expiring)

**Analog:** itself, lines 242-356 - three near-identical classes to fold into one class + three descriptions (A-13). Remove `_attr_entity_registry_enabled_default = False` (line ~253) and `self.entity_id = ...`; source tuples are `snapshot.router_problems / service_problems / middleware_problems` (`models.py:173-175`, built at `models.py:196-202`). `TraefikProxyRouterBinarySensor` (lines 189-240) and `_friendly_rule` (lines 33-40) are deleted (routers move to sensor).

### `button.py` (refresh button, D-17)

**Analog:** itself (lines 31-86). Keep `async_setup_entry` shape (lines 31-43). Delete the `ButtonDeviceClass` try/except import (lines 17-20) - no device class needed. New body:
```python
class TraefikRefreshButton(TraefikProxyEntity, ButtonEntity):
    _attr_translation_key = "refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    async def async_press(self) -> None:
        runtime = self._entry.runtime_data
        await runtime.coordinator.async_request_refresh()
        await runtime.cert_coordinator.async_request_refresh()
```
Add `PARALLEL_UPDATES` at module level in all three platform files.

### `__init__.py` (setup, devices, migration, repair, remove)

**Analog:** itself.
- Delete lines 11-14 (`probatio`/`voluptuous` import), 36-164 (`CONFIG_SCHEMA`, `RELOAD_ROUTERS_SCHEMA`, handler, `async_setup`) per D-16, plus imports `asyncio`, `time`, `ServiceCall`, `HomeAssistantError`, `cv`, `async_register_admin_service`, `ConfigEntryState`.
- Setup order (lines 226-253): build runtime data -> first refresh -> cert refresh -> **register devices here** (between line 251 and the `async_forward_entry_setups` at 253) -> forward platforms. Entities then attach to existing devices.

Device registration (new; API valid in O and N):
```python
dev_reg = dr.async_get(hass)
main = dev_reg.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, entry.entry_id)}, ...)
sub = dev_reg.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, f"{entry.entry_id}_routers")}, ...)
dev_reg.async_update_device(sub.id, via_device_id=main.id)
```
O: `async_get_or_create` `helpers/device_registry.py:833` (accepts `via_device`, line 859), `async_update_device` `:1317` (`via_device_id` param line 1345). N: `async_get_or_create` `:2301` (`via_device_id` line 2322; `via_device` -> `report_usage`), `async_update_device` `:3727`.

Migration - HA analog `components/niko_home_control/__init__.py:40-67` (present in O and N):
```python
if config_entry.minor_version < 2:
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, config_entry.entry_id)
    for entry in entries:
        if entry.unique_id.startswith("light-"):
            ...
            registry.async_update_entity(entry.entity_id, new_unique_id=new_unique_id)
    hass.config_entries.async_update_entry(config_entry, minor_version=2)
return True
```
Filter for D-18: `entry.domain == "binary_sensor" and unique_id.startswith(f"{entry_id}_http_router_")`, `unique_id == f"{entry_id}_diagnostics_reload"` -> `registry.async_remove(entity_id)`; problem aggregates with `disabled_by is er.RegistryEntryDisabler.INTEGRATION` -> `async_update_entity(entity_id, disabled_by=None)`. Add `if config_entry.version > 1: return False` first.

Repair issue - HA analog `components/airvisual/__init__.py:28,325-341`:
```python
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue
async_create_issue(
    hass, DOMAIN, f"airvisual_pro_migration_{entry.entry_id}",
    is_fixable=False, is_persistent=True, severity=IssueSeverity.WARNING,
    translation_key="airvisual_pro_migration",
    translation_placeholders={...},
)
```
`async_create_issue` O `helpers/issue_registry.py:331`, N `:339`; `async_delete_issue` O `:407`, N `:415` (same signature) - use in new `async_remove_entry`.

Unload (lines 270-276): keep as is.

### D-15 verified registry behaviour (planner must follow this order)

1. **Removing a device removes its entities (both versions).** `EntityRegistry.async_device_modified` on `action == "remove"`:
   - O `helpers/entity_registry.py:1319-1345`: entities whose `config_entry_id in removed_device_dict["config_entries"]` (and matching subentry) -> `self.async_remove(entity_id)`; others get `device_id=None`.
   - N `helpers/entity_registry.py:1778-1800`: same, but compares `entity.config_entry_id == removed_device_dict["config_entry_id"]` (singular - N device entries carry one `config_entry_id`).
   - Consequence: removing an old per-category device (`{entry_id}_http_services` etc.) while service sensors still point at it **deletes those registry entries** (loses user renames/areas). Re-point first.
2. **Re-adding an entity with a new `DeviceInfo` re-points `device_id` (both versions).** Platform add path resolves the device then calls `entity_registry.async_get_or_create(..., device_id=device.id if device else None, ...)`: O `helpers/entity_platform.py:911-918`, N `:1109-1116`. For an existing unique_id, `async_get_or_create` goes through `_async_update_entity(entity_id, ..., device_id=device_id, ...)`: O `helpers/entity_registry.py:1121-1127`, N around `:1571`. So once the platforms have added all entities with new `DeviceInfo`, every surviving entity is on a new device.
3. **Safe order:** forward platforms (entities re-point) -> then, in `async_setup_entry` after `async_forward_entry_setups`, iterate `dr.async_entries_for_config_entry(dev_reg, entry.entry_id)` (O `helpers/device_registry.py:1730`, N `:4812`) and `async_remove_device` the old-identifier devices that have no entity left (`er.async_entries_for_device(..., include_disabled_entities=True)` empty). Caveat: per-item entities that are not re-added on this setup (missing keys) still point at the old device - the manager must create them on setup (D-04 already requires this) or call `er.async_update_entity(entity_id, device_id=new_id)` before removal.
4. O `async_remove_device` (`helpers/device_registry.py:1435-1460`) also clears `via_device_id` on children; N (`:4175`) additionally removes child devices. Old devices have no children, so no impact.
5. Never read `DeviceEntry.config_entries` (N reports it via `report_usage`, `device_registry.py:1617-1638`).

### `const.py`

Analog lines 7-12 / 45-47. Add `CONF_PER_ITEM_ENTITIES: Final = "per_item_entities"`, `DEFAULT_PER_ITEM_ENTITIES: Final = True`, `MISSING_GRACE_PERIOD: Final = timedelta(hours=24)`. `PLATFORMS` (line 47) may switch to `Platform.SENSOR, ...` enum; order is not semantically relevant.

### `data.py`

Analog lines 16-27: add `entity_manager: TraefikEntityManager` field under the existing `TYPE_CHECKING` import block (lines 10-13).

### `config_flow.py`

Line 266 `MINOR_VERSION = 1` -> `2`.

### `translations/en.json`, `strings.json`, `translations/de.json`

Analog: `translations/en.json` (70 lines; top keys `config`, `options`, `exceptions`). Add `entity.{sensor,binary_sensor,button}.<key>.{name,state}`, `device.{main,routers,services,certificates}.name` with `{host}` placeholder, `issues.entities_migrated.{title,description}`. State block shape (HA `sfr_box/strings.json:53-56`):
```json
"state": { "off": "On-hook", "on": "Off-hook" }
```
**Finding:** `strings.json` is currently NOT byte-identical to `en.json` (line 6: `strings.json` has a literal em dash, `en.json` has `—`). D-12 requires byte identity - plan a `cp` or a test asserting equality.

### `icons.json` (new)

HA analog `components/sfr_box/icons.json` (whole file):
```json
{
  "entity": {
    "binary_sensor": {
      "voip_hook_status": {
        "default": "mdi:phone-hangup",
        "state": { "on": "mdi:phone-in-talk" }
      }
    }
  }
}
```

### Tests

**Full-setup fixture analog** `tests/test_platforms_real_fixtures.py:28-44`:
```python
@pytest.fixture(params=FIXTURE_VERSIONS)
async def loaded(request, hass, aioclient_mock, mock_tls_probe) -> TraefikSnapshot:
    version = request.param
    stub_traefik(aioclient_mock, version=version)
    entry = MockConfigEntry(domain=DOMAIN, title="Traefik",
        data={CONF_URL: MOCK_URL, CONF_API_KEY: "k", CONF_VERIFY_SSL: True},
        unique_id="traefik.example.com")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
```
For migration tests add `version=1, minor_version=1` to `MockConfigEntry` and pre-create registry entries with `er.async_get(hass).async_get_or_create("binary_sensor", DOMAIN, f"{entry.entry_id}_http_router_x", config_entry=entry)` before `async_setup`.

**Change-between-cycles analog** `tests/test_coordinator.py:295-302,316-320`:
```python
aioclient_mock.clear_requests()
stub_traefik(aioclient_mock, version="v3.7", rawdata=modified)   # conftest.py:106-128
freezer.tick(VERSION_RECHECK_INTERVAL)
await coordinator.async_refresh()
```
Use `freezer.tick(MISSING_GRACE_PERIOD + timedelta(seconds=1))` + `async_fire_time_changed(hass)` + `await hass.async_block_till_done()` for the 24 h removal.

Entity IDs in existing tests (`test_platforms_real_fixtures.py:21-25,49-58,66-81,86-91`) are hard-coded `traefik_*` IDs set via `self.entity_id`; after D-08 new installs derive IDs from device name + entity name, so tests should look IDs up via `er.async_get_entity_id(domain, DOMAIN, unique_id)` instead of literal strings.

## Shared Patterns

### Runtime access
**Source:** `data.py:16-30`, `__init__.py:229-233`. Everything reads `entry.runtime_data.{coordinator,cert_coordinator,client}`; the manager joins it there.

### Listener/timer lifetime
**Source:** `sensor.py:146,191`. Always wrap with `entry.async_on_unload(...)`.

### Registry scoping
Only `er.async_entries_for_config_entry` / `dr.async_entries_for_config_entry`; never `registry.entities.values()` and never `DeviceEntry.config_entries`.

### Logging
`_LOGGER = logging.getLogger(__name__)`, debug level only, entity_id in messages (`sensor.py:128,164`). Never log the token or URL userinfo.

### Version-compat imports
`try/except ImportError` shim pattern (`button.py:17-20`, `__init__.py:11-14`) exists for symbols that moved between 2026.3 and 2026.10; reuse only if a needed symbol differs (none identified for this phase after removing `ButtonDeviceClass` and `vol`).

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `entity_manager.py` | service | event-driven + timer | No grace-period lifecycle manager exists in repo; build from D-01..D-06, using registry/listener excerpts above |
| `translations/de.json` | i18n | - | No German file yet; mirror `en.json` key structure for new keys only |

## Metadata

**Analog search scope:** `custom_components/traefik_proxy/`, `tests/`, HA components in N (`niko_home_control`, `airvisual`, `sfr_box`, `iperf3`, all confirmed present in O), HA helpers `device_registry.py`, `entity_registry.py`, `entity_platform.py`, `issue_registry.py` in N and O.
**Files scanned:** ~25
**Pattern extraction date:** 2026-11-14
