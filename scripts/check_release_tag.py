#!/usr/bin/env python3
"""Release check: the pushed tag must equal the manifest version (skeleton)."""

from __future__ import annotations

import sys


def check(tag: str, version: str) -> str | None:
    """Return an error message when the tag does not match, else None."""
    return None


def main(argv: list[str]) -> int:
    """Compare argv[0] with manifest.json and return the exit code."""
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
