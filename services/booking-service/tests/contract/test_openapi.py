from pathlib import Path

from libs.contract_testing import assert_openapi_conformance

from app.config import Settings
from app.main import create_app

EXPECTED_OPERATIONS = {
    "createBooking",
    "getBooking",
    "listCustomerBookings",
    "bookingReservation",
    "bookingPaymentStarted",
    "bookingPaymentResult",
    "bookingTickets",
    "bookingConfirm",
    "bookingFail",
    "bookingCancel",
    "decideBookingResourceAccess",
}


def test_openapi_matches_canonical_operations(booking_settings: Settings) -> None:
    schema = create_app(booking_settings).openapi()
    operation_ids = {
        operation["operationId"]
        for path in schema["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
    assert EXPECTED_OPERATIONS.issubset(operation_ids)
    assert schema["components"]["securitySchemes"]["ServiceJwt"] == {
        "type": "http",
        "scheme": "bearer",
    }
    assert (
        schema["components"]["schemas"]["CreateBookingRequest"]["additionalProperties"]
        is False
    )


def test_provider_matches_canonical_contract(booking_settings: Settings) -> None:
    canonical = Path(__file__).parents[4] / "contracts" / "booking-service.yaml"
    assert_openapi_conformance(create_app(booking_settings).openapi(), canonical)
