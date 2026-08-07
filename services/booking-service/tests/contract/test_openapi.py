"""Contract tests for the self-contained Booking Service artifact."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from tests.factories import build_settings
from app.main import create_app

SERVICE_ROOT = Path(__file__).resolve().parents[2]
BUSINESS_OPERATIONS = {
    "createBooking",
    "listBookings",
    "getBooking",
    "listCustomerBookings",
    "reconcileBookings",
    "getBookingHistory",
    "attachReservation",
    "confirmReservationEvidence",
    "startPayment",
    "recordPayment",
    "attachTickets",
    "confirmBooking",
    "failBooking",
    "cancelBooking",
    "recordCompensationResult",
}
HEALTH_OPERATIONS = {"bookingLiveness", "bookingReadiness"}
EXPECTED_OPERATIONS = BUSINESS_OPERATIONS | HEALTH_OPERATIONS


def settings():
    return build_settings()


def operation_ids(schema: dict[str, object]) -> list[str]:
    paths = schema["paths"]
    assert isinstance(paths, dict)
    return [
        operation["operationId"]
        for path_item in paths.values()
        if isinstance(path_item, dict)
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]


def test_openapi_has_unique_expected_operations_and_closed_request_models() -> None:
    schema = create_app(settings()).openapi()
    ids = operation_ids(schema)

    assert len(ids) == len(set(ids))
    assert set(ids) == EXPECTED_OPERATIONS
    assert BUSINESS_OPERATIONS.issubset(ids)

    schemes = schema["components"]["securitySchemes"]
    # Internal callers authenticate with the shared Service JWT, not a shared secret.
    assert schemes["ServiceJwt"] == {"type": "http", "scheme": "bearer"}
    assert "serviceToken" not in schemes
    assert (
        schema["components"]["schemas"]["CreateBookingRequest"][
            "additionalProperties"
        ]
        is False
    )


def test_versioned_openapi_is_reproducible_from_runtime() -> None:
    contract_path = SERVICE_ROOT / "contracts" / "openapi" / "booking-service.yaml"
    static_contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    runtime_contract = create_app(settings()).openapi()

    assert static_contract == runtime_contract
    assert static_contract["openapi"].startswith("3.1")
    assert static_contract["info"]["version"] == "2.0.0"
    assert set(operation_ids(static_contract)) == EXPECTED_OPERATIONS



def test_mutations_support_if_match_without_breaking_legacy_body_version() -> None:
    schema = create_app(settings()).openapi()
    mutation_operations = {
        "attachReservation",
        "confirmReservationEvidence",
        "startPayment",
        "recordPayment",
        "attachTickets",
        "confirmBooking",
        "failBooking",
        "cancelBooking",
        "recordCompensationResult",
    }
    found: set[str] = set()
    for path_item in schema["paths"].values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId")
            if operation_id not in mutation_operations:
                continue
            found.add(operation_id)
            parameters = operation.get("parameters", [])
            if_match = next(
                item
                for item in parameters
                if item.get("in") == "header" and item.get("name") == "If-Match"
            )
            assert if_match["required"] is False
            success = operation["responses"]["200"]
            assert "ETag" in success["headers"]

    assert found == mutation_operations

    paths = schema["paths"]
    assert "ETag" in paths["/bookings"]["post"]["responses"]["201"]["headers"]
    get_response = paths["/bookings/{booking_id}"]["get"]["responses"]["200"]
    assert "ETag" in get_response["headers"]

    request_names = {
        "AttachReservationRequest",
        "ConfirmReservationRequest",
        "StartPaymentRequest",
        "RecordPaymentRequest",
        "AttachTicketsRequest",
        "ConfirmBookingRequest",
        "FailBookingRequest",
        "CancelBookingRequest",
        "CompensationResultRequest",
    }
    for request_name in request_names:
        request_schema = schema["components"]["schemas"][request_name]
        assert "expectedVersion" not in request_schema.get("required", [])

def test_documented_booking_event_schemas_are_valid_draft_2020_12() -> None:
    events_path = SERVICE_ROOT / "contracts" / "events"
    expected_events = {
        "booking-created.schema.json": "booking.created",
        "booking-confirmed.schema.json": "booking.confirmed",
        "booking-failed.schema.json": "booking.failed",
        "booking-cancelled.schema.json": "booking.cancelled",
    }

    for filename, event_type in expected_events.items():
        schema = json.loads((events_path / filename).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["title"] == event_type
        assert schema["properties"]["eventType"]["const"] == event_type
        assert "payload" in schema["required"]
