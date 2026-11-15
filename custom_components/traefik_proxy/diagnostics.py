"""Diagnostics download of a Traefik config entry.

Holds the entry, both coordinators' status, the parsed snapshot, the
certificate state per host and the missing-since times of vanished items.
Only parsed models are dumped, never a raw API payload. Credentials are
redacted, the URL loses any userinfo, and router rules lose the values of
their header and query matchers, also where a router error repeats the rule.
A router error that may quote such a value elsewhere is redacted whole.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Final

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY, CONF_URL
from .coordinator import split_url_userinfo
from .data import TraefikProxyConfigEntry
from .rules import has_matcher_call, redact_rule, rule_secret_values

TO_REDACT: Final = {CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME, CONF_API_KEY, "users", "authorization"}


def _jsonable(value: Any) -> Any:
    """Return ``value`` as JSON-safe data: ISO datetimes, seconds for timedeltas, lists for tuples."""
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, Enum):
        return value.value
    return value


def _seconds(interval: timedelta | None) -> float | None:
    return interval.total_seconds() if interval is not None else None


def _safe_url(url: Any) -> Any:
    """Return ``url`` without userinfo; a URL that cannot be parsed is redacted as a whole."""
    if not isinstance(url, str):
        return url
    try:
        return split_url_userinfo(url)[0]
    except ValueError:
        return REDACTED


def _may_quote_a_secret(segment: str, secrets: frozenset[str]) -> bool:
    """Return True when ``segment`` holds a secret value or any quoted text.

    Traefik and Go quote a rule value without a matcher call, for example
    ``error parsing regexp: missing closing ): `<value>```, and may quote
    only a fragment of it, so any backtick or double quote counts.
    """
    return "`" in segment or '"' in segment or any(value in segment for value in secrets)


def _redact_error(error: str, rule: str, redacted_rule: str, secrets: frozenset[str] | None) -> str:
    """Return a router error with the raw rule replaced by its redacted form.

    ``secrets`` are the values ``redacted_rule`` hides (None: the rule is
    unparsable and its secrets are unknown). Fails closed: the error is
    redacted as a whole when the rule is unparsable, when text outside the
    verbatim rule holds a matcher call (Traefik may quote a fragment or a
    normalized form of the rule), or, for a rule with hidden values, when
    that text holds one of them or any quoted text.
    """
    if secrets is None:
        return REDACTED
    segments = error.split(rule) if rule.strip() else [error]
    if any(has_matcher_call(segment) for segment in segments):
        return REDACTED
    if secrets and any(_may_quote_a_secret(segment, secrets) for segment in segments):
        return REDACTED
    return redacted_rule.join(segments)


def _redact_router_rules(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Redact the rule and the errors of every router in a dumped snapshot."""
    for router in snapshot["routers"].values():
        rule = router["rule"]
        redacted_rule = redact_rule(rule)
        secrets = rule_secret_values(rule)
        router["rule"] = redacted_rule
        router["errors"] = [_redact_error(error, rule, redacted_rule, secrets) for error in router["errors"]]
    return snapshot


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: TraefikProxyConfigEntry) -> dict[str, Any]:
    """Return the redacted diagnostics of a loaded Traefik config entry."""
    runtime_data = entry.runtime_data
    coordinator = runtime_data.coordinator
    cert_coordinator = runtime_data.cert_coordinator
    data = dict(entry.data)
    if CONF_URL in data:
        data[CONF_URL] = _safe_url(data[CONF_URL])
    snapshot = coordinator.data
    hosts = cert_coordinator.data or {}
    return async_redact_data(
        {
            "entry": {
                "title": entry.title,
                "unique_id": entry.unique_id,
                "version": entry.version,
                "minor_version": entry.minor_version,
                "data": data,
                "options": dict(entry.options),
            },
            "coordinator": {
                "last_update_success": coordinator.last_update_success,
                "update_interval": _seconds(coordinator.update_interval),
                "paginated": runtime_data.client.paginated,
            },
            "snapshot": (
                _redact_router_rules(_jsonable(dataclasses.asdict(snapshot))) if snapshot is not None else None
            ),
            "certificates": {
                "last_update_success": cert_coordinator.last_update_success,
                "update_interval": _seconds(cert_coordinator.update_interval),
                "threshold_days": cert_coordinator.threshold_days,
                "hosts": {host: _jsonable(dataclasses.asdict(state)) for host, state in hosts.items()},
            },
            "missing": runtime_data.entity_manager.missing_map(),
        },
        TO_REDACT,
    )
