#!/usr/bin/env python3
"""Deterministically materialize the reviewed Prompt-2A event catalog."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

CONTRACTS = Path(__file__).resolve().parents[1]

IDENTIFIER = {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"}
VERSION = {"type": "integer", "minimum": 1}


def obj(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": properties,
    }


SPECS: dict[str, dict[str, Any]] = {
    "booking.created": obj(
        ["bookingId", "customerId", "eventId", "status", "resourceVersion"],
        {
            "bookingId": IDENTIFIER,
            "customerId": IDENTIFIER,
            "eventId": IDENTIFIER,
            "status": {"const": "PENDING"},
            "resourceVersion": VERSION,
        },
    ),
    "booking.confirmed": obj(
        ["bookingId", "status", "reservationId", "paymentId", "ticketIds", "resourceVersion"],
        {
            "bookingId": IDENTIFIER,
            "status": {"const": "CONFIRMED"},
            "reservationId": IDENTIFIER,
            "paymentId": IDENTIFIER,
            "ticketIds": {"type": "array", "minItems": 1, "items": IDENTIFIER},
            "resourceVersion": VERSION,
        },
    ),
    "booking.failed": obj(
        ["bookingId", "status", "reasonCode", "compensationState", "resourceVersion"],
        {
            "bookingId": IDENTIFIER,
            "status": {"const": "FAILED"},
            "reasonCode": {"type": "string", "pattern": "^[A-Z0-9_]{2,64}$"},
            "compensationState": {"type": "string", "enum": ["NOT_REQUIRED", "COMPLETED", "PENDING"]},
            "resourceVersion": VERSION,
        },
    ),
    "booking.cancelled": obj(
        ["bookingId", "status", "compensationState", "resourceVersion"],
        {
            "bookingId": IDENTIFIER,
            "status": {"type": "string", "enum": ["CANCELLED", "COMPENSATION_PENDING"]},
            "compensationState": {"type": "string", "enum": ["COMPLETED", "PENDING"]},
            "resourceVersion": VERSION,
        },
    ),
    "payment.created": obj(
        ["paymentId", "bookingId", "status", "amount", "resourceVersion"],
        {
            "paymentId": IDENTIFIER,
            "bookingId": IDENTIFIER,
            "status": {"const": "CREATED"},
            "amount": {"$ref": "urn:event-ticketing:money:v1"},
            "resourceVersion": VERSION,
        },
    ),
    "payment.authorized": obj(
        ["paymentId", "bookingId", "status", "amount", "resourceVersion"],
        {
            "paymentId": IDENTIFIER,
            "bookingId": IDENTIFIER,
            "status": {"const": "AUTHORIZED"},
            "amount": {"$ref": "urn:event-ticketing:money:v1"},
            "resourceVersion": VERSION,
        },
    ),
    "payment.succeeded": obj(
        ["paymentId", "bookingId", "status", "capturedAmount", "resourceVersion"],
        {
            "paymentId": IDENTIFIER,
            "bookingId": IDENTIFIER,
            "status": {"const": "CAPTURED"},
            "capturedAmount": {"$ref": "urn:event-ticketing:money:v1"},
            "resourceVersion": VERSION,
        },
    ),
    "payment.failed": obj(
        ["paymentId", "bookingId", "status", "failureCode", "resourceVersion"],
        {
            "paymentId": IDENTIFIER,
            "bookingId": IDENTIFIER,
            "status": {"const": "FAILED"},
            "failureCode": {"type": "string", "pattern": "^[A-Z0-9_]{2,64}$"},
            "resourceVersion": VERSION,
        },
    ),
    "payment.cancelled": obj(
        ["paymentId", "bookingId", "status", "reason", "resourceVersion"],
        {
            "paymentId": IDENTIFIER,
            "bookingId": IDENTIFIER,
            "status": {"const": "CANCELLED"},
            "reason": {"type": "string", "minLength": 1, "maxLength": 300},
            "resourceVersion": VERSION,
        },
    ),
    "payment.refunded": obj(
        ["paymentId", "bookingId", "status", "refundAmount", "resourceVersion"],
        {
            "paymentId": IDENTIFIER,
            "bookingId": IDENTIFIER,
            "status": {"type": "string", "enum": ["PARTIALLY_REFUNDED", "REFUNDED"]},
            "refundAmount": {"$ref": "urn:event-ticketing:money:v1"},
            "resourceVersion": VERSION,
        },
    ),
    "ticket.issued": obj(
        ["ticketId", "bookingId", "eventId", "seatId", "status", "resourceVersion"],
        {
            "ticketId": IDENTIFIER,
            "bookingId": IDENTIFIER,
            "eventId": IDENTIFIER,
            "seatId": IDENTIFIER,
            "status": {"const": "ISSUED"},
            "resourceVersion": VERSION,
        },
    ),
    "ticket.checked-in": obj(
        ["ticketId", "bookingId", "status", "gateId", "resourceVersion"],
        {
            "ticketId": IDENTIFIER,
            "bookingId": IDENTIFIER,
            "status": {"const": "CHECKED_IN"},
            "gateId": IDENTIFIER,
            "resourceVersion": VERSION,
        },
    ),
    "ticket.cancelled": obj(
        ["ticketId", "bookingId", "status", "reason", "resourceVersion"],
        {
            "ticketId": IDENTIFIER,
            "bookingId": IDENTIFIER,
            "status": {"const": "CANCELLED"},
            "reason": {"type": "string", "minLength": 1, "maxLength": 300},
            "resourceVersion": VERSION,
        },
    ),
    "ticket.qr-regenerated": obj(
        ["ticketId", "bookingId", "status", "qrVersion", "resourceVersion"],
        {
            "ticketId": IDENTIFIER,
            "bookingId": IDENTIFIER,
            "status": {"const": "ISSUED"},
            "qrVersion": VERSION,
            "resourceVersion": VERSION,
        },
    ),
}


def example(event_type: str, data_schema: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name, schema in data_schema["properties"].items():
        if "$ref" in schema:
            values[name] = {"amountMinor": 100000, "currency": "VND"}
        elif "const" in schema:
            values[name] = schema["const"]
        elif "enum" in schema:
            values[name] = schema["enum"][0]
        elif schema.get("type") == "array":
            values[name] = ["TKT-001"]
        elif schema.get("type") == "integer":
            values[name] = 1
        elif name.endswith("Ids"):
            values[name] = ["ID-001"]
        elif name in {"reason", "reasonCode", "failureCode"}:
            values[name] = "PROCESSING_FAILED" if name != "reason" else "Requested cancellation"
        else:
            prefix = name.removesuffix("Id").upper().replace("RESOURCEVERSION", "V") or "ID"
            values[name] = f"{prefix}-001"
    return {
        "eventId": "EVTMSG-001",
        "eventType": event_type,
        "schemaVersion": 1,
        "occurredAt": "2026-08-03T03:00:00Z",
        "correlationId": "corr-1234567890abcdef",
        "aggregateId": values.get("bookingId") or values.get("paymentId") or values.get("ticketId") or "AGG-001",
        "data": values,
    }


def main() -> None:
    for event_type, data_schema in SPECS.items():
        producer = event_type.split(".", 1)[0]
        filename = event_type.split(".", 1)[1].replace(".", "-") + ".schema.json"
        target = CONTRACTS / "events" / producer / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        description = (
            f"Official design-derived v1 producer-owned schema for {event_type}. "
            "Delivery is at-least-once and consumers deduplicate by eventId."
        )
        document = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"urn:event-ticketing:event:{event_type}:v1",
            "title": event_type,
            "description": description,
            "x-contract-status": "canonical-v1",
            "x-designed-baseline-version": "1.0.0",
            "x-origin": "design-derived-v1",
            "allOf": [
                {"$ref": "urn:event-ticketing:event-envelope:v1"},
                {
                    "type": "object",
                    "properties": {
                        "eventType": {"const": event_type},
                        "schemaVersion": {"const": 1},
                        "data": {"$ref": "#/$defs/data"},
                    },
                },
            ],
            "$defs": {"data": data_schema},
            "examples": [example(event_type, data_schema)],
        }
        target.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        example_target = CONTRACTS / "examples" / "events" / f"{event_type}.json"
        example_target.parent.mkdir(parents=True, exist_ok=True)
        example_target.write_text(json.dumps(document["examples"][0], indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
