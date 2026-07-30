"""SOAP 1.1 response envelope builders."""

from __future__ import annotations

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
    node = element("seat")
    append(node, "seatId", seat.seat_id)
    append(node, "section", seat.section)
    append(node, "rowLabel", seat.row_label)
    append(node, "seatNumber", seat.seat_number)
    append(node, "ticketType", seat.ticket_type)
    append(node, "status", seat.status.value)
    append(node, "resourceVersion", seat.resource_version)
    parent.append(node)


def append_reservation(parent: etree._Element, value: ReservationView) -> None:
    node = element("reservation")
    append(node, "reservationId", value.reservation_id)
    append(node, "bookingId", value.booking_id)
    append(node, "eventId", value.event_id)
    seat_ids = element("seatIds")
    for seat_id in value.seat_ids:
        append(seat_ids, "seatId", seat_id)
    node.append(seat_ids)
    append(node, "status", value.status.value)
    append(node, "expiresAt", iso_datetime(value.expires_at))
    append(node, "extendCount", value.extend_count)
    append(node, "resourceVersion", value.resource_version)
    append(node, "createdAt", iso_datetime(value.created_at))
    append(node, "updatedAt", iso_datetime(value.updated_at))
    parent.append(node)


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
