"""Config-entry migrations 1.1 -> 1.2 (registry, repair notice) and 1.2 -> 1.3 (entry data).

Old (0.3.0) registry entries are pre-created before setup. HA schedules an
entry reload 30 s after the migration clears ``disabled_by`` on an entity, so
no test advances time after setup.
"""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryDisabler, ConfigEntryState
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

import custom_components.traefik_proxy as integration
from custom_components.traefik_proxy.config_flow import TraefikProxyConfigFlow
from custom_components.traefik_proxy.const import (
    CONF_API_KEY,
    CONF_URL,
    CONF_VERIFY_SSL,
    DOMAIN,
    UID_MIDDLEWARES_PROBLEM,
    UID_ROUTERS_PROBLEM,
    UID_SERVICES_PROBLEM,
)
from custom_components.traefik_proxy.coordinator import VERSION_RECHECK_INTERVAL
from custom_components.traefik_proxy.entity import TraefikDevice, device_identifier
from custom_components.traefik_proxy.entity_manager import CERT_EXPIRING, SERVICES, missing_store_key
from tests.conftest import (
    AUTH_TYPE,
    MOCK_URL,
    entity_id_for,
    load_fixture,
    make_traefik_entry,
    restub_traefik,
    setup_traefik_entry,
    stub_traefik,
)

pytestmark = pytest.mark.usefixtures("mock_tls_probe")

ENTRY_ID = "legacy-entry"
OTHER_ENTRY_ID = "other-entry"
SERVICE_ENTITY_ID = "sensor.traefik_http_service_whoami_docker"
CERT_HOST = "secure.example.com"


def _issue_id(entry_id: str) -> str:
    return f"entities_migrated_{entry_id}"


def _get_issue(hass: HomeAssistant, entry_id: str) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, _issue_id(entry_id))


def _own_issues(hass: HomeAssistant) -> list[ir.IssueEntry]:
    return [issue for (domain, _), issue in ir.async_get(hass).issues.items() if domain == DOMAIN]


def _create(
    hass: HomeAssistant,
    entry: Any,
    domain: str,
    suffix: str,
    *,
    object_id: str | None = None,
    disabled_by: er.RegistryEntryDisabler | None = None,
    device_id: str | None = None,
) -> str:
    """Pre-create a registry entry with unique_id ``{entry_id}_{suffix}``; return its entity_id."""
    reg_entry = er.async_get(hass).async_get_or_create(
        domain,
        DOMAIN,
        f"{entry.entry_id}_{suffix}",
        config_entry=entry,
        suggested_object_id=object_id,
        disabled_by=disabled_by,
        device_id=device_id,
    )
    return reg_entry.entity_id


def _disabled_legacy_device(hass: HomeAssistant, entry: Any, suffix: str = "http_routers") -> str:
    """Pre-create one of the entry's 0.3.0 per-category devices, disabled by the user; return its id."""
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{entry.entry_id}_{suffix}")},
        name=f"traefik.example.com Traefik Proxy - {suffix}",
    )
    device_registry.async_update_device(device.id, disabled_by=dr.DeviceEntryDisabler.USER)
    return device.id


def _entries(registry: er.EntityRegistry, *entry_ids: str) -> dict[str, er.RegistryEntry]:
    """Return {entity_id: registry entry} for every entity of the given config entries."""
    return {
        reg_entry.entity_id: reg_entry
        for entry_id in entry_ids
        for reg_entry in er.async_entries_for_config_entry(registry, entry_id)
    }


def _device(hass: HomeAssistant, entry_id: str, device: TraefikDevice) -> dr.DeviceEntry:
    """Return the current ``device`` of a config entry."""
    return next(
        reg_device
        for reg_device in dr.async_entries_for_config_entry(dr.async_get(hass), entry_id)
        if device_identifier(entry_id, device) in reg_device.identifiers
    )


