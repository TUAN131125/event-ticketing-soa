"""contracts/seat-inventory.xsd is the single Seat Inventory schema.

These guard the properties the Seat/ESB split depends on: one file, one namespace, nine
operations, and a seat map that is not capped at a single booking's ten seats.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from lxml import etree

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CONTRACTS = REPOSITORY_ROOT / "contracts"
CANONICAL_XSD = CONTRACTS / "seat-inventory.xsd"
CANONICAL_WSDL = CONTRACTS / "seat-inventory.wsdl"
SEAT_NAMESPACE = "urn:event-ticketing:seat:v1"
XSD_NS = {"xs": "http://www.w3.org/2001/XMLSchema"}
WSDL_NS = {
    "wsdl": "http://schemas.xmlsoap.org/wsdl/",
    "xsd": "http://www.w3.org/2001/XMLSchema",
}
EXPECTED_OPERATIONS = {
    "GetSeatMap",
    "CheckAvailability",
    "ReserveSeats",
    "GetReservation",
    "ExtendReservation",
    "ConfirmSeats",
    "ReleaseSeats",
    "ExpireReservations",
    "ConfigureInventory",
}


@pytest.fixture(scope="module")
def xsd_tree() -> etree._ElementTree:
    return etree.parse(str(CANONICAL_XSD))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_canonical_xsd_compiles_and_keeps_its_namespace(xsd_tree) -> None:
    etree.XMLSchema(xsd_tree)
    assert xsd_tree.getroot().get("targetNamespace") == SEAT_NAMESPACE


def test_canonical_wsdl_imports_the_canonical_xsd_and_publishes_every_operation() -> None:
    tree = etree.parse(str(CANONICAL_WSDL))
    assert any(
        item.get("schemaLocation") == "seat-inventory.xsd"
        for item in tree.xpath("//xsd:import", namespaces=WSDL_NS)
    )
    assert tree.getroot().get("targetNamespace") == SEAT_NAMESPACE
    operations = {
        item.get("name")
        for item in tree.xpath("//wsdl:portType/wsdl:operation", namespaces=WSDL_NS)
    }
    assert operations == EXPECTED_OPERATIONS
    bound = {
        item.get("name")
        for item in tree.xpath("//wsdl:binding/wsdl:operation", namespaces=WSDL_NS)
    }
    assert bound == EXPECTED_OPERATIONS


def test_booking_selection_stays_capped_at_ten_seats(xsd_tree) -> None:
    (selection,) = xsd_tree.xpath(
        '//xs:complexType[@name="SeatSelectionList"]//xs:element[@name="seat"]',
        namespaces=XSD_NS,
    )
    assert selection.get("maxOccurs") == "10"
    assert selection.get("type") == "tns:SeatRef"
    for element_name in ("CheckAvailabilityRequest", "ReserveSeatsRequest"):
        (seat_ids,) = xsd_tree.xpath(
            f'//xs:element[@name="{element_name}"]//xs:element[@name="seatIds"]',
            namespaces=XSD_NS,
        )
        assert seat_ids.get("type") == "tns:SeatSelectionList"


def test_seat_map_is_a_separate_unbounded_by_ten_list(xsd_tree) -> None:
    (seat_map,) = xsd_tree.xpath(
        '//xs:complexType[@name="SeatMapList"]//xs:element[@name="seat"]',
        namespaces=XSD_NS,
    )
    assert seat_map.get("type") == "tns:SeatMapSeat"
    assert int(seat_map.get("maxOccurs")) > 10
    assert seat_map.get("maxOccurs") == "20000"
    (response_seats,) = xsd_tree.xpath(
        '//xs:element[@name="GetSeatMapResponse"]//xs:element[@name="seats"]',
        namespaces=XSD_NS,
    )
    assert response_seats.get("type") == "tns:SeatMapList"


def test_seat_map_seat_requires_status_and_keeps_descriptive_fields(xsd_tree) -> None:
    children = xsd_tree.xpath(
        '//xs:complexType[@name="SeatMapSeat"]/xs:sequence/xs:element',
        namespaces=XSD_NS,
    )
    assert [child.get("name") for child in children] == [
        "seatId",
        "section",
        "rowLabel",
        "seatNumber",
        "ticketTypeCode",
        "status",
    ]
    optional = {
        child.get("name") for child in children if child.get("minOccurs") == "0"
    }
    assert optional == {"section", "rowLabel", "seatNumber"}
    (status,) = [child for child in children if child.get("name") == "status"]
    assert status.get("type") == "tns:SeatStatus"
    assert status.get("minOccurs") is None  # required


def test_configure_inventory_is_still_part_of_the_contract(xsd_tree) -> None:
    names = {
        item.get("name")
        for item in xsd_tree.xpath("/xs:schema/xs:element", namespaces=XSD_NS)
    }
    assert {"ConfigureInventoryRequest", "ConfigureInventoryResponse"} <= names


def test_no_second_seat_schema_is_tracked_anywhere_in_the_repository() -> None:
    """A second copy is how Seat and the ESB drifted apart in the first place.

    dist/ is a generated build artifact and is allowed to hold a copy, but it must be a
    byte-identical copy of the canonical file.
    """
    for canonical in (CANONICAL_XSD, CANONICAL_WSDL):
        copies = [
            path
            for path in REPOSITORY_ROOT.rglob(canonical.name)
            if "node_modules" not in path.parts
        ]
        unexpected = [
            path
            for path in copies
            if path != canonical and path.parts[-3:-1] != ("dist", "contracts")
        ]
        assert not unexpected, [str(path) for path in unexpected]

        canonical_digest = sha256(canonical)
        for path in copies:
            assert sha256(path) == canonical_digest, str(path)


def test_service_images_copy_the_canonical_schema_not_a_stale_artifact() -> None:
    seat_dockerfile = (
        REPOSITORY_ROOT / "services/seat-inventory-service/Dockerfile"
    ).read_text(encoding="utf-8")
    esb_dockerfile = (
        REPOSITORY_ROOT / "gateway/booking-orchestrator/Dockerfile"
    ).read_text(encoding="utf-8")

    assert "contracts/seat-inventory.xsd ./contracts/seat-inventory.xsd" in seat_dockerfile
    assert "contracts/seat-inventory.wsdl ./contracts/seat-inventory.wsdl" in seat_dockerfile
    assert "contracts/seat-inventory.xsd ./contracts/seat-inventory.xsd" in esb_dockerfile
    for dockerfile in (seat_dockerfile, esb_dockerfile):
        assert "dist/contracts/seat-inventory" not in dockerfile
