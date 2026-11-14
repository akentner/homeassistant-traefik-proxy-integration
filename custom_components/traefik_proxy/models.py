"""Typed, immutable models of the Traefik API payloads.

Pure module: stdlib only, no Home Assistant imports and no import of the API
client. Parsers accept both payload shapes Traefik serves for HTTP items:

- the ``/api/rawdata`` map form, ``{"<name@provider>": {...}}``;
- the list form of ``/api/http/<kind>``, ``[{"name": "<name@provider>", ...}]``.

Shape violations raise ``TypeError`` / ``KeyError`` / ``ValueError``; the
client wraps them into its payload error. Optional fields with an unexpected
type are treated as absent. Item dicts are keyed by the exact Traefik name
(including the ``@provider`` suffix) and built in sorted name order.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

_LOGGER = logging.getLogger(__name__)

_INTERNAL_SUFFIX = "@internal"

# Distinct unknown status values already logged; bounded so a misbehaving
# server cannot grow it without limit.
_LOGGED_UNKNOWN_STATUSES: set[str | None] = set()
_MAX_LOGGED_UNKNOWN_STATUSES = 16

# Keys of an item that are not its configuration block. The single remaining
# key names the item type when the payload carries no ``type`` (rawdata form).
_SERVICE_META_KEYS = frozenset({"name", "provider", "type", "status", "error", "usedBy", "serverStatus"})
_MIDDLEWARE_META_KEYS = frozenset({"name", "provider", "type", "status", "error", "usedBy"})

_RAWDATA_SECTIONS = ("routers", "services", "middlewares")


class Status(StrEnum):
    """Item status as reported by Traefik, plus ``error``.

    Traefik reports ``enabled`` / ``warning`` / ``disabled``; a ``disabled``
    item with a non-empty ``error`` list is mapped to ``error``.
    """

    enabled = "enabled"
    warning = "warning"
    disabled = "disabled"
    error = "error"


@dataclass(frozen=True, slots=True)
class TlsDomain:
    """One ``tls.domains`` entry of a router."""

    main: str
    sans: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Router:
    """An HTTP router."""

    name: str
    provider: str
    status: Status
    rule: str
    service: str
    entry_points: tuple[str, ...]
    middlewares: tuple[str, ...]
    tls: bool
    tls_domains: tuple[TlsDomain, ...]
    errors: tuple[str, ...]
    using: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Service:
    """An HTTP service.

    Backend health is reduced to counts from ``serverStatus``; backend URLs
    and addresses are deliberately not stored.
    """

    name: str
    provider: str
    status: Status
    type: str
    servers_total: int
    servers_up: int
    used_by: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Middleware:
    """An HTTP middleware."""

    name: str
    provider: str
    status: Status
    type: str
    used_by: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Entrypoint:
    """An entrypoint; ``protocol`` is ``udp`` or ``tcp``."""

    name: str
    address: str
    protocol: str


@dataclass(frozen=True, slots=True)
class TraefikVersion:
    """The ``/api/version`` payload; ``start_date`` is timezone-aware."""

    version: str
    codename: str
    start_date: datetime


@dataclass(frozen=True, slots=True)
class StatusCounts:
    """Number of items per status."""

    total: int
    enabled: int
    warning: int
    error: int
    disabled: int

    @classmethod
    def of(cls, statuses: Iterable[Status]) -> StatusCounts:
        """Count ``statuses``."""
        counts = dict.fromkeys(Status, 0)
        for status in statuses:
            counts[status] += 1
        return cls(
            total=sum(counts.values()),
            enabled=counts[Status.enabled],
            warning=counts[Status.warning],
            error=counts[Status.error],
            disabled=counts[Status.disabled],
        )


@dataclass(frozen=True, slots=True)
class TraefikState:
    """HTTP routers, services and middlewares of one Traefik instance."""

    routers: dict[str, Router]
    services: dict[str, Service]
    middlewares: dict[str, Middleware]


@dataclass(frozen=True, slots=True)
class TraefikSnapshot:
    """Everything one coordinator cycle publishes, with precomputed aggregates."""

    version: TraefikVersion
    entrypoints: dict[str, Entrypoint]
    routers: dict[str, Router]
    services: dict[str, Service]
    middlewares: dict[str, Middleware]
    router_counts: StatusCounts
    service_counts: StatusCounts
    middleware_counts: StatusCounts
    router_problems: tuple[str, ...]
    service_problems: tuple[str, ...]
    middleware_problems: tuple[str, ...]

    @classmethod
    def build(
        cls, *, version: TraefikVersion, entrypoints: dict[str, Entrypoint], state: TraefikState
    ) -> TraefikSnapshot:
        """Build a snapshot and compute its counts and sorted problem names once.

        A service is a problem when its status is not ``enabled`` or when not
        all of its servers are up.
        """
        routers, services, middlewares = state.routers, state.services, state.middlewares
        return cls(
            version=version,
            entrypoints=entrypoints,
            routers=routers,
            services=services,
            middlewares=middlewares,
            router_counts=StatusCounts.of(r.status for r in routers.values()),
            service_counts=StatusCounts.of(s.status for s in services.values()),
            middleware_counts=StatusCounts.of(m.status for m in middlewares.values()),
            router_problems=tuple(sorted(n for n, r in routers.items() if r.status is not Status.enabled)),
            service_problems=tuple(
                sorted(
                    n for n, s in services.items() if s.status is not Status.enabled or s.servers_up < s.servers_total
                )
            ),
            middleware_problems=tuple(sorted(n for n, m in middlewares.items() if m.status is not Status.enabled)),
        )


def provider_from_name(name: str) -> str:
    """Return the provider suffix after the last ``@`` (``""`` when absent)."""
    _, sep, provider = name.rpartition("@")
    return provider if sep else ""


def is_internal(name: str) -> bool:
    """Return True for Traefik's own items (names ending in ``@internal``)."""
    return name.endswith(_INTERNAL_SUFFIX)