def _legacy_registry(hass: HomeAssistant, entry: Any) -> dict[str, str]:
    """Pre-create the 0.3.0 registry entries of ``entry``; return {name: entity_id}."""
    return {
        "router_a": _create(hass, entry, "binary_sensor", "http_router_file-ok@file"),
        "router_b": _create(hass, entry, "binary_sensor", "http_router_whoami@docker"),
        "reload": _create(hass, entry, "button", "diagnostics_reload"),
        "routers_problem": _create(
            hass, entry, "binary_sensor", UID_ROUTERS_PROBLEM, disabled_by=er.RegistryEntryDisabler.INTEGRATION
        ),
        "middlewares_problem": _create(
            hass, entry, "binary_sensor", UID_MIDDLEWARES_PROBLEM, disabled_by=er.RegistryEntryDisabler.INTEGRATION
        ),
        "services_problem": _create(
            hass, entry, "binary_sensor", UID_SERVICES_PROBLEM, disabled_by=er.RegistryEntryDisabler.USER
        ),
        "service": _create(
            hass,
            entry,
            "sensor",
            f"{SERVICES.prefix}whoami@docker",
            object_id="traefik_http_service_whoami_docker",
        ),
        "cert": _create(hass, entry, CERT_EXPIRING.domain, f"{CERT_EXPIRING.prefix}{CERT_HOST}"),
    }


