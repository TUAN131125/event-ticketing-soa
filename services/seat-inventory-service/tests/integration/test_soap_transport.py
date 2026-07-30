from __future__ import annotations

from pathlib import Path

import pytest
from conftest import create_inventory
from fastapi.testclient import TestClient
from lxml import etree

from app.config import Settings
from app.main import create_app
from app.security.xml_hardening import SOAP_ENV_NS, get_schema

ROOT = Path(__file__).resolve().parents[2]
HEADERS = {
    "X-Service-Token": "test-service-token",
    "Content-Type": "text/xml; charset=utf-8",
}


def request(name: str) -> bytes:
    return (ROOT / "contracts" / "examples" / f"{name}-request.xml").read_bytes()


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
            headers={**HEADERS, "SOAPAction": "GetSeatMap"},
        )
        assert map_response.status_code == 200
        get_schema().assertValid(body_operation(map_response.content))

        reserve_payload = request("reserve-seats").replace(
            b"<seat:holdSeconds>600</seat:holdSeconds>",
            b"<seat:holdSeconds>10</seat:holdSeconds>",
        )
        reserve_payload = reserve_payload.replace(b"A-01", b"A-001").replace(
            b"A-02", b"A-002"
        )
        reserve_response = client.post(
            "/soap",
            content=reserve_payload,
            headers={**HEADERS, "SOAPAction": "ReserveSeats"},
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
        b"<seat:holdSeconds>600</seat:holdSeconds>",
        b"<seat:holdSeconds>10</seat:holdSeconds>",
    )
    original = original.replace(b"A-01", b"A-001").replace(b"A-02", b"A-002")
    conflict = (
        original.replace(b"COR-RESERVE-1", b"COR-RESERVE-2")
        .replace(b"IDEM-RESERVE-1", b"IDEM-RESERVE-2")
        .replace(b"BKG-DEMO-1", b"BKG-DEMO-2")
    )
    with TestClient(app) as client:
        first = client.post("/soap", content=original, headers=HEADERS)
        assert first.status_code == 200, first.text
        response = client.post("/soap", content=conflict, headers=HEADERS)
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
def test_admin_configure_inventory_contract(
    clean_database: None, test_settings: Settings
) -> None:
    app = create_app(test_settings)
    payload = {
        "eventId": "EVT-ADMIN",
        "inventoryVersion": 1,
        "seats": [
            {
                "seatId": "A-01",
                "section": "A",
                "rowLabel": "A",
                "seatNumber": "01",
                "ticketType": "STANDARD",
                "status": "AVAILABLE",
            }
        ],
    }
    with TestClient(app) as client:
        unauthorized = client.post("/admin/inventory", json=payload)
        response = client.post(
            "/admin/inventory",
            json=payload,
            headers={
                "X-Service-Token": "test-service-token",
                "X-Correlation-ID": "COR-ADMIN-1",
                "X-Actor-ID": "ADMIN-1",
            },
        )
    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert response.json() == {
        "eventId": "EVT-ADMIN",
        "inventoryVersion": 1,
        "seatCount": 1,
        "correlationId": "COR-ADMIN-1",
    }
