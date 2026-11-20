"""Capture real Traefik API responses into redacted test fixtures.

Brings up the throwaway harness in ``compose.yaml``, waits until Traefik has
loaded the scenario, captures the API responses, redacts them and writes them
to ``tests/fixtures/<version>/``. The stack is torn down afterwards.

    uv run python tests/traefik/capture.py [--only v3.7] [--keep-up]

Re-captured fixtures are byte-stable only while the throwaway certificate in
``tests/traefik/certs/`` is kept: it is generated on the first run and reused
afterwards, but it is git-ignored, so a fresh checkout or a deleted
``certs/`` directory generates a new one and changes the certificate
fixtures (serial number and validity dates) on the next capture.

This file is a script, not a test module: pytest never collects or runs it.
Importing it has no side effects (tests load it to reuse the constants and the
``Redactor``).
"""

from __future__ import annotations

import argparse
import base64
import getpass
import ipaddress
import json
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HARNESS_DIR = Path(__file__).resolve().parent
REPO_ROOT = HARNESS_DIR.parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
COMPOSE_FILE = HARNESS_DIR / "compose.yaml"
SCENARIO_FILE = HARNESS_DIR / "dynamic" / "scenario.yml"
BULK_FILE = HARNESS_DIR / "dynamic" / "bulk.yml"
CERT_DIR = HARNESS_DIR / "certs"

# Harness-only credentials. They protect a throwaway container bound to
# 127.0.0.1 and are not secrets; the capture still proves they never reach a
# fixture.
HARNESS_USER = "capture"
HARNESS_PASSWORD = "harness-only-not-a-secret"

PAGE_SIZE = 100
MAX_PAGES = 50
PAGED_KINDS = ("routers", "services", "middlewares")
BULK_ROUTERS = 120
READY_TIMEOUT = 90.0
REQUEST_TIMEOUT = 10.0


@dataclass(frozen=True, slots=True)
class Target:
    """One Traefik generation in the harness."""

    service: str
    port: int
    certificates: bool = False


# Fixture directory name -> compose service and loopback host port.
TARGETS: dict[str, Target] = {
    "v2.11": Target(service="traefik-v2", port=18211),
    "v3.7": Target(service="traefik-v3", port=18370, certificates=True),
}


class CaptureError(RuntimeError):
    """Raised when the harness does not behave as the capture expects."""


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

DOC_V4_NETS = (
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
)
DOC_V6_NET = ipaddress.ip_network("2001:db8::/32")

IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
IPV6_RE = re.compile(r"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![0-9A-Fa-f:])")
UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
# Container-ID-shaped tokens (full and short form). Requiring a letter and a
# digit keeps plain numbers and plain words out.
CONTAINER_ID_RE = re.compile(r"\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*[0-9])(?:[0-9a-f]{64}|[0-9a-f]{12})\b")
AUTH_MIDDLEWARE_KEYS = frozenset({"basicAuth", "digestAuth"})
ZERO_UUID = "00000000-0000-0000-0000-000000000000"


