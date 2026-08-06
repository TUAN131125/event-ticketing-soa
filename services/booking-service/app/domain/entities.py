"""Booking aggregate and business state machine.

Booking Service is authoritative for the booking lifecycle.  The orchestrator
may submit evidence produced by Seat, Payment and Ticket services, but only the
aggregate decides whether that evidence can advance, fail or cancel a booking.
No method in this module performs network or database I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.enums import (
    BookingStatus,
    CompensationAction,
    CompensationStatus,
    PaymentStatus,
    ReservationEvidenceStatus,
)
from app.domain.exceptions import (
    CompensationEvidenceRequired,
    InvalidRequest,
    MissingPaymentEvidence,
    MissingReservationEvidence,
    MissingTicketEvidence,
    VersionConflict,
)
from app.domain.rules import (
    ensure_transition_allowed,
    normalize_new_booking,
    validate_identifier,
    validate_reason,
    validate_ticket_ids,
)
from app.domain.value_objects import (
    BookingItem,
    CompensationEvidence,
    NewBookingRequest,
)


ACTIVE_BOOKING_STATUSES = frozenset(
    {
        BookingStatus.PENDING,
        BookingStatus.SEAT_RESERVED,
        BookingStatus.PAYMENT_PROCESSING,
    }
)
TERMINAL_BOOKING_STATUSES = frozenset(
    {BookingStatus.CONFIRMED, BookingStatus.FAILED, BookingStatus.CANCELLED}
)


@dataclass(slots=True)
class Booking:
    booking_id: str
    customer_id: str
    event_id: str
    items: tuple[BookingItem, ...]
    total_amount: Decimal
    currency: str
    status: BookingStatus
    payment_status: PaymentStatus
    reservation_status: ReservationEvidenceStatus
    compensation_status: CompensationStatus
    compensation_action: CompensationAction
    resource_version: int
    created_at: datetime
    updated_at: datetime
    reservation_id: str | None = None
    payment_method: str | None = None
    payment_id: str | None = None
    ticket_ids: tuple[str, ...] = ()
    failure_code: str | None = None
    failure_reason: str | None = None
    payment_failure_code: str | None = None
    cancellation_reason: str | None = None
    compensation_reason: str | None = None
    intended_terminal_status: BookingStatus | None = None
    reservation_version: int | None = None
    reservation_expires_at: datetime | None = None
    payment_provider_reference: str | None = None
    compensation_provider_reference: str | None = None
    confirmed_at: datetime | None = None
    cancelled_at: datetime | None = None
    reservation_confirmed_at: datetime | None = None
    reservation_released_at: datetime | None = None
    payment_recorded_at: datetime | None = None
    payment_refunded_at: datetime | None = None
    compensation_updated_at: datetime | None = None
    tickets_attached_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        booking_id: str,
        customer_id: str,
        event_id: str,
        items: tuple[BookingItem, ...],
        currency: str,
        now: datetime,
        total_amount: Decimal | None = None,
        reservation_id: str | None = None,
        payment_method: str | None = None,
    ) -> Booking:
        request = normalize_new_booking(
            customer_id=customer_id,
            event_id=event_id,
            reservation_id=reservation_id,
            payment_method=payment_method,
            items=items,
            total_amount=total_amount,
            currency=currency,
        )
        return cls.from_request(
            booking_id=validate_identifier(booking_id, "bookingId"),
            request=request,
            now=now,
        )

    @classmethod
    def from_request(
        cls, *, booking_id: str, request: NewBookingRequest, now: datetime
    ) -> Booking:
        return cls(
            booking_id=validate_identifier(booking_id, "bookingId"),
            customer_id=request.customer_id,
            event_id=request.event_id,
            reservation_id=request.reservation_id,
            payment_method=request.payment_method,
            items=request.items,
            total_amount=request.total_amount,
            currency=request.currency,
            status=BookingStatus.PENDING,
            payment_status=PaymentStatus.PENDING,
            reservation_status=ReservationEvidenceStatus.PENDING,
            compensation_status=CompensationStatus.NOT_REQUIRED,
            compensation_action=CompensationAction.NONE,
            resource_version=1,
            created_at=now,
            updated_at=now,
        )

    def attach_reservation(
        self,
        *,
        reservation_id: str,
        expected_version: int,
        now: datetime,
        expires_at: datetime | None = None,
        reservation_version: int | None = None,
        confirmed: bool = False,
    ) -> None:
        """Record ReserveSeats evidence and move ``PENDING`` to ``SEAT_RESERVED``.

        The new canonical contract supplies ``expires_at`` for a normal hold.
        ``confirmed=True`` remains supported for the legacy endpoint whose
        AttachReservation command represented already-confirmed seat evidence.
        """
        self._check_version(expected_version)
        if self.status not in {BookingStatus.PENDING, BookingStatus.SEAT_RESERVED}:
            raise InvalidRequest(
                "Reservation evidence can only be attached before payment starts"
            )

        normalized_id = validate_identifier(reservation_id, "reservationId")
        if self.reservation_id is not None and normalized_id != self.reservation_id:
            raise InvalidRequest("reservationId does not match this booking")
        if reservation_version is not None and reservation_version < 1:
            raise InvalidRequest("reservationVersion must be at least 1")
        if expires_at is not None and expires_at <= now:
            raise InvalidRequest("reservationExpiresAt must be in the future")
        if not confirmed and expires_at is None and self.reservation_expires_at is None:
            raise InvalidRequest(
                "reservationExpiresAt is required for RESERVED evidence"
            )

        self.reservation_id = normalized_id
        self.reservation_expires_at = expires_at or self.reservation_expires_at
        self.reservation_version = reservation_version or self.reservation_version
        self.reservation_status = (
            ReservationEvidenceStatus.CONFIRMED
            if confirmed
            else ReservationEvidenceStatus.RESERVED
        )
        if confirmed:
            self.reservation_confirmed_at = self.reservation_confirmed_at or now

        if self.status == BookingStatus.PENDING:
            ensure_transition_allowed(self.status, BookingStatus.SEAT_RESERVED)
            self.status = BookingStatus.SEAT_RESERVED
        self._touch(now)

    def confirm_reservation(
        self,
        *,
        reservation_id: str,
        expected_version: int,
        now: datetime,
        reservation_version: int | None = None,
    ) -> None:
        """Record authoritative ConfirmSeats evidence.

        In the canonical workflow ConfirmSeats happens after a successful
        payment.  The legacy AttachReservation path can still mark the hold as
        confirmed before payment, so this method only enforces the ordering for
        the dedicated confirmation command.
        """
        self._check_version(expected_version)
        if self.status == BookingStatus.SEAT_RESERVED:
            raise MissingPaymentEvidence()
        if self.status != BookingStatus.PAYMENT_PROCESSING:
            raise InvalidRequest(
                "Reservation confirmation is only valid after payment starts"
            )
        if self.payment_status != PaymentStatus.SUCCEEDED:
            raise MissingPaymentEvidence()

        normalized_id = validate_identifier(reservation_id, "reservationId")
        if self.reservation_id != normalized_id:
            raise InvalidRequest("reservationId does not match this booking")
        if self.reservation_status not in {
            ReservationEvidenceStatus.RESERVED,
            ReservationEvidenceStatus.UNKNOWN,
            ReservationEvidenceStatus.CONFIRMED,
        }:
            raise InvalidRequest("Reservation cannot be confirmed in its current state")
        if reservation_version is not None:
            if reservation_version < 1:
                raise InvalidRequest("reservationVersion must be at least 1")
            self.reservation_version = reservation_version

        self.reservation_status = ReservationEvidenceStatus.CONFIRMED
        self.reservation_confirmed_at = self.reservation_confirmed_at or now
        self._touch(now)

    def start_payment(
        self, *, payment_id: str, expected_version: int, now: datetime
    ) -> None:
        self._check_version(expected_version)
        if self.status != BookingStatus.SEAT_RESERVED:
            raise InvalidRequest(
                "Payment can only start after reservation evidence is attached"
            )
        if self.reservation_status not in {
            ReservationEvidenceStatus.RESERVED,
            ReservationEvidenceStatus.CONFIRMED,
        }:
            raise MissingReservationEvidence()
        if (
            self.reservation_status == ReservationEvidenceStatus.RESERVED
            and self.reservation_expires_at is not None
            and self.reservation_expires_at <= now
        ):
            raise InvalidRequest("Reservation evidence has expired")
        if self.payment_status != PaymentStatus.PENDING:
            raise InvalidRequest("Payment evidence has already been started")

        self.payment_id = validate_identifier(payment_id, "paymentId")
        self.payment_status = PaymentStatus.PROCESSING
        ensure_transition_allowed(self.status, BookingStatus.PAYMENT_PROCESSING)
        self.status = BookingStatus.PAYMENT_PROCESSING
        self._touch(now)

    def record_payment(
        self,
        *,
        payment_id: str,
        expected_version: int,
        now: datetime,
        payment_status: PaymentStatus | None = None,
        succeeded: bool | None = None,
        provider_reference: str | None = None,
        failure_code: str | None = None,
    ) -> None:
        """Record Payment Service evidence, including an unknown outcome.

        ``succeeded`` is the v1.1 compatibility input; new callers submit the
        normalized ``payment_status``.  A payment that was UNKNOWN may also be
        resolved while the booking waits in ``COMPENSATION_PENDING``.
        """
        self._check_version(expected_version)
        resolved_status = self._resolve_payment_input(payment_status, succeeded)
        if self.status not in {
            BookingStatus.PAYMENT_PROCESSING,
            BookingStatus.COMPENSATION_PENDING,
        }:
            raise InvalidRequest(
                "Payment evidence can only be recorded for an active payment workflow"
            )
        if (
            self.status == BookingStatus.COMPENSATION_PENDING
            and self.payment_status
            not in {PaymentStatus.UNKNOWN, PaymentStatus.PROCESSING}
        ):
            raise InvalidRequest(
                "Only an unknown payment can be reconciled during compensation"
            )
        if self.payment_status not in {PaymentStatus.PROCESSING, PaymentStatus.UNKNOWN}:
            raise InvalidRequest("Payment outcome has already been recorded")
        if validate_identifier(payment_id, "paymentId") != self.payment_id:
            raise InvalidRequest("paymentId does not match the started payment")

        self._apply_payment_outcome(
            resolved_status,
            now=now,
            provider_reference=provider_reference,
            failure_code=failure_code,
        )
        if self.status == BookingStatus.COMPENSATION_PENDING:
            # UNKNOWN was the first safe action.  Once Payment Service resolves
            # it, recompute the actual release/refund work without closing the
            # booking until explicit compensation evidence is recorded.
            self.compensation_action = self.required_compensation_action()
            self._mark_compensation_pending(self.compensation_action)
            self.compensation_updated_at = now
        self._touch(now)

    def attach_tickets(
        self, *, ticket_ids: tuple[str, ...], expected_version: int, now: datetime
    ) -> None:
        self._check_version(expected_version)
        if self.status != BookingStatus.PAYMENT_PROCESSING:
            raise InvalidRequest(
                "Ticket evidence can only be attached while payment is processing"
            )
        if self.payment_status != PaymentStatus.SUCCEEDED:
            raise MissingPaymentEvidence()
        if self.reservation_status != ReservationEvidenceStatus.CONFIRMED:
            raise MissingReservationEvidence()

        normalized = validate_ticket_ids(ticket_ids)
        if len(normalized) != len(self.items):
            raise InvalidRequest(
                "Exactly one ticket is required for each booking item",
                details={
                    "bookingItemCount": len(self.items),
                    "ticketCount": len(normalized),
                },
            )
        if self.ticket_ids and self.ticket_ids != normalized:
            raise InvalidRequest("Ticket evidence has already been attached")
        self.ticket_ids = normalized
        self.tickets_attached_at = self.tickets_attached_at or now
        self._touch(now)

    def confirm(self, *, expected_version: int, now: datetime) -> None:
        self._check_version(expected_version)
        ensure_transition_allowed(self.status, BookingStatus.CONFIRMED)
        if self.reservation_status != ReservationEvidenceStatus.CONFIRMED:
            raise MissingReservationEvidence()
        if self.payment_status != PaymentStatus.SUCCEEDED or self.payment_id is None:
            raise MissingPaymentEvidence()
        if len(self.ticket_ids) != len(self.items):
            raise MissingTicketEvidence()

        self.status = BookingStatus.CONFIRMED
        self.compensation_status = CompensationStatus.NOT_REQUIRED
        self.compensation_action = CompensationAction.NONE
        self.intended_terminal_status = None
        self.confirmed_at = now
        self._touch(now)

    def fail(
        self,
        *,
        failure_code: str,
        reason: str,
        expected_version: int,
        now: datetime,
        compensation_status: CompensationStatus | None = None,
        evidence: CompensationEvidence | None = None,
    ) -> None:
        self._check_version(expected_version)
        if self.status not in ACTIVE_BOOKING_STATUSES:
            raise InvalidRequest(
                "Only PENDING, SEAT_RESERVED or PAYMENT_PROCESSING bookings can fail"
            )
        self.failure_code = validate_identifier(failure_code, "failureCode")
        self.failure_reason = validate_reason(reason)
        self._begin_or_complete_terminal_transition(
            target=BookingStatus.FAILED,
            requested_status=compensation_status,
            evidence=evidence or CompensationEvidence(),
            now=now,
        )

    def cancel(
        self,
        *,
        reason: str,
        expected_version: int,
        now: datetime,
        payment_status: PaymentStatus | None = None,
        compensation_status: CompensationStatus | None = None,
        evidence: CompensationEvidence | None = None,
    ) -> None:
        self._check_version(expected_version)
        if self.status not in {
            BookingStatus.PENDING,
            BookingStatus.SEAT_RESERVED,
            BookingStatus.CONFIRMED,
        }:
            raise InvalidRequest(
                "Only PENDING, SEAT_RESERVED or CONFIRMED bookings can be cancelled"
            )
        self.cancellation_reason = validate_reason(reason)
        if payment_status is not None:
            self._apply_cancel_payment_status(payment_status, now)
        self._begin_or_complete_terminal_transition(
            target=BookingStatus.CANCELLED,
            requested_status=compensation_status,
            evidence=evidence or CompensationEvidence(),
            now=now,
        )

    def record_compensation(
        self,
        *,
        expected_version: int,
        now: datetime,
        compensation_status: CompensationStatus,
        evidence: CompensationEvidence,
        reason: str | None = None,
    ) -> None:
        self._check_version(expected_version)
        if self.status != BookingStatus.COMPENSATION_PENDING:
            raise InvalidRequest(
                "Compensation results can only be recorded for COMPENSATION_PENDING"
            )
        if compensation_status not in {
            CompensationStatus.COMPLETED,
            CompensationStatus.FAILED,
            CompensationStatus.PENDING,
        }:
            raise InvalidRequest("Invalid compensationStatus")
        if reason is not None:
            self.compensation_reason = validate_reason(reason, "compensationReason")

        action = self.compensation_action
        self._apply_compensation_evidence(evidence, now)
        if action == CompensationAction.RECONCILE_PAYMENT:
            action = self.required_compensation_action()
        self.compensation_action = action
        self._mark_compensation_pending(action)
        self.compensation_updated_at = now

        if compensation_status == CompensationStatus.COMPLETED:
            if not self._compensation_requirements_satisfied(action):
                raise CompensationEvidenceRequired(action.value)
            target = self.intended_terminal_status
            if target not in {BookingStatus.FAILED, BookingStatus.CANCELLED}:
                raise InvalidRequest("Compensation target is missing")
            ensure_transition_allowed(self.status, target)
            self.status = target
            self.compensation_status = CompensationStatus.COMPLETED
            self.intended_terminal_status = None
            if target == BookingStatus.CANCELLED:
                self.cancelled_at = now
        else:
            self.compensation_status = compensation_status
        self._touch(now)

    def required_compensation_action(self) -> CompensationAction:
        """Derive the remaining Saga work from authoritative evidence."""
        if self.payment_status in {
            PaymentStatus.PROCESSING,
            PaymentStatus.UNKNOWN,
        }:
            return CompensationAction.RECONCILE_PAYMENT

        release_required = self.reservation_status in {
            ReservationEvidenceStatus.RESERVED,
            ReservationEvidenceStatus.CONFIRMED,
            ReservationEvidenceStatus.RELEASE_PENDING,
            ReservationEvidenceStatus.UNKNOWN,
        }
        refund_required = self.payment_status in {
            PaymentStatus.SUCCEEDED,
            PaymentStatus.REFUND_PENDING,
        }
        if release_required and refund_required:
            return CompensationAction.RELEASE_AND_REFUND
        if release_required:
            return CompensationAction.RELEASE_RESERVATION
        if refund_required:
            return CompensationAction.REFUND_PAYMENT
        return CompensationAction.NONE

    def _begin_or_complete_terminal_transition(
        self,
        *,
        target: BookingStatus,
        requested_status: CompensationStatus | None,
        evidence: CompensationEvidence,
        now: datetime,
    ) -> None:
        # Compute the obligation before evidence mutates RELEASE/REFUND status so
        # audit data retains which compensation was actually required.
        action = self.required_compensation_action()
        self._apply_compensation_evidence(evidence, now)
        if action == CompensationAction.RECONCILE_PAYMENT:
            action = self.required_compensation_action()

        requirements_satisfied = self._compensation_requirements_satisfied(action)
        requested = requested_status or (
            CompensationStatus.COMPLETED
            if requirements_satisfied
            else CompensationStatus.PENDING
        )
        if requested == CompensationStatus.NOT_REQUIRED:
            if action != CompensationAction.NONE:
                raise CompensationEvidenceRequired(action.value)
            requested = CompensationStatus.COMPLETED

        if requested == CompensationStatus.COMPLETED:
            if not requirements_satisfied:
                raise CompensationEvidenceRequired(action.value)
            ensure_transition_allowed(self.status, target)
            self.status = target
            self.compensation_status = (
                CompensationStatus.NOT_REQUIRED
                if action == CompensationAction.NONE
                else CompensationStatus.COMPLETED
            )
            self.compensation_action = action
            self.intended_terminal_status = None
            if target == BookingStatus.CANCELLED:
                self.cancelled_at = now
        else:
            if requested not in {CompensationStatus.PENDING, CompensationStatus.FAILED}:
                raise InvalidRequest("Invalid compensationStatus")
            ensure_transition_allowed(self.status, BookingStatus.COMPENSATION_PENDING)
            self.status = BookingStatus.COMPENSATION_PENDING
            self.compensation_status = requested
            self.compensation_action = action
            self.intended_terminal_status = target
            self._mark_compensation_pending(action)

        self.compensation_updated_at = now
        self._touch(now)

    def _apply_compensation_evidence(
        self, evidence: CompensationEvidence, now: datetime
    ) -> None:
        if evidence.resolved_payment_status is not None:
            if self.payment_status not in {
                PaymentStatus.UNKNOWN,
                PaymentStatus.PROCESSING,
            } and evidence.resolved_payment_status != self.payment_status:
                raise InvalidRequest(
                    "Resolved payment status would regress authoritative evidence"
                )
            if evidence.resolved_payment_status not in {
                PaymentStatus.SUCCEEDED,
                PaymentStatus.FAILED,
                PaymentStatus.UNKNOWN,
                PaymentStatus.REFUNDED,
            }:
                raise InvalidRequest("Invalid resolvedPaymentStatus")
            self.payment_status = evidence.resolved_payment_status
            self.payment_recorded_at = evidence.verified_at or now
            if self.payment_status != PaymentStatus.FAILED:
                self.payment_failure_code = None

        if evidence.reservation_released:
            if self.reservation_id is None:
                raise InvalidRequest(
                    "Cannot record release evidence without reservationId"
                )
            self.reservation_status = ReservationEvidenceStatus.RELEASED
            self.reservation_released_at = evidence.verified_at or now

        if evidence.payment_refunded:
            if self.payment_id is None:
                raise InvalidRequest("Cannot record refund evidence without paymentId")
            if self.payment_status not in {
                PaymentStatus.SUCCEEDED,
                PaymentStatus.REFUND_PENDING,
                PaymentStatus.REFUNDED,
            }:
                raise InvalidRequest(
                    "Refund evidence requires a previously successful payment"
                )
            self.payment_status = PaymentStatus.REFUNDED
            self.payment_refunded_at = evidence.verified_at or now

        if evidence.provider_reference is not None:
            self.compensation_provider_reference = validate_identifier(
                evidence.provider_reference, "providerReference"
            )

    def _mark_compensation_pending(self, action: CompensationAction) -> None:
        if action in {
            CompensationAction.RELEASE_RESERVATION,
            CompensationAction.RELEASE_AND_REFUND,
        } and self.reservation_status != ReservationEvidenceStatus.RELEASED:
            self.reservation_status = ReservationEvidenceStatus.RELEASE_PENDING
        if action in {
            CompensationAction.REFUND_PAYMENT,
            CompensationAction.RELEASE_AND_REFUND,
        } and self.payment_status != PaymentStatus.REFUNDED:
            self.payment_status = PaymentStatus.REFUND_PENDING

    def _compensation_requirements_satisfied(
        self, action: CompensationAction
    ) -> bool:
        if action == CompensationAction.RECONCILE_PAYMENT:
            return self.payment_status not in {
                PaymentStatus.UNKNOWN,
                PaymentStatus.PROCESSING,
            }
        if action in {
            CompensationAction.RELEASE_RESERVATION,
            CompensationAction.RELEASE_AND_REFUND,
        } and self.reservation_status != ReservationEvidenceStatus.RELEASED:
            return False
        if action in {
            CompensationAction.REFUND_PAYMENT,
            CompensationAction.RELEASE_AND_REFUND,
        } and self.payment_status != PaymentStatus.REFUNDED:
            return False
        return True

    def _apply_payment_outcome(
        self,
        status: PaymentStatus,
        *,
        now: datetime,
        provider_reference: str | None,
        failure_code: str | None,
    ) -> None:
        if status not in {
            PaymentStatus.SUCCEEDED,
            PaymentStatus.FAILED,
            PaymentStatus.UNKNOWN,
        }:
            raise InvalidRequest(
                "paymentStatus must be SUCCEEDED, FAILED or UNKNOWN"
            )
        if provider_reference is not None:
            normalized_reference = validate_identifier(
                provider_reference, "providerReference"
            )
            if (
                self.payment_provider_reference is not None
                and self.payment_provider_reference != normalized_reference
            ):
                raise InvalidRequest("Payment provider evidence does not match")
            self.payment_provider_reference = normalized_reference
        self.payment_status = status
        self.payment_failure_code = (
            validate_identifier(failure_code, "failureCode")
            if status == PaymentStatus.FAILED and failure_code is not None
            else None
        )
        self.payment_recorded_at = now

    def _apply_cancel_payment_status(
        self, new_status: PaymentStatus, now: datetime
    ) -> None:
        allowed: dict[PaymentStatus, frozenset[PaymentStatus]] = {
            PaymentStatus.PENDING: frozenset(
                {PaymentStatus.PENDING, PaymentStatus.FAILED, PaymentStatus.UNKNOWN}
            ),
            PaymentStatus.PROCESSING: frozenset(
                {PaymentStatus.FAILED, PaymentStatus.UNKNOWN}
            ),
            PaymentStatus.UNKNOWN: frozenset(
                {
                    PaymentStatus.UNKNOWN,
                    PaymentStatus.FAILED,
                    PaymentStatus.SUCCEEDED,
                    PaymentStatus.REFUNDED,
                }
            ),
            PaymentStatus.SUCCEEDED: frozenset(
                {
                    PaymentStatus.SUCCEEDED,
                    PaymentStatus.REFUND_PENDING,
                    PaymentStatus.REFUNDED,
                }
            ),
            PaymentStatus.FAILED: frozenset({PaymentStatus.FAILED}),
            PaymentStatus.REFUND_PENDING: frozenset(
                {PaymentStatus.REFUND_PENDING, PaymentStatus.REFUNDED}
            ),
            PaymentStatus.REFUNDED: frozenset({PaymentStatus.REFUNDED}),
        }
        if new_status not in allowed[self.payment_status]:
            raise InvalidRequest("paymentStatus would regress authoritative evidence")
        self.payment_status = new_status
        self.payment_recorded_at = now
        if new_status == PaymentStatus.REFUNDED:
            self.payment_refunded_at = now

    @staticmethod
    def _resolve_payment_input(
        payment_status: PaymentStatus | None, succeeded: bool | None
    ) -> PaymentStatus:
        if payment_status is None and succeeded is None:
            raise InvalidRequest("paymentStatus or succeeded is required")
        legacy = (
            PaymentStatus.SUCCEEDED
            if succeeded is True
            else PaymentStatus.FAILED
            if succeeded is False
            else None
        )
        if (
            payment_status is not None
            and legacy is not None
            and payment_status != legacy
        ):
            raise InvalidRequest("paymentStatus and succeeded disagree")
        resolved = payment_status or legacy
        if resolved is None:
            raise InvalidRequest("paymentStatus or succeeded is required")
        return resolved

    def _check_version(self, expected_version: int) -> None:
        if self.resource_version != expected_version:
            raise VersionConflict(expected_version, self.resource_version)

    def _touch(self, now: datetime) -> None:
        self.updated_at = now
        self.resource_version += 1
