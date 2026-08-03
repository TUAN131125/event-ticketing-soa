from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from app.config import REPOSITORY_ROOT

EXPECTED_FREEZE_ID = "event-ticketing-contracts-v1.0.0"
EXPECTED_CATALOG_SHA = "6fea9810b380cd94a00fa2a5b611e70c01d8db1c41b6ca886b303a9395d408a6"


def verify_contract_freeze(root: Path = REPOSITORY_ROOT) -> None:
    contracts = root / "contracts"
    freeze_path = contracts / "FREEZE.lock.yaml"
    manifest_path = contracts / "manifest.yaml"
    if not freeze_path.is_file() or not manifest_path.is_file():
        raise RuntimeError("frozen contract catalog is missing")
    freeze = yaml.safe_load(freeze_path.read_text(encoding="utf-8"))
    if freeze.get("freezeId") != EXPECTED_FREEZE_ID or freeze.get("catalogSha256") != EXPECTED_CATALOG_SHA:
        raise RuntimeError("unexpected contract freeze")
    manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if manifest_digest != freeze.get("manifestSha256"):
        raise RuntimeError("contract manifest digest mismatch")
    for entry in freeze.get("contracts", []):
        artifact = contracts / entry["canonicalPath"]
        if not artifact.is_file() or hashlib.sha256(artifact.read_bytes()).hexdigest() != entry["sha256"]:
            raise RuntimeError(f"contract artifact mismatch: {entry['contractId']}")
