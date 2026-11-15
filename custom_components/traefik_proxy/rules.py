"""Host names from Traefik router rules, normalized for TLS probing.

Pure module: no Home Assistant imports; besides the stdlib only ``idna``
(bundled with Home Assistant through ``yarl``). Router rules come from
the Traefik API and are treated as untrusted text: only literal ``Host()``
arguments are returned, never regex, SNI, header, template or wildcard
patterns, and every name goes through :func:`normalize_host`.

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


__all__ = ["extract_hosts", "normalize_host"]
