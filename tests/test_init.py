"""Tests for the Traefik integration __init__.py service registration + reload handler.

Covers:
- module-level async_setup registers traefik.reload_routers
- service handler returns verified=True when router set changes
- service handler returns verified=False after budget exhaustion
- service handler propagates TraefikProxyApiError on non-2xx POST
- TraefikProxyReloadButton.async_press dispatches through the service
- reload_routers is admin-only: non-admin callers get Unauthorized, admin
  callers reach the handler

Hermetic — uses aioclient_mock + AsyncMock for client.reload_routers so the
tests don't depend on a live Traefik instance or the 5s polling budget
finishing in real wall-clock time.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import Unauthorized
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.traefik_proxy.api import TraefikProxyApiError
from custom_components.traefik_proxy.button import TraefikProxyReloadButton
from custom_components.traefik_proxy.const import DOMAIN
from tests.conftest import MOCK_URL, make_snapshot, stub_traefik


def _make_entry() -> MockConfigEntry:
    """Build a loaded Traefik MockConfigEntry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Traefik",
        data={"url": MOCK_URL, "api_key": "k", "verify_ssl": True},
        unique_id="traefik.example.com",
    )


def _rawdata(*routers: str) -> dict[str, Any]:
    """A /api/rawdata payload (map form, key = name) holding enabled routers ``routers``."""
    return {
        "routers": {
            name: {"status": "enabled", "rule": f"Host(`{name.split('@')[0]}.example.com`)"} for name in routers
        }
    }


async def test_async_setup_registers_reload_service(hass) -> None:
    """Module-level async_setup registers traefik.reload_routers (PITFALLS M5)."""
    from custom_components.traefik_proxy import async_setup

    assert await async_setup(hass, {}) is True
    assert hass.services.has_service(DOMAIN, "reload_routers")


async def test_reload_service_verified_true_when_routers_change(hass, aioclient_mock) -> None:
    """Reload handler: router set changes -> verified=True with name_diff."""
    from custom_components.traefik_proxy import _async_handle_reload_routers

    # Setup serves routers A and B; every later cycle serves A and C.
    initial = _rawdata("router-a", "router-b")
    updated = _rawdata("router-a", "router-c")
    rawdata_calls = {"count": 0}

    async def _rawdata_response(method, url, data):  # type: ignore[no-untyped-def]
        """side_effect callback returning an AiohttpClientMockResponse."""
        from pytest_homeassistant_custom_component.test_util.aiohttp import (
            AiohttpClientMockResponse,
        )

        rawdata_calls["count"] += 1
        payload = updated if rawdata_calls["count"] > 1 else initial
        return AiohttpClientMockResponse(method, url, json=payload)

    # Registered first, so it wins over the rawdata mock of stub_traefik.
    aioclient_mock.get(f"{MOCK_URL}/api/rawdata", side_effect=_rawdata_response)
    stub_traefik(aioclient_mock, rawdata={})
    # Refresh POST returns 202.
    aioclient_mock.post(f"{MOCK_URL}/api/http/routers/refresh", status=202)

    entry = _make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Stub client.reload_routers to do nothing extra (the POST is mocked above).
    runtime = entry.runtime_data
    runtime.client.reload_routers = AsyncMock(  # type: ignore[attr-defined]
        return_value=None
    )

    # Drive the service handler via a ServiceCall.
    call = _make_service_call(hass)
    result = await _async_handle_reload_routers(call)

    assert result["verified"] is True
    assert result["attempts"] >= 1
    assert sorted(result["name_diff"]["added"]) == ["router-c"]
    assert sorted(result["name_diff"]["removed"]) == ["router-b"]
    assert "elapsed_ms" in result
    assert isinstance(result["elapsed_ms"], int)


async def test_reload_service_verified_false_when_no_change_within_budget(hass, aioclient_mock) -> None:
    """If router set never changes, verified=False after max attempts."""
    from custom_components.traefik_proxy import _async_handle_reload_routers

    stub_traefik(aioclient_mock, rawdata=_rawdata("stable-router"))
    aioclient_mock.post(f"{MOCK_URL}/api/http/routers/refresh", status=202)

    entry = _make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    runtime = entry.runtime_data
    runtime.client.reload_routers = AsyncMock(  # type: ignore[attr-defined]
        return_value=None
    )

    call = _make_service_call(hass)
    result = await _async_handle_reload_routers(call)

    # Router set never changed -> verified=False after the 5s budget elapses.
    # Exact attempt count depends on per-iteration sleep timing (200ms -> 5s
    # backoff caps at attempt ~5 with mocked instant refresh); semantic check
    # is just that we exited via the budget guard, not via a router-set change.
    assert result["verified"] is False
    assert result["attempts"] >= 1
    assert result["attempts"] <= 10
    assert result["name_diff"]["added"] == []
    assert result["name_diff"]["removed"] == []
    assert result["elapsed_ms"] >= 0


