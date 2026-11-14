"""Pagination and payload-shape tests for TraefikProxyApiClient.async_get_state.

Every case answers ``/api/rawdata`` with 404, so the client takes its
paginated fallback. HTTP is mocked with ``aioclient_mock``; list pages are registered with their
``per_page``/``page`` query and the ``X-Next-Page`` header Traefik sends.
Traefik repeats a page number not greater than the current page on the last
page (observed ``X-Next-Page: 1`` in both captured generations).
"""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

from custom_components.traefik_proxy import api
from custom_components.traefik_proxy.api import (
    TraefikProxyApiClient,
    TraefikProxyApiError,
    TraefikProxyPayloadError,
)
from custom_components.traefik_proxy.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL, DOMAIN
from custom_components.traefik_proxy.models import parse_routers
from tests.conftest import MOCK_URL, load_fixture, load_paginated, stub_traefik_paginated

ROUTERS_PATH = "/api/http/routers"


def _client(hass, page_size: int) -> TraefikProxyApiClient:  # type: ignore[no-untyped-def]
    """Build the client under test on HA's shared (mocked) session."""
    return TraefikProxyApiClient(async_get_clientsession(hass), MOCK_URL, api.Auth(), page_size=page_size)


def _items(*names: str) -> list[dict[str, Any]]:
    return [{"name": name, "status": "enabled", "rule": f"Host(`{name.split('@')[0]}.example.com`)"} for name in names]


def _stub_page(aioclient_mock, page_size: int, page: int, items: Any, next_page: str | None = None) -> None:  # type: ignore[no-untyped-def]
    aioclient_mock.get(
        f"{MOCK_URL}{ROUTERS_PATH}",
        params={"per_page": page_size, "page": page},
        json=items,
        headers={"X-Next-Page": next_page} if next_page is not None else None,
    )


def _stub_no_rawdata(aioclient_mock) -> None:  # type: ignore[no-untyped-def]
    """Answer /api/rawdata with 404 so async_get_state takes the paginated path."""
    aioclient_mock.get(f"{MOCK_URL}/api/rawdata", status=404)


def _stub_empty_services_and_middlewares(aioclient_mock) -> None:  # type: ignore[no-untyped-def]
    aioclient_mock.get(f"{MOCK_URL}/api/http/services", json=[])
    aioclient_mock.get(f"{MOCK_URL}/api/http/middlewares", json=[])


def _router_requests(aioclient_mock) -> list[int]:  # type: ignore[no-untyped-def]
    """Page numbers of every recorded routers request, in order."""
    return [int(call[1].query["page"]) for call in aioclient_mock.mock_calls if call[1].path == ROUTERS_PATH]


async def test_real_router_pages_followed_to_the_end(hass, aioclient_mock) -> None:
    """The captured v3.7 router pages are all requested and parse like the concatenated list."""
    per_page = load_fixture("v3.7", "pages/index.json")["per_page"]
    stub_traefik_paginated(aioclient_mock, version="v3.7")

    state = await _client(hass, per_page).async_get_state()

    items, _next_pages = load_paginated("v3.7", "routers")
    assert state.routers == parse_routers(items)
    assert len(state.routers) == 128
    assert _router_requests(aioclient_mock) == [1, 2]


async def test_full_page_with_non_increasing_next_page_ends_the_loop(hass, aioclient_mock) -> None:
    """A page holding exactly page_size items whose X-Next-Page equals the current page is the last one."""
    _stub_page(aioclient_mock, 2, 1, _items("a@file", "b@file"), next_page="1")
    _stub_no_rawdata(aioclient_mock)
    _stub_empty_services_and_middlewares(aioclient_mock)

    state = await _client(hass, 2).async_get_state()

    assert set(state.routers) == {"a@file", "b@file"}
    assert _router_requests(aioclient_mock) == [1]


async def test_missing_or_non_integer_next_page_ends_the_loop(hass, aioclient_mock) -> None:
    """No header or a non-integer header stops after the current page."""
    _stub_page(aioclient_mock, 2, 1, _items("a@file", "b@file"), next_page="next")
    _stub_no_rawdata(aioclient_mock)
    _stub_empty_services_and_middlewares(aioclient_mock)

    state = await _client(hass, 2).async_get_state()

    assert set(state.routers) == {"a@file", "b@file"}
    assert _router_requests(aioclient_mock) == [1]


async def test_name_repeated_across_pages_yields_one_entry(hass, aioclient_mock) -> None:
    """An item that shifts onto the next page between requests is kept once."""
    _stub_page(aioclient_mock, 2, 1, _items("a@file", "b@file"), next_page="2")
    _stub_page(aioclient_mock, 2, 2, _items("b@file"), next_page="2")
    _stub_no_rawdata(aioclient_mock)
    _stub_empty_services_and_middlewares(aioclient_mock)

    state = await _client(hass, 2).async_get_state()

    assert list(state.routers) == ["a@file", "b@file"]
    assert _router_requests(aioclient_mock) == [1, 2]


