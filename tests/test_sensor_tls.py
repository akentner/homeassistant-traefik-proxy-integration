"""Unit tests for ``TraefikCertExpirySensor``.

A ``MagicMock`` cert coordinator on a mock entry feeds the sensor; these
tests cover state derivation and identity. Lifecycle (adding, missing,
grace period) is covered by ``test_cert_entity_state.py`` and
``test_entity_manager.py``.

Contract pins:

- ``native_value`` is the cached ``CertInfo.not_after``; None for a
  ``CertError`` row or an absent host.
- ``available`` is False for a ``CertError`` row, an absent host and a
  failed cert cycle.
- The attribute set is always the same, with None values on the error path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

from homeassistant.components.sensor import SensorDeviceClass

from custom_components.traefik_proxy.const import DOMAIN
from custom_components.traefik_proxy.entity import TraefikCertEntity
from custom_components.traefik_proxy.sensor import TraefikCertExpirySensor
from custom_components.traefik_proxy.tls import CertError, CertInfo

HOST = "api.example.com"
ATTRIBUTE_KEYS = {
    "days_until_expiry",
    "subject",
    "issuer",
    "san",
    "san_mismatch",
    "host",
    "port",
    "fetched_at",
    "last_error",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cert_info(*, host: str = HOST, days_until_expiry: int = 30, san_mismatch: bool = False) -> CertInfo:
    """Build a CertInfo with sensible defaults for assertions."""
    return CertInfo(
        host=host,
        port=443,
        not_after=datetime(2030, 1, 1, tzinfo=UTC),
        days_until_expiry=days_until_expiry,
        subject=f"CN={host}",
        issuer="CN=Test CA",
        san=("z.example.com", host),
        san_mismatch=san_mismatch,
    )


def _cert_error(host: str = HOST, *, code: str = "timeout") -> CertError:
    return CertError(host=host, port=8443, error=code, detail="test stub")


def _coord(cache: dict[str, Any] | None = None, *, last_update_success: bool = True) -> MagicMock:
    """Build a mock CertCoordinator with the given cert data."""
    coord: MagicMock = MagicMock()
    coord.data = cache if cache is not None else {HOST: _cert_info()}
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
    info = _cert_info()
    sensor = _sensor({HOST: info})
    assert sensor.native_value == info.not_after
    assert sensor.available is True


def test_certerror_row_is_none_and_unavailable() -> None:
    sensor = _sensor({HOST: _cert_error()})
    assert sensor.native_value is None
    assert sensor.available is False


def test_absent_host_is_none_and_unavailable() -> None:
    sensor = _sensor({"other.example.com": _cert_info(host="other.example.com")})
    assert sensor.native_value is None
    assert sensor.available is False


def test_failed_cert_cycle_is_unavailable() -> None:
    sensor = _sensor({HOST: _cert_info()}, last_update_success=False)
    assert sensor.available is False


def test_empty_cert_data_is_unavailable() -> None:
    sensor = _sensor({})
    assert sensor.native_value is None
    assert sensor.available is False


# ---------------------------------------------------------------------------
# extra_state_attributes
# ---------------------------------------------------------------------------


def test_attributes_for_a_certificate() -> None:
    info = _cert_info(days_until_expiry=10, san_mismatch=True)
    attrs = _sensor({HOST: info}).extra_state_attributes
    assert set(attrs) == ATTRIBUTE_KEYS
    assert attrs["days_until_expiry"] == 10
    assert attrs["subject"] == f"CN={HOST}"
    assert attrs["issuer"] == "CN=Test CA"
    assert attrs["san"] == (HOST, "z.example.com")
    assert attrs["san_mismatch"] is True
    assert attrs["host"] == HOST
    assert attrs["port"] == 443
    assert attrs["fetched_at"] == info.fetched_at.isoformat()
    assert attrs["last_error"] is None


def test_attributes_for_a_probe_error() -> None:
    attrs = _sensor({HOST: _cert_error(code="refused")}).extra_state_attributes
    assert set(attrs) == ATTRIBUTE_KEYS
    assert attrs["days_until_expiry"] is None
    assert attrs["san_mismatch"] is None
    assert attrs["port"] == 8443
    assert attrs["last_error"] == "refused"
    assert attrs["host"] == HOST


def test_attributes_for_an_absent_host() -> None:
    attrs = _sensor({}).extra_state_attributes
    assert set(attrs) == ATTRIBUTE_KEYS
    assert attrs["days_until_expiry"] is None
    assert attrs["port"] is None
    assert attrs["last_error"] is None


def test_attributes_keep_cached_values_after_a_failed_cycle() -> None:
    """A failed cert cycle makes the sensor unavailable but keeps the last row's attributes."""
    attrs = _sensor({HOST: _cert_info(days_until_expiry=10)}, last_update_success=False).extra_state_attributes
    assert attrs["days_until_expiry"] == 10
    assert attrs["last_error"] is None


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
    assert sensor.device_info["identifiers"] == {(DOMAIN, "test-entry_certificates")}
    assert sensor.translation_key == "certificate_expiry"
    assert sensor.translation_placeholders == {"host": HOST}
    assert sensor.device_class == SensorDeviceClass.TIMESTAMP
    assert sensor.state_class is None
    assert sensor.has_entity_name is True


def test_host_is_lowercased() -> None:
    sensor = TraefikCertExpirySensor(_entry(_coord()), "API.Example.COM")
    assert sensor.unique_id == f"test-entry_tls_cert_{HOST}"
    assert sensor.translation_placeholders == {"host": HOST}
    assert sensor.native_value == datetime(2030, 1, 1, tzinfo=UTC)


def test_no_alias_attribute_for_the_coordinator() -> None:
    sensor = TraefikCertExpirySensor(_entry(_coord()), HOST)
    assert not hasattr(sensor, "_coordinator")
