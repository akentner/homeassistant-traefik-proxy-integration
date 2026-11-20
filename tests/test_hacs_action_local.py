"""Unit tests for scripts/hacs_action_local.py (the local hacs/action overlay).

The overlay only runs inside the hacs/action image, so the HACS and
aiogithubapi modules it imports are replaced by minimal stubs here. The tests
pin the overlay's own guarantees: it refuses to run as a no-op when a patch
target is missing or overridden, it serves files only from the local tree and
only those in the files list (an unknown manifest category in the local tree
is what the validators see, not GitHub's copy), and it hands control to
``/hacs/action.py`` only after patching. No token, network or image is needed.
"""

from __future__ import annotations

import json
import logging
import runpy
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "hacs_action_local.py"
REPOSITORY = "owner/repo"
RAW = f"https://raw.githubusercontent.com/{REPOSITORY}"
MANIFEST_PATH = "custom_components/traefik_proxy/manifest.json"
BOGUS_CATEGORY = "computers_network.bogus"


class HacsError(Exception):
    """Stand-in for ``custom_components.hacs.exceptions.HacsException``."""


class TreeEntry:
    """Stand-in for ``GitHubGitTreeEntryModel``."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.path = data["path"]
        self.type = data["type"]
        self.size = data.get("size")


def _stub_classes(*, drop: str | None = None, override: str | None = None) -> dict[str, type]:
    """Return fresh HACS stand-in classes, optionally without or overriding one patch target."""

    async def get_tree(self: Any, ref: str) -> list[Any]:
        return ["github-tree"]

    async def async_get_hacs_json(self: Any, ref: str | None = None) -> dict[str, Any]:
        return {"source": "github"}

    async def async_get_integration_manifest(self: Any, ref: str | None = None) -> dict[str, Any]:
        return {"source": "github"}

    async def async_download_file(self: Any, url: str, **kwargs: Any) -> bytes | None:
        return b"remote:" + url.encode()

    repository_methods: dict[str, Callable[..., Any]] = {
        "get_tree": get_tree,
        "async_get_hacs_json": async_get_hacs_json,
    }
    integration_methods: dict[str, Callable[..., Any]] = {
        "async_get_integration_manifest": async_get_integration_manifest
    }
    base_methods: dict[str, Callable[..., Any]] = {"async_download_file": async_download_file}
    for methods in (repository_methods, integration_methods, base_methods):
        methods.pop(drop or "", None)
    if override is not None:
        # A subclass definition shadows the patch on HacsRepository.
        integration_methods[override] = get_tree
    hacs_base = type("HacsBase", (), base_methods)
    hacs_repository = type("HacsRepository", (), repository_methods)
    hacs_integration = type("HacsIntegrationRepository", (hacs_repository,), integration_methods)
    return {"HacsBase": hacs_base, "HacsRepository": hacs_repository, "HacsIntegrationRepository": hacs_integration}


def _module(name: str, **attributes: Any) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _install_stubs(monkeypatch: pytest.MonkeyPatch, classes: dict[str, type]) -> None:
    modules = {
        "aiogithubapi": _module("aiogithubapi"),
        "aiogithubapi.models": _module("aiogithubapi.models"),
        "aiogithubapi.models.git_tree": _module("aiogithubapi.models.git_tree", GitHubGitTreeEntryModel=TreeEntry),
        "custom_components.hacs": _module("custom_components.hacs"),
        "custom_components.hacs.base": _module("custom_components.hacs.base", HacsBase=classes["HacsBase"]),
        "custom_components.hacs.exceptions": _module("custom_components.hacs.exceptions", HacsException=HacsError),
        "custom_components.hacs.repositories": _module("custom_components.hacs.repositories"),
        "custom_components.hacs.repositories.base": _module(
            "custom_components.hacs.repositories.base", HacsRepository=classes["HacsRepository"]
        ),
        "custom_components.hacs.repositories.integration": _module(
            "custom_components.hacs.repositories.integration",
            HacsIntegrationRepository=classes["HacsIntegrationRepository"],
        ),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


@pytest.fixture
def local_tree(tmp_path: Path) -> Path:
    """A local tree with an unknown manifest category and one file outside the files list."""
    root = tmp_path / "repo"
    manifest = root / MANIFEST_PATH
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"domain": "traefik_proxy", "categories": [BOGUS_CATEGORY]}), encoding="utf-8")
    (root / "hacs.json").write_text(json.dumps({"name": "Traefik Proxy"}), encoding="utf-8")
    (root / "README.md").write_bytes(b"# local readme\n")
    (root / ".env").write_bytes(b"ignored, not in files.txt\n")
    files = tmp_path / "files.txt"
    files.write_text(f"hacs.json\nREADME.md\n{MANIFEST_PATH}\nlisted-but-missing.txt\n\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def run_overlay(
    monkeypatch: pytest.MonkeyPatch, local_tree: Path
) -> Callable[..., tuple[dict[str, Any], dict[str, type], list[str]]]:
    """Run the overlay script against stubs; return its globals, the stub classes and the started actions."""

    def run(**stub_options: str) -> tuple[dict[str, Any], dict[str, type], list[str]]:
        classes = _stub_classes(**stub_options)
        _install_stubs(monkeypatch, classes)
        monkeypatch.setenv("LOCAL_ROOT", str(local_tree / "repo"))
        monkeypatch.setenv("LOCAL_FILES", str(local_tree / "files.txt"))
        monkeypatch.setenv("REPOSITORY", REPOSITORY)
        monkeypatch.setattr(sys, "path", list(sys.path))
        started: list[str] = []
        real_run_path = runpy.run_path

        def fake_run_path(path: str, run_name: str | None = None) -> dict[str, Any]:
            started.append(path)
            return {}

        monkeypatch.setattr(runpy, "run_path", fake_run_path)
        namespace = real_run_path(str(SCRIPT), run_name="hacs_action_local")
        return namespace, classes, started

    return run


def _repository() -> SimpleNamespace:
    return SimpleNamespace(
        logger=logging.getLogger("test_hacs_action_local"),
        content=SimpleNamespace(path=SimpleNamespace(remote="custom_components/traefik_proxy")),
    )


async def test_overlay_validates_the_local_tree_not_github(
    run_overlay: Callable[..., tuple[dict[str, Any], dict[str, type], list[str]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Negative control at overlay level: the bogus local category, not GitHub's manifest, reaches the validators."""
    _, classes, started = run_overlay()
    repository = _repository()

    manifest = await classes["HacsIntegrationRepository"].async_get_integration_manifest(repository)  # type: ignore[attr-defined]
    assert manifest["categories"] == [BOGUS_CATEGORY]
    hacs_json = await classes["HacsIntegrationRepository"].async_get_hacs_json(repository)  # type: ignore[attr-defined]
    assert hacs_json == {"name": "Traefik Proxy"}

    tree = await classes["HacsIntegrationRepository"].get_tree(repository, "local-tree")  # type: ignore[attr-defined]
    blobs = {entry.path for entry in tree if entry.type == "blob"}
    dirs = {entry.path for entry in tree if entry.type == "tree"}
    assert blobs == {"hacs.json", "README.md", MANIFEST_PATH}
    assert dirs == {"custom_components", "custom_components/traefik_proxy"}

    assert started == ["/hacs/action.py"]
    assert "LOCAL OVERLAY: patched 4 methods; 3 files from" in capsys.readouterr().out


