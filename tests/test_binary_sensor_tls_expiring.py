"""Unit tests for ``TraefikCertExpiringBinarySensor``.

Contract pins:

- ``is_on`` is True when ``days_until_expiry <= threshold_days`` (signed:
  an expired certificate is on); None, not False, for a ``CertError`` row or
  an absent host, so HA never shows "off" without a certificate.
- The threshold is read live from the cert coordinator, so a threshold
  change flips the state without a new probe, and it is part of the
  write-on-change token.
- Enabled by default, device class ``problem``.
- The attribute set is always the same, with None values on the error path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.traefik_proxy.binary_sensor import TraefikCertExpiringBinarySensor
from custom_components.traefik_proxy.const import DOMAIN
from custom_components.traefik_proxy.entity import TraefikCertEntity
from custom_components.traefik_proxy.tls import CertError, CertInfo

HOST = "api.example.com"
ATTRIBUTE_KEYS = {
    "days_until_expiry",
    "threshold_days",
    "not_after",
    "last_error",
    "san_mismatch",
    "host",
    "fetched_at",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cert_info(*, host: str = HOST, days_until_expiry: int = 30, san_mismatch: bool = False) -> CertInfo:
    return CertInfo(
        host=host,
        port=443,
        not_after=datetime(2030, 1, 1, tzinfo=UTC),
        days_until_expiry=days_until_expiry,
        subject=f"CN={host}",
        issuer="CN=Test CA",
        san=(host,),
        san_mismatch=san_mismatch,
    )


def _cert_error(host: str = HOST, *, code: str = "timeout") -> CertError:
    return CertError(host=host, port=443, error=code, detail="test stub")


def _coord(
    cache: dict[str, Any] | None = None, *, threshold_days: int = 14, last_update_success: bool = True
) -> MagicMock:
    coord: MagicMock = MagicMock()
    coord.data = cache if cache is not None else {HOST: _cert_info()}
    coord.threshold_days = threshold_days
    coord.last_update_success = last_update_success
    return coord


def _entry(coord: MagicMock) -> MagicMock:
    entry: MagicMock = MagicMock()
    entry.entry_id = "test-entry"
    entry.data = {"url": "https://traefik.example.com:8080"}
    entry.runtime_data.cert_coordinator = coord
    return entry


def _entity(
    row: CertInfo | CertError | None = None, *, threshold_days: int = 14, last_update_success: bool = True
) -> TraefikCertExpiringBinarySensor:
    cache: dict[str, Any] = {} if row is None else {HOST: row}
    coord = _coord(cache, threshold_days=threshold_days, last_update_success=last_update_success)
    return TraefikCertExpiringBinarySensor(_entry(coord), HOST)


# ---------------------------------------------------------------------------
# is_on / available
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("days_until_expiry", "threshold", "expected"),
    [
        (30, 14, False),  # comfortably above the threshold
        (15, 14, False),  # one day above
        (14, 14, True),  # at the threshold (<=)
        (10, 14, True),  # below
        (0, 0, True),  # expires today, threshold 0
        (-1, 14, True),  # already expired
    ],
)
def test_is_on_signed_threshold(days_until_expiry: int, threshold: int, expected: bool) -> None:
    entity = _entity(_cert_info(days_until_expiry=days_until_expiry), threshold_days=threshold)
    assert entity.is_on is expected
    assert entity.available is True


def test_certerror_row_is_unknown_and_unavailable() -> None:
    entity = _entity(_cert_error())
    assert entity.is_on is None
    assert entity.available is False


def test_absent_host_is_unknown_and_unavailable() -> None:
    entity = _entity(None)
    assert entity.is_on is None
    assert entity.available is False


def test_failed_cert_cycle_is_unavailable() -> None:
    entity = _entity(_cert_info(), last_update_success=False)
    assert entity.available is False


def test_threshold_change_flips_state_without_probe() -> None:
    entity = _entity(_cert_info(days_until_expiry=10), threshold_days=14)
    assert entity.is_on is True
    entity.coordinator.threshold_days = 7
    assert entity.is_on is False
    assert entity.extra_state_attributes["threshold_days"] == 7
    entity.coordinator.threshold_days = 14
    assert entity.is_on is True


def test_state_token_follows_row_and_threshold() -> None:
    """The write-on-change token changes with the threshold and the row, not otherwise."""
    entity = _entity(_cert_info(days_until_expiry=10), threshold_days=14)
    token = entity._state_token()
    assert entity._state_token() == token
    entity.coordinator.threshold_days = 7
    assert entity._state_token() != token
    entity.coordinator.threshold_days = 14
    assert entity._state_token() == token
    entity.coordinator.data = {HOST: _cert_info(days_until_expiry=9)}
    assert entity._state_token() != token


# ---------------------------------------------------------------------------
# extra_state_attributes
# ---------------------------------------------------------------------------


def test_attributes_for_a_certificate() -> None:
    info = _cert_info(days_until_expiry=10, san_mismatch=True)
    attrs = _entity(info).extra_state_attributes
    assert set(attrs) == ATTRIBUTE_KEYS
    assert attrs["days_until_expiry"] == 10
    assert attrs["threshold_days"] == 14
    assert attrs["not_after"] == info.not_after.isoformat()
    assert attrs["last_error"] is None
    assert attrs["san_mismatch"] is True
    assert attrs["host"] == HOST
    assert attrs["fetched_at"] == info.fetched_at.isoformat()


def test_attributes_for_a_probe_error() -> None:
    attrs = _entity(_cert_error(code="timeout")).extra_state_attributes
    assert set(attrs) == ATTRIBUTE_KEYS
    assert attrs["days_until_expiry"] is None
    assert attrs["threshold_days"] == 14
    assert attrs["not_after"] is None
    assert attrs["last_error"] == "timeout"
    assert attrs["san_mismatch"] is None


def test_attributes_for_an_absent_host() -> None:
    attrs = _entity(None).extra_state_attributes
    assert set(attrs) == ATTRIBUTE_KEYS
    assert attrs["days_until_expiry"] is None
    assert attrs["last_error"] is None
    assert attrs["threshold_days"] == 14


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def test_identity_and_device() -> None:
    coord = _coord()
    entry = _entry(coord)
    entity = TraefikCertExpiringBinarySensor(entry, HOST)
    assert isinstance(entity, TraefikCertEntity)
    assert entity.unique_id == f"test-entry_tls_expiring_{HOST}"
    assert entity.entity_id is None
    assert entity.coordinator is coord
    assert entity.coordinator is not entry.runtime_data.coordinator
    assert entity.device_info is not None
    assert entity.device_info["identifiers"] == {(DOMAIN, "test-entry_certificates")}
    assert entity.translation_key == "certificate_expiring"
    assert entity.translation_placeholders == {"host": HOST}
    assert entity.device_class == BinarySensorDeviceClass.PROBLEM
    assert entity.entity_registry_enabled_default is True
    assert not hasattr(entity, "_coordinator")


def test_host_is_lowercased() -> None:
    entity = TraefikCertExpiringBinarySensor(_entry(_coord()), "API.Example.COM")
    assert entity.unique_id == f"test-entry_tls_expiring_{HOST}"
    assert entity.translation_placeholders == {"host": HOST}
    assert entity.is_on is False