def is_documentation_ip(value: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True when the address sits in an RFC 5737 / RFC 3849 range."""
    if isinstance(value, ipaddress.IPv4Address):
        return any(value in net for net in DOC_V4_NETS)
    return value in DOC_V6_NET


def iter_ip_literals(text: str) -> Iterator[tuple[str, ipaddress.IPv4Address | ipaddress.IPv6Address]]:
    """Yield ``(literal, address)`` for every valid IP literal in ``text``."""
    for regex in (IPV4_RE, IPV6_RE):
        for match in regex.finditer(text):
            try:
                yield match.group(0), ipaddress.ip_address(match.group(0))
            except ValueError:
                continue


def _v4_pool() -> Iterator[ipaddress.IPv4Address]:
    for net in DOC_V4_NETS[:2]:
        yield from net.hosts()


class Redactor:
    """Replace identifying values in captured payloads.

    One instance serves a whole capture run (all files, all generations), so
    the same source value maps to the same replacement everywhere. Addresses
    are assigned in order of first appearance during a sorted-key traversal,
    which keeps re-runs byte-identical.
    """

    def __init__(self, hostname: str | None = None, username: str | None = None) -> None:
        self._v4: dict[str, str] = {}
        self._v6: dict[str, str] = {}
        self._reserved: set[str] = set()
        self._v4_pool = _v4_pool()
        self._v6_next = 1
        self._literals: list[tuple[re.Pattern[str], str]] = []
        for value, replacement in (
            (hostname if hostname is not None else socket.gethostname(), "capture-host.example.org"),
            (username if username is not None else getpass.getuser(), "capture-user"),
        ):
            if len(value) >= 3:
                self._literals.append((re.compile(rf"(?<![\w-]){re.escape(value)}(?![\w-])"), replacement))

    def reserve(self, obj: Any) -> None:
        """Mark documentation addresses already present so none is reused."""
        for text in _iter_strings(obj):
            for literal, address in iter_ip_literals(text):
                if is_documentation_ip(address):
                    self._reserved.add(str(address))
                    self._reserved.add(literal)

    def redact(self, obj: Any) -> Any:
        """Return a redacted deep copy of ``obj``."""
        if isinstance(obj, dict):
            result: dict[str, Any] = {}
            for key in sorted(obj):
                value = obj[key]
                if key in AUTH_MIDDLEWARE_KEYS and isinstance(value, dict):
                    value = {k: (["redacted:redacted"] if k == "users" else v) for k, v in value.items()}
                result[self.redact_text(key)] = self.redact(value)
            return result
        if isinstance(obj, list):
            return [self.redact(item) for item in obj]
        if isinstance(obj, str):
            return self.redact_text(obj)
        return obj

    def redact_text(self, text: str) -> str:
        """Redact one string."""
        text = UUID_RE.sub(ZERO_UUID, text)
        text = CONTAINER_ID_RE.sub(lambda m: "0" * len(m.group(0)), text)
        text = IPV4_RE.sub(self._map_v4, text)
        text = IPV6_RE.sub(self._map_v6, text)
        for pattern, replacement in self._literals:
            text = pattern.sub(replacement, text)
        return text

    def _map_v4(self, match: re.Match[str]) -> str:
        literal = match.group(0)
        try:
            address = ipaddress.IPv4Address(literal)
        except ValueError:
            return literal
        if is_documentation_ip(address):
            return literal
        if literal not in self._v4:
            for candidate in self._v4_pool:
                if str(candidate) not in self._reserved:
                    self._v4[literal] = str(candidate)
                    break
            else:
                raise CaptureError("documentation IPv4 pool exhausted")
        return self._v4[literal]

    def _map_v6(self, match: re.Match[str]) -> str:
        literal = match.group(0)
        try:
            address = ipaddress.IPv6Address(literal)
        except ValueError:
            return literal
        if is_documentation_ip(address):
            return literal
        if literal not in self._v6:
            while True:
                candidate = str(ipaddress.IPv6Address(f"2001:db8::{self._v6_next:x}"))
                self._v6_next += 1
                if candidate not in self._reserved:
                    break
            self._v6[literal] = candidate
        return self._v6[literal]


def _iter_strings(obj: Any) -> Iterator[str]:
    if isinstance(obj, dict):
        for key in sorted(obj):
            yield key
            yield from _iter_strings(obj[key])
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_strings(item)
    elif isinstance(obj, str):
        yield obj


# ---------------------------------------------------------------------------
# Secrets that must never reach a fixture
# ---------------------------------------------------------------------------


def basic_token() -> str:
    """Return the base64 Basic token of the harness credentials."""
    return base64.b64encode(f"{HARNESS_USER}:{HARNESS_PASSWORD}".encode()).decode()


def htpasswd_hash() -> str:
    """Return the htpasswd hash for HARNESS_USER as written in scenario.yml."""
    match = re.search(rf"{re.escape(HARNESS_USER)}:(\$2[aby]\$\d\d\$[./A-Za-z0-9]{{53}})", SCENARIO_FILE.read_text())
    if match is None:
        raise CaptureError(f"no htpasswd entry for {HARNESS_USER!r} in {SCENARIO_FILE}")
    return match.group(1)


def forbidden_strings() -> tuple[str, ...]:
    """Return every harness credential representation."""
    return (HARNESS_PASSWORD, basic_token(), htpasswd_hash())


# ---------------------------------------------------------------------------
# HTTP + docker helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Response:
    """Minimal HTTP response."""

    status: int
    headers: dict[str, str]
    body: bytes


def http_get(port: int, path: str, *, auth: tuple[str, str] | None) -> Response:
    """GET ``path`` from the harness on 127.0.0.1:``port``."""
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    if auth is not None:
        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        request.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as resp:
            return Response(resp.status, dict(resp.headers.items()), resp.read())
    except urllib.error.HTTPError as err:
        return Response(err.code, dict(err.headers.items()), err.read())


def fetch_json(port: int, path: str) -> tuple[Any, dict[str, str]]:
    """GET ``path`` with harness credentials; return ``(json, headers)``."""
    resp = http_get(port, path, auth=(HARNESS_USER, HARNESS_PASSWORD))
    if resp.status != 200:
        raise CaptureError(f"GET {path} returned {resp.status}")
    return json.loads(resp.body), resp.headers


def compose(*args: str) -> None:
    """Run ``docker compose`` against the harness file."""
    subprocess.run(["docker", "compose", "-f", str(COMPOSE_FILE), *args], check=True)


def wait_for(description: str, check: Any, timeout: float = READY_TIMEOUT) -> Any:
    """Poll ``check()`` until it returns a truthy value or ``timeout`` passes."""
    deadline = time.monotonic() + timeout
    last_error = "no attempt"
    while time.monotonic() < deadline:
        try:
            result = check()
        except (OSError, CaptureError, ValueError) as err:
            last_error = str(err)
        else:
            if result:
                return result
            last_error = "condition not met"
        time.sleep(1.0)
    raise CaptureError(f"timed out after {timeout:.0f}s waiting for {description} ({last_error})")


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


def check_auth(port: int) -> None:
    """Fail unless the API rejects missing and wrong credentials."""
    for label, auth in (("no credentials", None), ("wrong password", (HARNESS_USER, "wrong-password"))):
        status = http_get(port, "/api/version", auth=auth).status
        if status != 401:
            raise CaptureError(f"API answered {status} with {label}; it must not be reachable unauthenticated")


def _rawdata_ready(port: int) -> dict[str, Any] | None:
    """Return rawdata once every scenario element has settled, else None."""
    rawdata, _ = fetch_json(port, "/api/rawdata")
    routers = rawdata.get("routers") or {}
    services = rawdata.get("services") or {}
    if not any(name.endswith("@docker") for name in routers):
        return None
    if f"bulk-{BULK_ROUTERS - 1:03d}@file" not in routers or "secure@file" not in routers:
        return None
    states = sorted((services.get("lb-mixed@file") or {}).get("serverStatus", {}).values())
    if states != ["DOWN", "UP"]:
        return None
    return rawdata


def fetch_pages(port: int, kind: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Fetch every page of ``/api/http/<kind>``; return files and index entries."""
    files: dict[str, Any] = {}
    index: list[dict[str, Any]] = []
    page = 1
    while True:
        if page > MAX_PAGES:
            raise CaptureError(f"/api/http/{kind} did not terminate within {MAX_PAGES} pages")
        body, headers = fetch_json(port, f"/api/http/{kind}?per_page={PAGE_SIZE}&page={page}")
        if not isinstance(body, list):
            raise CaptureError(f"/api/http/{kind} page {page} is not a list")
        raw_next = next((v for k, v in headers.items() if k.lower() == "x-next-page"), None)
        file_name = f"{kind}_{page}.json"
        files[f"pages/{file_name}"] = body
        index.append({"page": page, "file": file_name, "x_next_page": raw_next})
        try:
            next_page = int(raw_next) if raw_next is not None else None
        except ValueError:
            next_page = None
        if next_page is None or next_page <= page:
            return files, index
        page = next_page


def capture_version(name: str, target: Target) -> dict[str, Any]:
    """Capture one Traefik generation; return ``{relative path: payload}``."""
    port = target.port
    print(f"[{name}] waiting for the API on 127.0.0.1:{port}", file=sys.stderr)
    wait_for(
        f"{name} /api/version",
        lambda: http_get(port, "/api/version", auth=(HARNESS_USER, HARNESS_PASSWORD)).status == 200,
    )
    check_auth(port)
    wait_for(f"{name} scenario", lambda: _rawdata_ready(port))

    files: dict[str, Any] = {}
    files["version.json"], _ = fetch_json(port, "/api/version")
    files["entrypoints.json"], _ = fetch_json(port, "/api/entrypoints")
    files["rawdata.json"], _ = fetch_json(port, "/api/rawdata")
    page_index: dict[str, Any] = {"per_page": PAGE_SIZE}
    for kind in PAGED_KINDS:
        page_files, page_index[kind] = fetch_pages(port, kind)
        files.update(page_files)
    files["pages/index.json"] = page_index
    if target.certificates:
        files["certificates.json"], _ = fetch_json(port, "/api/certificates")

    _print_summary(name, files)
    return files


def _print_summary(name: str, files: dict[str, Any]) -> None:
    rawdata = files["rawdata.json"]
    index = files["pages/index.json"]
    for kind in PAGED_KINDS:
        pages = index[kind]
        headers = [entry["x_next_page"] for entry in pages]
        print(
            f"[{name}] {kind}: {len(rawdata.get(kind, {}))} in rawdata, {len(pages)} page(s), X-Next-Page {headers}",
            file=sys.stderr,
        )
    for kind in PAGED_KINDS:
        for item_name, item in sorted(rawdata.get(kind, {}).items()):
            if item.get("status") != "enabled" or item.get("error"):
                print(f"[{name}] {kind} {item_name}: {item.get('status')} {item.get('error')}", file=sys.stderr)


def generate_bulk_routers(path: Path) -> None:
    """Write the file-provider routers that push the list endpoints past one page."""
    lines = [
        "# Generated by tests/traefik/capture.py (generate_bulk_routers). Do not edit.",
        "http:",
        "  routers:",
    ]
    for n in range(BULK_ROUTERS):
        lines += [
            f"    bulk-{n:03d}:",
            "      entryPoints:",
            "        - web",
            f"      rule: Host(`bulk-{n:03d}.example.com`)",
            "      service: bulk-svc",
        ]
    path.write_text("\n".join(lines) + "\n")


def generate_self_signed_cert(cert_dir: Path) -> None:
    """Create a throwaway self-signed cert for secure.example.com unless present."""
    cert_path = cert_dir / "secure.crt"
    key_path = cert_dir / "secure.key"
    if cert_path.exists() and key_path.exists():
        return
    # Imported lazily: only the capture needs it (Home Assistant ships it).
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "secure.example.com")])
    now = datetime.datetime.now(datetime.UTC).replace(microsecond=0)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=90))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("secure.example.com"), x509.DNSName("www.secure.example.com")]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_dir.mkdir(exist_ok=True)
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def write_fixtures(name: str, files: dict[str, Any], redactor: Redactor) -> list[Path]:
    """Redact and write the files of one generation."""
    out_dir = FIXTURES_DIR / name
    # Drop stale pages so the directory always matches the latest capture.
    for stale in (out_dir / "pages").glob("*.json"):
        stale.unlink()
    written: list[Path] = []
    for rel in sorted(files):
        path = out_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(redactor.redact(files[rel]), indent=2, sort_keys=True) + "\n")
        written.append(path)
    return written


