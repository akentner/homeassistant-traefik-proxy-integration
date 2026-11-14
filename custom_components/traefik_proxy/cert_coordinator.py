"""Cert-coordinator side of Phase 3: 6h TLS-handshake cycle with bounded concurrency.

This module is the cert coordinator (stored next to the main coordinator
on ``entry.runtime_data``) that runs every 6 hours and probes every
distinct hostname extracted from the routers of the main
coordinator's snapshot. It is the data path Phase 3 entities depend on
(TLS-03, TLS-04, TLS-05); the entity platforms land in plan 03-02 and
the test surface lands in plan 03-03.

Design contracts locked by CONTEXT.md and spike 004:

- CONTEXT.md D-05 — bounded concurrent handshakes
  (``asyncio.Semaphore(4)``) and per-host ``asyncio.timeout(5)`` so a
  hanging host cannot stall the cycle indefinitely.
- CONTEXT.md D-06 — in-memory ``dict[str, CertInfo | CertError]`` cache;
  errors are kept in the cache (not just successes) so a single
  transient failure does not erase the prior result on the next cycle.
- CONTEXT.md D-07 — independent of the main ``TraefikProxyCoordinator`` cycle;
  a TLS failure on one hostname never marks the main coordinator as
  failed.
- CONTEXT.md D-10 — every error path becomes a typed ``CertError`` and
  is recorded in the cache; nothing propagates as an exception.
- PITFALLS #14 — read hostnames from the main coordinator's
  snapshot routers (already polled at the 15s scan
  interval) rather than re-polling the Traefik HTTP API; the cert
  cycle is much slower than the main cycle (6h vs 15s).
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DEFAULT_TLS_CERT_COOLDOWN,
    DEFAULT_TLS_WARN_DAYS,
    TLS_HANDSHAKE_TIMEOUT,
    TLS_SEMAPHORE,
)
from .tls import CertError, CertInfo, fetch_cert_info_async

if TYPE_CHECKING:
    from .data import TraefikProxyConfigEntry

_LOGGER = logging.getLogger(__name__)

# Pull the ``Host(`...`)`` substring out of a Traefik rule string. Copied
# from ``binary_sensor.py`` (Phase 1 origin) so this module does not import
# a platform module.
_HOST_FROM_RULE = re.compile(r"Host\(`([^`]+)`\)")


class CertCoordinator(DataUpdateCoordinator[dict[str, CertInfo | CertError]]):
    """Background 6h TLS-handshake cycle keyed by hostname.

    Every cycle:

    1. Reads the routers of the main ``TraefikProxyCoordinator`` snapshot
       (no direct Traefik HTTP API call — main cycle already covers
       that at the 15s scan interval).
    2. Extracts the deduplicated union of hostnames from
       ``tls_domains[].main`` + ``tls_domains[].sans`` + ``Host(...)``
       rule matches.
    3. Probes every hostname concurrently through
       ``asyncio.Semaphore(4)`` + ``asyncio.timeout(5)`` — each
       handshake runs on a worker thread via ``asyncio.to_thread`` so
       the HA event loop stays responsive.
    4. Writes the per-host result back to ``self.data`` keyed by
       hostname; ``CertInfo`` AND ``CertError`` are both kept (CONTEXT.md
       D-06 — errors surface on the entity, not just successes).

    Threshold mutations (``CONF_TLS_WARN_DAYS`` from the Options Flow)
    flow through :meth:`async_set_threshold` from the
    ``_async_options_updated`` listener — that path mutates
    ``threshold_days`` and calls :meth:`async_update_listeners` so the
    binary sensor re-renders immediately without re-handshaking.
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
    ) -> None:
        """Construct the cert coordinator with the spike-validated defaults.

        The ``config_entry=entry`` kwarg to ``super().__init__`` is the
        BLOCKER #1 fix — it auto-populates ``self.config_entry`` (the
        HA base class only sets it when the kwarg is provided), which
        in turn is what :meth:`_collect_hosts_from_main_coordinator`
        needs to read the main coordinator's ``data`` dict.
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
        # Optional port cache so future probes can override the default
        # 443 (tests inject custom ports via the test seam).
        self._host_port: dict[str, int] = {}

    async def _async_update_data(self) -> dict[str, CertInfo | CertError]:
        """One cert cycle — probe every distinct hostname in parallel.

        ``asyncio.gather(..., return_exceptions=False)`` documents the
        contract: :meth:`_probe` catches every exception internally so
        no exception is ever returned. The cycle can never raise.
        """
        hosts = self._collect_hosts_from_main_coordinator()
        tasks = [self._probe(host) for host in hosts]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return {host: result for host, result in zip(hosts, results, strict=False)}

    async def _probe(self, host: str, port: int = 443) -> CertInfo | CertError:
        """Probe one hostname with the bounded-concurrency wrapper.

        Defense in depth — ``fetch_cert_info`` itself never raises
        (CONTEXT.md D-10) but this method adds an
        ``asyncio.TimeoutError`` catch for handshake timeouts that
        aren't caught by the inner ``socket.timeout``, plus a final
        ``Exception`` catch for any other surprise. The cycle must
        never propagate.
        """
        async with self._sem:
            try:
                async with asyncio.timeout(self._timeout):
                    return await fetch_cert_info_async(host, port, timeout=self._timeout)
            except TimeoutError as exc:
                return {
                    "host": host,
                    "port": port,
                    "error": "timeout",
                    "detail": str(exc) or f"timeout after {self._timeout}s",
                }
            except Exception as exc:  # final-resort catch-all; every error path becomes a typed CertError
                return {
                    "host": host,
                    "port": port,
                    "error": "unreachable",
                    "detail": f"{type(exc).__name__}: {exc}",
                }

    async def async_set_threshold(self, threshold_days: int) -> None:
        """Update the warning threshold live (no re-handshake needed).

        The Options Flow listener (``_async_options_updated`` in
        ``__init__.py``) calls this whenever ``CONF_TLS_WARN_DAYS``
        changes. The cert data (``not_after``, ``days_until_expiry``)
        is unchanged; only the threshold applied to it shifts.
        ``async_update_listeners`` is the HA method that schedules a
        ``_ha_state_updated`` callback for every registered listener so
        the binary sensor re-renders within the next event-loop tick.
        """
        self.threshold_days = int(threshold_days)
        self.async_update_listeners()

    def _collect_hosts_from_main_coordinator(self) -> set[str]:
        """Build the deduplicated, lowercased hostname set for this cycle.

        Reads the routers of the main coordinator's snapshot through
        ``self.config_entry.runtime_data.coordinator.data`` (needs
        ``config_entry=entry`` set in ``__init__``). Traefik-internal
        routers are not part of the snapshot, so they never become probe
        targets. Routers without TLS are skipped.

        For each TLS router, hostnames come from the union of:

        - ``tls_domains[].main`` — primary domain on the cert
        - ``tls_domains[].sans`` — Subject Alternative Names on the cert
        - ``Host(`x`)`` regex matches in the rule — the routing-side
          hostname (may differ from the cert's main/SAN; e.g. a router
          named ``api.example.com`` may be served by a wildcard cert
          whose SAN covers ``api.example.com`` but the cert's main
          domain is the apex)

        A TLS router without domains and without a ``Host`` rule (wildcard
        / default cert, owned by Traefik) contributes no host.
        """
        hosts: set[str] = set()
        for router in self.config_entry.runtime_data.coordinator.data.routers.values():
            if not router.tls:
                continue
            for domain in router.tls_domains:
                if domain.main:
                    hosts.add(domain.main.lower())
                for san in domain.sans:
                    if san:
                        hosts.add(san.lower())
            # ``Host(`x`)`` matches in the rule (routing-side hostname).
            for match in _HOST_FROM_RULE.findall(router.rule):
                if isinstance(match, str) and match:
                    hosts.add(match.lower())
        return hosts

    def get_threshold(self) -> int:
        """Return the current warning threshold (read accessor)."""
        return self.threshold_days

    def _reset(self) -> None:
        """Clear the in-memory cache — test seam only, not exposed in the front door."""
        self.data = {}
        self._host_port = {}


__all__ = ["CertCoordinator"]
