#!/usr/bin/env python3
"""Release check: the pushed tag must equal the manifest version.

Run by `.github/workflows/release.yml` (tag passed via `env:` and argv only,
never interpolated into the shell) or locally:

    python3 scripts/check_release_tag.py v1.0.0

Tags follow the `v<version>` scheme. Exactly one leading `v` is stripped;
the rest must equal `version` in `custom_components/traefik_proxy/manifest.json`.

Exit code 0 = tag matches, 1 = mismatch (with a `::error::` annotation),
2 = usage error.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "custom_components" / "traefik_proxy" / "manifest.json"


def check(tag: str, version: str) -> str | None:
    """Return an error message when the tag does not match, else None."""
    tag_version = tag.removeprefix("v")
    if tag_version == version:
        return None
    return f"tag {tag} (version {tag_version}) != manifest.json version {version}"


def main(argv: list[str]) -> int:
    """Compare argv[0] with manifest.json and return the exit code."""
    if len(argv) != 1:
        print("usage: check_release_tag.py <tag>", file=sys.stderr)
        return 2
    tag = argv[0]
    version = json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]
    error = check(tag, version)
    if error is not None:
        print(f"::error::{error}")
        return 1
    print(f"tag {tag} matches manifest.json version {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
