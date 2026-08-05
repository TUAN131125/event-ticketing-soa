from pathlib import Path

from libs.contract_testing import assert_openapi_conformance

from app.config import Settings
from app.main import create_app

EXPECTED_OPERATIONS = {
    "issueTickets",
    "getTicket",
    "listBookingTickets",
    "validateTicket",
    "cancelTicket",
    "checkInTicket",
    "reissueQr",
    "ticketLiveness",
    "ticketReadiness",
}


def test_openapi_has_unique_operation_ids_closed_models_and_security(
    ticket_settings: Settings,
) -> None:
    schema = create_app(ticket_settings).openapi()
    operation_ids: list[str] = []
    for path in schema["paths"].values():
        for operation in path.values():
            if isinstance(operation, dict) and "operationId" in operation:
                operation_ids.append(operation["operationId"])
    assert len(operation_ids) == len(set(operation_ids))
    assert EXPECTED_OPERATIONS.issubset(operation_ids)
    assert schema["components"]["securitySchemes"]["ServiceJwt"] == {
        "type": "http",
        "scheme": "bearer",
    }
    assert (
        schema["components"]["schemas"]["IssueTicketsRequest"]["additionalProperties"]
        is False
    )
    response_fields = schema["components"]["schemas"]["TicketResponse"]["properties"]
    assert "qrToken" in response_fields
    assert "qrCode" not in response_fields


def test_provider_matches_canonical_contract(ticket_settings: Settings) -> None:
    canonical = Path(__file__).parents[4] / "contracts" / "ticket-service.yaml"
    assert_openapi_conformance(create_app(ticket_settings).openapi(), canonical)
