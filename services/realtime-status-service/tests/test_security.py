from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from libs.contract_testing import assert_openapi_conformance

from app.config import Settings


def test_production_rejects_wildcard_and_requires_ticket_key(
    settings: Settings,
) -> None:
    with pytest.raises(ValueError, match="Wildcard"):
        replace(settings, app_env="production", allowed_ws_origins=("*",))
    with pytest.raises(ValueError, match="ticket public key"):
        replace(
            settings,
            app_env="production",
            allowed_ws_origins=("https://customer.example",),
            ws_ticket_public_key_path=None,
        )


def test_generated_openapi_describes_service_jwt_and_contract_routes(
    client: TestClient,
) -> None:
    schema = client.get("/openapi.json").json()
    assert schema["components"]["securitySchemes"]["ServiceJwt"] == {
        "type": "http",
        "scheme": "bearer",
    }
    operation = schema["paths"]["/internal/status-events"]["post"]
    assert operation["security"] == [{"ServiceJwt": []}]
    assert "202" in operation["responses"]
    assert "/health/live" in schema["paths"]
    assert "/health/ready" in schema["paths"]


def test_provider_matches_canonical_contract(client: TestClient) -> None:
    canonical = Path(__file__).parents[3] / "contracts" / "realtime-service.openapi.yaml"
    assert_openapi_conformance(client.get("/openapi.json").json(), canonical)
