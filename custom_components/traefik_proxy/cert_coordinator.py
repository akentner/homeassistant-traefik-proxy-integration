"""Cert coordinator: per-host certificate state of the Traefik TLS routers.

The cert coordinator is stored next to the main coordinator on
``entry.runtime_data`` and runs on its own slow cadence. Every cycle reads
the TLS hosts of the main coordinator's latest snapshot and then asks
Traefik for its certificates (``GET /api/certificates``, Traefik >= 3.7):

- When Traefik answers, every host maps to the certificate that covers it.
  No TLS connection is opened. A host no certificate covers is reported as
  ``not_found`` and is never probed: a probe would read Traefik's default
  certificate and make a broken host look healthy.
- When Traefik answers 404 (older versions), each host is probed once: a
  TLS handshake to the Traefik host of the entry URL, on the TLS entrypoint
  port of the host's routers, with the router host as SNI name, at most
  ``TLS_SEMAPHORE`` handshakes at a time. Router hostnames are never
  resolved through DNS. The presented chain is verified against Home
  Assistant's own trust anchors (read from memory, never from disk).
- Any other API error fails the cycle.

The result is one :class:`HostCertState` per host of the current host set.
Days until expiry are never stored; entities compute them from the clock at
read time. One timer fires at the earliest moment a host's whole-day count
changes and notifies the listeners, so threshold crossings, expiry and the
daily countdown reach the entities when they happen, without a new cycle.
A cycle never fails because a probe failed; a failed probe is part of the
host's state.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Final
from urllib.parse import urlsplit

from cryptography.x509.verification import Store
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util import ssl as ha_ssl

from .api import TraefikProxyApiError, TraefikProxyNotFoundError
from .const import (
    CERT_RETRY_INTERVAL,
    CONF_URL,
    DEFAULT_TLS_CERT_COOLDOWN,
    DEFAULT_TLS_WARN_DAYS,
    MAX_CERT_HOSTS,
    TLS_HANDSHAKE_TIMEOUT,
    TLS_SEMAPHORE,
)
from .models import Router, TraefikCertificate, TraefikSnapshot
from .rules import extract_hosts, normalize_host
from .tls import ProbedCertificate, ProbeResult, async_probe_certificate, build_trust_store, match_certificate

if TYPE_CHECKING:
    from .data import TraefikProxyConfigEntry

_LOGGER = logging.getLogger(__name__)

# Port probed when no TLS entrypoint port of a host's routers resolves.
DEFAULT_PROBE_PORT: Final = 443
# Consecutive failed probes after which a host is a problem.
CERT_FAILURES_FOR_PROBLEM: Final = 2
# ``error`` of a host the Traefik API reports no certificate for.
NOT_FOUND: Final = "not_found"
DAY: Final = timedelta(days=1)
# How long after a whole-day boundary the day-boundary timer fires.
DAY_CHANGE_DELAY: Final = timedelta(seconds=1)


class CertSource(StrEnum):
    """Where a host's certificate state came from."""

    API = "api"
    PROBE = "probe"


class CertProblem(StrEnum):
    """Why a host's certificate is a problem, in precedence order."""

    EXPIRED = "expired"
    PROBE_FAILED = "probe_failed"
    NOT_FOUND = "not_found"
    EXPIRING = "expiring"


def entrypoint_port(address: str) -> int | None:
    """Return the TCP port of a Traefik entrypoint address, or None.

    Accepts ``:443``, ``0.0.0.0:443``, ``[::]:443`` and a trailing ``/tcp``.
    UDP addresses, non-numeric ports and ports outside 1..65535 give None.
    """
    if address.endswith("/udp"):
        return None
    address = address.removesuffix("/tcp")
    _, sep, port = address.rpartition(":")
    if not sep or not port.isascii() or not port.isdigit():
        return None
    value = int(port)
    return value if 1 <= value <= 65535 else None


def _router_hosts(router: Router) -> set[str]:
    """Return the normalized hostnames a TLS router contributes (empty without TLS).

    The union of ``tls_domains[].main`` / ``sans`` and the literal
    ``Host()`` names of the rule; names :func:`.rules.normalize_host`
    rejects are skipped.
    """
    if not router.tls:
        return set()
    hosts: set[str] = set()
    for domain in router.tls_domains:
        for name in (domain.main, *domain.sans):
            host = normalize_host(name) if name else None
            if host is not None:
                hosts.add(host)
    hosts.update(extract_hosts(router.rule))
    return hosts


def _router_ports(router: Router, snapshot: TraefikSnapshot) -> set[int]:
    """Return the TCP ports of a router's entry points (unknown names and UDP skipped)."""
    ports: set[int] = set()
    for name in router.entry_points:
        entrypoint = snapshot.entrypoints.get(name)
        port = entrypoint_port(entrypoint.address) if entrypoint is not None else None
        if port is not None:
            ports.add(port)
    return ports


