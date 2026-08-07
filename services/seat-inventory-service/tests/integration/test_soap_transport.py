from __future__ import annotations

from pathlib import Path

import pytest
from conftest import create_inventory, service_authorization
from fastapi.testclient import TestClient
from lxml import etree

from app.config import Settings
from app.main import create_app
from app.security.xml_hardening import SOAP_ENV_NS, get_schema

ROOT = Path(__file__).resolve().parents[4]


def headers(**extra: str) -> dict[str, str]:
    return {
        "Authorization": service_authorization(),
        "Content-Type": "text/xml; charset=utf-8",
        **extra,
    }


def request(name: str) -> bytes:
    return (
        (ROOT / "contracts" / "examples" / "soap" / f"{name}.xml")
        .read_bytes()
        .replace(b"EV-001", b"EVT-DEMO")
    )


def body_operation(payload: bytes) -> etree._Element:
    root = etree.fromstring(payload)
    body = root.find(f"{{{SOAP_ENV_NS}}}Body")
    assert body is not None and len(body) == 1
    return body[0]


@pytest.mark.integration
def test_valid_query_and_command_responses_match_xsd(
    clean_database: None, test_settings: Settings
) -> None:
    create_inventory(test_settings, event_id="EVT-DEMO", seat_count=3)
    app = create_app(test_settings)
    with TestClient(app) as client:
        map_response = client.post(
            "/soap",
            content=request("get-seat-map"),
            headers=headers(SOAPAction="GetSeatMap"),
        )
        assert map_response.status_code == 200
        get_schema().assertValid(body_operation(map_response.content))

        reserve_payload = request("reserve-seats").replace(
            b"<seat:ttlSeconds>600</seat:ttlSeconds>",
            b"<seat:ttlSeconds>10</seat:ttlSeconds>",
        )
        reserve_payload = reserve_payload.replace(b"A12", b"A-001")
        reserve_response = client.post(
            "/soap",
            content=reserve_payload,
            headers=headers(SOAPAction="ReserveSeats"),
        )
        assert reserve_response.status_code == 200, reserve_response.text
        get_schema().assertValid(body_operation(reserve_response.content))


@pytest.mark.integration
def test_soap_fault_is_stable_and_does_not_leak_storage_details(
    clean_database: None, test_settings: Settings
) -> None:
    create_inventory(test_settings, event_id="EVT-DEMO", seat_count=3)
    app = create_app(test_settings)
    original = request("reserve-seats").replace(
        b"<seat:ttlSeconds>600</seat:ttlSeconds>",
        b"<seat:ttlSeconds>10</seat:ttlSeconds>",
    )
    original = original.replace(b"A12", b"A-001")
    conflict = (
        original.replace(b"corr-1234567890abcdef", b"corr-2234567890abcdef")
        .replace(b"seat-BKG-001", b"seat-BKG-002")
        .replace(b"BKG-001", b"BKG-002")
    )
    with TestClient(app) as client:
        first = client.post("/soap", content=original, headers=headers())
        assert first.status_code == 200, first.text
        response = client.post("/soap", content=conflict, headers=headers())
    assert response.status_code == 500
    assert "SEAT_UNAVAILABLE" in response.text
    lowered = response.text.lower()
    assert "traceback" not in lowered
    assert "postgres" not in lowered
    assert "localhost" not in lowered
    fault_detail = body_operation(response.content).find("detail")
    assert fault_detail is not None


@pytest.mark.integration
def test_soap_requires_service_authentication(
    clean_database: None, test_settings: Settings
) -> None:
    app = create_app(test_settings)
    with TestClient(app) as client:
        response = client.post("/soap", content=request("get-seat-map"))
    assert response.status_code == 500
    assert "AUTHENTICATION_FAILED" in response.text
    assert "retryable>false" in response.text


@pytest.mark.integration
def test_seat_map_over_the_booking_selection_limit_validates_end_to_end(
    clean_database: None, test_settings: Settings
) -> None:
    """A real event has far more than the ten seats one booking may select.

    The previous canonical schema reused SeatRefList (maxOccurs=10) for the whole map, so
    any realistic inventory failed validation at the ESB.
    """
    seat_count = 40
    create_inventory(test_settings, event_id="EVT-DEMO", seat_count=seat_count)
    app = create_app(test_settings)
    with TestClient(app) as client:
        response = client.post(
            "/soap",
            content=request("get-seat-map"),
            headers=headers(SOAPAction="GetSeatMap"),
        )

    assert response.status_code == 200, response.text
    operation = body_operation(response.content)
    get_schema().assertValid(operation)

    seat_ns = "urn:event-ticketing:seat:v1"
    seats = operation.findall(f"{{{seat_ns}}}seats/{{{seat_ns}}}seat")
    assert len(seats) == seat_count
    statuses = {seat.findtext(f"{{{seat_ns}}}status") for seat in seats}
    assert statuses == {"AVAILABLE"}
    first = seats[0]
    assert [etree.QName(child).localname for child in first] == [
        "seatId",
        "section",
        "rowLabel",
        "seatNumber",
        "ticketTypeCode",
        "status",
    ]


@pytest.mark.integration
def test_seat_map_reports_a_held_seat_as_held_not_available(
    clean_database: None, test_settings: Settings
) -> None:
    from conftest import context
    from app.application.reserve_seats import reserve_seats
    from app.infrastructure.database.session import session_scope

    create_inventory(test_settings, event_id="EVT-DEMO", seat_count=3)
    with session_scope(test_settings) as session:
        reserve_seats(
            session,
            test_settings,
            context("map-hold", idempotency_key="map-hold"),
            booking_id="BKG-MAP",
            event_id="EVT-DEMO",
            seat_ids=("A-001",),
            hold_seconds=10,
        )

    app = create_app(test_settings)
    with TestClient(app) as client:
        response = client.post(
            "/soap",
            content=request("get-seat-map"),
            headers=headers(SOAPAction="GetSeatMap"),
        )

    assert response.status_code == 200, response.text
    operation = body_operation(response.content)
    get_schema().assertValid(operation)
    seat_ns = "urn:event-ticketing:seat:v1"
    by_id = {
        seat.findtext(f"{{{seat_ns}}}seatId"): seat.findtext(f"{{{seat_ns}}}status")
        for seat in operation.findall(f"{{{seat_ns}}}seats/{{{seat_ns}}}seat")
    }
    assert by_id["A-001"] == "HELD"
    assert by_id["A-002"] == "AVAILABLE"
