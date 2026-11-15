"""Regression guards for the Home Assistant 2026.11.0 baseline (FLOW-08).

Phase 7 raised the minimum Home Assistant to 2026.11.0 and removed everything
that existed only for older releases. These filesystem/AST checks mirror the
acceptance greps of plans 07-01, 07-02 and 07-03, so a regression fails the
suite instead of waiting for a manual grep:

* 07-01: no import shim or test helper for releases before the minimum.
* 07-02: shipped code reads no attribute private to an HA base class.
* 07-03: no code path or comment for releases before the minimum.

They need no Home Assistant fixture and read no planning docs (PR branches are
cut without .planning/). This file is excluded from the text scans.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "custom_components" / "traefik_proxy"
THIS_FILE = Path(__file__).resolve()

# Import fallbacks a shim would catch.
IMPORT_ERRORS = frozenset({"ImportError", "ModuleNotFoundError"})
# Modules replaced by probatio / the one-statement binary_sensor import (07-01 D-01).
FORBIDDEN_MODULES = frozenset({"voluptuous", "voluptuous_serialize", "homeassistant.components.binary_sensor.const"})
# Names that only serve a version gate against the running Home Assistant (07-01: no version arithmetic).
VERSION_GATE_NAMES = frozenset({"MAJOR_VERSION", "MINOR_VERSION", "PATCH_VERSION", "__short_version__", "__version__"})
# The discontinued test package that only supported releases before 2026.11 (07-01 acceptance grep).
OLD_TEST_PACKAGE = re.compile(rb"pytest_homeassistant_custom_component|pytest-homeassistant-custom-component")
# Private DataUpdateCoordinator attributes (07-02 acceptance grep, T-07-01).
PRIVATE_BASE_ATTRS = frozenset(
    {
        "_shutdown_requested",
        "_listeners",
        "_unsub_refresh",
        "_unsub_shutdown",
        "_update_interval",
        "_debounced_refresh",
        "_request_refresh_task",
        "_retry_after",
        "_last_listener_id",
        "_microsecond",
    }
)
# Old minimum release (07-01/07-02/07-03 acceptance greps).
OLD_RELEASE = re.compile(rb"2026\.3")
OLDER_HA_WORDING = re.compile(rb"older home assistant", re.IGNORECASE)


def _files(*dirs: Path) -> Iterator[Path]:
    """Yield every file below ``dirs`` (like ``grep -r``), minus caches and this guard."""
    for base in dirs:
        for path in sorted(base.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.resolve() != THIS_FILE:
                yield path


def _python_files(*dirs: Path) -> Iterator[Path]:
    return (path for path in _files(*dirs) if path.suffix == ".py")


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _where(path: Path, node: ast.AST) -> str:
    return f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', '?')}"


def _grep(pattern: re.Pattern[bytes], *paths: Path) -> list[str]:
    hits: list[str] = []
    for path in paths:
        for lineno, line in enumerate(path.read_bytes().splitlines(), start=1):
            if pattern.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{lineno}")
    return hits


def _caught_names(handler: ast.ExceptHandler) -> set[str]:
    """Exception class names an ``except`` clause catches (bare ``except`` catches everything)."""
    if handler.type is None:
        return set(IMPORT_ERRORS)
    exprs = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    names: set[str] = set()
    for expr in exprs:
        if isinstance(expr, ast.Name):
            names.add(expr.id)
        elif isinstance(expr, ast.Attribute):
            names.add(expr.attr)
    return names


def test_no_import_shim_in_integration_or_tests() -> None:
    """07-01: no ``try: import ... except ImportError`` fallback in shipped code or tests."""
    offenders: list[str] = []
    for path in _python_files(PACKAGE, ROOT / "tests"):
        for node in ast.walk(_parse(path)):
            if not isinstance(node, ast.Try | ast.TryStar):
                continue
            imports = any(
                isinstance(inner, ast.Import | ast.ImportFrom) for stmt in node.body for inner in ast.walk(stmt)
            )
            if imports and any(_caught_names(handler) & IMPORT_ERRORS for handler in node.handlers):
                offenders.append(_where(path, node))
    assert not offenders, f"import fallback for an older Home Assistant: {offenders}"


def test_no_import_of_pre_baseline_modules() -> None:
    """07-01: probatio replaces voluptuous; BinarySensorDeviceClass comes from the platform module."""
    offenders: list[str] = []
    for path in _python_files(PACKAGE, ROOT / "tests"):
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                modules = [node.module]
            else:
                continue
            for module in modules:
                if any(module == name or module.startswith(f"{name}.") for name in FORBIDDEN_MODULES):
                    offenders.append(f"{_where(path, node)} imports {module}")
    assert not offenders, f"import that only older Home Assistant releases needed: {offenders}"


def test_no_home_assistant_version_gate() -> None:
    """07-01: the integration does no version arithmetic against the running Home Assistant."""
    offenders: list[str] = []
    for path in _python_files(PACKAGE):
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.ImportFrom) and node.module == "homeassistant.const":
                offenders.extend(
                    f"{_where(path, node)} imports {alias.name}"
                    for alias in node.names
                    if alias.name in VERSION_GATE_NAMES
                )
            elif isinstance(node, ast.Import | ast.ImportFrom):
                modules = [node.module or ""] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
                if any(module.split(".")[0] == "awesomeversion" for module in modules):
                    offenders.append(f"{_where(path, node)} imports awesomeversion")
    assert not offenders, f"Home Assistant version gate in shipped code: {offenders}"


def test_no_old_test_package_or_helper() -> None:
    """07-01: tests and pyproject.toml use pytest-homeassistant only, without the old package's helpers."""
    hits = _grep(OLD_TEST_PACKAGE, *_files(ROOT / "tests"), ROOT / "pyproject.toml")
    assert not hits, f"reference to the discontinued pre-2026.11 test package: {hits}"

    # The old package needed an autouse fixture to enable custom integrations; pytest-homeassistant's
    # hass fixture does that itself.
    helpers = [
        _where(path, node)
        for path in _python_files(ROOT / "tests")
        for node in ast.walk(_parse(path))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == "enable_custom_integrations"
    ]
    assert not helpers, f"test helper that only the pre-2026.11 test package needed: {helpers}"


def test_shipped_code_reads_no_private_base_class_attribute() -> None:
    """07-02: no private DataUpdateCoordinator attribute is read, by attribute or by name string."""
    offenders: list[str] = []
    for path in _python_files(PACKAGE):
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.Attribute) and node.attr in PRIVATE_BASE_ATTRS:
                offenders.append(f"{_where(path, node)} .{node.attr}")
            elif isinstance(node, ast.Constant) and node.value in PRIVATE_BASE_ATTRS:
                # getattr(coordinator, "_shutdown_requested") and friends.
                offenders.append(f"{_where(path, node)} {node.value!r}")
    assert not offenders, f"private Home Assistant base-class attribute in shipped code: {offenders}"


def test_no_text_for_releases_before_the_minimum() -> None:
    """07-01/07-02/07-03: no code path or comment names the old 2026.3 minimum or "older" releases."""
    hits = _grep(OLD_RELEASE, *_files(PACKAGE.parent, ROOT / "tests", ROOT / "scripts"))
    assert not hits, f"reference to Home Assistant 2026.3: {hits}"
    hits = _grep(OLDER_HA_WORDING, *_files(PACKAGE.parent))
    assert not hits, f"code justified by older Home Assistant releases: {hits}"
