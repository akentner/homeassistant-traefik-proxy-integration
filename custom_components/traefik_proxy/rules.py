"""Host names from Traefik router rules, and rules with their secrets redacted.

Pure module: no Home Assistant imports; besides the stdlib only ``idna``
(bundled with Home Assistant through ``yarl``). Router rules come from
the Traefik API and are treated as untrusted text: only literal ``Host()``
arguments are returned, never regex, SNI, header, template or wildcard
patterns, and every name goes through :func:`normalize_host`.

:func:`redact_rule` hides the values of header and query matchers, which
may carry tokens or keys, while the rest of the rule stays readable. A rule
it cannot parse is redacted as a whole. :func:`rule_secret_values` returns
the values it hides, so text that quotes them elsewhere can be detected.

Supported rule shapes:

- Traefik v2 multi-argument matcher: ``Host(`a.example.com`, `b.example.com`)``;
- Traefik v3 combinations: ``Host(`a`) || Host(`b`)``, ``Host(`a`) && PathPrefix(`/x`)``;
- backtick or double-quoted arguments.

A negated ``!Host(...)`` contributes no name, because the router does not
serve it. A negated group such as ``!(Host(`a`) || Host(`b`))`` is not
detected.
"""

from __future__ import annotations

import ipaddress
import re

import idna

# ``Host(`` not preceded by a word character. ``HostRegexp(``, ``HostSNI(``,
# ``HostSNIRegexp(`` and ``HostHeader(`` never match: their next character
# after ``Host`` is not ``(``.
_HOST_MATCHER = re.compile(r"(?<![A-Za-z0-9_])Host\(")

# The argument list of one matcher: quoted strings separated by commas,
# closed by ``)``.
_QUOTED = r"(?:`[^`]*`|\"[^\"]*\")"
_ARGUMENT_LIST = re.compile(rf"\s*({_QUOTED}(?:\s*,\s*{_QUOTED})*)\s*\)")
_ARGUMENT = re.compile(r"`([^`]*)`|\"([^\"]*)\"")

# Allowed characters of a normalized DNS name (ASCII A-label form).
_HOST_CHARS = re.compile(r"[a-z0-9._-]+")

# Marker for redacted values; equal to the one of Home Assistant diagnostics.
_REDACTED = "**REDACTED**"

# HTTP matcher names of Traefik v2 and v3, lowercase. Traefik accepts each
# name in its exact, lower, UPPER and Title case, so names are compared
# case-insensitively.
_SAFE_MATCHERS = frozenset(
    {"clientip", "host", "hostheader", "hostregexp", "method", "path", "pathprefix", "pathregexp"}
)
# Argument 0 is the header name and stays; every further argument is a value.
_HEADER_MATCHERS = frozenset({"header", "headerregexp", "headers", "headersregexp"})
# v3: ``Query(key[, value])``; v2: ``Query(`key=value`, ...)``.
_QUERY_MATCHERS = frozenset({"query", "queryregexp"})
_MATCHERS = _SAFE_MATCHERS | _HEADER_MATCHERS | _QUERY_MATCHERS

# One token of a rule. Every alternative starts with a distinct character
# class, so a scan is linear in the rule length. A backtick literal cannot
# contain a backtick; a double-quoted literal is a Go string with
# backslash escapes.
_TOKEN = re.compile(
    r"(?P<space>\s+)"
    r"|(?P<operator>&&|\|\||[!(),])"
    r'|(?P<literal>`[^`]*`|"(?:[^"\\]|\\.)*")'
    r"|(?P<name>[A-Za-z][A-Za-z0-9]*)"
)

