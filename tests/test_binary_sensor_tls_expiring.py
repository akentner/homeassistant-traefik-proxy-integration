"""Unit tests for ``TraefikCertExpiringBinarySensor``.

Contract pins:

- ``is_on`` follows ``HostCertState.problem``: on with ``reason`` expired
  (days < 0), else probe_failed (>= 2 consecutive failed probes), else
  not_found, else expiring (days <= threshold); off with reason None.
  None (unknown) only while the host has no certificate and fewer than two
  failures.
- Available while the cert cycle succeeded and the host is in the cert data,
  also after a failed probe.
- The threshold is read live from the cert coordinator, so a threshold
  change flips the state without a new probe, and it is part of the
  write-on-change token, as are the live days.
- Enabled by default, device class ``problem``.
- The attribute set is always the same, with None values without a
  certificate.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.traefik_proxy.binary_sensor import TraefikCertExpiringBinarySensor
from custom_components.traefik_proxy.cert_coordinator import NOT_FOUND, CertSource, HostCertState
from custom_components.traefik_proxy.const import DOMAIN
from custom_components.traefik_proxy.entity import TraefikCertEntity
from tests.conftest import make_cert_state

HOST = "api.example.com"
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
ATTRIBUTE_KEYS = {
    "reason",
    "days_until_expiry",
    "threshold_days",
    "not_after",
    "last_error",
    "verified",
    "source",
    "san_mismatch",
    "host",
    "fetched_at",
}


@pytest.fixture(autouse=True)
def _frozen(freezer: Any) -> None:
    freezer.move_to(NOW)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cert_state(days: int | None = 30, **kwargs: Any) -> HostCertState:
    return make_cert_state(HOST, days=days, now=NOW, **kwargs)


def _coord(
    cache: dict[str, Any] | None = None, *, threshold_days: int = 14, last_update_success: bool = True
) -> MagicMock:
    coord: MagicMock = MagicMock()
    coord.data = cache if cache is not None else {HOST: _cert_state()}
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
    row: HostCertState | None = None, *, threshold_days: int = 14, last_update_success: bool = True
) -> TraefikCertExpiringBinarySensor:
    cache: dict[str, Any] = {} if row is None else {HOST: row}
    coord = _coord(cache, threshold_days=threshold_days, last_update_success=last_update_success)
    return TraefikCertExpiringBinarySensor(_entry(coord), HOST)


# ---------------------------------------------------------------------------
# is_on / reason / available
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("days", "threshold", "expected"),
    [
        (30, 14, False),  # comfortably above the threshold
        (15, 14, False),  # one day above
        (14, 14, True),  # at the threshold (<=)
        (10, 14, True),  # below
        (0, 0, True),  # expires today, threshold 0
        (-1, 14, True),  # already expired
    ],
)
def test_is_on_signed_threshold(days: int, threshold: int, expected: bool) -> None:
    entity = _entity(_cert_state(days), threshold_days=threshold)
    assert entity.is_on is expected
    assert entity.available is True


@pytest.mark.parametrize(
    ("row", "is_on", "reason"),
    [
        (_cert_state(-1, error="timeout", failures=2), True, "expired"),
        (_cert_state(40, error="ssl", failures=2), True, "probe_failed"),
        (_cert_state(None, error="timeout", failures=2), True, "probe_failed"),
        (_cert_state(None, source=CertSource.API, error=NOT_FOUND, port=None), True, "not_found"),
        (_cert_state(14), True, "expiring"),
        (_cert_state(15), False, None),
        (_cert_state(40, error="timeout", failures=1), False, None),
        (_cert_state(None, error="timeout", failures=1), None, None),
    ],
)
def test_reason_precedence(row: HostCertState, is_on: bool | None, reason: str | None) -> None:
    entity = _entity(row)
    assert entity.is_on is is_on
    assert entity.extra_state_attributes["reason"] == reason
    assert entity.available is True


def test_absent_host_is_unknown_and_unavailable() -> None:
    entity = _entity(None)
    assert entity.is_on is None
    assert entity.available is False


def test_failed_cert_cycle_is_unavailable() -> None:
    entity = _entity(_cert_state(), last_update_success=False)
    assert entity.available is False


def test_threshold_change_flips_state_without_probe() -> None:
    entity = _entity(_cert_state(10), threshold_days=14)
    assert entity.is_on is True
    entity.coordinator.threshold_days = 7
    assert entity.is_on is False
    assert entity.extra_state_attributes["threshold_days"] == 7
    entity.coordinator.threshold_days = 14
    assert entity.is_on is True


def test_state_token_follows_row_threshold_and_live_days(freezer: Any) -> None:
    """The write-on-change token changes with the threshold, the row and the day count, not otherwise."""
    entity = _entity(_cert_state(10), threshold_days=14)
    token = entity._state_token()
    assert entity._state_token() == token
    entity.coordinator.threshold_days = 7
    assert entity._state_token() != token
    entity.coordinator.threshold_days = 14
    assert entity._state_token() == token
    freezer.tick(timedelta(days=1))
    assert entity._state_token() != token
    assert entity.extra_state_attributes["days_until_expiry"] == 9


def test_crossing_the_threshold_by_time_turns_on(freezer: Any) -> None:
    entity = _entity(_cert_state(15), threshold_days=14)
    assert entity.is_on is False
    freezer.tick(timedelta(days=1))
    assert entity.is_on is True
    assert entity.extra_state_attributes["reason"] == "expiring"


# ---------------------------------------------------------------------------
# extra_state_attributes
# ---------------------------------------------------------------------------


def test_attributes_for_a_certificate() -> None:
    row = _cert_state(10, verified=True)
    assert row.certificate is not None
    attrs = _entity(row).extra_state_attributes
    assert set(attrs) == ATTRIBUTE_KEYS
    assert attrs["reason"] == "expiring"
    assert attrs["days_until_expiry"] == 10
    assert attrs["threshold_days"] == 14
    assert attrs["not_after"] == row.certificate.not_after.isoformat()
    assert attrs["last_error"] is None
    assert attrs["verified"] is True
    assert attrs["source"] == "probe"
    assert attrs["san_mismatch"] is False
    assert attrs["host"] == HOST
    assert attrs["fetched_at"] == NOW.isoformat()


def test_attributes_for_a_probe_error() -> None:
    attrs = _entity(_cert_state(None, error="timeout", failures=1)).extra_state_attributes
    assert set(attrs) == ATTRIBUTE_KEYS
    assert attrs["reason"] is None
    assert attrs["days_until_expiry"] is None
    assert attrs["threshold_days"] == 14
    assert attrs["not_after"] is None
    assert attrs["last_error"] == "timeout"
    assert attrs["verified"] is None
    assert attrs["san_mismatch"] is None
    assert attrs["fetched_at"] is None


def test_attributes_for_an_absent_host() -> None:
    attrs = _entity(None).extra_state_attributes
    assert set(attrs) == ATTRIBUTE_KEYS
    assert attrs["reason"] is None
    assert attrs["days_until_expiry"] is None
    assert attrs["last_error"] is None
    assert attrs["source"] is None
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
    assert entity.device_info.identifiers == {(DOMAIN, "test-entry_certificates")}
    assert entity.translation_key == "certificate_expiring"
    assert entity.translation_placeholders == {"host": HOST}
    assert entity.device_class == BinarySensorDeviceClass.PROBLEM
    assert entity.entity_registry_enabled_default is True
    assert not hasattr(entity, "_coordinator")


def test_host_key_is_used_unchanged() -> None:
    """The cert coordinator normalises hosts; the entity keeps its key as given."""
    entity = TraefikCertExpiringBinarySensor(_entry(_coord()), "API.Example.COM")
    assert entity.unique_id == "test-entry_tls_expiring_API.Example.COM"
    assert entity.translation_placeholders == {"host": "API.Example.COM"}
    assert entity.is_on is None
