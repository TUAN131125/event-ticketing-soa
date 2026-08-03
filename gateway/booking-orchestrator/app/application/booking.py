from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any
from uuid import uuid4

from app.domain.errors import AmbiguousOutcome, BusinessFault, DependencyFailure
from app.domain.idempotency import (
    normalized_request_hash,
    request_fingerprint,
    step_key,
)
from app.domain.models import (
    Money,
    OperationResult,
    OutboxItem,
    PaymentOutcome,
    PlaceBookingCommand,
    RequestContext,
    WorkflowEvidence,
    WorkflowPhase,
)
from app.ports.providers import (
    BookingPort,
    CustomerPort,
    EventPort,
    PaymentPort,
    SeatPort,
    TicketPort,
)
from app.ports.repositories import (
    Clock,
    IdempotencyRepository,
    OutboxRepository,
    ReconciliationRepository,
    TraceRepository,
    WorkflowRepository,
)


class BookingSaga:
    def __init__(
        self,
        customer: CustomerPort,
        events: EventPort,
        seats: SeatPort,
        bookings: BookingPort,
        payments: PaymentPort,
        tickets: TicketPort,
        workflows: WorkflowRepository,
        idempotency: IdempotencyRepository,
        traces: TraceRepository,
        outbox: OutboxRepository,
        reconciliation: ReconciliationRepository,
        clock: Clock,
        reserve_replay_limit: int = 2,
    ) -> None:
        self.customer = customer
        self.events = events
        self.seats = seats
        self.bookings = bookings
        self.payments = payments
        self.tickets = tickets
        self.workflows = workflows
        self.idempotency = idempotency
        self.traces = traces
        self.outbox = outbox
        self.reconciliation = reconciliation
        self.clock = clock
        self.reserve_replay_limit = max(1, reserve_replay_limit)

    async def execute(self, command: PlaceBookingCommand, context: RequestContext) -> OperationResult:
        request_payload = {
            "customerId": command.browser_customer_id,
            "eventId": command.event_id,
            "seatIds": list(command.seat_ids),
            "paymentMethodToken": command.payment_method_token,
        }
        request_hash = normalized_request_hash(request_payload)
        claim = await self.idempotency.claim(
            "placeBooking",
            context.principal.subject,
            command.idempotency_key,
            request_hash,
        )
        if claim.kind == "REPLAY" and claim.recorded_result is not None:
            return claim.recorded_result
        if claim.kind == "IN_PROGRESS":
            existing = await self.workflows.get(claim.workflow_id)
            if existing is None:
                raise DependencyFailure(
                    "IDEMPOTENCY_STATE_UNAVAILABLE",
                    "The existing workflow cannot currently be resumed.",
                    503,
                    True,
                )
            return self._booking_result(existing, existing.phase, 202)

        context = replace(context, workflow_id=claim.workflow_id)

        workflow = WorkflowEvidence(
            workflow_id=claim.workflow_id,
            operation="placeBooking",
            subject=context.principal.subject,
            request_hash=request_hash,
            correlation_id=context.correlation_id,
            phase=WorkflowPhase.PENDING,
        )
        await self.workflows.create(workflow)

        mapping = await self.customer.resolve_mapping(context.principal.subject, context)
        if mapping.get("status") != "ACTIVE" or not mapping.get("customerId"):
            raise BusinessFault(
                "IDENTITY_NOT_MAPPED",
                "Customer identity mapping is unavailable.",
                403,
                False,
            )
        workflow.customer_id = str(mapping["customerId"])
        customer = await self.customer.get_customer(workflow.customer_id, context)
        if customer.get("status") != "ACTIVE":
            raise BusinessFault("CUSTOMER_INACTIVE", "Customer is inactive.", 403, False)

        event = await self.events.get_event(command.event_id, context)
        eligibility = await self.events.get_sale_eligibility(command.event_id, context)
        if not eligibility.get("eligible") or event.get("status") != "ON_SALE":
            raise BusinessFault("EVENT_NOT_ON_SALE", "Event is not available for sale.", 409, False)
        ticket_type, amount = self._authoritative_selection(event, eligibility, len(command.seat_ids))
        workflow.total = amount
        workflow.evidence.update(
            {
                "eventId": command.event_id,
                "seatIds": list(command.seat_ids),
                "ticketTypeCode": ticket_type,
            }
        )

        availability = await self.seats.check_availability(command.event_id, command.seat_ids, context)
        if not availability.get("available"):
            raise BusinessFault("SEAT_UNAVAILABLE", "One or more seats are unavailable.", 409, False)

        items = [
            {
                "seatId": seat_id,
                "ticketTypeCode": ticket_type,
                "unitPrice": self._unit_price(event, ticket_type),
            }
            for seat_id in command.seat_ids
        ]
        created = await self.bookings.create_booking(
            {
                "customerId": workflow.customer_id,
                "eventId": command.event_id,
                "items": items,
            },
            step_key(workflow.workflow_id, "createBooking"),
            context,
        )
        workflow.booking_id = str(created["bookingId"])
        await self._save_step(
            workflow,
            "createBooking",
            "booking-service",
            "PENDING",
            {"bookingId": workflow.booking_id},
        )

        reserve_payload = {
            "bookingId": workflow.booking_id,
            "eventId": command.event_id,
            "seatIds": [{"seatId": seat_id, "ticketTypeCode": ticket_type} for seat_id in command.seat_ids],
            "ttlSeconds": 600,
            "requestContext": {
                "correlationId": context.correlation_id,
                "callerService": "booking-orchestrator",
                "schemaVersion": 1,
            },
        }
        reserve_key = step_key(workflow.workflow_id, "ReserveSeats")
        reservation = await self._reserve_with_same_request(workflow, reserve_payload, reserve_key, context)
        if reservation is None:
            result = self._booking_result(workflow, WorkflowPhase.PENDING)
            await self._complete(command, context, result)
            return result

        workflow.reservation_id = str(reservation["reservationId"])
        workflow.reservation_version = int(reservation.get("resourceVersion", 1))
        workflow.phase = WorkflowPhase.SEAT_RESERVED
        await self._save_step(
            workflow,
            "ReserveSeats",
            "seat-inventory-service",
            "ACTIVE",
            {"reservationId": workflow.reservation_id},
        )

        try:
            await self.bookings.transition(
                "bookingReservation",
                workflow.booking_id,
                {
                    "reservationId": workflow.reservation_id,
                    "evidence": {"seatStatus": "ACTIVE"},
                },
                step_key(workflow.workflow_id, "bookingReservation"),
                context,
            )
        except Exception:  # noqa: BLE001 -- any release failure means durable compensation remains pending
            released = await self._release(workflow, "BOOKING_RESERVATION_EVIDENCE_FAILED", context)
            await self._fail_booking(workflow, "RESERVATION_EVIDENCE_FAILED", released, context)
            raise

        payment = await self.payments.create_payment(
            workflow.booking_id,
            amount,
            command.payment_method_token,
            step_key(workflow.workflow_id, "createPayment"),
            context,
        )
        workflow.payment_id = str(payment["paymentId"])
        workflow.phase = WorkflowPhase.PAYMENT_PROCESSING
        await self.bookings.transition(
            "bookingPaymentStarted",
            workflow.booking_id,
            {"paymentId": workflow.payment_id},
            step_key(workflow.workflow_id, "bookingPaymentStarted"),
            context,
        )

        authorization = await self._payment_command("authorizePayment", workflow, context)
        if authorization in {PaymentOutcome.FAILED, PaymentOutcome.DECLINED}:
            return await self._payment_failed(workflow, command, context)
        if authorization == PaymentOutcome.UNKNOWN:
            return await self._payment_unknown(workflow, command, context)

        capture = await self._payment_command("capturePayment", workflow, context)
        workflow.payment_status = capture
        await self.bookings.transition(
            "bookingPaymentResult",
            workflow.booking_id,
            {
                "paymentId": workflow.payment_id,
                "paymentStatus": capture.value,
                "evidence": {"verified": True},
            },
            step_key(workflow.workflow_id, "bookingPaymentResult"),
            context,
        )
        if capture in {PaymentOutcome.FAILED, PaymentOutcome.DECLINED}:
            return await self._payment_failed(workflow, command, context)
        if capture != PaymentOutcome.CAPTURED:
            return await self._payment_unknown(workflow, command, context)

        try:
            issued = await self.tickets.issue_tickets(
                {
                    "bookingId": workflow.booking_id,
                    "eventId": command.event_id,
                    "customerId": workflow.customer_id,
                    "items": [{"seatId": value} for value in command.seat_ids],
                },
                step_key(workflow.workflow_id, "issueTickets"),
                context,
            )
            workflow.ticket_ids = [str(ticket["ticketId"]) for ticket in issued]
            await self.bookings.transition(
                "bookingTickets",
                workflow.booking_id,
                {
                    "ticketIds": workflow.ticket_ids,
                    "evidence": {"ticketStatus": "ISSUED"},
                },
                step_key(workflow.workflow_id, "bookingTickets"),
                context,
            )
            confirmed_seat = await self.seats.confirm_seats(
                workflow.reservation_id,
                workflow.reservation_version or 1,
                step_key(workflow.workflow_id, "ConfirmSeats"),
                context,
            )
            await self.bookings.transition(
                "bookingConfirm",
                workflow.booking_id,
                {
                    "reservationId": workflow.reservation_id,
                    "paymentId": workflow.payment_id,
                    "paymentStatus": "CAPTURED",
                    "ticketIds": workflow.ticket_ids,
                    "evidence": {
                        "paymentCaptured": True,
                        "seatConfirmed": confirmed_seat.get("status") == "CONFIRMED",
                        "ticketsIssued": True,
                    },
                },
                step_key(workflow.workflow_id, "bookingConfirm"),
                context,
            )
        except Exception as exc:
            workflow.phase = WorkflowPhase.COMPENSATION_PENDING
            await self.workflows.save(workflow)
            await self.reconciliation.schedule(
                workflow.workflow_id,
                "AFTER_CAPTURE_COMPENSATION",
                {
                    "bookingId": workflow.booking_id,
                    "paymentId": workflow.payment_id,
                    "reservationId": workflow.reservation_id,
                    "ticketIds": workflow.ticket_ids,
                },
                step_key(workflow.workflow_id, "afterCaptureCompensation"),
            )
            await self._fail_booking(workflow, "AFTER_CAPTURE_FAILURE", False, context)
            raise DependencyFailure("AFTER_CAPTURE_FAILURE", "Booking compensation is pending.", 503, True) from exc

        workflow.phase = WorkflowPhase.CONFIRMED
        await self.outbox.commit_with_outbox(
            workflow,
            [
                OutboxItem(
                    str(uuid4()),
                    "notification",
                    "booking.confirmed",
                    self._event_payload(workflow),
                    context.correlation_id,
                ),
                OutboxItem(
                    str(uuid4()),
                    "realtime",
                    "booking.status",
                    self._realtime_payload(workflow),
                    context.correlation_id,
                ),
            ],
        )
        result = self._booking_result(workflow, WorkflowPhase.CONFIRMED, 201)
        await self._complete(command, context, result)
        return result

    async def _reserve_with_same_request(
        self,
        workflow: WorkflowEvidence,
        payload: Mapping[str, Any],
        idempotency_key: str,
        context: RequestContext,
    ) -> Mapping[str, Any] | None:
        fingerprint = request_fingerprint(payload)
        for attempt in range(1, self.reserve_replay_limit + 1):
            if self.clock.monotonic() >= context.deadline_monotonic:
                break
            try:
                result = await self.seats.reserve_seats(payload, idempotency_key, context)
                if request_fingerprint(payload) != fingerprint:
                    raise RuntimeError("ReserveSeats replay payload changed")
                return result
            except AmbiguousOutcome:
                await self.workflows.record_step(
                    workflow.workflow_id,
                    "ReserveSeats",
                    "seat-inventory-service",
                    "UNKNOWN",
                    {"attempt": attempt, "requestFingerprint": fingerprint},
                )
                continue
            except BusinessFault:
                await self._fail_booking(workflow, "RESERVATION_FAILED", True, context)
                raise
        await self.reconciliation.schedule(
            workflow.workflow_id,
            "RESERVE_REPLAY",
            {"request": dict(payload), "requestFingerprint": fingerprint},
            idempotency_key,
        )
        workflow.phase = WorkflowPhase.PENDING
        await self.workflows.save(workflow)
        return None

    async def _payment_command(self, operation: str, workflow: WorkflowEvidence, context: RequestContext) -> PaymentOutcome:
        try:
            response = await self.payments.command(
                operation,
                workflow.payment_id or "",
                {},
                step_key(workflow.workflow_id, operation),
                context,
            )
            return PaymentOutcome(str(response.get("status", "UNKNOWN")))
        except AmbiguousOutcome:
            return PaymentOutcome.UNKNOWN

    async def _payment_failed(
        self,
        workflow: WorkflowEvidence,
        command: PlaceBookingCommand,
        context: RequestContext,
    ) -> OperationResult:
        released = await self._release(workflow, "PAYMENT_FAILED", context)
        await self._fail_booking(workflow, "PAYMENT_FAILED", released, context)
        workflow.phase = WorkflowPhase.FAILED if released else WorkflowPhase.COMPENSATION_PENDING
        await self.workflows.save(workflow)
        result = OperationResult(
            402,
            self._error("PAYMENT_FAILED", "Payment was declined.", context, not released),
        )
        await self._complete(command, context, result)
        return result

    async def _payment_unknown(
        self,
        workflow: WorkflowEvidence,
        command: PlaceBookingCommand,
        context: RequestContext,
    ) -> OperationResult:
        workflow.payment_status = PaymentOutcome.UNKNOWN
        workflow.phase = WorkflowPhase.PAYMENT_PROCESSING
        await self.workflows.save(workflow)
        await self.reconciliation.schedule(
            workflow.workflow_id,
            "PAYMENT_UNKNOWN",
            {"paymentId": workflow.payment_id, "bookingId": workflow.booking_id},
            step_key(workflow.workflow_id, "reconcilePayment"),
        )
        result = self._booking_result(workflow, WorkflowPhase.PAYMENT_PROCESSING, 202)
        await self._complete(command, context, result)
        return result

    async def _release(self, workflow: WorkflowEvidence, reason: str, context: RequestContext) -> bool:
        if not workflow.reservation_id:
            return False
        try:
            response = await self.seats.release_seats(
                workflow.reservation_id,
                reason,
                step_key(workflow.workflow_id, f"ReleaseSeats:{reason}"),
                context,
            )
            return response.get("status") == "RELEASED"
        except Exception:
            return False

    async def _fail_booking(
        self,
        workflow: WorkflowEvidence,
        reason: str,
        compensation_complete: bool,
        context: RequestContext,
    ) -> None:
        if not workflow.booking_id:
            return
        state = "COMPLETED" if compensation_complete else "PENDING"
        await self.bookings.transition(
            "bookingFail",
            workflow.booking_id,
            {
                "reasonCode": reason,
                "compensationStatus": state,
                "evidence": dict(workflow.evidence),
            },
            step_key(workflow.workflow_id, f"bookingFail:{reason}"),
            context,
        )

    async def _save_step(
        self,
        workflow: WorkflowEvidence,
        step: str,
        provider: str,
        outcome: str,
        details: Mapping[str, Any],
    ) -> None:
        await self.workflows.save(workflow)
        await self.workflows.record_step(workflow.workflow_id, step, provider, outcome, details)

    async def _complete(
        self,
        command: PlaceBookingCommand,
        context: RequestContext,
        result: OperationResult,
    ) -> None:
        await self.idempotency.complete("placeBooking", context.principal.subject, command.idempotency_key, result)

    @staticmethod
    def _authoritative_selection(event: Mapping[str, Any], eligibility: Mapping[str, Any], quantity: int) -> tuple[str, Money]:
        ticket_types = list(event.get("ticketTypes", []))
        if not ticket_types:
            raise BusinessFault("TICKET_TYPE_UNAVAILABLE", "No ticket type is available.", 409, False)
        selected = ticket_types[0]
        price = selected.get("price") or (eligibility.get("priceSnapshot") or [{}])[0].get("price")
        if not price:
            raise BusinessFault(
                "AUTHORITATIVE_PRICE_MISSING",
                "Authoritative price is unavailable.",
                503,
                True,
            )
        return str(selected.get("code", "STANDARD")), Money(int(price["amountMinor"]) * quantity, str(price["currency"]))

    @staticmethod
    def _unit_price(event: Mapping[str, Any], code: str) -> Mapping[str, Any]:
        selected = next(item for item in event.get("ticketTypes", []) if item.get("code") == code)
        return selected["price"]

    @staticmethod
    def _error(code: str, message: str, context: RequestContext, retryable: bool) -> Mapping[str, Any]:
        return {
            "correlationId": context.correlation_id,
            "traceId": context.trace_id,
            "error": {"code": code, "message": message, "retryable": retryable},
        }

    @staticmethod
    def _booking_result(workflow: WorkflowEvidence, phase: WorkflowPhase, status_code: int = 202) -> OperationResult:
        return OperationResult(
            status_code,
            {
                "bookingId": workflow.booking_id or workflow.workflow_id,
                "status": phase.value,
                "total": (workflow.total or Money(0, "VND")).as_wire(),
                "reservationId": workflow.reservation_id,
                "paymentId": workflow.payment_id,
                "ticketIds": list(workflow.ticket_ids),
                "correlationId": workflow.correlation_id,
            },
        )

    @staticmethod
    def _event_payload(workflow: WorkflowEvidence) -> Mapping[str, Any]:
        return {
            "bookingId": workflow.booking_id,
            "status": "CONFIRMED",
            "ticketIds": list(workflow.ticket_ids),
        }

    @staticmethod
    def _realtime_payload(workflow: WorkflowEvidence) -> Mapping[str, Any]:
        return {
            "bookingId": workflow.booking_id,
            "status": "CONFIRMED",
            "sequence": workflow.version,
        }