async def test_reload_service_propagates_api_errors(hass, aioclient_mock) -> None:
    """Non-2xx POST raises TraefikProxyApiError -> HA surfaces as service failure."""
    from custom_components.traefik_proxy import _async_handle_reload_routers

    stub_traefik(aioclient_mock, rawdata={})
    # POST returns 500 -> reload_routers raises TraefikProxyApiError.
    aioclient_mock.post(f"{MOCK_URL}/api/http/routers/refresh", status=500)

    entry = _make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # No need to stub reload_routers — the real client will hit the mocked POST.

    call = _make_service_call(hass)
    with pytest.raises(TraefikProxyApiError):
        await _async_handle_reload_routers(call)


async def test_reload_button_async_press_calls_service(hass, aioclient_mock) -> None:
    """TraefikProxyReloadButton.async_press dispatches via hass.services.async_call.

    Proof of dispatch chain (button -> service -> handler -> client):
    1. Replace ``entry.runtime_data.client.reload_routers`` with an AsyncMock spy.
    2. Press the button.
    3. Assert the spy was called -> the handler ran -> the button dispatched
       via the service (NOT a direct client call).

    We can't patch ``_async_handle_reload_routers`` after registration because
    the ServiceRegistry captures the handler reference at registration time;
    instead we observe the handler's downstream effect (the client call).
    """
    stub_traefik(aioclient_mock, rawdata={})
    aioclient_mock.post(f"{MOCK_URL}/api/http/routers/refresh", status=202)

    entry = _make_entry()
    entry.add_to_hass(hass)
    # Register the service (module-level setup hasn't fired in tests — call it).
    from custom_components.traefik_proxy import async_setup

    await async_setup(hass, {})

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    # Spy on the handler's downstream effect: ``client.reload_routers`` is
    # only called from inside the service handler.
    spy = AsyncMock(return_value=None)
    runtime.client.reload_routers = spy  # type: ignore[attr-defined]
    # Make the polling loop's ``async_request_refresh`` instant so the press
    # doesn't wait for the 5s budget. The router set never changes (mocked
    # routers are stable) so the handler still returns verified=False.
    coordinator.async_request_refresh = AsyncMock(  # type: ignore[attr-defined]
        return_value=None
    )

    button = TraefikProxyReloadButton(hass, entry, coordinator)
    await button.async_press()
    await hass.async_block_till_done()

    # If the button dispatched via the service -> the handler ran ->
    # ``client.reload_routers`` was called. Without the service dispatch, the
    # button would never reach the handler and the spy stays at 0 calls.
    assert spy.call_count >= 1, (
        f"Expected client.reload_routers to be called via service dispatch, got {spy.call_count} calls"
    )


async def _setup_with_service(hass, aioclient_mock):  # type: ignore[no-untyped-def]
    """Register the service, load an entry and return its coordinator + reload spy."""
    from custom_components.traefik_proxy import async_setup

    stub_traefik(aioclient_mock, rawdata={})
    entry = _make_entry()
    entry.add_to_hass(hass)
    await async_setup(hass, {})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    runtime = entry.runtime_data
    spy = AsyncMock(return_value=None)
    runtime.client.reload_routers = spy  # type: ignore[attr-defined]
    coordinator = runtime.coordinator
    return coordinator, spy


async def test_reload_service_rejects_non_admin_user(hass, aioclient_mock, hass_read_only_user) -> None:
    """A non-admin user calling reload_routers gets Unauthorized; the handler never runs."""
    _coordinator, spy = await _setup_with_service(hass, aioclient_mock)

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            "reload_routers",
            {},
            blocking=True,
            context=Context(user_id=hass_read_only_user.id),
        )

    assert spy.call_count == 0


async def test_reload_service_allows_admin_user(hass, aioclient_mock, hass_admin_user) -> None:
    """An admin user reaches the handler; verification exits on the first attempt."""
    coordinator, spy = await _setup_with_service(hass, aioclient_mock)

    async def _refresh_with_new_router() -> None:
        coordinator.data = make_snapshot(routers=[{"name": "new@docker"}])

    coordinator.async_request_refresh = AsyncMock(  # type: ignore[attr-defined]
        side_effect=_refresh_with_new_router
    )

    await hass.services.async_call(
        DOMAIN,
        "reload_routers",
        {},
        blocking=True,
        context=Context(user_id=hass_admin_user.id),
    )

    spy.assert_awaited_once()
    assert coordinator.async_request_refresh.await_count == 1


def _make_service_call(hass):  # type: ignore[no-untyped-def]
    """Build a ServiceCall for direct handler invocation."""
    from homeassistant.core import Context, ServiceCall

    return ServiceCall(
        hass,
        DOMAIN,
        "reload_routers",
        data={},
        context=Context(),
    )
