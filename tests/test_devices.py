"""Device topology after setup: legacy cleanup, live sw_version, registry links (D-14, D-15, ENT-03).

Legacy (0.3.0) per-category devices are pre-created before setup. Entries use
minor version 2, so the 1.2 migration does not run. Devices are always found
through ``dr.async_entries_for_config_entry``.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryDisabler, ConfigEntryState
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.traefik_proxy.const import CONF_PER_ITEM_ENTITIES, DOMAIN
from custom_components.traefik_proxy.coordinator import VERSION_RECHECK_INTERVAL
from custom_components.traefik_proxy.entity import TraefikDevice, device_identifier
from custom_components.traefik_proxy.entity_manager import CERT_EXPIRING, ENTRYPOINTS, ROUTERS, SERVICES
from tests.conftest import load_fixture, make_traefik_entry, rawdata_copy, restub_traefik, setup_traefik_entry

pytestmark = pytest.mark.usefixtures("mock_tls_probe")

ENTRY_ID = "device-entry"
OTHER_ENTRY_ID = "other-entry"
LEGACY_SUFFIXES = ("http_routers", "http_routers_tls", "http_services", "http_entrypoints", "overview", "diagnostics")
SERVICE_ENTITY_ID = "sensor.traefik_http_service_whoami_docker"
CERT_HOST = "secure.example.com"
# A unique_id no platform of the integration adds; its entity is never re-pointed.
ORPHAN_SUFFIX = "legacy_orphan"


def _devices(hass: HomeAssistant, entry_id: str) -> dict[tuple[str, str], dr.DeviceEntry]:
    """Return {identifier: device} for every device of a config entry."""
    return {
        identifier: device
        for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry_id)
        for identifier in device.identifiers
    }


def _legacy_identifier(entry_id: str, suffix: str) -> tuple[str, str]:
    return (DOMAIN, f"{entry_id}_{suffix}")


def _create_legacy_devices(hass: HomeAssistant, entry: Any, suffixes: tuple[str, ...]) -> dict[str, str]:
    """Pre-create 0.3.0 per-category devices; return {suffix: device_id}."""
    registry = dr.async_get(hass)
    return {
        suffix: registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={_legacy_identifier(entry.entry_id, suffix)},
            name=f"traefik.example.com Traefik Proxy - {suffix}",
        ).id
        for suffix in suffixes
    }


def _attach(
    hass: HomeAssistant,
    entry: Any,
    domain: str,
    suffix: str,
    device_id: str,
    *,
    object_id: str | None = None,
    disabled_by: er.RegistryEntryDisabler | None = None,
) -> str:
    """Pre-create a registry entry with unique_id ``{entry_id}_{suffix}`` on ``device_id``; return its entity_id."""
    return (
        er.async_get(hass)
        .async_get_or_create(
            domain,
            DOMAIN,
            f"{entry.entry_id}_{suffix}",
            config_entry=entry,
            device_id=device_id,
            suggested_object_id=object_id,
            disabled_by=disabled_by,
        )
        .entity_id
    )


async def test_legacy_devices_removed_after_entities_moved(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """Empty legacy devices are removed; surviving entities keep entity_id and customisations on new devices."""
    entry = make_traefik_entry(entry_id=ENTRY_ID, minor_version=2)
    entry.add_to_hass(hass)
    legacy = _create_legacy_devices(hass, entry, LEGACY_SUFFIXES)
    registry = er.async_get(hass)
    service = _attach(
        hass,
        entry,
        "sensor",
        f"{SERVICES.prefix}whoami@docker",
        legacy["http_services"],
        object_id="traefik_http_service_whoami_docker",
    )
    registry.async_update_entity(service, name="My whoami")
    count = _attach(hass, entry, "sensor", "overview_routers_count", legacy["overview"])
    cert = _attach(hass, entry, CERT_EXPIRING.domain, f"{CERT_EXPIRING.prefix}{CERT_HOST}", legacy["http_routers_tls"])
    entrypoint = _attach(
        hass,
        entry,
        ENTRYPOINTS.domain,
        f"{ENTRYPOINTS.prefix}websecure",
        legacy["http_entrypoints"],
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    orphan = _attach(hass, entry, "sensor", ORPHAN_SUFFIX, legacy["diagnostics"])

    await setup_traefik_entry(hass, aioclient_mock, entry)

    devices = _devices(hass, ENTRY_ID)
    for suffix in ("http_routers", "http_routers_tls", "http_services", "http_entrypoints", "overview"):
        assert _legacy_identifier(ENTRY_ID, suffix) not in devices, suffix
    # The diagnostics device still holds an entity and is kept.
    assert devices[_legacy_identifier(ENTRY_ID, "diagnostics")].id == legacy["diagnostics"]
    orphan_entry = registry.async_get(orphan)
    assert orphan_entry is not None
    assert orphan_entry.device_id == legacy["diagnostics"]

    main = devices[device_identifier(ENTRY_ID, TraefikDevice.MAIN)]
    services = devices[device_identifier(ENTRY_ID, TraefikDevice.SERVICES)]
    certificates = devices[device_identifier(ENTRY_ID, TraefikDevice.CERTIFICATES)]

    service_entry = registry.async_get(SERVICE_ENTITY_ID)
    assert service_entry is not None
    assert service_entry.entity_id == service
    assert service_entry.name == "My whoami"
    assert service_entry.device_id == services.id
    assert hass.states.get(SERVICE_ENTITY_ID) is not None

    count_entry = registry.async_get(count)
    assert count_entry is not None
    assert count_entry.device_id == main.id
    cert_entry = registry.async_get(cert)
    assert cert_entry is not None
    assert cert_entry.device_id == certificates.id
    # A user-disabled entity is re-pointed too and stays disabled.
    entrypoint_entry = registry.async_get(entrypoint)
    assert entrypoint_entry is not None
    assert entrypoint_entry.disabled_by is er.RegistryEntryDisabler.USER
    assert entrypoint_entry.device_id == main.id


@pytest.mark.parametrize(
    "disabled_by",
    [None, er.RegistryEntryDisabler.USER, er.RegistryEntryDisabler.INTEGRATION],
    ids=["enabled", "user-disabled", "integration-disabled"],
)
async def test_legacy_device_with_entity_is_kept(
    hass: HomeAssistant, aioclient_mock: Any, disabled_by: er.RegistryEntryDisabler | None
) -> None:
    """A legacy device whose only entity is not re-pointed is kept, whether that entity is enabled or disabled."""
    entry = make_traefik_entry(entry_id=ENTRY_ID, minor_version=2)
    entry.add_to_hass(hass)
    legacy = _create_legacy_devices(hass, entry, ("http_services",))
    orphan = _attach(hass, entry, "sensor", ORPHAN_SUFFIX, legacy["http_services"], disabled_by=disabled_by)
    er.async_get(hass).async_update_entity(orphan, name="Kept name")

    await setup_traefik_entry(hass, aioclient_mock, entry)

    devices = _devices(hass, ENTRY_ID)
    assert devices[_legacy_identifier(ENTRY_ID, "http_services")].id == legacy["http_services"]
    orphan_entry = er.async_get(hass).async_get(orphan)
    assert orphan_entry is not None
    assert orphan_entry.entity_id == orphan
    assert orphan_entry.name == "Kept name"
    assert orphan_entry.disabled_by is disabled_by
    assert orphan_entry.device_id == legacy["http_services"]


async def test_devices_of_other_entry_untouched(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """Empty legacy-looking devices of another config entry survive this entry's cleanup."""
    other = make_traefik_entry(
        entry_id=OTHER_ENTRY_ID, unique_id="other.example.com", minor_version=2, disabled_by=ConfigEntryDisabler.USER
    )
    other.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    # Identifier built from the entry under test's id, but owned by the other entry.
    lookalike = device_registry.async_get_or_create(
        config_entry_id=OTHER_ENTRY_ID, identifiers={_legacy_identifier(ENTRY_ID, "overview")}
    )
    own_legacy = device_registry.async_get_or_create(
        config_entry_id=OTHER_ENTRY_ID, identifiers={_legacy_identifier(OTHER_ENTRY_ID, "http_services")}
    )
    entry = make_traefik_entry(entry_id=ENTRY_ID, minor_version=2)

    await setup_traefik_entry(hass, aioclient_mock, entry)

    other_devices = _devices(hass, OTHER_ENTRY_ID)
    assert other_devices[_legacy_identifier(ENTRY_ID, "overview")].id == lookalike.id
    assert other_devices[_legacy_identifier(OTHER_ENTRY_ID, "http_services")].id == own_legacy.id


