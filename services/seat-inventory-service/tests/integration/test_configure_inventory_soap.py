"""ConfigureInventory provisioning through the canonical SOAP boundary."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import context, service_authorization
from fastapi.testclient import TestClient
from lxml import etree

from app.application.configure_inventory import SeatDefinition, configure_inventory
from app.application.reserve_seats import reserve_seats
from app.config import Settings
from app.domain.exceptions import IdempotencyConflict, InventoryConflict
from app.infrastructure.database.session import session_scope
from app.main import create_app
from app.security.xml_hardening import SOAP_ENV_NS, get_schema

ROOT = Path(__file__).resolve().parents[4]
EXAMPLE = ROOT / "contracts" / "examples" / "soap" / "configure-inventory.xml"
GET_SEAT_MAP_REQUEST = b"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:seat="urn:event-ticketing:seat:v1">
  <soapenv:Body>
    <seat:GetSeatMapRequest>
      <seat:context>
        <seat:correlationId>corr-1234567890abcdef</seat:correlationId>
        <seat:callerService>pytest</seat:callerService>
        <seat:schemaVersion>1</seat:schemaVersion>
      </seat:context>
      <seat:eventId>EV001</seat:eventId>
    </seat:GetSeatMapRequest>
  </soapenv:Body>
</soapenv:Envelope>
"""


def headers(**extra: str) -> dict[str, str]:
    return {
        "Authorization": service_authorization(),
        "Content-Type": "text/xml; charset=utf-8",
        **extra,
    }


def body_operation(payload: bytes) -> etree._Element:
    root = etree.fromstring(payload)
    body = root.find(f"{{{SOAP_ENV_NS}}}Body")
    assert body is not None and len(body) == 1
    return body[0]


def field(node: etree._Element, name: str) -> str:
    child = node.find(f"{{urn:event-ticketing:seat:v1}}{name}")
    assert child is not None and child.text is not None
    return child.text


def seats(count: int, *, ticket_type: str = "VIP") -> tuple[SeatDefinition, ...]:
    return tuple(
        SeatDefinition(
            seat_id=f"S-{index:03d}",
            section="A",
            row_label="1",
            seat_number=f"{index:03d}",
            ticket_type=ticket_type,
        )
        for index in range(1, count + 1)
    )


@pytest.mark.integration
def test_soap_provisioning_creates_seats_and_replays_identical_requests(
    clean_database: None, test_settings: Settings
) -> None:
    payload = EXAMPLE.read_bytes()
    app = create_app(test_settings)
    with TestClient(app) as client:
        first = client.post(
            "/soap", content=payload, headers=headers(SOAPAction="ConfigureInventory")
        )
        assert first.status_code == 200, first.text
        created = body_operation(first.content)
        get_schema().assertValid(created)
        assert field(created, "eventId") == "EV001"
        assert field(created, "inventoryVersion") == "1"
        assert field(created, "configuredSeatCount") == "2"
        assert field(created, "status") == "CONFIGURED"

        # A byte-identical retry must not create a second inventory version.
        replay = client.post(
            "/soap", content=payload, headers=headers(SOAPAction="ConfigureInventory")
        )
        assert replay.status_code == 200, replay.text
        replayed = body_operation(replay.content)
        get_schema().assertValid(replayed)
        assert field(replayed, "status") == "REPLAYED"
        assert field(replayed, "configuredSeatCount") == "2"

        # The provisioned seats are visible through the canonical read operation.
        seat_map = client.post(
            "/soap",
            content=GET_SEAT_MAP_REQUEST,
            headers=headers(SOAPAction="GetSeatMap"),
        )
        assert seat_map.status_code == 200, seat_map.text
        assert b"A12" in seat_map.content and b"A13" in seat_map.content


@pytest.mark.integration
def test_same_idempotency_key_with_different_payload_faults(
    clean_database: None, test_settings: Settings
) -> None:
    payload = EXAMPLE.read_bytes()
    app = create_app(test_settings)
    with TestClient(app) as client:
        assert (
            client.post(
                "/soap",
                content=payload,
                headers=headers(SOAPAction="ConfigureInventory"),
            ).status_code
            == 200
        )
        # Schema-valid, but a different seat layout under the same idempotency key.
        divergent = payload.replace(
            b"<seat:ticketTypeCode>VIP</seat:ticketTypeCode>",
            b"<seat:ticketTypeCode>STANDARD</seat:ticketTypeCode>",
        )
        assert divergent != payload
        response = client.post(
            "/soap", content=divergent, headers=headers(SOAPAction="ConfigureInventory")
        )
    assert response.status_code == 500
    assert "IDEMPOTENCY_KEY_REUSED" in response.text
    assert "corr-1234567890abcdef" in response.text
    assert "retryable>false" in response.text


