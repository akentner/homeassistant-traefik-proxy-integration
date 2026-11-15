"""Tests for the config entry diagnostics download."""

from __future__ import annotations

import json
from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.components.diagnostics import get_diagnostics_for_config_entry

from custom_components.traefik_proxy import api
from custom_components.traefik_proxy.const import CONF_URL, CONF_VERIFY_SSL
from tests.conftest import (
    AUTH_TYPE,
    MOCK_URL,
    load_fixture,
    make_traefik_entry,
    rawdata_copy,
    restub_traefik,
    setup_traefik_entry,
    stub_traefik_paginated,
)

REDACTED = "**REDACTED**"
USERNAME = "diag-user-7f3"
PASSWORD = "diag-pass-9c1"
TOKEN = "diag-token-5e2"
CERT_HOST = "secure.example.com"
VANISHING_ROUTER = "file-ok@file"


def _basic_entry() -> Any:
    return make_traefik_entry(
        data={
            CONF_URL: MOCK_URL,
            CONF_VERIFY_SSL: True,
            AUTH_TYPE: "basic",
            CONF_USERNAME: USERNAME,
            CONF_PASSWORD: PASSWORD,
        }
    )


def _bearer_entry() -> Any:
    return make_traefik_entry(data={CONF_URL: MOCK_URL, CONF_VERIFY_SSL: True, AUTH_TYPE: "bearer", CONF_TOKEN: TOKEN})


async def test_basic_entry_diagnostics_redact_credentials(
    hass: HomeAssistant, hass_client: Any, aioclient_mock: Any
) -> None:
    """A basic entry's username and password never appear; entry, coordinator, snapshot and certificates do."""
    entry = await setup_traefik_entry(hass, aioclient_mock, _basic_entry())

    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    dump = json.dumps(diag)

    assert USERNAME not in dump
    assert PASSWORD not in dump
    assert diag["entry"]["data"][CONF_USERNAME] == REDACTED
    assert diag["entry"]["data"][CONF_PASSWORD] == REDACTED
    assert diag["entry"]["data"][CONF_URL] == MOCK_URL
    assert diag["entry"]["title"] == entry.title
    assert diag["entry"]["unique_id"] == entry.unique_id
    assert diag["entry"]["version"] == 1
    assert diag["entry"]["minor_version"] == 3
    assert diag["entry"]["options"] == {}
    coordinator = entry.runtime_data.coordinator
    assert diag["coordinator"]["last_update_success"] is True
    assert diag["coordinator"]["update_interval"] == coordinator.update_interval.total_seconds()
    assert diag["coordinator"]["paginated"] is False
    assert set(diag["snapshot"]["routers"]) == set(coordinator.data.routers)
    assert diag["snapshot"]["version"]["start_date"] == coordinator.data.version.start_date.isoformat()
    certificates = diag["certificates"]
    assert certificates["last_update_success"] is True
    assert certificates["threshold_days"] == entry.runtime_data.cert_coordinator.threshold_days
    host = certificates["hosts"][CERT_HOST]
    assert host["source"] == "api"
    assert isinstance(host["certificate"]["not_after"], str)
    assert host["certificate"]["not_after"] == (
        entry.runtime_data.cert_coordinator.data[CERT_HOST].certificate.not_after.isoformat()
    )
    assert diag["missing"] == {}


async def test_bearer_entry_diagnostics_redact_token(
    hass: HomeAssistant, hass_client: Any, aioclient_mock: Any
) -> None:
    """A bearer entry's token never appears in the download."""
    entry = await setup_traefik_entry(hass, aioclient_mock, _bearer_entry())

    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)

    assert TOKEN not in json.dumps(diag)
    assert diag["entry"]["data"][CONF_TOKEN] == REDACTED


async def test_diagnostics_strip_url_userinfo(hass: HomeAssistant, hass_client: Any, aioclient_mock: Any) -> None:
    """Credentials inside a stored URL are cut from it."""
    entry = await setup_traefik_entry(hass, aioclient_mock, _bearer_entry())
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_URL: "https://diag-user:diag-pass@traefik.example.com:8080"}
    )

    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)

    assert diag["entry"]["data"][CONF_URL] == "https://traefik.example.com:8080"
    assert "diag-pass" not in json.dumps(diag)


async def test_diagnostics_contain_no_raw_payload(hass: HomeAssistant, hass_client: Any, aioclient_mock: Any) -> None:
    """Only parsed models are dumped: raw-only Traefik keys never appear."""
    entry = await setup_traefik_entry(hass, aioclient_mock, _bearer_entry())

    dump = json.dumps(await get_diagnostics_for_config_entry(hass, hass_client, entry))

    assert "serverStatus" not in dump
    assert "usedBy" not in dump


async def test_diagnostics_report_paginated_client(
    hass: HomeAssistant,
    hass_client: Any,
    aioclient_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_tls_probe: Any,
) -> None:
    """A client reading the paginated list endpoints is reported as paginated."""
    monkeypatch.setattr(api, "DEFAULT_PAGE_SIZE", load_fixture("v2.11", "pages/index.json")["per_page"])
    stub_traefik_paginated(aioclient_mock, version="v2.11")
    entry = make_traefik_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.state is ConfigEntryState.LOADED

    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)

    assert diag["coordinator"]["paginated"] is True


async def test_diagnostics_before_a_successful_cert_cycle(
    hass: HomeAssistant, hass_client: Any, aioclient_mock: Any
) -> None:
    """A failed first cert cycle is reported as failed with no hosts."""
    aioclient_mock.get(f"{MOCK_URL}/api/certificates", status=500)
    entry = await setup_traefik_entry(hass, aioclient_mock, _bearer_entry())

    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)

    assert diag["certificates"]["last_update_success"] is False
    assert diag["certificates"]["hosts"] == {}


async def test_diagnostics_list_missing_items(hass: HomeAssistant, hass_client: Any, aioclient_mock: Any) -> None:
    """A router that vanished is listed with the time it went missing."""
    entry = await setup_traefik_entry(hass, aioclient_mock, _bearer_entry())
    rawdata = rawdata_copy()
    del rawdata["routers"][VANISHING_ROUTER]
    restub_traefik(aioclient_mock, rawdata=rawdata)
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert entry.runtime_data.coordinator.last_update_success

    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)

    since = diag["missing"]["router"][VANISHING_ROUTER]
    assert isinstance(since, str)
    assert since.endswith("+00:00")