def _parse_status(item: Mapping[str, Any], errors: tuple[str, ...]) -> Status:
    raw = item.get("status")
    if raw == "disabled" and errors:
        return Status.error
    if isinstance(raw, str) and raw in Status.__members__:
        return Status(raw)
    key = raw if isinstance(raw, str) or raw is None else repr(raw)
    if key not in _LOGGED_UNKNOWN_STATUSES and len(_LOGGED_UNKNOWN_STATUSES) < _MAX_LOGGED_UNKNOWN_STATUSES:
        _LOGGED_UNKNOWN_STATUSES.add(key)
        _LOGGER.debug("Unknown Traefik status %r, treated as warning", key)
    return Status.warning


def _iter_items(payload: object) -> Iterator[tuple[str, Mapping[str, Any]]]:
    """Yield ``(name, item)`` in sorted name order, ``@internal`` items dropped."""
    items: dict[str, Mapping[str, Any]] = {}
    if isinstance(payload, Mapping):
        for name, item in payload.items():
            if not isinstance(name, str):
                raise TypeError(f"item key must be a string, got {type(name).__name__}")
            if not isinstance(item, Mapping):
                raise TypeError(f"item {name!r} must be an object, got {type(item).__name__}")
            items[name] = item
    elif isinstance(payload, list):
        for item in payload:
            if not isinstance(item, Mapping):
                raise TypeError(f"item must be an object, got {type(item).__name__}")
            name = item["name"]
            if not isinstance(name, str):
                raise TypeError(f"item name must be a string, got {type(name).__name__}")
            items[name] = item
    else:
        raise TypeError(f"expected an object or a list, got {type(payload).__name__}")
    for name in sorted(items):
        if not is_internal(name):
            yield name, items[name]


def _str(item: Mapping[str, Any], key: str) -> str:
    value = item.get(key)
    return value if isinstance(value, str) else ""


def _required_str(item: Mapping[str, Any], key: str) -> str:
    value = item[key]
    if not isinstance(value, str):
        raise TypeError(f"{key!r} must be a string, got {type(value).__name__}")
    return value


