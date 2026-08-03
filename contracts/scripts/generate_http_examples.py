#!/usr/bin/env python3
"""Materialize deterministic HTTP examples and their validation index."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

CONTRACTS = Path(__file__).resolve().parents[1]
OUT = CONTRACTS / "examples" / "http"
NOW = "2026-08-03T03:00:00Z"
CORR = "corr-1234567890abcdef"
MONEY = {"amountMinor": 100000, "currency": "VND"}


def error(code: str, message: str, retryable: bool = False) -> dict[str, Any]:
    return {
        "correlationId": CORR,
        "traceId": None,
        "error": {"code": code, "message": message, "retryable": retryable, "details": {}},
    }


SUCCESS: dict[str, tuple[str, str, dict[str, Any]]] = {
    "customer-success.json": (
        "customer-service.yaml", "Customer",
        {"customerId": "CUS-001", "name": "Demo Customer", "email": "demo@example.invalid", "phone": None, "status": "ACTIVE", "resourceVersion": 1, "createdAt": NOW, "updatedAt": NOW},
    ),
    "event-success.json": (
        "event-service.yaml", "Event",
        {"eventId": "EV-001", "name": "SOA Conference", "venue": "Hall A", "startsAt": "2026-08-20T12:00:00Z", "saleStartsAt": NOW, "saleEndsAt": "2026-08-19T12:00:00Z", "status": "ON_SALE", "ticketTypes": [{"code": "VIP", "name": "VIP", "price": MONEY}], "resourceVersion": 2},
    ),
    "booking-success.json": (
        "booking-service.yaml", "Booking",
        {"bookingId": "BKG-001", "customerId": "CUS-001", "eventId": "EV-001", "status": "COMPENSATION_PENDING", "items": [{"seatId": "A12", "ticketTypeCode": "VIP"}], "total": MONEY, "reservationId": "RES-001", "paymentId": "PAY-001", "ticketIds": [], "resourceVersion": 5, "createdAt": NOW, "updatedAt": NOW},
    ),
    "payment-success.json": (
        "payment-service.yaml", "Payment",
        {"paymentId": "PAY-001", "bookingId": "BKG-001", "amount": MONEY, "status": "UNKNOWN", "providerReference": "PROV-001", "resourceVersion": 3, "createdAt": NOW, "updatedAt": NOW},
    ),
    "ticket-success.json": (
        "ticket-service.yaml", "Ticket",
        {"ticketId": "TKT-001", "bookingId": "BKG-001", "eventId": "EV-001", "customerId": "CUS-001", "seatId": "A12", "status": "ISSUED", "qrToken": None, "resourceVersion": 1},
    ),
    "notification-success.json": (
        "notification-service.yaml", "Delivery",
        {"deliveryId": "DEL-001", "eventId": "EVTMSG-001", "channel": "EMAIL", "status": "RETRY_PENDING", "attemptCount": 1, "lastErrorCode": "PROVIDER_TIMEOUT", "createdAt": NOW},
    ),
    "esb-success.json": (
        "esb-public-api.yaml", "BookingResult",
        {"bookingId": "BKG-001", "status": "PAYMENT_PROCESSING", "total": MONEY, "reservationId": "RES-001", "paymentId": "PAY-001", "ticketIds": [], "correlationId": CORR},
    ),
    "realtime-success.json": (
        "realtime-service.yaml", "ConnectionHealth",
        {"status": "UP", "activeConnections": 12, "activeBookingChannels": 5, "broadcastBackend": "memory", "backendAvailable": True, "draining": False},
    ),
    "realtime-event-accepted.json": (
        "realtime-service.yaml", "StatusEventResult",
        {"outcome": "ACCEPTED", "messageId": "MSG-001", "bookingId": "BKG-001", "sequence": 3, "correlationId": CORR},
    ),
    "identity-link-success.json": (
        "customer-service.yaml", "IdentityMapping",
        {"identitySubject": "user-subject", "customerId": "CUS-001", "status": "ACTIVE", "resourceVersion": 1, "linkedAt": NOW, "updatedAt": NOW},
    ),
    "identity-resolve-active.json": (
        "customer-service.yaml", "IdentityMapping",
        {"identitySubject": "user-subject", "customerId": "CUS-001", "status": "ACTIVE", "resourceVersion": 2, "linkedAt": NOW, "updatedAt": NOW},
    ),
    "identity-resolve-inactive.json": (
        "customer-service.yaml", "IdentityMapping",
        {"identitySubject": "inactive-subject", "customerId": "CUS-002", "status": "INACTIVE", "resourceVersion": 4, "linkedAt": NOW, "updatedAt": NOW},
    ),
    "booking-access-owner.json": (
        "booking-service.yaml", "BookingAccessDecision",
        {"allowed": True, "reasonCode": "OWNER", "cacheTtlSeconds": 5},
    ),
    "booking-access-admin-override.json": (
        "booking-service.yaml", "BookingAccessDecision",
        {"allowed": True, "reasonCode": "ADMIN_OVERRIDE", "cacheTtlSeconds": 5},
    ),
    "booking-access-not-owner.json": (
        "booking-service.yaml", "BookingAccessDecision",
        {"allowed": False, "reasonCode": "NOT_OWNER", "cacheTtlSeconds": 0},
    ),
    "booking-access-dependency-failure.json": (
        "booking-service.yaml", "BookingAccessDecision",
        {"allowed": False, "reasonCode": "DEPENDENCY_UNAVAILABLE", "cacheTtlSeconds": 0},
    ),
    "ws-ticket-success.json": (
        "esb-public-api.yaml", "WsTicketResponse",
        {"ticket": "eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleS0xIn0.eyJhdWQiOiJyZWFsdGltZS1zdGF0dXMtc2VydmljZSJ9.signature", "bookingId": "BKG-001", "expiresAt": "2026-08-03T03:01:00Z"},
    ),
}

ERRORS = {
    "customer-error.json": error("VERSION_CONFLICT", "Customer version is stale", True),
    "event-error.json": error("EVENT_NOT_ON_SALE", "Event is not on sale"),
    "booking-error.json": error("INVALID_BOOKING_STATE", "Booking transition is not allowed"),
    "payment-error.json": error("PAYMENT_RESULT_UNKNOWN", "Payment result requires reconciliation", True),
    "ticket-error.json": error("TICKET_ALREADY_USED", "Ticket has already been checked in"),
    "notification-error.json": error("INVALID_SIGNATURE", "Webhook signature is invalid"),
    "esb-error.json": error("DEPENDENCY_UNAVAILABLE", "A required provider is unavailable", True),
    "realtime-error.json": error("REALTIME_UNAVAILABLE", "Use authoritative booking REST status", True),
    "idempotency-conflict.json": error("IDEMPOTENCY_KEY_REUSED", "The key was reused with a different payload"),
    "optimistic-concurrency-conflict.json": error("VERSION_CONFLICT", "If-Match does not match resourceVersion", True),
    "identity-link-conflict.json": error("IDENTITY_MAPPING_CONFLICT", "The identity subject or customer already has an active mapping"),
    "identity-resolve-not-found.json": error("IDENTITY_NOT_MAPPED", "No identity mapping was found"),
    "ws-ticket-denied.json": error("ACCESS_DENIED", "Booking access was denied"),
    "internal-status-invalid-audience.json": error("INVALID_SERVICE_AUDIENCE", "The service credential audience is invalid"),
    "internal-status-replayed-jti.json": error("SERVICE_TOKEN_REPLAYED", "The service credential has already been used"),
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    index: list[dict[str, str]] = []
    for filename, (contract, schema, value) in SUCCESS.items():
        (OUT / filename).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        index.append({"file": filename, "openapi": contract, "schema": schema})
    for filename, value in ERRORS.items():
        (OUT / filename).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        index.append({"file": filename, "jsonSchema": "../../common/error-response.schema.json"})
    (OUT / "idempotency-replay.json").write_text(
        json.dumps(SUCCESS["booking-success.json"][2], indent=2) + "\n", encoding="utf-8"
    )
    index.append({"file": "idempotency-replay.json", "openapi": "booking-service.yaml", "schema": "Booking"})
    status_event = {
        "messageId": "MSG-001", "bookingId": "BKG-001", "status": "PAYMENT_PROCESSING",
        "sequence": 3, "occurredAt": NOW, "correlationId": CORR,
        "message": "Payment result is being verified",
    }
    (OUT / "internal-status-event-valid.json").write_text(
        json.dumps(status_event, indent=2) + "\n", encoding="utf-8"
    )
    index.append({
        "file": "internal-status-event-valid.json",
        "jsonSchema": "../../websocket/realtime-status/status-message.schema.json",
    })
    (OUT / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
