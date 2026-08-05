"""Build validated runtime contracts and a deterministic SHA-256 manifest."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from contract_utils import (
    DIST_ROOT,
    REPOSITORY_ROOT,
    aggregate_sha256,
    load_manifest,
    manifest_artifacts,
    sha256,
)
from validate_contracts import validate_contracts


def build_manifest(source: dict[str, Any]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for artifact in sorted(manifest_artifacts(source), key=lambda item: item.relative_path):
        entry: dict[str, Any] = {
            "contractId": artifact.contract_id,
            "path": artifact.relative_path,
            "format": artifact.format,
            "sizeBytes": artifact.path.stat().st_size,
            "sha256": sha256(artifact.path),
        }
        if artifact.port is not None:
            entry["port"] = artifact.port
        entries.append(entry)
    return {
        "catalogVersion": source["catalogVersion"],
        "sourceOfTruth": source["sourceOfTruth"],
        "runtimeContractCount": len(source["runtimeContracts"]),
        "artifactCount": len(entries),
        "aggregateSha256": aggregate_sha256(entries),
        "artifacts": entries,
    }


def replace_output(staging: Path) -> None:
    dist_parent = DIST_ROOT.parent.resolve()
    target = DIST_ROOT.resolve()
    if target.parent != dist_parent or target == REPOSITORY_ROOT.resolve():
        raise RuntimeError(f"unsafe build target: {target}")
    if DIST_ROOT.exists():
        shutil.rmtree(DIST_ROOT)
    staging.replace(DIST_ROOT)


def build() -> dict[str, Any]:
    report = validate_contracts()
    if report.errors:
        details = "\n".join(f"ERROR {error}" for error in report.errors)
        raise RuntimeError(f"contract validation failed before build:\n{details}")
    source = load_manifest()
    artifacts = manifest_artifacts(source)
    DIST_ROOT.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".contracts-build-", dir=DIST_ROOT.parent))
    try:
        for artifact in artifacts:
            shutil.copy2(artifact.path, staging / artifact.relative_path)
        manifest = build_manifest(source)
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        replace_output(staging)
        return manifest
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def main() -> int:
    try:
        manifest = build()
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"CONTRACT_BUILD FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        "CONTRACT_BUILD PASS "
        f"contracts={manifest['runtimeContractCount']} "
        f"artifacts={manifest['artifactCount']} "
        f"aggregateSha256={manifest['aggregateSha256']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
