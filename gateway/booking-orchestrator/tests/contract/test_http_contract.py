from fastapi.testclient import TestClient
from jsonschema import validate

from app.api.router import parse_if_match
from app.domain.errors import EsbError
from app.main import create_app


def test_validation_errors_use_canonical_error_envelope():
    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/api/bookings",
        headers={"Idempotency-Key": "idem-12345678"},
        json={"eventId": "event-1"},
    )
    assert response.status_code == 422
    body = response.json()
    validate(body, {"$ref": "#/components/schemas/ErrorResponse", "components": app.openapi()["components"]})
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert response.headers["X-Correlation-ID"] == body["correlationId"]
    serialized = str(body)
    assert "input" not in serialized.lower()


def test_if_match_accepts_only_canonical_quoted_positive_version():
    assert parse_if_match('"3"') == 3
    for invalid in ("3", '"0"', 'W/"3"', '"-1"', ""):
        try:
            parse_if_match(invalid)
        except EsbError as exc:
            assert exc.status_code == 400
            assert exc.code == "INVALID_IF_MATCH"
        else:
            raise AssertionError(f"Expected invalid If-Match: {invalid}")


def test_dynamic_health_endpoints_do_not_emit_resource_etags():
    client = TestClient(create_app())
    live = client.get("/health/live")
    ready = client.get("/health/ready")
    assert live.status_code == 200
    assert "etag" not in live.headers
    assert "etag" not in ready.headers
