"""Contract operation dispatch and application mapping."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from lxml import etree
from sqlalchemy.orm import Session

from app.application.check_availability import check_availability
from app.application.common import RequestContext
from app.application.confirm_seats import confirm_seats
from app.application.executor import execute_database_operation
from app.application.expire_reservations import expire_reservations
from app.application.extend_reservation import extend_reservation
from app.application.get_reservation import get_reservation_view
from app.application.get_seat_map import get_seat_map
from app.application.release_seats import release_seats
from app.application.reserve_seats import reserve_seats
from app.config import Settings
from app.domain.exceptions import InvalidRequest
from app.soap.envelope import (
    append,
    append_reservation,
    append_seat,
    element,
)
from app.soap.types import (
    child_int,
    child_text,
    iso_datetime,
    operation_name,
    request_context,
    seat_ids,
)


def dispatch(operation: etree._Element, settings: Settings) -> etree._Element:
    name = operation_name(operation)
    handlers: dict[str, Callable[[etree._Element, Settings], etree._Element]] = {
        "GetSeatMap": _get_seat_map,
        "CheckAvailability": _check_availability,
        "ReserveSeats": _reserve_seats,
        "GetReservation": _get_reservation,
        "ExtendReservation": _extend_reservation,
        "ConfirmSeats": _confirm_seats,
        "ReleaseSeats": _release_seats,
        "ExpireReservations": _expire_reservations,
    }
    handler = handlers.get(name)
    if handler is None:
        raise InvalidRequest(f"Unsupported SOAP operation: {name}")
    return handler(operation, settings)


def _execute(
    settings: Settings,
    operation: Callable[[Session], etree._Element],
    *,
    retries: int = 1,
) -> etree._Element:
    return execute_database_operation(settings, operation, max_retries=retries)


def _context_response(name: str, context: RequestContext) -> etree._Element:
    response = element(f"{name}Response")
    append(response, "correlationId", context.correlation_id)
    return response


def _get_seat_map(operation: etree._Element, settings: Settings) -> etree._Element:
    context = request_context(operation)
    event_id = cast(str, child_text(operation, "eventId"))

    def run(session: Session) -> etree._Element:
        result = get_seat_map(session, context, event_id)
        response = _context_response("GetSeatMap", context)
        append(response, "eventId", result.event_id)
        append(response, "inventoryVersion", result.inventory_version)
        append(response, "generatedAt", iso_datetime(result.generated_at))
        seats_node = element("seats")
        for seat in result.seats:
            append_seat(seats_node, seat)
        response.append(seats_node)
        return response

    return _execute(settings, run, retries=0)


def _check_availability(
    operation: etree._Element, settings: Settings
) -> etree._Element:
    context = request_context(operation)
    event_id = cast(str, child_text(operation, "eventId"))
    requested = seat_ids(operation)

    def run(session: Session) -> etree._Element:
        result = check_availability(session, context, event_id, requested)
        response = _context_response("CheckAvailability", context)
        append(response, "eventId", result.event_id)
        append(response, "available", result.available)
        available_node = element("availableSeatIds")
        for seat_id in result.available_seat_ids:
            append(available_node, "seatId", seat_id)
        response.append(available_node)
        unavailable_node = element("unavailableSeatIds")
        for seat_id in result.unavailable_seat_ids:
            append(unavailable_node, "seatId", seat_id)
        response.append(unavailable_node)
        append(response, "checkedAt", iso_datetime(result.checked_at))
        return response

    return _execute(settings, run, retries=0)


def _reserve_seats(operation: etree._Element, settings: Settings) -> etree._Element:
    context = request_context(operation)
    booking_id = cast(str, child_text(operation, "bookingId"))
    event_id = cast(str, child_text(operation, "eventId"))
    requested = seat_ids(operation)
    hold_seconds = child_int(
        operation,
        "holdSeconds",
        required=False,
        default=settings.default_hold_seconds,
    )

    def run(session: Session) -> etree._Element:
        result = reserve_seats(
            session,
            settings,
            context,
            booking_id=booking_id,
            event_id=event_id,
            seat_ids=requested,
            hold_seconds=hold_seconds,
        )
        response = _context_response("ReserveSeats", context)
        append_reservation(response, result)
        return response

    return _execute(settings, run)


def _get_reservation(operation: etree._Element, settings: Settings) -> etree._Element:
    context = request_context(operation)
    reservation_id = cast(str, child_text(operation, "reservationId"))

    def run(session: Session) -> etree._Element:
        result = get_reservation_view(session, context, reservation_id)
        response = _context_response("GetReservation", context)
        append_reservation(response, result)
        return response

    return _execute(settings, run, retries=0)


def _extend_reservation(
    operation: etree._Element, settings: Settings
) -> etree._Element:
    context = request_context(operation)
    reservation_id = cast(str, child_text(operation, "reservationId"))
    expected_version = child_int(operation, "expectedVersion")
    extension_seconds = child_int(operation, "extensionSeconds")

    def run(session: Session) -> etree._Element:
        result = extend_reservation(
            session,
            settings,
            context,
            reservation_id=reservation_id,
            expected_version=expected_version,
            extension_seconds=extension_seconds,
        )
        response = _context_response("ExtendReservation", context)
        append_reservation(response, result)
        return response

    return _execute(settings, run)


def _confirm_seats(operation: etree._Element, settings: Settings) -> etree._Element:
    context = request_context(operation)
    reservation_id = cast(str, child_text(operation, "reservationId"))
    expected_version = child_int(operation, "expectedVersion")

    def run(session: Session) -> etree._Element:
        result = confirm_seats(
            session,
            settings,
            context,
            reservation_id=reservation_id,
            expected_version=expected_version,
        )
        response = _context_response("ConfirmSeats", context)
        append_reservation(response, result)
        return response

    return _execute(settings, run)


def _release_seats(operation: etree._Element, settings: Settings) -> etree._Element:
    context = request_context(operation)
    reservation_id = cast(str, child_text(operation, "reservationId"))
    reason_code = cast(
        str,
        child_text(
            operation,
            "reasonCode",
            required=False,
            default="CALLER_COMPENSATION",
        ),
    )

    def run(session: Session) -> etree._Element:
        result = release_seats(
            session,
            settings,
            context,
            reservation_id=reservation_id,
            reason_code=reason_code,
        )
        response = _context_response("ReleaseSeats", context)
        append_reservation(response, result)
        return response

    return _execute(settings, run)


def _expire_reservations(
    operation: etree._Element, settings: Settings
) -> etree._Element:
    context = request_context(operation)
    batch_size = child_int(
        operation,
        "batchSize",
        required=False,
        default=settings.expiry_batch_size,
    )

    def run(session: Session) -> etree._Element:
        result = expire_reservations(session, settings, context, batch_size=batch_size)
        response = _context_response("ExpireReservations", context)
        append(response, "expiredCount", result.expired_count)
        ids_node = element("reservationIds")
        for reservation_id in result.reservation_ids:
            append(ids_node, "reservationId", reservation_id)
        response.append(ids_node)
        return response

    return _execute(settings, run)
