"""The saga may only continue past ReserveSeats while the hold is ACTIVE.

Every non-ACTIVE case asserts that the Payment fake was never called, not merely that the
caller received an error: an error response with a payment already created would still have
taken money against seats nobody is holding.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from app.application.booking import BookingSaga
from app.domain.errors import EsbError
from app.domain.models import Principal, RequestContext
from app.persistence.repositories import InMemoryRepository
from tests.fakes import Booking, Customer, Event, Payment, Seat, Ticket

PAYMENT_CALLS = {"payment-create", "authorize", "capture"}


def _saga(log, reserve_status):
    repo = InMemoryRepository()
    saga = BookingSaga(
        Customer(),
        Event(),
        Seat(log, reserve_status=reserve_status),
        Booking(log),
        Payment(log),
        Ticket(log),
        repo,
        repo,
        SimpleNamespace(reservation_ttl_seconds=300),
    )
    return saga, repo


def _context(correlation: str) -> RequestContext:
    return RequestContext(
        correlation,
        "1" * 32,
        time.monotonic() + 5,
        Principal("u", frozenset({"CUSTOMER"}), "cust-1"),
    )


async def _place(saga, key: str, correlation: str):
    return await saga.place(
        {"eventId": "e1", "seatIds": ["A1"], "paymentMethodToken": "success"},
        key,
        _context(correlation),
    )


@pytest.mark.asyncio
async def test_active_reservation_lets_the_workflow_continue() -> None:
    log: list[str] = []
    saga, repo = _saga(log, "ACTIVE")

    status, body = await _place(saga, "guard-active", "corr-active")

    assert status == 201
    assert body["status"] == "CONFIRMED"
    assert "payment-create" in log
    workflow = next(iter(repo.workflows.values()))
    assert workflow.evidence["reservationStatus"] == "ACTIVE"


@pytest.mark.parametrize("reservation_status", ["EXPIRED", "RELEASED", "CONFIRMED"])
@pytest.mark.asyncio
async def test_non_active_reservation_stops_before_payment(
    reservation_status: str,
) -> None:
    log: list[str] = []
    saga, repo = _saga(log, reservation_status)

    with pytest.raises(EsbError) as raised:
        await _place(saga, f"guard-{reservation_status}", f"corr-{reservation_status}")

    error = raised.value
    assert error.code == "SEAT_RESERVATION_NOT_ACTIVE"
    assert error.status_code == 409
    assert error.retryable is False
    assert "reserve" in log  # the reservation call really happened
    assert not PAYMENT_CALLS & set(log)
    assert "issue-ticket" not in log
    assert "booking-confirm" not in log
    # Evidence records what Seat actually said, not a convenient default.
    workflow = next(iter(repo.workflows.values()))
    assert workflow.evidence["reservationStatus"] == reservation_status


@pytest.mark.asyncio
async def test_missing_status_is_a_protocol_error_and_stops_before_payment() -> None:
    log: list[str] = []
    saga, _ = _saga(log, None)

    with pytest.raises(EsbError) as raised:
        await _place(saga, "guard-missing", "corr-missing")

    error = raised.value
    assert error.code == "SEAT_PROTOCOL_ERROR"
    assert error.status_code == 502
    # A response that violates the contract is not transient; retrying re-reads the same
    # invalid document.
    assert error.retryable is False
    assert not PAYMENT_CALLS & set(log)


@pytest.mark.asyncio
async def test_unknown_status_is_a_protocol_error_and_stops_before_payment() -> None:
    log: list[str] = []
    saga, _ = _saga(log, "RESERVED")

    with pytest.raises(EsbError) as raised:
        await _place(saga, "guard-unknown", "corr-unknown")

    assert raised.value.code == "SEAT_PROTOCOL_ERROR"
    assert raised.value.retryable is False
    assert not PAYMENT_CALLS & set(log)


@pytest.mark.asyncio
async def test_guard_failure_carries_no_raw_soap_into_the_error_envelope() -> None:
    """context_middleware renders EsbError.code/message/retryable straight to JSON, so the
    guard must not put provider XML in either field."""
    log: list[str] = []
    saga, _ = _saga(log, "EXPIRED")

    with pytest.raises(EsbError) as raised:
        await _place(saga, "guard-json", "corr-json")

    error = raised.value
    rendered = f"{error.code} {error.message} {error.details or ''}"
    assert "<" not in rendered
    assert "envelope" not in rendered.lower()
    assert "xml" not in rendered.lower()
