"""Shared helpers for validating and building the canonical contract catalog."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

try:
    import yaml
except ImportError as exc:  # pragma: no cover - dependency diagnostic
    raise SystemExit("PyYAML is required: python -m pip install pyyaml") from exc


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = REPOSITORY_ROOT / "contracts"
DIST_ROOT = REPOSITORY_ROOT / "dist" / "contracts"
MANIFEST_PATH = CONTRACTS_ROOT / "manifest.yaml"
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}

EXPECTED_PORTS = {
    "esb-public-api": 8000,
    "customer-service": 8001,
    "event-service": 8002,
    "seat-inventory": 8003,
    "booking-service": 8004,
    "payment-service": 8005,
    "ticket-service": 8006,
    "notification-service": 8007,
    "realtime-service": 8008,
    "identity-service": 8009,
}

EXPECTED_ARTIFACTS = {
    "esb-public-api.yaml",
    "identity-service.yaml",
    "customer-service.yaml",
    "event-service.yaml",
    "seat-inventory.wsdl",
    "seat-inventory.xsd",
    "booking-service.yaml",
    "payment-service.yaml",
    "ticket-service.yaml",
    "notification-service.yaml",
    "realtime-service.openapi.yaml",
    "realtime-service.asyncapi.yaml",
    "event-messages.schema.json",
}


class ContractError(ValueError):
    """Catalog error carrying stable file and rule context."""

    def __init__(self, file: Path | str, rule: str, message: str) -> None:
        self.file = str(file)
        self.rule = rule
        self.message = message
        super().__init__(f"{self.file}: [{self.rule}] {self.message}")


@dataclass(frozen=True)
class Artifact:
    contract_id: str
    path: Path
    relative_path: str
    format: str
    port: int | None


def read_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ContractError(path, "parse.yaml", str(exc)) from exc
    if not isinstance(value, dict):
        raise ContractError(path, "parse.yaml", "document root must be a mapping")
    return value


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(path, "parse.json", str(exc)) from exc
    if not isinstance(value, dict):
        raise ContractError(path, "parse.json", "document root must be an object")
    return value


def load_manifest() -> dict[str, Any]:
    return read_yaml(MANIFEST_PATH)


def manifest_artifacts(manifest: dict[str, Any]) -> list[Artifact]:
    result: list[Artifact] = []
    contracts = manifest.get("runtimeContracts")
    if not isinstance(contracts, list):
        raise ContractError(
            MANIFEST_PATH, "manifest.runtimeContracts", "must be a list"
        )
    for contract in contracts:
        if not isinstance(contract, dict):
            raise ContractError(
                MANIFEST_PATH, "manifest.contract", "entry must be a mapping"
            )
        contract_id = contract.get("id")
        port = contract.get("port")
        entries = contract.get("artifacts")
        if not isinstance(contract_id, str) or not isinstance(entries, list):
            raise ContractError(
                MANIFEST_PATH, "manifest.contract", "id and artifacts are required"
            )
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise ContractError(
                    MANIFEST_PATH,
                    "manifest.artifact",
                    f"invalid artifact for {contract_id}",
                )
            relative = entry["path"]
            relative_path = Path(relative)
            if (
                relative_path.is_absolute()
                or ".." in relative_path.parts
                or len(relative_path.parts) != 1
            ):
                raise ContractError(
                    MANIFEST_PATH, "manifest.path", f"artifact must be flat: {relative}"
                )
            result.append(
                Artifact(
                    contract_id=contract_id,
                    path=CONTRACTS_ROOT / relative_path,
                    relative_path=relative_path.as_posix(),
                    format=str(entry.get("format", "")),
                    port=port if isinstance(port, int) else None,
                )
            )
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(65536), b""):
                digest.update(block)
    except OSError as exc:
        raise ContractError(path, "digest.sha256", str(exc)) from exc
    return digest.hexdigest()


def aggregate_sha256(entries: list[dict[str, Any]]) -> str:
    payload = "".join(
        f"{entry['path']}\0{entry['sha256']}\n"
        for entry in sorted(entries, key=lambda item: item["path"])
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def operations(document: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    for path, path_item in document.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method in HTTP_METHODS and isinstance(operation, dict):
                yield method.upper(), path, operation


def walk_refs(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value
            else:
                yield from walk_refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk_refs(value)


def walk_mappings(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk_mappings(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk_mappings(value)


def json_pointer(document: Any, ref: str) -> Any:
    if ref == "#":
        return document
    if not ref.startswith("#/"):
        raise KeyError(f"unsupported local reference: {ref}")
    current = document
    for token in ref[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current
