"""Tests for the single effective ``verify_ssl`` value (security fix 1).

Precedence is ``entry.options`` -> ``entry.data`` -> ``DEFAULT_VERIFY_SSL``.
Covers:
- ``effective_verify_ssl`` unit precedence.
- (a) user flow with verify_ssl=False: probe and runtime client use False.
- (b) options False, then reconfigure True: data, options and runtime client
  all end up True; the reconfigure form defaults to the effective value.
- (c) options form defaults to the effective value (data-only entry).
- (d) options change reaches the running client without a reload.
- (e) reauth probe uses the effective value.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.traefik_proxy.api import TraefikProxyApiClient
from custom_components.traefik_proxy.const import (
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    CONF_TLS_WARN_DAYS,
    CONF_URL,
    CONF_VERIFY_SSL,
    DOMAIN,
)
from custom_components.traefik_proxy.coordinator import effective_verify_ssl

MOCK_URL = "https://traefik.example.com:8080"
NEW_URL = "https://traefik-new.example.com:8080"
PROBE_CLIENT = "custom_components.traefik_proxy.config_flow.TraefikProxyApiClient"


def _make_entry(*, verify_ssl: bool = True, options: dict[str, Any] | None = None) -> MockConfigEntry:
    """Build a Traefik MockConfigEntry with the given data verify_ssl and options."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Traefik",
        data={CONF_URL: MOCK_URL, CONF_API_KEY: "k", CONF_VERIFY_SSL: verify_ssl},
        options=options or {},
        unique_id="traefik.example.com",
    )


def _stub_all_endpoints(aioclient_mock, base_url: str) -> None:  # type: ignore[no-untyped-def]
    """Mock the six GET endpoints ``fetch_all`` and the probe request."""
    aioclient_mock.get(
        f"{base_url}/api/version",
        json={"Version": "3.1.4", "Codename": "rancher", "StartDate": "2026-07-01"},
    )
    aioclient_mock.get(f"{base_url}/api/entrypoints", json=[])
    aioclient_mock.get(f"{base_url}/api/http/routers", json=[])
    aioclient_mock.get(f"{base_url}/api/http/services", json=[])
    aioclient_mock.get(f"{base_url}/api/http/middlewares", json=[])
    aioclient_mock.get(
        f"{base_url}/api/overview",
        json={"http": {"routers": [], "services": [], "middlewares": []}},
    )


async def _setup_entry(hass, entry: MockConfigEntry) -> None:  # type: ignore[no-untyped-def]
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


@pytest.mark.parametrize(
    ("data", "options", "expected"),
    [
        ({CONF_VERIFY_SSL: True}, {}, True),
        ({CONF_VERIFY_SSL: False}, {}, False),
        ({}, {}, True),
        ({CONF_VERIFY_SSL: True}, {CONF_VERIFY_SSL: False}, False),
        ({CONF_VERIFY_SSL: False}, {CONF_VERIFY_SSL: True}, True),
    ],
)
def test_effective_verify_ssl_precedence(data: dict[str, Any], options: dict[str, Any], expected: bool) -> None:
    """Options win over data; data wins over the default."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_URL: MOCK_URL, **data}, options=options)
    assert effective_verify_ssl(entry) is expected


async def test_user_flow_verify_ssl_false_reaches_runtime_client(hass, aioclient_mock) -> None:
    """(a) A user who disables verify_ssl at setup gets a runtime client with False."""
    _stub_all_endpoints(aioclient_mock, MOCK_URL)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM

    with patch(PROBE_CLIENT, wraps=TraefikProxyApiClient) as probe:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_URL: MOCK_URL, CONF_API_KEY: "k", CONF_VERIFY_SSL: False},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert probe.call_args.kwargs["verify_ssl"] is False
    entry = result["result"]
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.client._verify_ssl is False


async def test_options_false_then_reconfigure_true(hass, aioclient_mock) -> None:
    """(b) Reconfigure with True after options False syncs data, options and client."""
    _stub_all_endpoints(aioclient_mock, MOCK_URL)
    _stub_all_endpoints(aioclient_mock, NEW_URL)
    entry = _make_entry(verify_ssl=True, options={CONF_VERIFY_SSL: False})
    await _setup_entry(hass, entry)
    assert entry.runtime_data.client._verify_ssl is False

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["data_schema"]({})[CONF_VERIFY_SSL] is False

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: NEW_URL, CONF_API_KEY: "k", CONF_VERIFY_SSL: True},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    assert entry.data[CONF_VERIFY_SSL] is True
    assert entry.options[CONF_VERIFY_SSL] is True
    assert entry.runtime_data.client._verify_ssl is True


async def test_options_form_defaults_to_effective_value(hass, aioclient_mock) -> None:
    """(c) A data-only verify_ssl=False entry shows False in the options form."""
    _stub_all_endpoints(aioclient_mock, MOCK_URL)
    entry = _make_entry(verify_ssl=False)
    await _setup_entry(hass, entry)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["data_schema"]({})[CONF_VERIFY_SSL] is False


async def test_options_change_reaches_running_client(hass, aioclient_mock) -> None:
    """(d) An options verify_ssl change rebuilds the client without a reload."""
    _stub_all_endpoints(aioclient_mock, MOCK_URL)
    entry = _make_entry(verify_ssl=True)
    await _setup_entry(hass, entry)
    coordinator = entry.runtime_data
    assert coordinator.client._verify_ssl is True

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCAN_INTERVAL: 30, CONF_VERIFY_SSL: False, CONF_TLS_WARN_DAYS: 14},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is coordinator
    assert entry.runtime_data.client._verify_ssl is False


async def test_reauth_probe_uses_effective_value(hass, aioclient_mock) -> None:
    """(e) The reauth probe uses options verify_ssl over data."""
    _stub_all_endpoints(aioclient_mock, MOCK_URL)
    entry = _make_entry(verify_ssl=True, options={CONF_VERIFY_SSL: False})
    await _setup_entry(hass, entry)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM

    with patch(PROBE_CLIENT, wraps=TraefikProxyApiClient) as probe:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "new"})
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert probe.call_args.kwargs["verify_ssl"] is False
