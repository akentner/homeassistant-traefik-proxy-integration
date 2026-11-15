"""Tests for the options flow: selectors, int storage, bounds and the reload.

Covers:
- the form: ``scan_interval``, ``tls_warn_days`` and ``missing_grace_hours`` are
  box NumberSelectors with units and bounds, ``verify_ssl`` is a BooleanSelector;
  defaults for an entry without options (D-17)
- the flow is an ``OptionsFlowWithReload``: changed options reload the entry
  and the reloaded runtime uses the new values; unchanged options (also a
  float of the stored int) do not reload (D-16, FLOW-02/adjacency)
- numbers are stored as ``int`` (D-32); values outside a range raise
  ``InvalidData``, the bounds are accepted (D-17)
- no update listener exists after setup or after the reload, and Home
  Assistant reports no listener usage (D-16, WR-03)
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import ClientSession
from homeassistant.config_entries import ConfigEntryState, OptionsFlowWithReload
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.helpers.selector import BooleanSelector, NumberSelector
from pytest_homeassistant.common import MockConfigEntry

from custom_components.traefik_proxy.config_flow import TraefikProxyOptionsFlow
from tests.conftest import ENTRY_DATA, make_traefik_entry, setup_traefik_entry

# Stored option keys are a persistence contract, so the tests spell them out.
SCAN_INTERVAL = "scan_interval"
VERIFY_SSL = "verify_ssl"
TLS_WARN_DAYS = "tls_warn_days"
PER_ITEM_ENTITIES = "per_item_entities"
MISSING_GRACE_HOURS = "missing_grace_hours"

# The form defaults of an entry without options (verify_ssl: the entry data's True).
DEFAULT_INPUT: dict[str, Any] = {SCAN_INTERVAL: 15, VERIFY_SSL: True, TLS_WARN_DAYS: 14, MISSING_GRACE_HOURS: 24}

USAGE_REPORT = "Detected that custom integration 'traefik_proxy'"
LISTENER_MESSAGE = "update listeners should not be used"


async def _init_options(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, Any]:
    """Open the options form of ``entry`` and return the form result."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    return dict(result)


async def _submit(hass: HomeAssistant, entry: MockConfigEntry, user_input: dict[str, Any]) -> dict[str, Any]:
    """Submit ``user_input`` in a fresh options flow and wait for the scheduled reload."""
    result = await _init_options(hass, entry)
    result = dict(await hass.config_entries.options.async_configure(result["flow_id"], user_input))
    # The reload is scheduled; the first cert cycle is an entry background task.
    await hass.async_block_till_done(wait_background_tasks=True)
    return result


