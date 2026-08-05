"""Closed canonical Booking request schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class MoneyRequest(ClosedModel):
    amount_minor: int = Field(alias="amountMinor", ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class BookingItemRequest(ClosedModel):
    seat_id: str = Field(alias="seatId", min_length=1, max_length=128)
    ticket_type_code: str = Field(alias="ticketTypeCode", min_length=1, max_length=128)
    unit_price: MoneyRequest = Field(alias="unitPrice")


class CreateBookingRequest(ClosedModel):
    customer_id: str = Field(alias="customerId", min_length=1, max_length=128)
    event_id: str = Field(alias="eventId", min_length=1, max_length=128)
    items: list[BookingItemRequest] = Field(min_length=1, max_length=50)


class TransitionEvidence(ClosedModel):
    provider_reference: str | None = Field(default=None, alias="providerReference")
    reservation_expires_at: datetime | None = Field(
        default=None, alias="reservationExpiresAt"
    )
    seat_confirmed: bool | None = Field(default=None, alias="seatConfirmed")
    payment_captured: bool | None = Field(default=None, alias="paymentCaptured")
    tickets_issued: bool | None = Field(default=None, alias="ticketsIssued")
    compensation_completed: bool | None = Field(
        default=None, alias="compensationCompleted"
    )
    verified_at: datetime | None = Field(default=None, alias="verifiedAt")

    @model_validator(mode="after")
    def require_evidence(self) -> "TransitionEvidence":
        if not self.model_fields_set:
            raise ValueError("evidence must contain at least one property")
        for value in (self.reservation_expires_at, self.verified_at):
            if value is not None and (
                value.tzinfo is None or value.utcoffset() is None
            ):
                raise ValueError("evidence timestamps must include UTC offset")
        return self


class TransitionCommand(ClosedModel):
    reservation_id: str | None = Field(default=None, alias="reservationId")
    payment_id: str | None = Field(default=None, alias="paymentId")
    payment_status: Literal["CAPTURED", "FAILED", "UNKNOWN"] | None = Field(
        default=None, alias="paymentStatus"
    )
    ticket_ids: list[str] | None = Field(default=None, alias="ticketIds")
    reason_code: str | None = Field(default=None, alias="reasonCode")
    compensation_status: Literal["NOT_REQUIRED", "COMPLETED", "PENDING"] | None = Field(
        default=None, alias="compensationStatus"
    )
    evidence: TransitionEvidence | None = None


class ReservationTransition(TransitionCommand):
    reservation_id: str = Field(alias="reservationId")
    evidence: TransitionEvidence


class PaymentStartedTransition(TransitionCommand):
    payment_id: str = Field(alias="paymentId")


class PaymentResultTransition(TransitionCommand):
    payment_id: str = Field(alias="paymentId")
    payment_status: Literal["CAPTURED", "FAILED", "UNKNOWN"] = Field(
        alias="paymentStatus"
    )
    evidence: TransitionEvidence


class TicketsTransition(TransitionCommand):
    ticket_ids: list[str] = Field(alias="ticketIds", min_length=1)
    evidence: TransitionEvidence


class ConfirmTransition(TransitionCommand):
    reservation_id: str = Field(alias="reservationId")
    payment_id: str = Field(alias="paymentId")
    payment_status: Literal["CAPTURED"] = Field(alias="paymentStatus")
    ticket_ids: list[str] = Field(alias="ticketIds", min_length=1)
    evidence: TransitionEvidence

    @model_validator(mode="after")
    def require_confirmation_evidence(self) -> "ConfirmTransition":
        if not all(
            (
                self.evidence.seat_confirmed is True,
                self.evidence.payment_captured is True,
                self.evidence.tickets_issued is True,
                self.evidence.verified_at is not None,
            )
        ):
            raise ValueError("confirmation evidence is incomplete")
        return self


class TerminalTransition(TransitionCommand):
    reason_code: str = Field(alias="reasonCode")
    evidence: TransitionEvidence
    compensation_status: Literal["NOT_REQUIRED", "COMPLETED", "PENDING"] = Field(
        alias="compensationStatus"
    )


class BookingAccessDecisionRequest(ClosedModel):
    identity_subject: str = Field(alias="identitySubject", min_length=1, max_length=128)
    roles: set[Literal["CUSTOMER", "ADMIN", "CHECKIN_STAFF", "SERVICE"]] = Field(
        min_length=1
    )
