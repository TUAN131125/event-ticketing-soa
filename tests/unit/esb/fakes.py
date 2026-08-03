from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from app.domain.errors import DependencyFailure
from app.domain.models import Money, Principal, RequestContext


class FakeClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return time.monotonic()


def request_context(
    subject: str = "identity-subject", roles: tuple[str, ...] = ("CUSTOMER",)
) -> RequestContext:
    return RequestContext(
        "CORRELATION-0001",
        "TRACE-0001",
        time.monotonic() + 30,
        Principal(subject, roles),
    )


class FakeProviders:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, Any]]] = []
        self.mapping: Mapping[str, Any] = {"customerId": "CUS-1", "status": "ACTIVE"}
        self.customer: Mapping[str, Any] = {"customerId": "CUS-1", "status": "ACTIVE"}
        self.event: Mapping[str, Any] = {
            "eventId": "EVT-1",
            "name": "Concert",
            "venue": "Hall",
            "startsAt": "2026-08-04T10:00:00Z",
            "status": "ON_SALE",
            "ticketTypes": [
                {
                    "code": "STANDARD",
                    "price": {"amountMinor": 100000, "currency": "VND"},
                }
            ],
        }
        self.eligibility: Mapping[str, Any] = {"eligible": True}
        self.available = True
        self.reserve_outcomes: list[object] = [
            {"reservationId": "RES-1", "resourceVersion": 1, "status": "ACTIVE"}
        ]
        self.payment_outcomes: dict[str, object] = {
            "authorizePayment": {"status": "AUTHORIZED"},
            "capturePayment": {"status": "CAPTURED"},
            "createRefund": {"status": "REFUNDED"},
            "cancelPayment": {"status": "CANCELLED"},
        }
        self.transition_failures: set[str] = set()
        self.ticket_failure = False
        self.confirm_failure = False
        self.release_failure = False
        self.access_allowed = True
        self.booking: dict[str, Any] = {
            "bookingId": "BK-1",
            "status": "CONFIRMED",
            "total": {"amountMinor": 100000, "currency": "VND"},
            "reservationId": "RES-1",
            "paymentId": "PAY-1",
            "ticketIds": ["TKT-1"],
        }
        self.payment: Mapping[str, Any] = {"paymentId": "PAY-1", "status": "CAPTURED"}
        self.booking_tickets: list[Mapping[str, Any]] = [
            {"ticketId": "TKT-1", "status": "ISSUED"}
        ]

    def _record(self, operation: str, **details: Any) -> None:
        self.calls.append((operation, details))

    async def resolve_mapping(
        self, identity_subject: str, context: RequestContext
    ) -> Mapping[str, Any]:
        self._record("resolveIdentityMapping", identitySubject=identity_subject)
        return self.mapping

    async def get_customer(
        self, customer_id: str, context: RequestContext
    ) -> Mapping[str, Any]:
        self._record("getCustomer", customerId=customer_id)
        return self.customer

    async def list_events(self, context: RequestContext) -> Sequence[Mapping[str, Any]]:
        self._record("listEvents")
        return [self.event]

    async def get_event(
        self, event_id: str, context: RequestContext
    ) -> Mapping[str, Any]:
        self._record("getEvent", eventId=event_id)
        return self.event

    async def get_sale_eligibility(
        self, event_id: str, context: RequestContext
    ) -> Mapping[str, Any]:
        self._record("getSaleEligibility", eventId=event_id)
        return self.eligibility

    async def check_availability(
        self, event_id: str, seat_ids: Sequence[str], context: RequestContext
    ) -> Mapping[str, Any]:
        self._record("CheckAvailability", eventId=event_id, seatIds=list(seat_ids))
        return {"available": self.available}

    async def reserve_seats(
        self, payload: Mapping[str, Any], idempotency_key: str, context: RequestContext
    ) -> Mapping[str, Any]:
        self._record(
            "ReserveSeats", payload=dict(payload), idempotencyKey=idempotency_key
        )
        outcome = (
            self.reserve_outcomes.pop(0)
            if len(self.reserve_outcomes) > 1
            else self.reserve_outcomes[0]
        )
        if isinstance(outcome, Exception):
            raise outcome
        return outcome  # type: ignore[return-value]

    async def get_reservation(
        self, reservation_id: str, context: RequestContext
    ) -> Mapping[str, Any]:
        self._record("GetReservation", reservationId=reservation_id)
        return {"reservationId": reservation_id, "status": "ACTIVE"}

    async def confirm_seats(
        self,
        reservation_id: str,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> Mapping[str, Any]:
        self._record(
            "ConfirmSeats", reservationId=reservation_id, idempotencyKey=idempotency_key
        )
        if self.confirm_failure:
            raise DependencyFailure(
                "SEAT_CONFIRM_FAILED", "Seat confirmation failed.", 503, True
            )
        return {"reservationId": reservation_id, "status": "CONFIRMED"}

    async def release_seats(
        self,
        reservation_id: str,
        reason: str,
        idempotency_key: str,
        context: RequestContext,
    ) -> Mapping[str, Any]:
        self._record(
            "ReleaseSeats",
            reservationId=reservation_id,
            reason=reason,
            idempotencyKey=idempotency_key,
        )
        if self.release_failure:
            raise DependencyFailure("RELEASE_FAILED", "Seat release failed.", 503, True)
        return {"reservationId": reservation_id, "status": "RELEASED"}

    async def create_booking(
        self, payload: Mapping[str, Any], idempotency_key: str, context: RequestContext
    ) -> Mapping[str, Any]:
        self._record(
            "createBooking", payload=dict(payload), idempotencyKey=idempotency_key
        )
        return {"bookingId": "BK-1", "status": "PENDING"}

    async def get_booking(
        self, booking_id: str, context: RequestContext
    ) -> Mapping[str, Any]:
        self._record("getBooking", bookingId=booking_id)
        return self.booking

    async def decide_access(
        self, booking_id: str, context: RequestContext
    ) -> Mapping[str, Any]:
        self._record(
            "bookingAccessDecision",
            bookingId=booking_id,
            subject=context.principal.subject,
        )
        return {
            "allowed": self.access_allowed,
            "reasonCode": "OWNER" if self.access_allowed else "NOT_OWNER",
        }

    async def transition(
        self,
        operation: str,
        booking_id: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        context: RequestContext,
    ) -> Mapping[str, Any]:
        self._record(
            operation,
            bookingId=booking_id,
            payload=dict(payload),
            idempotencyKey=idempotency_key,
        )
        if operation in self.transition_failures:
            raise DependencyFailure(
                "BOOKING_TRANSITION_UNKNOWN",
                "Booking transition is uncertain.",
                503,
                True,
            )
        status_by_operation = {
            "bookingReservation": "SEAT_RESERVED",
            "bookingPaymentStarted": "PAYMENT_PROCESSING",
            "bookingPaymentResult": str(
                payload.get("paymentStatus", "PAYMENT_PROCESSING")
            ),
            "bookingTickets": "PAYMENT_PROCESSING",
            "bookingConfirm": "CONFIRMED",
            "bookingFail": "FAILED"
            if payload.get("compensationStatus") == "COMPLETED"
            else "COMPENSATION_PENDING",
            "bookingCancel": "CANCELLED"
            if payload.get("compensationStatus") == "COMPLETED"
            else "COMPENSATION_PENDING",
        }
        result = dict(self.booking)
        result.update(
            {
                "bookingId": booking_id,
                "status": status_by_operation.get(operation, self.booking["status"]),
            }
        )
        return result

    async def create_payment(
        self,
        booking_id: str,
        amount: Money,
        method_token: str,
        idempotency_key: str,
        context: RequestContext,
    ) -> Mapping[str, Any]:
        self._record(
            "createPayment",
            bookingId=booking_id,
            amount=amount.as_wire(),
            idempotencyKey=idempotency_key,
        )
        return {"paymentId": "PAY-1", "status": "CREATED"}

    async def get_payment(
        self, payment_id: str, context: RequestContext
    ) -> Mapping[str, Any]:
        self._record("getPayment", paymentId=payment_id)
        return self.payment

    async def command(
        self,
        operation: str,
        payment_id: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        context: RequestContext,
    ) -> Mapping[str, Any]:
        self._record(
            operation,
            paymentId=payment_id,
            payload=dict(payload),
            idempotencyKey=idempotency_key,
        )
        outcome = self.payment_outcomes[operation]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome  # type: ignore[return-value]

    async def issue_tickets(
        self, payload: Mapping[str, Any], idempotency_key: str, context: RequestContext
    ) -> Sequence[Mapping[str, Any]]:
        self._record(
            "issueTickets", payload=dict(payload), idempotencyKey=idempotency_key
        )
        if self.ticket_failure:
            raise DependencyFailure(
                "TICKET_ISSUE_FAILED", "Ticket issue failed.", 503, True
            )
        return [{"ticketId": "TKT-1", "status": "ISSUED"}]

    async def list_booking_tickets(
        self, booking_id: str, context: RequestContext
    ) -> Sequence[Mapping[str, Any]]:
        self._record("listBookingTickets", bookingId=booking_id)
        return self.booking_tickets

    async def cancel_ticket(
        self, ticket_id: str, idempotency_key: str, context: RequestContext
    ) -> Mapping[str, Any]:
        self._record("cancelTicket", ticketId=ticket_id, idempotencyKey=idempotency_key)
        return {"ticketId": ticket_id, "status": "CANCELLED"}

    async def publish(
        self, payload: Mapping[str, Any], message_id: str, context: RequestContext
    ) -> None:
        self._record("publish", payload=dict(payload), messageId=message_id)
