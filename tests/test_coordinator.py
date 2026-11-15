"""Integration tests for TraefikProxyCoordinator + __init__.py lifecycle.

Mirrors the gatus project's test_init.py patterns: state-machine assertions
(LOADED / SETUP_RETRY / SETUP_ERROR) and runtime_data wiring verified via
hass.config_entries.async_setup (the proper HA entry machinery).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant.common import MockConfigEntry

from custom_components.traefik_proxy import api
from custom_components.traefik_proxy.cert_coordinator import CertCoordinator
from custom_components.traefik_proxy.const import (
    CONF_API_KEY,
    CONF_URL,
    CONF_VERIFY_SSL,
    DOMAIN,
)
from custom_components.traefik_proxy.coordinator import (
    VERSION_RECHECK_INTERVAL,
    TraefikProxyCoordinator,
    url_host,
    url_unique_id,
)
from custom_components.traefik_proxy.data import TraefikRuntimeData
from custom_components.traefik_proxy.entity_manager import ROUTERS
from custom_components.traefik_proxy.models import TraefikSnapshot
from tests.conftest import (
    AUTH_TYPE,
    MOCK_URL,
    entity_id_for,
    load_fixture,
    snapshot_from_fixture,
    stub_traefik,
    stub_traefik_paginated,
)


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


async def test_request_construction_error_stops_setup_without_traceback(hass, aioclient_mock, caplog) -> None:
    """aiohttp refusing to build the request => ConfigEntryError 'invalid_url' => SETUP_ERROR, no traceback (D-15)."""
    aioclient_mock.get(
        f"{MOCK_URL}/api/version",
        exc=ValueError("Cannot combine AUTHORIZATION header with AUTH argument or credentials encoded in URL"),
    )

    entry = _make_entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert result is False
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert entry.error_reason_translation_key == "invalid_url"
    assert "Unexpected error fetching" not in caplog.text
    # Home Assistant logs a ConfigEntryError from setup with its traceback at
    # ERROR. That record is the only one above DEBUG with a traceback, and its
    # exception chain stops at the translated error: aiohttp's cause (its text
    # can be the URL) never reaches the log.
    tracebacks = [record for record in caplog.records if record.exc_info and record.levelno > logging.DEBUG]
    assert [record.name for record in tracebacks] == ["homeassistant.config_entries"]
    exc_info = tracebacks[0].exc_info
    assert exc_info is not None
    logged = exc_info[1]
    assert getattr(logged, "translation_key", None) == "invalid_url"
    assert logged is not None
    assert logged.__cause__ is None
    assert logged.__suppress_context__ is True
    assert "Cannot combine" not in caplog.text


@pytest.mark.parametrize(
    "auth",
    [
        pytest.param({AUTH_TYPE: "bearer", CONF_TOKEN: "bad\ntoken"}, id="control-character"),
        pytest.param({AUTH_TYPE: "digest"}, id="unknown-auth-type"),
    ],
)
async def test_invalid_credentials_start_reauth_without_request(hass, aioclient_mock, caplog, auth) -> None:
    """Stored credentials Auth rejects => ConfigEntryAuthFailed 'invalid_credentials' => reauth, no request (D-15)."""
    entry = _make_entry(data={CONF_URL: MOCK_URL, CONF_VERIFY_SSL: True, **auth}, minor_version=3)
    entry.add_to_hass(hass)
    result = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert result is False
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert entry.error_reason_translation_key == "invalid_credentials"
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == "reauth"
    assert flows[0]["context"]["entry_id"] == entry.entry_id
    assert aioclient_mock.mock_calls == []
    assert "bad" not in caplog.text


async def test_5xx_triggers_setup_retry(hass, aioclient_mock) -> None:
    """TraefikProxyApiError (5xx) is mapped to UpdateFailed -> ConfigEntryNotReady -> SETUP_RETRY."""
    aioclient_mock.get(f"{MOCK_URL}/api/version", status=500)

    entry = _make_entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert result is False
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_redirect_on_setup_retries_with_translation_key(hass, aioclient_mock) -> None:
    """A 3xx on /api/version at setup => translated UpdateFailed => SETUP_RETRY with key 'redirect'."""
    aioclient_mock.get(f"{MOCK_URL}/api/version", status=302, headers={"Location": "https://other.example.org/"})

    entry = _make_entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert result is False
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert entry.error_reason_translation_key == "redirect"
    assert len(aioclient_mock.mock_calls) == 1


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


async def test_missing_version_raises_translated_update_failed(hass, aioclient_mock, mock_tls_probe) -> None:
    """A cycle that ends without a stored version fails with 'version_unavailable'."""
    stub_traefik(aioclient_mock)
    entry = await _setup_entry(hass)
    coordinator = entry.runtime_data.coordinator
    coordinator._version = None

    with (
        patch.object(coordinator, "_async_refresh_version", AsyncMock()),
        pytest.raises(UpdateFailed) as excinfo,
    ):
        await coordinator._async_update_data()

    assert excinfo.value.translation_key == "version_unavailable"
    assert excinfo.value.translation_domain == DOMAIN


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
    enabled = hass.states.get(entity_id_for(hass, "sensor", ROUTERS.unique_id(entry.entry_id, "secure@file")))
    broken = hass.states.get(
        entity_id_for(hass, "sensor", ROUTERS.unique_id(entry.entry_id, "broken-missing-service@file"))
    )
    assert enabled is not None and enabled.state == "enabled"
    assert broken is not None and broken.state == "error"
    assert _requested_paths(aioclient_mock) == ["/api/version", "/api/entrypoints", "/api/rawdata", "/api/certificates"]

    aioclient_mock.mock_calls.clear()
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success is True
    assert _requested_paths(aioclient_mock) == ["/api/rawdata"]


async def test_rawdata_404_switches_to_pages_once(
    hass, aioclient_mock, monkeypatch: pytest.MonkeyPatch, mock_tls_probe
) -> None:
    """A Traefik without /api/rawdata is read through the pages; rawdata is not requested again before the hourly re-check."""
    index = load_fixture("v3.7", "pages/index.json")
    monkeypatch.setattr(api, "DEFAULT_PAGE_SIZE", index["per_page"])
    stub_traefik_paginated(aioclient_mock, version="v3.7")
    pages = [f"/api/http/{kind}" for kind in ("routers", "services", "middlewares") for _page in index[kind]]

    entry = await _setup_entry(hass)
    coordinator = entry.runtime_data.coordinator

    assert _requested_paths(aioclient_mock) == [
        "/api/version",
        "/api/entrypoints",
        "/api/rawdata",
        *pages,
        "/api/certificates",
    ]
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


async def test_switch_back_to_rawdata_publishes_no_change(
    hass, aioclient_mock, freezer, monkeypatch: pytest.MonkeyPatch, mock_tls_probe
) -> None:
    """Pages and rawdata yield the same snapshot: switching back notifies no listener."""
    index = load_fixture("v3.7", "pages/index.json")
    monkeypatch.setattr(api, "DEFAULT_PAGE_SIZE", index["per_page"])
    stub_traefik_paginated(aioclient_mock, version="v3.7")
    entry = await _setup_entry(hass)
    coordinator = entry.runtime_data.coordinator
    calls: list[None] = []
    entry.async_on_unload(coordinator.async_add_listener(lambda: calls.append(None)))
    before = coordinator.data

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{MOCK_URL}/api/rawdata", json=load_fixture("v3.7", "rawdata.json"))
    stub_traefik_paginated(aioclient_mock, version="v3.7")
    freezer.tick(VERSION_RECHECK_INTERVAL)

    assert await _refresh_paths(hass, aioclient_mock, coordinator) == ["/api/version", "/api/rawdata"]
    assert coordinator.last_update_success is True
    assert coordinator.data == before
    assert calls == []


def _version_started_later(hours: int) -> dict[str, str]:
    """The v3.7 /api/version payload with a start date ``hours`` later (a restarted Traefik)."""
    payload = dict(load_fixture("v3.7", "version.json"))
    start = datetime.fromisoformat(payload["startDate"]) + timedelta(hours=hours)
    payload["startDate"] = start.isoformat()
    return payload


async def _refresh_paths(hass, aioclient_mock, coordinator: TraefikProxyCoordinator) -> list[str]:  # type: ignore[no-untyped-def]
    """Run one coordinator cycle and return the paths it requested.

    ``/api/certificates`` is left out: it belongs to the cert coordinator,
    whose own 6 h timer fires while long freezer ticks pass.
    """
    aioclient_mock.mock_calls.clear()
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    return [path for path in _requested_paths(aioclient_mock) if path != "/api/certificates"]


async def test_request_budget_matrix(
    hass, aioclient_mock, freezer, monkeypatch: pytest.MonkeyPatch, mock_tls_probe
) -> None:
    """Exact requests per scenario.

    Rawdata mode: setup, steady, hourly, post-failure and restart. Then the
    paginated fallback after a rawdata 404 and its hourly rawdata re-probe:
    no probe before the re-check interval, and a probe that succeeds
    switches the client back to one rawdata request per cycle. Recurring
    failures cannot starve the probe: it keeps its own hourly clock. A cycle
    in which rawdata and the pages both fail does not switch to the pages.
    """
    assert timedelta(hours=1) == VERSION_RECHECK_INTERVAL
    index = load_fixture("v3.7", "pages/index.json")
    monkeypatch.setattr(api, "DEFAULT_PAGE_SIZE", index["per_page"])
    pages = [f"/api/http/{kind}" for kind in ("routers", "services", "middlewares") for _page in index[kind]]
    stub_traefik(aioclient_mock)

    # (1) Setup reads version, entrypoints and the state.
    entry = await _setup_entry(hass)
    coordinator = entry.runtime_data.coordinator
    assert _requested_paths(aioclient_mock) == ["/api/version", "/api/entrypoints", "/api/rawdata", "/api/certificates"]

    # (2) A steady cycle is one request.
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == ["/api/rawdata"]
    assert coordinator.last_update_success is True

    # (3) After the re-check interval the version is re-read; the same start date
    # means no restart, so the entrypoints are not requested.
    freezer.tick(timedelta(hours=1, seconds=1))
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == ["/api/version", "/api/rawdata"]
    assert coordinator.last_update_success is True

    # (4) A failed cycle makes the next successful one re-check the version.
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{MOCK_URL}/api/rawdata", status=500)
    stub_traefik(aioclient_mock)
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == ["/api/rawdata"]
    assert coordinator.last_update_success is False
    aioclient_mock.clear_requests()
    stub_traefik(aioclient_mock)
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == ["/api/version", "/api/rawdata"]
    assert coordinator.last_update_success is True

    # (5) A changed start date (Traefik restarted) re-reads the entrypoints.
    restarted = _version_started_later(hours=1)
    aioclient_mock.clear_requests()
    stub_traefik(aioclient_mock, version_payload=restarted)
    freezer.tick(timedelta(hours=1))
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == [
        "/api/version",
        "/api/entrypoints",
        "/api/rawdata",
    ]
    assert coordinator.data.version.start_date == datetime.fromisoformat(restarted["startDate"])

    # The next hourly re-check sees the stored pair again: no entrypoints request.
    freezer.tick(timedelta(hours=1))
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == ["/api/version", "/api/rawdata"]

    # (6) /api/rawdata answers 404: the same cycle falls back to the pages.
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{MOCK_URL}/api/version", json=restarted)
    stub_traefik_paginated(aioclient_mock)
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == ["/api/rawdata", *pages]
    assert coordinator.last_update_success is True

    # (7) A steady paginated cycle reads the pages only.
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == pages

    # (8) One second before the re-check interval: still no probe.
    freezer.tick(VERSION_RECHECK_INTERVAL - timedelta(seconds=1))
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == pages

    # (9) Exactly on the interval: version re-check plus one rawdata probe;
    # the probe gets 404 again, so the same cycle is served from the pages.
    freezer.tick(timedelta(seconds=1))
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == ["/api/version", "/api/rawdata", *pages]
    assert coordinator.last_update_success is True

    # (10) Still paginated: the pages only.
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == pages

    # (10a) A failing page fails the cycle.
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{MOCK_URL}/api/http/routers", params={"per_page": index["per_page"], "page": 1}, status=500)
    aioclient_mock.get(f"{MOCK_URL}/api/version", json=restarted)
    stub_traefik_paginated(aioclient_mock)
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == ["/api/http/routers"]
    assert coordinator.last_update_success is False

    # (10b) The post-failure version re-check inside the interval arms no probe.
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{MOCK_URL}/api/version", json=restarted)
    stub_traefik_paginated(aioclient_mock)
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == ["/api/version", *pages]
    assert coordinator.last_update_success is True

    # (11) Rawdata is back, but the re-check interval has not elapsed: no probe.
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{MOCK_URL}/api/rawdata", json=load_fixture("v3.7", "rawdata.json"))
    aioclient_mock.get(f"{MOCK_URL}/api/version", json=restarted)
    stub_traefik_paginated(aioclient_mock)
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == pages

    # (12) The hourly re-check retries rawdata once; success switches back.
    freezer.tick(VERSION_RECHECK_INTERVAL)
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == ["/api/version", "/api/rawdata"]
    assert coordinator.last_update_success is True

    # (13) Back in rawdata mode: one request per cycle.
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == ["/api/rawdata"]

    # (14) Another rawdata 404 switches to the pages again.
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{MOCK_URL}/api/version", json=restarted)
    stub_traefik_paginated(aioclient_mock)
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == ["/api/rawdata", *pages]

    # (15) A page fails every 50 minutes for almost five hours, so every
    # recovery re-checks the version inside the interval. The probe keeps its
    # own hourly clock: it still runs once per hour, the first one an hour
    # after the switch, and never in a failing or recovering cycle.
    def stub_pages(*, failing: bool = False) -> None:
        aioclient_mock.clear_requests()
        if failing:
            aioclient_mock.get(
                f"{MOCK_URL}/api/http/routers", params={"per_page": index["per_page"], "page": 1}, status=500
            )
        aioclient_mock.get(f"{MOCK_URL}/api/version", json=restarted)
        stub_traefik_paginated(aioclient_mock)

    probe_minutes: list[int] = []
    for minute in range(10, 300, 10):
        freezer.tick(timedelta(minutes=10))
        if minute % 50 == 0:
            stub_pages(failing=True)
            assert await _refresh_paths(hass, aioclient_mock, coordinator) == ["/api/http/routers"], minute
            assert coordinator.last_update_success is False
            stub_pages()
            assert await _refresh_paths(hass, aioclient_mock, coordinator) == ["/api/version", *pages], minute
            assert coordinator.last_update_success is True
            continue
        paths = await _refresh_paths(hass, aioclient_mock, coordinator)
        if minute % 60 == 0:
            probe_minutes.append(minute)
            assert paths == ["/api/rawdata", *pages], minute
        else:
            assert paths == pages, minute
    assert probe_minutes == [60, 120, 180, 240]

    # (16) Rawdata is back: the next hourly probe switches back, although the
    # last version check (after the failure at minute 250) is only 50 minutes old.
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{MOCK_URL}/api/rawdata", json=load_fixture("v3.7", "rawdata.json"))
    aioclient_mock.get(f"{MOCK_URL}/api/version", json=restarted)
    stub_traefik_paginated(aioclient_mock)
    freezer.tick(timedelta(minutes=10))
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == ["/api/rawdata"]
    assert coordinator.last_update_success is True

    # (17) Back in rawdata mode: one request per cycle.
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == ["/api/rawdata"]

    # (18) Traefik restarts and its API router is not loaded yet: rawdata and
    # the first page both answer 404. The cycle fails without switching modes.
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{MOCK_URL}/api/rawdata", status=404)
    aioclient_mock.get(f"{MOCK_URL}/api/http/routers", status=404)
    aioclient_mock.get(f"{MOCK_URL}/api/version", status=404)
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == ["/api/rawdata", "/api/http/routers"]
    assert coordinator.last_update_success is False

    # (19) Traefik is back: the post-failure re-check reads rawdata, not the pages.
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{MOCK_URL}/api/rawdata", json=load_fixture("v3.7", "rawdata.json"))
    aioclient_mock.get(f"{MOCK_URL}/api/version", json=restarted)
    stub_traefik_paginated(aioclient_mock)
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == ["/api/version", "/api/rawdata"]
    assert coordinator.last_update_success is True

    # (20) Steady: one rawdata request per cycle.
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == ["/api/rawdata"]


# The request path that fails in each step of _stub_failing_step.
_STEP_PATHS = {"state": "/api/rawdata", "version": "/api/version", "entrypoints": "/api/entrypoints"}


def _stub_failing_step(aioclient_mock, freezer, step: str, status: int) -> None:  # type: ignore[no-untyped-def]
    """Make one step of the next cycle answer ``status``; earlier steps are healthy and due."""
    aioclient_mock.clear_requests()
    if step == "state":
        aioclient_mock.get(f"{MOCK_URL}/api/rawdata", status=status)
        stub_traefik(aioclient_mock)
        return
    freezer.tick(VERSION_RECHECK_INTERVAL)
    if step == "version":
        aioclient_mock.get(f"{MOCK_URL}/api/version", status=status)
        stub_traefik(aioclient_mock)
        return
    aioclient_mock.get(f"{MOCK_URL}/api/entrypoints", status=status)
    stub_traefik(aioclient_mock, version_payload=_version_started_later(hours=1))


@pytest.mark.parametrize("step", ["state", "version", "entrypoints"])
async def test_cycle_auth_error_starts_reauth(hass, aioclient_mock, freezer, mock_tls_probe, step: str) -> None:
    """A 401 in any cycle step becomes ConfigEntryAuthFailed and starts a reauth flow."""
    stub_traefik(aioclient_mock)
    entry = await _setup_entry(hass)
    coordinator = entry.runtime_data.coordinator
    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []

    _stub_failing_step(aioclient_mock, freezer, step, 401)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success is False
    assert coordinator.last_exception is not None
    assert getattr(coordinator.last_exception, "translation_key", None) == "auth_failed"
    assert coordinator.last_exception.translation_placeholders == {"path": _STEP_PATHS[step]}
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == "reauth"
    assert flows[0]["context"]["entry_id"] == entry.entry_id


@pytest.mark.parametrize("step", ["state", "version", "entrypoints"])
async def test_cycle_server_error_keeps_previous_snapshot(
    hass, aioclient_mock, freezer, mock_tls_probe, step: str
) -> None:
    """A 500 in any cycle step becomes UpdateFailed; the entry stays loaded on the previous snapshot."""
    stub_traefik(aioclient_mock)
    entry = await _setup_entry(hass)
    coordinator = entry.runtime_data.coordinator
    previous = coordinator.data

    _stub_failing_step(aioclient_mock, freezer, step, 500)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert coordinator.last_update_success is False
    assert coordinator.data is previous
    assert getattr(coordinator.last_exception, "translation_key", None) == "api_error"
    assert coordinator.last_exception.translation_placeholders == {"path": _STEP_PATHS[step], "detail": "HTTP 500"}
    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []


async def test_cycle_redirect_keeps_entry_loaded(hass, aioclient_mock, freezer, mock_tls_probe) -> None:
    """A 3xx on /api/rawdata in a later cycle => translated 'redirect' failure, entry stays loaded."""
    stub_traefik(aioclient_mock)
    entry = await _setup_entry(hass)
    coordinator = entry.runtime_data.coordinator

    _stub_failing_step(aioclient_mock, freezer, "state", 302)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert coordinator.last_update_success is False
    assert getattr(coordinator.last_exception, "translation_key", None) == "redirect"
    assert coordinator.last_exception.translation_placeholders == {"path": "/api/rawdata", "status": "302"}
    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []


async def test_failed_entrypoint_refetch_is_retried(hass, aioclient_mock, freezer, mock_tls_probe) -> None:
    """A restart whose entrypoint fetch failed is detected again on the next cycle."""
    stub_traefik(aioclient_mock)
    entry = await _setup_entry(hass)
    coordinator = entry.runtime_data.coordinator

    _stub_failing_step(aioclient_mock, freezer, "entrypoints", 500)
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False

    restarted = _version_started_later(hours=1)
    aioclient_mock.clear_requests()
    stub_traefik(aioclient_mock, version_payload=restarted)
    assert await _refresh_paths(hass, aioclient_mock, coordinator) == [
        "/api/version",
        "/api/entrypoints",
        "/api/rawdata",
    ]
    assert coordinator.data.version.start_date == datetime.fromisoformat(restarted["startDate"])


@pytest.mark.parametrize(
    ("url", "unique_id"),
    [
        pytest.param("https://Traefik.Example.com:8443/x", "traefik.example.com:8443", id="host-lowercased"),
        pytest.param("https://traefik.example.com", "traefik.example.com:443", id="https-default-port"),
        pytest.param("http://traefik.example.com", "traefik.example.com:80", id="http-default-port"),
        pytest.param("http://[::1]:8080", "[::1]:8080", id="ipv6"),
    ],
)
def test_url_unique_id(url: str, unique_id: str) -> None:
    """The entry unique_id is host:port with a lowercased host, IPv6 in brackets and the scheme's default port."""
    assert url_unique_id(url) == unique_id


@pytest.mark.parametrize("url", ["http://[::1", "http://h:99999", "https://", "traefik.example.com"])
def test_url_unique_id_rejects_unusable_url(url: str) -> None:
    """A URL without a usable host or port raises ValueError."""
    with pytest.raises(ValueError):
        url_unique_id(url)


@pytest.mark.parametrize(
    ("url", "host"),
    [
        pytest.param("https://Traefik.Example.com:8080/x", "traefik.example.com", id="lowercased"),
        pytest.param("https://", None, id="no-host"),
        pytest.param("http://[::1", None, id="unparsable"),
    ],
)
def test_url_host(url: str, host: str | None) -> None:
    """The host of a URL is lowercased; a URL without a parsable host has none."""
    assert url_host(url) == host
