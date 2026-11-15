"""Tests for the reconfigure flow (security fix 5 + same-host reconfigure).

Covers:
- the reconfigure form never contains the stored token (no default, no
  suggested value);
- with an unchanged auth type an empty or omitted token keeps the stored one,
  for the probe and storage;
- a non-empty token replaces it;
- reconfigure on the same host succeeds (also with a verify_ssl flip);
- reconfiguring to a host owned by another entry aborts with
  ``already_configured`` before any probe;
- a host change to an unused host succeeds.
"""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry

from custom_components.traefik_proxy.const import (
    CONF_URL,
    CONF_VERIFY_SSL,
)
from tests.conftest import AUTH_TYPE, MOCK_URL, make_traefik_entry, stub_traefik

NEW_URL = "https://traefik-new.example.com:8080"
OTHER_URL = "https://other.example.com:8080"
SECRET = "test-secret"


def _make_entry(*, options: dict[str, Any] | None = None) -> MockConfigEntry:
    """Entry A: MOCK_URL with the stored bearer token ``test-secret``."""
    return make_traefik_entry(
        data={CONF_URL: MOCK_URL, CONF_VERIFY_SSL: True, AUTH_TYPE: "bearer", CONF_TOKEN: SECRET},
        options=options,
    )


def _probe_auth(aioclient_mock) -> str | None:  # type: ignore[no-untyped-def]
    """Authorization header of the first recorded ``/api/version`` request.

    The entries in these tests are added but not set up before the flow, so
    the first version request is the config-flow probe.
    """
    for call in aioclient_mock.mock_calls:
        if str(call[1]).endswith("/api/version"):
            headers = call[3] or {}
            return headers.get("Authorization")
    raise AssertionError("no /api/version request recorded")


async def test_reconfigure_form_does_not_contain_token(hass) -> None:
    """The form pre-fills the URL but never the stored token."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    validated = result["data_schema"]({})
    assert validated[CONF_URL] == MOCK_URL
    assert validated[AUTH_TYPE] == "bearer"
    assert CONF_TOKEN not in validated
    for marker in result["data_schema"].schema:
        assert SECRET not in repr(getattr(marker, "description", None))


@pytest.mark.parametrize("submitted", [{CONF_TOKEN: ""}, {}], ids=["empty", "omitted"])
async def test_same_host_empty_token_keeps_stored_token(hass, aioclient_mock, submitted: dict[str, Any]) -> None:
    """Same host + empty/omitted token: success, stored token kept and used for the probe."""
    stub_traefik(aioclient_mock, base_url=MOCK_URL, rawdata={})
    entry = _make_entry()
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: MOCK_URL, CONF_VERIFY_SSL: True, AUTH_TYPE: "bearer", **submitted},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert dict(entry.data) == {CONF_URL: MOCK_URL, CONF_VERIFY_SSL: True, AUTH_TYPE: "bearer", CONF_TOKEN: SECRET}
    assert _probe_auth(aioclient_mock) == f"Bearer {SECRET}"


async def test_same_host_new_token_replaces_stored_token(hass, aioclient_mock) -> None:
    """Same host + non-empty token: the new token is probed and stored."""
    stub_traefik(aioclient_mock, base_url=MOCK_URL, rawdata={})
    entry = _make_entry()
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: MOCK_URL, AUTH_TYPE: "bearer", CONF_TOKEN: "new-token", CONF_VERIFY_SSL: True},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_TOKEN] == "new-token"
    assert _probe_auth(aioclient_mock) == "Bearer new-token"


async def test_same_host_verify_ssl_flip(hass, aioclient_mock) -> None:
    """Same-host reconfigure from options verify_ssl False to True updates the runtime client."""
    stub_traefik(aioclient_mock, base_url=MOCK_URL, rawdata={})
    entry = _make_entry(options={CONF_VERIFY_SSL: False})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.client._verify_ssl is False

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: MOCK_URL, CONF_VERIFY_SSL: True},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.options[CONF_VERIFY_SSL] is True
    assert entry.runtime_data.client._verify_ssl is True
    assert entry.data[CONF_VERIFY_SSL] is True
    assert entry.data[CONF_TOKEN] == SECRET


async def test_reconfigure_to_other_entry_host_aborts(hass, aioclient_mock) -> None:
    """Reconfiguring A to a host owned by entry B aborts without probing."""
    entry = _make_entry()
    entry.add_to_hass(hass)
    other = make_traefik_entry(
        title="Other Traefik",
        data={CONF_URL: OTHER_URL, CONF_VERIFY_SSL: True, AUTH_TYPE: "bearer", CONF_TOKEN: "other"},
        unique_id="other.example.com",
    )
    other.add_to_hass(hass)
    before = dict(entry.data)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: OTHER_URL, AUTH_TYPE: "bearer", CONF_TOKEN: "x", CONF_VERIFY_SSL: True},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert dict(entry.data) == before
    assert not [call for call in aioclient_mock.mock_calls if str(call[1]).startswith(OTHER_URL)]


async def test_reconfigure_to_unused_host_succeeds(hass, aioclient_mock) -> None:
    """A host change to a host no entry owns still succeeds."""
    stub_traefik(aioclient_mock, base_url=NEW_URL, rawdata={})
    entry = _make_entry()
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: NEW_URL, AUTH_TYPE: "bearer", CONF_TOKEN: "k", CONF_VERIFY_SSL: True},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_URL] == NEW_URL


async def test_reconfigure_rejects_userinfo_url(hass, aioclient_mock) -> None:
    """A new URL with embedded credentials is refused with invalid_url; nothing is sent or stored."""
    entry = _make_entry()
    entry.add_to_hass(hass)
    before = dict(entry.data)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: "https://u:p@traefik.example.com:8080", AUTH_TYPE: "bearer", CONF_TOKEN: "k", CONF_VERIFY_SSL: True},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_url"}
    assert dict(entry.data) == before
    assert aioclient_mock.call_count == 0
