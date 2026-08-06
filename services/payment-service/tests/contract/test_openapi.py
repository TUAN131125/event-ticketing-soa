import json
from pathlib import Path

import yaml

from app.config import Settings
from app.main import create_app
from tests.factories import build_settings

EXPECTED_OPERATIONS = {
    "createPayment",
    "listPayments",
    "getPayment",
    "listPaymentRefunds",
    "authorizePayment",
    "capturePayment",
    "cancelPayment",
    "refundPayment",
    "reconcilePayment",
    "createPaymentRefund",
    "handleProviderCallback",
    "listPaymentProviderEvents",
    "paymentLiveness",
    "paymentReadiness",
}
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def settings() -> Settings:
    return build_settings()


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
        "description": "Internal shared secret. Never send payment credentials here.",
        "in": "header",
        "name": "X-Service-Token",
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


def test_shared_openapi_and_event_contracts_match_the_service() -> None:
    contract_path = REPOSITORY_ROOT / "contracts" / "openapi" / "payment-service.yaml"
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
        "payment-created.schema.json": "payment.created",
        "payment-authorized.schema.json": "payment.authorized",
        "payment-succeeded.schema.json": "payment.succeeded",
        "payment-failed.schema.json": "payment.failed",
        "payment-cancelled.schema.json": "payment.cancelled",
        "payment-refunded.schema.json": "payment.refunded",
        "payment-unknown.schema.json": "payment.unknown",
        "payment-reconciled.schema.json": "payment.reconciled",
    }
    for filename, event_type in expected_events.items():
        schema = json.loads((events_path / filename).read_text(encoding="utf-8"))
        assert schema["title"] == event_type
        assert schema["properties"]["eventType"]["const"] == event_type
        assert "payload" in schema["required"]

LEGACY_OPERATIONS = {
    ("get", "/health/live", "paymentLiveness"),
    ("get", "/health/ready", "paymentReadiness"),
    ("post", "/payments", "createPayment"),
    ("get", "/payments", "listPayments"),
    ("get", "/payments/{payment_id}", "getPayment"),
    ("get", "/payments/{payment_id}/refunds", "listPaymentRefunds"),
    ("post", "/payments/{payment_id}/authorize", "authorizePayment"),
    ("post", "/payments/{payment_id}/capture", "capturePayment"),
    ("post", "/payments/{payment_id}/cancel", "cancelPayment"),
    ("post", "/payments/{payment_id}/refund", "refundPayment"),
    ("post", "/payments/{payment_id}/reconcile", "reconcilePayment"),
}


def test_legacy_paths_operation_ids_and_request_fields_are_preserved() -> None:
    schema = create_app(settings()).openapi()
    for method, path, operation_id in LEGACY_OPERATIONS:
        assert schema["paths"][path][method]["operationId"] == operation_id

    components = schema["components"]["schemas"]
    legacy_request_fields = {
        "CreatePaymentRequest": {
            "bookingId",
            "customerId",
            "amount",
            "currency",
            "paymentMethod",
            "provider",
        },
        "AuthorizePaymentRequest": {
            "approved",
            "providerReference",
            "failureCode",
            "reason",
            "expectedVersion",
        },
        "CapturePaymentRequest": {
            "succeeded",
            "providerReference",
            "failureCode",
            "reason",
            "expectedVersion",
        },
        "RefundPaymentRequest": {
            "amount",
            "reason",
            "providerRefundReference",
            "expectedVersion",
        },
    }
    for schema_name, expected_fields in legacy_request_fields.items():
        actual_fields = set(components[schema_name]["properties"])
        assert expected_fields.issubset(actual_fields)
