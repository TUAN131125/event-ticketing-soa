"""Shared offline helpers for the canonical contract catalog."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ImportError as exc:  # pragma: no cover - environment diagnostic
    raise SystemExit("PyYAML is required for offline contract validation") from exc

CONTRACTS = Path(__file__).resolve().parents[1]
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


class ContractError(ValueError):
    """A validation error with stable file/rule context."""

    def __init__(self, file: Path | str, rule: str, message: str) -> None:
        self.file = str(file)
        self.rule = rule
        self.message = message
        super().__init__(f"{self.file}: [{self.rule}] {self.message}")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(path, "parse.json", str(exc)) from exc


def read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ContractError(path, "parse.yaml", str(exc)) from exc


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def operations(document: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    result: list[tuple[str, str, dict[str, Any]]] = []
    for path, item in document.get("paths", {}).items():
        if not isinstance(item, dict):
            continue
        for method, operation in item.items():
            if method in HTTP_METHODS and isinstance(operation, dict):
                result.append((method.upper(), path, operation))
    return result


def canonical_artifacts() -> set[str]:
    patterns = (
        "common/*.schema.json",
        "common/*.yaml",
        "openapi/*.yaml",
        "soap/*.wsdl",
        "soap/*.xsd",
        "events/**/*.schema.json",
        "webhooks/**/*.schema.json",
        "websocket/**/*.schema.json",
        "websocket/**/close-codes.yaml",
        "websocket/**/protocol.md",
    )
    return {
        path.relative_to(CONTRACTS).as_posix()
        for pattern in patterns
        for path in CONTRACTS.glob(pattern)
        if path.is_file()
    }


def json_pointer(document: Any, fragment: str) -> Any:
    if not fragment or fragment == "#":
        return document
    pointer = fragment[1:] if fragment.startswith("#") else fragment
    if not pointer.startswith("/"):
        raise KeyError(f"unsupported JSON pointer: {fragment}")
    current = document
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def resolve_ref(ref: str, document: Any, source: Path) -> tuple[Any, Any, Path]:
    if ref.startswith("#"):
        return json_pointer(document, ref), document, source
    if source.name.endswith(".schema.json"):
        raise ContractError(
            source,
            "ref.registry-required",
            "non-fragment JSON Schema references must resolve by canonical $id through the Draft 2020-12 registry",
        )
    path_part, separator, fragment = ref.partition("#")
    target = (source.parent / path_part).resolve()
    if not target.is_relative_to(CONTRACTS.resolve()):
        raise ContractError(source, "ref.scope", f"reference escapes contracts/: {ref}")
    if not target.exists():
        raise ContractError(source, "ref.missing", f"missing reference target: {ref}")
    target_document = read_json(target) if target.suffix == ".json" else read_yaml(target)
    target_schema = json_pointer(target_document, f"#{fragment}" if separator else "#")
    return target_schema, target_document, target


def walk_refs(node: Any) -> Iterable[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value
            else:
                yield from walk_refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk_refs(value)


def find_placeholders() -> list[ContractError]:
    errors: list[ContractError] = []
    for path in sorted(CONTRACTS.rglob("*")):
        if path.is_dir() and path.name == "__pycache__":
            errors.append(ContractError(path, "catalog.cache", "Python cache directory is forbidden under contracts/"))
        elif path.is_file() and path.suffix.lower() in {".pyc", ".pyo"}:
            errors.append(ContractError(path, "catalog.cache", "compiled Python artifact is forbidden under contracts/"))
    marker = re.compile(r"(?i)(\bplaceholder\b|\bTODO\b|_placeholder|chưa có lệnh triển khai)")
    for relative in sorted(canonical_artifacts()):
        path = CONTRACTS / relative
        text = path.read_text(encoding="utf-8", errors="replace")
        if marker.search(text):
            errors.append(ContractError(relative, "placeholder.marker", "placeholder marker remains"))
        if path.stat().st_size < 40:
            errors.append(ContractError(relative, "placeholder.size", "artifact is suspiciously small"))
    return errors
