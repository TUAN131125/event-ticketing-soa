from __future__ import annotations

import ast
from pathlib import Path

GATEWAY = Path(__file__).resolve().parents[3] / "gateway" / "booking-orchestrator"


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_domain_has_no_framework_or_adapter_dependencies() -> None:
    forbidden = (
        "fastapi",
        "httpx",
        "sqlalchemy",
        "alembic",
        "lxml",
        "app.adapters",
        "app.persistence",
    )
    for path in (GATEWAY / "app" / "domain").glob("*.py"):
        assert not [name for name in imports(path) if name.startswith(forbidden)], path


def test_application_depends_only_on_domain_and_ports() -> None:
    forbidden = (
        "fastapi",
        "httpx",
        "sqlalchemy",
        "alembic",
        "lxml",
        "app.adapters",
        "app.persistence",
    )
    for path in (GATEWAY / "app" / "application").glob("*.py"):
        assert not [name for name in imports(path) if name.startswith(forbidden)], path


def test_runtime_contains_no_placeholder_or_todo() -> None:
    for path in (GATEWAY / "app").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "Placeholder:" not in source
        assert "TODO" not in source
