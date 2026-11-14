"""Guards for the captured Traefik fixtures in tests/fixtures/<version>/.

The fixtures are real API captures written by tests/traefik/capture.py. These
tests never start Docker or touch the network: they scan the committed files
for anything that must not be published (non-documentation IPs, real
hostnames, harness credentials).
"""

from __future__ import annotations

import importlib.util
import ipaddress
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

TESTS_DIR = Path(__file__).parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
CAPTURE_SCRIPT = TESTS_DIR / "traefik" / "capture.py"
GENERATIONS = ("v2.11", "v3.7")

FIXTURE_FILES = sorted(path for gen in GENERATIONS for path in (FIXTURES_DIR / gen).rglob("*.json"))

DOC_NETS = tuple(
    ipaddress.ip_network(net) for net in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32")
)
ALLOWED_HOST_SUFFIXES = ("example.com", "example.org", "example.net")
# Dotted tokens that look like hostnames but are not. Keep this explicit and
# minimal; every entry needs a reason.
NON_HOST_TOKENS: frozenset[str] = frozenset()

IPV4_RE = re.compile(r"(?<!\d)\d{1,3}(?:\.\d{1,3}){3}(?!\d)")
IPV6_RE = re.compile(r"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![0-9A-Fa-f:])")
HOST_RE = re.compile(r"(?<![\w.-])(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}(?![\w-])")


