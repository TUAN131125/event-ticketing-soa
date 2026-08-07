"""Semantic parity between the ESB runtime schema and the canonical public contract.

The canonical document (`contracts/esb-public-api.yaml`) is curated: it adds servers, a
reusable parameter/response vocabulary, UTC constraints on date-time strings and prose
descriptions that FastAPI cannot express. Byte equality is therefore the wrong check —
it either forbids curation or forces the canonical to be a raw `app.openapi()` dump.

What must not drift is the wire contract, so every comparison here resolves local
`$ref`s on both sides and then demands exact equality of:

  * the set of method/path pairs, and the operationId of each;
  * the request body schema and whether a body is required;
  * the response status codes, their body schemas and their header names;
  * every header parameter, including whether it is required — If-Match and
    Idempotency-Key are compared like any other header, never skipped;
  * the effective security requirement of each operation, and the definition of every
    security scheme an operation actually references.

Only documentation-shaped keys are normalised away (`title`, `description`, `example`,
`summary`) plus the UTC `pattern` the canonical adds beside `format: date-time`. A change
to a type, an enum, a required list, a status code, a header or a security requirement on
either side is reported.
"""

from __future__ import annotations

from typing import Any

METHODS = frozenset({"get", "post", "put", "patch", "delete"})
UTC_PATTERN = r"(?:Z|\+00:00)$"
# Present only to describe the document to a reader; they carry no wire meaning.
DOCUMENTATION_KEYS = frozenset({"title", "description", "example", "examples", "summary"})


def _pointer(document: dict[str, Any], ref: str) -> Any:
    node: Any = document
    for raw in ref.lstrip("#/").split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        node = node[key]
    return node


def normalize(node: Any, document: dict[str, Any], seen: frozenset[str] = frozenset()) -> Any:
    """Resolve local $refs and drop documentation-only keys."""
    if isinstance(node, list):
        return [normalize(item, document, seen) for item in node]
    if not isinstance(node, dict):
        return node

    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/"):
        if ref in seen:
            # A self-referential schema is compared by identity rather than expanded.
            return {"$circular": ref}
        merged = dict(_pointer(document, ref))
        merged.update({key: value for key, value in node.items() if key != "$ref"})
        return normalize(merged, document, seen | {ref})

    result: dict[str, Any] = {}
    for key, value in node.items():
        if key in DOCUMENTATION_KEYS:
            continue
        result[key] = normalize(value, document, seen)
    if result.get("format") == "date-time" and result.get("pattern") == UTC_PATTERN:
        del result["pattern"]
    return result


def _operations(document: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (method, path): operation
        for path, item in document.get("paths", {}).items()
        if isinstance(item, dict)
        for method, operation in item.items()
        if method in METHODS and isinstance(operation, dict)
    }


def _parameters(document: dict[str, Any], operation: dict[str, Any]) -> dict[tuple[str, str], Any]:
    resolved: dict[tuple[str, str], Any] = {}
    for parameter in operation.get("parameters", []):
        expanded = normalize(parameter, document)
        key = (expanded.get("name"), expanded.get("in"))
        resolved[key] = {
            "required": bool(expanded.get("required")),
            "schema": expanded.get("schema"),
        }
    return resolved


def _request_body(document: dict[str, Any], operation: dict[str, Any]) -> Any:
    body = operation.get("requestBody")
    if body is None:
        return None
    expanded = normalize(body, document)
    return {
        "required": bool(expanded.get("required")),
        "content": expanded.get("content"),
    }


