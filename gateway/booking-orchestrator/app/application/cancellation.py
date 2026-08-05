from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from app.domain.errors import AccessDenied, BusinessFault
from app.domain.idempotency import normalized_request_hash, step_key
from app.domain.models import (
    Money,
    OperationResult,
    PaymentOutcome,
    RequestContext,
    WorkflowEvidence,
    WorkflowPhase,
)
from app.ports.providers import BookingPort, PaymentPort, SeatPort, TicketPort
from app.ports.repositories import (
    Clock,
    IdempotencyRepository,
    ReconciliationRepository,
    WorkflowRepository,
)


class CancellationSaga:
    def __init__(
        self,
        bookings: BookingPort,
        payments: PaymentPort,
        tickets: TicketPort,
        seats: SeatPort,
        workflows: WorkflowRepository,
        idempotency: IdempotencyRepository,
        reconciliation: ReconciliationRepository,
        clock: Clock,
    ) -> None:
        self.bookings, self.payments, self.tickets, self.seats = (
            bookings,
            payments,
            tickets,
            seats,
        )
        self.workflows, self.idempotency, self.reconciliation, self.clock = (
            workflows,
            idempotency,
            reconciliation,
            clock,
        )

    async def execute(
        self,
        booking_id: str,
        idempotency_key: str,
        context: RequestContext,
        expected_version: int | None = None,
    ) -> OperationResult:
        request_hash = normalized_request_hash({"bookingId": booking_id})
        claim = await self.idempotency.claim(
            "publicCancelBooking",
            context.principal.subject,
            idempotency_key,
            request_hash,
        )
        if claim.kind == "REPLAY" and claim.recorded_result:
            return claim.recorded_result
        if claim.kind == "IN_PROGRESS":
            existing = await self.workflows.get(claim.workflow_id)
            if existing is None:
                raise AccessDenied(message="Cancellation workflow state is unavailable.")
            return self._result({"bookingId": booking_id}, context, existing.phase.value)
        context = replace(context, workflow_id=claim.workflow_id)
        decision = await self.bookings.decide_access(booking_id, context)
        if not decision.get("allowed"):
            raise AccessDenied()
        booking = await self.bookings.get_booking(booking_id, context)
        if expected_version is not None and booking.get("resourceVersion") != expected_version:
            raise BusinessFault(
                "PRECONDITION_FAILED",
                "The booking resource version does not match If-Match.",
                412,
                False,
                {"currentVersion": booking.get("resourceVersion")},
            )
        if booking.get("status") == "CANCELLED":
            result = self._result(booking, context, "CANCELLED")
            await self.idempotency.complete(
                "publicCancelBooking",
                context.principal.subject,
                idempotency_key,
                result,
            )
            return result

        workflow = WorkflowEvidence(
            claim.workflow_id,
            "publicCancelBooking",
            context.principal.subject,
            request_hash,
            context.correlation_id,
            WorkflowPhase.COMPENSATION_PENDING,
            booking_id=booking_id,
        )
        await self.workflows.create(workflow)
        complete = True
        tickets = await self.tickets.list_booking_tickets(booking_id, context)
        for ticket in tickets:
            if ticket.get("status") == "ISSUED":
                try:
                    await self.tickets.cancel_ticket(
                        str(ticket["ticketId"]),
                        step_key(workflow.workflow_id, f"cancelTicket:{ticket['ticketId']}"),
                        context,
                    )
                except Exception:  # noqa: BLE001 -- all adapter failures become pending compensation evidence
                    complete = False

        payment_id = booking.get("paymentId")
        if payment_id:
            payment = await self.payments.get_payment(str(payment_id), context)
            payment_status = PaymentOutcome(str(payment.get("status", "UNKNOWN")))
            if payment_status == PaymentOutcome.UNKNOWN:
                complete = False
            elif payment_status == PaymentOutcome.CAPTURED:
                try:
                    await self.payments.command(
                        "createRefund",
                        str(payment_id),
                        {"amount": booking["total"], "reason": "BOOKING_CANCELLED"},
                        step_key(workflow.workflow_id, "createRefund"),
                        context,
                    )
                except Exception:  # noqa: BLE001 -- all adapter failures become pending compensation evidence
                    complete = False
            elif payment_status in {PaymentOutcome.CREATED, PaymentOutcome.AUTHORIZED}:
                try:
                    await self.payments.command(
                        "cancelPayment",
                        str(payment_id),
                        {},
                        step_key(workflow.workflow_id, "cancelPayment"),
                        context,
                    )
                except Exception:  # noqa: BLE001 -- all adapter failures become pending compensation evidence
                    complete = False

        reservation_id = booking.get("reservationId")
        if reservation_id:
            try:
                reservation = await self.seats.get_reservation(str(reservation_id), context)
                if reservation.get("status") == "ACTIVE":
                    await self.seats.release_seats(
                        str(reservation_id),
                        "BOOKING_CANCELLED",
                        step_key(workflow.workflow_id, "cancelReleaseSeats"),
                        context,
                    )
            except Exception:  # noqa: BLE001 -- all adapter failures become pending compensation evidence
                complete = False

        compensation_status = "COMPLETED" if complete else "PENDING"
        updated = await self.bookings.transition(
            "bookingCancel",
            booking_id,
            {
                "reasonCode": "USER_REQUEST",
                "compensationStatus": compensation_status,
                "evidence": {
                    "compensationCompleted": complete,
                    "verifiedAt": datetime.now(UTC).isoformat(),
                },
            },
            step_key(workflow.workflow_id, "bookingCancel"),
            context,
        )
        final_status = "CANCELLED" if complete else "COMPENSATION_PENDING"
        workflow.phase = WorkflowPhase(final_status)
        await self.workflows.save(workflow)
        if not complete:
            await self.reconciliation.schedule(
                workflow.workflow_id,
                "CANCEL_COMPENSATION",
                {
                    "bookingId": booking_id,
                    "paymentId": payment_id,
                    "reservationId": reservation_id,
                    "ticketIds": [str(ticket["ticketId"]) for ticket in tickets if ticket.get("status") == "ISSUED"],
                    "total": booking.get("total"),
                },
                step_key(workflow.workflow_id, "cancelCompensation"),
            )
        result = self._result(updated or booking, context, final_status)
        await self.idempotency.complete("publicCancelBooking", context.principal.subject, idempotency_key, result)
        return result

    @staticmethod
    def _result(booking: Mapping[str, Any], context: RequestContext, status: str) -> OperationResult:
        total = booking.get("total", Money(0, "VND").as_wire())
        return OperationResult(
            200,
            {
                "bookingId": booking.get("bookingId"),
                "status": status,
                "total": total,
                "reservationId": booking.get("reservationId"),
                "paymentId": booking.get("paymentId"),
                "ticketIds": booking.get("ticketIds", []),
                "correlationId": context.correlation_id,
            },
        )
