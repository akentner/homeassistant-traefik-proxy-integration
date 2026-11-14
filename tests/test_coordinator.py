"""Integration tests for TraefikProxyCoordinator + __init__.py lifecycle.

Mirrors the gatus project's test_init.py patterns: state-machine assertions
(LOADED / SETUP_RETRY / SETUP_ERROR) and runtime_data wiring verified via
hass.config_entries.async_setup (the proper HA entry machinery).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.util import slugify
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.traefik_proxy import api
from custom_components.traefik_proxy.cert_coordinator import CertCoordinator
from custom_components.traefik_proxy.const import (
    CONF_API_KEY,
    CONF_URL,
    CONF_VERIFY_SSL,
    DOMAIN,
)
from custom_components.traefik_proxy.coordinator import TraefikProxyCoordinator
from custom_components.traefik_proxy.data import TraefikRuntimeData
from custom_components.traefik_proxy.models import TraefikSnapshot
from tests.conftest import MOCK_URL, load_fixture, snapshot_from_fixture, stub_traefik, stub_traefik_paginated


def _make_entry(**kwargs) -> MockConfigEntry:
    """Build a MockConfigEntry with defaults for the Traefik integration."""
    defaults = {
        "domain": DOMAIN,
        "title": "Traefik",
        "data": {
            CONF_URL: MOCK_URL,
            CONF_API_KEY: "k",
            CONF_VERIFY_SSL: True,
        },
        "unique_id": "traefik.example.com",
    }
    defaults.update(kwargs)
    return MockConfigEntry(**defaults)


async def test_setup_creates_coordinator_in_runtime_data(hass, aioclient_mock) -> None:
    """Happy path: async_setup_entry stores a TraefikRuntimeData holding the coordinator."""
    stub_traefik(aioclient_mock, rawdata={})

    entry = _make_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert result is True
    assert entry.state is ConfigEntryState.LOADED
    assert isinstance(entry.runtime_data, TraefikRuntimeData)
    assert isinstance(entry.runtime_data.coordinator, TraefikProxyCoordinator)
    assert isinstance(entry.runtime_data.cert_coordinator, CertCoordinator)
    assert entry.runtime_data.coordinator.data.version.version == "3.7.19"


async def test_unload_returns_to_not_loaded(hass, aioclient_mock) -> None:
    """async_unload_entry clears state back to NOT_LOADED."""
    stub_traefik(aioclient_mock, rawdata={})

    entry = _make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    result = await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert result is True
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_network_failure_triggers_setup_retry(hass, aioclient_mock) -> None:
    """Transient network failure => ConfigEntryNotReady => SETUP_RETRY."""
    aioclient_mock.get(f"{MOCK_URL}/api/version", exc=Exception("connection refused"))

    entry = _make_entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert result is False
    # SETUP_RETRY is what HA shows when ConfigEntryNotReady is raised.
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_5xx_triggers_setup_retry(hass, aioclient_mock) -> None:
    """TraefikProxyApiError (5xx) is mapped to UpdateFailed -> ConfigEntryNotReady -> SETUP_RETRY."""
    aioclient_mock.get(f"{MOCK_URL}/api/version", status=500)

    entry = _make_entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert result is False
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_401_triggers_setup_error(hass, aioclient_mock) -> None:
    """TraefikProxyAuthError is mapped to ConfigEntryAuthFailed -> SETUP_ERROR."""
    aioclient_mock.get(f"{MOCK_URL}/api/version", status=401)

    entry = _make_entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert result is False
    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_runtime_data_verify_ssl_defaults_true(hass, aioclient_mock) -> None:
    """If data lacks verify_ssl (set via UI), entry.options overrides default=True."""
    stub_traefik(aioclient_mock, rawdata={})

    entry = _make_entry(data={CONF_URL: MOCK_URL, CONF_API_KEY: "k"})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    # verify_ssl defaults to True when neither options nor data provide it.
    assert entry.runtime_data.client._verify_ssl is True  # type: ignore[attr-defined]


async def test_runtime_data_set_before_cert_first_refresh(hass, aioclient_mock) -> None:
    """The cert coordinator's first refresh sees the runtime data and the main data."""
    stub_traefik(aioclient_mock, rawdata={})
    entry = _make_entry()
    entry.add_to_hass(hass)
    seen: dict[str, bool] = {}

    async def _record(self: CertCoordinator) -> dict:
        runtime = self.config_entry.runtime_data
        seen["is_runtime_data"] = isinstance(runtime, TraefikRuntimeData)
        seen["main_data_present"] = runtime.coordinator.data is not None
        return {}

    with patch.object(CertCoordinator, "_async_update_data", _record):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert seen == {"is_runtime_data": True, "main_data_present": True}