@dataclass(frozen=True, slots=True)
class HostCertState:
    """Certificate state of one TLS host.

    ``certificate`` is the last known certificate (None until one was read).
    ``verified`` and ``san_mismatch`` belong to that certificate. ``error``
    is the code of the last failed attempt (None after a success) and
    ``failures`` the number of consecutive failed probes. ``fetched_at`` is
    when ``certificate`` was read.
    """

    host: str
    source: CertSource
    certificate: TraefikCertificate | None
    verified: bool | None
    san_mismatch: bool | None
    port: int | None
    error: str | None
    failures: int
    fetched_at: datetime | None

    def days_left(self, now: datetime) -> int | None:
        """Return the signed whole days until ``not_after`` (floor), or None without a certificate."""
        if self.certificate is None:
            return None
        return (self.certificate.not_after - now) // DAY

    def next_day_change(self, now: datetime) -> datetime | None:
        """Return the first instant after ``now`` with a lower :meth:`days_left`, or None without a certificate.

        That is one second after the floor-day count drops, so a timer firing
        then always computes the new value.
        """
        days = self.days_left(now)
        if self.certificate is None or days is None:
            return None
        return self.certificate.not_after - days * DAY + DAY_CHANGE_DELAY

    def problem(self, threshold_days: int, now: datetime) -> CertProblem | None:
        """Return the host's problem by precedence, or None when it has none."""
        days = self.days_left(now)
        if days is not None and days < 0:
            return CertProblem.EXPIRED
        if self.failures >= CERT_FAILURES_FOR_PROBLEM:
            return CertProblem.PROBE_FAILED
        if self.error == NOT_FOUND:
            return CertProblem.NOT_FOUND
        if days is not None and days <= threshold_days:
            return CertProblem.EXPIRING
        return None

    def is_problem(self, threshold_days: int, now: datetime) -> bool | None:
        """Return True for any problem, None without a certificate, else False."""
        if self.problem(threshold_days, now) is not None:
            return True
        if self.certificate is None:
            return None
        return False


