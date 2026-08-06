#!/usr/bin/env python3
"""Deterministically generate browser TypeScript types from canonical contracts.

The normal npm/openapi-typescript generator remains the primary workflow. This fallback
regenerates the ESB public API, Identity provider API, Realtime provider API, and Realtime
AsyncAPI message schemas when npm packages cannot be downloaded. No wire type is copied
by hand.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

FRONTEND_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_ROOT = FRONTEND_ROOT.parent / "contracts"
GENERATED_ROOT = FRONTEND_ROOT / "shared-ui" / "src" / "generated"
GENERATORS = (
    ("esb-public-api.yaml", "esb-public-api.ts", False),
    ("providers/identity-service.yaml", "identity-service.ts", False),
    ("providers/realtime-status-service.yaml", "realtime-service.ts", False),
    ("providers/realtime-status.asyncapi.yaml", "realtime-messages.ts", True),
)
HTTP_METHODS = ("get", "put", "post", "delete", "patch", "options", "head", "trace")


def quote_key(value: str) -> str:
    return value if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", value) else json.dumps(value)


def ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def schema_to_ts(schema: Any) -> str:
    if schema is None:
        return "unknown"
    if schema is True:
        return "unknown"
    if schema is False:
        return "never"
    if not isinstance(schema, dict):
        return "unknown"
    if "$ref" in schema:
        ref = str(schema["$ref"])
        if ref.startswith("#/components/schemas/"):
            return f"components['schemas'][{json.dumps(ref_name(ref))}]"
        return "unknown"
    if "const" in schema:
        return json.dumps(schema["const"])
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return " | ".join(json.dumps(value) for value in enum)
    for union_key in ("oneOf", "anyOf"):
        if isinstance(schema.get(union_key), list):
            values = [schema_to_ts(item) for item in schema[union_key]]
            return " | ".join(dict.fromkeys(values)) or "unknown"
    if isinstance(schema.get("allOf"), list):
        values = [schema_to_ts(item) for item in schema["allOf"]]
        return " & ".join(dict.fromkeys(values)) or "unknown"

    raw_type = schema.get("type")
    if isinstance(raw_type, list):
        values = [schema_to_ts({**schema, "type": value}) for value in raw_type]
        return " | ".join(dict.fromkeys(values))
    if raw_type == "null":
        return "null"
    if raw_type == "string":
        return "string"
    if raw_type in {"integer", "number"}:
        return "number"
    if raw_type == "boolean":
        return "boolean"
    if raw_type == "array":
        item = schema_to_ts(schema.get("items", {}))
        return f"({item})[]" if " | " in item or " & " in item else f"{item}[]"
    if raw_type == "object" or "properties" in schema or "additionalProperties" in schema:
        properties = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        fields: list[str] = []
        for name, value in properties.items():
            optional = "" if name in required else "?"
            description = value.get("description") if isinstance(value, dict) else None
            if description:
                safe = str(description).replace("*/", "* /").replace("\n", " ")
                fields.append(f"/** {safe} */")
            fields.append(f"{quote_key(str(name))}{optional}: {schema_to_ts(value)};")
        additional = schema.get("additionalProperties")
        if additional is True:
            fields.append("[key: string]: unknown;")
        elif isinstance(additional, dict):
            fields.append(f"[key: string]: {schema_to_ts(additional)};")
        if not fields:
            return "Record<string, never>" if additional is False else "Record<string, unknown>"
        return "{ " + " ".join(fields) + " }"
    return "unknown"


def resolve_ref(document: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    ref = value.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/components/"):
        return value
    parts = ref.removeprefix("#/components/").split("/")
    current: Any = document.get("components", {})
    for part in parts:
        current = current[part]
    return current


def content_to_ts(content: Any) -> str:
    if not isinstance(content, dict) or not content:
        return "never"
    fields = []
    for media_type, media in content.items():
        schema = media.get("schema", {}) if isinstance(media, dict) else {}
        fields.append(f"{json.dumps(str(media_type))}: {schema_to_ts(schema)};")
    return "{ " + " ".join(fields) + " }"


def parameter_groups(document: dict[str, Any], parameters: list[Any]) -> str:
    groups: dict[str, list[tuple[str, bool, str]]] = {
        "query": [],
        "header": [],
        "path": [],
        "cookie": [],
    }
    for parameter in parameters:
        if not isinstance(parameter, dict):
            continue
        parameter = resolve_ref(document, parameter)
        where = parameter.get("in")
        if where not in groups:
            continue
        groups[where].append(
            (
                str(parameter.get("name")),
                bool(parameter.get("required")),
                schema_to_ts(parameter.get("schema", {})),
            )
        )
    rendered = []
    for group in ("query", "header", "path", "cookie"):
        values = groups[group]
        if not values:
            rendered.append(f"{group}?: never;")
            continue
        fields = " ".join(
            f"{quote_key(name)}{'' if required else '?'}: {kind};"
            for name, required, kind in values
        )
        rendered.append(f"{group}: {{ {fields} }};")
    return "{ " + " ".join(rendered) + " }"


def headers_to_ts(document: dict[str, Any], headers: Any) -> str:
    if not isinstance(headers, dict) or not headers:
        return "Record<string, never>"
    fields = []
    for name, header in headers.items():
        if isinstance(header, dict):
            header = resolve_ref(document, header)
        fields.append(f"{quote_key(str(name))}?: {schema_to_ts(header.get('schema', {}))};")
    return "{ " + " ".join(fields) + " }"


def operation_to_ts(document: dict[str, Any], operation: dict[str, Any], path_parameters: list[Any]) -> str:
    parameters = [*path_parameters, *(operation.get("parameters") or [])]
    lines = [f"parameters: {parameter_groups(document, parameters)};"]
    request_body = operation.get("requestBody")
    if isinstance(request_body, dict):
        request_body = resolve_ref(document, request_body)
        optional = "" if request_body.get("required") else "?"
        lines.append(f"requestBody{optional}: {{ content: {content_to_ts(request_body.get('content'))}; }};")
    else:
        lines.append("requestBody?: never;")

    response_fields: list[str] = []
    for status, response in (operation.get("responses") or {}).items():
        if isinstance(response, dict):
            response = resolve_ref(document, response)
        response_fields.append(
            f"{quote_key(str(status))}: {{ headers: {headers_to_ts(document, response.get('headers'))}; "
            f"content: {content_to_ts(response.get('content'))}; }};"
        )
    lines.append("responses: { " + " ".join(response_fields) + " };")
    return "{ " + " ".join(lines) + " }"


def generate(document: dict[str, Any], digest: str, source: str) -> str:
    schemas = document.get("components", {}).get("schemas", {})
    schema_fields = [
        f"{quote_key(str(name))}: {schema_to_ts(schema)};" for name, schema in schemas.items()
    ]
    components = (
        "export interface components {\n"
        "  schemas: {\n    "
        + "\n    ".join(schema_fields)
        + "\n  };\n"
        "  responses: Record<string, never>;\n"
        "  parameters: Record<string, never>;\n"
        "  requestBodies: Record<string, never>;\n"
        "  headers: Record<string, never>;\n"
        "  pathItems: Record<string, never>;\n"
        "}\n"
    )

    operations: dict[str, tuple[dict[str, Any], list[Any]]] = {}
    path_methods: dict[str, dict[str, str]] = {}
    for path, path_item in (document.get("paths") or {}).items():
        if not isinstance(path_item, dict):
            continue
        path_parameters = path_item.get("parameters") or []
        methods: dict[str, str] = {}
        for method in HTTP_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId")
            if not operation_id:
                raise ValueError(f"Missing operationId for {method.upper()} {path}")
            operations[str(operation_id)] = (operation, path_parameters)
            methods[method] = str(operation_id)
        path_methods[str(path)] = methods

    operation_lines = [
        f"  {quote_key(name)}: {operation_to_ts(document, operation, path_parameters)};"
        for name, (operation, path_parameters) in operations.items()
    ]
    operation_interface = "export interface operations {\n" + "\n".join(operation_lines) + "\n}\n"

    path_lines: list[str] = []
    for path, methods in path_methods.items():
        method_fields = []
        for method in HTTP_METHODS:
            operation_id = methods.get(method)
            method_fields.append(
                f"{method}: operations[{json.dumps(operation_id)}];"
                if operation_id
                else f"{method}?: never;"
            )
        path_lines.append(
            f"  {json.dumps(path)}: {{ parameters: {{ query?: never; header?: never; path?: never; cookie?: never; }}; "
            + " ".join(method_fields)
            + " };"
        )
    paths_interface = "export interface paths {\n" + "\n".join(path_lines) + "\n}\n"

    return (
        f"// Generated from contracts/{source}. Do not edit manually.\n"
        f"// Contract SHA-256: {digest}\n"
        "// Generator: frontend/scripts/generate_esb_types.py\n\n"
        + paths_interface
        + "\nexport type webhooks = Record<string, never>;\n\n"
        + components
        + "\n"
        + operation_interface
        + "\nexport type $defs = Record<string, never>;\n"
    )


def inline_local_defs(schema: Any, defs: dict[str, Any]) -> Any:
    if isinstance(schema, list):
        return [inline_local_defs(item, defs) for item in schema]
    if not isinstance(schema, dict):
        return schema
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        name = ref.removeprefix("#/$defs/")
        if name not in defs:
            raise ValueError(f"Unresolved local definition {ref}")
        return inline_local_defs(defs[name], defs)
    return {
        key: inline_local_defs(value, defs)
        for key, value in schema.items()
        if key != "$defs"
    }


def asyncapi_schema_document(asyncapi: dict[str, Any]) -> dict[str, Any]:
    components = asyncapi.get("components", {})
    schemas = components.get("schemas", {})
    required = {
        "RealtimeClientMessage",
        "RealtimeMessage",
        "RealtimeServerControlMessage",
    }
    if not isinstance(schemas, dict) or not required.issubset(schemas):
        missing = sorted(required - set(schemas if isinstance(schemas, dict) else {}))
        raise ValueError(f"AsyncAPI is missing canonical message schemas: {missing}")
    info = asyncapi.get("info", {})
    return {
        "openapi": "3.1.0",
        "info": {
            "title": info.get("title", "Realtime message schemas"),
            "version": info.get("version", "0.0.0"),
        },
        "paths": {},
        # Preserve every shared schema because message schemas may reference BookingStatus.
        "components": {"schemas": schemas},
    }


def main() -> None:
    GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
    for source, output_name, is_asyncapi in GENERATORS:
        contract_path = CONTRACTS_ROOT / source
        raw = contract_path.read_bytes()
        document = yaml.safe_load(raw)
        if not isinstance(document, dict):
            raise ValueError(f"Contract {contract_path} is not a mapping")
        generated_document = asyncapi_schema_document(document) if is_asyncapi else document
        digest = hashlib.sha256(raw).hexdigest()
        output_path = GENERATED_ROOT / output_name
        output_path.write_text(generate(generated_document, digest, source), encoding="utf-8")
        print(f"Generated {output_path} from {contract_path} ({digest})")


if __name__ == "__main__":
    main()
