"""Unit tests for ``TraefikCertExpirySensor``.

A ``MagicMock`` cert coordinator on a mock entry feeds the sensor with
``HostCertState`` rows under a frozen clock; these tests cover state
derivation and identity. Lifecycle (adding, missing, grace period) is
covered by ``test_cert_entity_state.py`` and ``test_entity_manager.py``.

Contract pins:

- ``native_value`` is the last known ``certificate.not_after``; None
  without a certificate or for an absent host.
- ``available`` while the cert cycle succeeded and the host is in the cert
  data, also after a failed probe; False for an absent host and a failed
  cert cycle.
- ``days_until_expiry`` is computed from the clock at read time.
- The attribute set is always the same, with None values without a
  certificate.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass

from custom_components.traefik_proxy.cert_coordinator import NOT_FOUND, CertSource, HostCertState
from custom_components.traefik_proxy.const import DOMAIN
from custom_components.traefik_proxy.entity import TraefikCertEntity
from custom_components.traefik_proxy.sensor import TraefikCertExpirySensor
from tests.conftest import make_cert_state

HOST = "api.example.com"
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
ATTRIBUTE_KEYS = {
    "days_until_expiry",
    "subject",
    "issuer",
    "san",
    "san_mismatch",
    "verified",
    "source",
    "host",
    "port",
    "fetched_at",
    "last_error",
}


@pytest.fixture(autouse=True)
def _frozen(freezer: Any) -> None:
    freezer.move_to(NOW)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cert_state(days: int = 30, **kwargs: Any) -> HostCertState:
    return make_cert_state(HOST, days=days, now=NOW, **kwargs)


def _failed_state(code: str = "timeout", failures: int = 1, **kwargs: Any) -> HostCertState:
    return make_cert_state(HOST, now=NOW, error=code, failures=failures, **kwargs)


def _coord(cache: dict[str, Any] | None = None, *, last_update_success: bool = True) -> MagicMock:
    """Build a mock CertCoordinator with the given cert data."""
    coord: MagicMock = MagicMock()
    coord.data = cache if cache is not None else {HOST: _cert_state()}
    coord.threshold_days = 14
    coord.last_update_success = last_update_success
    return coord


def _entry(coord: MagicMock) -> MagicMock:
    """Build a mock config entry whose runtime data carries ``coord`` as cert coordinator."""
    entry: MagicMock = MagicMock()
    entry.entry_id = "test-entry"
    entry.data = {"url": "https://traefik.example.com:8080"}
    entry.runtime_data.cert_coordinator = coord
    return entry


def _sensor(
    cache: dict[str, Any] | None = None, *, host: str = HOST, last_update_success: bool = True
) -> TraefikCertExpirySensor:
    return TraefikCertExpirySensor(_entry(_coord(cache, last_update_success=last_update_success)), host)


# ---------------------------------------------------------------------------
# native_value / available
# ---------------------------------------------------------------------------


def test_native_value_is_not_after_for_a_certificate() -> None:
    state = _cert_state()
    sensor = _sensor({HOST: state})
    assert state.certificate is not None
    assert sensor.native_value == state.certificate.not_after
    assert sensor.available is True


def test_failed_probe_without_certificate_is_none_but_available() -> None:
    sensor = _sensor({HOST: _failed_state()})
    assert sensor.native_value is None
    assert sensor.available is True


def test_failed_probe_with_last_known_certificate_keeps_the_value() -> None:
    state = make_cert_state(HOST, days=20, now=NOW, error="ssl", failures=2)
    sensor = _sensor({HOST: state})
    assert state.certificate is not None
    assert sensor.native_value == state.certificate.not_after
    assert sensor.available is True
    assert sensor.extra_state_attributes["last_error"] == "ssl"


def test_not_found_row_is_available() -> None:
    sensor = _sensor({HOST: make_cert_state(HOST, now=NOW, source=CertSource.API, error=NOT_FOUND, port=None)})
    assert sensor.native_value is None
    assert sensor.available is True
    assert sensor.extra_state_attributes["last_error"] == NOT_FOUND


def test_absent_host_is_none_and_unavailable() -> None:
    sensor = _sensor({"other.example.com": make_cert_state("other.example.com", days=30, now=NOW)})
    assert sensor.native_value is None
    assert sensor.available is False


def test_failed_cert_cycle_is_unavailable() -> None:
    sensor = _sensor({HOST: _cert_state()}, last_update_success=False)
    assert sensor.available is False


def test_empty_cert_data_is_unavailable() -> None:
    sensor = _sensor({})
    assert sensor.native_value is None
    assert sensor.available is False


# ---------------------------------------------------------------------------
# extra_state_attributes
# ---------------------------------------------------------------------------


def test_attributes_for_a_certificate() -> None:
    base = _cert_state(10, verified=True)
    assert base.certificate is not None
    certificate = dataclasses.replace(base.certificate, sans=("z.example.com", HOST))
    state = dataclasses.replace(base, certificate=certificate, san_mismatch=True)
    attrs = _sensor({HOST: state}).extra_state_attributes
    assert set(attrs) == ATTRIBUTE_KEYS
    assert attrs["days_until_expiry"] == 10
    assert attrs["subject"] == HOST
    assert attrs["issuer"] == "Test CA"
    assert attrs["san"] == (HOST, "z.example.com")
    assert attrs["san_mismatch"] is True
    assert attrs["verified"] is True
    assert attrs["source"] == "probe"
    assert attrs["host"] == HOST
    assert attrs["port"] == 443
    assert attrs["fetched_at"] == NOW.isoformat()
    assert attrs["last_error"] is None


def test_attributes_for_a_probe_error() -> None:
    attrs = _sensor({HOST: _failed_state("refused", port=8443)}).extra_state_attributes
    assert set(attrs) == ATTRIBUTE_KEYS
    assert attrs["days_until_expiry"] is None
    assert attrs["subject"] is None
    assert attrs["issuer"] is None
    assert attrs["san"] is None
    assert attrs["san_mismatch"] is None
    assert attrs["verified"] is None
    assert attrs["source"] == "probe"
    assert attrs["port"] == 8443
    assert attrs["fetched_at"] is None
    assert attrs["last_error"] == "refused"
    assert attrs["host"] == HOST


def test_attributes_for_an_absent_host() -> None:
    attrs = _sensor({}).extra_state_attributes
    assert set(attrs) == ATTRIBUTE_KEYS
    assert attrs["days_until_expiry"] is None
    assert attrs["port"] is None
    assert attrs["source"] is None
    assert attrs["last_error"] is None
    assert attrs["host"] == HOST


def test_attributes_keep_cached_values_after_a_failed_cycle() -> None:
    """A failed cert cycle makes the sensor unavailable but keeps the last row's attributes."""
    attrs = _sensor({HOST: _cert_state(10)}, last_update_success=False).extra_state_attributes
    assert attrs["days_until_expiry"] == 10
    assert attrs["last_error"] is None


