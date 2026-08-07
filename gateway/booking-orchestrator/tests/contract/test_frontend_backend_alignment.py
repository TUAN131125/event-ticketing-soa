from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml
from jsonschema import validate

from app.api.schemas import CheckInRequest
from app.application.projections import event_request_to_provider
from app.application.queries import QueryService
from app.domain.models import Principal, RequestContext
from app.main import create_app

ROOT = Path(__file__).resolve().parents[4]


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def canonical() -> dict:
    return load_yaml(ROOT / "contracts" / "esb-public-api.yaml")


def provider(name: str) -> dict:
    return load_yaml(ROOT / "contracts" / name)


def schema(document: dict, name: str) -> dict:
    return {
        "$ref": f"#/components/schemas/{name}",
        "components": document["components"],
    }


def assert_schema(document: dict, name: str, value: object) -> None:
    validate(value, schema(document, name))


def request_schema_for(document: dict, path: str, method: str) -> dict:
    body = document["paths"][path][method]["requestBody"]["content"]["application/json"]["schema"]
    if "$ref" in body:
        return document["components"]["schemas"][body["$ref"].split("/")[-1]]
    for candidate in body.get("anyOf", []):
        if isinstance(candidate, dict) and "$ref" in candidate:
            return document["components"]["schemas"][candidate["$ref"].split("/")[-1]]
    return body


def response_ref(document: dict, path: str, method: str, status: str) -> str:
    value = document["paths"][path][method]["responses"][status]["content"]["application/json"]["schema"]
    return value.get("$ref", "").split("/")[-1]


def test_frontend_routes_use_the_projection_schemas_expected_by_the_apps():
    document = canonical()
    expected = {
        ("/api/events/{eventId}/seat-map", "get", "200"): "SeatMapProjection",
        ("/api/bookings", "get", "200"): "BookingListProjection",
        ("/api/bookings/{bookingId}", "get", "200"): "BookingResult",
        ("/api/bookings/{bookingId}/cancel", "post", "200"): "BookingResult",
        ("/api/tickets", "get", "200"): "TicketListProjection",
        ("/api/tickets/{ticketId}", "get", "200"): "TicketProjection",
        ("/api/admin/events", "post", "201"): "PublicEvent",
        ("/api/admin/events/{eventId}", "put", "200"): "PublicEvent",
        ("/api/check-in/validate", "post", "200"): "TicketValidationResult",
        ("/api/check-in/tickets/{ticketId}", "post", "200"): "CheckInResult",
    }
    for (path, method, status), expected_schema in expected.items():
        assert response_ref(document, path, method, status) == expected_schema


def test_new_public_requests_match_runtime_validation_and_do_not_expose_provider_fields():
    document = canonical()
    runtime = create_app().state.generated_openapi()

    pairs = [
        ("/api/admin/events", "post"),
        ("/api/bookings/{bookingId}/cancel", "post"),
        ("/api/check-in/validate", "post"),
        ("/api/check-in/tickets/{ticketId}", "post"),
    ]
    for path, method in pairs:
        public = request_schema_for(document, path, method)
        live = request_schema_for(runtime, path, method)
        assert set(public.get("properties", {})) == set(live.get("properties", {}))
        assert set(public.get("required", [])) == set(live.get("required", []))

    event_request = request_schema_for(document, "/api/admin/events", "post")
    assert "description" not in event_request["properties"]
    assert "imageUrl" not in event_request["properties"]
    ticket_type = document["components"]["schemas"]["AdminTicketTypeInput"]
    assert set(ticket_type["properties"]) == {"ticketTypeId", "name", "price"}
    check_in = request_schema_for(document, "/api/check-in/tickets/{ticketId}", "post")
    assert set(check_in["properties"]) == {"qrToken"}


def test_projection_fields_are_backed_by_provider_contracts():
    document = canonical()
    event = provider("event-service.yaml")["components"]["schemas"]["Event"]
    booking = provider("booking-service.yaml")["components"]["schemas"]["BookingResponse"]
    ticket = provider("ticket-service.yaml")["components"]["schemas"]["Ticket"]

    event_fields = set(event["properties"])
    assert {"eventId", "name", "venue", "startsAt", "saleStartsAt", "saleEndsAt", "status", "ticketTypes", "resourceVersion"} <= event_fields
    booking_fields = set(booking["properties"])
    assert {"bookingId", "customerId", "eventId", "items", "seats", "total", "currency", "status", "ticketIds", "resourceVersion"} <= booking_fields
    ticket_fields = set(ticket["properties"])
    assert {"ticketId", "bookingId", "eventId", "customerId", "seatId", "status", "qrToken", "resourceVersion"} <= ticket_fields

    public_ticket = document["components"]["schemas"]["TicketProjection"]
    assert "issuedAt" not in public_ticket["properties"]
    assert "checkedInAt" not in public_ticket["properties"]
    assert "qrImageDataUrl" not in public_ticket["properties"]


def test_admin_event_transform_is_valid_for_event_service_contract():
    public = {
        "name": "Summer Show",
        "venue": "Hall A",
        "startsAt": "2027-06-01T12:00:00Z",
        "saleStartsAt": "2027-05-01T00:00:00Z",
        "saleEndsAt": "2027-06-01T11:00:00Z",
        "ticketTypes": [
            {
                "ticketTypeId": "VIP",
                "name": "VIP",
                "price": {"amountMinor": 500000, "currency": "VND"},
            }
        ],
    }
    transformed = event_request_to_provider(public)
    event_document = provider("event-service.yaml")
    assert_schema(event_document, "EventCreate", transformed)
    assert transformed["ticketTypes"][0]["code"] == "VIP"
    assert "ticketTypeId" not in transformed["ticketTypes"][0]