async def test_failing_page_raises_and_returns_nothing(hass, aioclient_mock) -> None:
    """HTTP 500 on page 2 raises; no partial state is returned."""
    _stub_page(aioclient_mock, 2, 1, _items("a@file", "b@file"), next_page="2")
    aioclient_mock.get(f"{MOCK_URL}{ROUTERS_PATH}", params={"per_page": 2, "page": 2}, status=500)
    _stub_no_rawdata(aioclient_mock)
    _stub_empty_services_and_middlewares(aioclient_mock)

    with pytest.raises(TraefikProxyApiError):
        await _client(hass, 2).async_get_state()
    assert _router_requests(aioclient_mock) == [1, 2]


async def test_failing_page_keeps_previous_snapshot(
    hass, aioclient_mock, monkeypatch: pytest.MonkeyPatch, mock_tls_probe
) -> None:
    """A mid-pagination failure keeps the previous snapshot object and marks the update failed."""
    per_page = load_fixture("v3.7", "pages/index.json")["per_page"]
    monkeypatch.setattr(api, "DEFAULT_PAGE_SIZE", per_page)
    stub_traefik_paginated(aioclient_mock, version="v3.7")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Traefik",
        data={CONF_URL: MOCK_URL, CONF_API_KEY: "k", CONF_VERIFY_SSL: True},
        unique_id="traefik.example.com",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    coordinator = entry.runtime_data.coordinator
    previous = coordinator.data

    # The first matching mock wins: the failing page 2 shadows the capture's page 2.
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{MOCK_URL}{ROUTERS_PATH}", params={"per_page": per_page, "page": 2}, status=500)
    stub_traefik_paginated(aioclient_mock, version="v3.7")
    await coordinator.async_refresh()

    assert coordinator.last_update_success is False
    assert coordinator.data is previous
    assert _router_requests(aioclient_mock) == [1, 2]


async def test_page_cap_raises_instead_of_truncating(hass, aioclient_mock, monkeypatch: pytest.MonkeyPatch) -> None:
    """A Traefik that always announces another page hits MAX_PAGES and raises."""
    monkeypatch.setattr(api, "MAX_PAGES", 3)

    async def _always_next(method, url, data):  # type: ignore[no-untyped-def]
        page = int(url.query["page"])
        return AiohttpClientMockResponse(
            method, url, json=_items(f"p{page}@file"), headers={"X-Next-Page": str(page + 1)}
        )

    aioclient_mock.get(f"{MOCK_URL}{ROUTERS_PATH}", side_effect=_always_next)
    _stub_no_rawdata(aioclient_mock)
    _stub_empty_services_and_middlewares(aioclient_mock)

    with pytest.raises(TraefikProxyPayloadError, match="more than 3 pages"):
        await _client(hass, 1).async_get_state()
    assert _router_requests(aioclient_mock) == [1, 2, 3]


async def test_object_page_raises_payload_error(hass, aioclient_mock) -> None:
    """A page that is a JSON object instead of a list is rejected."""
    _stub_page(aioclient_mock, 2, 1, {"routers": []})
    _stub_no_rawdata(aioclient_mock)
    _stub_empty_services_and_middlewares(aioclient_mock)

    with pytest.raises(TraefikProxyPayloadError):
        await _client(hass, 2).async_get_state()


async def test_parser_errors_become_path_only_payload_errors(hass, aioclient_mock) -> None:
    """Parser shape errors surface as TraefikProxyPayloadError naming only the path."""
    _stub_page(aioclient_mock, 2, 1, ["not-an-object"])
    _stub_no_rawdata(aioclient_mock)
    _stub_empty_services_and_middlewares(aioclient_mock)

    with pytest.raises(TraefikProxyPayloadError) as err:
        await _client(hass, 2).async_get_state()
    assert str(err.value) == f"{ROUTERS_PATH}: unexpected payload shape"
    assert isinstance(err.value.__cause__, TypeError)


async def test_version_and_entrypoint_shape_errors(hass, aioclient_mock) -> None:
    """Version without a start date and a non-list entrypoints payload raise payload errors."""
    aioclient_mock.get(f"{MOCK_URL}/api/version", json={"Version": "3.7.19"})
    aioclient_mock.get(f"{MOCK_URL}/api/entrypoints", json={"web": {}})
    client = _client(hass, 2)

    with pytest.raises(TraefikProxyPayloadError, match=r"^/api/version: unexpected payload shape$"):
        await client.async_get_version()
    with pytest.raises(TraefikProxyPayloadError, match=r"^/api/entrypoints: unexpected payload shape$"):
        await client.async_get_entrypoints()


def test_page_size_defaults_to_module_constant(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without an explicit page_size the client reads DEFAULT_PAGE_SIZE at construction."""
    monkeypatch.setattr(api, "DEFAULT_PAGE_SIZE", 7)
    client = TraefikProxyApiClient(None, MOCK_URL, api.Auth())  # type: ignore[arg-type]
    assert client._page_size == 7