async def test_single_client_owner(hass, aioclient_mock) -> None:
    """The coordinator uses the runtime data's client, not a copy of its own."""
    stub_traefik(aioclient_mock, rawdata={})
    entry = _make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    runtime = entry.runtime_data
    assert runtime.coordinator.client is runtime.client


def _requested_paths(aioclient_mock) -> list[str]:
    """Return the URL paths of every recorded request, in order."""
    return [call[1].path for call in aioclient_mock.mock_calls]


async def _setup_entry(hass) -> MockConfigEntry:  # type: ignore[no-untyped-def]
    """Add and set up an entry against whatever the test stubbed; it must load."""
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


async def test_rawdata_snapshot_reaches_entities(hass, aioclient_mock, mock_tls_probe) -> None:
    """Real v3.7 rawdata flows through client and coordinator into router entities, one request per cycle."""
    stub_traefik(aioclient_mock, version="v3.7")
    entry = await _setup_entry(hass)
    coordinator = entry.runtime_data.coordinator

    assert isinstance(coordinator.data, TraefikSnapshot)
    assert coordinator.data == snapshot_from_fixture("v3.7")
    assert len(coordinator.data.routers) == 128
    enabled = hass.states.get(f"binary_sensor.traefik_http_router_{slugify('secure@file')}")
    broken = hass.states.get(f"binary_sensor.traefik_http_router_{slugify('broken-missing-service@file')}")
    assert enabled is not None and enabled.state == "on"
    assert broken is not None and broken.state == "off"
    assert broken.attributes["status"] == "error"
    assert _requested_paths(aioclient_mock) == ["/api/version", "/api/entrypoints", "/api/rawdata"]

    aioclient_mock.mock_calls.clear()
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success is True
    assert _requested_paths(aioclient_mock) == ["/api/rawdata"]


async def test_rawdata_404_switches_to_pages_once(
    hass, aioclient_mock, monkeypatch: pytest.MonkeyPatch, mock_tls_probe
) -> None:
    """A Traefik without /api/rawdata is read through the pages, and rawdata is never asked for again."""
    index = load_fixture("v3.7", "pages/index.json")
    monkeypatch.setattr(api, "DEFAULT_PAGE_SIZE", index["per_page"])
    stub_traefik_paginated(aioclient_mock, version="v3.7")
    pages = [f"/api/http/{kind}" for kind in ("routers", "services", "middlewares") for _page in index[kind]]

    entry = await _setup_entry(hass)
    coordinator = entry.runtime_data.coordinator

    assert _requested_paths(aioclient_mock) == ["/api/version", "/api/entrypoints", "/api/rawdata", *pages]
    expected = snapshot_from_fixture("v3.7")
    assert coordinator.data.routers == expected.routers
    assert coordinator.data.services == expected.services
    assert coordinator.data.middlewares == expected.middlewares

    aioclient_mock.mock_calls.clear()
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success is True
    assert _requested_paths(aioclient_mock) == pages


async def test_equal_snapshots_do_not_notify_listeners(hass, aioclient_mock, mock_tls_probe) -> None:
    """always_update=False: an unchanged snapshot does not call listeners; a changed one does."""
    stub_traefik(aioclient_mock, version="v3.7")
    entry = await _setup_entry(hass)
    coordinator = entry.runtime_data.coordinator
    calls: list[None] = []
    entry.async_on_unload(coordinator.async_add_listener(lambda: calls.append(None)))

    first = coordinator.data
    await coordinator.async_refresh()
    after_first = len(calls)
    await coordinator.async_refresh()

    assert coordinator.data == first
    assert after_first == 0
    assert len(calls) == after_first

    # Positive control: a changed router set is published to listeners.
    aioclient_mock.clear_requests()
    stub_traefik(
        aioclient_mock,
        rawdata={"routers": {"only@file": {"status": "enabled", "rule": "Host(`a.example.com`)"}}},
    )
    await coordinator.async_refresh()

    assert set(coordinator.data.routers) == {"only@file"}
    assert len(calls) == after_first + 1
