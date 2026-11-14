"""HA-state propagation of the TLS certificate entities after a full setup.

The cert entities must follow the cert coordinator: a cert cycle, a
threshold change and a ``tls_warn_days`` options change reach
``hass.states`` without any change of the main Traefik snapshot. The main
coordinator keeps ``always_update=False``, so these tests fail whenever a
cert entity only listens to the main coordinator.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.traefik_proxy.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL, DOMAIN
from custom_components.traefik_proxy.tls import CertInfo
from tests.conftest import MOCK_URL, stub_traefik

# TLS hosts of the v3.7 capture (tls.domains and Host(...) rules).
HOST = "secure.example.com"
OTHER_HOST = "www.secure.example.com"

EXPIRING = "binary_sensor.traefik_secure_example_com_expiring"
OTHER_EXPIRING = "binary_sensor.traefik_www_secure_example_com_expiring"
CERT = "sensor.traefik_secure_example_com_cert"
OTHER_CERT = "sensor.traefik_www_secure_example_com_cert"

# Fixed reference instant so not_after values are deterministic.
REFERENCE = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def _cert(host: str, days: int, *, port: int = 443) -> CertInfo:
    """Return a successful probe result for ``host`` with ``days`` left."""
    return CertInfo(
        host=host,
        port=port,
        not_after=REFERENCE + timedelta(days=days),
        days_until_expiry=days,
        subject=f"CN={host}",
        issuer="CN=Test CA",
        san=(host,),
        fetched_at=REFERENCE,
    )


@pytest.fixture
def cert_probe_ok() -> Iterator[AsyncMock]:
    """Answer every TLS probe with a certificate that expires in 30 days."""

    async def _ok(host: str, port: int, **_kwargs: Any) -> CertInfo:
        return _cert(host, 30, port=port)

    with patch(
        "custom_components.traefik_proxy.cert_coordinator.fetch_cert_info_async",
        AsyncMock(side_effect=_ok),
    ) as probe:
        yield probe


async def _setup(hass: HomeAssistant, aioclient_mock: Any) -> MockConfigEntry:
    """Set up one entry served by the v3.7 capture and return it loaded."""
    stub_traefik(aioclient_mock, version="v3.7")
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
    return entry


async def test_cert_cycle_updates_expiring_binary_sensor_state(
    hass: HomeAssistant, aioclient_mock: Any, cert_probe_ok: AsyncMock
) -> None:
    """A cert cycle inside the warning window turns only that host's alarm on."""
    entry = await _setup(hass, aioclient_mock)
    cert_coordinator = entry.runtime_data.cert_coordinator

    state = hass.states.get(EXPIRING)
    assert state is not None
    assert state.state == "off"
    assert state.attributes["days_until_expiry"] == 30

    cert_coordinator.async_set_updated_data({HOST: _cert(HOST, 3), OTHER_HOST: _cert(OTHER_HOST, 30)})
    await hass.async_block_till_done()

    state = hass.states.get(EXPIRING)
    assert state is not None
    assert state.state == "on"
    assert state.attributes["days_until_expiry"] == 3
    other = hass.states.get(OTHER_EXPIRING)
    assert other is not None
    assert other.state == "off"
    assert other.attributes["days_until_expiry"] == 30

    # An unchanged main cycle must not bring the old value back.
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get(EXPIRING)
    assert state is not None
    assert state.state == "on"
    assert state.attributes["days_until_expiry"] == 3
