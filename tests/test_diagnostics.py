"""Tests for the config entry diagnostics download."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.components.diagnostics import get_diagnostics_for_config_entry

from custom_components.traefik_proxy import api
from custom_components.traefik_proxy.cert_coordinator import CertSource
from custom_components.traefik_proxy.const import CONF_URL, CONF_VERIFY_SSL
from custom_components.traefik_proxy.diagnostics import _jsonable, _redact_error, _safe_url
from custom_components.traefik_proxy.entity_manager import ROUTERS
from custom_components.traefik_proxy.rules import redact_rule, rule_secret_values
from tests.conftest import (
    AUTH_TYPE,
    MOCK_URL,
    entity_id_for,
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
SECRET_ROUTER = "secure@file"
HEADER_SECRET = "diag-secret-41a"
SECRET_RULE = f"Host(`secure.example.com`) && Header(`X-Api-Key`, `{HEADER_SECRET}`)"


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


async def test_diagnostics_redact_header_value_in_router_rule(
    hass: HomeAssistant, hass_client: Any, aioclient_mock: Any
) -> None:
    """A header value in a router rule is redacted in the download; the entity attribute keeps it."""
    rawdata = rawdata_copy()
    rawdata["routers"][SECRET_ROUTER]["rule"] = SECRET_RULE
    entry = await setup_traefik_entry(hass, aioclient_mock, _bearer_entry(), rawdata=rawdata)

    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    dump = json.dumps(diag)

    assert HEADER_SECRET not in dump
    assert "X-Api-Key" in dump
    assert REDACTED in dump
    assert diag["snapshot"]["routers"][SECRET_ROUTER]["rule"] == (
        f"Host(`secure.example.com`) && Header(`X-Api-Key`, `{REDACTED}`)"
    )
    state = hass.states.get(entity_id_for(hass, ROUTERS.domain, ROUTERS.unique_id(entry.entry_id, SECRET_ROUTER)))
    assert state is not None
    assert HEADER_SECRET in state.attributes["rule"]


async def test_diagnostics_redact_router_errors_that_repeat_the_rule(
    hass: HomeAssistant, hass_client: Any, aioclient_mock: Any
) -> None:
    """An error with the raw rule gets the redacted rule, one with another matcher call is redacted whole."""
    rawdata = rawdata_copy()
    rawdata["routers"][SECRET_ROUTER]["rule"] = SECRET_RULE
    rawdata["routers"][SECRET_ROUTER]["error"] = [
        f"error while parsing rule {SECRET_RULE}: bad",
        "matcher Header(`A`, `x-fragment-secret`) is invalid",
        "service not found",
    ]
    entry = await setup_traefik_entry(hass, aioclient_mock, _bearer_entry(), rawdata=rawdata)

    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)

    assert diag["snapshot"]["routers"][SECRET_ROUTER]["errors"] == [
        f"error while parsing rule Host(`secure.example.com`) && Header(`X-Api-Key`, `{REDACTED}`): bad",
        REDACTED,
        "service not found",
    ]
    dump = json.dumps(diag)
    assert HEADER_SECRET not in dump
    assert "x-fragment-secret" not in dump
    state = hass.states.get(entity_id_for(hass, ROUTERS.domain, ROUTERS.unique_id(entry.entry_id, SECRET_ROUTER)))
    assert state is not None
    assert state.attributes["errors"] == rawdata["routers"][SECRET_ROUTER]["error"]


async def test_diagnostics_redact_regexp_errors_that_quote_a_header_value(
    hass: HomeAssistant, hass_client: Any, aioclient_mock: Any
) -> None:
    """A Go regexp error quotes a HeaderRegexp value without a matcher call; the error is redacted whole."""
    rule = "Host(`a.example.com`) && HeaderRegexp(`X-Api-Key`, `^s3cr3t-(`)"
    rawdata = rawdata_copy()
    rawdata["routers"][SECRET_ROUTER]["rule"] = rule
    rawdata["routers"][SECRET_ROUTER]["error"] = [
        f"error while adding rule {rule}: compiling HeaderRegexp matcher: "
        "error parsing regexp: missing closing ): `^s3cr3t-(`",
    ]
    entry = await setup_traefik_entry(hass, aioclient_mock, _bearer_entry(), rawdata=rawdata)

    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)

    assert diag["snapshot"]["routers"][SECRET_ROUTER]["errors"] == [REDACTED]
    assert "s3cr3t" not in json.dumps(diag)
    state = hass.states.get(entity_id_for(hass, ROUTERS.domain, ROUTERS.unique_id(entry.entry_id, SECRET_ROUTER)))
    assert state is not None
    assert state.attributes["errors"] == rawdata["routers"][SECRET_ROUTER]["error"]


HOST_RULE = "Host(`a.example.com`)"


@pytest.mark.parametrize(
    ("error", "rule", "expected"),
    [
        # a rule with a secret value: quoted text outside the rule is redacted whole
        ("invalid character class range: `z-a`", SECRET_RULE, REDACTED),
        ('the service "api@docker" does not exist', SECRET_RULE, REDACTED),
        # ... and so is the bare value
        (f"value {HEADER_SECRET} rejected", SECRET_RULE, REDACTED),
        # an unquoted error without the value keeps the redacted rule
        (f"rule {SECRET_RULE} failed", SECRET_RULE, f"rule {SECRET_RULE.replace(HEADER_SECRET, REDACTED)} failed"),
        ("service not found", SECRET_RULE, "service not found"),
        # a rule without secret values keeps quoted text
        ('the service "api@docker" does not exist', HOST_RULE, 'the service "api@docker" does not exist'),
        (f"rule {HOST_RULE}: bad", HOST_RULE, f"rule {HOST_RULE}: bad"),
        # a matcher call outside the rule is redacted whole, also without secret values
        ("matcher Header(`A`, `x`) is invalid", HOST_RULE, REDACTED),
        # an unparsable rule: its secrets are unknown, every error is redacted whole
        ("service not found", "Header(`X-Key`, s3cr3t)", REDACTED),
        # no rule: nothing to leak
        ('the service "api@docker" does not exist', "", 'the service "api@docker" does not exist'),
    ],
)
def test_redact_error_fails_closed(error: str, rule: str, expected: str) -> None:
    """Router errors that may carry a header or query value are redacted whole."""
    assert _redact_error(error, rule, redact_rule(rule), rule_secret_values(rule)) == expected


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


def test_jsonable_converts_model_values() -> None:
    """Datetimes become ISO strings, timedeltas seconds, tuples lists, enums their value, keys strings."""
    value = {
        1: (datetime(2026, 11, 15, 12, 0, tzinfo=UTC), timedelta(minutes=5)),
        "source": CertSource.API,
        "nested": [{"none": None}],
    }

    assert _jsonable(value) == {
        "1": ["2026-11-15T12:00:00+00:00", 300.0],
        "source": "api",
        "nested": [{"none": None}],
    }


def test_safe_url_redacts_an_unparsable_url() -> None:
    """A stored URL that cannot be parsed is redacted as a whole; a non-string passes through."""
    assert _safe_url("https://diag-user:diag-pass@[::1:8080") == REDACTED
    assert _safe_url(None) is None
