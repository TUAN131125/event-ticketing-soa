#!/usr/bin/env python3
"""Refresh the official clean-slate v1 catalog and SHA-256 digests."""

from __future__ import annotations

import sys
from typing import Any

sys.dont_write_bytecode = True

from contract_utils import CONTRACTS, canonical_artifacts, read_json, sha256, yaml

VERSION = "1.0.0"
STATUS = "canonical-v1"


def format_for(relative: str) -> str:
    if relative.endswith(".schema.json"):
        return "json-schema-2020-12"
    if relative.endswith(".wsdl"):
        return "wsdl-1.1"
    if relative.endswith(".xsd"):
        return "xsd-1.0"
    if relative.endswith(".md"):
        return "markdown"
    if relative.endswith(".yaml"):
        return "openapi-3.1" if "openapi" in relative else "yaml"
    raise ValueError(f"unsupported canonical artifact: {relative}")


def owner_for(relative: str) -> str:
    if relative.startswith("common/"):
        return "Architecture"
    if relative.startswith("soap/"):
        return "Seat Inventory Service"
    if relative.startswith("events/"):
        return f"{relative.split('/')[1].title()} Service"
    if relative.startswith("webhooks/notification/"):
        return "Notification Service"
    if relative.startswith("websocket/realtime-status/"):
        return "Realtime Status Service"
    if relative.startswith("openapi/"):
        filename = relative.rsplit("/", 1)[-1]
        names = {
            "customer-service.yaml": "Customer Service",
            "event-service.yaml": "Event Service",
            "booking-service.yaml": "Booking Service",
            "payment-service.yaml": "Payment Service",
            "ticket-service.yaml": "Ticket Service",
            "notification-service.yaml": "Notification Service",
            "realtime-service.yaml": "Realtime Status Service",
            "identity-service.yaml": "Identity Service",
            "esb-public-api.yaml": "Booking Orchestrator / ESB",
        }
        return names[filename]
    raise ValueError(f"owner is not declared for {relative}")


def title_for(relative: str) -> str:
    path = CONTRACTS / relative
    if relative.endswith(".schema.json"):
        return str(read_json(path).get("title") or path.stem)
    return path.stem.replace("-", " ").title()


def consumers_for(relative: str) -> list[str]:
    if relative.startswith("common/"):
        return ["All contract providers and consumers"]
    if relative.startswith("openapi/esb-public-api"):
        return ["Browser frontend", "Operations"]
    if relative.startswith("openapi/"):
        return ["Booking Orchestrator / ESB", "Authorized internal consumers"]
    if relative.startswith("events/") or relative.startswith("webhooks/"):
        return ["Notification Service", "Authorized event consumers"]
    if relative.startswith("websocket/"):
        return ["Browser frontend", "Realtime Status Service"]
    if relative.startswith("soap/"):
        return ["Booking Orchestrator / ESB"]
    return []


def build_entry(relative: str) -> dict[str, Any]:
    return {
        "contractId": relative.replace("/", ".").replace(".schema.json", "").replace(".yaml", "").replace(".md", ""),
        "title": title_for(relative),
        "semanticOwner": owner_for(relative),
        "format": format_for(relative),
        "canonicalPath": relative,
        "designedBaselineVersion": VERSION,
        "publicationVersion": VERSION,
        "contractStatus": STATUS,
        "consumers": consumers_for(relative),
        "sourceEvidence": ["Official clean-slate v1 contract decision"],
        "sha256": sha256(CONTRACTS / relative),
    }


def main() -> None:
    entries = [build_entry(relative) for relative in sorted(canonical_artifacts())]
    document = {
        "catalogVersion": VERSION,
        "baselineType": "clean-slate",
        "compatibilityPolicy": "no-legacy-baseline",
        "status": STATUS,
        "canonicalRoot": "contracts/",
        "contracts": entries,
    }
    (CONTRACTS / "manifest.yaml").write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=110),
        encoding="utf-8",
    )
    print(f"MANIFEST_REFRESHED status={STATUS} entries={len(entries)}")


if __name__ == "__main__":
    main()
