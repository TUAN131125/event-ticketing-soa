from pathlib import Path

import yaml


def test_openapi_contract_is_valid_and_closed():
    document = yaml.safe_load(
        Path(__file__)
        .parents[2]
        .joinpath("contracts/identity-service.yaml")
        .read_text()
    )
    assert document["openapi"] == "3.1.0"
    assert document["paths"]["/auth/register"]["post"]["operationId"] == "register"
    assert document["paths"]["/auth/refresh"]["post"]["operationId"] == "refresh"
    assert (
        document["components"]["schemas"]["RegisterRequest"]["additionalProperties"]
        is False
    )


def test_runtime_openapi_has_unique_operation_ids(client):
    document = client.get("/openapi.json").json()
    operation_ids = [
        operation["operationId"]
        for path in document["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]
    assert len(operation_ids) == len(set(operation_ids))
    assert "BearerAuth" in document["components"]["securitySchemes"]
