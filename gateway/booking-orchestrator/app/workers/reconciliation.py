from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any
from uuid import uuid4

from app.domain.idempotency import step_key
from app.domain.models import (
    Money,
    OutboxItem,
    PaymentOutcome,
    Principal,
    RequestContext,
    WorkflowEvidence,
    WorkflowPhase,
)
from app.ports.providers import BookingPort, PaymentPort, SeatPort, TicketPort
from app.ports.repositories import (
    Clock,
    OutboxRepository,
    ReconciliationRepository,
    WorkflowRepository,
)

# Payment outcomes that end reconciliation without a ticket.
TERMINAL_UNSUCCESSFUL_PAYMENTS = frozenset({PaymentOutcome.FAILED, PaymentOutcome.DECLINED, PaymentOutcome.CANCELLED})
# Reservation states that still entitle the booking to its seats.
HOLDABLE_RESERVATION_STATES = frozenset({"ACTIVE", "CONFIRMED"})
REFUNDED_PAYMENT_STATES = frozenset({"REFUNDED", "PARTIALLY_REFUNDED"})


class ReconciliationWorker:
    def __init__(
        self,
        jobs: ReconciliationRepository,
        workflows: WorkflowRepository,
        seats: SeatPort,
        bookings: BookingPort,
        payments: PaymentPort,
        tickets: TicketPort,
        outbox: OutboxRepository,
        clock: Clock,
        backoff_seconds: int = 15,
        max_backoff_seconds: int = 300,
        lease_seconds: int = 60,
    ) -> None:
        (
            self.jobs,
            self.workflows,
            self.seats,
            self.bookings,
            self.payments,
            self.tickets,
            self.clock,
        ) = (
            jobs,
            workflows,
            seats,
            bookings,
            payments,
            tickets,
            clock,
        )
        self.outbox = outbox
        self.backoff_seconds = backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.lease_seconds = lease_seconds

    async def run_once(self, limit: int = 20) -> int:
        now = self.clock.now()
        jobs = await self.jobs.due_jobs(now, limit, now + timedelta(seconds=self.lease_seconds))
        for job in jobs:
            context = RequestContext(
                "recovery-" + str(job["jobId"]),
                None,
                monotonic() + 20,
                Principal("booking-orchestrator", ("SERVICE",)),
            )
            try:
                workflow = await self.workflows.get(str(job["workflowId"]))
                if workflow is None:
                    await self.jobs.complete_job(str(job["jobId"]))
                    continue
                if job["kind"] == "RESERVE_REPLAY":
                    reservation = await self.seats.reserve_seats(job["payload"]["request"], str(job["idempotencyKey"]), context)
                    workflow.reservation_id = str(reservation["reservationId"])
                    workflow.reservation_version = int(reservation.get("resourceVersion", 1))
                    workflow.phase = WorkflowPhase.SEAT_RESERVED
                    await self.bookings.transition(
                        "bookingReservation",
                        workflow.booking_id or "",
                        {
                            "reservationId": workflow.reservation_id,
                            "evidence": {
                                "providerReference": workflow.reservation_id,
                                "reservationExpiresAt": reservation["expiresAt"],
                            },
                        },
                        step_key(workflow.workflow_id, "bookingReservation"),
                        context,
                    )
                    await self.workflows.save(workflow)
                    await self.jobs.complete_job(str(job["jobId"]))
                elif job["kind"] == "PAYMENT_UNKNOWN":
                    await self._reconcile_payment(job, workflow, context)
                elif job["kind"] == "AFTER_CAPTURE_COMPENSATION":
                    await self._after_capture(job, workflow, context)
                elif job["kind"] == "CANCEL_COMPENSATION":
                    await self._complete_cancellation(job, workflow, context)
                else:
                    await self.jobs.reschedule_job(
                        str(job["jobId"]),
                        self.clock.now() + timedelta(seconds=60),
                        {"outcome": "UNSUPPORTED_KIND"},
                    )
            except Exception:  # noqa: BLE001 -- durable retry records every reconciliation failure
                attempts = int(job.get("attempts", 0)) + 1
                await self.jobs.reschedule_job(
                    str(job["jobId"]),
                    self.clock.now() + timedelta(seconds=min(300, 2**attempts)),
                    {"outcome": "RETRY"},
                )
        return len(jobs)

    async def _reconcile_payment(
        self,
        job: Mapping[str, Any],
        workflow: WorkflowEvidence,
        context: RequestContext,
    ) -> None:
        """Ask Payment for the authoritative outcome and act on it, never invent one."""
        payment_id = await self._resolve_payment_id(job, workflow, context)
        if payment_id is None:
            await self._retry_or_abandon(job, "PAYMENT_NOT_RESOLVED")
            return
        payment = await self.payments.command(
            "reconcilePayment",
            payment_id,
            {},
            str(job["idempotencyKey"]),
            context,
        )
        status = PaymentOutcome(str(payment.get("status", "UNKNOWN")))
        workflow.payment_status = status
        if status is PaymentOutcome.CAPTURED:
            await self._settle_captured_payment(job, workflow, context)
        elif status in TERMINAL_UNSUCCESSFUL_PAYMENTS:
            await self._settle_failed_payment(job, workflow, context)
        else:
            # Still not authoritative: back off, but never past the deadline.
            await self._retry_or_abandon(job, status.value)

    async def _resolve_payment_id(
        self,
        job: Mapping[str, Any],
        workflow: WorkflowEvidence,
        context: RequestContext,
    ) -> str | None:
        """Recover the payment identifier when createPayment itself was ambiguous.

        Replaying createPayment with the original idempotency key is safe: Payment
        Service returns the stored response instead of charging again.
        """
        payment_id = workflow.payment_id or job["payload"].get("paymentId")
        if payment_id:
            return str(payment_id)
        create_key = job["payload"].get("createIdempotencyKey")
        amount = job["payload"].get("amount")
        booking_id = job["payload"].get("bookingId")
        if not create_key or not amount or not booking_id:
            return None
        replay = await self.payments.create_payment(
            str(booking_id),
            Money(int(amount["amountMinor"]), str(amount["currency"])),
            str(job["payload"]["methodToken"]),
            str(create_key),
            context,
        )
        workflow.payment_id = str(replay["paymentId"])
        await self.workflows.save(workflow)
        return workflow.payment_id

    async def _settle_captured_payment(
        self,
        job: Mapping[str, Any],
        workflow: WorkflowEvidence,
        context: RequestContext,
    ) -> None:
        await self.bookings.transition(
            "bookingPaymentResult",
            workflow.booking_id or "",
            {
                "paymentId": workflow.payment_id,
                "paymentStatus": PaymentOutcome.CAPTURED.value,
                "evidence": {
                    "providerReference": workflow.payment_id,
                    "verifiedAt": self._verified_at(),
                },
            },
            step_key(workflow.workflow_id, "bookingPaymentResult"),
            context,
        )
        if not await self._reservation_still_holds(workflow, context):
            # Money was taken but the seat is gone: refund instead of confirming.
            await self._refund_unfulfillable_payment(job, workflow, context)
            return
        await self._complete_after_capture(workflow, context)
        await self.jobs.complete_job(str(job["jobId"]))

    async def _reservation_still_holds(self, workflow: WorkflowEvidence, context: RequestContext) -> bool:
        if not workflow.reservation_id:
            return False
        reservation = await self.seats.get_reservation(workflow.reservation_id, context)
        return str(reservation.get("status")) in HOLDABLE_RESERVATION_STATES

    async def _refund_unfulfillable_payment(
        self,
        job: Mapping[str, Any],
        workflow: WorkflowEvidence,
        context: RequestContext,
    ) -> None:
        """Captured payment without a usable seat: refund, never issue or confirm."""
        refund = await self.payments.command(
            "createRefund",
            workflow.payment_id or "",
            {
                "amount": workflow.total.as_wire() if workflow.total else None,
                "reason": "RESERVATION_LOST",
            },
            step_key(workflow.workflow_id, "refund:reservationLost"),
            context,
        )
        refunded = str(refund.get("status")) in REFUNDED_PAYMENT_STATES
        await self.bookings.transition(
            "bookingFail",
            workflow.booking_id or "",
            {
                "reasonCode": "RESERVATION_LOST_AFTER_CAPTURE",
                "compensationStatus": "COMPLETED" if refunded else "PENDING",
                "evidence": {
                    "compensationCompleted": refunded,
                    "refundStatus": str(refund.get("status", "UNKNOWN")),
                    "verifiedAt": self._verified_at(),
                },
            },
            step_key(workflow.workflow_id, "bookingFail:reservationLost"),
            context,
        )
        workflow.phase = WorkflowPhase.FAILED if refunded else WorkflowPhase.COMPENSATION_PENDING
        await self.workflows.save(workflow)
        if refunded:
            await self.jobs.complete_job(str(job["jobId"]))
        else:
            await self._retry_or_abandon(job, "REFUND_PENDING")

    async def _settle_failed_payment(
        self,
        job: Mapping[str, Any],
        workflow: WorkflowEvidence,
        context: RequestContext,
    ) -> None:
        released = False
        if workflow.reservation_id:
            response = await self.seats.release_seats(
                workflow.reservation_id,
                "PAYMENT_FAILED",
                step_key(workflow.workflow_id, "reconciledRelease"),
                context,
            )
            released = response.get("status") == "RELEASED"
        await self.bookings.transition(
            "bookingFail",
            workflow.booking_id or "",
            {
                "reasonCode": "PAYMENT_FAILED",
                "compensationStatus": "COMPLETED" if released else "PENDING",
                "evidence": {
                    "compensationCompleted": released,
                    "verifiedAt": self._verified_at(),
                },
            },
            step_key(workflow.workflow_id, "bookingFail:reconciled"),
            context,
        )
        workflow.phase = WorkflowPhase.FAILED if released else WorkflowPhase.COMPENSATION_PENDING
        await self.workflows.save(workflow)
        await self.jobs.complete_job(str(job["jobId"]))

    async def _retry_or_abandon(self, job: Mapping[str, Any], status: str) -> None:
        """Back off within the deadline; past it, stop guessing and leave evidence."""
        now = self.clock.now()
        deadline = job.get("deadlineAt")
        if isinstance(deadline, datetime) and now >= deadline:
            await self.jobs.abandon_job(
                str(job["jobId"]),
                {
                    "status": status,
                    "outcome": "DEADLINE_EXCEEDED",
                    "abandonedAt": now.isoformat(),
                },
            )
            return
        attempts = int(job.get("attempts", 0)) + 1
        delay = min(self.max_backoff_seconds, self.backoff_seconds * (2 ** (attempts - 1)))
        await self.jobs.reschedule_job(
            str(job["jobId"]),
            now + timedelta(seconds=delay),
            {"status": status},
        )

    async def _after_capture(
        self,
        job: Mapping[str, Any],
        workflow: WorkflowEvidence,
        context: RequestContext,
    ) -> None:
        payload = job["payload"]
        authoritative = await self.bookings.get_booking(workflow.booking_id or "", context)
        if authoritative.get("status") == "CONFIRMED":
            workflow.phase = WorkflowPhase.CONFIRMED
            await self.outbox.commit_with_outbox(
                workflow,
                [
                    OutboxItem(
                        str(uuid4()),
                        "notification",
                        "booking.confirmed",
                        {
                            "bookingId": workflow.booking_id,
                            "status": "CONFIRMED",
                            "ticketIds": workflow.ticket_ids,
                        },
                        context.correlation_id,
                    ),
                    OutboxItem(
                        str(uuid4()),
                        "realtime",
                        "booking.status",
                        {
                            "bookingId": workflow.booking_id,
                            "status": "CONFIRMED",
                            "sequence": workflow.version,
                        },
                        context.correlation_id,
                    ),
                ],
            )
            await self.jobs.complete_job(str(job["jobId"]))
            return
        for ticket_id in payload.get("ticketIds", []):
            await self.tickets.cancel_ticket(
                str(ticket_id),
                step_key(workflow.workflow_id, f"cancel:{ticket_id}"),
                context,
            )
        if payload.get("paymentId"):
            payment = await self.payments.get_payment(str(payload["paymentId"]), context)
            await self.payments.command(
                "createRefund",
                str(payload["paymentId"]),
                {
                    "amount": payment.get("amount") or (workflow.total.as_wire() if workflow.total else None),
                    "reason": "AFTER_CAPTURE_FAILURE",
                },
                step_key(workflow.workflow_id, "refund"),
                context,
            )
        if payload.get("reservationId"):
            await self.seats.release_seats(
                str(payload["reservationId"]),
                "AFTER_CAPTURE_FAILURE",
                step_key(workflow.workflow_id, "release"),
                context,
            )
        await self.bookings.transition(
            "bookingFail",
            workflow.booking_id or "",
            {
                "reasonCode": "AFTER_CAPTURE_FAILURE",
                "compensationStatus": "COMPLETED",
                "evidence": {
                    "compensationCompleted": True,
                    "verifiedAt": self._verified_at(),
                },
            },
            step_key(workflow.workflow_id, "bookingFail:compensated"),
            context,
        )
        workflow.phase = WorkflowPhase.FAILED
        await self.workflows.save(workflow)
        await self.jobs.complete_job(str(job["jobId"]))

    async def _complete_cancellation(
        self,
        job: Mapping[str, Any],
        workflow: WorkflowEvidence,
        context: RequestContext,
    ) -> None:
        payload = job["payload"]
        for ticket_id in payload.get("ticketIds", []):
            await self.tickets.cancel_ticket(
                str(ticket_id),
                step_key(workflow.workflow_id, f"cancelTicket:{ticket_id}"),
                context,
            )
        payment_id = payload.get("paymentId")
        if payment_id:
            payment = await self.payments.get_payment(str(payment_id), context)
            status = PaymentOutcome(str(payment.get("status", "UNKNOWN")))
            if status == PaymentOutcome.UNKNOWN:
                raise RuntimeError("cancellation payment outcome remains unknown")
            if status == PaymentOutcome.CAPTURED:
                await self.payments.command(
                    "createRefund",
                    str(payment_id),
                    {"amount": payload.get("total"), "reason": "BOOKING_CANCELLED"},
                    step_key(workflow.workflow_id, "createRefund"),
                    context,
                )
            elif status in {PaymentOutcome.CREATED, PaymentOutcome.AUTHORIZED}:
                await self.payments.command(
                    "cancelPayment",
                    str(payment_id),
                    {},
                    step_key(workflow.workflow_id, "cancelPayment"),
                    context,
                )
        reservation_id = payload.get("reservationId")
        if reservation_id:
            reservation = await self.seats.get_reservation(str(reservation_id), context)
            if reservation.get("status") == "ACTIVE":
                await self.seats.release_seats(
                    str(reservation_id),
                    "BOOKING_CANCELLED",
                    step_key(workflow.workflow_id, "cancelReleaseSeats"),
                    context,
                )
        await self.bookings.transition(
            "bookingCancel",
            str(payload["bookingId"]),
            {
                "reasonCode": "USER_REQUEST",
                "compensationStatus": "COMPLETED",
                "evidence": {
                    "compensationCompleted": True,
                    "verifiedAt": self._verified_at(),
                },
            },
            step_key(workflow.workflow_id, "bookingCancel:reconciled"),
            context,
        )
        workflow.phase = WorkflowPhase.CANCELLED
        await self.workflows.save(workflow)
        await self.jobs.complete_job(str(job["jobId"]))

    async def _complete_after_capture(self, workflow: WorkflowEvidence, context: RequestContext) -> None:
        event_id = str(workflow.evidence["eventId"])
        seats = [str(value) for value in workflow.evidence["seatIds"]]
        issued = await self.tickets.issue_tickets(
            {
                "bookingId": workflow.booking_id,
                "eventId": event_id,
                "customerId": workflow.customer_id,
                "items": [{"seatId": value} for value in seats],
            },
            step_key(workflow.workflow_id, "issueTickets"),
            context,
        )
        workflow.ticket_ids = [str(ticket["ticketId"]) for ticket in issued]
        await self.bookings.transition(
            "bookingTickets",
            workflow.booking_id or "",
            {
                "ticketIds": workflow.ticket_ids,
                "evidence": {
                    "providerReference": workflow.ticket_ids[0],
                    "ticketsIssued": True,
                },
            },
            step_key(workflow.workflow_id, "bookingTickets"),
            context,
        )
        confirmed = await self.seats.confirm_seats(
            workflow.reservation_id or "",
            workflow.reservation_version or 1,
            step_key(workflow.workflow_id, "ConfirmSeats"),
            context,
        )
        await self.bookings.transition(
            "bookingConfirm",
            workflow.booking_id or "",
            {
                "reservationId": workflow.reservation_id,
                "paymentId": workflow.payment_id,
                "paymentStatus": "CAPTURED",
                "ticketIds": workflow.ticket_ids,
                "evidence": {
                    "paymentCaptured": True,
                    "seatConfirmed": confirmed.get("status") == "CONFIRMED",
                    "ticketsIssued": True,
                    "verifiedAt": self._verified_at(),
                },
            },
            step_key(workflow.workflow_id, "bookingConfirm"),
            context,
        )
        workflow.phase = WorkflowPhase.CONFIRMED
        await self.outbox.commit_with_outbox(
            workflow,
            [
                OutboxItem(
                    str(uuid4()),
                    "notification",
                    "booking.confirmed",
                    {
                        "bookingId": workflow.booking_id,
                        "status": "CONFIRMED",
                        "ticketIds": workflow.ticket_ids,
                    },
                    context.correlation_id,
                ),
                OutboxItem(
                    str(uuid4()),
                    "realtime",
                    "booking.status",
                    {
                        "bookingId": workflow.booking_id,
                        "status": "CONFIRMED",
                        "sequence": workflow.version,
                    },
                    context.correlation_id,
                ),
            ],
        )

    @staticmethod
    def _verified_at() -> str:
        return datetime.now(UTC).isoformat()


class RecoveryScanner:
    def __init__(self, workflows: WorkflowRepository, jobs: ReconciliationRepository) -> None:
        self.workflows, self.jobs = workflows, jobs

    async def recover(self) -> int:
        workflows = await self.workflows.recoverable()
        for workflow in workflows:
            if workflow.payment_status == PaymentOutcome.UNKNOWN:
                await self.jobs.schedule(
                    workflow.workflow_id,
                    "PAYMENT_UNKNOWN",
                    {
                        "paymentId": workflow.payment_id,
                        "bookingId": workflow.booking_id,
                    },
                    step_key(workflow.workflow_id, "reconcilePayment"),
                )
        return len(workflows)
