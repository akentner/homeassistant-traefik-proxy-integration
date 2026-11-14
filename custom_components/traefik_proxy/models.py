"""Typed, immutable models of the Traefik API payloads.

Pure module: stdlib only, no Home Assistant imports and no import of the API
client. Parsers accept both payload shapes Traefik serves for HTTP items:

- the ``/api/rawdata`` map form, ``{"<name@provider>": {...}}``;
- the list form of ``/api/http/<kind>``, ``[{"name": "<name@provider>", ...}]``.

Shape violations raise ``TypeError`` / ``KeyError`` / ``ValueError``; the
client wraps them into its payload error. Optional fields with an unexpected
type are treated as absent.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

_LOGGER = logging.getLogger(__name__)

_INTERNAL_SUFFIX = "@internal"

# Distinct unknown status values already logged; bounded so a misbehaving
# server cannot grow it without limit.
_LOGGED_UNKNOWN_STATUSES: set[str | None] = set()
_MAX_LOGGED_UNKNOWN_STATUSES = 16


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


def _str_tuple(item: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = item.get(key)
    if not isinstance(value, list):
        return ()
    return tuple(entry for entry in value if isinstance(entry, str))


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
    is_tls = isinstance(tls, Mapping)
    return Router(
        name=name,
        provider=provider_from_name(name),
        status=_parse_status(item, errors),
        rule=_str(item, "rule"),
        service=_str(item, "service"),
        entry_points=_str_tuple(item, "entryPoints"),
        middlewares=_str_tuple(item, "middlewares"),
        tls=is_tls,
        tls_domains=_tls_domains(tls) if isinstance(tls, Mapping) else (),
        errors=errors,
        using=_str_tuple(item, "using"),
    )


def parse_routers(payload: object) -> dict[str, Router]:
    """Parse HTTP routers from the rawdata map or a list page."""
    return {name: _router(name, item) for name, item in _iter_items(payload)}


# --- Interface stubs (implementation pending) ---------------------------------


@dataclass(frozen=True, slots=True)
class Service:
    """An HTTP service (stub)."""

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
    """An HTTP middleware (stub)."""

    name: str
    provider: str
    status: Status
    type: str
    used_by: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Entrypoint:
    """An entrypoint (stub)."""

    name: str
    address: str
    protocol: str


@dataclass(frozen=True, slots=True)
class TraefikVersion:
    """Version payload (stub)."""

    version: str
    codename: str
    start_date: datetime


@dataclass(frozen=True, slots=True)
class StatusCounts:
    """Per-status counts (stub)."""

    total: int
    enabled: int
    warning: int
    error: int
    disabled: int


@dataclass(frozen=True, slots=True)
class TraefikState:
    """Routers, services and middlewares (stub)."""

    routers: dict[str, Router]
    services: dict[str, Service]
    middlewares: dict[str, Middleware]


@dataclass(frozen=True, slots=True)
class TraefikSnapshot:
    """Coordinator payload (stub)."""

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
        """Stub."""
        raise NotImplementedError


def parse_services(payload: object) -> dict[str, Service]:
    """Stub."""
    return {}


def parse_middlewares(payload: object) -> dict[str, Middleware]:
    """Stub."""
    return {}


def parse_entrypoints(payload: object) -> dict[str, Entrypoint]:
    """Stub."""
    return {}


def parse_version(payload: object) -> TraefikVersion:
    """Stub."""
    raise NotImplementedError


def parse_rawdata(payload: object) -> TraefikState:
    """Stub."""
    return TraefikState(routers={}, services={}, middlewares={})
