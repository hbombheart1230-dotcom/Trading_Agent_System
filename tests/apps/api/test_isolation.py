from __future__ import annotations

import ast
from pathlib import Path

from fastapi.routing import APIRoute

from apps.api.main import create_app

API_ROOT = Path(__file__).resolve().parents[3] / "apps" / "api"
FORBIDDEN_IMPORT_PREFIXES = (
    "apps.operator_ui",
    "graphs",
    "libs",
    "scripts",
)
FORBIDDEN_SIDE_EFFECT_MODULES = (
    "httpx",
    "requests",
    "subprocess",
    "urllib.request",
    "websocket",
)
FORBIDDEN_WRITE_METHODS = {
    "mkdir",
    "rename",
    "replace",
    "rmdir",
    "touch",
    "unlink",
    "write_bytes",
    "write_text",
}


def _import_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_api_has_no_core_or_side_effect_imports() -> None:
    violations: list[str] = []
    for path in API_ROOT.rglob("*.py"):
        for imported in _import_names(path):
            forbidden = FORBIDDEN_IMPORT_PREFIXES + FORBIDDEN_SIDE_EFFECT_MODULES
            if imported.startswith(forbidden):
                violations.append(f"{path.relative_to(API_ROOT)}: {imported}")

    assert violations == []


def test_api_source_has_no_filesystem_write_calls() -> None:
    violations: list[str] = []
    for path in API_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr in FORBIDDEN_WRITE_METHODS:
                violations.append(
                    f"{path.relative_to(API_ROOT)}:{node.lineno}:{node.func.attr}"
                )

    assert violations == []


def test_api_routes_are_get_only(api_settings) -> None:
    app = create_app(api_settings)
    routes = [route for route in app.routes if isinstance(route, APIRoute)]

    assert routes
    assert all(route.methods == {"GET"} for route in routes)
