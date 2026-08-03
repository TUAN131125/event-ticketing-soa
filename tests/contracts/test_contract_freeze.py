from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"
MANIFEST_PATH = CONTRACTS / "manifest.yaml"
LOCK_PATH = CONTRACTS / "FREEZE.lock.yaml"


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aggregate_digest(entries: list[dict]) -> str:
    payload = "".join(
        f"{entry['contractId']}\n{entry['canonicalPath']}\n{entry['sha256']}\n"
        for entry in sorted(entries, key=lambda value: value["contractId"])
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def canonical_artifacts() -> set[str]:
    patterns = (
        "common/*.schema.json", "common/*.yaml", "openapi/*.yaml",
        "soap/*.wsdl", "soap/*.xsd", "events/**/*.schema.json",
        "webhooks/**/*.schema.json", "websocket/**/*.schema.json",
        "websocket/**/close-codes.yaml", "websocket/**/protocol.md",
    )
    return {
        path.relative_to(CONTRACTS).as_posix()
        for pattern in patterns
        for path in CONTRACTS.glob(pattern)
        if path.is_file()
    }


def test_freeze_lock_exists_and_identifies_v1() -> None:
    assert LOCK_PATH.is_file()
    lock = load_yaml(LOCK_PATH)
    assert lock["freezeId"] == "event-ticketing-contracts-v1.0.0"
    assert lock["catalogVersion"] == "1.0.0"
    assert lock["baselineType"] == "clean-slate"
    assert lock["status"] == "frozen"


def test_manifest_digest_matches() -> None:
    lock = load_yaml(LOCK_PATH)
    assert lock["manifestPath"] == "contracts/manifest.yaml"
    assert lock["manifestSha256"] == digest(MANIFEST_PATH)


def test_aggregate_catalog_digest_matches_algorithm() -> None:
    manifest = load_yaml(MANIFEST_PATH)
    lock = load_yaml(LOCK_PATH)
    assert lock["catalogSha256"] == aggregate_digest(manifest["contracts"])


def test_lock_entries_match_manifest_exactly() -> None:
    manifest_entries = load_yaml(MANIFEST_PATH)["contracts"]
    expected = [
        {key: entry[key] for key in ("contractId", "canonicalPath", "sha256")}
        for entry in sorted(manifest_entries, key=lambda value: value["contractId"])
    ]
    assert load_yaml(LOCK_PATH)["contracts"] == expected
    assert len(expected) == 36


def test_every_frozen_artifact_digest_matches() -> None:
    for entry in load_yaml(LOCK_PATH)["contracts"]:
        artifact = (CONTRACTS / entry["canonicalPath"]).resolve()
        assert artifact.is_relative_to(CONTRACTS.resolve())
        assert artifact.is_file()
        assert digest(artifact) == entry["sha256"]


def test_manifest_has_no_orphan_or_extra_freeze_entry() -> None:
    manifest_paths = {entry["canonicalPath"] for entry in load_yaml(MANIFEST_PATH)["contracts"]}
    lock_paths = {entry["canonicalPath"] for entry in load_yaml(LOCK_PATH)["contracts"]}
    assert manifest_paths == canonical_artifacts()
    assert lock_paths == manifest_paths


def test_contract_paths_are_relative_and_inside_canonical_root() -> None:
    for entry in load_yaml(LOCK_PATH)["contracts"]:
        relative = Path(entry["canonicalPath"])
        assert not relative.is_absolute()
        assert ".." not in relative.parts
        assert (CONTRACTS / relative).resolve().is_relative_to(CONTRACTS.resolve())


def test_freeze_is_deterministic_from_manifest() -> None:
    manifest = load_yaml(MANIFEST_PATH)
    lock = load_yaml(LOCK_PATH)
    assert lock["catalogSha256"] == aggregate_digest(manifest["contracts"])
    assert [entry["contractId"] for entry in lock["contracts"]] == sorted(
        entry["contractId"] for entry in lock["contracts"]
    )


def test_existing_contract_validator_passes_without_writing() -> None:
    before = LOCK_PATH.read_bytes()
    completed = subprocess.run(
        [sys.executable, str(CONTRACTS / "scripts" / "validate_contracts.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "CONTRACT_VALIDATION PASS" in completed.stdout
    assert LOCK_PATH.read_bytes() == before
