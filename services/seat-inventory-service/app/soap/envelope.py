"""SOAP 1.1 response envelope builders."""

from __future__ import annotations

from collections.abc import Iterable

from lxml import etree

from app.domain.reservation import ReservationView
from app.domain.seat import SeatView
from app.soap.namespaces import NSMAP, SOAP_ENV, qname
from app.soap.types import iso_datetime


def element(name: str, text: str | int | bool | None = None) -> etree._Element:
    node = etree.Element(qname(name))
    if text is not None:
        if isinstance(text, bool):
            node.text = "true" if text else "false"
        else:
            node.text = str(text)
    return node


def append(parent: etree._Element, name: str, value: str | int | bool) -> None:
    parent.append(element(name, value))


def append_seat(parent: etree._Element, seat: SeatView) -> None:
    """Serialise one SeatMapSeat in canonical xs:sequence order.

    section, rowLabel and seatNumber are minOccurs="0", so they are written only when the
    domain actually carries them. status is required: it comes straight from the seat's own
    status enum and is never inferred from the current hold owner or defaulted.
    """
    node = element("seat")
    append(node, "seatId", seat.seat_id)
    for name, value in (
        ("section", seat.section),
        ("rowLabel", seat.row_label),
        ("seatNumber", seat.seat_number),
    ):
        if value:
            append(node, name, value)
    append(node, "ticketTypeCode", seat.ticket_type)
    append(node, "status", seat.status.value)
    parent.append(node)


def seat_map_response(
    event_id: str, seats: Iterable[SeatView]
) -> etree._Element:
    """Build a complete GetSeatMapResponse.

    Kept next to append_seat and free of any session so the canonical-XSD conformance of a
    seat map can be tested directly from domain values.
    """
    response = element("GetSeatMapResponse")
    append(response, "eventId", event_id)
    seats_node = element("seats")
    for seat in seats:
        append_seat(seats_node, seat)
    response.append(seats_node)
    return response


def append_reservation(parent: etree._Element, value: ReservationView) -> None:
    append(parent, "reservationId", value.reservation_id)
    append(parent, "bookingId", value.booking_id)
    append(parent, "eventId", value.event_id)
    append(parent, "status", value.status.value)
    append(parent, "expiresAt", iso_datetime(value.expires_at))
    append(parent, "resourceVersion", value.resource_version)


def soap_envelope(content: etree._Element) -> bytes:
    envelope = etree.Element(f"{{{SOAP_ENV}}}Envelope", nsmap=NSMAP)
    body = etree.SubElement(envelope, f"{{{SOAP_ENV}}}Body")
    body.append(content)
    return etree.tostring(
        envelope,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=False,
    )
