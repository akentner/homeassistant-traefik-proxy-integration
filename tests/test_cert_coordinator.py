"""CertCoordinator tests — Phase 3 lifecycle invariants (TEST-04 + D-05/D-08/D-10).

Covers the data-path invariants of ``custom_components.traefik_proxy.cert_coordinator.CertCoordinator``:

- Semaphore-bounded concurrent probes (CONTEXT.md D-05).
- Per-host ``asyncio.timeout(5)`` graceful error path (D-10 — never raises).
- ``async_set_threshold`` mutates ``threshold_days`` AND fires
  ``async_update_listeners()`` (D-08 live re-eval).
- ``_collect_hosts`` union extraction from ``tls.domains[].main`` +
  ``tls.domains[].sans[]`` + literal ``Host()`` rule names (config_entry
  wiring), sorted and normalized.

All async tests run under ``pytest-homeassistant-custom-component``;
``MagicMock`` powers the entry / main-coordinator state. Network
operations are mocked at the ``fetch_cert_info_async`` boundary so the
test stays hermetic — the real TLS handshake surface is exercised by
``tests/test_tls.py``.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.traefik_proxy.cert_coordinator import CertCoordinator
from custom_components.traefik_proxy.const import (
    DEFAULT_TLS_CERT_COOLDOWN,
    DEFAULT_TLS_WARN_DAYS,
    MAX_CERT_HOSTS,
    TLS_HANDSHAKE_TIMEOUT,
    TLS_SEMAPHORE,
)
from custom_components.traefik_proxy.entity_manager import CERT_EXPIRING, CERT_EXPIRY
from custom_components.traefik_proxy.tls import CertError, CertInfo, is_error
from tests.conftest import entity_id_for, make_snapshot, rawdata_copy, setup_traefik_entry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    *,
    tls_warn_days: int | None = DEFAULT_TLS_WARN_DAYS,
    title: str = "Traefik",
) -> MagicMock:
    """Build a ``MagicMock`` entry suitable for ``CertCoordinator.__init__``.

    Mirrors ``tests/test_coordinator.py:_make_entry`` so the cert
    coordinator tests reuse the same fixture-building idiom as the main
    coordinator lifecycle tests.
    """
    entry: MagicMock = MagicMock()
    entry.entry_id = "test-entry"
    entry.title = title
    options: dict[str, Any] = {}
    if tls_warn_days is not None:
        options["tls_warn_days"] = tls_warn_days
    entry.options = options
    entry.runtime_data = MagicMock()
    # ``coordinator.data`` is the snapshot the main coordinator publishes;
    # tests override this per scenario.
    entry.runtime_data.coordinator = MagicMock()
    entry.runtime_data.coordinator.data = make_snapshot()
    return entry


def _make_main_coord(
    *,
    entry_options: dict[str, Any] | None = None,
) -> Any:
    """Build a mock main coordinator wired to the entry's runtime_data.

    The cert coordinator reads ``self.config_entry.runtime_data.coordinator.data.routers``
    (BLOCKER #1 fix path). Tests populate ``runtime_data.coordinator.data`` directly
    rather than going through ``aioclient_mock`` — these are pure
    unit tests, not integration tests.
    """
    return _make_entry(tls_warn_days=(entry_options or {}).get("tls_warn_days"))


def _cert_info(
    *,
    host: str = "h1.example.com",
    port: int = 443,
    days_until_expiry: int = 30,
) -> CertInfo:
    """Build a frozen ``CertInfo`` with sensible defaults for assertions."""
    return CertInfo(
        host=host,
        port=port,
        not_after=datetime.now(UTC) + timedelta(days=days_until_expiry),
        days_until_expiry=days_until_expiry,
        subject=f"CN={host}",
        issuer="CN=Test CA",
        san=(host,),
    )


def _cert_error(host: str = "h1.example.com", *, code: str = "timeout") -> CertError:
    return CertError(host=host, port=443, error=code, detail="test stub")


# ---------------------------------------------------------------------------
# Defaults & construction
# ---------------------------------------------------------------------------


def test_default_update_interval_is_6_hours() -> None:
    """CONTEXT.md D-05 spike-validated cycle = 21_600 seconds."""
    c = CertCoordinator(MagicMock(), _make_entry())
    assert c.update_interval == timedelta(seconds=21600)
    assert c.threshold_days == DEFAULT_TLS_WARN_DAYS


def test_threshold_sourced_from_options() -> None:
    """``threshold_days`` falls back to ``DEFAULT_TLS_WARN_DAYS`` when options omit it."""
    c_default = CertCoordinator(MagicMock(), _make_entry(tls_warn_days=None))
    assert c_default.threshold_days == DEFAULT_TLS_WARN_DAYS

    c7 = CertCoordinator(MagicMock(), _make_entry(tls_warn_days=7))
    assert c7.threshold_days == 7

    c90 = CertCoordinator(MagicMock(), _make_entry(tls_warn_days=90))
    assert c90.threshold_days == 90


def test_default_cooldown_constant_matches() -> None:
    """Sanity pin: the const value must match the ``update_interval`` above."""
    assert DEFAULT_TLS_CERT_COOLDOWN == 21600
    assert timedelta(seconds=DEFAULT_TLS_CERT_COOLDOWN) == timedelta(hours=6)


def test_semaphore_default_is_4() -> None:
    """``Semaphore(4)`` per CONTEXT.md D-05 (bounded concurrent handshakes)."""
    c = CertCoordinator(MagicMock(), _make_entry())
    assert isinstance(c._sem, asyncio.Semaphore)
    # ``_value`` is the remaining capacity (private but stable in CPython
    # 3.10+); pin the spike-validated bound.
    assert c._sem._value == 4
    assert TLS_SEMAPHORE == 4


def test_timeout_default_is_5_seconds() -> None:
    """Per-host timeout = 5.0 (CONTEXT.md D-05 spike-validated)."""
    c = CertCoordinator(MagicMock(), _make_entry())
    assert c._timeout == 5.0
    assert TLS_HANDSHAKE_TIMEOUT == 5.0


def test_config_entry_wired_via_super_init() -> None:
    """BLOCKER #1 fix pin: ``super().__init__(config_entry=entry)`` wires the entry.

    Without this, ``self.config_entry.runtime_data.coordinator.data`` access in
    ``_collect_hosts`` raises ``AttributeError``.
    """
    entry = _make_entry()
    c = CertCoordinator(MagicMock(), entry)
    assert c.config_entry is entry


# ---------------------------------------------------------------------------
# Probe — graceful error paths
# ---------------------------------------------------------------------------


async def test_probe_returns_certerror_on_timeout() -> None:
    """Per-host ``asyncio.timeout(5)`` → ``CertError(error="timeout")``.

    Mirrors the production contract: the blocking ``fetch_cert_info_async``
    is wrapped in ``asyncio.timeout(self._timeout)``. A ``TimeoutError``
    escaping that wrapper must be classified as ``timeout`` — not as
    ``unreachable`` (the catch-all).
    """
    c = CertCoordinator(MagicMock(), _make_entry())
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "custom_components.traefik_proxy.cert_coordinator.fetch_cert_info_async",
            AsyncMock(side_effect=TimeoutError()),
        )
        result = await c._probe("example.com")

    assert is_error(result)
    err: Any = result
    assert err["error"] == "timeout"
    assert err["host"] == "example.com"
    assert err["port"] == 443


async def test_probe_catches_generic_exception() -> None:
    """Defense in depth — ``Exception`` → ``CertError(error="unreachable")``.

    The catch-all classification must be deterministic so dashboards can
    group failing hosts by category even when an unusual exception
    (e.g. ``MemoryError``, custom integration error) bubbles up.
    """
    c = CertCoordinator(MagicMock(), _make_entry())
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "custom_components.traefik_proxy.cert_coordinator.fetch_cert_info_async",
            AsyncMock(side_effect=RuntimeError("boom")),
        )
        result = await c._probe("example.com")

    assert is_error(result)
    err: Any = result
    assert err["error"] == "unreachable"
    assert "RuntimeError" in err["detail"]


# ---------------------------------------------------------------------------
# Threshold — live re-eval per D-08
# ---------------------------------------------------------------------------


async def test_async_set_threshold_mutates_and_notifies_listeners() -> None:
    """``async_set_threshold`` mutates ``threshold_days`` AND fires listeners once.

    Note: ``DataUpdateCoordinator.async_update_listeners`` is a SYNC
    method (despite the ``async_`` prefix) that schedules callbacks
    via ``self._listeners`` — not a coroutine. The production code
    (``cert_coordinator.async_set_threshold``) calls it without
    ``await``, so we mock it with ``MagicMock()`` (not ``AsyncMock()``).
    """
    c = CertCoordinator(MagicMock(), _make_entry())
    c.async_update_listeners = MagicMock()  # type: ignore[method-assign]

    await c.async_set_threshold(7)

    assert c.threshold_days == 7
    assert c.async_update_listeners.call_count == 1


async def test_get_threshold_returns_current_value() -> None:
    """Read accessor mirrors the stored ``threshold_days``."""
    c = CertCoordinator(MagicMock(), _make_entry(tls_warn_days=21))
    assert c.get_threshold() == c.threshold_days
    assert c.get_threshold() == 21

    await c.async_set_threshold(5)
    assert c.get_threshold() == 5


# ---------------------------------------------------------------------------
# Data path — async update fans out via gather
# ---------------------------------------------------------------------------


async def test_async_update_data_fans_out_via_gather() -> None:
    """All hosts in the cache get probed; success + error rows merge.

    Two TLS-enabled routers expose three unique hostnames (one with a
    SAN). ``fetch_cert_info_async`` is mocked to return a CertInfo per
    host; the coordinator must fan out via ``asyncio.gather`` and the
    resulting data dict must have one row per host.
    """
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot(
        routers=[
            {
                "name": "r1",
                "tls": {
                    "domains": [
                        {"main": "h1.example.com", "sans": ["h1-alt.example.com"]},
                    ],
                },
                "rule": "Host(`h1.example.com`)",
            },
            {
                "name": "r2",
                "tls": {
                    "domains": [{"main": "h2.example.com"}],
                },
                "rule": "Host(`h2.example.com`)",
            },
        ],
    )
    c = CertCoordinator(MagicMock(), entry)

    async def fake_probe(host: str, port: int = 443, **_kwargs: object) -> CertInfo:
        return _cert_info(host=host, days_until_expiry=30, port=port)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "custom_components.traefik_proxy.cert_coordinator.fetch_cert_info_async",
            AsyncMock(side_effect=fake_probe),
        )
        data = await c._async_update_data()

    assert set(data.keys()) == {
        "h1.example.com",
        "h1-alt.example.com",
        "h2.example.com",
    }
    for value in data.values():
        assert not is_error(value)


async def test_async_update_data_handles_error_rows_mixing_in_success() -> None:
    """Mixed success / error rows both surface in the cache (D-06)."""
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot(
        routers=[
            {
                "name": "r1",
                "tls": {"domains": [{"main": "ok-a.example.com"}]},
                "rule": "Host(`ok-a.example.com`)",
            },
            {
                "name": "r2",
                "tls": {"domains": [{"main": "ok-b.example.com"}]},
                "rule": "Host(`ok-b.example.com`)",
            },
            {
                "name": "r3",
                "tls": {"domains": [{"main": "ok-c.example.com"}]},
                "rule": "Host(`ok-c.example.com`)",
            },
            {
                "name": "r4",
                "tls": {"domains": [{"main": "timeout.example.com"}]},
                "rule": "Host(`timeout.example.com`)",
            },
        ],
    )
    c = CertCoordinator(MagicMock(), entry)

    async def fake_probe(host: str, port: int = 443, **_kwargs: object) -> CertInfo | CertError:
        if host == "timeout.example.com":
            return _cert_error(host=host, code="timeout")
        return _cert_info(host=host, port=port)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "custom_components.traefik_proxy.cert_coordinator.fetch_cert_info_async",
            AsyncMock(side_effect=fake_probe),
        )
        data = await c._async_update_data()

    successes = [host for host, value in data.items() if not is_error(value)]
    failures = [host for host, value in data.items() if is_error(value)]
    assert len(successes) == 3
    assert len(failures) == 1
    assert "timeout.example.com" in failures
    failed_value: Any = data["timeout.example.com"]
    assert failed_value["error"] == "timeout"


async def test_async_update_data_returns_empty_when_no_routers() -> None:
    """Defensive: a snapshot with an empty router list returns an empty cache dict."""
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot(routers=[])
    c = CertCoordinator(MagicMock(), entry)

    data = await c._async_update_data()
    assert data == {}


async def test_async_update_data_handles_empty_snapshot() -> None:
    """A snapshot without any router → empty cache, never raises."""
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot()
    c = CertCoordinator(MagicMock(), entry)

    data = await c._async_update_data()
    assert data == {}


# ---------------------------------------------------------------------------
# Hostname extraction
# ---------------------------------------------------------------------------


def test_collect_hosts_extracts_union_of_domains_and_sans() -> None:
    """BLOCKER #1 fix pin: union of tls.domains[].main + sans[] + Host() matches.

    Routers config:
    - r1 — TLS with main + sans → must be in hosts
    - r2 — TLS with main → must be in hosts
    - r3 — no TLS → dropped
    - api@internal — TLS, but internal routers are not part of the snapshot

    Dedup collapses ``Host(`h1.example.com`)`` (rule) with
    ``domains[].main="h1.example.com"`` to a single host.
    """
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot(
        routers=[
            {
                "name": "r1",
                "tls": {
                    "domains": [
                        {"main": "h1.example.com", "sans": ["h1-alt.example.com"]},
                    ],
                },
                "rule": "Host(`h1.example.com`)",
            },
            {
                "name": "r2",
                "tls": {"domains": [{"main": "h2.example.com"}]},
                "rule": "Host(`h2.example.com`)",
            },
            {
                "name": "r3",
                "tls": None,
                "rule": "",
            },
            {
                "name": "api@internal",
                "tls": {"domains": [{"main": "internal.example.com"}]},
                "rule": "Host(`internal.example.com`)",
            },
        ],
    )
    c = CertCoordinator(MagicMock(), entry)
    assert c.config_entry is entry  # BLOCKER #1 fix pin

    hosts = c._collect_hosts()
    assert hosts == ("h1-alt.example.com", "h1.example.com", "h2.example.com")
    assert "internal.example.com" not in hosts  # internal router not in the snapshot
    assert "r3" not in hosts and "api@internal" not in hosts


def test_collect_hosts_lowercases_for_dedup() -> None:
    """Mixed casing in rule + domains → lowercased + deduped."""
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot(
        routers=[
            {
                "name": "r1",
                "tls": {"domains": [{"main": "EXAMPLE.com"}]},
                "rule": "Host(`Example.COM`)",
            },
            {
                "name": "r2",
                "tls": {"domains": [{"main": "example.com"}]},
                "rule": "Host(`example.com`)",
            },
        ],
    )
    c = CertCoordinator(MagicMock(), entry)
    hosts = c._collect_hosts()
    assert hosts == ("example.com",)


def test_collect_hosts_skips_routers_with_tls_but_no_host() -> None:
    """Routers with empty TLS, TLS without domains, malformed shapes — all skipped.

    The parser absorbs the malformed shapes (non-object tls, wrong keys),
    so they reach the cert coordinator as routers without a probe target.
    Traefik wildcard / default-cert setups leave no useful probe target either.
    """
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot(
        routers=[
            {"name": "r1", "tls": {}, "rule": ""},  # TLS set but empty
            {"name": "r2", "tls": {"domains": []}, "rule": ""},  # empty domains list
            {"name": "r3", "tls": {"not_domains": "x"}, "rule": ""},  # wrong key
            {"name": "r4", "rule": "Path(`/api`)"},  # no Host() in rule
            {"name": "not-a-dict"},  # malformed
            {"name": "r5", "tls": "should-be-dict", "rule": ""},  # wrong tls type
            {
                "name": "r6",
                "tls": {
                    "domains": [
                        {"main": "good.example.com"},
                    ],
                },
                "rule": "Host(`good.example.com`)",
            },  # valid — should appear
        ],
    )
    c = CertCoordinator(MagicMock(), entry)
    hosts = c._collect_hosts()
    assert hosts == ("good.example.com",)


def test_collect_hosts_handles_sans_as_string_or_list() -> None:
    """Sans can be a string OR a list (Traefik v3 spec)."""
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot(
        routers=[
            {
                "name": "r1",
                "tls": {"domains": [{"main": "h.example.com", "sans": "alt.example.com"}]},
                "rule": "",
            },
            {
                "name": "r2",
                "tls": {
                    "domains": [
                        {
                            "main": "h2.example.com",
                            "sans": ["a.example.com", "b.example.com"],
                        },
                    ],
                },
                "rule": "",
            },
            {
                "name": "r3",
                "tls": {"domains": [{"main": "h3.example.com", "sans": 42}]},
                "rule": "",
            },  # bad sans type → main still picked up
        ],
    )
    c = CertCoordinator(MagicMock(), entry)
    hosts = c._collect_hosts()
    assert hosts == tuple(sorted(hosts))
    assert {
        "h.example.com",
        "alt.example.com",
        "h2.example.com",
        "a.example.com",
        "b.example.com",
        "h3.example.com",
    }.issubset(hosts)


def test_collect_hosts_multi_host_rules_and_domains() -> None:
    """v2 multi-argument rules, normalized domains, skipped wildcards, non-TLS routers ignored."""
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot(
        routers=[
            {
                "name": "r1",
                "tls": {},
                "rule": "Host(`a.example.com`, `b.example.com`)",
            },
            {
                "name": "r2",
                "tls": {
                    "domains": [
                        {"main": "C.example.com", "sans": ["*.wild.example.com", "d.example.com"]},
                    ],
                },
                "rule": "",
            },
            {
                "name": "r3",
                "rule": "Host(`x.example.com`)",
            },
        ],
    )
    c = CertCoordinator(MagicMock(), entry)
    assert c._collect_hosts() == (
        "a.example.com",
        "b.example.com",
        "c.example.com",
        "d.example.com",
    )


def test_collect_hosts_skips_regex_sni_and_negated_names() -> None:
    """HostRegexp, HostSNI and negated Host() names never become probe targets."""
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot(
        routers=[
            {
                "name": "r1",
                "tls": {},
                "rule": "HostRegexp(`{sub:[a-z]+}.example.com`) || HostSNI(`sni.example.com`)",
            },
            {
                "name": "r2",
                "tls": {},
                "rule": "PathPrefix(`/x`) && !Host(`neg.example.com`) || Host(`Ok.Example.com.`)",
            },
        ],
    )
    c = CertCoordinator(MagicMock(), entry)
    assert c._collect_hosts() == ("ok.example.com",)


async def test_full_setup_registers_cert_entities_for_alt_host(
    hass: Any, aioclient_mock: Any, mock_tls_probe: AsyncMock
) -> None:
    """A v2 multi-argument rule in the v3.7 capture yields cert entities for every host."""
    rawdata = rawdata_copy("v3.7")
    rawdata["routers"]["secure@file"]["rule"] = "Host(`secure.example.com`, `alt.example.com`)"
    entry = await setup_traefik_entry(hass, aioclient_mock, rawdata=rawdata)

    probed = {call.args[0] for call in mock_tls_probe.call_args_list}
    assert "alt.example.com" in probed
    entity_id_for(hass, CERT_EXPIRY.domain, CERT_EXPIRY.unique_id(entry.entry_id, "alt.example.com"))
    entity_id_for(hass, CERT_EXPIRING.domain, CERT_EXPIRING.unique_id(entry.entry_id, "alt.example.com"))


# ---------------------------------------------------------------------------
# Host limit (MAX_CERT_HOSTS)
# ---------------------------------------------------------------------------

_CERT_LOGGER = "custom_components.traefik_proxy.cert_coordinator"


def _entry_with_hosts(count: int) -> MagicMock:
    """Entry whose snapshot has ``count`` TLS routers, one distinct host each."""
    entry = _make_entry()
    entry.runtime_data.coordinator.data = make_snapshot(
        routers=[{"name": f"r{i:03d}", "tls": {}, "rule": f"Host(`h{i:03d}.example.com`)"} for i in range(count)],
    )
    return entry


def _cap_warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == _CERT_LOGGER and r.levelno >= logging.WARNING]


def test_max_cert_hosts_is_200() -> None:
    """The host limit is a fixed constant of 200."""
    assert MAX_CERT_HOSTS == 200


@pytest.mark.parametrize("count", [199, 200])
def test_collect_hosts_cap_not_reached(count: int, caplog: pytest.LogCaptureFixture) -> None:
    """Up to the limit every host is kept and nothing is logged."""
    caplog.set_level(logging.WARNING, logger=_CERT_LOGGER)
    c = CertCoordinator(MagicMock(), _entry_with_hosts(count))
    hosts = c._collect_hosts()
    assert len(hosts) == count
    assert hosts == tuple(sorted(hosts))
    assert _cap_warnings(caplog) == []


def test_collect_hosts_cap_201_drops_last_sorted(caplog: pytest.LogCaptureFixture) -> None:
    """201 hosts keep the first 200 in sorted order and log one WARNING naming 1 dropped host."""
    caplog.set_level(logging.WARNING, logger=_CERT_LOGGER)
    c = CertCoordinator(MagicMock(), _entry_with_hosts(201))
    hosts = c._collect_hosts()
    assert len(hosts) == 200
    assert hosts[0] == "h000.example.com"
    assert hosts[-1] == "h199.example.com"
    assert "h200.example.com" not in hosts
    warnings = _cap_warnings(caplog)
    assert len(warnings) == 1
    assert warnings[0].args == (200, 1)


async def test_cert_cycle_cap_250_probes_200(caplog: pytest.LogCaptureFixture) -> None:
    """250 hosts lead to exactly 200 probes and one WARNING naming 50, without host names."""
    caplog.set_level(logging.DEBUG, logger=_CERT_LOGGER)
    c = CertCoordinator(MagicMock(), _entry_with_hosts(250))

    async def fake_probe(host: str, port: int = 443, **_kwargs: object) -> CertError:
        return _cert_error(host=host)

    probe = AsyncMock(side_effect=fake_probe)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("custom_components.traefik_proxy.cert_coordinator.fetch_cert_info_async", probe)
        data = await c._async_update_data()

    assert probe.call_count == 200
    assert len(data) == 200
    warnings = _cap_warnings(caplog)
    assert len(warnings) == 1
    assert warnings[0].args == (200, 50)
    assert "50" in warnings[0].getMessage()
    for record in caplog.records:
        assert ".example.com" not in record.getMessage()


async def test_cert_cycle_cap_warns_once_per_cycle(caplog: pytest.LogCaptureFixture) -> None:
    """Two cycles over 250 hosts log exactly two WARNINGs."""
    caplog.set_level(logging.WARNING, logger=_CERT_LOGGER)
    c = CertCoordinator(MagicMock(), _entry_with_hosts(250))

    async def fake_probe(host: str, port: int = 443, **_kwargs: object) -> CertError:
        return _cert_error(host=host)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "custom_components.traefik_proxy.cert_coordinator.fetch_cert_info_async",
            AsyncMock(side_effect=fake_probe),
        )
        await c._async_update_data()
        await c._async_update_data()

    assert len(_cap_warnings(caplog)) == 2