@pytest.mark.integration
def test_repeated_provisioning_requires_a_newer_inventory_version(
    clean_database: None, test_settings: Settings
) -> None:
    with session_scope(test_settings) as session:
        configure_inventory(
            session,
            test_settings,
            context("CFG-1", idempotency_key="cfg-ev-900-v1"),
            event_id="EV-900",
            inventory_version=1,
            seats=seats(2),
        )
    with session_scope(test_settings) as session:
        with pytest.raises(InventoryConflict):
            configure_inventory(
                session,
                test_settings,
                context("CFG-2", idempotency_key="cfg-ev-900-stale"),
                event_id="EV-900",
                inventory_version=1,
                seats=seats(3),
            )
    with session_scope(test_settings) as session:
        result = configure_inventory(
            session,
            test_settings,
            context("CFG-3", idempotency_key="cfg-ev-900-v2"),
            event_id="EV-900",
            inventory_version=2,
            seats=seats(3),
        )
    assert result.inventory_version == 2
    assert result.seat_count == 3
    assert result.replayed is False


@pytest.mark.integration
def test_provisioning_never_removes_or_mutates_held_seats(
    clean_database: None, test_settings: Settings
) -> None:
    with session_scope(test_settings) as session:
        configure_inventory(
            session,
            test_settings,
            context("CFG-HELD", idempotency_key="cfg-ev-901-v1"),
            event_id="EV-901",
            inventory_version=1,
            seats=seats(2),
        )
    with session_scope(test_settings) as session:
        reserve_seats(
            session,
            test_settings,
            context("RES-HELD", idempotency_key="res-ev-901-001"),
            booking_id="BKG-901",
            event_id="EV-901",
            seat_ids=("S-001",),
            hold_seconds=10,
        )

    # Dropping the held seat from the layout must fail closed.
    with session_scope(test_settings) as session:
        with pytest.raises(InventoryConflict):
            configure_inventory(
                session,
                test_settings,
                context("CFG-DROP", idempotency_key="cfg-ev-901-v2-drop"),
                event_id="EV-901",
                inventory_version=2,
                seats=(seats(2)[1],),
            )

    # Silently re-typing the held seat must fail closed as well.
    with session_scope(test_settings) as session:
        with pytest.raises(InventoryConflict):
            configure_inventory(
                session,
                test_settings,
                context("CFG-RETYPE", idempotency_key="cfg-ev-901-v2-retype"),
                event_id="EV-901",
                inventory_version=2,
                seats=seats(2, ticket_type="STANDARD"),
            )


@pytest.mark.integration
def test_provisioning_rejects_duplicate_seats_and_missing_idempotency_key(
    clean_database: None, test_settings: Settings
) -> None:
    duplicate = seats(1) + seats(1)
    with session_scope(test_settings) as session:
        with pytest.raises(Exception) as duplicate_error:
            configure_inventory(
                session,
                test_settings,
                context("CFG-DUP", idempotency_key="cfg-ev-902-dup"),
                event_id="EV-902",
                inventory_version=1,
                seats=duplicate,
            )
    assert "Duplicate seatId" in str(duplicate_error.value)

    with session_scope(test_settings) as session:
        with pytest.raises(Exception) as missing_key:
            configure_inventory(
                session,
                test_settings,
                context("CFG-NOKEY"),
                event_id="EV-903",
                inventory_version=1,
                seats=seats(1),
            )
    assert "idempotencyKey" in str(missing_key.value)


@pytest.mark.integration
def test_idempotency_conflict_is_raised_for_a_reused_key(
    clean_database: None, test_settings: Settings
) -> None:
    with session_scope(test_settings) as session:
        configure_inventory(
            session,
            test_settings,
            context("CFG-K1", idempotency_key="cfg-ev-904-shared"),
            event_id="EV-904",
            inventory_version=1,
            seats=seats(2),
        )
    with session_scope(test_settings) as session:
        with pytest.raises(IdempotencyConflict):
            configure_inventory(
                session,
                test_settings,
                context("CFG-K2", idempotency_key="cfg-ev-904-shared"),
                event_id="EV-904",
                inventory_version=2,
                seats=seats(3),
            )
