"""Hardened SOAP parsing and local-only XSD validation."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import cast

from lxml import etree

from app.domain.exceptions import InvalidRequest

SOAP_ENV_NS = "http://schemas.xmlsoap.org/soap/envelope/"
CONTRACT_PATH = Path(__file__).resolve().parents[2] / "contracts" / "seat-inventory.xsd"


def reject_unsafe_declarations(payload: bytes) -> None:
    upper = payload.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise InvalidRequest("DTD and entity declarations are not allowed")


def parse_soap(payload: bytes, max_xml_bytes: int) -> etree._Element:
    if not payload:
        raise InvalidRequest("SOAP request body is empty")
    if len(payload) > max_xml_bytes:
        raise InvalidRequest("SOAP request exceeds the configured payload limit")
    reject_unsafe_declarations(payload)
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        recover=False,
        huge_tree=False,
        remove_comments=True,
        remove_pis=True,
    )
    try:
        root = etree.fromstring(payload, parser=parser)
    except (etree.XMLSyntaxError, ValueError) as exc:
        raise InvalidRequest("SOAP XML is not well formed") from exc
    if root.tag != f"{{{SOAP_ENV_NS}}}Envelope":
        raise InvalidRequest("SOAP 1.1 Envelope is required")
    body = root.find(f"{{{SOAP_ENV_NS}}}Body")
    if body is None:
        raise InvalidRequest("SOAP Body is required")
    operations = [
        cast(etree._Element, node) for node in body if isinstance(node.tag, str)
    ]
    if len(operations) != 1:
        raise InvalidRequest("SOAP Body must contain exactly one operation")
    operation = operations[0]
    try:
        get_schema().assertValid(operation)
    except etree.DocumentInvalid as exc:
        raise InvalidRequest("SOAP operation does not match the XSD contract") from exc
    return operation


@lru_cache(maxsize=1)
def get_schema() -> etree.XMLSchema:
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
    )
    document = etree.parse(str(CONTRACT_PATH), parser)
    return etree.XMLSchema(document)
