import json
from pathlib import Path

import yaml

from app.config import Settings
from app.main import create_app

EXPECTED_OPERATIONS = {
    "createBooking",
    "listBookings",
    "getBooking",
    "confirmBooking",
    "failBooking",
    "cancelBooking",
}
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def settings() -> Settings:
    return Settings(
        app_name="booking-service",
        app_env="test",
        database_url="postgresql+psycopg://booking:booking@localhost:5437/booking",
        service_token="test-service-token",
        db_pool_size=1,
        db_max_overflow=0,
        db_pool_timeout_seconds=1,
        db_connect_timeout_seconds=1,
        db_lock_timeout_ms=1_000,
        db_statement_timeout_ms=5_000,
        idempotency_ttl_seconds=3_600,
        log_level="WARNING",
        docs_enabled=True,
    )


def test_openapi_has_unique_operation_ids_and_closed_request_models() -> None:
    schema = create_app(settings()).openapi()
    operation_ids: list[str] = []
    for path in schema["paths"].values():
        for operation in path.values():
            if isinstance(operation, dict) and "operationId" in operation:
                operation_ids.append(operation["operationId"])
    assert len(operation_ids) == len(set(operation_ids))
    assert EXPECTED_OPERATIONS.issubset(operation_ids)
    service_token = schema["components"]["securitySchemes"]["serviceToken"]
    assert service_token == {
        "type": "apiKey",
        "description": "Internal shared secret. Never forward a customer token here.",
        "in": "header",
        "name": "X-Service-Token",
    }
    assert (
        schema["components"]["schemas"]["CreateBookingRequest"]["additionalProperties"]
        is False
    )


def test_shared_openapi_and_event_contracts_match_the_service() -> None:
    contract_path = REPOSITORY_ROOT / "contracts" / "openapi" / "booking-service.yaml"
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    static_operations = {
        operation["operationId"]
        for path_item in contract["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
    assert static_operations == EXPECTED_OPERATIONS

    events_path = REPOSITORY_ROOT / "contracts" / "events"
    expected_events = {
        "booking-created.schema.json": "booking.created",
        "booking-confirmed.schema.json": "booking.confirmed",
        "booking-failed.schema.json": "booking.failed",
        "booking-cancelled.schema.json": "booking.cancelled",
    }
    for filename, event_type in expected_events.items():
        schema = json.loads((events_path / filename).read_text(encoding="utf-8"))
        assert schema["title"] == event_type
        assert schema["properties"]["eventType"]["const"] == event_type
        assert "payload" in schema["required"]