async def test_overlay_downloads_only_listed_local_files(
    run_overlay: Callable[..., tuple[dict[str, Any], dict[str, type], list[str]]],
) -> None:
    """Raw URLs are answered from the local tree; files outside the list are absent; other URLs pass through."""
    _, classes, _ = run_overlay()
    download = classes["HacsBase"].async_download_file  # type: ignore[attr-defined]
    hacs = object()

    assert await download(hacs, f"{RAW}/main/README.md") == b"# local readme\n"
    assert await download(hacs, f"{RAW}/refs/tags/v1.0.0/README.md") == b"# local readme\n"
    assert await download(hacs, f"{RAW}/main/custom_components/traefik_proxy/manifest.json") is not None
    assert await download(hacs, f"{RAW}/main/.env") is None
    assert await download(hacs, f"{RAW}/main/../../etc/passwd") is None
    other = "https://api.github.com/repos/owner/repo"
    assert await download(hacs, other) == b"remote:" + other.encode()


@pytest.mark.parametrize(
    "target",
    ["get_tree", "async_get_hacs_json", "async_get_integration_manifest", "async_download_file"],
)
def test_overlay_refuses_to_run_when_a_target_is_missing(
    run_overlay: Callable[..., tuple[dict[str, Any], dict[str, type], list[str]]],
    capsys: pytest.CaptureFixture[str],
    target: str,
) -> None:
    """An image without one patch target stops with exit 1 before the action starts."""
    with pytest.raises(SystemExit) as raised:
        run_overlay(drop=target)
    assert raised.value.code == 1
    err = capsys.readouterr().err
    assert f".{target} is missing in this image; refusing to run as a no-op" in err


@pytest.mark.parametrize("target", ["get_tree", "async_get_hacs_json"])
def test_overlay_refuses_to_run_when_a_subclass_shadows_a_patch(
    run_overlay: Callable[..., tuple[dict[str, Any], dict[str, type], list[str]]],
    capsys: pytest.CaptureFixture[str],
    target: str,
) -> None:
    """A subclass override of a repository-level target would bypass the patch: exit 1."""
    with pytest.raises(SystemExit) as raised:
        run_overlay(override=target)
    assert raised.value.code == 1
    assert f"HacsIntegrationRepository.{target} does not resolve to the overlay" in capsys.readouterr().err


def test_overlay_refuses_an_empty_file_list(
    run_overlay: Callable[..., tuple[dict[str, Any], dict[str, type], list[str]]],
    local_tree: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A files list that matches nothing in the tree stops with exit 1."""
    (local_tree / "files.txt").write_text("missing.txt\n", encoding="utf-8")
    with pytest.raises(SystemExit) as raised:
        run_overlay()
    assert raised.value.code == 1
    assert "LOCAL OVERLAY ERROR: no files from" in capsys.readouterr().err


async def test_overlay_does_not_serve_unlisted_hacs_json_or_manifest(
    run_overlay: Callable[..., tuple[dict[str, Any], dict[str, type], list[str]]],
    local_tree: Path,
) -> None:
    """hacs.json and manifest.json that exist on disk but are not in the list raise like a missing file."""
    (local_tree / "files.txt").write_text("README.md\n", encoding="utf-8")
    _, classes, _ = run_overlay()
    repository = _repository()
    with pytest.raises(HacsError, match=r"No hacs\.json"):
        await classes["HacsIntegrationRepository"].async_get_hacs_json(repository)  # type: ignore[attr-defined]
    with pytest.raises(HacsError, match=r"No manifest\.json"):
        await classes["HacsIntegrationRepository"].async_get_integration_manifest(repository)  # type: ignore[attr-defined]
