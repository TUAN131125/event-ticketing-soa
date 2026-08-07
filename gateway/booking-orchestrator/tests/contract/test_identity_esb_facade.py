from __future__ import annotations

import json
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from app.adapters.rest.identity import IdentityProxyResponse
from app.main import create_app


USER = {
    "userId": "123e4567-e89b-12d3-a456-426614174000",
    "email": "user@example.com",
    "status": "ACTIVE",
    "roles": ["CUSTOMER"],
    "tokenVersion": 1,
    "createdAt": "2026-08-06T12:00:00Z",
}
TOKEN = {
    "accessToken": "signed-access-token",
    "tokenType": "Bearer",
    "expiresIn": 900,
    "csrfToken": "c" * 32,
    "user": USER,
}


class FakeIdentityProxy:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def proxy(self, method, path, ctx, **kwargs):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "headers": dict(kwargs.get("headers") or {}),
                "body": kwargs.get("body"),
                "idempotent": kwargs.get("idempotent", False),
            }
        )
        if path == "/auth/register":
            return IdentityProxyResponse(
                201,
                json.dumps(USER).encode(),
                "application/json",
                (),
                (),
            )
        if path in {"/auth/login", "/auth/refresh"}:
            return IdentityProxyResponse(
                200,
                json.dumps(TOKEN).encode(),
                "application/json",
                (("Cache-Control", "no-store"), ("Pragma", "no-cache")),
                (
                    "identity_refresh=refresh; HttpOnly; SameSite=lax; Path=/api/auth",
                    "identity_csrf=csrf; SameSite=lax; Path=/api/auth",
                ),
            )
        if path == "/auth/logout":
            return IdentityProxyResponse(
                204,
                b"",
                "application/json",
                (),
                (
                    "identity_refresh=; Max-Age=0; HttpOnly; SameSite=lax; Path=/api/auth",
                    "identity_csrf=; Max-Age=0; SameSite=lax; Path=/api/auth",
                ),
            )
        return IdentityProxyResponse(
            200,
            json.dumps(USER).encode(),
            "application/json",
            (),
            (),
        )


def client_with_identity() -> tuple[TestClient, FakeIdentityProxy]:
    app = create_app()
    identity = FakeIdentityProxy()
    app.state.container.identity = identity
    return TestClient(app), identity


def test_login_is_proxied_through_esb_and_preserves_cookie_headers():
    client, identity = client_with_identity()
    response = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "correct-password"},
    )
    assert response.status_code == 200
    assert response.json() == TOKEN
    assert response.headers["cache-control"] == "no-store"
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 2
    assert all("Path=/api/auth" in value for value in cookies)
    assert identity.calls[0]["path"] == "/auth/login"
    assert b"correct-password" in identity.calls[0]["body"]


def test_refresh_and_logout_forward_cookie_and_csrf_to_identity():
    client, identity = client_with_identity()
    headers = {
        "Cookie": "identity_refresh=refresh; identity_csrf=csrf",
        "X-CSRF-Token": "csrf",
    }
    refresh = client.post("/api/auth/refresh", headers=headers)
    logout = client.post("/api/auth/logout", headers=headers)
    assert refresh.status_code == 200
    assert logout.status_code == 204
    for call in identity.calls:
        assert call["headers"]["Cookie"] == headers["Cookie"]
        assert call["headers"]["X-CSRF-Token"] == "csrf"


def test_me_forwards_browser_bearer_token_without_service_token_substitution():
    client, identity = client_with_identity()
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer browser-access-token"},
    )
    assert response.status_code == 200
    assert identity.calls[0]["headers"]["Authorization"] == "Bearer browser-access-token"


def test_esb_openapi_declares_auth_facade_and_security_boundary():
    document = create_app().openapi()
    assert document["components"]["securitySchemes"]["UserJwt"]["scheme"] == "bearer"
    assert document["paths"]["/api/auth/register"]["post"]["security"] == []
    assert document["paths"]["/api/auth/login"]["post"]["security"] == []
    assert document["paths"]["/api/auth/me"]["get"]["security"] == [
        {"UserJwt": []}
    ]
    expected_cookie_security = [{"RefreshCookie": [], "CsrfCookie": [], "CsrfHeader": []}]
    assert document["paths"]["/api/auth/refresh"]["post"]["security"] == expected_cookie_security
    assert document["paths"]["/api/auth/logout"]["post"]["security"] == expected_cookie_security

    for path, status in (("/api/auth/login", "200"), ("/api/auth/refresh", "200"), ("/api/auth/logout", "204")):
        headers = document["paths"][path]["post"]["responses"][status]["headers"]
        assert "Set-Cookie" in headers
        assert "Cache-Control" in headers


def test_identity_provider_and_esb_facade_share_the_current_github_wire_shapes():
    repository_root = Path(__file__).resolve().parents[4]
    provider = yaml.safe_load(
        (repository_root / "contracts/providers/identity-service.yaml").read_text()
    )
    esb = yaml.safe_load((repository_root / "contracts/esb-public-api.yaml").read_text())
    provider_schemas = provider["components"]["schemas"]
    esb_schemas = esb["components"]["schemas"]
    for name in ("RegisterRequest", "LoginRequest", "User", "TokenResponse"):
        provider_required = set(provider_schemas[name].get("required", []))
        esb_required = set(esb_schemas[name].get("required", []))
        assert provider_required == esb_required
        assert set(provider_schemas[name].get("properties", {})) == set(
            esb_schemas[name].get("properties", {})
        )
