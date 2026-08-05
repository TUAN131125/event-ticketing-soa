from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"
MANIFEST_PATH = CONTRACTS / "manifest.yaml"


def load_manifest() -> dict:
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))


def runtime_entries() -> list[tuple[str, str]]:
    return sorted(
        (contract["id"], artifact["path"])
        for contract in load_manifest()["runtimeContracts"]
        for artifact in contract["artifacts"]
    )


def test_manifest_identifies_the_only_source_and_exact_runtime_inventory() -> None:
    manifest = load_manifest()
    assert manifest["catalogVersion"] == "1.0.0"
    assert manifest["sourceOfTruth"] == "contracts/"
    assert len(manifest["runtimeContracts"]) == 11
    assert len(runtime_entries()) == 13


def test_every_runtime_artifact_is_flat_and_present() -> None:
    for _, relative in runtime_entries():
        path = Path(relative)
        assert not path.is_absolute()
        assert len(path.parts) == 1
        assert ".." not in path.parts
        assert (CONTRACTS / path).is_file()


def test_contract_validator_passes_without_writing_sources() -> None:
    before = {
        relative: hashlib.sha256((CONTRACTS / relative).read_bytes()).hexdigest()
        for _, relative in runtime_entries()
    }
    completed = subprocess.run(
        [sys.executable, str(CONTRACTS / "scripts" / "validate_contracts.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "CONTRACT_VALIDATION PASS" in completed.stdout
    after = {
        relative: hashlib.sha256((CONTRACTS / relative).read_bytes()).hexdigest()
        for _, relative in runtime_entries()
    }
    assert after == before


def test_contract_build_emits_sha256_manifest() -> None:
    completed = subprocess.run(
        [sys.executable, str(CONTRACTS / "scripts" / "build_contracts.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    output = json.loads(
        (ROOT / "dist/contracts/manifest.json").read_text(encoding="utf-8")
    )
    assert output["runtimeContractCount"] == 11
    assert output["artifactCount"] == 13
    assert len(output["aggregateSha256"]) == 64
    assert all(len(entry["sha256"]) == 64 for entry in output["artifacts"])
