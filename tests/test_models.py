"""Tests for the typed Traefik models, run against the real captures of both generations."""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

import pytest

from custom_components.traefik_proxy import models
from custom_components.traefik_proxy.models import (
    Router,
    Status,
    TlsDomain,
    is_internal,
    parse_routers,
    provider_from_name,
)
from tests.conftest import FIXTURE_VERSIONS, load_fixture, load_paginated

# Fields that genuinely differ between the v2.11 and v3.7 captures for the shared
# scenario, keyed "<kind>.<field>" with the observed (v2.11, v3.7) values. The
# generation-equality tests drop these fields from their projection. Empty: the
# captures agree on every projected field.
ALLOWED_GENERATION_DIFFERENCES: dict[str, tuple[object, object]] = {}

_ROUTER_FIELDS = (
    "name",
    "provider",
    "status",
    "rule",
    "service",
    "entry_points",
    "middlewares",
    "tls",
    "tls_domains",
    "errors",
)


def _project(items: dict[str, Any], kind: str, fields: tuple[str, ...]) -> dict[str, tuple[object, ...]]:
    """Project model dicts onto ``fields`` minus the allowed generation differences."""
    kept = tuple(f for f in fields if f"{kind}.{f}" not in ALLOWED_GENERATION_DIFFERENCES)
    projection: dict[str, tuple[object, ...]] = {}
    for name, item in items.items():
        values: list[object] = []
        for field in kept:
            value = getattr(item, field)
            # Error texts are free-form; only their presence is a model fact.
            values.append(bool(value) if field == "errors" else value)
        projection[name] = tuple(values)
    return projection


def _raw_routers(version: str) -> dict[str, Any]:
    raw: dict[str, Any] = load_fixture(version, "rawdata.json")["routers"]
    return raw


# --- Routers: real captures -------------------------------------------------


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_routers_map_form_equals_list_form(version: str) -> None:
    """Rawdata map form and concatenated list pages parse to equal routers (D-04)."""
    from_map = parse_routers(_raw_routers(version))
    items, _next_pages = load_paginated(version, "routers")
    from_list = parse_routers(items)

    assert from_map
    assert from_map == from_list


def test_router_projection_equal_across_generations() -> None:
    """v2.11 and v3.7 yield the same router projection for the shared scenario."""
    old, new = (parse_routers(_raw_routers(v)) for v in FIXTURE_VERSIONS)

    assert _project(old, "router", _ROUTER_FIELDS) == _project(new, "router", _ROUTER_FIELDS)


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_internal_routers_are_dropped(version: str) -> None:
    raw = _raw_routers(version)
    assert any(name.endswith("@internal") for name in raw), "capture lost its @internal router"

    routers = parse_routers(raw)

    assert not any(name.endswith("@internal") for name in routers)
    assert "ping@internal" not in routers


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_router_names_keep_exact_case_and_provider(version: str) -> None:
    routers = parse_routers(_raw_routers(version))

    assert {"whoami@docker", "secure@file", "file-ok@file"} <= set(routers)
    assert routers["whoami@docker"].name == "whoami@docker"
    assert routers["whoami@docker"].provider == "docker"
    assert routers["secure@file"].provider == "file"
    for name, router in routers.items():
        assert router.name == name


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_disabled_routers_with_errors_parse_as_error(version: str) -> None:
    raw = _raw_routers(version)
    disabled_with_errors = {name for name, item in raw.items() if item["status"] == "disabled" and item.get("error")}
    assert disabled_with_errors == {"broken-missing-service@file", "chain-router@file"}

    routers = parse_routers(raw)

    for name in disabled_with_errors:
        assert routers[name].status is Status.error
        assert routers[name].errors


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_captured_warning_and_enabled_routers(version: str) -> None:
    routers = parse_routers(_raw_routers(version))

    warn = routers["warn-unknown-entrypoint@file"]
    assert warn.status is Status.warning
    assert warn.errors == ('entryPoint "does-not-exist" doesn\'t exist',)
    assert warn.entry_points == ("web", "does-not-exist")
    assert warn.using == ("web",)
    assert routers["file-ok@file"].status is Status.enabled


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_router_field_mapping(version: str) -> None:
    routers = parse_routers(_raw_routers(version))

    chain = routers["chain-router@file"]
    assert chain.rule == "Host(`chain.example.com`)"
    assert chain.service == "file-ok-svc"
    assert chain.middlewares == ("broken-chain@file",)
    assert chain.tls is False
    assert chain.tls_domains == ()


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_secure_router_tls_domains(version: str) -> None:
    routers = parse_routers(_raw_routers(version))

    assert "secure@file" in routers
    secure = routers["secure@file"]
    assert secure.tls is True
    assert secure.tls_domains == (TlsDomain(main="secure.example.com", sans=("www.secure.example.com",)),)


# --- Routers: provider / internal helpers -----------------------------------


def test_provider_from_name_uses_last_at() -> None:
    assert provider_from_name("a@b@file") == "file"
    assert provider_from_name("whoami@docker") == "docker"
    assert provider_from_name("plain") == ""


def test_is_internal() -> None:
    assert is_internal("api@internal")
    assert not is_internal("internal@file")
    assert not is_internal("ha-nextgen@file")


