"""Tests for the package module and the "Refresh now" button.

Covers:
- the integration registers no service; the package module has neither
  ``async_setup`` nor ``CONFIG_SCHEMA`` (D-16, ENT-07)
- the refresh button's registry entry: unique_id, diagnostic category, no
  device class, main device (D-17, ENT-08)
- with two loaded entries a press refreshes only its own entry's two
  coordinators (D-17, A-09, S-08)
- setup, refreshes and a real press send only GET requests to Traefik (ENT-07)
- the options update listener stays registered once across reloads, runs once
  per options change and is removed on unload (ENT-09)
"""

from __future__ import annotations

import importlib
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EntityCategory
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.traefik_proxy.const import CONF_API_KEY, CONF_SCAN_INTERVAL, CONF_URL, CONF_VERIFY_SSL, DOMAIN
from custom_components.traefik_proxy.coordinator import build_api_client
from custom_components.traefik_proxy.entity import TraefikDevice, device_identifier
from tests.conftest import entity_id_for, make_traefik_entry, setup_traefik_entry, stub_traefik

SECOND_URL = "https://traefik2.example.com:8080"


def _refresh_unique_id(entry_id: str) -> str:
    return f"{entry_id}_refresh"


async def test_no_service_registered(hass, aioclient_mock, mock_tls_probe) -> None:  # type: ignore[no-untyped-def]
    """After setup the integration owns no service."""
    await setup_traefik_entry(hass, aioclient_mock)

    assert DOMAIN not in hass.services.async_services()


def test_package_module_has_no_setup_or_config_schema() -> None:
    """Without a module-level async_setup there is nothing for CONFIG_SCHEMA to guard."""
    module = importlib.import_module("custom_components.traefik_proxy")

    assert not hasattr(module, "async_setup")
    assert not hasattr(module, "CONFIG_SCHEMA")


def test_button_module_serializes_presses() -> None:
    """button.py declares PARALLEL_UPDATES = 1."""
    module = importlib.import_module("custom_components.traefik_proxy.button")

    assert module.PARALLEL_UPDATES == 1


async def test_refresh_button_registry_entry(hass, aioclient_mock, mock_tls_probe) -> None:  # type: ignore[no-untyped-def]
    """One diagnostic refresh button per entry, without device class, on the main device."""
    entry = await setup_traefik_entry(hass, aioclient_mock)

    entity_id = entity_id_for(hass, "button", _refresh_unique_id(entry.entry_id))
    reg_entry = er.async_get(hass).async_get(entity_id)
    assert reg_entry is not None
    assert reg_entry.unique_id == f"{entry.entry_id}_refresh"
    assert reg_entry.translation_key == "refresh"
    assert reg_entry.entity_category is EntityCategory.DIAGNOSTIC
    assert reg_entry.original_device_class is None

    # Lookup by config entry works on HA 2026.3 and on releases that deprecate async_get_device.
    main_identifier = device_identifier(entry.entry_id, TraefikDevice.MAIN)
    mains = [
        device
        for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
        if main_identifier in device.identifiers
    ]
    assert len(mains) == 1
    assert reg_entry.device_id == mains[0].id

    buttons = [e for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id) if e.domain == "button"]
    assert [e.unique_id for e in buttons] == [f"{entry.entry_id}_refresh"]
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["friendly_name"].endswith("Refresh now")


async def test_press_refreshes_only_own_entry(hass, aioclient_mock, mock_tls_probe) -> None:  # type: ignore[no-untyped-def]
    """Pressing entry A's button refreshes A's two coordinators once each and B's not at all."""
    entry_a = await setup_traefik_entry(hass, aioclient_mock)
    entry_b = make_traefik_entry(
        data={CONF_URL: SECOND_URL, CONF_API_KEY: "k2", CONF_VERIFY_SSL: True},
        unique_id="traefik2.example.com",
    )
    stub_traefik(aioclient_mock, base_url=SECOND_URL)
    entry_b.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry_b.entry_id)
    await hass.async_block_till_done()
    assert entry_b.state is ConfigEntryState.LOADED

    mocks = {(name, attr): AsyncMock() for name in ("a", "b") for attr in ("coordinator", "cert_coordinator")}
    runtimes = {"a": entry_a.runtime_data, "b": entry_b.runtime_data}
    with (
        patch.object(runtimes["a"].coordinator, "async_request_refresh", mocks["a", "coordinator"]),
        patch.object(runtimes["a"].cert_coordinator, "async_request_refresh", mocks["a", "cert_coordinator"]),
        patch.object(runtimes["b"].coordinator, "async_request_refresh", mocks["b", "coordinator"]),
        patch.object(runtimes["b"].cert_coordinator, "async_request_refresh", mocks["b", "cert_coordinator"]),
    ):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": entity_id_for(hass, "button", _refresh_unique_id(entry_a.entry_id))},
            blocking=True,
        )
        await hass.async_block_till_done()

    mocks["a", "coordinator"].assert_awaited_once_with()
    mocks["a", "cert_coordinator"].assert_awaited_once_with()
    mocks["b", "coordinator"].assert_not_awaited()
    mocks["b", "cert_coordinator"].assert_not_awaited()


async def test_only_get_requests_reach_traefik(hass, aioclient_mock, mock_tls_probe) -> None:  # type: ignore[no-untyped-def]
    """Setup, a refresh and a real button press send GET requests only."""
    entry = await setup_traefik_entry(hass, aioclient_mock)
    runtime = entry.runtime_data
    await runtime.coordinator.async_refresh()
    await runtime.cert_coordinator.async_refresh()
    await hass.async_block_till_done()
    calls_before_press = len(aioclient_mock.mock_calls)

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity_id_for(hass, "button", _refresh_unique_id(entry.entry_id))},
        blocking=True,
    )
    await hass.async_block_till_done()

    # The press reached Traefik through the main coordinator's refresh.
    assert len(aioclient_mock.mock_calls) > calls_before_press
    methods = {str(method).upper() for method, _url, _data, _headers in aioclient_mock.mock_calls}
    assert methods == {"GET"}


@pytest.mark.xfail(strict=True, reason="RED: the update listener stacks across reloads and survives unload")
async def test_update_listener_registered_once_across_reloads(hass, aioclient_mock, mock_tls_probe) -> None:  # type: ignore[no-untyped-def]
    """One update listener after setup and reload, one run per options change, none after unload."""
    entry = await setup_traefik_entry(hass, aioclient_mock, make_traefik_entry(minor_version=2))
    assert len(entry.update_listeners) == 1

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert len(entry.update_listeners) == 1

    with patch("custom_components.traefik_proxy.build_api_client", wraps=build_api_client) as spy:
        hass.config_entries.async_update_entry(entry, options={CONF_SCAN_INTERVAL: 45})
        await hass.async_block_till_done()
    assert spy.call_count == 1
    assert entry.runtime_data.coordinator.update_interval == timedelta(seconds=45)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(entry.update_listeners) == 0