async def test_main_device_sw_version_follows_traefik(hass: HomeAssistant, aioclient_mock: Any, freezer: Any) -> None:
    """One device update with sw_version per Traefik version change; none for other snapshot changes."""
    entry = await setup_traefik_entry(hass, aioclient_mock, make_traefik_entry(entry_id=ENTRY_ID, minor_version=2))
    main = _devices(hass, ENTRY_ID)[device_identifier(ENTRY_ID, TraefikDevice.MAIN)]
    assert main.sw_version == "3.7.19"
    events: list[Event[Any]] = []

    @callback
    def _record(event: Event[Any]) -> None:
        if event.data["action"] == "update" and event.data["device_id"] == main.id:
            events.append(event)

    entry.async_on_unload(hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, _record))
    coordinator = entry.runtime_data.coordinator

    version = dict(load_fixture("v3.7", "version.json"))
    version["Version"] = "3.7.99"
    restub_traefik(aioclient_mock, version_payload=version)
    freezer.tick(VERSION_RECHECK_INTERVAL)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.data.version.version == "3.7.99"
    assert _devices(hass, ENTRY_ID)[device_identifier(ENTRY_ID, TraefikDevice.MAIN)].sw_version == "3.7.99"
    sw_updates = [event for event in events if "sw_version" in event.data["changes"]]
    assert len(sw_updates) == 1
    assert sw_updates[0].data["changes"]["sw_version"] == "3.7.19"

    # A router-only change keeps the version: no further sw_version update.
    rawdata = rawdata_copy()
    rawdata["routers"]["file-ok@file"]["status"] = "disabled"
    restub_traefik(aioclient_mock, version_payload=version, rawdata=rawdata)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.data.routers["file-ok@file"].status == "disabled"
    assert len([event for event in events if "sw_version" in event.data["changes"]]) == 1