def test_days_until_expiry_is_computed_live(freezer: Any) -> None:
    """Floor days drop right after the exact boundary and then hold for a day; the state token follows."""
    sensor = _sensor({HOST: _cert_state(10)})
    token = sensor._state_token()
    assert sensor.extra_state_attributes["days_until_expiry"] == 10
    freezer.tick(timedelta(microseconds=1))
    assert sensor.extra_state_attributes["days_until_expiry"] == 9
    assert sensor._state_token() != token
    token = sensor._state_token()
    freezer.tick(timedelta(hours=23))
    assert sensor.extra_state_attributes["days_until_expiry"] == 9
    assert sensor._state_token() == token


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def test_identity_and_device() -> None:
    coord = _coord()
    sensor = TraefikCertExpirySensor(_entry(coord), HOST)
    assert isinstance(sensor, TraefikCertEntity)
    assert sensor.unique_id == f"test-entry_tls_cert_{HOST}"
    assert sensor.entity_id is None
    assert sensor.coordinator is coord
    assert sensor.device_info is not None
    assert sensor.device_info.identifiers == {(DOMAIN, "test-entry_certificates")}
    assert sensor.translation_key == "certificate_expiry"
    assert sensor.translation_placeholders == {"host": HOST}
    assert sensor.device_class == SensorDeviceClass.TIMESTAMP
    assert sensor.state_class is None
    assert sensor.has_entity_name is True


def test_host_is_lowercased() -> None:
    sensor = TraefikCertExpirySensor(_entry(_coord()), "API.Example.COM")
    assert sensor.unique_id == f"test-entry_tls_cert_{HOST}"
    assert sensor.translation_placeholders == {"host": HOST}
    assert sensor.native_value == NOW + timedelta(days=30)


def test_no_alias_attribute_for_the_coordinator() -> None:
    sensor = TraefikCertExpirySensor(_entry(_coord()), HOST)
    assert not hasattr(sensor, "_coordinator")