# A name followed by optional whitespace and ``(``, not preceded by a word character.
_CALL = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9]*)\s*\(")


def normalize_host(name: str) -> str | None:
    """Return the canonical form of a host name, or None when it cannot be probed.

    Strips whitespace, lowercases and removes one trailing dot. IP literals
    (IPv6 also in ``[...]`` form) are returned in compressed form. Non-ASCII
    names are converted to A-labels with IDNA 2008 / UTS-46 non-transitional
    processing, as browsers and ACME clients do (``straße.de`` becomes
    ``xn--strae-oqa.de``, not ``strasse.de``). Empty names, wildcards and any
    name with a character outside ``[a-z0-9._-]`` (templates, regex syntax,
    slashes, spaces, ``host:port``) or an empty label are skipped.
    """
    host = name.strip().lower()
    if host.endswith("."):
        host = host[:-1]
    bracketed = host.startswith("[") and host.endswith("]")
    if bracketed:
        host = host[1:-1]
    if not host:
        return None
    if "%" not in host:
        try:
            return ipaddress.ip_address(host).compressed
        except ValueError:
            pass
    if bracketed:
        return None
    if not host.isascii():
        try:
            host = idna.encode(host, uts46=True, transitional=False).decode("ascii")
        except UnicodeError:  # idna.IDNAError is a UnicodeError
            return None
    if not _HOST_CHARS.fullmatch(host) or "" in host.split("."):
        return None
    return host


def _is_negated(rule: str, start: int) -> bool:
    """Return True when the last non-whitespace character before ``start`` is ``!``."""
    index = start - 1
    while index >= 0 and rule[index].isspace():
        index -= 1
    return index >= 0 and rule[index] == "!"


def extract_hosts(rule: str) -> tuple[str, ...]:
    """Return the literal ``Host()`` names of a Traefik rule.

    Names are normalized, de-duplicated and returned in first-seen order.
    Arguments that fail :func:`normalize_host` are dropped; a matcher
    preceded by ``!`` or without a well-formed argument list contributes
    nothing.
    """
    hosts: dict[str, None] = {}
    for matcher in _HOST_MATCHER.finditer(rule):
        if _is_negated(rule, matcher.start()):
            continue
        arguments = _ARGUMENT_LIST.match(rule, matcher.end())
        if arguments is None:
            continue
        for backtick, quoted in _ARGUMENT.findall(arguments.group(1)):
            host = normalize_host(backtick or quoted)
            if host is not None:
                hosts.setdefault(host, None)
    return tuple(hosts)


class _UnparsableRuleError(ValueError):
    """The rule does not follow the matcher grammar."""


def _tokenize(rule: str) -> list[tuple[str, str]]:
    """Return the ``(kind, text)`` tokens of ``rule``; raise when a character fits no token."""
    tokens: list[tuple[str, str]] = []
    position = 0
    while position < len(rule):
        token = _TOKEN.match(rule, position)
        if token is None or token.lastgroup is None:
            raise _UnparsableRuleError
        tokens.append((token.lastgroup, token.group()))
        position = token.end()
    return tokens


def _redacted_literal(literal: str) -> str:
    """Return ``literal`` with its content replaced by the marker, keeping its quote character."""
    return f"{literal[0]}{_REDACTED}{literal[0]}"


def _redacted_query_pair(literal: str) -> str:
    """Return a v2 ``key=value`` literal as ``key=`` plus the marker; a literal without ``=`` as the marker."""
    key, separator, _ = literal[1:-1].partition("=")
    if not separator:
        return _redacted_literal(literal)
    return f"{literal[0]}{key}={_REDACTED}{literal[0]}"


def _redacted_arguments(matcher: str, arguments: list[str]) -> list[str]:
    """Return the argument literals of one matcher call with secret-bearing values redacted."""
    if matcher in _SAFE_MATCHERS:
        return arguments
    if matcher in _HEADER_MATCHERS:
        return [arguments[0], *(_redacted_literal(argument) for argument in arguments[1:])]
    if matcher in _QUERY_MATCHERS:
        if "=" in arguments[0]:
            return [_redacted_query_pair(argument) for argument in arguments]
        return [arguments[0], *(_redacted_literal(argument) for argument in arguments[1:])]
    raise _UnparsableRuleError


def _hidden_value(literal: str, redacted: str) -> str | None:
    """Return the part of ``literal`` that ``redacted`` hides, or None when it hides nothing."""
    if literal == redacted:
        return None
    content = literal[1:-1]
    key, separator, value = content.partition("=")
    if separator and redacted == f"{literal[0]}{key}={_REDACTED}{literal[0]}":
        return value
    return content


def _redact_tokens(tokens: list[tuple[str, str]]) -> tuple[str, frozenset[str]]:
    """Rebuild a rule from its tokens with matcher values redacted; raise on a grammar violation.

    Returns the redacted rule and the unquoted values it hides. Outside a
    matcher call only ``&&``, ``||``, ``!`` and parentheses may occur. A
    matcher call is a name, ``(``, one or more literals separated by ``,``,
    and ``)``. Whitespace may stand between any two tokens and is kept.
    """
    hidden: set[str] = set()
    parts = [text for _, text in tokens]
    significant = [index for index, (kind, _) in enumerate(tokens) if kind != "space"]
    position = 0

    def take() -> tuple[int, str, str]:
        nonlocal position
        if position >= len(significant):
            raise _UnparsableRuleError
        index = significant[position]
        position += 1
        return index, *tokens[index]

    while position < len(significant):
        _, kind, text = take()
        if kind == "operator" and text != ",":
            continue
        if kind != "name" or take()[1:] != ("operator", "("):
            raise _UnparsableRuleError
        slots: list[int] = []
        separator = ","
        while separator == ",":
            index, kind, _ = take()
            if kind != "literal":
                raise _UnparsableRuleError
            slots.append(index)
            _, kind, separator = take()
            if kind != "operator" or separator not in {",", ")"}:
                raise _UnparsableRuleError
        redacted = _redacted_arguments(text.lower(), [parts[slot] for slot in slots])
        for slot, argument in zip(slots, redacted, strict=True):
            value = _hidden_value(parts[slot], argument)
            if value:
                hidden.add(value)
            parts[slot] = argument
    return "".join(parts), frozenset(hidden)


def has_matcher_call(text: str) -> bool:
    """Return True when ``text`` contains a call of a known matcher, in any letter case."""
    return any(call.group(1).lower() in _MATCHERS for call in _CALL.finditer(text))


def redact_rule(rule: str) -> str:
    """Return ``rule`` with the values of header and query matchers replaced by ``**REDACTED**``.

    Matcher names, header names and query keys stay readable; ``Host``,
    ``Path``, ``Method``, ``ClientIP`` and the other safe matchers stay
    verbatim, as do whitespace and operators. For a v2 ``Query(`key=value`)``
    every argument keeps its key and loses its value. A rule that does not
    tokenize, uses an unknown matcher or holds a literal outside a matcher
    call is replaced by the marker as a whole. An empty or whitespace-only
    rule is returned unchanged. Never raises.
    """
    if not rule.strip():
        return rule
    try:
        return _redact_tokens(_tokenize(rule))[0]
    except _UnparsableRuleError:
        return _REDACTED


def rule_secret_values(rule: str) -> frozenset[str] | None:
    """Return the unquoted values that :func:`redact_rule` hides, or None when the rule is unparsable.

    For a v2 ``Query(`key=value`)`` the value without its key is returned.
    An empty or whitespace-only rule hides nothing. A rule that
    :func:`redact_rule` redacts as a whole gives None: its secrets are
    unknown. Empty values are left out. Never raises.
    """
    if not rule.strip():
        return frozenset()
    try:
        return _redact_tokens(_tokenize(rule))[1]
    except _UnparsableRuleError:
        return None


__all__ = ["extract_hosts", "has_matcher_call", "normalize_host", "redact_rule", "rule_secret_values"]
