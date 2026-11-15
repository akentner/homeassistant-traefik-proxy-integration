"""Cert coordinator: per-host certificate state of the Traefik TLS routers.

The cert coordinator is stored next to the main coordinator on
``entry.runtime_data`` and runs on its own slow cadence. Every cycle reads
the TLS hosts of the main coordinator's latest snapshot (no extra Traefik
API call) and probes each host once: a TLS handshake to the Traefik host of
the entry URL with the router host as SNI name, at most ``TLS_SEMAPHORE``
handshakes at a time. Router hostnames are never resolved through DNS.

The result is one :class:`HostCertState` per host of the current host set.
Days until expiry are never stored; entities compute them from the clock at
read time. A cycle never fails because a probe failed; a failed probe is
part of the host's state.
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
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_URL,
    DEFAULT_TLS_CERT_COOLDOWN,
    DEFAULT_TLS_WARN_DAYS,
    MAX_CERT_HOSTS,
    TLS_HANDSHAKE_TIMEOUT,
    TLS_SEMAPHORE,
)
from .models import TraefikCertificate
from .rules import extract_hosts, normalize_host
from .tls import ProbedCertificate, ProbeResult, async_probe_certificate

if TYPE_CHECKING:
    from .data import TraefikProxyConfigEntry

_LOGGER = logging.getLogger(__name__)

# Port probed on the Traefik host.
PROBE_PORT: Final = 443
# Consecutive failed probes after which a host is a problem.
CERT_FAILURES_FOR_PROBLEM: Final = 2
# ``error`` of a host the Traefik API reports no certificate for.
NOT_FOUND: Final = "not_found"
DAY: Final = timedelta(days=1)


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
    main snapshot (:meth:`_collect_hosts`) and probes each one concurrently
    under the semaphore; ``data`` maps each host to its
    :class:`HostCertState`.

    Threshold changes (``tls_warn_days`` in the options) go through
    :meth:`async_set_threshold`, which notifies the listeners so the
    expiring sensors re-evaluate without a new probe.
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

        ``trust_store`` holds the roots a probed chain is verified against;
        without one every probed certificate reports ``verified`` False.
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

    async def _async_update_data(self) -> dict[str, HostCertState]:
        """Run one cert cycle over the current host set."""
        hosts = self._collect_hosts()
        now = dt_util.utcnow()
        return await self._async_probe_states(hosts, now)

    def _connect_host(self) -> str:
        """Return the Traefik host of the entry URL; every probe connects there."""
        url: str = self.config_entry.data[CONF_URL]
        host = urlsplit(url).hostname
        if host is None:
            raise UpdateFailed("The Traefik URL has no host to probe certificates at")
        return host

    async def _async_probe_states(self, hosts: Sequence[str], now: datetime) -> dict[str, HostCertState]:
        """Probe every host and return their states in host order."""
        if not hosts:
            return {}
        connect_host = self._connect_host()
        results = await asyncio.gather(*(self._async_probe_host(host, PROBE_PORT, connect_host, now) for host in hosts))
        return {
            host: self._probe_state(host, PROBE_PORT, result, now) for host, result in zip(hosts, results, strict=True)
        }

    async def _async_probe_host(self, host: str, port: int, connect_host: str, now: datetime) -> ProbeResult:
        """Probe ``host`` (as SNI) at ``connect_host:port`` under the semaphore."""
        async with self._sem:
            return await async_probe_certificate(
                connect_host,
                port,
                host,
                handshake_timeout=self._timeout,
                trust_store=self._trust_store,
                now=now,
            )

    @staticmethod
    def _probe_state(host: str, port: int, result: ProbeResult, now: datetime) -> HostCertState:
        """Map one probe result to the host's state."""
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
            certificate=None,
            verified=None,
            san_mismatch=None,
            port=port,
            error=result.error.value,
            failures=1,
            fetched_at=None,
        )

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
            if not router.tls:
                continue
            for domain in router.tls_domains:
                for name in (domain.main, *domain.sans):
                    host = normalize_host(name) if name else None
                    if host is not None:
                        hosts.add(host)
            hosts.update(extract_hosts(router.rule))
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
]