def _str_tuple(item: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = item.get(key)
    if not isinstance(value, list):
        return ()
    return tuple(entry for entry in value if isinstance(entry, str))


def _item_type(item: Mapping[str, Any], meta_keys: frozenset[str]) -> str:
    """Return the list-form ``type``, else the lowercased single config key."""
    if "type" in item:
        return _str(item, "type")
    config_keys = [key for key in item if key not in meta_keys]
    return config_keys[0].lower() if len(config_keys) == 1 else ""


def _tls_domains(tls: Mapping[str, Any]) -> tuple[TlsDomain, ...]:
    domains = tls.get("domains")
    if not isinstance(domains, list):
        return ()
    result: list[TlsDomain] = []
    for domain in domains:
        if not isinstance(domain, Mapping):
            continue
        main = _str(domain, "main")
        raw_sans = domain.get("sans")
        if isinstance(raw_sans, str):
            sans: tuple[str, ...] = (raw_sans,) if raw_sans else ()
        else:
            sans = _str_tuple(domain, "sans")
        if main or sans:
            result.append(TlsDomain(main=main, sans=sans))
    return tuple(result)


def _router(name: str, item: Mapping[str, Any]) -> Router:
    errors = _str_tuple(item, "error")
    tls = item.get("tls")
    return Router(
        name=name,
        provider=provider_from_name(name),
        status=_parse_status(item, errors),
        rule=_str(item, "rule"),
        service=_str(item, "service"),
        entry_points=_str_tuple(item, "entryPoints"),
        middlewares=_str_tuple(item, "middlewares"),
        tls=isinstance(tls, Mapping),
        tls_domains=_tls_domains(tls) if isinstance(tls, Mapping) else (),
        errors=errors,
        using=_str_tuple(item, "using"),
    )


def _service(name: str, item: Mapping[str, Any]) -> Service:
    errors = _str_tuple(item, "error")
    server_status = item.get("serverStatus")
    states = list(server_status.values()) if isinstance(server_status, Mapping) else []
    return Service(
        name=name,
        provider=provider_from_name(name),
        status=_parse_status(item, errors),
        type=_item_type(item, _SERVICE_META_KEYS),
        servers_total=len(states),
        servers_up=sum(1 for state in states if state == "UP"),
        used_by=_str_tuple(item, "usedBy"),
        errors=errors,
    )


def _middleware(name: str, item: Mapping[str, Any]) -> Middleware:
    errors = _str_tuple(item, "error")
    return Middleware(
        name=name,
        provider=provider_from_name(name),
        status=_parse_status(item, errors),
        type=_item_type(item, _MIDDLEWARE_META_KEYS),
        used_by=_str_tuple(item, "usedBy"),
        errors=errors,
    )


def parse_routers(payload: object) -> dict[str, Router]:
    """Parse HTTP routers from the rawdata map or a list page."""
    return {name: _router(name, item) for name, item in _iter_items(payload)}


def parse_services(payload: object) -> dict[str, Service]:
    """Parse HTTP services from the rawdata map or a list page."""
    return {name: _service(name, item) for name, item in _iter_items(payload)}


def parse_middlewares(payload: object) -> dict[str, Middleware]:
    """Parse HTTP middlewares from the rawdata map or a list page."""
    return {name: _middleware(name, item) for name, item in _iter_items(payload)}


def parse_entrypoints(payload: object) -> dict[str, Entrypoint]:
    """Parse the ``/api/entrypoints`` list."""
    if not isinstance(payload, list):
        raise TypeError(f"expected a list, got {type(payload).__name__}")
    entrypoints: dict[str, Entrypoint] = {}
    for item in payload:
        if not isinstance(item, Mapping):
            raise TypeError(f"entrypoint must be an object, got {type(item).__name__}")
        name = _required_str(item, "name")
        address = _required_str(item, "address")
        protocol = "udp" if address.endswith("/udp") else "tcp"
        entrypoints[name] = Entrypoint(name=name, address=address, protocol=protocol)
    return {name: entrypoints[name] for name in sorted(entrypoints)}


def parse_version(payload: object) -> TraefikVersion:
    """Parse ``/api/version``; a naive start date is treated as UTC."""
    if not isinstance(payload, Mapping):
        raise TypeError(f"expected an object, got {type(payload).__name__}")
    version = _required_str(payload, "Version")
    # Traefik serialises the start date as ``startDate``; accept ``StartDate`` too.
    key = "startDate" if "startDate" in payload else "StartDate"
    start_date = datetime.fromisoformat(_required_str(payload, key))
    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=UTC)
    return TraefikVersion(version=version, codename=_str(payload, "Codename"), start_date=start_date)


def parse_rawdata(payload: object) -> TraefikState:
    """Parse ``/api/rawdata``; missing or null HTTP sections are empty, TCP/UDP ignored."""
    if not isinstance(payload, Mapping):
        raise TypeError(f"expected an object, got {type(payload).__name__}")
    routers, services, middlewares = (payload.get(section) or {} for section in _RAWDATA_SECTIONS)
    return TraefikState(
        routers=parse_routers(routers),
        services=parse_services(services),
        middlewares=parse_middlewares(middlewares),
    )