class _Event:
    def __init__(self) -> None:
        self.value = {
            "eventId": "event-1",
            "name": "Summer Show",
            "venue": "Hall A",
            "startsAt": "2027-06-01T12:00:00Z",
            "saleStartsAt": "2027-05-01T00:00:00Z",
            "saleEndsAt": "2027-06-01T11:00:00Z",
            "status": "ON_SALE",
            "ticketTypes": [
                {"code": "VIP", "name": "VIP", "price": {"amountMinor": 500000, "currency": "VND"}},
                {"code": "STD", "name": "Standard", "price": {"amountMinor": 200000, "currency": "VND"}},
            ],
            "resourceVersion": 3,
        }

    async def list_events(self, params, ctx):
        return [self.value]

    async def get_event(self, event_id, ctx):
        return {**self.value, "eventId": event_id}


class _Seat:
    async def get_seat_map(self, event_id, ctx):
        return {"eventId": event_id, "seats": {"seat": [
            {"seatId": "A1", "ticketTypeCode": "STD", "status": "AVAILABLE"},
            {"seatId": "V1", "ticketTypeCode": "VIP", "status": "SOLD"},
        ]}}

    async def check_availability(self, event_id, refs, ctx):
        return {"available": refs[0]["seatId"] == "A1"}


class _Booking:
    def value(self):
        return {
            "bookingId": "booking-1",
            "customerId": "customer-1",
            "eventId": "event-1",
            "items": [
                {"seatId": "A1", "ticketType": "STD", "ticketTypeCode": "STD", "unitPrice": "200000"}
            ],
            "seats": ["A1"],
            "total": "200000",
            "totalAmount": "200000",
            "currency": "VND",
            "status": "CONFIRMED",
            "paymentStatus": "SUCCEEDED",
            "reservationId": "reservation-1",
            "paymentId": "payment-1",
            "ticketIds": ["ticket-1"],
            "resourceVersion": 7,
            "createdAt": "2027-05-01T00:00:00Z",
            "updatedAt": "2027-05-01T00:10:00Z",
        }

    async def get(self, booking_id, ctx):
        return {**self.value(), "bookingId": booking_id}

    async def list_customer(self, customer_id, params, ctx):
        return {"items": [self.value()], "page": 1, "pageSize": 20, "total": 1, "totalPages": 1}


class _Ticket:
    def value(self):
        return {
            "ticketId": "ticket-1",
            "bookingId": "booking-1",
            "eventId": "event-1",
            "customerId": "customer-1",
            "seatId": "A1",
            "status": "ISSUED",
            "qrToken": "signed-owner-qr-token",
            "resourceVersion": 2,
        }

    async def get(self, ticket_id, ctx):
        return {**self.value(), "ticketId": ticket_id}

    async def list_booking(self, booking_id, ctx):
        return [self.value()]


class _Customer:
    async def resolve_identity(self, subject, ctx):
        return {"customerId": "customer-1"}


def context() -> RequestContext:
    return RequestContext(
        "corr-frontend",
        "a" * 32,
        time.monotonic() + 10,
        Principal("identity-1", frozenset({"CUSTOMER"}), "customer-1"),
    )


@pytest.mark.asyncio
async def test_query_facade_emits_frontend_contract_from_backend_outputs():
    service = QueryService(_Event(), _Seat(), _Booking(), _Ticket(), _Customer())
    ctx = context()
    document = canonical()

    event = await service.event_get("event-1", ctx)
    seat_map = await service.seat_map("event-1", ctx)
    bookings = await service.booking_list({"page": 1, "pageSize": 20}, ctx)
    ticket = await service.ticket_get("ticket-1", ctx)
    tickets = await service.ticket_list(ctx, page=1, page_size=20)

    assert_schema(document, "PublicEvent", event)
    assert_schema(document, "SeatMapProjection", seat_map)
    assert_schema(document, "BookingListProjection", bookings)
    assert_schema(document, "TicketProjection", ticket)
    assert_schema(document, "TicketListProjection", tickets)
    assert seat_map["seats"][0]["status"] == "AVAILABLE"
    assert seat_map["seats"][1]["status"] == "UNAVAILABLE"
    assert ticket["eventName"] == "Summer Show"
    assert ticket["ticketTypeName"] == "Standard"
    assert ticket["qrToken"] == "signed-owner-qr-token"
    assert "qrToken" not in tickets["items"][0]


def test_check_in_public_body_requires_qr_token_only():
    model = CheckInRequest(qrToken="x" * 16)
    assert model.model_dump() == {"qrToken": "x" * 16}


def test_event_projection_accepts_provider_optional_sale_dates():
    from app.application.projections import event_projection

    provider_event = {
        "eventId": "event-with-provider-minimum",
        "name": "Provider Minimum Event",
        "venue": "Hall B",
        "startsAt": "2027-06-01T12:00:00Z",
        "status": "DRAFT",
        "ticketTypes": [
            {
                "code": "STD",
                "name": "Standard",
                "price": {"amountMinor": 100000, "currency": "VND"},
            }
        ],
        "resourceVersion": 1,
    }
    projected = event_projection(provider_event)
    assert "saleStartsAt" not in projected
    assert "saleEndsAt" not in projected
    assert_schema(canonical(), "PublicEvent", projected)


def test_public_booking_enums_match_booking_service_contract():
    public = canonical()["components"]["schemas"]
    booking = provider("booking-service.yaml")["components"]["schemas"]
    assert public["BookingStatus"]["enum"] == booking["BookingStatus"]["enum"]
    assert public["BookingPaymentStatus"]["enum"] == booking["PaymentStatus"]["enum"]
