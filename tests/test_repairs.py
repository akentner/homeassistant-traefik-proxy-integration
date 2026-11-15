"""Tests for the insecure_credentials repair issue (credentials over plain HTTP)."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant.common import MockConfigEntry

from custom_components.traefik_proxy.const import CONF_URL, CONF_VERIFY_SSL, DOMAIN
from tests.conftest import AUTH_TYPE, MOCK_URL, make_traefik_entry, stub_traefik

HTTP_URL = "http://traefik.example.com:8080"
BEARER = {AUTH_TYPE: "bearer", CONF_TOKEN: "repair-token"}
BASIC = {AUTH_TYPE: "basic", CONF_USERNAME: "repair-user", CONF_PASSWORD: "repair-pass"}
NONE = {AUTH_TYPE: "none"}

pytestmark = pytest.mark.usefixtures("mock_tls_probe")


def _issue_id(entry: MockConfigEntry) -> str:
    return f"insecure_credentials_{entry.entry_id}"


def _get_issue(hass: HomeAssistant, entry: MockConfigEntry) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, _issue_id(entry))


def _own_issues(hass: HomeAssistant) -> list[ir.IssueEntry]:
    return [issue for (domain, _), issue in ir.async_get(hass).issues.items() if domain == DOMAIN]


def _entry(url: str, auth: dict[str, Any]) -> MockConfigEntry:
    return make_traefik_entry(data={CONF_URL: url, CONF_VERIFY_SSL: True, **auth})


async def _setup(hass: HomeAssistant, aioclient_mock: Any, url: str, auth: dict[str, Any]) -> MockConfigEntry:
    """Serve Traefik on the http and https base URL and set up an entry for ``url``."""
    stub_traefik(aioclient_mock, base_url=HTTP_URL)
    stub_traefik(aioclient_mock, base_url=MOCK_URL)
    entry = _entry(url, auth)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.state is ConfigEntryState.LOADED
    return entry


async def test_http_bearer_raises_insecure_credentials_issue(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """A bearer token over http raises a WARNING issue bound to the entry."""
    entry = await _setup(hass, aioclient_mock, HTTP_URL, BEARER)

    issue = _get_issue(hass, entry)
    assert issue is not None
    assert issue.domain == DOMAIN
    assert issue.translation_key == "insecure_credentials"
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.is_fixable is False
    assert issue.is_persistent is False
    assert issue.config_entry_id == entry.entry_id
    assert issue.translation_placeholders == {"entry_title": entry.title}


@pytest.mark.parametrize(
    ("url", "auth", "expected"),
    [
        (HTTP_URL, BASIC, True),
        (HTTP_URL, NONE, False),
        (MOCK_URL, BEARER, False),
        (MOCK_URL, BASIC, False),
    ],
    ids=["http-basic", "http-none", "https-bearer", "https-basic"],
)
async def test_issue_only_for_credentials_over_http(
    hass: HomeAssistant, aioclient_mock: Any, url: str, auth: dict[str, Any], expected: bool
) -> None:
    """Only credentials over http raise the issue; https or no auth raise none."""
    entry = await _setup(hass, aioclient_mock, url, auth)

    assert (_get_issue(hass, entry) is not None) is expected
    if not expected:
        assert _own_issues(hass) == []


async def test_unload_deletes_issue_and_setup_raises_it_again(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """Unload deletes the issue; setting the entry up again raises it again."""
    entry = await _setup(hass, aioclient_mock, HTTP_URL, BEARER)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert _get_issue(hass, entry) is None

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert _get_issue(hass, entry) is not None


@pytest.mark.parametrize(
    "submitted",
    [
        # A new scheme needs the token entered again (WR-01).
        {CONF_URL: MOCK_URL, CONF_VERIFY_SSL: True, AUTH_TYPE: "bearer", CONF_TOKEN: "repair-token"},
        {CONF_URL: HTTP_URL, CONF_VERIFY_SSL: True, AUTH_TYPE: "none"},
    ],
    ids=["to-https", "to-none"],
)
async def test_reconfigure_fix_deletes_issue(
    hass: HomeAssistant, aioclient_mock: Any, submitted: dict[str, Any]
) -> None:
    """Reconfiguring to https or to no authentication reloads the entry without the issue."""
    entry = await _setup(hass, aioclient_mock, HTTP_URL, BEARER)
    assert _get_issue(hass, entry) is not None

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], submitted)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data[CONF_URL] == submitted[CONF_URL]
    assert _get_issue(hass, entry) is None
    assert _own_issues(hass) == []


async def test_removal_leaves_no_issue(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """Removing the entry leaves no issue of it behind."""
    entry = await _setup(hass, aioclient_mock, HTTP_URL, BASIC)
    assert _get_issue(hass, entry) is not None

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert _own_issues(hass) == []


async def test_ignored_issue_returns_after_reload(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """A reload deletes and re-creates the issue, so a user's ignore does not survive it (accepted)."""
    entry = await _setup(hass, aioclient_mock, HTTP_URL, BEARER)
    ir.async_ignore_issue(hass, DOMAIN, _issue_id(entry), True)
    issue = _get_issue(hass, entry)
    assert issue is not None
    assert issue.dismissed_version is not None

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    issue = _get_issue(hass, entry)
    assert issue is not None
    assert issue.dismissed_version is None
