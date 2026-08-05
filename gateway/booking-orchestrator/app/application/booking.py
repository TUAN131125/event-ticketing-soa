from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.domain.errors import (
    AmbiguousOutcome,
    BusinessFault,
    CommandNotDispatched,
    DependencyFailure,
)
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

# Provider error codes that mean "the payment did not go through", as opposed to a
# transport or state problem the saga must not swallow.
DECLINED_PAYMENT_CODES = frozenset({"PAYMENT_DECLINED", "PAYMENT_FAILED"})


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
        reconciliation_deadline_seconds: int = 900,
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
        self.reconciliation_deadline_seconds = reconciliation_deadline_seconds

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

        event, ticket_type, amount = await self._load_authoritative_sale(command, workflow, context)
        reservation = await self._create_and_reserve(command, workflow, event, ticket_type, context)
        if reservation is None:
            result = self._booking_result(workflow, WorkflowPhase.PENDING)
            await self._complete(command, context, result)
            return result
        await self._record_reservation(workflow, reservation, context)

        payment_result = await self._take_payment(command, workflow, amount, context)
        if payment_result is not None:
            return payment_result

        await self._issue_and_confirm(command, workflow, context)
        return await self._complete_success(command, workflow, context)

    async def _load_authoritative_sale(
        self,
        command: PlaceBookingCommand,
        workflow: WorkflowEvidence,
        context: RequestContext,
    ) -> tuple[Mapping[str, Any], str, Money]:
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
        return event, ticket_type, amount

    async def _create_and_reserve(
        self,
        command: PlaceBookingCommand,
        workflow: WorkflowEvidence,
        event: Mapping[str, Any],
        ticket_type: str,
        context: RequestContext,
    ) -> Mapping[str, Any] | None:
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
        return await self._reserve_with_same_request(
            workflow,
            reserve_payload,
            step_key(workflow.workflow_id, "ReserveSeats"),
            context,
        )

    async def _record_reservation(
        self,
        workflow: WorkflowEvidence,
        reservation: Mapping[str, Any],
        context: RequestContext,
    ) -> None:
        workflow.reservation_id = str(reservation["reservationId"])
        workflow.reservation_version = int(reservation.get("resourceVersion", 1))
        booking_id = workflow.booking_id
        reservation_id = workflow.reservation_id
        if booking_id is None:
            raise RuntimeError("Booking identifier is missing after creation")
        workflow.phase = WorkflowPhase.SEAT_RESERVED
        await self._save_step(
            workflow,
            "ReserveSeats",
            "seat-inventory-service",
            "ACTIVE",
            {"reservationId": reservation_id},
        )
        try:
            await self.bookings.transition(
                "bookingReservation",
                booking_id,
                {
                    "reservationId": reservation_id,
                    "evidence": {
                        "providerReference": reservation_id,
                        "reservationExpiresAt": reservation["expiresAt"],
                    },
                },
                step_key(workflow.workflow_id, "bookingReservation"),
                context,
            )
        except Exception:  # noqa: BLE001 -- failure must leave durable compensation evidence
            released = await self._release(workflow, "BOOKING_RESERVATION_EVIDENCE_FAILED", context)
            await self._fail_booking(workflow, "RESERVATION_EVIDENCE_FAILED", released, context)
            raise

    async def _take_payment(
        self,
        command: PlaceBookingCommand,
        workflow: WorkflowEvidence,
        amount: Money,
        context: RequestContext,
    ) -> OperationResult | None:
        booking_id = workflow.booking_id
        if booking_id is None:
            raise RuntimeError("Booking identifier is missing before payment")
        create_key = step_key(workflow.workflow_id, "createPayment")
        try:
            payment = await self.payments.create_payment(
                booking_id,
                amount,
                command.payment_method_token,
                create_key,
                context,
            )
        except CommandNotDispatched:
            # No payment can exist, so compensation is safe and immediate.
            return await self._payment_not_dispatched(workflow, command, "createPayment", context)
        except AmbiguousOutcome:
            # A payment may exist under create_key; only reconciliation may decide.
            return await self._payment_unknown(workflow, command, context, create_key=create_key)
        except DependencyFailure:
            # Dispatched but unanswered, including a deadline that expired mid-flight.
            return await self._payment_unknown(workflow, command, context, create_key=create_key)
        workflow.payment_id = str(payment["paymentId"])
        payment_id = workflow.payment_id
        workflow.phase = WorkflowPhase.PAYMENT_PROCESSING
        await self.bookings.transition(
            "bookingPaymentStarted",
            booking_id,
            {"paymentId": payment_id},
            step_key(workflow.workflow_id, "bookingPaymentStarted"),
            context,
        )
        authorization = await self._payment_command("authorizePayment", workflow, context)
        if authorization is PaymentOutcome.NOT_DISPATCHED:
            return await self._payment_not_dispatched(workflow, command, "authorizePayment", context)
        if authorization in {PaymentOutcome.FAILED, PaymentOutcome.DECLINED}:
            return await self._payment_failed(workflow, command, context)
        if authorization is PaymentOutcome.UNKNOWN:
            return await self._payment_unknown(workflow, command, context)
        capture = await self._payment_command("capturePayment", workflow, context)
        if capture is PaymentOutcome.NOT_DISPATCHED:
            # Authorized but never captured: the outcome is known, so release directly.
            return await self._payment_not_dispatched(workflow, command, "capturePayment", context)
        workflow.payment_status = capture
        await self.bookings.transition(
            "bookingPaymentResult",
            booking_id,
            {
                "paymentId": payment_id,
                "paymentStatus": capture.value,
                "evidence": {
                    "providerReference": payment_id,
                    "verifiedAt": datetime.now(UTC).isoformat(),
                },
            },
            step_key(workflow.workflow_id, "bookingPaymentResult"),
            context,
        )
        if capture in {PaymentOutcome.FAILED, PaymentOutcome.DECLINED}:
            return await self._payment_failed(workflow, command, context)
        if capture != PaymentOutcome.CAPTURED:
            return await self._payment_unknown(workflow, command, context)
        return None

    async def _issue_and_confirm(
        self,
        command: PlaceBookingCommand,
        workflow: WorkflowEvidence,
        context: RequestContext,
    ) -> None:
        booking_id = workflow.booking_id
        reservation_id = workflow.reservation_id
        payment_id = workflow.payment_id
        if booking_id is None or reservation_id is None or payment_id is None:
            raise RuntimeError("Confirmed booking evidence is incomplete")
        try:
            issued = await self.tickets.issue_tickets(
                {
                    "bookingId": booking_id,
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
                booking_id,
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
            confirmed_seat = await self.seats.confirm_seats(
                reservation_id,
                workflow.reservation_version or 1,
                step_key(workflow.workflow_id, "ConfirmSeats"),
                context,
            )
            await self.bookings.transition(
                "bookingConfirm",
                booking_id,
                {
                    "reservationId": reservation_id,
                    "paymentId": payment_id,
                    "paymentStatus": "CAPTURED",
                    "ticketIds": workflow.ticket_ids,
                    "evidence": {
                        "paymentCaptured": True,
                        "seatConfirmed": confirmed_seat.get("status") == "CONFIRMED",
                        "ticketsIssued": True,
                        "verifiedAt": datetime.now(UTC).isoformat(),
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

    async def _complete_success(
        self,
        command: PlaceBookingCommand,
        workflow: WorkflowEvidence,
        context: RequestContext,
    ) -> OperationResult:
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
        except CommandNotDispatched:
            # Rejected before any byte was sent, so no payment state can exist.
            return PaymentOutcome.NOT_DISPATCHED
        except AmbiguousOutcome:
            return PaymentOutcome.UNKNOWN
        except BusinessFault as fault:
            # Payment Service reports a decline as a 402 business fault. Letting it
            # escape would abort the saga before compensation, leaving the seat held
            # and the booking un-failed, so it is folded back into the outcome.
            if fault.status_code == 402 or fault.code in DECLINED_PAYMENT_CODES:
                return PaymentOutcome.DECLINED
            raise
        except DependencyFailure:
            # Dispatched, but the transport or an ambiguous 5xx hid the result.
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

    async def _payment_not_dispatched(
        self,
        workflow: WorkflowEvidence,
        command: PlaceBookingCommand,
        operation: str,
        context: RequestContext,
    ) -> OperationResult:
        """The command never left the ESB: release the seat now, never reconcile."""
        workflow.payment_status = PaymentOutcome.NOT_DISPATCHED
        released = await self._release(workflow, "PAYMENT_NOT_DISPATCHED", context)
        await self._fail_booking(workflow, "PAYMENT_NOT_DISPATCHED", released, context)
        workflow.phase = WorkflowPhase.FAILED if released else WorkflowPhase.COMPENSATION_PENDING
        workflow.evidence = {
            **dict(workflow.evidence),
            "paymentDispatch": {"operation": operation, "dispatched": False},
        }
        await self.workflows.save(workflow)
        result = OperationResult(
            503,
            self._error(
                "PAYMENT_NOT_DISPATCHED",
                "The payment command was not sent; no payment was created.",
                context,
                True,
            ),
        )
        await self._complete(command, context, result)
        return result

    async def _payment_unknown(
        self,
        workflow: WorkflowEvidence,
        command: PlaceBookingCommand,
        context: RequestContext,
        *,
        create_key: str | None = None,
    ) -> OperationResult:
        workflow.payment_status = PaymentOutcome.UNKNOWN
        workflow.phase = WorkflowPhase.PAYMENT_PROCESSING
        await self.workflows.save(workflow)
        await self.reconciliation.schedule(
            workflow.workflow_id,
            "PAYMENT_UNKNOWN",
            {
                "paymentId": workflow.payment_id,
                "bookingId": workflow.booking_id,
                "createIdempotencyKey": create_key,
                "amount": workflow.total.as_wire() if workflow.total else None,
                "methodToken": command.payment_method_token,
            },
            step_key(workflow.workflow_id, "reconcilePayment"),
            deadline=self.clock.now() + timedelta(seconds=self.reconciliation_deadline_seconds),
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
                "evidence": {
                    "compensationCompleted": compensation_complete,
                    "verifiedAt": datetime.now(UTC).isoformat(),
                },
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
