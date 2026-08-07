from __future__ import annotations

import uuid
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from typing import Any

from app.application.evidence import booking_evidence
from app.domain.errors import Conflict, EsbError, PaymentUnknown
from app.domain.idempotency import assert_replay_compatible, request_hash
from app.domain.models import (
    BookingItem,
    OutboxMessage,
    PaymentStatus,
    RequestContext,
    Workflow,
    WorkflowStatus,
)
from app.domain.payment_status import (
    is_captured,
    is_failed,
    is_pending,
    parse_payment_status,
    to_booking_payment_status,
)

TERMINAL_WORKFLOW_STATUSES = {
    WorkflowStatus.CONFIRMED,
    WorkflowStatus.FAILED,
    WorkflowStatus.CANCELLED,
}
# tns:ReservationStatus in contracts/seat-inventory.xsd. Only ACTIVE means the seats are
# still held for this booking.
RESERVATION_STATUSES = {"ACTIVE", "CONFIRMED", "RELEASED", "EXPIRED"}


class BookingSaga:
    """Coordinates provider capabilities without owning their business rules."""

    def __init__(
        self,
        customer: Any,
        event: Any,
        seat: Any,
        booking: Any,
        payment: Any,
        ticket: Any,
        workflows: Any,
        outbox: Any,
        settings: Any,
    ) -> None:
        self.customer = customer
        self.event = event
        self.seat = seat
        self.booking = booking
        self.payment = payment
        self.ticket = ticket
        self.workflows = workflows
        self.outbox = outbox
        self.settings = settings

    async def place(
        self,
        request: dict[str, Any],
        key: str,
        ctx: RequestContext,
    ) -> tuple[int, dict[str, Any]]:
        payload_hash = request_hash(request)
        existing = await self.workflows.find_by_idempotency(key)
        if existing is not None:
            assert_replay_compatible(existing.request_hash, payload_hash)
            if existing.response_body is not None:
                return existing.response_status or 200, existing.response_body
            # A crash can happen after the workflow record is created but before
            # Booking Service returns a durable booking/version. Replaying the
            # same public command resumes the idempotent first stage instead of
            # emitting an incomplete BookingResult that violates the contract.
            if not existing.booking_id or existing.booking_version is None:
                return await self._start(existing, request, ctx)
            return 202, self._response(existing)

        customer = await self.customer.resolve_identity(ctx.principal.subject, ctx)
        customer_id = str(customer.get("customerId") or customer.get("id") or "")
        if not customer_id:
            raise EsbError(
                "IDENTITY_NOT_MAPPED",
                "Authenticated identity has no active Customer mapping",
                409,
            )
        self._validate_compatibility_customer_id(request.get("customerId"), customer_id)

        seat_ids = list(dict.fromkeys(request["seatIds"]))
        if not seat_ids:
            raise EsbError("VALIDATION_ERROR", "seatIds must not be empty", 422)

        workflow = Workflow(
            workflow_id=str(uuid.uuid4()),
            idempotency_key=key,
            request_hash=payload_hash,
            customer_id=customer_id,
            event_id=request["eventId"],
            seat_ids=seat_ids,
            evidence={
                "correlationId": ctx.correlation_id,
                "traceId": ctx.trace_id,
            },
        )
        await self.workflows.save(workflow)

        try:
            return await self._start(workflow, request, ctx)
        except PaymentUnknown:
            await self._persist_payment_unknown(workflow, ctx)
            return 202, workflow.response_body or self._response(workflow)
        except Exception as exc:
            await self._handle_unexpected_failure(workflow, exc, ctx)
            raise

    async def reconcile(
        self,
        workflow_id: str,
        ctx: RequestContext,
    ) -> tuple[int, dict[str, Any]]:
        workflow = await self.workflows.get(workflow_id)
        if workflow is None:
            raise EsbError("WORKFLOW_NOT_FOUND", "Workflow was not found", 404)

        if workflow.response_body is not None and workflow.status in TERMINAL_WORKFLOW_STATUSES:
            return workflow.response_status or 200, workflow.response_body

        if workflow.status == WorkflowStatus.COMPENSATION_PENDING:
            return await self.compensate(workflow_id, ctx)

        if not workflow.payment_id:
            raise EsbError(
                "WORKFLOW_EVIDENCE_INCOMPLETE",
                "Payment evidence is missing from workflow",
                409,
            )

        payment = await self.payment.get(workflow.payment_id, ctx)
        payment_status = parse_payment_status(payment)
        if is_pending(payment_status):
            workflow.payment_status = PaymentStatus.UNKNOWN
            await self._persist_payment_unknown(workflow, ctx)
            return 202, workflow.response_body or self._response(workflow)
        if is_failed(payment_status):
            return await self._payment_failed(workflow, payment, ctx)
        if not is_captured(payment_status):
            # A refunded or partially refunded payment is a real state, but not one this
            # saga can drive forward; it belongs to compensation, not reconciliation.
            raise EsbError(
                "PAYMENT_STATE_UNSUPPORTED",
                f"Cannot reconcile payment state {payment_status.value}",
                409,
            )

        workflow.payment_status = PaymentStatus.CAPTURED
        await self._refresh_booking_version(workflow, ctx)
        items = self._workflow_items(workflow)
        try:
            return await self._after_payment_captured(workflow, items, payment, ctx)
        except Exception as exc:
            await self._handle_unexpected_failure(workflow, exc, ctx)
            raise

    async def compensate(
        self,
        workflow_id: str,
        ctx: RequestContext,
    ) -> tuple[int, dict[str, Any]]:
        workflow = await self.workflows.get(workflow_id)
        if workflow is None:
            raise EsbError("WORKFLOW_NOT_FOUND", "Workflow was not found", 404)
        if workflow.status != WorkflowStatus.COMPENSATION_PENDING:
            return workflow.response_status or 200, workflow.response_body or self._response(workflow)
        if not workflow.booking_id:
            raise EsbError(
                "WORKFLOW_EVIDENCE_INCOMPLETE",
                "Booking evidence is missing from compensation workflow",
                409,
            )

        booking = await self.booking.get(workflow.booking_id, ctx)
        workflow.booking_version = _int_or_none(booking.get("resourceVersion"))
        evidence: dict[str, Any] = {}
        complete = True

        ticket_ids = await self._authoritative_ticket_ids(workflow, ctx)
        for ticket_id in ticket_ids:
            try:
                ticket = await self.ticket.get(ticket_id, ctx)
                if str(ticket.get("status", "")).upper() != "CANCELLED":
                    await self.ticket.cancel(
                        ticket_id,
                        {
                            "reason": "WORKFLOW_COMPENSATION",
                            "expectedVersion": ticket.get("resourceVersion"),
                        },
                        f"{workflow.idempotency_key}:compensate-ticket:{ticket_id}",
                        ctx,
                    )
                evidence.setdefault("tickets", []).append(
                    {"ticketId": ticket_id, "status": "CANCELLED"}
                )
            except Exception as exc:
                complete = False
                evidence.setdefault("tickets", []).append(
                    {
                        "ticketId": ticket_id,
                        "status": "PENDING",
                        "errorCode": self._safe_error_code(exc),
                    }
                )

        if workflow.payment_id:
            payment_complete, payment_evidence = await self._compensate_payment(workflow, ctx)
            complete = complete and payment_complete
            evidence["payment"] = payment_evidence

        if workflow.reservation_id:
            try:
                await self.seat.release(
                    workflow.reservation_id,
                    "WORKFLOW_COMPENSATION",
                    workflow.idempotency_key + ":compensate-seat",
                    ctx,
                )
                evidence["reservation"] = {"status": "RELEASED"}
            except Exception as exc:
                complete = False
                evidence["reservation"] = {
                    "status": "PENDING",
                    "errorCode": self._safe_error_code(exc),
                }

        result = await self.booking.record_compensation(
            workflow.booking_id,
            {
                "compensationStatus": "COMPLETED" if complete else "PENDING",
                "expectedVersion": workflow.booking_version,
                "reason": "BOOKING_WORKFLOW_FAILED",
                "evidence": booking_evidence(
                    reservation_released=(
                        evidence.get("reservation", {}).get("status") == "RELEASED"
                    ),
                    payment_refunded=(
                        evidence.get("payment", {}).get("status") == "REFUNDED"
                    ),
                    compensation_completed=complete,
                    details=evidence,
                ),
            },
            workflow.idempotency_key + ":compensation-result",
            ctx,
        )
        workflow.booking_version = _int_or_none(
            result.get("resourceVersion") or workflow.booking_version
        )
        workflow.status = (
            WorkflowStatus.FAILED if complete else WorkflowStatus.COMPENSATION_PENDING
        )
        workflow.response_status = 409 if complete else 202
        if complete:
            workflow.response_body = self._workflow_failure_response(
                workflow,
                code="BOOKING_WORKFLOW_FAILED",
                message="Booking workflow failed and compensation completed",
                retryable=False,
                details={"compensationStatus": "COMPLETED"},
            )
        else:
            # 202 is typed as a BookingResult by the canonical contract, and a booking
            # whose compensation is still running is exactly what that projection is for:
            # it carries the bookingId, paymentId and reservationId a caller needs to
            # poll. Answering 202 with an ErrorResponse instead made the replay of this
            # workflow fail response validation and turn into a 500.
            workflow.response_body = self._response(workflow)
        await self.workflows.save(workflow)
        return workflow.response_status, workflow.response_body

    @staticmethod
    def _validate_compatibility_customer_id(
        browser_customer_id: object,
        authoritative_customer_id: str,
    ) -> None:
        if browser_customer_id and str(browser_customer_id) not in {
            "AUTHENTICATED-CUSTOMER",
            authoritative_customer_id,
        }:
            raise Conflict(
                "CUSTOMER_IDENTITY_MISMATCH",
                "customerId does not match authenticated identity",
            )

    async def _selection(
        self,
        workflow: Workflow,
        ctx: RequestContext,
    ) -> list[BookingItem]:
        event = await self.event.get_event(workflow.event_id, ctx)
        eligibility = await self.event.check_sale_eligibility(workflow.event_id, ctx)
        if eligibility.get("eligible") is False:
            raise Conflict(
                "EVENT_NOT_ON_SALE",
                str(eligibility.get("reason") or "Event is not on sale"),
            )

        seat_map = await self.seat.get_seat_map(workflow.event_id, ctx)
        raw_seats = seat_map.get("seats") or seat_map.get("seat") or []
        if isinstance(raw_seats, dict):
            raw_seats = raw_seats.get("seat") or raw_seats.get("items") or []
        if isinstance(raw_seats, dict):
            raw_seats = [raw_seats]
        seats_by_id = {
            str(seat.get("seatId") or seat.get("id")): seat
            for seat in raw_seats
            if isinstance(seat, dict)
        }
        ticket_types = {
            str(ticket_type.get("code")): ticket_type
            for ticket_type in event.get("ticketTypes", [])
            if isinstance(ticket_type, dict)
        }

        items: list[BookingItem] = []
        for seat_id in workflow.seat_ids:
            seat = seats_by_id.get(seat_id)
            if seat is None:
                raise Conflict(
                    "SEAT_NOT_FOUND",
                    f"Seat {seat_id} is not in the authoritative seat map",
                )
            ticket_type_code = str(
                seat.get("ticketTypeCode") or seat.get("ticketType") or ""
            )
            ticket_type = ticket_types.get(ticket_type_code)
            if not ticket_type_code or ticket_type is None:
                raise Conflict(
                    "TICKET_TYPE_UNAVAILABLE",
                    f"Seat {seat_id} has no authoritative ticket type",
                )
            price = ticket_type.get("price") or {}
            amount_minor = price.get("amountMinor")
            currency = price.get("currency")
            if not isinstance(amount_minor, int) or amount_minor < 0 or not currency:
                raise Conflict(
                    "AUTHORITATIVE_PRICE_MISSING",
                    f"No authoritative price for ticket type {ticket_type_code}",
                )
            items.append(
                BookingItem(
                    seat_id=seat_id,
                    ticket_type=ticket_type_code,
                    unit_price=amount_minor,
                    currency=str(currency),
                )
            )

        return items

    @staticmethod
    def _authoritative_booking_money(booking: dict[str, Any]) -> tuple[int, str]:
        total = booking.get("total")
        if isinstance(total, dict):
            amount = total.get("amountMinor")
            currency = total.get("currency")
        else:
            amount = booking.get("totalAmount", total)
            currency = booking.get("currency")
        try:
            # Booking Service publishes `total`/`totalAmount` as a decimal string (its
            # canonical contract types both as `string`), carrying the same minor-unit
            # value the ESB sent as `unitPrice` — "100000.00" for 100000 minor units.
            # int() cannot read that, so parse as a decimal and require a whole number
            # rather than truncating a fractional minor unit into a wrong charge.
            quantity = Decimal(str(amount).strip())
        except (AttributeError, InvalidOperation, TypeError, ValueError) as exc:
            raise EsbError(
                "BOOKING_PROTOCOL_ERROR",
                "Booking Service did not return an authoritative totalAmount",
                502,
                True,
            ) from exc
        if quantity != quantity.to_integral_value():
            raise EsbError(
                "BOOKING_PROTOCOL_ERROR",
                "Booking Service returned a fractional minor-unit totalAmount",
                502,
                True,
            )
        amount_minor = int(quantity)
        currency_code = str(currency or "").upper()
        if amount_minor < 0 or len(currency_code) != 3:
            raise EsbError(
                "BOOKING_PROTOCOL_ERROR",
                "Booking Service returned invalid authoritative money evidence",
                502,
                True,
            )
        return amount_minor, currency_code

    async def _start(
        self,
        workflow: Workflow,
        request: dict[str, Any],
        ctx: RequestContext,
    ) -> tuple[int, dict[str, Any]]:
        items = await self._selection(workflow, ctx)
        workflow.evidence["items"] = [asdict(item) for item in items]

        booking = await self.booking.create(
            {
                "customerId": workflow.customer_id,
                "eventId": workflow.event_id,
                "items": [
                    {
                        "seatId": item.seat_id,
                        "ticketType": item.ticket_type,
                        "unitPrice": item.unit_price,
                        "priceCurrency": item.currency,
                    }
                    for item in items
                ],
            },
            workflow.idempotency_key + ":booking",
            ctx,
        )
        workflow.booking_id = str(booking.get("bookingId") or booking.get("id") or "")
        workflow.booking_version = _int_or_none(booking.get("resourceVersion"))
        workflow.amount_minor, workflow.currency = self._authoritative_booking_money(booking)
        workflow.evidence["authoritativeBookingMoney"] = {
            "amountMinor": workflow.amount_minor,
            "currency": workflow.currency,
            "resourceVersion": workflow.booking_version,
        }
        if not workflow.booking_id:
            raise EsbError(
                "BOOKING_PROTOCOL_ERROR",
                "Booking Service did not return bookingId",
                502,
                True,
            )
        await self.workflows.save(workflow)

        seat_references = [item.seat_reference() for item in items]
        availability = await self.seat.check_availability(
            workflow.event_id,
            seat_references,
            ctx,
        )
        if availability.get("available") is False:
            raise Conflict(
                "SEAT_UNAVAILABLE",
                f"Seat {availability.get('unavailableSeatId', '')} is unavailable".strip(),
            )
        reservation = await self.seat.reserve(
            workflow.booking_id,
            workflow.event_id,
            seat_references,
            self.settings.reservation_ttl_seconds,
            workflow.idempotency_key + ":reserve",
            ctx,
        )
        workflow.reservation_id = str(reservation.get("reservationId") or "")
        workflow.reservation_version = _int_or_none(
            reservation.get("resourceVersion") or reservation.get("version")
        )
        if not workflow.reservation_id or workflow.reservation_version is None:
            raise EsbError(
                "SEAT_PROTOCOL_ERROR",
                "Seat Inventory returned incomplete reservation evidence",
                502,
                True,
            )
        reservation_status = _reservation_status(reservation)
        workflow.evidence["reservationStatus"] = reservation_status
        if reservation_status != "ACTIVE":
            # The seats are not held for this booking, so the saga must not reach Payment,
            # Ticket or CONFIRMED. Any hold Seat Inventory did create is left to the
            # existing reservation expiry and reconciliation paths.
            raise Conflict(
                "SEAT_RESERVATION_NOT_ACTIVE",
                "The seat reservation is not active, so the booking cannot continue",
            )
        workflow.status = WorkflowStatus.SEAT_RESERVED

        booking = await self.booking.attach_reservation(
            workflow.booking_id,
            {
                "reservationId": workflow.reservation_id,
                "reservationVersion": workflow.reservation_version,
                "reservationExpiresAt": reservation.get("expiresAt"),
                "expectedVersion": workflow.booking_version,
                "evidence": booking_evidence(
                    reservation_expires_at=reservation.get("expiresAt"),
                    details={
                        "source": "SeatInventory",
                        "status": reservation_status,
                    },
                ),
            },
            workflow.idempotency_key + ":booking-reservation",
            ctx,
        )
        workflow.booking_version = _require_booking_version(booking)
        await self.workflows.save(workflow)

        payment = await self.payment.create(
            {
                "bookingId": workflow.booking_id,
                "customerId": workflow.customer_id,
                "amountMinor": workflow.amount_minor,
                "currency": workflow.currency,
                "methodToken": request["paymentMethodToken"],
                "bookingEvidence": {
                    "bookingId": workflow.booking_id,
                    "customerId": workflow.customer_id,
                    "amountMinor": workflow.amount_minor,
                    "currency": workflow.currency,
                    "resourceVersion": workflow.booking_version,
                    "evidenceId": workflow.workflow_id,
                },
            },
            workflow.idempotency_key + ":payment-create",
            ctx,
        )
        workflow.payment_id = str(payment.get("paymentId") or payment.get("id") or "")
        if not workflow.payment_id:
            raise EsbError(
                "PAYMENT_PROTOCOL_ERROR",
                "Payment Service did not return paymentId",
                502,
                True,
            )
        booking = await self.booking.start_payment(
            workflow.booking_id,
            {
                "paymentId": workflow.payment_id,
                "expectedVersion": workflow.booking_version,
            },
            workflow.idempotency_key + ":booking-payment-start",
            ctx,
        )
        workflow.booking_version = _require_booking_version(booking)
        workflow.status = WorkflowStatus.PAYMENT_PROCESSING
        await self.workflows.save(workflow)

        try:
            authorization = await self.payment.authorize(
                workflow.payment_id,
                {"expectedVersion": payment.get("resourceVersion")},
                workflow.idempotency_key + ":authorize",
                ctx,
            )
        except EsbError as exc:
            if exc.retryable:
                workflow.payment_status = PaymentStatus.UNKNOWN
                raise PaymentUnknown("Payment authorization outcome is unknown") from exc
            declined = await self._declined_payment(workflow, exc, ctx)
            if declined is not None:
                return await self._payment_failed(workflow, declined, ctx)
            raise
        # A status outside the canonical enum raises PAYMENT_PROTOCOL_ERROR rather than
        # being guessed at; see app.domain.payment_status.
        authorization_status = parse_payment_status(authorization)
        if is_failed(authorization_status):
            return await self._payment_failed(workflow, authorization, ctx)
        if is_pending(authorization_status):
            workflow.payment_status = PaymentStatus.UNKNOWN
            raise PaymentUnknown()

        try:
            captured = await self.payment.capture(
                workflow.payment_id,
                {"expectedVersion": authorization.get("resourceVersion")},
                workflow.idempotency_key + ":capture",
                ctx,
            )
        except EsbError as exc:
            if exc.retryable:
                workflow.payment_status = PaymentStatus.UNKNOWN
                raise PaymentUnknown("Payment capture outcome is unknown") from exc
            declined = await self._declined_payment(workflow, exc, ctx)
            if declined is not None:
                return await self._payment_failed(workflow, declined, ctx)
            raise
        captured_status = parse_payment_status(captured)
        if is_pending(captured_status):
            workflow.payment_status = PaymentStatus.UNKNOWN
            raise PaymentUnknown()
        if is_failed(captured_status):
            return await self._payment_failed(workflow, captured, ctx)
        if not is_captured(captured_status):
            # AUTHORIZED, PARTIALLY_REFUNDED or REFUNDED here means capture did not settle
            # the way the saga assumes. Previously any non-CAPTURED value fell through to
            # the failure path, which would release seats against possibly-captured money.
            # The outcome is indeterminate, so the workflow is marked UNKNOWN before the
            # protocol error propagates and compensation — not seat release — takes over.
            workflow.payment_status = PaymentStatus.UNKNOWN
            await self.workflows.save(workflow)
            raise EsbError(
                "PAYMENT_PROTOCOL_ERROR",
                "Payment Service returned an unexpected status for a capture",
                502,
                False,
            )

        workflow.payment_status = PaymentStatus.CAPTURED
        await self.workflows.save(workflow)
        return await self._after_payment_captured(workflow, items, captured, ctx)

    async def _after_payment_captured(
        self,
        workflow: Workflow,
        items: list[BookingItem],
        payment: dict[str, Any],
        ctx: RequestContext,
    ) -> tuple[int, dict[str, Any]]:
        if not workflow.booking_id or not workflow.payment_id:
            raise EsbError(
                "WORKFLOW_EVIDENCE_INCOMPLETE",
                "Booking or payment evidence is missing",
                409,
            )
        if not workflow.reservation_id or workflow.reservation_version is None:
            raise EsbError(
                "WORKFLOW_EVIDENCE_INCOMPLETE",
                "Reservation evidence is missing",
                409,
            )

        steps = workflow.evidence.setdefault("completedSteps", {})
        if workflow.status in {
            WorkflowStatus.SEAT_CONFIRMED,
            WorkflowStatus.TICKETS_ISSUED,
            WorkflowStatus.CONFIRMED,
        }:
            steps["paymentRecorded"] = True
            steps["seatConfirmed"] = True
        if workflow.status in {
            WorkflowStatus.TICKETS_ISSUED,
            WorkflowStatus.CONFIRMED,
        }:
            steps["reservationEvidenceConfirmed"] = True
            steps["ticketsIssued"] = True
        if workflow.ticket_ids:
            steps["ticketsIssued"] = True

        if not steps.get("paymentRecorded"):
            booking = await self.booking.record_payment(
                workflow.booking_id,
                {
                    "paymentId": workflow.payment_id,
                    "paymentStatus": "SUCCEEDED",
                    "succeeded": True,
                    "expectedVersion": workflow.booking_version,
                    "evidence": booking_evidence(
                        provider_reference=payment.get("providerReference"),
                        payment_captured=True,
                        resolved_payment_status="SUCCEEDED",
                        details={"source": "Payment"},
                    ),
                },
                workflow.idempotency_key + ":booking-payment-result",
                ctx,
            )
            workflow.booking_version = _require_booking_version(booking)
            steps["paymentRecorded"] = True
            await self.workflows.save(workflow)

        if not steps.get("seatConfirmed"):
            # P0 invariant: Ticket Service must not be called before Seat confirmation.
            confirmed_reservation = await self.seat.confirm(
                workflow.reservation_id,
                workflow.reservation_version,
                workflow.idempotency_key + ":seat-confirm",
                ctx,
            )
            workflow.reservation_version = _int_or_none(
                confirmed_reservation.get("resourceVersion")
                or confirmed_reservation.get("version")
            )
            if workflow.reservation_version is None:
                raise EsbError(
                    "SEAT_PROTOCOL_ERROR",
                    "Seat Inventory did not return confirmed reservation version",
                    502,
                    True,
                )
            workflow.status = WorkflowStatus.SEAT_CONFIRMED
            steps["seatConfirmed"] = True
            await self.workflows.save(workflow)

        if not steps.get("reservationEvidenceConfirmed"):
            booking = await self.booking.confirm_reservation(
                workflow.booking_id,
                {
                    "reservationId": workflow.reservation_id,
                    "reservationVersion": workflow.reservation_version,
                    "expectedVersion": workflow.booking_version,
                    "evidence": booking_evidence(
                        seat_confirmed=True,
                        details={"source": "SeatInventory", "status": "CONFIRMED"},
                    ),
                },
                workflow.idempotency_key + ":booking-seat-confirmed",
                ctx,
            )
            workflow.booking_version = _require_booking_version(booking)
            steps["reservationEvidenceConfirmed"] = True
            await self.workflows.save(workflow)

        if not steps.get("ticketsIssued"):
            issued = await self.ticket.issue(
                {
                    "bookingId": workflow.booking_id,
                    "eventId": workflow.event_id,
                    "customerId": workflow.customer_id,
                    "items": [{"seatId": item.seat_id} for item in items],
                },
                workflow.idempotency_key + ":tickets",
                ctx,
            )
            if isinstance(issued, list):
                tickets = issued
            elif isinstance(issued, dict):
                tickets = issued.get("tickets") or issued.get("items") or []
            else:
                tickets = []
            workflow.ticket_ids = [
                str(ticket.get("ticketId") if isinstance(ticket, dict) else ticket)
                for ticket in tickets
            ]
            if not workflow.ticket_ids:
                raise EsbError(
                    "TICKET_PROTOCOL_ERROR",
                    "Ticket Service returned no issued tickets",
                    502,
                    True,
                )
            workflow.status = WorkflowStatus.TICKETS_ISSUED
            steps["ticketsIssued"] = True
            await self.workflows.save(workflow)
        elif not workflow.ticket_ids:
            workflow.ticket_ids = await self._authoritative_ticket_ids(workflow, ctx)
            if not workflow.ticket_ids:
                raise EsbError(
                    "WORKFLOW_EVIDENCE_INCOMPLETE",
                    "Ticket issue step completed without durable ticket IDs",
                    409,
                )

        if not steps.get("ticketsAttached"):
            booking = await self.booking.attach_tickets(
                workflow.booking_id,
                {
                    "ticketIds": workflow.ticket_ids,
                    "expectedVersion": workflow.booking_version,
                    "evidence": booking_evidence(
                        tickets_issued=True,
                        details={"source": "Ticket"},
                    ),
                },
                workflow.idempotency_key + ":booking-tickets",
                ctx,
            )
            workflow.booking_version = _require_booking_version(booking)
            steps["ticketsAttached"] = True
            await self.workflows.save(workflow)

        if not steps.get("bookingConfirmed"):
            booking = await self.booking.confirm(
                workflow.booking_id,
                {
                    "expectedVersion": workflow.booking_version,
                    "reservationId": workflow.reservation_id,
                    "paymentId": workflow.payment_id,
                    "paymentStatus": "SUCCEEDED",
                    "ticketIds": workflow.ticket_ids,
                    "evidence": booking_evidence(
                        seat_confirmed=True,
                        tickets_issued=True,
                        payment_captured=True,
                        resolved_payment_status="SUCCEEDED",
                        details={"orchestratorWorkflowId": workflow.workflow_id},
                    ),
                },
                workflow.idempotency_key + ":booking-confirm",
                ctx,
            )
            workflow.booking_version = _require_booking_version(booking)
            steps["bookingConfirmed"] = True

        workflow.status = WorkflowStatus.CONFIRMED
        body = self._response(workflow)
        workflow.response_status = 201
        workflow.response_body = body
        messages = [
            OutboxMessage(
                message_id=str(uuid.uuid4()),
                topic=topic,
                payload={
                    **body,
                    "correlationId": ctx.correlation_id,
                    "traceId": ctx.trace_id,
                },
            )
            for topic in ("booking.confirmed", "booking.status")
        ]
        save_with_outbox = getattr(self.workflows, "save_with_outbox", None)
        if save_with_outbox is not None:
            await save_with_outbox(workflow, messages)
        else:  # compatibility for external test doubles
            await self.workflows.save(workflow)
            for message in messages:
                await self.outbox.add(message)
        return 201, body

    async def _declined_payment(
        self,
        workflow: Workflow,
        exc: EsbError,
        ctx: RequestContext,
    ) -> dict[str, Any] | None:
        """Return the authoritative payment when Payment reports a hard decline.

        Payment Service answers a declined authorization or capture with 402 rather than
        a 200 carrying a FAILED status, so the saga would otherwise never reach
        `_payment_failed` and would try to fail the booking while Booking still believed
        the payment was PROCESSING — which Booking correctly refuses with
        COMPENSATION_EVIDENCE_REQUIRED, stranding the booking and the seat.

        The decline is re-read from Payment instead of being inferred from the error, so
        the status recorded on Booking is the provider's own, and a payment that turns
        out not to be terminally failed falls through to the generic handler untouched.
        """
        if exc.status_code != 402 or not workflow.payment_id:
            return None
        try:
            payment = await self.payment.get(workflow.payment_id, ctx)
        except EsbError:
            return None
        if not is_failed(parse_payment_status(payment)):
            return None
        payment.setdefault("failureCode", exc.code)
        return payment

    async def _payment_failed(
        self,
        workflow: Workflow,
        payment: dict[str, Any],
        ctx: RequestContext,
    ) -> tuple[int, dict[str, Any]]:
        if not workflow.booking_id or not workflow.payment_id:
            raise EsbError(
                "WORKFLOW_EVIDENCE_INCOMPLETE",
                "Booking or payment evidence is missing",
                409,
            )
        workflow.payment_status = PaymentStatus.FAILED
        booking = await self.booking.record_payment(
            workflow.booking_id,
            {
                "paymentId": workflow.payment_id,
                "paymentStatus": "FAILED",
                "succeeded": False,
                "failureCode": payment.get("failureCode", "PAYMENT_DECLINED"),
                "expectedVersion": workflow.booking_version,
                "evidence": booking_evidence(
                    resolved_payment_status="FAILED",
                    details={"source": "Payment"},
                ),
            },
            workflow.idempotency_key + ":booking-payment-failed",
            ctx,
        )
        workflow.booking_version = _require_booking_version(booking)

        compensation = "NOT_REQUIRED"
        if workflow.reservation_id:
            try:
                await self.seat.release(
                    workflow.reservation_id,
                    "PAYMENT_FAILED",
                    workflow.idempotency_key + ":release",
                    ctx,
                )
                compensation = "COMPLETED"
            except Exception as exc:
                compensation = "PENDING"
                workflow.evidence["reservationReleaseErrorCode"] = self._safe_error_code(exc)

        await self.booking.fail(
            workflow.booking_id,
            {
                "failureCode": payment.get("failureCode", "PAYMENT_DECLINED"),
                "reason": "Payment was not captured",
                "expectedVersion": workflow.booking_version,
                "compensationStatus": compensation,
                "evidence": booking_evidence(
                    reservation_released=compensation == "COMPLETED",
                    compensation_completed=compensation in {"COMPLETED", "NOT_REQUIRED"},
                    details={"reservationRelease": compensation},
                ),
            },
            workflow.idempotency_key + ":booking-fail",
            ctx,
        )
        workflow.status = (
            WorkflowStatus.FAILED
            if compensation in {"COMPLETED", "NOT_REQUIRED"}
            else WorkflowStatus.COMPENSATION_PENDING
        )
        failure_code = str(payment.get("failureCode") or "PAYMENT_DECLINED")
        body = self._workflow_failure_response(
            workflow,
            code=failure_code,
            message="Payment was declined; the reservation is being released",
            retryable=False,
            details={
                "bookingId": workflow.booking_id,
                "workflowStatus": workflow.status.value,
                "compensationStatus": compensation,
            },
        )
        workflow.response_status = 402
        workflow.response_body = body
        await self.workflows.save(workflow)
        return 402, body

    async def _persist_payment_unknown(
        self,
        workflow: Workflow,
        ctx: RequestContext,
    ) -> None:
        workflow.status = WorkflowStatus.PAYMENT_UNKNOWN
        workflow.payment_status = PaymentStatus.UNKNOWN
        if workflow.booking_id and workflow.payment_id:
            try:
                booking = await self.booking.record_payment(
                    workflow.booking_id,
                    {
                        "paymentId": workflow.payment_id,
                        "paymentStatus": "UNKNOWN",
                        "expectedVersion": workflow.booking_version,
                        "evidence": booking_evidence(
                            resolved_payment_status="UNKNOWN",
                            details={
                                "source": "Payment",
                                "reconciliationRequired": True,
                            },
                        ),
                    },
                    workflow.idempotency_key + ":booking-payment-unknown",
                    ctx,
                )
                workflow.booking_version = _int_or_none(
                    booking.get("resourceVersion") or workflow.booking_version
                )
            except Exception as exc:
                # The workflow evidence remains durable even when Booking Service
                # cannot be updated during the same degraded request.
                workflow.evidence["recordPaymentUnknownErrorCode"] = (
                    self._safe_error_code(exc)
                )
        workflow.response_status = 202
        workflow.response_body = self._response(workflow)
        await self.workflows.save(workflow)

    async def _handle_unexpected_failure(
        self,
        workflow: Workflow,
        exc: Exception,
        ctx: RequestContext,
    ) -> None:
        workflow.evidence["lastErrorCode"] = self._safe_error_code(exc)
        workflow.evidence["lastFailedStepStatus"] = workflow.status.value
        # UNKNOWN counts as "money may already have moved". Releasing seats and failing the
        # booking is only safe when the payment is authoritatively not captured; an
        # indeterminate outcome goes to compensation so reconciliation can settle it.
        if workflow.payment_status in {PaymentStatus.CAPTURED, PaymentStatus.UNKNOWN}:
            workflow.status = WorkflowStatus.COMPENSATION_PENDING
            await self._mark_booking_compensation_pending(workflow, exc, ctx)
        elif workflow.status not in TERMINAL_WORKFLOW_STATUSES:
            await self._fail_pre_capture_workflow(workflow, exc, ctx)
        await self.workflows.save(workflow)

    async def _fail_pre_capture_workflow(
        self,
        workflow: Workflow,
        exc: Exception,
        ctx: RequestContext,
    ) -> None:
        """Compensate provisional resources and fail the authoritative Booking."""

        evidence: dict[str, Any] = {}
        complete = True
        compensation_required = False

        if workflow.payment_id:
            compensation_required = True
            payment_complete, payment_evidence = await self._compensate_payment(
                workflow,
                ctx,
            )
            complete = complete and payment_complete
            evidence["payment"] = payment_evidence

        if workflow.reservation_id:
            compensation_required = True
            try:
                await self.seat.release(
                    workflow.reservation_id,
                    "BOOKING_WORKFLOW_FAILED",
                    workflow.idempotency_key + ":pre-capture-release",
                    ctx,
                )
                evidence["reservation"] = {"status": "RELEASED"}
            except Exception as release_error:
                complete = False
                evidence["reservation"] = {
                    "status": "PENDING",
                    "errorCode": self._safe_error_code(release_error),
                }

        compensation_status = (
            "NOT_REQUIRED"
            if not compensation_required
            else "COMPLETED" if complete else "PENDING"
        )

        booking_failed = workflow.booking_id is None
        if workflow.booking_id:
            try:
                result = await self.booking.fail(
                    workflow.booking_id,
                    {
                        "failureCode": self._safe_error_code(exc),
                        "reason": "Booking workflow failed before payment capture",
                        "expectedVersion": workflow.booking_version,
                        "compensationStatus": compensation_status,
                        "evidence": booking_evidence(
                            reservation_released=(
                                evidence.get("reservation", {}).get("status")
                                == "RELEASED"
                            ),
                            compensation_completed=complete,
                            details=evidence,
                        ),
                    },
                    workflow.idempotency_key + ":pre-capture-fail",
                    ctx,
                )
                workflow.booking_version = _int_or_none(
                    result.get("resourceVersion") or workflow.booking_version
                )
                booking_failed = True
            except Exception as booking_error:
                complete = False
                workflow.evidence["bookingFailErrorCode"] = self._safe_error_code(
                    booking_error
                )

        workflow.status = (
            WorkflowStatus.FAILED
            if complete and booking_failed
            else WorkflowStatus.COMPENSATION_PENDING
        )

    async def _mark_booking_compensation_pending(
        self,
        workflow: Workflow,
        exc: Exception,
        ctx: RequestContext,
    ) -> None:
        if not workflow.booking_id:
            return
        try:
            result = await self.booking.fail(
                workflow.booking_id,
                {
                    "failureCode": self._safe_error_code(exc),
                    "reason": "A post-capture workflow step failed",
                    "expectedVersion": workflow.booking_version,
                    "compensationStatus": "PENDING",
                    "evidence": booking_evidence(
                        payment_captured=True,
                        compensation_completed=False,
                        details={
                            "orchestratorWorkflowId": workflow.workflow_id,
                            "failedStepStatus": workflow.evidence.get("lastFailedStepStatus"),
                        },
                    ),
                },
                workflow.idempotency_key + ":mark-compensation-pending",
                ctx,
            )
            workflow.booking_version = _int_or_none(
                result.get("resourceVersion") or workflow.booking_version
            )
        except Exception as mark_error:
            workflow.evidence["markCompensationErrorCode"] = self._safe_error_code(
                mark_error
            )

    async def _compensate_payment(
        self,
        workflow: Workflow,
        ctx: RequestContext,
    ) -> tuple[bool, dict[str, Any]]:
        if not workflow.payment_id:
            return True, {"status": "NOT_REQUIRED"}
        try:
            payment = await self.payment.get(workflow.payment_id, ctx)
            status = str(payment.get("status", "")).upper()
            if status in {"CAPTURED", "PARTIALLY_REFUNDED"}:
                # Payment Service remains authoritative for the refundable amount.
                refund = await self.payment.refund(
                    workflow.payment_id,
                    {
                        "reason": "BOOKING_WORKFLOW_FAILED",
                        "expectedVersion": payment.get("resourceVersion"),
                    },
                    workflow.idempotency_key + ":compensate-refund",
                    ctx,
                )
                return True, {
                    "status": "REFUNDED",
                    "refundId": refund.get("refundId"),
                    "amountMinor": refund.get("amountMinor"),
                }
            if status in {"PENDING", "AUTHORIZED"}:
                await self.payment.cancel(
                    workflow.payment_id,
                    {
                        "reason": "BOOKING_WORKFLOW_FAILED",
                        "expectedVersion": payment.get("resourceVersion"),
                    },
                    workflow.idempotency_key + ":compensate-payment-cancel",
                    ctx,
                )
                return True, {"status": "CANCELLED"}
            if status in {"REFUNDED", "CANCELLED", "FAILED"}:
                return True, {"status": status, "action": "NONE"}
            return False, {"status": status, "action": "RECONCILE"}
        except Exception as exc:
            return False, {
                "status": "PENDING",
                "errorCode": self._safe_error_code(exc),
            }

    async def _authoritative_ticket_ids(
        self,
        workflow: Workflow,
        ctx: RequestContext,
    ) -> list[str]:
        ids = list(workflow.ticket_ids)
        if not workflow.booking_id:
            return ids
        try:
            response = await self.ticket.list_booking(workflow.booking_id, ctx)
            rows = (
                response.get("tickets") or response.get("items") or []
                if isinstance(response, dict)
                else response
            )
            for row in rows or []:
                ticket_id = row.get("ticketId") if isinstance(row, dict) else row
                if ticket_id and str(ticket_id) not in ids:
                    ids.append(str(ticket_id))
        except Exception as exc:
            workflow.evidence["ticketDiscoveryErrorCode"] = self._safe_error_code(exc)
        workflow.ticket_ids = ids
        return ids

    async def _refresh_booking_version(
        self,
        workflow: Workflow,
        ctx: RequestContext,
    ) -> None:
        if not workflow.booking_id:
            return
        booking = await self.booking.get(workflow.booking_id, ctx)
        workflow.booking_version = _require_booking_version(booking)
        steps = workflow.evidence.setdefault("completedSteps", {})
        payment_status = str(booking.get("paymentStatus") or "").upper()
        reservation_status = str(booking.get("reservationStatus") or "").upper()
        booking_status = str(booking.get("status") or "").upper()
        if payment_status == "SUCCEEDED" or booking.get("paymentRecordedAt"):
            steps["paymentRecorded"] = True
        if reservation_status == "CONFIRMED" or booking.get("reservationConfirmedAt"):
            steps["seatConfirmed"] = True
            steps["reservationEvidenceConfirmed"] = True
        ticket_ids = booking.get("ticketIds") or []
        if ticket_ids and (booking.get("ticketsAttachedAt") or booking_status == "CONFIRMED"):
            workflow.ticket_ids = [str(ticket_id) for ticket_id in ticket_ids]
            steps["ticketsIssued"] = True
            steps["ticketsAttached"] = True
        if booking_status == "CONFIRMED":
            steps["bookingConfirmed"] = True
        reservation_version = _int_or_none(booking.get("reservationVersion"))
        if reservation_version is not None:
            workflow.reservation_version = reservation_version
        await self.workflows.save(workflow)

    @staticmethod
    def _workflow_items(workflow: Workflow) -> list[BookingItem]:
        items = [BookingItem(**item) for item in workflow.evidence.get("items", [])]
        if not items:
            raise EsbError(
                "WORKFLOW_EVIDENCE_INCOMPLETE",
                "Authoritative booking items are missing from workflow",
                409,
            )
        return items

    @staticmethod
    def _safe_error_code(exc: Exception) -> str:
        return exc.code if isinstance(exc, EsbError) else type(exc).__name__.upper()

    @staticmethod
    def _workflow_failure_response(
        workflow: Workflow,
        *,
        code: str,
        message: str,
        retryable: bool,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "correlationId": workflow.evidence.get("correlationId"),
            "traceId": workflow.evidence.get("traceId"),
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "details": details,
            },
        }

    @staticmethod
    def _public_booking_status(status: WorkflowStatus) -> str:
        mapping = {
            WorkflowStatus.STARTED: "PENDING",
            WorkflowStatus.SEAT_RESERVED: "SEAT_RESERVED",
            WorkflowStatus.PAYMENT_PROCESSING: "PAYMENT_PROCESSING",
            WorkflowStatus.PAYMENT_UNKNOWN: "PAYMENT_PROCESSING",
            WorkflowStatus.SEAT_CONFIRMED: "PAYMENT_PROCESSING",
            WorkflowStatus.TICKETS_ISSUED: "PAYMENT_PROCESSING",
            WorkflowStatus.CANCELLATION_PENDING: "COMPENSATION_PENDING",
            WorkflowStatus.COMPENSATION_PENDING: "COMPENSATION_PENDING",
            WorkflowStatus.CONFIRMED: "CONFIRMED",
            WorkflowStatus.FAILED: "FAILED",
            WorkflowStatus.CANCELLED: "CANCELLED",
        }
        return mapping[status]

    @staticmethod
    def _public_payment_status(status: PaymentStatus) -> str:
        # One mapping table, shared with everything that talks to Booking Service.
        return to_booking_payment_status(status)

    @staticmethod
    def _response(workflow: Workflow) -> dict[str, Any]:
        return {
            "workflowId": workflow.workflow_id,
            "bookingId": workflow.booking_id,
            "eventId": workflow.event_id,
            "seatIds": workflow.seat_ids,
            "status": BookingSaga._public_booking_status(workflow.status),
            "total": {
                "amountMinor": workflow.amount_minor,
                "currency": workflow.currency,
            },
            "reservationId": workflow.reservation_id,
            "paymentId": workflow.payment_id,
            "paymentStatus": BookingSaga._public_payment_status(workflow.payment_status),
            "ticketIds": workflow.ticket_ids,
            "correlationId": workflow.evidence.get("correlationId"),
            "resourceVersion": workflow.booking_version,
        }


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _require_booking_version(booking: dict[str, Any]) -> int:
    """Read the resourceVersion a Booking transition response must carry.

    Falling back to the version already held would send the *previous* version as the next
    command's expectedVersion. Booking Service uses optimistic concurrency, so that either
    conflicts or — worse, if the version happens to still match — applies a transition
    against state the orchestrator has not actually seen. A response without a usable
    version is a protocol error and the saga stops there.
    """
    version = _int_or_none(booking.get("resourceVersion"))
    if version is None:
        raise EsbError(
            "BOOKING_PROTOCOL_ERROR",
            "Booking Service returned a transition without resourceVersion",
            502,
            False,
        )
    return version


def _reservation_status(reservation: dict[str, Any]) -> str:
    """Read the reservation status a Seat response is required to carry.

    There is deliberately no default. A missing status, or one outside the canonical
    ReservationStatus enumeration, means the provider broke its own contract, which is a
    protocol error rather than a transient failure worth retrying — the same response would
    be just as invalid the second time.
    """
    raw = reservation.get("status")
    if not isinstance(raw, str) or raw.strip().upper() not in RESERVATION_STATUSES:
        raise EsbError(
            "SEAT_PROTOCOL_ERROR",
            "Seat Inventory returned a reservation without a valid status",
            502,
            False,
        )
    return raw.strip().upper()
