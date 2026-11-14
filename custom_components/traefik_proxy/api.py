"""Async Traefik API client (no HA imports; pure aiohttp wrapper)."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import aiohttp

from .models import (
    Entrypoint,
    TraefikState,
    TraefikVersion,
    parse_entrypoints,
    parse_middlewares,
    parse_rawdata,
    parse_routers,
    parse_services,
    parse_version,
)

_LOGGER = logging.getLogger(__name__)

# Items requested per page from the paginated list endpoints. Traefik's own
# default is 100; a larger page keeps a typical installation at one request
# per kind.
DEFAULT_PAGE_SIZE = 500
# Upper bound for pages followed per list endpoint. Reaching it raises
# instead of silently returning a truncated list.
MAX_PAGES = 100

_RAWDATA_PATH = "/api/rawdata"
_REFRESH_PATH = "/api/http/routers/refresh"


class AuthMode(StrEnum):
    """How the client authenticates against the Traefik API."""

    none = "none"
    basic = "basic"
    bearer = "bearer"


def _has_control_chars(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


@dataclass(frozen=True, slots=True)
class Auth:
    """Authentication mode plus its credentials.

    The credentials are excluded from ``repr()``. Validation errors name the
    offending field only, never its value.
    """

    mode: AuthMode = AuthMode.none
    username: str | None = field(default=None, repr=False)
    password: str | None = field(default=None, repr=False)
    token: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Reject credential combinations the mode cannot use."""
        if self.mode is AuthMode.basic:
            if not self.username:
                raise ValueError("basic auth requires a username")
            if ":" in self.username:
                raise ValueError("basic auth username must not contain ':'")
            if not self.password:
                raise ValueError("basic auth requires a password")
            unused = {"token": self.token}
        elif self.mode is AuthMode.bearer:
            if not self.token:
                raise ValueError("bearer auth requires a token")
            unused = {"username": self.username, "password": self.password}
        else:
            unused = {"username": self.username, "password": self.password, "token": self.token}
        for name, value in unused.items():
            if value is not None:
                raise ValueError(f"{self.mode} auth does not use a {name}")
        for name in ("username", "password", "token"):
            value = getattr(self, name)
            if value is not None and _has_control_chars(value):
                raise ValueError(f"{name} must not contain control characters")

    def header(self) -> dict[str, str]:
        """Return the Authorization header for one request (empty for mode none)."""
        if self.mode is AuthMode.basic and self.username and self.password:
            # RFC 7617 with UTF-8 credentials. Built here because aiohttp 3.14
            # deprecates BasicAuth and the aiohttp of older Home Assistant
            # releases lacks its replacement.
            credentials = f"{self.username}:{self.password}".encode()
            return {"Authorization": f"Basic {base64.b64encode(credentials).decode('ascii')}"}
        if self.mode is AuthMode.bearer and self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}


class TraefikProxyApiError(Exception):
    """Base class of every error the client raises.

    The message is ``"<path>: <detail>"`` where the detail is an HTTP status,
    an exception type name or a fixed description; it never contains a URL,
    a header or a credential.
    """

    def __init__(self, path: str, detail: str, *, status: int | None = None) -> None:
        super().__init__(f"{path}: {detail}")
        self.path = path
        self.status = status


class TraefikProxyAuthError(TraefikProxyApiError):
    """Traefik answered 401 or 403."""


class TraefikProxyNotFoundError(TraefikProxyApiError):
    """Traefik answered 404 (endpoint missing or API disabled)."""


class TraefikProxyConnectionError(TraefikProxyApiError):
    """The request failed below HTTP (connection, timeout, OS error)."""


class TraefikProxyInvalidUrlError(TraefikProxyConnectionError):
    """aiohttp rejected the configured URL or refused to build the request for it."""


class TraefikProxyPayloadError(TraefikProxyApiError):
    """Traefik answered with invalid JSON or a payload of an unexpected shape."""


def _status_error(path: str, status: int) -> TraefikProxyApiError:
    """Map a non-2xx status of a read request to the taxonomy."""
    detail = f"HTTP {status}"
    if status in (401, 403):
        return TraefikProxyAuthError(path, detail, status=status)
    if status == 404:
        return TraefikProxyNotFoundError(path, detail, status=status)
    return TraefikProxyApiError(path, detail, status=status)


def _is_success(status: int) -> bool:
    return 200 <= status < 300