async def test_migration_from_1_1(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """A 0.3.0 entry loses the replaced entries, keeps user choices and gets one repair issue."""
    entry = make_traefik_entry(entry_id=ENTRY_ID, version=1, minor_version=1)
    entry.add_to_hass(hass)
    ids = _legacy_registry(hass, entry)
    registry = er.async_get(hass)
    registry.async_update_entity(ids["service"], name="My whoami")
    # A second entry with look-alike entries stays untouched. It is disabled, so
    # setting up the integration does not set it up (and migrate it) as well.
    other = make_traefik_entry(
        entry_id=OTHER_ENTRY_ID,
        unique_id="other.example.com",
        version=1,
        minor_version=1,
        disabled_by=ConfigEntryDisabler.USER,
    )
    other.add_to_hass(hass)
    other_router = _create(hass, other, "binary_sensor", "http_router_file-ok@file")
    other_problem = _create(
        hass, other, "binary_sensor", UID_ROUTERS_PROBLEM, disabled_by=er.RegistryEntryDisabler.INTEGRATION
    )

    await setup_traefik_entry(hass, aioclient_mock, entry)

    for name in ("router_a", "router_b", "reload"):
        assert registry.async_get(ids[name]) is None, name
    # 1.1 reaches 1.3 in one setup.
    assert entry.minor_version == 3
    assert dict(entry.data) == {CONF_URL: MOCK_URL, CONF_VERIFY_SSL: True, AUTH_TYPE: "bearer", CONF_TOKEN: "k"}
    for name in ("routers_problem", "middlewares_problem"):
        reg_entry = registry.async_get(ids[name])
        assert reg_entry is not None
        assert reg_entry.disabled_by is None
        assert hass.states.get(ids[name]) is not None
    services_problem = registry.async_get(ids["services_problem"])
    assert services_problem is not None
    assert services_problem.disabled_by is er.RegistryEntryDisabler.USER
    assert hass.states.get(ids["services_problem"]) is None

    service = registry.async_get(ids["service"])
    assert service is not None
    assert service.entity_id == SERVICE_ENTITY_ID
    assert service.name == "My whoami"
    assert hass.states.get(SERVICE_ENTITY_ID) is not None
    assert registry.async_get(ids["cert"]) is not None

    issue = _get_issue(hass, ENTRY_ID)
    assert issue is not None
    assert issue.is_fixable is False
    assert issue.is_persistent is True
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.translation_key == "entities_migrated"
    assert issue.translation_placeholders == {"entry_title": "Traefik", "removed_count": "3"}
    assert len(_own_issues(hass)) == 1

    # The other entry was not migrated and kept everything.
    assert other.minor_version == 1
    assert registry.async_get(other_router) is not None
    other_reg = registry.async_get(other_problem)
    assert other_reg is not None
    assert other_reg.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert _get_issue(hass, OTHER_ENTRY_ID) is None


async def test_migration_without_old_entries(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """A 1.1 entry without replaced entries is bumped to 1.3 without a repair issue."""
    entry = make_traefik_entry(entry_id=ENTRY_ID, version=1, minor_version=1)
    await setup_traefik_entry(hass, aioclient_mock, entry)

    assert entry.minor_version == 3
    assert _own_issues(hass) == []


async def test_entry_at_1_2_skips_migration(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """An entry at minor version 2 skips the 1.2 step: it keeps a look-alike router binary_sensor and gets no issue."""
    assert (TraefikProxyConfigFlow.VERSION, TraefikProxyConfigFlow.MINOR_VERSION) == (1, 3)
    entry = make_traefik_entry(entry_id=ENTRY_ID, version=1, minor_version=2)
    entry.add_to_hass(hass)
    router = _create(hass, entry, "binary_sensor", "http_router_file-ok@file")

    await setup_traefik_entry(hass, aioclient_mock, entry)

    assert er.async_get(hass).async_get(router) is not None
    assert entry.minor_version == 3
    assert _own_issues(hass) == []


async def test_issue_survives_reload_and_is_deleted_on_remove(
    hass: HomeAssistant, aioclient_mock: Any, hass_storage: dict[str, Any]
) -> None:
    """The entry-bound repair issue outlives reload and unload; Home Assistant deletes it with the entry."""
    entry = make_traefik_entry(entry_id=ENTRY_ID, version=1, minor_version=1)
    entry.add_to_hass(hass)
    _create(hass, entry, "button", "diagnostics_reload")
    key = missing_store_key(ENTRY_ID)
    hass_storage[key] = {"version": 1, "minor_version": 1, "key": key, "data": {}}

    await setup_traefik_entry(hass, aioclient_mock, entry)
    issue = _get_issue(hass, ENTRY_ID)
    assert issue is not None
    assert issue.config_entry_id == ENTRY_ID
    assert issue.is_persistent is True

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert _get_issue(hass, ENTRY_ID) is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert _get_issue(hass, ENTRY_ID) is not None

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert _get_issue(hass, ENTRY_ID) is None
    assert key not in hass_storage


async def test_downgrade_fails_and_keeps_registry(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """An entry written by a newer major version fails migration and leaves the registry alone."""
    stub_traefik(aioclient_mock)
    entry = make_traefik_entry(entry_id=ENTRY_ID, version=2, minor_version=1)
    entry.add_to_hass(hass)
    router = _create(hass, entry, "binary_sensor", "http_router_file-ok@file")
    reload_button = _create(hass, entry, "button", "diagnostics_reload")
    problem = _create(
        hass, entry, "binary_sensor", UID_ROUTERS_PROBLEM, disabled_by=er.RegistryEntryDisabler.INTEGRATION
    )

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.MIGRATION_ERROR
    registry = er.async_get(hass)
    assert registry.async_get(router) is not None
    assert registry.async_get(reload_button) is not None
    problem_entry = registry.async_get(problem)
    assert problem_entry is not None
    assert problem_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert (entry.version, entry.minor_version) == (2, 1)
    assert _own_issues(hass) == []


async def test_downgrade_direct_call_returns_false(hass: HomeAssistant) -> None:
    """Called directly, the migration refuses an entry from a newer major version and leaves it unchanged."""
    entry = make_traefik_entry(entry_id=ENTRY_ID, version=2, minor_version=1)
    entry.add_to_hass(hass)

    assert await integration.async_migrate_entry(hass, entry) is False
    assert (entry.version, entry.minor_version) == (2, 1)
    assert _own_issues(hass) == []


async def test_migration_is_idempotent(hass: HomeAssistant) -> None:
    """A second migration run on a partially migrated entry removes nothing and keeps one issue."""
    entry = make_traefik_entry(entry_id=ENTRY_ID, version=1, minor_version=1)
    entry.add_to_hass(hass)
    _legacy_registry(hass, entry)
    registry = er.async_get(hass)

    assert await integration.async_migrate_entry(hass, entry)
    after_first = {e.entity_id: e for e in er.async_entries_for_config_entry(registry, ENTRY_ID)}
    first_issue = _get_issue(hass, ENTRY_ID)
    assert first_issue is not None
    assert first_issue.translation_placeholders == {"entry_title": "Traefik", "removed_count": "3"}

    data_after_first = dict(entry.data)
    assert data_after_first == {CONF_URL: MOCK_URL, CONF_VERIFY_SSL: True, AUTH_TYPE: "bearer", CONF_TOKEN: "k"}
    hass.config_entries.async_update_entry(entry, minor_version=1)
    assert await integration.async_migrate_entry(hass, entry)

    after_second = {e.entity_id: e for e in er.async_entries_for_config_entry(registry, ENTRY_ID)}
    assert after_second == after_first
    assert entry.minor_version == 3
    assert dict(entry.data) == data_after_first
    assert len(_own_issues(hass)) == 1
    issue = _get_issue(hass, ENTRY_ID)
    assert issue is not None
    assert issue.translation_placeholders == {"entry_title": "Traefik", "removed_count": "3"}


async def test_user_disabled_router_stays_disabled(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """A user-disabled 0.3.0 router binary sensor comes back as a user-disabled router sensor without state."""
    entry = make_traefik_entry(entry_id=ENTRY_ID, version=1, minor_version=1)
    entry.add_to_hass(hass)
    disabled_old = _create(
        hass,
        entry,
        "binary_sensor",
        "http_router_file-ok@file",
        object_id="traefik_http_router_file_ok_file",
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    enabled_old = _create(
        hass, entry, "binary_sensor", "http_router_whoami@docker", object_id="traefik_http_router_whoami_docker"
    )
    registry = er.async_get(hass)

    await setup_traefik_entry(hass, aioclient_mock, entry)

    assert registry.async_get(disabled_old) is None
    assert registry.async_get(enabled_old) is None
    routers = next(
        device
        for device in dr.async_entries_for_config_entry(dr.async_get(hass), ENTRY_ID)
        if device_identifier(ENTRY_ID, TraefikDevice.ROUTERS) in device.identifiers
    )

    disabled_id = entity_id_for(hass, "sensor", f"{ENTRY_ID}_http_router_file-ok@file")
    assert disabled_id == "sensor.traefik_http_router_file_ok_file"
    disabled = registry.async_get(disabled_id)
    assert disabled is not None
    assert disabled.disabled_by is er.RegistryEntryDisabler.USER
    assert disabled.name is None
    assert disabled.device_id == routers.id
    assert hass.states.get(disabled_id) is None

    enabled_id = entity_id_for(hass, "sensor", f"{ENTRY_ID}_http_router_whoami@docker")
    enabled = registry.async_get(enabled_id)
    assert enabled is not None
    assert enabled.disabled_by is None
    assert hass.states.get(enabled_id) is not None

    issue = _get_issue(hass, ENTRY_ID)
    assert issue is not None
    assert issue.translation_placeholders == {"entry_title": "Traefik", "removed_count": "2"}


@pytest.mark.parametrize(
    ("old_disabled_by", "expected"),
    [
        pytest.param(er.RegistryEntryDisabler.USER, er.RegistryEntryDisabler.USER, id="user"),
        pytest.param(er.RegistryEntryDisabler.DEVICE, er.RegistryEntryDisabler.USER, id="device"),
        pytest.param(
            er.RegistryEntryDisabler.INTEGRATION,
            er.RegistryEntryDisabler.INTEGRATION,
            id="integration",
        ),
        pytest.param(None, None, id="enabled"),
    ],
)
async def test_disabled_router_replacement_keeps_disabled_state(
    hass: HomeAssistant,
    aioclient_mock: Any,
    old_disabled_by: er.RegistryEntryDisabler | None,
    expected: er.RegistryEntryDisabler | None,
) -> None:
    """Each way a 0.3.0 router was disabled carries over to its replacement; names do not carry over."""
    entry = make_traefik_entry(entry_id=ENTRY_ID, version=1, minor_version=1)
    entry.add_to_hass(hass)
    device_id = _disabled_legacy_device(hass, entry) if old_disabled_by is er.RegistryEntryDisabler.DEVICE else None
    old = _create(
        hass,
        entry,
        "binary_sensor",
        "http_router_file-ok@file",
        object_id="traefik_http_router_file_ok_file",
        disabled_by=old_disabled_by,
        device_id=device_id,
    )
    registry = er.async_get(hass)
    registry.async_update_entity(old, name="Noisy router")

    await setup_traefik_entry(hass, aioclient_mock, entry)

    assert registry.async_get(old) is None
    replacement_id = entity_id_for(hass, "sensor", f"{ENTRY_ID}_http_router_file-ok@file")
    replacement = registry.async_get(replacement_id)
    assert replacement is not None
    assert replacement.disabled_by is expected
    assert replacement.name is None
    if expected is None:
        assert replacement_id != "sensor.traefik_http_router_file_ok_file"
        assert hass.states.get(replacement_id) is not None
    else:
        assert replacement_id == "sensor.traefik_http_router_file_ok_file"
        assert hass.states.get(replacement_id) is None
    if old_disabled_by is er.RegistryEntryDisabler.DEVICE:
        legacy = (DOMAIN, f"{ENTRY_ID}_http_routers")
        assert all(
            legacy not in device.identifiers
            for device in dr.async_entries_for_config_entry(dr.async_get(hass), ENTRY_ID)
        )


@pytest.mark.parametrize(
    ("old_disabled_by", "hidden_by"),
    [
        pytest.param(None, er.RegistryEntryHider.USER, id="enabled-user"),
        pytest.param(er.RegistryEntryDisabler.USER, er.RegistryEntryHider.USER, id="disabled-user"),
        pytest.param(None, er.RegistryEntryHider.INTEGRATION, id="enabled-integration"),
    ],
)
async def test_hidden_router_replacement_stays_hidden(
    hass: HomeAssistant,
    aioclient_mock: Any,
    old_disabled_by: er.RegistryEntryDisabler | None,
    hidden_by: er.RegistryEntryHider,
) -> None:
    """A hidden 0.3.0 router comes back hidden with the old object id; a visible one stays visible."""
    entry = make_traefik_entry(entry_id=ENTRY_ID, version=1, minor_version=1)
    entry.add_to_hass(hass)
    hidden_old = _create(
        hass,
        entry,
        "binary_sensor",
        "http_router_file-ok@file",
        object_id="traefik_http_router_file_ok_file",
        disabled_by=old_disabled_by,
    )
    registry = er.async_get(hass)
    registry.async_update_entity(hidden_old, hidden_by=hidden_by)
    _create(hass, entry, "binary_sensor", "http_router_whoami@docker", object_id="traefik_http_router_whoami_docker")

    await setup_traefik_entry(hass, aioclient_mock, entry)

    assert registry.async_get(hidden_old) is None
    replacement_id = entity_id_for(hass, "sensor", f"{ENTRY_ID}_http_router_file-ok@file")
    assert replacement_id == "sensor.traefik_http_router_file_ok_file"
    replacement = registry.async_get(replacement_id)
    assert replacement is not None
    assert replacement.hidden_by is hidden_by
    assert replacement.disabled_by is old_disabled_by
    assert replacement.device_id == _device(hass, ENTRY_ID, TraefikDevice.ROUTERS).id
    assert (hass.states.get(replacement_id) is None) is (old_disabled_by is not None)

    visible_id = entity_id_for(hass, "sensor", f"{ENTRY_ID}_http_router_whoami@docker")
    assert visible_id != "sensor.traefik_http_router_whoami_docker"
    visible = registry.async_get(visible_id)
    assert visible is not None
    assert visible.hidden_by is None
    assert visible.disabled_by is None

    issue = _get_issue(hass, ENTRY_ID)
    assert issue is not None
    assert issue.translation_placeholders == {"entry_title": "Traefik", "removed_count": "2"}


async def test_migration_with_disabled_routers_is_idempotent(hass: HomeAssistant) -> None:
    """A second run with the disabled replacements present changes no registry entry and keeps one issue."""
    entry = make_traefik_entry(entry_id=ENTRY_ID, version=1, minor_version=1)
    entry.add_to_hass(hass)
    legacy_device = _disabled_legacy_device(hass, entry)
    _create(hass, entry, "binary_sensor", "http_router_file-ok@file", disabled_by=er.RegistryEntryDisabler.USER)
    _create(
        hass,
        entry,
        "binary_sensor",
        "http_router_whoami@docker",
        disabled_by=er.RegistryEntryDisabler.DEVICE,
        device_id=legacy_device,
    )
    _create(hass, entry, "binary_sensor", "http_router_secure@file", disabled_by=er.RegistryEntryDisabler.INTEGRATION)
    _create(hass, entry, "binary_sensor", "http_router_chain-router@file")
    registry = er.async_get(hass)

    assert await integration.async_migrate_entry(hass, entry)
    expected = {
        "file-ok@file": er.RegistryEntryDisabler.USER,
        "whoami@docker": er.RegistryEntryDisabler.USER,
        "secure@file": er.RegistryEntryDisabler.INTEGRATION,
    }
    for key, disabled_by in expected.items():
        entity_id = entity_id_for(hass, "sensor", f"{ENTRY_ID}_http_router_{key}")
        reg_entry = registry.async_get(entity_id)
        assert reg_entry is not None
        assert reg_entry.disabled_by is disabled_by, key
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{ENTRY_ID}_http_router_chain-router@file") is None
    after_first = {e.entity_id: e for e in er.async_entries_for_config_entry(registry, ENTRY_ID)}
    first_issue = _get_issue(hass, ENTRY_ID)
    assert first_issue is not None
    assert first_issue.translation_placeholders == {"entry_title": "Traefik", "removed_count": "4"}

    hass.config_entries.async_update_entry(entry, minor_version=1)
    assert await integration.async_migrate_entry(hass, entry)

    after_second = {e.entity_id: e for e in er.async_entries_for_config_entry(registry, ENTRY_ID)}
    assert after_second == after_first
    assert len(_own_issues(hass)) == 1
    issue = _get_issue(hass, ENTRY_ID)
    assert issue is not None
    assert issue.translation_placeholders == {"entry_title": "Traefik", "removed_count": "4"}


async def test_device_disabled_entities_stay_disabled_after_device_updates(
    hass: HomeAssistant, aioclient_mock: Any, freezer: Any
) -> None:
    """Entities disabled through a 0.3.0 device stay disabled (by the user) when their new device is updated."""
    entry = make_traefik_entry(entry_id=ENTRY_ID, version=1, minor_version=1)
    entry.add_to_hass(hass)
    by_device = er.RegistryEntryDisabler.DEVICE
    ids = {
        "service": _create(
            hass,
            entry,
            "sensor",
            f"{SERVICES.prefix}whoami@docker",
            disabled_by=by_device,
            device_id=_disabled_legacy_device(hass, entry, "http_services"),
        ),
        "aggregate": _create(
            hass,
            entry,
            "binary_sensor",
            UID_ROUTERS_PROBLEM,
            disabled_by=by_device,
            device_id=_disabled_legacy_device(hass, entry, "diagnostics"),
        ),
        "cert": _create(
            hass,
            entry,
            CERT_EXPIRING.domain,
            f"{CERT_EXPIRING.prefix}{CERT_HOST}",
            disabled_by=by_device,
            device_id=_disabled_legacy_device(hass, entry, "http_routers_tls"),
        ),
    }
    new_device = {
        "service": TraefikDevice.SERVICES,
        "aggregate": TraefikDevice.MAIN,
        "cert": TraefikDevice.CERTIFICATES,
    }
    registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    await setup_traefik_entry(hass, aioclient_mock, entry)

    for name, entity_id in ids.items():
        reg_entry = registry.async_get(entity_id)
        assert reg_entry is not None
        assert reg_entry.disabled_by is er.RegistryEntryDisabler.USER, name
        assert reg_entry.device_id == _device(hass, ENTRY_ID, new_device[name]).id, name
        assert hass.states.get(entity_id) is None, name
    legacy = {(DOMAIN, f"{ENTRY_ID}_{suffix}") for suffix in ("http_services", "diagnostics", "http_routers_tls")}
    assert not any(
        device.identifiers & legacy for device in dr.async_entries_for_config_entry(device_registry, ENTRY_ID)
    )

    # A Traefik upgrade updates the main device; renaming updates the sub-devices.
    version = dict(load_fixture("v3.7", "version.json"))
    version["Version"] = "3.7.99"
    restub_traefik(aioclient_mock, version_payload=version)
    freezer.tick(VERSION_RECHECK_INTERVAL)
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _device(hass, ENTRY_ID, TraefikDevice.MAIN).sw_version == "3.7.99"
    for device in (TraefikDevice.SERVICES, TraefikDevice.CERTIFICATES):
        device_registry.async_update_device(_device(hass, ENTRY_ID, device).id, name_by_user=f"My {device}")
    await hass.async_block_till_done()

    for name, entity_id in ids.items():
        reg_entry = registry.async_get(entity_id)
        assert reg_entry is not None
        assert reg_entry.disabled_by is er.RegistryEntryDisabler.USER, name
        assert hass.states.get(entity_id) is None, name


async def test_device_disabled_mapping_is_scoped_and_idempotent(hass: HomeAssistant) -> None:
    """Only this entry's entities on its legacy devices change; other entries and devices keep DEVICE; a rerun is a no-op."""
    by_device = er.RegistryEntryDisabler.DEVICE
    entry = make_traefik_entry(entry_id=ENTRY_ID, version=1, minor_version=1)
    entry.add_to_hass(hass)
    other = make_traefik_entry(entry_id=OTHER_ENTRY_ID, unique_id="other.example.com", version=1, minor_version=1)
    other.add_to_hass(hass)
    own_legacy = _disabled_legacy_device(hass, entry, "http_services")
    other_legacy = _disabled_legacy_device(hass, other, "http_services")
    # A disabled device with the current main identifier (an install older than 0.3.0) is not a legacy device.
    device_registry = dr.async_get(hass)
    main = device_registry.async_get_or_create(
        config_entry_id=ENTRY_ID, identifiers={device_identifier(ENTRY_ID, TraefikDevice.MAIN)}
    )
    device_registry.async_update_device(main.id, disabled_by=dr.DeviceEntryDisabler.USER)
    service = _create(
        hass, entry, "sensor", f"{SERVICES.prefix}whoami@docker", disabled_by=by_device, device_id=own_legacy
    )
    on_main = _create(hass, entry, "sensor", "http_entrypoint_web", disabled_by=by_device, device_id=main.id)
    other_on_own_legacy = _create(
        hass, other, "sensor", f"{SERVICES.prefix}whoami@docker", disabled_by=by_device, device_id=own_legacy
    )
    other_on_other_legacy = _create(
        hass, other, "sensor", f"{SERVICES.prefix}api@internal", disabled_by=by_device, device_id=other_legacy
    )
    registry = er.async_get(hass)

    assert await integration.async_migrate_entry(hass, entry)

    expected = {
        service: er.RegistryEntryDisabler.USER,
        on_main: by_device,
        other_on_own_legacy: by_device,
        other_on_other_legacy: by_device,
    }
    for entity_id, disabled_by in expected.items():
        reg_entry = registry.async_get(entity_id)
        assert reg_entry is not None
        assert reg_entry.disabled_by is disabled_by, entity_id
    after_first = _entries(registry, ENTRY_ID, OTHER_ENTRY_ID)
    assert _get_issue(hass, ENTRY_ID) is None

    hass.config_entries.async_update_entry(entry, minor_version=1)
    assert await integration.async_migrate_entry(hass, entry)

    assert _entries(registry, ENTRY_ID, OTHER_ENTRY_ID) == after_first
    assert other.minor_version == 1


# ----------------------- 1.2 -> 1.3: entry data -----------------------


@pytest.mark.parametrize(
    ("legacy", "expected"),
    [
        pytest.param({CONF_API_KEY: "k"}, {AUTH_TYPE: "bearer", CONF_TOKEN: "k"}, id="token"),
        pytest.param({CONF_API_KEY: ""}, {AUTH_TYPE: "none"}, id="empty-token"),
        pytest.param({}, {AUTH_TYPE: "none"}, id="no-token"),
    ],
)
async def test_migration_1_2_maps_api_key_to_auth_type(
    hass: HomeAssistant, legacy: dict[str, Any], expected: dict[str, Any]
) -> None:
    """A 1.2 entry's api_key becomes bearer + token (non-empty) or auth type none; api_key is removed."""
    entry = make_traefik_entry(
        entry_id=ENTRY_ID, minor_version=2, data={CONF_URL: MOCK_URL, CONF_VERIFY_SSL: False, **legacy}
    )
    entry.add_to_hass(hass)

    assert await integration.async_migrate_entry(hass, entry)

    assert entry.minor_version == 3
    assert dict(entry.data) == {CONF_URL: MOCK_URL, CONF_VERIFY_SSL: False, **expected}


async def test_migration_1_2_keeps_existing_auth_type(hass: HomeAssistant) -> None:
    """An entry that already has an auth type keeps its auth keys (re-run after a reset minor version)."""
    data = {CONF_URL: MOCK_URL, CONF_VERIFY_SSL: True, AUTH_TYPE: "basic", "username": "admin", "password": "s3cret"}
    entry = make_traefik_entry(entry_id=ENTRY_ID, minor_version=2, data=data)
    entry.add_to_hass(hass)

    assert await integration.async_migrate_entry(hass, entry)
    hass.config_entries.async_update_entry(entry, minor_version=2)
    assert await integration.async_migrate_entry(hass, entry)

    assert entry.minor_version == 3
    assert dict(entry.data) == data


async def test_migrated_token_entry_loads_with_bearer_header(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """A migrated 0.3.0 token entry loads and sends its token as a bearer header."""
    entry = await setup_traefik_entry(hass, aioclient_mock, make_traefik_entry(entry_id=ENTRY_ID, minor_version=2))

    assert entry.minor_version == 3
    versions = [call for call in aioclient_mock.mock_calls if str(call[1]).endswith("/api/version")]
    assert versions
    assert all((call[3] or {}).get("Authorization") == "Bearer k" for call in versions)
