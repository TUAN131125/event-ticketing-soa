from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml

EXPECTED_FREEZE_ID = "event-ticketing-contracts-v1.0.0"
CONTRACT_DIRECTORY = Path(os.getenv("ESB_CONTRACT_DIR", "contracts"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65_536), b""):
            digest.update(block)
    return digest.hexdigest()


def _aggregate(entries: list[tuple[str, str]]) -> str:
    payload = "".join(f"{path}\0{digest}\n" for path, digest in sorted(entries))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _source_entries(manifest: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for contract in manifest.get("runtimeContracts", []):
        for artifact in contract.get("artifacts", []):
            result.append(str(artifact["path"]))
    return sorted(result)


def _load_document(path: Path) -> dict[str, Any]:
    try:
        if path.suffix == ".json":
            document = json.loads(path.read_text(encoding="utf-8"))
        else:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise RuntimeError(f"cannot read contract manifest: {path}") from exc
    if not isinstance(document, dict):
        raise RuntimeError("contract manifest must be an object")
    return document


def _built_catalog_sha(directory: Path, manifest: dict[str, Any]) -> str:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 13:
        raise RuntimeError("built contract inventory must contain 13 artifacts")
    entries: list[tuple[str, str]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise RuntimeError("built contract artifact entry must be an object")
        relative = str(artifact.get("path", ""))
        expected = str(artifact.get("sha256", ""))
        path = _flat_artifact(directory, relative)
        actual = _sha256(path)
        if actual != expected:
            raise RuntimeError(f"contract artifact digest mismatch: {relative}")
        entries.append((relative, actual))
    aggregate = _aggregate(entries)
    if aggregate != manifest.get("aggregateSha256"):
        raise RuntimeError("built contract aggregate digest mismatch")
    return aggregate


def _flat_artifact(directory: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
        raise RuntimeError(f"contract artifact path is not flat: {relative}")
    artifact = directory / path
    if not artifact.is_file():
        raise RuntimeError(f"contract artifact is missing: {relative}")
    return artifact


def _source_catalog_sha(directory: Path, manifest: dict[str, Any]) -> str:
    entries = _source_entries(manifest)
    if len(entries) != 13:
        raise RuntimeError("canonical contract inventory must contain 13 artifacts")
    return _aggregate([(relative, _sha256(_flat_artifact(directory, relative))) for relative in entries])


def _catalog_sha(directory: Path) -> str:
    built_manifest = directory / "manifest.json"
    if built_manifest.is_file():
        return _built_catalog_sha(directory, _load_document(built_manifest))
    return _source_catalog_sha(
        directory,
        _load_document(directory / "manifest.yaml"),
    )


EXPECTED_CATALOG_SHA = _catalog_sha(CONTRACT_DIRECTORY)


def verify_contract_freeze(directory: Path = CONTRACT_DIRECTORY) -> None:
    """Verify the canonical source tree or a built runtime contract bundle."""

    manifest_path = directory / "manifest.json"
    if manifest_path.is_file():
        manifest = _load_document(manifest_path)
        if manifest.get("catalogVersion") != "1.0.0":
            raise RuntimeError("unexpected built contract catalog version")
        _built_catalog_sha(directory, manifest)
        return

    manifest = _load_document(directory / "manifest.yaml")
    if manifest.get("catalogVersion") != "1.0.0" or manifest.get("sourceOfTruth") != "contracts/":
        raise RuntimeError("unexpected canonical contract catalog")
    _source_catalog_sha(directory, manifest)