class TraefikProxyApiClient:
    """Async client for Traefik's HTTP API (v2.11+ / v3.x).

    Runs on a caller-provided session (Home Assistant's shared one). The
    Authorization header is passed with each request and never stored on
    the session.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        auth: Auth,
        *,
        verify_ssl: bool = True,
        request_timeout: float = 10.0,
        page_size: int | None = None,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._auth = auth
        self._verify_ssl = verify_ssl
        self._request_timeout = request_timeout
        self._page_size = DEFAULT_PAGE_SIZE if page_size is None else page_size
        # Set once Traefik answers 404 on /api/rawdata; from then on the
        # client reads the paginated list endpoints for its whole lifetime.
        self._paginated = False

    async def _request(self, path: str, params: dict[str, int] | None = None) -> tuple[Any, str | None]:
        """GET ``path`` and return the decoded JSON payload and the raw ``X-Next-Page`` header."""
        url = f"{self._base_url}{path}"
        try:
            async with asyncio.timeout(self._request_timeout):
                async with self._session.get(
                    url,
                    params=params,
                    headers=self._auth.header(),
                    ssl=self._verify_ssl,
                ) as response:
                    _LOGGER.debug(
                        "path=%s page=%s status=%s",
                        path,
                        params.get("page") if params else None,
                        response.status,
                    )
                    if not _is_success(response.status):
                        raise _status_error(path, response.status)
                    body = await response.read()
                    next_page = response.headers.get("X-Next-Page")
        except aiohttp.InvalidUrlClientError as err:
            raise TraefikProxyInvalidUrlError(path, type(err).__name__) from err
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            raise TraefikProxyConnectionError(path, type(err).__name__) from err
        except ValueError as err:
            # aiohttp refused to build the request, e.g. URL credentials
            # combined with an Authorization header.
            raise TraefikProxyInvalidUrlError(path, type(err).__name__) from err
        # Decoded outside the network block: a decode ValueError must never be
        # mistaken for aiohttp's invalid-URL error (also a ValueError).
        try:
            payload = json.loads(body)
        except ValueError as err:
            raise TraefikProxyPayloadError(path, "invalid JSON") from err
        return payload, next_page

    async def _get_paginated(self, path: str) -> list[Any]:
        """Collect every page of a Traefik list endpoint.

        Traefik announces the next page in ``X-Next-Page``; on the last page
        it repeats a page number that is not greater than the current one.
        The loop continues only while the header is an integer greater than
        the current page, and raises once more than ``MAX_PAGES`` pages
        would be needed.
        """
        items: list[Any] = []
        page = 1
        while True:
            payload, next_page = await self._request(path, {"per_page": self._page_size, "page": page})
            if not isinstance(payload, list):
                raise TraefikProxyPayloadError(path, "unexpected payload shape")
            items.extend(payload)
            try:
                announced = int(next_page) if next_page is not None else None
            except ValueError:
                announced = None
            if announced is None or announced <= page:
                return items
            if announced > MAX_PAGES:
                raise TraefikProxyPayloadError(path, f"more than {MAX_PAGES} pages")
            page = announced

    async def async_get_version(self) -> TraefikVersion:
        """GET /api/version as a parsed model."""
        path = "/api/version"
        payload, _ = await self._request(path)
        try:
            return parse_version(payload)
        except (ValueError, TypeError, KeyError) as err:
            raise TraefikProxyPayloadError(path, "unexpected payload shape") from err

    async def async_get_entrypoints(self) -> dict[str, Entrypoint]:
        """GET /api/entrypoints as parsed models keyed by name."""
        path = "/api/entrypoints"
        payload, _ = await self._request(path)
        try:
            return parse_entrypoints(payload)
        except (ValueError, TypeError, KeyError) as err:
            raise TraefikProxyPayloadError(path, "unexpected payload shape") from err

    async def async_get_state(self) -> TraefikState:
        """Fetch HTTP routers, services and middlewares as parsed models.

        Reads the unpaginated ``/api/rawdata`` in one request. When Traefik
        answers 404 there, the client switches to the paginated list
        endpoints in the same call and keeps using them for its lifetime.
        Every other error propagates unchanged.
        """
        if not self._paginated:
            try:
                payload, _ = await self._request(_RAWDATA_PATH)
            except TraefikProxyNotFoundError:
                self._paginated = True
                _LOGGER.debug("path=%s not found, switching to the paginated list endpoints", _RAWDATA_PATH)
            else:
                try:
                    return parse_rawdata(payload)
                except (ValueError, TypeError, KeyError) as err:
                    raise TraefikProxyPayloadError(_RAWDATA_PATH, "unexpected payload shape") from err
        return await self._get_state_paginated()

    async def _get_state_paginated(self) -> TraefikState:
        """Read the three list endpoints one after another, each across all of its pages."""
        path = "/api/http/routers"
        try:
            routers = parse_routers(await self._get_paginated(path))
            path = "/api/http/services"
            services = parse_services(await self._get_paginated(path))
            path = "/api/http/middlewares"
            middlewares = parse_middlewares(await self._get_paginated(path))
        except (ValueError, TypeError, KeyError) as err:
            raise TraefikProxyPayloadError(path, "unexpected payload shape") from err
        return TraefikState(routers=routers, services=services, middlewares=middlewares)

    async def reload_routers(self) -> None:
        """POST /api/http/routers/refresh and return once Traefik answers 2xx.

        Raises ``TraefikProxyAuthError`` on 401/403, ``TraefikProxyApiError``
        on any other non-2xx status and ``TraefikProxyConnectionError`` on
        network failures. Traefik answers before a reload completes, so the
        caller verifies the effect itself. The empty body needs an explicit
        ``Content-Length: 0`` header.
        """
        path = _REFRESH_PATH
        url = f"{self._base_url}{path}"
        try:
            async with asyncio.timeout(self._request_timeout):
                async with self._session.post(
                    url,
                    headers={**self._auth.header(), "Content-Length": "0"},
                    ssl=self._verify_ssl,
                ) as response:
                    _LOGGER.debug("path=%s status=%s", path, response.status)
                    status = response.status
        except aiohttp.InvalidUrlClientError as err:
            raise TraefikProxyInvalidUrlError(path, type(err).__name__) from err
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            raise TraefikProxyConnectionError(path, type(err).__name__) from err
        except ValueError as err:
            # aiohttp refused to build the request, e.g. URL credentials
            # combined with an Authorization header.
            raise TraefikProxyInvalidUrlError(path, type(err).__name__) from err
        if status in (401, 403):
            raise TraefikProxyAuthError(path, f"HTTP {status}", status=status)
        if not _is_success(status):
            raise TraefikProxyApiError(path, f"HTTP {status}", status=status)