def _responses(document: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for status, response in operation.get("responses", {}).items():
        expanded = normalize(response, document)
        headers = expanded.get("headers") or {}
        resolved[str(status)] = {
            "content": expanded.get("content"),
            "headers": {name: value for name, value in sorted(headers.items())},
        }
    return resolved


def _security(document: dict[str, Any], operation: dict[str, Any]) -> Any:
    requirement = operation.get("security", document.get("security"))
    if requirement is None:
        return None
    return [
        {scheme: list(scopes) for scheme, scopes in sorted(entry.items())}
        for entry in requirement
    ]


def _referenced_schemes(document: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for operation in _operations(document).values():
        for entry in _security(document, operation) or []:
            names.update(entry)
    return names


def compare(runtime: dict[str, Any], canonical: dict[str, Any]) -> list[str]:
    """Return one message per semantic difference; empty means the two agree."""
    drift: list[str] = []

    runtime_operations = _operations(runtime)
    canonical_operations = _operations(canonical)
    only_runtime = sorted(set(runtime_operations) - set(canonical_operations))
    only_canonical = sorted(set(canonical_operations) - set(runtime_operations))
    for method, path in only_runtime:
        drift.append(f"{method.upper()} {path} exists in the runtime but not in the canonical contract")
    for method, path in only_canonical:
        drift.append(f"{method.upper()} {path} exists in the canonical contract but not in the runtime")

    for key in sorted(set(runtime_operations) & set(canonical_operations)):
        method, path = key
        label = f"{method.upper()} {path}"
        live, canon = runtime_operations[key], canonical_operations[key]

        if live.get("operationId") != canon.get("operationId"):
            drift.append(
                f"{label} operationId: runtime={live.get('operationId')!r} "
                f"canonical={canon.get('operationId')!r}"
            )

        live_body = _request_body(runtime, live)
        canon_body = _request_body(canonical, canon)
        if live_body != canon_body:
            drift.append(f"{label} request body differs between runtime and canonical")

        live_responses = _responses(runtime, live)
        canon_responses = _responses(canonical, canon)
        if set(live_responses) != set(canon_responses):
            drift.append(
                f"{label} response statuses: runtime={sorted(live_responses)} "
                f"canonical={sorted(canon_responses)}"
            )
        for status in sorted(set(live_responses) & set(canon_responses)):
            if live_responses[status]["content"] != canon_responses[status]["content"]:
                drift.append(f"{label} response {status} body schema differs")
            live_headers = live_responses[status]["headers"]
            canon_headers = canon_responses[status]["headers"]
            if set(live_headers) != set(canon_headers):
                drift.append(
                    f"{label} response {status} headers: runtime={sorted(live_headers)} "
                    f"canonical={sorted(canon_headers)}"
                )
            for name in sorted(set(live_headers) & set(canon_headers)):
                if live_headers[name] != canon_headers[name]:
                    drift.append(f"{label} response {status} header {name} differs")

        live_parameters = _parameters(runtime, live)
        canon_parameters = _parameters(canonical, canon)
        if set(live_parameters) != set(canon_parameters):
            drift.append(
                f"{label} parameters: runtime={sorted(live_parameters)} "
                f"canonical={sorted(canon_parameters)}"
            )
        for name in sorted(set(live_parameters) & set(canon_parameters)):
            if live_parameters[name] != canon_parameters[name]:
                drift.append(
                    f"{label} parameter {name[0]} in {name[1]} differs: "
                    f"runtime={live_parameters[name]} canonical={canon_parameters[name]}"
                )

        if _security(runtime, live) != _security(canonical, canon):
            drift.append(
                f"{label} security: runtime={_security(runtime, live)} "
                f"canonical={_security(canonical, canon)}"
            )

    runtime_schemes = runtime.get("components", {}).get("securitySchemes", {})
    canonical_schemes = canonical.get("components", {}).get("securitySchemes", {})
    for name in sorted(_referenced_schemes(runtime) | _referenced_schemes(canonical)):
        if name not in runtime_schemes:
            drift.append(f"security scheme {name} is used but not defined in the runtime")
        if name not in canonical_schemes:
            drift.append(f"security scheme {name} is used but not defined in the canonical contract")
        if name in runtime_schemes and name in canonical_schemes:
            if normalize(runtime_schemes[name], runtime) != normalize(
                canonical_schemes[name], canonical
            ):
                drift.append(f"security scheme {name} is defined differently on the two sides")

    return drift