def _fields(result: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
    """Map each form field name to its (marker, selector) pair."""
    return {str(marker): (marker, selector) for marker, selector in result["data_schema"].schema.items()}


def test_options_flow_reloads_through_home_assistant() -> None:
    """The options flow lets Home Assistant reload the entry; it has no listener of its own."""
    assert issubclass(TraefikProxyOptionsFlow, OptionsFlowWithReload)


async def test_options_form_selectors(hass: HomeAssistant, aioclient_mock: Any, mock_tls_probe: AsyncMock) -> None:
    """Numbers are box NumberSelectors with units and bounds; verify_ssl is a BooleanSelector."""
    entry = await setup_traefik_entry(hass, aioclient_mock)

    fields = _fields(await _init_options(hass, entry))

    assert list(fields) == [SCAN_INTERVAL, VERIFY_SSL, TLS_WARN_DAYS, MISSING_GRACE_HOURS]
    scan = fields[SCAN_INTERVAL][1]
    assert isinstance(scan, NumberSelector)
    assert scan.config == {"min": 15, "max": 300, "step": 1, "unit_of_measurement": "s", "mode": "box"}
    warn = fields[TLS_WARN_DAYS][1]
    assert isinstance(warn, NumberSelector)
    assert warn.config == {"min": 1, "max": 90, "step": 1, "unit_of_measurement": "d", "mode": "box"}
    assert isinstance(fields[VERIFY_SSL][1], BooleanSelector)
    grace = fields[MISSING_GRACE_HOURS][1]
    assert isinstance(grace, NumberSelector)
    assert grace.config == {"min": 1, "max": 168, "step": 1, "unit_of_measurement": "h", "mode": "box"}


@pytest.mark.parametrize("data_verify_ssl", [True, False])
async def test_options_form_defaults_without_options(
    hass: HomeAssistant, aioclient_mock: Any, mock_tls_probe: AsyncMock, data_verify_ssl: bool
) -> None:
    """Without options the form shows 15 s, the effective TLS verification, 14 days and 24 h."""
    entry_data = {**ENTRY_DATA, VERIFY_SSL: data_verify_ssl}
    entry = await setup_traefik_entry(hass, aioclient_mock, make_traefik_entry(data=entry_data))
    assert dict(entry.options) == {}

    fields = _fields(await _init_options(hass, entry))

    defaults = {name: marker.default() for name, (marker, _selector) in fields.items()}
    assert defaults == {**DEFAULT_INPUT, VERIFY_SSL: data_verify_ssl}


async def test_changed_options_reload_with_new_values(
    hass: HomeAssistant, aioclient_mock: Any, mock_tls_probe: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    """Changed options are stored as ints and reach a reloaded runtime; no listener exists."""
    caplog.set_level(logging.DEBUG)
    entry = await setup_traefik_entry(hass, aioclient_mock)
    runtime = entry.runtime_data
    assert entry.update_listeners == []

    user_input = {**DEFAULT_INPUT, SCAN_INTERVAL: 45, VERIFY_SSL: False, TLS_WARN_DAYS: 30}
    result = await _submit(hass, entry, user_input)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert dict(entry.options) == user_input
    assert type(entry.options[SCAN_INTERVAL]) is int
    assert type(entry.options[TLS_WARN_DAYS]) is int
    assert entry.state is ConfigEntryState.LOADED
    reloaded = entry.runtime_data
    assert reloaded is not runtime
    assert reloaded.coordinator.update_interval == timedelta(seconds=45)
    assert reloaded.cert_coordinator.threshold_days == 30
    assert entry.update_listeners == []

    # The next request of the reloaded entry goes out without TLS verification.
    with patch.object(ClientSession, "get", autospec=True, side_effect=ClientSession.get) as get:
        await reloaded.coordinator.async_refresh()
        await hass.async_block_till_done()
    assert get.call_count >= 1
    assert {call.kwargs["ssl"] for call in get.call_args_list} == {False}

    assert USAGE_REPORT not in caplog.text
    assert LISTENER_MESSAGE not in caplog.text


async def test_unchanged_options_do_not_reload(
    hass: HomeAssistant, aioclient_mock: Any, mock_tls_probe: AsyncMock
) -> None:
    """Submitting the stored values again (45.0 for a stored 45) keeps the running entry."""
    options = {**DEFAULT_INPUT, SCAN_INTERVAL: 45, TLS_WARN_DAYS: 30}
    entry = await setup_traefik_entry(hass, aioclient_mock, make_traefik_entry(options=options))
    runtime = entry.runtime_data

    result = await _submit(hass, entry, {**options, SCAN_INTERVAL: 45.0, TLS_WARN_DAYS: 30.0})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.runtime_data is runtime
    assert dict(entry.options) == options
    assert type(entry.options[SCAN_INTERVAL]) is int


async def test_options_outside_the_form_are_kept(
    hass: HomeAssistant, aioclient_mock: Any, mock_tls_probe: AsyncMock
) -> None:
    """An option the form does not show survives a save."""
    entry = await setup_traefik_entry(hass, aioclient_mock, make_traefik_entry(options={PER_ITEM_ENTITIES: False}))

    await _submit(hass, entry, {**DEFAULT_INPUT, SCAN_INTERVAL: 60})

    assert dict(entry.options) == {PER_ITEM_ENTITIES: False, **DEFAULT_INPUT, SCAN_INTERVAL: 60}
    assert entry.state is ConfigEntryState.LOADED


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (SCAN_INTERVAL, 14),
        (SCAN_INTERVAL, 301),
        (TLS_WARN_DAYS, 0),
        (TLS_WARN_DAYS, 91),
        (MISSING_GRACE_HOURS, 0),
        (MISSING_GRACE_HOURS, 169),
    ],
)
async def test_values_outside_a_range_raise_invalid_data(
    hass: HomeAssistant, aioclient_mock: Any, mock_tls_probe: AsyncMock, field: str, value: int
) -> None:
    """The flow schema rejects a number outside its range; nothing is stored or reloaded."""
    entry = await setup_traefik_entry(hass, aioclient_mock)
    runtime = entry.runtime_data
    result = await _init_options(hass, entry)
    user_input = {**DEFAULT_INPUT, SCAN_INTERVAL: 30, field: value}

    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(result["flow_id"], user_input)
    hass.config_entries.options.async_abort(result["flow_id"])
    await hass.async_block_till_done(wait_background_tasks=True)

    assert dict(entry.options) == {}
    assert entry.runtime_data is runtime


@pytest.mark.parametrize(
    ("scan_interval", "tls_warn_days"),
    [(15, 1), (300, 90)],
)
async def test_range_bounds_are_accepted(
    hass: HomeAssistant, aioclient_mock: Any, mock_tls_probe: AsyncMock, scan_interval: int, tls_warn_days: int
) -> None:
    """The bounds themselves are valid values."""
    entry = await setup_traefik_entry(hass, aioclient_mock)

    user_input = {**DEFAULT_INPUT, SCAN_INTERVAL: scan_interval, TLS_WARN_DAYS: tls_warn_days}
    result = await _submit(hass, entry, user_input)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert dict(entry.options) == user_input
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.coordinator.update_interval == timedelta(seconds=scan_interval)
    assert entry.runtime_data.cert_coordinator.threshold_days == tls_warn_days


@pytest.mark.parametrize("hours", [1, 168])
async def test_missing_grace_hours_bounds_are_accepted(
    hass: HomeAssistant, aioclient_mock: Any, mock_tls_probe: AsyncMock, hours: int
) -> None:
    """1 h and 168 h are valid grace periods and are stored as given."""
    entry = await setup_traefik_entry(hass, aioclient_mock)

    result = await _submit(hass, entry, {**DEFAULT_INPUT, MISSING_GRACE_HOURS: hours})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[MISSING_GRACE_HOURS] == hours
    assert entry.state is ConfigEntryState.LOADED


async def test_missing_grace_hours_stored_as_truncated_int(
    hass: HomeAssistant, aioclient_mock: Any, mock_tls_probe: AsyncMock
) -> None:
    """A non-integral grace period is truncated to whole hours and stored as int."""
    entry = await setup_traefik_entry(hass, aioclient_mock)

    await _submit(hass, entry, {**DEFAULT_INPUT, MISSING_GRACE_HOURS: 24.9})

    assert entry.options[MISSING_GRACE_HOURS] == 24
    assert type(entry.options[MISSING_GRACE_HOURS]) is int