def test_provider_split_keeps_name_untouched() -> None:
    routers = parse_routers({"My-Router@sub@File": {"status": "enabled"}, "plain": {"status": "enabled"}})

    assert set(routers) == {"My-Router@sub@File", "plain"}
    assert routers["My-Router@sub@File"].provider == "File"
    assert routers["plain"].provider == ""


# --- Routers: status semantics (D-02) ----------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"status": "enabled"}, Status.enabled),
        ({"status": "warning"}, Status.warning),
        ({"status": "disabled"}, Status.disabled),
        ({"status": "disabled", "error": []}, Status.disabled),
        ({"status": "disabled", "error": ["boom"]}, Status.error),
        ({"status": "error"}, Status.error),
        ({"status": "warning", "error": ["boom"]}, Status.warning),
        ({}, Status.warning),
    ],
)
def test_router_status_mapping(raw: dict[str, Any], expected: Status) -> None:
    assert parse_routers({"r@file": raw})["r@file"].status is expected


def test_status_values() -> None:
    assert [s.value for s in Status] == ["enabled", "warning", "disabled", "error"]
    assert [s.name for s in Status] == ["enabled", "warning", "disabled", "error"]


def test_unknown_status_is_warning_and_logged_once(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(models, "_LOGGED_UNKNOWN_STATUSES", set())
    caplog.set_level(logging.DEBUG, logger=models.__name__)

    routers = parse_routers({"a@file": {"status": "bogus"}, "b@file": {"status": "bogus"}})
    parse_routers({"c@file": {"status": "bogus"}})

    assert all(router.status is Status.warning for router in routers.values())
    records = [r for r in caplog.records if r.name == models.__name__ and "bogus" in r.getMessage()]
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG


def test_unknown_status_log_set_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: set[str | None] = set()
    monkeypatch.setattr(models, "_LOGGED_UNKNOWN_STATUSES", seen)

    parse_routers({f"r{i}@file": {"status": f"odd-{i}"} for i in range(40)})

    assert 0 < len(seen) <= 16


# --- Routers: TLS tolerance ---------------------------------------------------


@pytest.mark.parametrize(
    ("tls", "expected_tls", "expected_domains"),
    [
        ({}, True, ()),
        ({"options": "default"}, True, ()),
        (None, False, ()),
        ("yes", False, ()),
        (
            {"domains": [{"main": "a.example.com", "sans": "b.example.com"}]},
            True,
            (TlsDomain("a.example.com", ("b.example.com",)),),
        ),
        (
            {"domains": [{"main": "a.example.com", "sans": ["b.example.com", 7, None, "c.example.com"]}]},
            True,
            (TlsDomain("a.example.com", ("b.example.com", "c.example.com")),),
        ),
        ({"domains": [{"main": "a.example.com"}, "junk", 3]}, True, (TlsDomain("a.example.com", ()),)),
        ({"domains": "junk"}, True, ()),
    ],
)
def test_router_tls_parsing(tls: object, expected_tls: bool, expected_domains: tuple[TlsDomain, ...]) -> None:
    raw: dict[str, Any] = {"status": "enabled"}
    if tls is not None:
        raw["tls"] = tls

    router = parse_routers({"r@file": raw})["r@file"]

    assert router.tls is expected_tls
    assert router.tls_domains == expected_domains


def test_optional_fields_with_wrong_types_are_absent() -> None:
    router = parse_routers(
        {
            "r@file": {
                "status": "enabled",
                "rule": 5,
                "service": ["x"],
                "entryPoints": "web",
                "middlewares": None,
                "error": "x",
            }
        }
    )["r@file"]

    assert router.rule == ""
    assert router.service == ""
    assert router.entry_points == ()
    assert router.middlewares == ()
    assert router.errors == ()


# --- Routers: shape errors and empty payloads (D-10) ---------------------------


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ("x", TypeError),
        (["x"], TypeError),
        ([{"status": "enabled"}], KeyError),
        ([{"name": 5}], TypeError),
        ({"r@file": "x"}, TypeError),
        (None, TypeError),
        (5, TypeError),
    ],
)
def test_parse_routers_shape_errors(payload: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        parse_routers(payload)


def test_parse_routers_empty_payloads() -> None:
    assert parse_routers([]) == {}
    assert parse_routers({}) == {}


# --- Routers: ordering and immutability --------------------------------------


def test_routers_are_sorted_by_name_regardless_of_input_order() -> None:
    items = [{"name": n, "status": "enabled"} for n in ("c@file", "a@file", "b@docker")]

    forward = parse_routers(items)
    backward = parse_routers(list(reversed(items)))

    assert list(forward) == ["a@file", "b@docker", "c@file"]
    assert list(backward) == ["a@file", "b@docker", "c@file"]
    assert forward == backward


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_router_is_frozen_with_tuple_sequences(version: str) -> None:
    router = parse_routers(_raw_routers(version))["secure@file"]

    assert isinstance(router, Router)
    with pytest.raises(dataclasses.FrozenInstanceError):
        router.status = Status.error  # type: ignore[misc]
    for field in ("entry_points", "middlewares", "tls_domains", "errors", "using"):
        assert isinstance(getattr(router, field), tuple)
    assert isinstance(router.tls_domains[0].sans, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        router.tls_domains[0].main = "x"  # type: ignore[misc]