class CertCoordinator(DataUpdateCoordinator[dict[str, HostCertState]]):
    """Certificate cycle keyed by hostname.

    Every cycle collects the sorted, normalized, capped TLS hosts of the
    main snapshot (:meth:`_collect_hosts`) and reads Traefik's certificate
    list. With the list, each host is mapped to its certificate
    (:meth:`_api_states`); on a 404 each host is probed once, concurrently
    under the semaphore, on its TLS entrypoint port (:meth:`_probe_ports`)
    and against the trust store of :meth:`_get_trust_store`
    (:meth:`_async_probe_states`). ``data`` maps each host to its
    :class:`HostCertState`.

    Threshold changes (``tls_warn_days`` in the options) go through
    :meth:`async_set_threshold`, which notifies the listeners so the
    expiring sensors re-evaluate without a new probe. After every
    successful cycle one day-boundary timer is scheduled at the earliest
    :meth:`HostCertState.next_day_change` of the hosts; it notifies the
    listeners the same way and schedules the next one. Shutdown (entry
    unload) cancels it. After a failed cycle the next one runs after
    ``CERT_RETRY_INTERVAL``; a successful cycle restores the normal
    interval.
    """

    config_entry: TraefikProxyConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: TraefikProxyConfigEntry,
        *,
        threshold_days: int | None = None,
        sem: int = TLS_SEMAPHORE,
        timeout: float = TLS_HANDSHAKE_TIMEOUT,
        update_interval_seconds: int = DEFAULT_TLS_CERT_COOLDOWN,
        trust_store: Store | None = None,
    ) -> None:
        """Construct the cert coordinator.

        ``trust_store`` holds the roots a probed chain is verified against.
        Without one the first probe-mode cycle builds a store from Home
        Assistant's trust anchors (:meth:`_get_trust_store`).
        """
        super().__init__(
            hass,
            _LOGGER,
            name=f"{entry.title or 'Traefik'} certs",
            config_entry=entry,
            update_interval=timedelta(seconds=update_interval_seconds),
        )
        self.threshold_days = (
            threshold_days
            if threshold_days is not None
            else int(entry.options.get("tls_warn_days", DEFAULT_TLS_WARN_DAYS))
        )
        self._sem = asyncio.Semaphore(sem)
        self._timeout = timeout
        self._trust_store = trust_store
        # False until the default store was built; the built store may be None.
        self._trust_store_ready = trust_store is not None
        self._unsub_day_boundary: CALLBACK_TYPE | None = None
        self._normal_interval = timedelta(seconds=update_interval_seconds)
        self._retry_interval = timedelta(seconds=CERT_RETRY_INTERVAL)

    async def _async_update_data(self) -> dict[str, HostCertState]:
        """Run one cert cycle, set the next interval and schedule the day-boundary timer.

        Any failure switches to the retry interval; Home Assistant schedules
        the next cycle from ``update_interval`` after this returns or raises.
        A cancelled cycle changes neither.
        """
        try:
            states = await self._async_cycle()
        except Exception:
            self.update_interval = self._retry_interval
            raise
        self.update_interval = self._normal_interval
        self._async_schedule_day_boundary(states)
        return states

    async def _async_cycle(self) -> dict[str, HostCertState]:
        """Run one cert cycle over the current host set."""
        hosts = self._collect_hosts()
        now = dt_util.utcnow()
        try:
            certificates = await self.config_entry.runtime_data.client.async_get_certificates()
        except TraefikProxyNotFoundError:
            # Traefik < 3.7 has no certificate list: probe every host.
            return await self._async_probe_states(hosts, now)
        except TraefikProxyApiError as err:
            # The message is "<path>: <detail>" and never carries a URL or credential.
            raise UpdateFailed(f"Reading certificates failed: {err}") from err
        return self._api_states(hosts, certificates, now)

    @staticmethod
    def _api_states(
        hosts: Sequence[str], certificates: Sequence[TraefikCertificate], now: datetime
    ) -> dict[str, HostCertState]:
        """Map every host to the API certificate that covers it, in host order.

        A host without a covering certificate gets no certificate and the
        ``not_found`` error; it is never probed. The certificate's own
        ``status`` field is kept on the certificate and never read here.
        """
        states: dict[str, HostCertState] = {}
        for host in hosts:
            certificate = match_certificate(host, certificates)
            if certificate is None:
                states[host] = HostCertState(
                    host=host,
                    source=CertSource.API,
                    certificate=None,
                    verified=None,
                    san_mismatch=None,
                    port=None,
                    error=NOT_FOUND,
                    failures=0,
                    fetched_at=None,
                )
                continue
            states[host] = HostCertState(
                host=host,
                source=CertSource.API,
                certificate=certificate,
                verified=None,
                san_mismatch=False,
                port=None,
                error=None,
                failures=0,
                fetched_at=now,
            )
        return states

    def _connect_host(self) -> str:
        """Return the Traefik host of the entry URL; every probe connects there."""
        url: str = self.config_entry.data[CONF_URL]
        host = urlsplit(url).hostname
        if host is None:
            raise UpdateFailed("The Traefik URL has no host to probe certificates at")
        return host

    def _get_trust_store(self) -> Store | None:
        """Return the store probed chains are verified against.

        The ``trust_store`` given at construction, else a store built once
        from the roots of Home Assistant's pre-built client context (an
        in-memory read) and cached, None included.
        """
        if not self._trust_store_ready:
            self._trust_store = build_trust_store(ha_ssl.client_context().get_ca_certs(binary_form=True))
            self._trust_store_ready = True
        return self._trust_store

    def _probe_ports(self, hosts: Sequence[str]) -> dict[str, int]:
        """Return the port each host is probed on.

        The candidates of a host are the TLS entrypoint ports of every
        router that carries it. 443 wins when it is a candidate, else the
        lowest candidate; without any candidate the host is probed on 443.
        """
        snapshot = self.config_entry.runtime_data.coordinator.data
        candidates: dict[str, set[int]] = {host: set() for host in hosts}
        for router in snapshot.routers.values():
            router_hosts = _router_hosts(router) & candidates.keys()
            if not router_hosts:
                continue
            ports = _router_ports(router, snapshot)
            for host in router_hosts:
                candidates[host] |= ports
        return {
            host: DEFAULT_PROBE_PORT if not ports or DEFAULT_PROBE_PORT in ports else min(ports)
            for host, ports in candidates.items()
        }

    async def _async_probe_states(self, hosts: Sequence[str], now: datetime) -> dict[str, HostCertState]:
        """Probe every host once on its port and return their states in host order.

        The dict is built only after every probe returned, so a cancelled
        cycle leaves ``data`` untouched.
        """
        if not hosts:
            return {}
        connect_host = self._connect_host()
        ports = self._probe_ports(hosts)
        trust_store = self._get_trust_store()
        results = await asyncio.gather(
            *(self._async_probe_host(host, ports[host], connect_host, trust_store, now) for host in hosts)
        )
        # Only hosts of this cycle's host set are kept; history comes from the last data.
        previous = self.data or {}
        return {
            host: self._probe_state(host, ports[host], result, previous.get(host), now)
            for host, result in zip(hosts, results, strict=True)
        }

    async def _async_probe_host(
        self, host: str, port: int, connect_host: str, trust_store: Store | None, now: datetime
    ) -> ProbeResult:
        """Probe ``host`` (as SNI) at ``connect_host:port`` under the semaphore."""
        async with self._sem:
            return await async_probe_certificate(
                connect_host,
                port,
                host,
                handshake_timeout=self._timeout,
                trust_store=trust_store,
                now=now,
            )

    @staticmethod
    def _probe_state(
        host: str, port: int, result: ProbeResult, previous: HostCertState | None, now: datetime
    ) -> HostCertState:
        """Map one probe result and the host's previous state to its new state.

        A success replaces the certificate and resets the failures. A failure
        keeps the last known certificate with its trust flags and read time
        (from either source) and counts one more consecutive failure.
        """
        if isinstance(result, ProbedCertificate):
            return HostCertState(
                host=host,
                source=CertSource.PROBE,
                certificate=result.certificate,
                verified=result.verified,
                san_mismatch=result.san_mismatch,
                port=port,
                error=None,
                failures=0,
                fetched_at=now,
            )
        _LOGGER.debug("Certificate probe of %s failed: %s (%s)", host, result.error.value, result.detail)
        return HostCertState(
            host=host,
            source=CertSource.PROBE,
            certificate=previous.certificate if previous is not None else None,
            verified=previous.verified if previous is not None else None,
            san_mismatch=previous.san_mismatch if previous is not None else None,
            port=port,
            error=result.error.value,
            failures=previous.failures + 1 if previous is not None else 1,
            fetched_at=previous.fetched_at if previous is not None else None,
        )

    @callback
    def _async_schedule_day_boundary(self, states: dict[str, HostCertState]) -> None:
        """Replace the day-boundary timer with one at the earliest day change of ``states``.

        No timer is scheduled when no host has a certificate.
        """
        if self._unsub_day_boundary is not None:
            self._unsub_day_boundary()
            self._unsub_day_boundary = None
        now = dt_util.utcnow()
        changes = [when for state in states.values() if (when := state.next_day_change(now)) is not None]
        if changes:
            self._unsub_day_boundary = async_track_point_in_utc_time(
                self.hass, self._async_handle_day_boundary, min(changes)
            )

    @callback
    def _async_handle_day_boundary(self, _now: datetime) -> None:
        """Let the listeners re-evaluate at a day boundary, then schedule the next one."""
        self._unsub_day_boundary = None
        self.async_update_listeners()
        self._async_schedule_day_boundary(self.data or {})

    async def async_shutdown(self) -> None:
        """Cancel the day-boundary timer, then shut the coordinator down."""
        if self._unsub_day_boundary is not None:
            self._unsub_day_boundary()
            self._unsub_day_boundary = None
        await super().async_shutdown()

    async def async_set_threshold(self, threshold_days: int) -> None:
        """Update the warning threshold live and notify the listeners (no new probe)."""
        self.threshold_days = int(threshold_days)
        self.async_update_listeners()

    def _collect_hosts(self) -> tuple[str, ...]:
        """Return the sorted, normalized hostnames to probe in this cycle.

        Reads the routers of the main coordinator's snapshot through
        ``self.config_entry.runtime_data.coordinator.data``. Traefik-internal
        routers are not part of the snapshot, so they never become probe
        targets. Routers without TLS are skipped.

        For each TLS router, hostnames come from the union of:

        - ``tls_domains[].main`` and ``tls_domains[].sans`` — the names
          requested for the certificate;
        - the literal ``Host()`` names of the rule (:func:`.rules.extract_hosts`)
          — the routing-side names, which may be covered by a wildcard
          certificate whose main domain differs.

        Every name goes through :func:`.rules.normalize_host`; wildcard,
        regex, SNI and template names are skipped. A TLS router without
        domains and without a literal ``Host()`` name contributes no host.

        At most ``MAX_CERT_HOSTS`` names are returned: the first ones in
        sorted order, so the same hosts stay probed across cycles. A cut is
        logged once per call with the counts only, never the names.
        """
        hosts: set[str] = set()
        for router in self.config_entry.runtime_data.coordinator.data.routers.values():
            hosts |= _router_hosts(router)
        ordered = sorted(hosts)
        if len(ordered) > MAX_CERT_HOSTS:
            _LOGGER.warning(
                "Certificate host limit of %d reached; %d hosts are not checked",
                MAX_CERT_HOSTS,
                len(ordered) - MAX_CERT_HOSTS,
            )
        return tuple(ordered[:MAX_CERT_HOSTS])

    def get_threshold(self) -> int:
        """Return the current warning threshold (read accessor)."""
        return self.threshold_days


__all__ = [
    "CERT_FAILURES_FOR_PROBLEM",
    "NOT_FOUND",
    "CertCoordinator",
    "CertProblem",
    "CertSource",
    "HostCertState",
    "entrypoint_port",
]
