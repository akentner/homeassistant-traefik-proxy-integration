"""Config-entry migration 1.1 -> 1.2 and its repair notice (D-18, D-19, ENT-09, M34).

Old (0.3.0) registry entries are pre-created before setup. HA schedules an
entry reload 30 s after the migration clears ``disabled_by`` on an entity, so
no test advances time after setup.
"""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryDisabler, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

import custom_components.traefik_proxy as integration
from custom_components.traefik_proxy.config_flow import TraefikProxyConfigFlow
from custom_components.traefik_proxy.const import (
    DOMAIN,
    UID_MIDDLEWARES_PROBLEM,
    UID_ROUTERS_PROBLEM,
    UID_SERVICES_PROBLEM,
)
from custom_components.traefik_proxy.entity import TraefikDevice, device_identifier
from custom_components.traefik_proxy.entity_manager import CERT_EXPIRING, SERVICES, missing_store_key
from tests.conftest import entity_id_for, make_traefik_entry, setup_traefik_entry, stub_traefik

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
) -> str:
    """Pre-create a registry entry with unique_id ``{entry_id}_{suffix}``; return its entity_id."""
    reg_entry = er.async_get(hass).async_get_or_create(
        domain,
        DOMAIN,
        f"{entry.entry_id}_{suffix}",
        config_entry=entry,
        suggested_object_id=object_id,
        disabled_by=disabled_by,
    )
    return reg_entry.entity_id


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
    assert entry.minor_version == 2
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
    """A 1.1 entry without replaced entries is bumped to 1.2 without a repair issue."""
    entry = make_traefik_entry(entry_id=ENTRY_ID, version=1, minor_version=1)
    await setup_traefik_entry(hass, aioclient_mock, entry)

    assert entry.minor_version == 2
    assert _own_issues(hass) == []


async def test_entry_at_1_2_skips_migration(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """An entry created at minor version 2 keeps a look-alike router binary_sensor and gets no issue."""
    assert (TraefikProxyConfigFlow.VERSION, TraefikProxyConfigFlow.MINOR_VERSION) == (1, 2)
    entry = make_traefik_entry(entry_id=ENTRY_ID, version=1, minor_version=2)
    entry.add_to_hass(hass)
    router = _create(hass, entry, "binary_sensor", "http_router_file-ok@file")

    await setup_traefik_entry(hass, aioclient_mock, entry)

    assert er.async_get(hass).async_get(router) is not None
    assert entry.minor_version == 2
    assert _own_issues(hass) == []


async def test_issue_survives_reload_and_is_deleted_on_remove(
    hass: HomeAssistant, aioclient_mock: Any, hass_storage: dict[str, Any]
) -> None:
    """The repair issue outlives a reload; removing the entry deletes it and the missing-since Store."""
    entry = make_traefik_entry(entry_id=ENTRY_ID, version=1, minor_version=1)
    entry.add_to_hass(hass)
    _create(hass, entry, "button", "diagnostics_reload")
    key = missing_store_key(ENTRY_ID)
    hass_storage[key] = {"version": 1, "minor_version": 1, "key": key, "data": {}}

    await setup_traefik_entry(hass, aioclient_mock, entry)
    assert _get_issue(hass, ENTRY_ID) is not None

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

    hass.config_entries.async_update_entry(entry, minor_version=1)
    assert await integration.async_migrate_entry(hass, entry)

    after_second = {e.entity_id: e for e in er.async_entries_for_config_entry(registry, ENTRY_ID)}
    assert after_second == after_first
    assert entry.minor_version == 2
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