def verify_no_secrets(paths: list[Path]) -> None:
    """Fail when any harness credential survived redaction."""
    forbidden = forbidden_strings()
    for path in paths:
        text = path.read_text()
        for secret in forbidden:
            if secret in text:
                raise CaptureError(f"{path.relative_to(REPO_ROOT)} still contains a harness credential")


def main(argv: list[str] | None = None) -> int:
    """Run the capture."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", choices=sorted(TARGETS), help="capture a single Traefik generation")
    parser.add_argument("--keep-up", action="store_true", help="leave the harness running afterwards")
    args = parser.parse_args(argv)

    names = [args.only] if args.only else sorted(TARGETS)
    # Create the bind-mount sources ourselves; docker would create them root-owned.
    CERT_DIR.mkdir(exist_ok=True)
    generate_self_signed_cert(CERT_DIR)
    generate_bulk_routers(BULK_FILE)

    compose("up", "-d", "whoami", *(TARGETS[name].service for name in names))
    try:
        captured = {name: capture_version(name, TARGETS[name]) for name in names}
    except CaptureError as err:
        print(f"capture failed: {err}", file=sys.stderr)
        return 1
    finally:
        if not args.keep_up:
            compose("down", "-v", "--remove-orphans")

    redactor = Redactor()
    for name in names:
        redactor.reserve(captured[name])
    written: list[Path] = []
    for name in names:
        written += write_fixtures(name, captured[name], redactor)
    try:
        verify_no_secrets(written)
    except CaptureError as err:
        print(f"redaction check failed: {err}", file=sys.stderr)
        return 1
    print(f"wrote {len(written)} fixture files", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
