"""Run the official hacs/action validators against the LOCAL working tree.

Runs only inside the digest-pinned ``ghcr.io/hacs/action`` image (``HACS_IMG``
in the Makefile, ``make hacs-action``); it imports HACS from ``/hacs`` and is
never run on the host.

The stock action never reads the checkout: it takes the file tree from the
GitHub API and file contents from raw.githubusercontent.com at a ref. This
overlay patches four HACS methods so that the tree and the file contents
(``hacs.json``, ``manifest.json``, ``brand/``, README, ...) come from ``/repo``
instead, restricted to the paths in ``/harness/files.txt`` (host:
``git ls-files -co --exclude-standard``), so an ignored file cannot satisfy a
check. Everything else is the unmodified ``/hacs/action.py``.

Repository metadata (description, topics, issues, license, archived) still
comes from the live GitHub API for ``REPOSITORY``; the token is read by the
action from ``INPUT_GITHUB_TOKEN`` (set from ``HACS_ACTION_TOKEN``, a
fine-grained read-only token for public repositories) and is never printed here.

If the image no longer defines one of the patched methods, assigning it would
silently create a new attribute and the run would validate GitHub's default
branch instead of the local tree. The overlay therefore checks every target
before and after patching and exits 1 if one is missing.
"""

from __future__ import annotations

import json
import os
import runpy
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, "/hacs")

from aiogithubapi.models.git_tree import GitHubGitTreeEntryModel
from custom_components.hacs.base import HacsBase
from custom_components.hacs.exceptions import HacsException
from custom_components.hacs.repositories.base import HacsRepository
from custom_components.hacs.repositories.integration import (
    HacsIntegrationRepository,
)

ROOT = Path(os.environ.get("LOCAL_ROOT", "/repo"))
FILES_LIST = Path(os.environ.get("LOCAL_FILES", "/harness/files.txt"))
REPO = os.environ["REPOSITORY"]
RAW_PREFIX = f"https://raw.githubusercontent.com/{REPO}/"

# (class that must define it, attribute name)
TARGETS: list[tuple[type, str]] = [
    (HacsRepository, "get_tree"),
    (HacsRepository, "async_get_hacs_json"),
    (HacsIntegrationRepository, "async_get_integration_manifest"),
    (HacsBase, "async_download_file"),
]


def _fail(message: str) -> None:
    print(f"LOCAL OVERLAY ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def _load_files() -> list[str]:
    files = [
        line.strip()
        for line in FILES_LIST.read_text(encoding="utf-8").splitlines()
        if line.strip() and (ROOT / line.strip()).is_file()
    ]
    if not files:
        _fail(f"no files from {FILES_LIST} exist under {ROOT}")
    return files


FILES = _load_files()
FILE_SET = set(FILES)


def _tree() -> list[GitHubGitTreeEntryModel]:
    dirs: set[str] = set()
    for path in FILES:
        parts = path.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add("/".join(parts[:i]))
    entries: list[dict[str, Any]] = [{"path": d, "type": "tree", "mode": "040000"} for d in sorted(dirs)]
    entries += [{"path": f, "type": "blob", "mode": "100644", "size": (ROOT / f).stat().st_size} for f in FILES]
    return [GitHubGitTreeEntryModel(e) for e in entries]


async def _get_tree(self: HacsRepository, ref: str) -> list[GitHubGitTreeEntryModel]:
    self.logger.info("LOCAL OVERLAY: tree from %s (%s files)", ROOT, len(FILES))
    return _tree()


async def _get_hacs_json(self: HacsRepository, ref: str | None = None) -> dict[str, Any]:
    if "hacs.json" not in FILE_SET:
        raise HacsException("No hacs.json file found in the local tree")
    data: dict[str, Any] = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
    return data


async def _get_integration_manifest(self: HacsIntegrationRepository, ref: str | None = None) -> dict[str, Any]:
    path = f"{self.content.path.remote}/manifest.json"
    if path not in FILE_SET:
        raise HacsException(f"No manifest.json file found '{path}'")
    data: dict[str, Any] = json.loads((ROOT / path).read_text(encoding="utf-8"))
    return data


# Set by _apply() after the existence check, so a missing method reaches the
# guard instead of failing here with an AttributeError.
_orig_download: Any = None


async def _download(self: HacsBase, url: str, **kwargs: Any) -> bytes | None:
    if url and url.startswith(RAW_PREFIX):
        rel = url[len(RAW_PREFIX) :].split("/", 1)[1]  # drop the ref segment
        if rel.startswith("tags/"):
            rel = rel.split("/", 2)[2]
        if rel in FILE_SET:
            return (ROOT / rel).read_bytes()
        return None
    result: bytes | None = await _orig_download(self, url, **kwargs)
    return result


PATCHES = {
    "get_tree": _get_tree,
    "async_get_hacs_json": _get_hacs_json,
    "async_get_integration_manifest": _get_integration_manifest,
    "async_download_file": _download,
}


def _apply() -> None:
    global _orig_download
    for cls, name in TARGETS:
        if not hasattr(cls, name):
            _fail(f"{cls.__name__}.{name} is missing in this image; refusing to run as a no-op")
    _orig_download = HacsBase.async_download_file
    for cls, name in TARGETS:
        setattr(cls, name, PATCHES[name])
    # The integration repository class must resolve every repository-level
    # target to the patch (a subclass override would bypass it).
    for cls, name in TARGETS:
        owner = HacsBase if cls is HacsBase else HacsIntegrationRepository
        if getattr(owner, name) is not PATCHES[name]:
            _fail(f"{owner.__name__}.{name} does not resolve to the overlay")


_apply()
print(f"LOCAL OVERLAY: patched {len(TARGETS)} methods; {len(FILES)} files from {ROOT}", flush=True)
runpy.run_path("/hacs/action.py", run_name="__main__")
