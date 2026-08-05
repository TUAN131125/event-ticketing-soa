from pathlib import Path

from libs.contract_testing import assert_openapi_conformance

from app.config import Settings
from app.main import create_app

EXPECTED_OPERATIONS = {
    "createPayment",
    "getPayment",
    "authorizePayment",
    "capturePayment",
    "cancelPayment",
    "createRefund",
    "receiveProviderCallback",
    "reconcilePayment",
    "paymentLiveness",
    "paymentReadiness",
}


def test_openapi_has_unique_operation_ids_and_closed_request_models(
    payment_settings: Settings,
) -> None:
    schema = create_app(payment_settings).openapi()
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
        schema["components"]["schemas"]["CreatePaymentRequest"]["additionalProperties"]
        is False
    )
    create_properties = schema["components"]["schemas"]["CreatePaymentRequest"][
        "properties"
    ]
    assert "cardNumber" not in create_properties
    assert "cvv" not in create_properties


def test_provider_matches_canonical_contract(payment_settings: Settings) -> None:
    canonical = Path(__file__).parents[4] / "contracts" / "payment-service.yaml"
    assert_openapi_conformance(create_app(payment_settings).openapi(), canonical)