async def test_sub_devices_linked_without_deprecation(
    hass: HomeAssistant, aioclient_mock: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """Sub-devices carry via_device_id == main.id; setup and a refresh report no deprecation."""
    caplog.set_level(logging.DEBUG)
    entry = await setup_traefik_entry(hass, aioclient_mock, make_traefik_entry(entry_id=ENTRY_ID, minor_version=2))
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    devices = _devices(hass, ENTRY_ID)
    main = devices[device_identifier(ENTRY_ID, TraefikDevice.MAIN)]
    for sub in (TraefikDevice.ROUTERS, TraefikDevice.SERVICES, TraefikDevice.CERTIFICATES):
        assert devices[device_identifier(ENTRY_ID, sub)].via_device_id == main.id, sub
    for record in caplog.records:
        message = record.getMessage()
        assert "via_device" not in message, message
        assert "report_usage" not in message, message
        assert "Detected that custom integration 'traefik_proxy'" not in message, message


@pytest.mark.parametrize("disabled_by", [None, er.RegistryEntryDisabler.USER], ids=["enabled", "user-disabled"])
async def test_per_item_off_keeps_referenced_sub_device(
    hass: HomeAssistant, aioclient_mock: Any, disabled_by: er.RegistryEntryDisabler | None
) -> None:
    """With per-item entities off, a sub-device another integration's entity uses is kept; an unused one is removed."""
    entry = await setup_traefik_entry(hass, aioclient_mock, make_traefik_entry(entry_id=ENTRY_ID, minor_version=2))
    devices = _devices(hass, ENTRY_ID)
    routers = devices[device_identifier(ENTRY_ID, TraefikDevice.ROUTERS)]
    assert device_identifier(ENTRY_ID, TraefikDevice.SERVICES) in devices
    registry = er.async_get(hass)
    foreign = registry.async_get_or_create(
        "sensor", "derivative", "foreign-helper", device_id=routers.id, disabled_by=disabled_by
    )

    hass.config_entries.async_update_entry(entry, options={CONF_PER_ITEM_ENTITIES: False})
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    devices = _devices(hass, ENTRY_ID)
    assert devices[device_identifier(ENTRY_ID, TraefikDevice.ROUTERS)].id == routers.id
    assert device_identifier(ENTRY_ID, TraefikDevice.SERVICES) not in devices
    foreign_entry = registry.async_get(foreign.entity_id)
    assert foreign_entry is not None
    assert foreign_entry.device_id == routers.id
    assert foreign_entry.disabled_by is disabled_by
    prefixes = (f"{ENTRY_ID}_{ROUTERS.prefix}", f"{ENTRY_ID}_{SERVICES.prefix}")
    assert not [e for e in er.async_entries_for_config_entry(registry, ENTRY_ID) if e.unique_id.startswith(prefixes)]
