"""GetSeatMap must serialise every field the canonical XSD requires.

These run the real production serializer against hand-built domain values, so they need no
database, and they validate the result with the same canonical schema the ESB uses.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from app.domain.seat import SeatStatus, SeatView
from app.soap.envelope import seat_map_response
from app.soap.namespaces import TNS as SEAT_NS

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CANONICAL_XSD = REPOSITORY_ROOT / "contracts" / "seat-inventory.xsd"


@pytest.fixture(scope="module")
def canonical_schema() -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(CANONICAL_XSD)))


def seat(
    seat_id: str,
    status: SeatStatus,
    *,
    section: str = "A",
    row_label: str = "1",
    seat_number: str = "01",
    ticket_type: str = "STD",
) -> SeatView:
    return SeatView(
        event_id="EV001",
        seat_id=seat_id,
        section=section,
        row_label=row_label,
        seat_number=seat_number,
        ticket_type=ticket_type,
        status=status,
        resource_version=1,
    )


def seat_nodes(response: etree._Element) -> list[etree._Element]:
    return response.findall(f"{{{SEAT_NS}}}seats/{{{SEAT_NS}}}seat")


def child_text(node: etree._Element, name: str) -> str | None:
    found = node.find(f"{{{SEAT_NS}}}{name}")
    return None if found is None else found.text


def test_available_seat_serialises_status_and_validates(canonical_schema) -> None:
    response = seat_map_response("EV001", [seat("A-1-01", SeatStatus.AVAILABLE)])

    canonical_schema.assertValid(response)
    (node,) = seat_nodes(response)
    assert child_text(node, "status") == "AVAILABLE"


@pytest.mark.parametrize(
    "status", [SeatStatus.HELD, SeatStatus.SOLD, SeatStatus.BLOCKED]
)
def test_non_available_statuses_are_preserved(canonical_schema, status) -> None:
    """A held or sold seat must not be reported as available to the browser."""
    response = seat_map_response("EV001", [seat("A-1-02", status)])

    canonical_schema.assertValid(response)
    (node,) = seat_nodes(response)
    assert child_text(node, "status") == status.value


def test_every_canonical_status_round_trips(canonical_schema) -> None:
    seats = [
        seat(f"A-1-{index:02d}", status)
        for index, status in enumerate(SeatStatus, start=1)
    ]
    response = seat_map_response("EV001", seats)

    canonical_schema.assertValid(response)
    assert [child_text(node, "status") for node in seat_nodes(response)] == [
        status.value for status in SeatStatus
    ]


def test_descriptive_fields_are_serialised_in_schema_sequence_order(
    canonical_schema,
) -> None:
    response = seat_map_response(
        "EV001",
        [
            seat(
                "A-1-03",
                SeatStatus.AVAILABLE,
                section="Balcony",
                row_label="B",
                seat_number="12",
                ticket_type="VIP",
            )
        ],
    )

    canonical_schema.assertValid(response)
    (node,) = seat_nodes(response)
    assert [etree.QName(child).localname for child in node] == [
        "seatId",
        "section",
        "rowLabel",
        "seatNumber",
        "ticketTypeCode",
        "status",
    ]
    assert child_text(node, "section") == "Balcony"
    assert child_text(node, "rowLabel") == "B"
    assert child_text(node, "seatNumber") == "12"
    assert child_text(node, "ticketTypeCode") == "VIP"


def test_absent_optional_fields_still_validate(canonical_schema) -> None:
    """section, rowLabel and seatNumber are minOccurs=0 and may legitimately be blank."""
    response = seat_map_response(
        "EV001",
        [seat("A-1-04", SeatStatus.AVAILABLE, section="", row_label="", seat_number="")],
    )

    canonical_schema.assertValid(response)
    (node,) = seat_nodes(response)
    assert [etree.QName(child).localname for child in node] == [
        "seatId",
        "ticketTypeCode",
        "status",
    ]


def test_seat_map_larger_than_ten_seats_validates(canonical_schema) -> None:
    """The old SeatRefList capped the whole map at 10; a real event is much larger."""
    seats = [seat(f"A-1-{index:03d}", SeatStatus.AVAILABLE) for index in range(250)]
    response = seat_map_response("EV001", seats)

    canonical_schema.assertValid(response)
    assert len(seat_nodes(response)) == 250


def test_empty_seat_map_validates(canonical_schema) -> None:
    canonical_schema.assertValid(seat_map_response("EV001", []))
