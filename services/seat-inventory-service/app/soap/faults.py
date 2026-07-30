"""Stable SOAP Fault serialization."""

from __future__ import annotations

from lxml import etree

from app.domain.exceptions import SeatInventoryError
from app.soap.namespaces import NSMAP, SOAP_ENV, qname


def soap_fault(error: SeatInventoryError, correlation_id: str) -> bytes:
    envelope = etree.Element(f"{{{SOAP_ENV}}}Envelope", nsmap=NSMAP)
    body = etree.SubElement(envelope, f"{{{SOAP_ENV}}}Body")
    fault = etree.SubElement(body, f"{{{SOAP_ENV}}}Fault")
    fault_code = etree.SubElement(fault, "faultcode")
    fault_code.text = (
        "soap:Server" if error.retryable or error.http_status >= 500 else "soap:Client"
    )
    fault_string = etree.SubElement(fault, "faultstring")
    fault_string.text = error.message
    detail = etree.SubElement(fault, "detail")
    contract_fault = etree.SubElement(detail, qname("SeatInventoryFault"))
    code = etree.SubElement(contract_fault, qname("code"))
    code.text = error.code
    message = etree.SubElement(contract_fault, qname("message"))
    message.text = error.message
    correlation = etree.SubElement(contract_fault, qname("correlationId"))
    correlation.text = correlation_id
    retryable = etree.SubElement(contract_fault, qname("retryable"))
    retryable.text = "true" if error.retryable else "false"
    return etree.tostring(
        envelope,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=False,
    )
