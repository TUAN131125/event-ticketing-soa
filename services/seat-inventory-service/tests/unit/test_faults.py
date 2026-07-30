from __future__ import annotations

from lxml import etree

from app.domain.exceptions import DependencyUnavailable, SeatUnavailable
from app.soap.faults import soap_fault


def test_business_fault_is_non_retryable_and_contains_correlation() -> None:
    payload = soap_fault(SeatUnavailable(["A-01"]), "COR-1")
    root = etree.fromstring(payload)
    text = etree.tostring(root, encoding="unicode")
    assert "SEAT_UNAVAILABLE" in text
    assert "<seat:retryable>false</seat:retryable>" in text
    assert "COR-1" in text


def test_dependency_fault_is_retryable_without_internal_details() -> None:
    payload = soap_fault(DependencyUnavailable(), "COR-2").decode()
    assert "DEPENDENCY_UNAVAILABLE" in payload
    assert "<seat:retryable>true</seat:retryable>" in payload
    assert "postgres" not in payload.lower()
    assert "traceback" not in payload.lower()
