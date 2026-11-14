"""Tests for the typed Traefik models, run against the real captures of both generations."""

from __future__ import annotations

import dataclasses
import logging
import re
from datetime import UTC, datetime
from typing import Any

import pytest

from custom_components.traefik_proxy import models
from custom_components.traefik_proxy.models import (
    Entrypoint,
    Middleware,
    Router,
    Service,
    Status,
    StatusCounts,
    TlsDomain,
    TraefikSnapshot,
    TraefikState,
    TraefikVersion,
    is_internal,
    parse_entrypoints,
    parse_middlewares,
    parse_rawdata,
    parse_routers,
    parse_services,
    parse_version,
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
_SERVICE_FIELDS = ("name", "provider", "status", "type", "servers_total", "servers_up")
_MIDDLEWARE_FIELDS = ("name", "provider", "status", "type")


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


# --- Task 2 helpers ------------------------------------------------------------

_IP_LITERAL = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b|\[?[0-9a-fA-F]{0,4}(?::[0-9a-fA-F]{0,4}){2,7}\]?")


def _rawdata(version: str) -> dict[str, Any]:
    raw: dict[str, Any] = load_fixture(version, "rawdata.json")
    return raw


def _snapshot(version: str) -> TraefikSnapshot:
    return TraefikSnapshot.build(
        version=parse_version(load_fixture(version, "version.json")),
        entrypoints=parse_entrypoints(load_fixture(version, "entrypoints.json")),
        state=parse_rawdata(_rawdata(version)),
    )


def _values(obj: object) -> list[object]:
    """Flatten every field value of a model (tuples and nested models included)."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out: list[object] = []
        for field in dataclasses.fields(obj):
            out.extend(_values(getattr(obj, field.name)))
        return out
    if isinstance(obj, tuple):
        return [v for entry in obj for v in _values(entry)]
    return [obj]


# --- Services / middlewares / state: real captures -----------------------------


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_rawdata_equals_paginated_state(version: str) -> None:
    """parse_rawdata over rawdata.json equals the state built from the list pages (D-04)."""
    from_pages = TraefikState(
        routers=parse_routers(load_paginated(version, "routers")[0]),
        services=parse_services(load_paginated(version, "services")[0]),
        middlewares=parse_middlewares(load_paginated(version, "middlewares")[0]),
    )

    state = parse_rawdata(_rawdata(version))

    assert state.routers and state.services and state.middlewares
    assert state == from_pages


def test_service_projection_equal_across_generations() -> None:
    old, new = (parse_rawdata(_rawdata(v)).services for v in FIXTURE_VERSIONS)

    assert _project(old, "service", _SERVICE_FIELDS) == _project(new, "service", _SERVICE_FIELDS)


def test_middleware_projection_equal_across_generations() -> None:
    old, new = (parse_rawdata(_rawdata(v)).middlewares for v in FIXTURE_VERSIONS)

    assert _project(old, "middleware", _MIDDLEWARE_FIELDS) == _project(new, "middleware", _MIDDLEWARE_FIELDS)


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_lb_mixed_service_counts_servers(version: str) -> None:
    services = parse_rawdata(_rawdata(version)).services

    lb = services["lb-mixed@file"]
    assert lb.servers_total == 2
    assert lb.servers_up == 1
    assert lb.status is Status.enabled
    assert lb.type == "loadbalancer"
    assert lb.provider == "file"
    assert lb.used_by == ("lb-router@file",)
    assert lb.errors == ()


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_services_store_no_backend_url_or_ip(version: str) -> None:
    services = parse_rawdata(_rawdata(version)).services
    assert "whoami@docker" in services

    for service in services.values():
        for value in _values(service):
            text = str(value)
            assert "http://" not in text, (service.name, text)
            assert not _IP_LITERAL.search(text), (service.name, text)
    field_names = {f.name for f in dataclasses.fields(Service)}
    assert not field_names & {"url", "urls", "servers", "server_status", "address"}


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_internal_services_and_middlewares_are_dropped(version: str) -> None:
    state = parse_rawdata(_rawdata(version))

    assert set(state.services) == {"bulk-svc@file", "file-ok-svc@file", "lb-mixed@file", "whoami@docker"}
    assert set(state.middlewares) == {"api-auth@file", "broken-chain@file"}


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_captured_middlewares(version: str) -> None:
    middlewares = parse_rawdata(_rawdata(version)).middlewares

    chain = middlewares["broken-chain@file"]
    assert chain.status is Status.error
    assert chain.type == "chain"
    assert chain.used_by == ("chain-router@file",)
    assert chain.errors
    auth = middlewares["api-auth@file"]
    assert auth.status is Status.enabled
    assert auth.type == "basicauth"
    assert auth.used_by == ("traefik-api@file",)


# --- Services / middlewares: synthetic -------------------------------------------


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ({"status": "enabled", "weighted": {"services": []}}, "weighted"),
        ({"status": "enabled", "mirroring": {}}, "mirroring"),
        ({"status": "enabled", "failover": {}}, "failover"),
        ({"status": "enabled", "loadBalancer": {}, "type": "custom"}, "custom"),
        ({"status": "enabled"}, ""),
        ({"status": "enabled", "type": 5}, ""),
    ],
)
def test_service_type(item: dict[str, Any], expected: str) -> None:
    assert parse_services({"s@file": item})["s@file"].type == expected


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ({"status": "enabled", "stripPrefix": {"prefixes": ["/a"]}}, "stripprefix"),
        ({"status": "enabled", "headers": {}, "usedBy": ["r@file"], "error": []}, "headers"),
        ({"status": "enabled", "type": "ratelimit", "rateLimit": {}}, "ratelimit"),
        ({"status": "enabled"}, ""),
        ({"status": "enabled", "headers": {}, "compress": {}}, ""),
    ],
)
def test_middleware_type(item: dict[str, Any], expected: str) -> None:
    assert parse_middlewares({"m@file": item})["m@file"].type == expected


@pytest.mark.parametrize(
    ("server_status", "total", "up"),
    [
        ({"a": "UP", "b": "UP", "c": "DOWN"}, 3, 2),
        ({}, 0, 0),
        (None, 0, 0),
        (["UP"], 0, 0),
    ],
)
def test_service_server_counts(server_status: object, total: int, up: int) -> None:
    item: dict[str, Any] = {"status": "enabled", "loadBalancer": {}}
    if server_status is not None:
        item["serverStatus"] = server_status

    service = parse_services({"s@file": item})["s@file"]

    assert (service.servers_total, service.servers_up) == (total, up)


@pytest.mark.parametrize("parse", [parse_services, parse_middlewares])
@pytest.mark.parametrize(
    ("payload", "error"),
    [("x", TypeError), (["x"], TypeError), ([{"status": "enabled"}], KeyError), ([{"name": 5}], TypeError)],
)
def test_service_and_middleware_shape_errors(parse: Any, payload: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        parse(payload)


# --- Entrypoints -----------------------------------------------------------------


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_captured_entrypoints(version: str) -> None:
    entrypoints = parse_entrypoints(load_fixture(version, "entrypoints.json"))

    assert list(entrypoints) == ["traefik", "udp-ep", "web", "websecure"]
    assert entrypoints["udp-ep"] == Entrypoint(name="udp-ep", address=":9999/udp", protocol="udp")
    assert entrypoints["web"] == Entrypoint(name="web", address=":80", protocol="tcp")


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ("x", TypeError),
        ({"web": {"address": ":80"}}, TypeError),
        (["x"], TypeError),
        ([{"address": ":80"}], KeyError),
        ([{"name": "web"}], KeyError),
        ([{"name": 1, "address": ":80"}], TypeError),
        ([{"name": "web", "address": 80}], TypeError),
    ],
)
def test_parse_entrypoints_shape_errors(payload: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        parse_entrypoints(payload)


def test_parse_entrypoints_empty() -> None:
    assert parse_entrypoints([]) == {}


# --- Version -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("version", "number", "codename"), [("v2.11", "2.11.63", "mimolette"), ("v3.7", "3.7.19", "langres")]
)
def test_captured_version(version: str, number: str, codename: str) -> None:
    parsed = parse_version(load_fixture(version, "version.json"))

    assert parsed.version == number
    assert parsed.codename == codename
    assert parsed.start_date.tzinfo is not None
    assert parsed.start_date.utcoffset() is not None
    assert parsed.start_date.year == 2026


def test_version_naive_start_date_is_utc_and_legacy_key_accepted() -> None:
    parsed = parse_version({"Version": "3.0.0", "StartDate": "2026-01-02T03:04:05"})

    assert parsed == TraefikVersion(version="3.0.0", codename="", start_date=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC))


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ({"Version": "3.0.0", "startDate": "yesterday"}, ValueError),
        ("x", TypeError),
        ({"startDate": "2026-01-02T03:04:05Z"}, KeyError),
        ({"Version": "3.0.0"}, KeyError),
        ({"Version": 3, "startDate": "2026-01-02T03:04:05Z"}, TypeError),
        ({"Version": "3.0.0", "startDate": 5}, TypeError),
    ],
)
def test_parse_version_errors(payload: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        parse_version(payload)


# --- parse_rawdata shape and empty payloads ------------------------------------------


@pytest.mark.parametrize(
    ("payload", "error"),
    [("x", TypeError), ([], TypeError), ({"routers": ["x"]}, TypeError), ({"services": "x"}, TypeError)],
)
def test_parse_rawdata_shape_errors(payload: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        parse_rawdata(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"routers": None, "services": None, "middlewares": None},
        {"tcpRouters": {"t@file": {"status": "enabled"}}, "udpServices": {"u@file": {"status": "enabled"}}},
    ],
)
def test_parse_rawdata_empty_sections(payload: dict[str, Any]) -> None:
    assert parse_rawdata(payload) == TraefikState(routers={}, services={}, middlewares={})


# --- Immutability ------------------------------------------------------------------


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_every_model_is_frozen(version: str) -> None:
    snapshot = _snapshot(version)
    state = parse_rawdata(_rawdata(version))
    instances: list[object] = [
        snapshot,
        state,
        snapshot.version,
        snapshot.router_counts,
        snapshot.entrypoints["web"],
        snapshot.routers["secure@file"],
        snapshot.routers["secure@file"].tls_domains[0],
        snapshot.services["lb-mixed@file"],
        snapshot.middlewares["api-auth@file"],
    ]
    expected = {
        Router,
        TlsDomain,
        Service,
        Middleware,
        Entrypoint,
        TraefikVersion,
        StatusCounts,
        TraefikState,
        TraefikSnapshot,
    }
    assert {type(i) for i in instances} == expected

    for instance in instances:
        assert dataclasses.is_dataclass(instance)
        first = dataclasses.fields(instance)[0].name
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(instance, first, None)


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_snapshots_from_equal_content_are_equal(version: str) -> None:
    assert _snapshot(version) == _snapshot(version)


# --- TraefikSnapshot aggregates (D-15) -------------------------------------------------


@pytest.mark.parametrize("version", FIXTURE_VERSIONS)
def test_snapshot_aggregates_from_capture(version: str) -> None:
    snapshot = _snapshot(version)

    for items, counts in (
        (snapshot.routers, snapshot.router_counts),
        (snapshot.services, snapshot.service_counts),
        (snapshot.middlewares, snapshot.middleware_counts),
    ):
        assert counts.total == len(items)
        assert counts.enabled + counts.warning + counts.error + counts.disabled == counts.total
    assert snapshot.router_counts.total == 128
    assert snapshot.router_counts.warning == 1
    assert snapshot.router_counts.error == 2
    assert snapshot.router_problems == (
        "broken-missing-service@file",
        "chain-router@file",
        "warn-unknown-entrypoint@file",
    )
    assert snapshot.router_problems == tuple(
        sorted(n for n, r in snapshot.routers.items() if r.status is not Status.enabled)
    )
    assert snapshot.service_problems == ("lb-mixed@file",)
    assert snapshot.middleware_problems == ("broken-chain@file",)
    assert snapshot.middleware_counts == StatusCounts(total=2, enabled=1, warning=0, error=1, disabled=0)


def test_snapshot_service_problems_and_sorting() -> None:
    state = parse_rawdata(
        {
            "routers": {
                "z@file": {"status": "warning"},
                "a@file": {"status": "disabled"},
                "m@file": {"status": "enabled"},
            },
            "services": {
                "ok@file": {"status": "enabled", "serverStatus": {"u1": "UP", "u2": "UP"}},
                "down@file": {"status": "enabled", "serverStatus": {"u1": "UP", "u2": "DOWN"}},
                "off@file": {"status": "disabled"},
                "bad@file": {"status": "disabled", "error": ["x"]},
            },
        }
    )
    version = TraefikVersion(version="3.7.19", codename="", start_date=datetime(2026, 1, 1, tzinfo=UTC))

    snapshot = TraefikSnapshot.build(version=version, entrypoints={}, state=state)

    assert snapshot.router_problems == ("a@file", "z@file")
    assert snapshot.router_counts == StatusCounts(total=3, enabled=1, warning=1, error=0, disabled=1)
    assert snapshot.service_problems == ("bad@file", "down@file", "off@file")
    assert snapshot.service_counts == StatusCounts(total=4, enabled=2, warning=0, error=1, disabled=1)
    assert snapshot.middleware_problems == ()


def test_snapshot_of_empty_state() -> None:
    version = TraefikVersion(version="2.11.0", codename="", start_date=datetime(2026, 1, 1, tzinfo=UTC))

    snapshot = TraefikSnapshot.build(version=version, entrypoints={}, state=parse_rawdata({}))

    zero = StatusCounts(total=0, enabled=0, warning=0, error=0, disabled=0)
    assert (snapshot.router_counts, snapshot.service_counts, snapshot.middleware_counts) == (zero, zero, zero)
    assert (snapshot.router_problems, snapshot.service_problems, snapshot.middleware_problems) == ((), (), ())
    assert snapshot.routers == {} and snapshot.services == {} and snapshot.middlewares == {}
