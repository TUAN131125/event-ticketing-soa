"""Booking response contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities import Booking
from app.domain.enums import (
    BookingStatus,
    CompensationAction,
    CompensationStatus,
    PaymentStatus,
    ReservationEvidenceStatus,
)
from app.domain.value_objects import (
    BookingHistoryEntry,
    BookingPage,
    ReconciliationCandidate,
    ReconciliationPage,
)


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class BookingItemResponse(ResponseModel):
    seat_id: str = Field(alias="seatId")
    ticket_type: str = Field(alias="ticketType")
    ticket_type_code: str = Field(alias="ticketTypeCode")
    unit_price: Decimal = Field(alias="unitPrice")


class BookingResponse(ResponseModel):
    id: str
    booking_id: str = Field(alias="bookingId")
    customer_id: str = Field(alias="customerId")
    event_id: str = Field(alias="eventId")
    reservation_id: str | None = Field(default=None, alias="reservationId")
    payment_method: str | None = Field(default=None, alias="paymentMethod")
    items: list[BookingItemResponse]
    seats: list[str]
    total: Decimal
    total_amount: Decimal = Field(alias="totalAmount")
    currency: str
    status: BookingStatus
    payment_status: PaymentStatus = Field(alias="paymentStatus")
    payment_id: str | None = Field(default=None, alias="paymentId")
    reservation_status: ReservationEvidenceStatus = Field(alias="reservationStatus")
    reservation_version: int | None = Field(default=None, alias="reservationVersion")
    reservation_expires_at: datetime | None = Field(
        default=None, alias="reservationExpiresAt"
    )
    ticket_ids: list[str] = Field(alias="ticketIds")
    failure_code: str | None = Field(default=None, alias="failureCode")
    failure_reason: str | None = Field(default=None, alias="failureReason")
    payment_failure_code: str | None = Field(default=None, alias="paymentFailureCode")
    cancellation_reason: str | None = Field(default=None, alias="cancellationReason")
    compensation_status: CompensationStatus = Field(alias="compensationStatus")
    compensation_action: CompensationAction = Field(alias="compensationAction")
    compensation_reason: str | None = Field(default=None, alias="compensationReason")
    intended_terminal_status: BookingStatus | None = Field(
        default=None, alias="intendedTerminalStatus"
    )
    payment_provider_reference: str | None = Field(
        default=None, alias="paymentProviderReference"
    )
    compensation_provider_reference: str | None = Field(
        default=None, alias="compensationProviderReference"
    )
    resource_version: int = Field(alias="resourceVersion")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    confirmed_at: datetime | None = Field(default=None, alias="confirmedAt")
    cancelled_at: datetime | None = Field(default=None, alias="cancelledAt")
    reservation_confirmed_at: datetime | None = Field(
        default=None, alias="reservationConfirmedAt"
    )
    reservation_released_at: datetime | None = Field(
        default=None, alias="reservationReleasedAt"
    )
    payment_recorded_at: datetime | None = Field(
        default=None, alias="paymentRecordedAt"
    )
    payment_refunded_at: datetime | None = Field(
        default=None, alias="paymentRefundedAt"
    )
    compensation_updated_at: datetime | None = Field(
        default=None, alias="compensationUpdatedAt"
    )
    tickets_attached_at: datetime | None = Field(
        default=None, alias="ticketsAttachedAt"
    )

    @classmethod
    def from_entity(cls, booking: Booking) -> "BookingResponse":
        return cls(
            id=booking.booking_id,
            bookingId=booking.booking_id,
            customerId=booking.customer_id,
            eventId=booking.event_id,
            reservationId=booking.reservation_id,
            paymentMethod=booking.payment_method,
            items=[
                BookingItemResponse(
                    seatId=item.seat_id,
                    ticketType=item.ticket_type,
                    ticketTypeCode=item.ticket_type,
                    unitPrice=item.unit_price,
                )
                for item in booking.items
            ],
            seats=[item.seat_id for item in booking.items],
            total=booking.total_amount,
            totalAmount=booking.total_amount,
            currency=booking.currency,
            status=booking.status,
            paymentStatus=booking.payment_status,
            paymentId=booking.payment_id,
            reservationStatus=booking.reservation_status,
            reservationVersion=booking.reservation_version,
            reservationExpiresAt=booking.reservation_expires_at,
            ticketIds=list(booking.ticket_ids),
            failureCode=booking.failure_code,
            failureReason=booking.failure_reason,
            paymentFailureCode=booking.payment_failure_code,
            cancellationReason=booking.cancellation_reason,
            compensationStatus=booking.compensation_status,
            compensationAction=booking.compensation_action,
            compensationReason=booking.compensation_reason,
            intendedTerminalStatus=booking.intended_terminal_status,
            paymentProviderReference=booking.payment_provider_reference,
            compensationProviderReference=booking.compensation_provider_reference,
            resourceVersion=booking.resource_version,
            createdAt=booking.created_at,
            updatedAt=booking.updated_at,
            confirmedAt=booking.confirmed_at,
            cancelledAt=booking.cancelled_at,
            reservationConfirmedAt=booking.reservation_confirmed_at,
            reservationReleasedAt=booking.reservation_released_at,
            paymentRecordedAt=booking.payment_recorded_at,
            paymentRefundedAt=booking.payment_refunded_at,
            compensationUpdatedAt=booking.compensation_updated_at,
            ticketsAttachedAt=booking.tickets_attached_at,
        )


class BookingPageResponse(ResponseModel):
    items: list[BookingResponse]
    page: int
    page_size: int = Field(alias="pageSize")
    total: int
    total_pages: int = Field(alias="totalPages")

    @classmethod
    def from_page(cls, result: BookingPage) -> "BookingPageResponse":
        return cls(
            items=[BookingResponse.from_entity(item) for item in result.items],
            page=result.page,
            pageSize=result.page_size,
            total=result.total,
            totalPages=result.total_pages,
        )


class ReconciliationCandidateResponse(ResponseModel):
    booking_id: str = Field(alias="bookingId")
    status: BookingStatus
    missing_evidence: list[str] = Field(alias="missingEvidence")
    recommended_action: str = Field(alias="recommendedAction")
    compensation_status: CompensationStatus = Field(alias="compensationStatus")
    compensation_action: CompensationAction = Field(alias="compensationAction")
    resource_version: int = Field(alias="resourceVersion")
    updated_at: datetime = Field(alias="updatedAt")

    @classmethod
    def from_candidate(
        cls, candidate: ReconciliationCandidate
    ) -> "ReconciliationCandidateResponse":
        return cls(
            bookingId=candidate.booking_id,
            status=BookingStatus(candidate.status),
            missingEvidence=list(candidate.missing_evidence),
            recommendedAction=candidate.recommended_action,
            compensationStatus=CompensationStatus(candidate.compensation_status),
            compensationAction=CompensationAction(candidate.compensation_action),
            resourceVersion=candidate.resource_version,
            updatedAt=candidate.updated_at,
        )


class ReconciliationPageResponse(ResponseModel):
    items: list[ReconciliationCandidateResponse]
    page: int
    page_size: int = Field(alias="pageSize")
    total: int
    total_pages: int = Field(alias="totalPages")

    @classmethod
    def from_page(cls, result: ReconciliationPage) -> "ReconciliationPageResponse":
        return cls(
            items=[
                ReconciliationCandidateResponse.from_candidate(item)
                for item in result.items
            ],
            page=result.page,
            pageSize=result.page_size,
            total=result.total,
            totalPages=result.total_pages,
        )


class BookingHistoryEntryResponse(ResponseModel):
    operation: str
    previous_status: str | None = Field(alias="previousStatus")
    new_status: str = Field(alias="newStatus")
    caller_service: str = Field(alias="callerService")
    actor_id: str | None = Field(default=None, alias="actorId")
    correlation_id: str = Field(alias="correlationId")
    idempotency_key: str = Field(alias="idempotencyKey")
    resource_version: int = Field(alias="resourceVersion")
    details: dict[str, Any]
    occurred_at: datetime = Field(alias="occurredAt")

    @classmethod
    def from_value(cls, value: BookingHistoryEntry) -> "BookingHistoryEntryResponse":
        return cls(
            operation=value.operation,
            previousStatus=value.previous_status,
            newStatus=value.new_status,
            callerService=value.caller_service,
            actorId=value.actor_id,
            correlationId=value.correlation_id,
            idempotencyKey=value.idempotency_key,
            resourceVersion=value.resource_version,
            details=value.details,
            occurredAt=value.occurred_at,
        )


class BookingHistoryResponse(ResponseModel):
    booking_id: str = Field(alias="bookingId")
    items: list[BookingHistoryEntryResponse]
