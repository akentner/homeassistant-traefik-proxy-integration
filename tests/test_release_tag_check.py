"""Unit tests for scripts/check_release_tag.py (release tag == manifest version)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_release_tag.py"
MANIFEST = ROOT / "custom_components" / "traefik_proxy" / "manifest.json"


def _load_script() -> ModuleType:
    """Load the release check script by path; it has no import side effects."""
    spec = importlib.util.spec_from_file_location("check_release_tag", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script() -> ModuleType:
    """The release check script as a module."""
    return _load_script()


@pytest.fixture(scope="module")
def manifest_version() -> str:
    """The version currently in manifest.json (survives version bumps)."""
    version = json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]
    assert isinstance(version, str)
    return version


def test_tag_with_one_leading_v_matches(script: ModuleType, manifest_version: str) -> None:
    """`v<version>` is the project's tag scheme and passes."""
    assert script.check(f"v{manifest_version}", manifest_version) is None


def test_tag_without_v_matches(script: ModuleType, manifest_version: str) -> None:
    """A bare version tag also passes."""
    assert script.check(manifest_version, manifest_version) is None


@pytest.mark.parametrize("tag_template", ["vv{v}", "v9.9.9", ""])
def test_mismatching_tag_reports_tag_and_version(script: ModuleType, manifest_version: str, tag_template: str) -> None:
    """Only one leading `v` is stripped; any other difference is an error."""
    tag = tag_template.format(v=manifest_version)
    error = script.check(tag, manifest_version)
    assert error is not None
    assert f"tag {tag} " in error
    assert manifest_version in error


def test_main_fails_with_error_annotation_on_mismatch(script: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    """A mismatching tag exits 1 with a GitHub `::error::` annotation."""
    assert script.main(["v9.9.9"]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert any(line.startswith("::error::") for line in lines)


def test_main_passes_for_current_manifest_version(
    script: ModuleType, manifest_version: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """The tag `v<current manifest version>` exits 0 without an error line."""
    assert script.main([f"v{manifest_version}"]) == 0
    assert "::error::" not in capsys.readouterr().out


def test_main_without_tag_argument_fails(script: ModuleType) -> None:
    """Calling the script without a tag is a usage error, not a pass."""
    assert script.main([]) == 2
