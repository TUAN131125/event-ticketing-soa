#!/usr/bin/env python3
"""Conservative structural compatibility checker for canonical contracts."""

from __future__ import annotations

import argparse
import json
import posixpath
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from typing import Any

sys.dont_write_bytecode = True

from contract_utils import operations, read_json, read_yaml, yaml


class Loader:
    """Read a contracts tree from a directory or a Git ref without mutation."""

    def __init__(self, source: str) -> None:
        self.source = source
        candidate = Path(source)
        self.directory = candidate.resolve() if candidate.exists() else None
        if self.directory and (self.directory / "contracts").is_dir():
            self.directory = self.directory / "contracts"
        self._schema_ids: dict[str, tuple[str, dict[str, Any]]] | None = None

    def files(self) -> list[str]:
        if self.directory:
            return sorted(path.relative_to(self.directory).as_posix() for path in self.directory.rglob("*") if path.is_file())
        completed = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", self.source, "contracts"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            return []
        return sorted(
            line.removeprefix("contracts/")
            for line in completed.stdout.splitlines()
            if line.startswith("contracts/")
        )

    def text(self, relative: str) -> str | None:
        relative = PurePosixPath(relative).as_posix()
        if self.directory:
            path = self.directory / relative
            return path.read_text(encoding="utf-8") if path.is_file() else None
        completed = subprocess.run(
            ["git", "show", f"{self.source}:contracts/{relative}"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        return completed.stdout if completed.returncode == 0 else None

    def document(self, relative: str) -> Any | None:
        text = self.text(relative)
        if text is None:
            return None
        try:
            return json.loads(text) if relative.endswith(".json") else yaml.safe_load(text)
        except (json.JSONDecodeError, yaml.YAMLError):
            return None

    def schema_by_id(self, schema_id: str) -> tuple[str, dict[str, Any]] | None:
        if self._schema_ids is None:
            self._schema_ids = {}
            for relative in self.files():
                if not relative.endswith(".schema.json"):
                    continue
                document = self.document(relative)
                if isinstance(document, dict) and isinstance(document.get("$id"), str):
                    self._schema_ids[document["$id"]] = (relative, document)
        return self._schema_ids.get(schema_id)


def pointer(document: Any, fragment: str) -> Any:
    if fragment in {"", "#"}:
        return document
    value = document
    for token in fragment.removeprefix("#/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def merge_schema(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in overlay.items():
        if key == "required" and isinstance(value, list):
            result[key] = sorted(set(result.get(key, [])) | set(value or []))
        elif key == "properties" and isinstance(value, dict):
            result[key] = {**result.get(key, {}), **(value or {})}
        else:
            result[key] = value
    return result


def effective_schema(
    schema: Any,
    document: dict[str, Any],
    relative: str,
    loader: Loader,
    seen: set[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {}
    seen = set() if seen is None else seen
    result: dict[str, Any] = {}
    ref = schema.get("$ref")
    if isinstance(ref, str):
        path_part, _, fragment = ref.partition("#")
        id_match = loader.schema_by_id(path_part) if path_part.startswith("urn:") else None
        target_relative = (
            id_match[0]
            if id_match
            else relative if not path_part
            else posixpath.normpath(posixpath.join(posixpath.dirname(relative), path_part))
        )
        marker = (target_relative, fragment)
        if marker not in seen:
            target_document = id_match[1] if id_match else document if not path_part else loader.document(target_relative)
            if isinstance(target_document, dict):
                try:
                    target = pointer(target_document, f"#{fragment}" if fragment else "#")
                    result = effective_schema(target, target_document, target_relative, loader, seen | {marker})
                except (KeyError, IndexError, TypeError, ValueError):
                    pass
    for branch in schema.get("allOf", []):
        result = merge_schema(result, effective_schema(branch, document, relative, loader, seen))
    local = {key: value for key, value in schema.items() if key not in {"$ref", "allOf"}}
    return merge_schema(result, local)


def schema_type(schema: dict[str, Any]) -> tuple[Any, Any]:
    return schema.get("type"), schema.get("format")


def compare_schema(
    label: str,
    old_raw: Any,
    new_raw: Any,
    old_doc: dict[str, Any],
    new_doc: dict[str, Any],
    relative: str,
    old_loader: Loader,
    new_loader: Loader,
    breaking: list[str],
    warnings: list[str],
    *,
    response: bool = False,
    seen: set[str] | None = None,
) -> None:
    seen = set() if seen is None else seen
    if label in seen:
        return
    seen.add(label)
    old = effective_schema(old_raw, old_doc, relative, old_loader)
    new = effective_schema(new_raw, new_doc, relative, new_loader)
    if old.get("$id") != new.get("$id") and (old.get("$id") or new.get("$id")):
        breaking.append(f"{label}: $id changes {old.get('$id')!r} -> {new.get('$id')!r}")
    if schema_type(old) != schema_type(new) and any(schema_type(item) != (None, None) for item in (old, new)):
        breaking.append(f"{label}: type/format changes {schema_type(old)} -> {schema_type(new)}")
    old_required, new_required = set(old.get("required", [])), set(new.get("required", []))
    for field in sorted(new_required - old_required):
        breaking.append(f"{label}: adds required field {field}")
    old_properties, new_properties = old.get("properties", {}), new.get("properties", {})
    if response or old_properties or new_properties:
        for field in sorted(set(old_properties) - set(new_properties)):
            breaking.append(f"{label}: removes field {field}")
    old_enum, new_enum = old.get("enum"), new.get("enum")
    if isinstance(old_enum, list) and isinstance(new_enum, list):
        removed, added = set(old_enum) - set(new_enum), set(new_enum) - set(old_enum)
        if removed:
            breaking.append(f"{label}: narrows enum by removing {sorted(removed)}")
        if added:
            warnings.append(f"{label}: enum adds {sorted(added)}; closed consumers may require migration")
    for field in sorted(set(old_properties) & set(new_properties)):
        compare_schema(
            f"{label}.{field}", old_properties[field], new_properties[field], old_doc, new_doc,
            relative, old_loader, new_loader, breaking, warnings, response=response, seen=seen,
        )


def normalize_security(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {json.dumps(item, sort_keys=True) for item in value if isinstance(item, dict)}


def resolved_parameters(
    document: dict[str, Any], relative: str, loader: Loader, path_item: dict[str, Any], operation: dict[str, Any]
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in [*path_item.get("parameters", []), *operation.get("parameters", [])]:
        resolved = effective_schema(item, document, relative, loader)
        if resolved:
            output.append(resolved)
    return output


def response_schema(response: Any, document: dict[str, Any], relative: str, loader: Loader) -> dict[str, Any]:
    resolved = effective_schema(response, document, relative, loader)
    content = resolved.get("content", {})
    for media_type in ("application/json", "application/problem+json", "*/*"):
        schema = content.get(media_type, {}).get("schema")
        if isinstance(schema, dict):
            return schema
    return {}


def request_schema(operation: dict[str, Any], document: dict[str, Any], relative: str, loader: Loader) -> dict[str, Any]:
    body = effective_schema(operation.get("requestBody", {}), document, relative, loader)
    return body.get("content", {}).get("application/json", {}).get("schema", {})


def compare_openapi(
    relative: str,
    old: dict[str, Any],
    new: dict[str, Any],
    old_loader: Loader,
    new_loader: Loader,
    breaking: list[str],
    potential: list[str],
    warnings: list[str],
) -> None:
    old_ops = {(method, path): operation for method, path, operation in operations(old)}
    new_ops = {(method, path): operation for method, path, operation in operations(new)}
    for method, path in sorted(set(old_ops) - set(new_ops)):
        breaking.append(f"{relative}: removes operation {method} {path}")
    for key in sorted(set(old_ops) & set(new_ops)):
        method, path = key
        old_operation, new_operation = old_ops[key], new_ops[key]
        old_path_item, new_path_item = old["paths"][path], new["paths"][path]
        old_security = normalize_security(old_operation.get("security", old.get("security", [])))
        new_security = normalize_security(new_operation.get("security", new.get("security", [])))
        if old_security != new_security:
            potential.append(f"{relative}: {method} {path} security requirements change")
        old_headers = {
            item.get("name", "").lower()
            for item in resolved_parameters(old, relative, old_loader, old_path_item, old_operation)
            if item.get("in") == "header" and item.get("required") is True
        }
        new_headers = {
            item.get("name", "").lower()
            for item in resolved_parameters(new, relative, new_loader, new_path_item, new_operation)
            if item.get("in") == "header" and item.get("required") is True
        }
        for header in sorted(new_headers - old_headers):
            breaking.append(f"{relative}: {method} {path} adds required header {header}")
        old_responses, new_responses = old_operation.get("responses", {}), new_operation.get("responses", {})
        for status in sorted(set(old_responses) - set(new_responses)):
            breaking.append(f"{relative}: {method} {path} removes response status {status}")
        old_body = request_schema(old_operation, old, relative, old_loader)
        new_body = request_schema(new_operation, new, relative, new_loader)
        if old_body and new_body:
            compare_schema(
                f"{relative}:{method} {path}:request", old_body, new_body, old, new, relative,
                old_loader, new_loader, breaking, warnings,
            )
        for status in sorted(set(old_responses) & set(new_responses)):
            old_schema = response_schema(old_responses[status], old, relative, old_loader)
            new_schema = response_schema(new_responses[status], new, relative, new_loader)
            if old_schema and new_schema:
                compare_schema(
                    f"{relative}:{method} {path}:response[{status}]", old_schema, new_schema,
                    old, new, relative, old_loader, new_loader, breaking, warnings, response=True,
                )
    old_schemas = old.get("components", {}).get("schemas", {})
    new_schemas = new.get("components", {}).get("schemas", {})
    for name in sorted(set(old_schemas) & set(new_schemas)):
        compare_schema(
            f"{relative}:component[{name}]", old_schemas[name], new_schemas[name], old, new,
            relative, old_loader, new_loader, breaking, warnings,
        )


def schema_version(document: Any) -> Any:
    if isinstance(document, dict):
        property_schema = document.get("properties", {}).get("schemaVersion")
        if isinstance(property_schema, dict) and "const" in property_schema:
            return property_schema["const"]
        for value in document.values():
            found = schema_version(value)
            if found is not None:
                return found
    elif isinstance(document, list):
        for value in document:
            found = schema_version(value)
            if found is not None:
                return found
    return None


def soap_signature(text: str) -> tuple[str | None, dict[str, str], set[str], set[str]]:
    root = ET.fromstring(text)
    ns = {"wsdl": "http://schemas.xmlsoap.org/wsdl/", "soap": "http://schemas.xmlsoap.org/wsdl/soap/"}
    actions: dict[str, str] = {}
    faults: set[str] = set()
    operations_found: set[str] = set()
    for operation in root.findall("./wsdl:binding/wsdl:operation", ns):
        name = operation.get("name", "")
        operations_found.add(name)
        soap_operation = operation.find("soap:operation", ns)
        if soap_operation is not None:
            actions[name] = soap_operation.get("soapAction", "")
        faults |= {item.get("name", "") for item in operation.findall("wsdl:fault", ns)}
    return root.get("targetNamespace"), actions, faults, operations_found


def xsd_signature(text: str) -> tuple[str | None, set[str], set[str], dict[tuple[str, str], tuple[int, str | None]]]:
    root = ET.fromstring(text)
    ns = {"xsd": "http://www.w3.org/2001/XMLSchema"}
    elements = {item.get("name", "") for item in root.findall("./xsd:element", ns)}
    types = {item.get("name", "") for item in root.findall("./xsd:complexType", ns)}
    children: dict[tuple[str, str], tuple[int, str | None]] = {}
    for complex_type in root.findall("./xsd:complexType", ns):
        type_name = complex_type.get("name", "")
        for child in complex_type.findall(".//xsd:element", ns):
            name = child.get("name") or child.get("ref", "")
            children[(type_name, name)] = (int(child.get("minOccurs", "1")), child.get("type"))
    return root.get("targetNamespace"), elements, types, children


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="Directory containing contracts/ or a Git ref")
    parser.add_argument("--candidate", required=True, help="Candidate contracts directory")
    args = parser.parse_args()
    base, candidate = Loader(args.base), Loader(args.candidate)
    base_files = base.files()
    if not base_files:
        print(f"BASELINE_UNAVAILABLE source={args.base}")
        return 2

    breaking: list[str] = []
    potential: list[str] = []
    warnings: list[str] = []
    compared = 0

    for relative in [item for item in candidate.files() if item.startswith("openapi/") and item.endswith(".yaml")]:
        old, new = base.document(relative), candidate.document(relative)
        if not isinstance(old, dict):
            warnings.append(f"{relative}: no parseable base contract; new artifact")
            continue
        if isinstance(new, dict):
            compare_openapi(relative, old, new, base, candidate, breaking, potential, warnings)
            compared += 1

    base_schema_documents: list[tuple[str, dict[str, Any]]] = []
    for relative in [item for item in base_files if item.endswith(".schema.json")]:
        document = base.document(relative)
        if isinstance(document, dict):
            base_schema_documents.append((relative, document))
    by_id = {document.get("$id"): (relative, document) for relative, document in base_schema_documents if document.get("$id")}
    by_title = {document.get("title"): (relative, document) for relative, document in base_schema_documents if document.get("title")}
    for relative in [item for item in candidate.files() if item.endswith(".schema.json")]:
        new = candidate.document(relative)
        if not isinstance(new, dict):
            continue
        old_pair = next(((path, doc) for path, doc in base_schema_documents if path == relative), None)
        old_pair = old_pair or by_id.get(new.get("$id")) or by_title.get(new.get("title"))
        if not old_pair:
            warnings.append(f"{relative}: no matching base JSON Schema; new artifact")
            continue
        old_relative, old = old_pair
        compare_schema(
            f"{relative}", old, new, old, new, old_relative, base, candidate,
            breaking, warnings,
        )
        old_version, new_version = schema_version(old), schema_version(new)
        if old_version is not None and new_version is not None and old_version != new_version:
            breaking.append(f"{relative}: schemaVersion changes {old_version} -> {new_version}")
        compared += 1

    wsdl_relative = "soap/seat-inventory.wsdl"
    old_wsdl, new_wsdl = base.text(wsdl_relative), candidate.text(wsdl_relative)
    if old_wsdl and new_wsdl:
        try:
            old_ns, old_actions, old_faults, old_operations = soap_signature(old_wsdl)
            new_ns, new_actions, new_faults, new_operations = soap_signature(new_wsdl)
            if old_ns != new_ns:
                breaking.append(f"{wsdl_relative}: targetNamespace changes {old_ns!r} -> {new_ns!r}")
            for operation in sorted(old_operations - new_operations):
                breaking.append(f"{wsdl_relative}: removes SOAP operation {operation}")
            for name, action in old_actions.items():
                if new_actions.get(name) != action:
                    breaking.append(f"{wsdl_relative}: SOAP action {name} changes {action!r} -> {new_actions.get(name)!r}")
            if not old_faults <= new_faults:
                breaking.append(f"{wsdl_relative}: SOAP faults removed {sorted(old_faults - new_faults)}")
            compared += 1
        except ET.ParseError as exc:
            warnings.append(f"{wsdl_relative}: WSDL comparison failed: {exc}")

    xsd_relative = "soap/seat-inventory.xsd"
    old_xsd, new_xsd = base.text(xsd_relative), candidate.text(xsd_relative)
    if old_xsd and new_xsd:
        try:
            old_ns, old_elements, old_types, old_children = xsd_signature(old_xsd)
            new_ns, new_elements, new_types, new_children = xsd_signature(new_xsd)
            if old_ns != new_ns:
                breaking.append(f"{xsd_relative}: targetNamespace changes {old_ns!r} -> {new_ns!r}")
            for name in sorted(old_elements - new_elements):
                breaking.append(f"{xsd_relative}: removes top-level element {name}")
            for name in sorted(old_types - new_types):
                breaking.append(f"{xsd_relative}: removes complexType {name}")
            for key, (old_min, old_type) in old_children.items():
                if key not in new_children:
                    breaking.append(f"{xsd_relative}: removes element {key[0]}.{key[1]}")
                    continue
                new_min, new_type = new_children[key]
                if old_min == 0 and new_min > 0:
                    breaking.append(f"{xsd_relative}: makes element required {key[0]}.{key[1]}")
                if old_type != new_type:
                    potential.append(f"{xsd_relative}: element type changes {key[0]}.{key[1]} {old_type!r} -> {new_type!r}")
            compared += 1
        except ET.ParseError as exc:
            warnings.append(f"{xsd_relative}: XSD comparison failed: {exc}")

    for item in breaking:
        print(f"BREAKING {item}")
    for item in potential:
        print(f"POTENTIALLY_BREAKING {item}")
    for item in warnings:
        print(f"WARNING {item}")
    print(
        f"BREAKING_CHECK baseline={args.base} compared={compared} breaking={len(breaking)} "
        f"potentially_breaking={len(potential)} warnings={len(warnings)}"
    )
    print("LIMITATION behavioral/state compatibility and runtime conformance still require provider/consumer contract tests")
    return 1 if breaking or potential else 0


if __name__ == "__main__":
    raise SystemExit(main())
