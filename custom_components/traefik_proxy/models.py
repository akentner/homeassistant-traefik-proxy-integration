"""Typed, immutable Traefik models (interface stub, implementation pending)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

_LOGGED_UNKNOWN_STATUSES: set[str | None] = set()


class Status(StrEnum):
    """Item status as reported by Traefik, plus ``error``."""

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
    """Return the provider suffix of ``name``."""
    return ""


def is_internal(name: str) -> bool:
    """Return True for Traefik-internal items."""
    return False


def parse_routers(payload: object) -> dict[str, Router]:
    """Parse routers from either payload shape."""
    return {}
