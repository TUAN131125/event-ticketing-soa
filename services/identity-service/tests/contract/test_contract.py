from pathlib import Path

import yaml

from app.main import create_app
from app.openapi import route_operation_ids

EXPECTED_OPERATIONS = {
    ("POST", "/auth/register"): "registerIdentityAccount",
    ("POST", "/auth/login"): "loginIdentityAccount",
    ("POST", "/auth/refresh"): "refreshIdentitySession",
    ("POST", "/auth/logout"): "logoutIdentitySession",
    ("GET", "/auth/me"): "getCurrentIdentityPrincipal",
    ("POST", "/admin/users/{userId}/roles"): "changeIdentityUserRole",
    ("GET", "/.well-known/jwks.json"): "getIdentityJwks",
    ("GET", "/health/live"): "identityLiveness",
    ("GET", "/health/ready"): "identityReadiness",
}


def _canonical() -> dict:
    return yaml.safe_load(
        Path(__file__)
        .parents[4]
        .joinpath("contracts/identity-service.yaml")
        .read_text(encoding="utf-8")
    )


def test_canonical_contract_names_are_locked():
    document = _canonical()
    assert document["openapi"] == "3.1.0"
    actual = {
        (method.upper(), path): operation["operationId"]
        for path, path_item in document["paths"].items()
        for method, operation in path_item.items()
        if method.lower() in {"get", "post", "put", "patch", "delete"}
    }
    assert actual == EXPECTED_OPERATIONS
    schemes = document["components"]["securitySchemes"]
    assert {"UserJwt", "ServiceJwt", "WebhookHmac", "RefreshCookie"} <= set(schemes)
    assert "BearerAuth" not in schemes
    assert "UserBearerAuth" not in schemes
    claims = document["components"]["schemas"]["AccessTokenClaims"]
    assert "jti" in claims["required"]
    assert "customerId" not in claims["properties"]
    assert document["components"]["schemas"]["Role"]["enum"] == [
        "CUSTOMER",
        "ADMIN",
        "CHECKIN_STAFF",
        "SERVICE",
    ]


def test_runtime_routes_match_canonical_operation_ids(unit_settings):
    application = create_app(unit_settings)
    actual = route_operation_ids(application)
    assert {key: actual[key] for key in EXPECTED_OPERATIONS} == EXPECTED_OPERATIONS


def test_runtime_openapi_is_the_reviewed_contract(contract_client):
    runtime = contract_client.get("/openapi.json").json()
    canonical = _canonical()
    assert runtime == canonical


def test_contract_documents_local_transport_inputs_and_outputs():
    document = _canonical()
    assert document["servers"] == [
        {
            "url": "http://localhost:8009",
            "description": (
                "Local contract endpoint; deployment host is supplied by configuration."
            ),
        }
    ]

    common_parameters = {
        "#/components/parameters/CorrelationId",
        "#/components/parameters/Traceparent",
    }
    for path_item in document["paths"].values():
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            refs = {
                parameter["$ref"]
                for parameter in operation.get("parameters", [])
                if "$ref" in parameter
            }
            assert common_parameters.issubset(refs)

    for route in ("/auth/refresh", "/auth/logout"):
        refs = {
            parameter["$ref"]
            for parameter in document["paths"][route]["post"]["parameters"]
        }
        assert "#/components/parameters/CsrfHeader" in refs
        assert "#/components/parameters/CsrfCookie" in refs

    for route in (
        "/auth/register",
        "/auth/login",
        "/admin/users/{userId}/roles",
    ):
        assert (
            document["paths"][route]["post"]["responses"]["413"]["$ref"]
            == "#/components/responses/PayloadTooLarge"
        )

    assert (
        "Set-Cookie"
        in document["paths"]["/auth/login"]["post"]["responses"]["200"]["headers"]
    )
    assert (
        "Set-Cookie"
        in document["paths"]["/auth/refresh"]["post"]["responses"]["200"]["headers"]
    )
    assert (
        "Set-Cookie"
        in document["paths"]["/auth/logout"]["post"]["responses"]["204"]["headers"]
    )
