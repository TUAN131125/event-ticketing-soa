import json
from pathlib import Path

import yaml

from app.config import Settings
from app.main import create_app

EXPECTED_OPERATIONS = {
    "issueTickets",
    "listTickets",
    "getTicket",
    "cancelTicket",
    "checkInTicket",
    "regenerateTicketQr",
}
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def settings() -> Settings:
    return Settings(
        app_name="ticket-service",
        app_env="test",
        database_url="postgresql+psycopg://ticket:ticket@localhost:5439/ticket",
        service_token="test-service-token",
        qr_signing_key="test-qr-signing-key-that-is-long-enough",
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


def test_openapi_has_unique_operation_ids_closed_models_and_security() -> None:
    schema = create_app(settings()).openapi()
    operation_ids: list[str] = []
    for path in schema["paths"].values():
        for operation in path.values():
            if isinstance(operation, dict) and "operationId" in operation:
                operation_ids.append(operation["operationId"])
    assert len(operation_ids) == len(set(operation_ids))
    assert EXPECTED_OPERATIONS.issubset(operation_ids)
    assert schema["components"]["securitySchemes"]["serviceToken"] == {
        "type": "apiKey",
        "description": "Internal shared secret. Never expose QR signing material here.",
        "in": "header",
        "name": "X-Service-Token",
    }
    assert (
        schema["components"]["schemas"]["IssueTicketsRequest"]["additionalProperties"]
        is False
    )
    response_fields = schema["components"]["schemas"]["TicketResponse"]["properties"]
    assert "qrToken" not in response_fields
    assert "qrCode" in response_fields


def test_shared_openapi_and_event_contracts_match_the_service() -> None:
    contract_path = REPOSITORY_ROOT / "contracts" / "openapi" / "ticket-service.yaml"
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
        "ticket-issued.schema.json": "ticket.issued",
        "ticket-checked-in.schema.json": "ticket.checked-in",
        "ticket-cancelled.schema.json": "ticket.cancelled",
        "ticket-qr-regenerated.schema.json": "ticket.qr-regenerated",
    }
    for filename, event_type in expected_events.items():
        schema = json.loads((events_path / filename).read_text(encoding="utf-8"))
        assert schema["title"] == event_type
        assert schema["properties"]["eventType"]["const"] == event_type
        assert "payload" in schema["required"]
