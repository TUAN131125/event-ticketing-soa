from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.exceptions import InvalidRequest
from app.security.xml_hardening import parse_soap

ROOT = Path(__file__).resolve().parents[2]


def valid_payload() -> bytes:
    return (ROOT / "contracts" / "examples" / "get-seat-map-request.xml").read_bytes()


@pytest.mark.security
def test_valid_contract_request_is_accepted() -> None:
    parse_soap(valid_payload(), 262_144)


@pytest.mark.security
def test_dtd_and_xxe_are_rejected_before_parsing() -> None:
    payload = b"""<?xml version="1.0"?>
<!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
<soap:Body><x>&xxe;</x></soap:Body></soap:Envelope>"""
    with pytest.raises(InvalidRequest, match="DTD"):
        parse_soap(payload, 262_144)


@pytest.mark.security
def test_wrong_namespace_or_schema_is_rejected() -> None:
    payload = valid_payload().replace(
        b"urn:event-ticketing:seat-inventory:v1", b"urn:wrong"
    )
    with pytest.raises(InvalidRequest, match="XSD"):
        parse_soap(payload, 262_144)


@pytest.mark.security
def test_payload_limit_is_enforced() -> None:
    with pytest.raises(InvalidRequest, match="payload limit"):
        parse_soap(valid_payload(), 100)
