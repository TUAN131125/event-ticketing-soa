from app.config import Settings
from app.main import create_app

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
}
def settings() -> Settings:
    return Settings(
        app_name="payment-service",
        app_env="test",
        database_url="postgresql+psycopg://payment:payment@localhost:5438/payment",
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
