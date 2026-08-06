"""Translation between Booking aggregate and ORM rows."""

from __future__ import annotations

from decimal import Decimal

from app.domain.entities import Booking
from app.domain.enums import (
    BookingStatus,
    CompensationAction,
    CompensationStatus,
    PaymentStatus,
    ReservationEvidenceStatus,
)
from app.domain.value_objects import BookingItem
from app.infrastructure.database.models import BookingItemModel, BookingModel


def model_to_entity(model: BookingModel) -> Booking:
    return Booking(
        booking_id=model.booking_id,
        customer_id=model.customer_id,
        event_id=model.event_id,
        reservation_id=model.reservation_id,
        payment_method=model.payment_method,
        items=tuple(
            BookingItem(
                seat_id=item.seat_id,
                ticket_type=item.ticket_type,
                unit_price=Decimal(item.unit_price),
            )
            for item in model.items
        ),
        total_amount=Decimal(model.total_amount),
        currency=model.currency,
        status=BookingStatus(model.status),
        payment_status=PaymentStatus(model.payment_status),
        reservation_status=ReservationEvidenceStatus(model.reservation_status),
        compensation_status=CompensationStatus(model.compensation_status),
        compensation_action=CompensationAction(model.compensation_action),
        resource_version=model.resource_version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        payment_id=model.payment_id,
        ticket_ids=tuple(model.ticket_ids),
        failure_code=model.failure_code,
        failure_reason=model.failure_reason,
        payment_failure_code=model.payment_failure_code,
        cancellation_reason=model.cancellation_reason,
        compensation_reason=model.compensation_reason,
        intended_terminal_status=(
            BookingStatus(model.intended_terminal_status)
            if model.intended_terminal_status
            else None
        ),
        reservation_version=model.reservation_version,
        reservation_expires_at=model.reservation_expires_at,
        payment_provider_reference=model.payment_provider_reference,
        compensation_provider_reference=model.compensation_provider_reference,
        confirmed_at=model.confirmed_at,
        cancelled_at=model.cancelled_at,
        reservation_confirmed_at=model.reservation_confirmed_at,
        reservation_released_at=model.reservation_released_at,
        payment_recorded_at=model.payment_recorded_at,
        payment_refunded_at=model.payment_refunded_at,
        compensation_updated_at=model.compensation_updated_at,
        tickets_attached_at=model.tickets_attached_at,
    )


def entity_to_model(booking: Booking) -> BookingModel:
    return BookingModel(
        booking_id=booking.booking_id,
        customer_id=booking.customer_id,
        event_id=booking.event_id,
        reservation_id=booking.reservation_id,
        payment_method=booking.payment_method,
        status=booking.status,
        payment_status=booking.payment_status,
        reservation_status=booking.reservation_status,
        compensation_status=booking.compensation_status,
        compensation_action=booking.compensation_action,
        total_amount=booking.total_amount,
        currency=booking.currency,
        payment_id=booking.payment_id,
        payment_provider_reference=booking.payment_provider_reference,
        compensation_provider_reference=booking.compensation_provider_reference,
        payment_failure_code=booking.payment_failure_code,
        failure_code=booking.failure_code,
        failure_reason=booking.failure_reason,
        cancellation_reason=booking.cancellation_reason,
        compensation_reason=booking.compensation_reason,
        intended_terminal_status=(
            booking.intended_terminal_status.value
            if booking.intended_terminal_status
            else None
        ),
        reservation_version=booking.reservation_version,
        ticket_ids=list(booking.ticket_ids),
        resource_version=booking.resource_version,
        created_at=booking.created_at,
        updated_at=booking.updated_at,
        reservation_expires_at=booking.reservation_expires_at,
        confirmed_at=booking.confirmed_at,
        cancelled_at=booking.cancelled_at,
        reservation_confirmed_at=booking.reservation_confirmed_at,
        reservation_released_at=booking.reservation_released_at,
        payment_recorded_at=booking.payment_recorded_at,
        payment_refunded_at=booking.payment_refunded_at,
        compensation_updated_at=booking.compensation_updated_at,
        tickets_attached_at=booking.tickets_attached_at,
        items=[
            BookingItemModel(
                seat_id=item.seat_id,
                ticket_type=item.ticket_type,
                unit_price=item.unit_price,
                created_at=booking.created_at,
            )
            for item in booking.items
        ],
    )


def apply_entity(model: BookingModel, booking: Booking) -> None:
    model.reservation_id = booking.reservation_id
    model.status = booking.status
    model.payment_status = booking.payment_status
    model.reservation_status = booking.reservation_status
    model.compensation_status = booking.compensation_status
    model.compensation_action = booking.compensation_action
    model.ticket_ids = list(booking.ticket_ids)
    model.payment_id = booking.payment_id
    model.payment_provider_reference = booking.payment_provider_reference
    model.compensation_provider_reference = booking.compensation_provider_reference
    model.payment_failure_code = booking.payment_failure_code
    model.failure_code = booking.failure_code
    model.failure_reason = booking.failure_reason
    model.cancellation_reason = booking.cancellation_reason
    model.compensation_reason = booking.compensation_reason
    model.intended_terminal_status = (
        booking.intended_terminal_status.value
        if booking.intended_terminal_status
        else None
    )
    model.reservation_version = booking.reservation_version
    model.resource_version = booking.resource_version
    model.updated_at = booking.updated_at
    model.reservation_expires_at = booking.reservation_expires_at
    model.confirmed_at = booking.confirmed_at
    model.cancelled_at = booking.cancelled_at
    model.reservation_confirmed_at = booking.reservation_confirmed_at
    model.reservation_released_at = booking.reservation_released_at
    model.payment_recorded_at = booking.payment_recorded_at
    model.payment_refunded_at = booking.payment_refunded_at
    model.compensation_updated_at = booking.compensation_updated_at
    model.tickets_attached_at = booking.tickets_attached_at
