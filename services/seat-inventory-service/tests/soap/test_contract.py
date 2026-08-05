from __future__ import annotations

from pathlib import Path

from lxml import etree
from zeep import Client

from app.security.xml_hardening import get_schema, parse_soap

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CONTRACTS = REPOSITORY_ROOT / "contracts"
EXPECTED_OPERATIONS = {
    "GetSeatMap",
    "CheckAvailability",
    "ReserveSeats",
    "GetReservation",
    "ExtendReservation",
    "ConfirmSeats",
    "ReleaseSeats",
    "ExpireReservations",
}


def test_xsd_compiles_offline() -> None:
    assert isinstance(get_schema(), etree.XMLSchema)


def test_wsdl_exposes_exactly_eight_operations() -> None:
    client = Client(str(CONTRACTS / "seat-inventory.wsdl"))
    service = next(iter(client.wsdl.services.values()))
    port = next(iter(service.ports.values()))
    assert set(port.binding._operations) == EXPECTED_OPERATIONS


def test_every_example_request_validates_against_contract() -> None:
    example_dir = CONTRACTS / "examples" / "soap"
    examples = sorted(
        path for path in example_dir.glob("*.xml") if path.name != "soap-fault.xml"
    )
    assert len(examples) == 8
    names = {
        etree.QName(parse_soap(path.read_bytes(), 262_144))
        .localname.removesuffix("Request")
        for path in examples
    }
    assert names == EXPECTED_OPERATIONS
