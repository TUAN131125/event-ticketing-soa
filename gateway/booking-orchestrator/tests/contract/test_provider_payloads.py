from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from jsonschema import validate

from app.application.booking import BookingSaga
from app.application.cancellation import CancellationSaga
from app.domain.models import Principal, RequestContext
from app.persistence.repositories import InMemoryRepository
from tests.fakes import Booking, Customer, Event, Payment, Seat, Ticket

ROOT = Path(__file__).resolve().parents[4]


def load(name: str) -> dict:
    return yaml.safe_load(
        (ROOT / "contracts" / "providers" / name).read_text(encoding="utf-8")
    )


def request_schema(document: dict, path: str, method: str = "post") -> dict:
    return document["paths"][path][method]["requestBody"]["content"][
        "application/json"
    ]["schema"]


def assert_valid(document: dict, schema: dict, instance: dict) -> None:
    # Wrap the operation schema so its OpenAPI-local #/components references
    # resolve without the deprecated jsonschema RefResolver.
    validate(
        instance,
        {
            "$ref": "#/operationSchema",
            "operationSchema": schema,
            "components": document.get("components", {}),
        },
    )


def context() -> RequestContext:
    return RequestContext(
        "contract-correlation",
        "a" * 32,
        time.monotonic() + 10,
        Principal("user-1", frozenset({"CUSTOMER"}), "cust-1"),
    )


@pytest.mark.asyncio
async def test_booking_saga_outgoing_json_matches_refactored_provider_contracts():
    log: list[str] = []
    repository = InMemoryRepository()
    booking = Booking(log)
    payment = Payment(log)
    ticket = Ticket(log)
    saga = BookingSaga(
        Customer(),
        Event(),
        Seat(log),
        booking,
        payment,
        ticket,
        repository,
        repository,
        SimpleNamespace(reservation_ttl_seconds=600),
    )

    status, _ = await saga.place(
        {
            "eventId": "event-1",
            "seatIds": ["A1", "V1"],
            "paymentMethodToken": "tok_success_contract",
        },
        "idem-provider-contracts",
        context(),
    )
    assert status == 201

    booking_contract = load("booking-service-v2.yaml")
    booking_paths = {
        "create": "/bookings",
        "reservation": "/bookings/{booking_id}/reservation",
        "reservation-confirmed": "/bookings/{booking_id}/reservation-confirmed",
        "payment-started": "/bookings/{booking_id}/payment-started",
        "payment-result": "/bookings/{booking_id}/payment-result",
        "tickets": "/bookings/{booking_id}/tickets",
        "confirm": "/bookings/{booking_id}/confirm",
    }
    for key, path in booking_paths.items():
        assert_valid(
            booking_contract,
            request_schema(booking_contract, path),
            booking.payloads[key],
        )

    payment_contract = load("payment-service-refactored.yaml")
    payment_paths = {
        "create": "/payments",
        "authorize": "/payments/{payment_id}/authorize",
        "capture": "/payments/{payment_id}/capture",
    }
    for key, path in payment_paths.items():
        assert_valid(
            payment_contract,
            request_schema(payment_contract, path),
            payment.payloads[key],
        )

    ticket_contract = load("ticket-service.yaml")
    assert_valid(
        ticket_contract,
        request_schema(ticket_contract, "/tickets:issue"),
        ticket.payloads["issue"],
    )


@pytest.mark.asyncio
async def test_cancellation_payloads_match_booking_and_payment_contracts():
    log: list[str] = []
    booking = Booking(log)
    booking.current_status = "CONFIRMED"
    payment = Payment(log)
    ticket = Ticket(log)
    saga = CancellationSaga(booking, payment, Seat(log), ticket, Customer())

    await saga.cancel(
        "b1",
        {"reason": "USER_REQUEST", "expectedVersion": 1},
        "idem-cancel-contract",
        context(),
    )

    booking_contract = load("booking-service-v2.yaml")
    assert_valid(
        booking_contract,
        request_schema(booking_contract, "/bookings/{booking_id}/cancel"),
        booking.payloads["cancel"],
    )
    assert_valid(
        booking_contract,
        request_schema(
            booking_contract,
            "/bookings/{booking_id}/compensation-result",
        ),
        booking.payloads["compensation-result"],
    )

    payment_contract = load("payment-service-refactored.yaml")
    assert_valid(
        payment_contract,
        request_schema(payment_contract, "/payments/{payment_id}/refunds"),
        payment.payloads["refund"],
    )


@pytest.mark.asyncio
async def test_payment_decline_fail_payload_matches_booking_contract():
    class DeclinedPayment(Payment):
        async def authorize(self, *args):
            if len(args) > 1:
                self.payloads["authorize"] = args[1]
            self.log.append("authorize")
            return {
                "status": "FAILED",
                "failureCode": "PAYMENT_DECLINED",
                "resourceVersion": 2,
            }

    log: list[str] = []
    repository = InMemoryRepository()
    booking = Booking(log)
    payment = DeclinedPayment(log)
    saga = BookingSaga(
        Customer(),
        Event(),
        Seat(log),
        booking,
        payment,
        Ticket(log),
        repository,
        repository,
        SimpleNamespace(reservation_ttl_seconds=600),
    )

    status, _ = await saga.place(
        {
            "eventId": "event-1",
            "seatIds": ["A1"],
            "paymentMethodToken": "tok_decline_contract",
        },
        "idem-decline-contract",
        context(),
    )
    assert status == 402

    booking_contract = load("booking-service-v2.yaml")
    assert_valid(
        booking_contract,
        request_schema(booking_contract, "/bookings/{booking_id}/fail"),
        booking.payloads["fail"],
    )
