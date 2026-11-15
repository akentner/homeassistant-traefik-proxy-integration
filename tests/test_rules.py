"""Tests for the pure Traefik rule parser, host normalizer and rule redactor (``rules.py``)."""

from __future__ import annotations

import random
import re
import string

import pytest
from homeassistant.components.diagnostics import REDACTED

from custom_components.traefik_proxy import rules
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


# ---------------------------------------------------------------------------
# redact_rule — header/query matcher values
# ---------------------------------------------------------------------------


def test_redact_rule_hides_a_header_value() -> None:
    """The header value becomes the marker; matcher names, the header key and Host stay readable."""
    assert (
        rules.redact_rule("Host(`a.example.com`) && Header(`X-Token`, `s3cret`)")
        == "Host(`a.example.com`) && Header(`X-Token`, `**REDACTED**`)"
    )


def test_redact_rule_keeps_a_host_only_rule() -> None:
    """A rule without secret-bearing matchers is returned unchanged."""
    assert rules.redact_rule("Host(`a.example.com`)") == "Host(`a.example.com`)"


def test_redact_rule_keeps_an_empty_rule() -> None:
    """An empty rule stays empty."""
    assert rules.redact_rule("") == ""


def test_redact_marker_matches_home_assistant() -> None:
    """The marker equals the one Home Assistant diagnostics use."""
    assert rules._REDACTED == REDACTED


R = REDACTED


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        ("Header(`X-Token`, `s3cret`)", f"Header(`X-Token`, `{R}`)"),
        ("headers(`Authorization`, `Bearer x`)", f"headers(`Authorization`, `{R}`)"),
        ("HEADERSREGEXP(`X-Key`, `^k.*$`)", f"HEADERSREGEXP(`X-Key`, `{R}`)"),
        ("HeaderRegexp(`X-Key`, `^k`)", f"HeaderRegexp(`X-Key`, `{R}`)"),
        # v2 query: every key=value pair keeps its key
        ("Query(`token=abc`, `x=1`)", f"Query(`token={R}`, `x={R}`)"),
        # v3 query: key, value
        ("Query(`key`, `val=ue`)", f"Query(`key`, `{R}`)"),
        ("Query(`mobile`)", "Query(`mobile`)"),
        ("QueryRegexp(`key`, `^v`)", f"QueryRegexp(`key`, `{R}`)"),
        # double-quoted Go string with an escaped quote, quote character kept
        ('Header("K", "v\\"q")', f'Header("K", "{R}")'),
        (
            "Host(`a.example.com`) || PathPrefix(`/api`) && !Method(`POST`)",
            "Host(`a.example.com`) || PathPrefix(`/api`) && !Method(`POST`)",
        ),
        (
            "ClientIP(`10.0.0.0/8`) && HostRegexp(`^.+\\.example\\.com$`)",
            "ClientIP(`10.0.0.0/8`) && HostRegexp(`^.+\\.example\\.com$`)",
        ),
        ("(Header(`X`, `y`) && HostHeader(`a`))", f"(Header(`X`, `{R}`) && HostHeader(`a`))"),
        # whitespace between the tokens is kept
        ("Host (`a`)  &&  Header( `X` ,`y` )", f"Host (`a`)  &&  Header( `X` ,`{R}` )"),
        # fail closed: the whole rule is redacted
        ("Heder(`X`, `y`)", R),
        ("Header(`X`, `y)", R),
        ("Header(`X`, `y`,)", R),
        ("Host(`a`) `stray`", R),
        ("Header()", R),
        ("Header('X', 'y')", R),
        ("Host(`a`) && Header(`X`, `y`", R),
        ("Host(`a`) , Header(`X`, `y`)", R),
    ],
)
def test_redact_rule_table(rule: str, expected: str) -> None:
    """Header and query values become the marker; anything the grammar does not allow is redacted whole."""
    assert rules.redact_rule(rule) == expected


def test_redact_rule_keeps_a_whitespace_only_rule() -> None:
    """A whitespace-only rule is returned unchanged."""
    assert rules.redact_rule("  ") == "  "


# Secrets are digit runs; everything else in the generated rules is digit-free,
# so a run of four digits in the output can only come from a secret.
_SECRET_DIGITS = re.compile(r"\d{4}")


def _random_rule(rng: random.Random) -> str:
    """Return a random rule of safe, header and query matchers, possibly mutated by random characters."""

    def secret() -> str:
        return "".join(rng.choice(string.digits) for _ in range(8))

    def name(base: str) -> str:
        return rng.choice([base, base.lower(), base.upper(), base.title()])

    def quoted(text: str) -> str:
        return rng.choice([f"`{text}`", f'"{text}"'])

    matchers = [
        lambda: f"{name('Host')}({quoted('a.example.com')})",
        lambda: f"{name('PathPrefix')}({quoted('/api')})",
        lambda: (
            f"{name(rng.choice(['Header', 'Headers', 'HeaderRegexp', 'HeadersRegexp']))}"
            f"({quoted('X-Key')}, {quoted(secret())})"
        ),
        lambda: f"{name(rng.choice(['Query', 'QueryRegexp']))}({quoted('token')}, {quoted(secret())})",
        lambda: f"{name('Query')}({quoted('token=' + secret())}, {quoted('x=' + secret())})",
    ]
    parts = []
    for _ in range(rng.randint(1, 4)):
        call = rng.choice(matchers)()
        if rng.random() < 0.2:
            call = f"!({call})"
        parts.append(call)
    rule = rng.choice([" && ", " || "]).join(parts)
    for _ in range(rng.randint(0, 2)):
        position = rng.randint(0, len(rule))
        if rng.random() < 0.5 and position < len(rule):
            rule = rule[:position] + rule[position + 1 :]
        else:
            rule = rule[:position] + rng.choice(string.printable) + rule[position:]
    return rule


def test_redact_rule_random_rules_never_leak() -> None:
    """200 random, partly mutated rules never raise and never keep a header or query value."""
    rng = random.Random(4040)
    for _ in range(200):
        rule = _random_rule(rng)
        redacted = rules.redact_rule(rule)
        assert isinstance(redacted, str)
        assert _SECRET_DIGITS.search(redacted) is None, (rule, redacted)
