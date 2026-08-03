#!/usr/bin/env python3
"""Validate official v1 manifest completeness, scope and digests."""

from __future__ import annotations

import sys
from typing import Any

sys.dont_write_bytecode = True

from contract_utils import CONTRACTS, ContractError, canonical_artifacts, read_yaml, sha256

VERSION = "1.0.0"
STATUS = "canonical-v1"
REQUIRED = {
    "contractId", "title", "semanticOwner", "format", "canonicalPath",
    "designedBaselineVersion", "publicationVersion", "contractStatus",
    "consumers", "sourceEvidence", "sha256",
}


def validate_manifest() -> tuple[list[ContractError], dict[str, Any]]:
    document = read_yaml(CONTRACTS / "manifest.yaml")
    errors: list[ContractError] = []
    if not isinstance(document, dict):
        return [ContractError("manifest.yaml", "manifest.type", "root must be an object")], {}
    expected_top = {
        "catalogVersion": VERSION,
        "baselineType": "clean-slate",
        "compatibilityPolicy": "no-legacy-baseline",
        "status": STATUS,
    }
    for field, expected in expected_top.items():
        if document.get(field) != expected:
            errors.append(ContractError("manifest.yaml", "manifest.metadata", f"{field} must equal {expected}"))
    entries = document.get("contracts")
    if not isinstance(entries, list):
        return [*errors, ContractError("manifest.yaml", "manifest.entries", "contracts must be a list")], document

    ids: set[str] = set()
    paths: set[str] = set()
    for index, item in enumerate(entries):
        label = f"manifest.yaml#contracts[{index}]"
        if not isinstance(item, dict):
            errors.append(ContractError(label, "manifest.entry", "entry must be an object"))
            continue
        missing = REQUIRED - item.keys()
        if missing:
            errors.append(ContractError(label, "manifest.fields", f"missing fields: {sorted(missing)}"))
            continue
        forbidden = {
            "publication" + "Decision",
            "legacy" + "Baseline",
            "legacy" + "BaselineManifest",
            "compatibility",
        } & item.keys()
        if forbidden:
            errors.append(ContractError(label, "manifest.forbidden", f"forbidden fields: {sorted(forbidden)}"))
        contract_id = str(item["contractId"])
        relative = str(item["canonicalPath"])
        if contract_id in ids:
            errors.append(ContractError(label, "manifest.duplicate-id", contract_id))
        if relative in paths:
            errors.append(ContractError(label, "manifest.duplicate-path", relative))
        ids.add(contract_id)
        paths.add(relative)
        path = (CONTRACTS / relative).resolve()
        if not path.is_relative_to(CONTRACTS.resolve()):
            errors.append(ContractError(label, "manifest.scope", f"path escapes contracts/: {relative}"))
            continue
        if not path.is_file():
            errors.append(ContractError(label, "manifest.missing", relative))
            continue
        for field in ("designedBaselineVersion", "publicationVersion"):
            if item.get(field) != VERSION:
                errors.append(ContractError(label, "manifest.version", f"{field} must equal {VERSION}"))
        if item.get("contractStatus") != STATUS:
            errors.append(ContractError(label, "manifest.status", f"contractStatus must equal {STATUS}"))
        if not isinstance(item.get("sourceEvidence"), list) or not item["sourceEvidence"]:
            errors.append(ContractError(label, "manifest.evidence", "sourceEvidence must be non-empty"))
        actual = sha256(path)
        if item.get("sha256") != actual:
            errors.append(ContractError(label, "manifest.digest", f"expected {actual}, got {item.get('sha256')}"))

    artifacts = canonical_artifacts()
    for orphan in sorted(artifacts - paths):
        errors.append(ContractError(orphan, "manifest.orphan", "canonical artifact has no entry"))
    for non_artifact in sorted(paths - artifacts):
        errors.append(ContractError(non_artifact, "manifest.non-artifact", "entry is not a canonical artifact"))
    return errors, document


def main() -> int:
    errors, document = validate_manifest()
    for error in errors:
        print(f"ERROR {error}")
    count = len(document.get("contracts", [])) if document else 0
    if errors:
        print(f"MANIFEST_CHECK FAIL entries={count} errors={len(errors)}")
        return 1
    print(f"MANIFEST_CHECK PASS status={STATUS} entries={count} digests={count} orphans=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