def _load_capture() -> ModuleType:
    """Load the capture script by path; it has no import side effects."""
    spec = importlib.util.spec_from_file_location("traefik_capture", CAPTURE_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def capture() -> ModuleType:
    """The capture script as a module."""
    return _load_capture()


def _strings(obj: Any) -> Iterator[str]:
    """Yield every dict key and string value in ``obj``."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield key
            yield from _strings(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _strings(item)
    elif isinstance(obj, str):
        yield obj


def _ip_literals(text: str) -> Iterator[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    for regex in (IPV4_RE, IPV6_RE):
        for match in regex.finditer(text):
            try:
                yield ipaddress.ip_address(match.group(0))
            except ValueError:
                continue


def _is_allowed_host(token: str) -> bool:
    host = token.lower()
    if host in NON_HOST_TOKENS:
        return True
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in ALLOWED_HOST_SUFFIXES)


def _fixture_id(path: Path) -> str:
    return str(path.relative_to(FIXTURES_DIR))


def test_captures_exist() -> None:
    """At least one capture generation is committed; the scans below never pass vacuously."""
    assert FIXTURE_FILES, f"no captured fixtures under {FIXTURES_DIR}/{{{','.join(GENERATIONS)}}}"


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=_fixture_id)
def test_fixture_has_only_documentation_ips(path: Path) -> None:
    """Every IP literal sits in RFC 5737 (IPv4) or RFC 3849 (IPv6) documentation space."""
    offenders = sorted(
        {
            str(address)
            for text in _strings(json.loads(path.read_text()))
            for address in _ip_literals(text)
            if not any(address in net for net in DOC_NETS)
        }
    )
    assert not offenders, f"{_fixture_id(path)} contains non-documentation IPs: {offenders}"


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=_fixture_id)
def test_fixture_has_only_example_hostnames(path: Path) -> None:
    """Every hostname-like token ends in example.com, example.org or example.net."""
    offenders = sorted(
        {
            match.group(0)
            for text in _strings(json.loads(path.read_text()))
            for match in HOST_RE.finditer(text)
            if not _is_allowed_host(match.group(0))
        }
    )
    assert not offenders, f"{_fixture_id(path)} contains non-example hostnames: {offenders}"


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=_fixture_id)
def test_fixture_has_no_harness_credentials(path: Path, capture: ModuleType) -> None:
    """Neither the password, its Basic token nor the htpasswd hash appears in a fixture."""
    text = path.read_text()
    secrets = {
        "password": capture.HARNESS_PASSWORD,
        "basic token": capture.basic_token(),
        "htpasswd hash": capture.htpasswd_hash(),
    }
    leaked = [label for label, secret in secrets.items() if secret in text]
    assert not leaked, f"{_fixture_id(path)} leaks harness credentials: {leaked}"


def test_htpasswd_hash_is_read_from_scenario(capture: ModuleType) -> None:
    """The credential scan reads the real hash, so it cannot pass on an empty value."""
    scenario = (TESTS_DIR / "traefik" / "dynamic" / "scenario.yml").read_text()
    assert capture.htpasswd_hash().startswith("$2")
    assert f"{capture.HARNESS_USER}:{capture.htpasswd_hash()}" in scenario


# ---------------------------------------------------------------------------
# Scenario coverage: a thin capture must fail, not pass
# ---------------------------------------------------------------------------


def _load(gen: str, rel: str) -> Any:
    path = FIXTURES_DIR / gen / rel
    assert path.is_file(), f"{gen}: missing capture file {rel}"
    return json.loads(path.read_text())


@pytest.mark.parametrize("gen", GENERATIONS)
def test_capture_covers_scenario(gen: str) -> None:
    """Each generation contains every scenario element the later plans rely on."""
    rawdata = _load(gen, "rawdata.json")
    routers: dict[str, Any] = rawdata.get("routers", {})
    services: dict[str, Any] = rawdata.get("services", {})

    for provider in ("docker", "file", "internal"):
        assert any(name.endswith(f"@{provider}") for name in routers), f"{gen}: no @{provider} router in rawdata"
    assert any(router.get("error") for router in routers.values()), f"{gen}: no router with a non-empty error list"
    assert any({"UP", "DOWN"} <= set((service.get("serverStatus") or {}).values()) for service in services.values()), (
        f"{gen}: no service whose serverStatus holds both UP and DOWN"
    )
    assert any((router.get("tls") or {}).get("domains") for router in routers.values()), (
        f"{gen}: no router with tls.domains"
    )
    assert len(routers) > 100, f"{gen}: only {len(routers)} routers; the paginated path needs more than 100"

    index = _load(gen, "pages/index.json")
    router_pages = index.get("routers", [])
    assert len(router_pages) >= 2, f"{gen}: routers fit on {len(router_pages)} page(s); expected at least 2"
    paged = [item for entry in router_pages for item in _load(gen, f"pages/{entry['file']}")]
    assert len(paged) == len(routers), f"{gen}: {len(paged)} routers across pages vs {len(routers)} in rawdata"


def test_v37_capture_has_certificates() -> None:
    """The v3.7 capture includes /api/certificates (Phase 6 input)."""
    certificates = _load("v3.7", "certificates.json")
    assert isinstance(certificates, list), "v3.7: certificates.json is not a list"
    assert certificates, "v3.7: certificates.json is empty"


# ---------------------------------------------------------------------------
# Redactor behaviour
# ---------------------------------------------------------------------------


def test_redactor_maps_ips_consistently(capture: ModuleType) -> None:
    """Same source IP -> same documentation IP (keys and values); distinct IPs stay distinct."""
    redactor = capture.Redactor(hostname="", username="")
    source = {
        "loadBalancer": {"servers": [{"url": "http://10.1.2.3:80"}, {"url": "http://172.16.5.4:80"}]},
        "serverStatus": {"http://10.1.2.3:80": "UP", "http://172.16.5.4:80": "DOWN"},
        "middleware": {"basicAuth": {"users": ["someone:$apr1$abc$def"], "realm": "r"}},
    }
    redacted = redactor.redact(source)

    servers = [server["url"] for server in redacted["loadBalancer"]["servers"]]
    assert sorted(redacted["serverStatus"]) == sorted(servers), "dict-key and value mappings differ"
    assert servers[0] != servers[1], "distinct source IPs collapsed into one"
    doc_net = ipaddress.ip_network("192.0.2.0/24")
    for url in servers:
        host = url.removeprefix("http://").split(":")[0]
        assert ipaddress.ip_address(host) in doc_net, f"{host} is outside 192.0.2.0/24"
    assert redacted["middleware"]["basicAuth"] == {"users": ["redacted:redacted"], "realm": "r"}
    assert "10.1.2.3" not in json.dumps(redacted)
    assert "172.16.5.4" not in json.dumps(redacted)


def test_redactor_never_reuses_reserved_documentation_ip(capture: ModuleType) -> None:
    """A documentation IP already in the capture is never handed out for a private IP."""
    redactor = capture.Redactor(hostname="", username="")
    source = {"a": "http://10.0.0.1:80", "b": "http://192.0.2.1:80", "c": "fd00::1"}
    redactor.reserve(source)
    redacted = redactor.redact(source)
    assert redacted["b"] == "http://192.0.2.1:80"
    assert redacted["a"] not in {"http://192.0.2.1:80", "http://10.0.0.1:80"}
    assert ipaddress.ip_address(redacted["c"]) in ipaddress.ip_network("2001:db8::/32")


def test_redactor_replaces_identifiers(capture: ModuleType) -> None:
    """Machine host/user names, UUIDs and container IDs are normalised."""
    redactor = capture.Redactor(hostname="build-box", username="alice")
    text = "build-box alice 123e4567-e89b-12d3-a456-426614174000 0123456789ab " + "ab12" * 16
    assert redactor.redact_text(text) == (
        "capture-host.example.org capture-user 00000000-0000-0000-0000-000000000000 000000000000 " + "0" * 64
    )


# ---------------------------------------------------------------------------
# Harness isolation
# ---------------------------------------------------------------------------


def test_harness_is_not_collectable() -> None:
    """Nothing under tests/traefik looks like a test module or conftest to pytest."""
    harness = TESTS_DIR / "traefik"
    offenders = sorted(
        str(path.relative_to(TESTS_DIR))
        for pattern in ("test_*.py", "*_test.py", "conftest.py")
        for path in harness.rglob(pattern)
    )
    assert not offenders, f"collectable files in the capture harness: {offenders}"
