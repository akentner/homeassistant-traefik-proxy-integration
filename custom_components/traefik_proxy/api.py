"""Async Traefik API client (no HA imports; pure aiohttp wrapper)."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import aiohttp

from .models import (
    Entrypoint,
    TraefikState,
    TraefikVersion,
    parse_entrypoints,
    parse_middlewares,
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

# Matches Traefik's auto-generated *internal* items (CONTEXT.md D-06 /
# PITFALLS #2). Traefik itself exposes built-in API/dashboard/ping/etc.
# under the literal ``internal`` provider, so the only truly Traefik-internal
# items carry the suffix ``@internal`` (e.g. ``api@internal``,
# ``dashboard@internal``, ``web-to-websecure@internal``).
#
# The previous regex ``r"@\w+"`` was too aggressive — it also matched
# provider-suffixed USER items like ``ha-nextgen@file``,
# ``n8n@docker``, ``strip@docker`` (Traefik's universal naming scheme
# appends the provider name after every user-defined resource). With the
# old regex, every user router got dropped from the count and the
# overview sensors read 0 even when 9 user routers were configured
# (v0.1.5 bug).
#
# Traefik HA entity-IDs can handle ``@`` via ``slugify`` (``@`` → ``_``)
# so we only need to drop the Traefik-internal ones, not all
# provider-suffixed items.
_INTERNAL_ITEM_RE = re.compile(r"@internal$")


class TraefikProxyApiError(Exception):
    """Raised for non-auth Traefik API failures (5xx, network, parse)."""


class TraefikProxyAuthError(TraefikProxyApiError):
    """Raised on 401/403 — caller maps to ConfigEntryAuthFailed."""


class TraefikProxyPayloadError(TraefikProxyApiError):
    """Raised when Traefik answers with a payload of an unexpected shape."""


def filter_internal_items(
    items: list[dict[str, Any]],
    *,
    name_key: str = "name",
) -> list[dict[str, Any]]:
    """Drop Traefik-internal ``@internal`` suffixed items.

    Reused by services, middlewares, and routers platforms (CONTEXT.md D-06).
    Matches the literal suffix ``@internal`` only (Traefik's auto-generated
    API / dashboard / ping / redirect items) — does NOT drop provider-
    suffixed user items like ``ha-nextgen@file`` or ``strip@docker``
    which are user-named resources that Traefik just suffixes with the
    provider name. Use ``homeassistant.util.slugify`` to render
    ``@``-containing names into HA-valid entity IDs.

    :param items: list of dicts each with a ``name`` (or ``name_key``) field.
    :param name_key: name of the key whose value carries the item's display
        name. Defaults to ``"name"``.
    :return: filtered list with internal items removed.
    """
    return [item for item in items if not _INTERNAL_ITEM_RE.search(str(item.get(name_key, "")))]


class TraefikProxyApiClient:
    """Async client for Traefik's HTTP API (v2.11+ / v3.x)."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        api_key: str,
        *,
        verify_ssl: bool = True,
        request_timeout: float = 10.0,
        page_size: int | None = None,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._verify_ssl = verify_ssl
        self._request_timeout = request_timeout
        self._page_size = DEFAULT_PAGE_SIZE if page_size is None else page_size

    def _headers(self) -> dict[str, str]:
        """Per-request auth header — never default header on session."""
        if self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    async def _get_response(self, path: str, params: dict[str, int] | None = None) -> tuple[Any, str | None]:
        """GET ``path`` and return the JSON payload and the raw ``X-Next-Page`` header."""
        url = f"{self._base_url}{path}"
        try:
            async with asyncio.timeout(self._request_timeout):
                async with self._session.get(
                    url,
                    headers=self._headers(),
                    params=params,
                    ssl=self._verify_ssl,
                ) as response:
                    _LOGGER.debug(
                        "path=%s page=%s status=%s",
                        path,
                        params.get("page") if params else None,
                        response.status,
                    )
                    if response.status in (401, 403):
                        raise TraefikProxyAuthError(f"Auth failed for {path}: {response.status}")
                    response.raise_for_status()
                    payload = await response.json(content_type=None)
                    return payload, response.headers.get("X-Next-Page")
        except aiohttp.ClientResponseError as err:
            # raise_for_status already raised; re-classify for safety
            if err.status in (401, 403):
                raise TraefikProxyAuthError(str(err)) from err
            raise TraefikProxyApiError(str(err)) from err
        except (TimeoutError, aiohttp.ClientConnectorError, aiohttp.InvalidUrlClientError) as err:
            raise TraefikProxyApiError(str(err)) from err

    async def _get(self, path: str) -> Any:
        payload, _ = await self._get_response(path)
        return payload

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
            payload, next_page = await self._get_response(path, {"per_page": self._page_size, "page": page})
            if not isinstance(payload, list):
                raise TraefikProxyPayloadError(f"{path}: unexpected payload shape")
            items.extend(payload)
            try:
                announced = int(next_page) if next_page is not None else None
            except ValueError:
                announced = None
            if announced is None or announced <= page:
                return items
            if announced > MAX_PAGES:
                raise TraefikProxyPayloadError(f"{path}: more than {MAX_PAGES} pages")
            page = announced

    async def async_get_version(self) -> TraefikVersion:
        """GET /api/version as a parsed model."""
        path = "/api/version"
        payload = await self._get(path)
        try:
            return parse_version(payload)
        except (ValueError, TypeError, KeyError) as err:
            raise TraefikProxyPayloadError(f"{path}: unexpected payload shape") from err

    async def async_get_entrypoints(self) -> dict[str, Entrypoint]:
        """GET /api/entrypoints as parsed models keyed by name."""
        path = "/api/entrypoints"
        payload = await self._get(path)
        try:
            return parse_entrypoints(payload)
        except (ValueError, TypeError, KeyError) as err:
            raise TraefikProxyPayloadError(f"{path}: unexpected payload shape") from err

    async def async_get_state(self) -> TraefikState:
        """Fetch HTTP routers, services and middlewares as parsed models.

        The three list endpoints are requested one after another, each
        followed across all of its pages.
        """
        path = "/api/http/routers"
        try:
            routers = parse_routers(await self._get_paginated(path))
            path = "/api/http/services"
            services = parse_services(await self._get_paginated(path))
            path = "/api/http/middlewares"
            middlewares = parse_middlewares(await self._get_paginated(path))
        except (ValueError, TypeError, KeyError) as err:
            raise TraefikProxyPayloadError(f"{path}: unexpected payload shape") from err
        return TraefikState(routers=routers, services=services, middlewares=middlewares)

    # --- Read endpoints ---
    async def get_version(self) -> dict[str, Any]:
        """GET /api/version — returns {Version, Codename, StartDate}."""
        result = await self._get("/api/version")
        assert isinstance(result, dict)
        return result

    async def get_entrypoints(self) -> list[dict[str, Any]]:
        """GET /api/entrypoints — list of configured TCP/UDP entrypoints."""
        result = await self._get("/api/entrypoints")
        assert isinstance(result, list)
        return result

    async def get_routers(self) -> list[dict[str, Any]]:
        """GET /api/http/routers."""
        result = await self._get("/api/http/routers")
        assert isinstance(result, list)
        return result

    async def get_http_services(self) -> list[dict[str, Any]]:
        """GET /api/http/services — list of HTTP service definitions."""
        result = await self._get("/api/http/services")
        assert isinstance(result, list)
        return result

    async def get_http_middlewares(self) -> list[dict[str, Any]]:
        """GET /api/http/middlewares — list of HTTP middleware definitions."""
        result = await self._get("/api/http/middlewares")
        assert isinstance(result, list)
        return result

    async def get_overview(self) -> dict[str, Any]:
        """GET /api/overview — used by config flow for auth probe."""
        result = await self._get("/api/overview")
        assert isinstance(result, dict)
        return result

    # --- Write endpoints ---
    async def reload_routers(self) -> None:
        """POST /api/http/routers/refresh — ask Traefik to reload routers.

        Returns ``None`` on 2xx. Raises ``TraefikProxyAuthError`` on 401/403 and
        ``TraefikProxyApiError`` on other non-2xx. Does NOT poll — the reload
        service handler (plan 02-04) is responsible for verifying that the
        reload actually completed (CONTEXT.md D-05/D-12).

        PITFALLS #15 — Traefik returns 202 before the reload finishes; we do
        not block here. The empty POST body requires an explicit
        ``Content-Length: 0`` header — aiohttp would otherwise hang waiting
        for the writer to flush.
        """
        url = f"{self._base_url}/api/http/routers/refresh"
        try:
            async with asyncio.timeout(self._request_timeout):
                async with self._session.post(
                    url,
                    headers={**self._headers(), "Content-Length": "0"},
                    ssl=self._verify_ssl,
                ) as response:
                    _LOGGER.debug("path=%s status=%s", "/api/http/routers/refresh", response.status)
                    if response.status in (401, 403):
                        raise TraefikProxyAuthError(f"Auth failed for /api/http/routers/refresh: {response.status}")
                    response.raise_for_status()
                    return None
        except aiohttp.ClientResponseError as err:
            if err.status in (401, 403):
                raise TraefikProxyAuthError(str(err)) from err
            raise TraefikProxyApiError(str(err)) from err
        except (TimeoutError, aiohttp.ClientConnectorError, aiohttp.InvalidUrlClientError) as err:
            raise TraefikProxyApiError(str(err)) from err

    # --- Aggregated fetch ---
    async def fetch_all(self) -> dict[str, Any]:
        """Phase 2 parallel fetch: all six endpoints in one asyncio.gather.

        Per CONTEXT.md D-07, partial-failure policy is: auth failures raise
        immediately (the coordinator maps them to ConfigEntryAuthFailed), and
        any other exception bubbles to the first non-auth error so the
        coordinator surfaces a single ``UpdateFailed`` per cycle. Successful
        sections are NOT returned on partial failure — the caller decides
        whether to fall back to stale coordinator data (the DataUpdateCoordinator
        default keeps last-known-good data).
        """
        version, entrypoints, http_routers, http_services, http_middlewares, overview = await asyncio.gather(
            self.get_version(),
            self.get_entrypoints(),
            self.get_routers(),
            self.get_http_services(),
            self.get_http_middlewares(),
            self.get_overview(),
            return_exceptions=True,
        )
        # Auth failures always win — never swallow them (PITFALLS).
        for result in (version, entrypoints, http_routers, http_services, http_middlewares, overview):
            if isinstance(result, TraefikProxyAuthError):
                raise result
        # First non-auth exception wins (CONTEXT.md D-07).
        first_exc = next(
            (
                r
                for r in (
                    version,
                    entrypoints,
                    http_routers,
                    http_services,
                    http_middlewares,
                    overview,
                )
                if isinstance(r, BaseException)
            ),
            None,
        )
        if first_exc is not None:
            raise first_exc
        return {
            "version": version,
            "entrypoints": entrypoints,
            "http_routers": http_routers,
            "http_services": http_services,
            "http_middlewares": http_middlewares,
            "overview": overview,
        }
