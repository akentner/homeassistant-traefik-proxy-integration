"""Tests for the pure Traefik rule parser and host normalizer (``rules.py``)."""

from __future__ import annotations

import pytest

from custom_components.traefik_proxy.rules import extract_hosts, normalize_host

# ---------------------------------------------------------------------------
# extract_hosts — literal Host() names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        # v2 multi-argument form
        ("Host(`a.example.com`, `b.example.com`)", ("a.example.com", "b.example.com")),
        # v3 OR form
        ("Host(`a.example.com`) || Host(`b.example.com`)", ("a.example.com", "b.example.com")),
        # AND mixed with another matcher, mixed case
        (
            "Host(`A.Example.com`) && PathPrefix(`/x`) || Host(`b.example.com`)",
            ("a.example.com", "b.example.com"),
        ),
        # single host
        ("Host(`api.example.com`)", ("api.example.com",)),
        # duplicates across calls collapse, first-seen order kept
        (
            "Host(`b.example.com`) || Host(`a.example.com`) || Host(`B.example.com`)",
            ("b.example.com", "a.example.com"),
        ),
        # duplicates inside one call
        ("Host(`a.example.com`,`a.example.com`)", ("a.example.com",)),
        # double-quoted arguments
        ('Host("a.example.com")', ("a.example.com",)),
        ('Host("a.example.com", `b.example.com`)', ("a.example.com", "b.example.com")),
        # whitespace inside the parentheses
        ("Host( `a.example.com` ,  `b.example.com` )", ("a.example.com", "b.example.com")),
        # Host() after a parenthesis group
        ("(Host(`a.example.com`) || Host(`b.example.com`)) && Path(`/x`)", ("a.example.com", "b.example.com")),
        # literal host kept next to a skipped regex matcher
        ("HostRegexp(`{sub:[a-z]+}.example.com`) || Host(`a.example.com`)", ("a.example.com",)),
        # a wildcard argument drops only that name
        ("Host(`*.example.com`, `a.example.com`)", ("a.example.com",)),
    ],
)
def test_extract_hosts_literal_names(rule: str, expected: tuple[str, ...]) -> None:
    """Literal Host() arguments come out lowercased, de-duplicated, in first-seen order."""
    assert extract_hosts(rule) == expected


@pytest.mark.parametrize(
    "rule",
    [
        "HostRegexp(`{sub:[a-z]+}.example.com`)",
        "HostSNI(`a.example.com`)",
        "HostSNIRegexp(`^.+$`)",
        "HostHeader(`a.example.com`)",
        "Host(`*.example.com`)",
        "Host(`{sub}.example.com`)",
        "!Host(`a.example.com`)",
        "! Host(`a.example.com`)",
        "PathPrefix(`/api`) && !Host(`a.example.com`)",
        "PathPrefix(`/api`)",
        "MyHost(`a.example.com`)",
        "Host()",
        "Host(`a.example.com`",
        "",
    ],
)
def test_extract_hosts_skips_non_literal_names(rule: str) -> None:
    """Regex, SNI, header, wildcard, template and negated matchers yield no host."""
    assert extract_hosts(rule) == ()


# ---------------------------------------------------------------------------
# normalize_host
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Example.COM.", "example.com"),
        ("  a.example.com ", "a.example.com"),
        ("Bücher.example", "xn--bcher-kva.example"),
        # IDNA 2008 / UTS-46 non-transitional, as browsers and ACME clients: deviation characters are encoded.
        ("straße.de", "xn--strae-oqa.de"),
        ("Straße.de", "xn--strae-oqa.de"),
        ("ς.example", "xn--3xa.example"),
        ("192.168.1.10", "192.168.1.10"),
        ("::1", "::1"),
        ("[::1]", "::1"),
        ("[2001:DB8:0:0::1]", "2001:db8::1"),
        ("my_host-1.example.com", "my_host-1.example.com"),
    ],
)
def test_normalize_host_accepts(name: str, expected: str) -> None:
    """Valid names are stripped, lowercased and converted to their ASCII form."""
    assert normalize_host(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        "*.example.com",
        "",
        "   ",
        ".",
        "a b.example.com",
        "a/b",
        "example.com:8443",
        "{sub}.example.com",
        "^.+$",
        "[not-an-ip]",
        "a..bÿ\u0000.example",
        "\u200d.example",
        "\U0001f600.example",
    ],
)
def test_normalize_host_rejects(name: str) -> None:
    """Empty, wildcard, template, regex, host:port and other invalid names are skipped."""
    assert normalize_host(name) is None
