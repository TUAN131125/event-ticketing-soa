"""Transport-neutral parsing helpers for contract XML values."""

from __future__ import annotations

from datetime import UTC, datetime

from lxml import etree

from app.application.common import RequestContext
from app.domain.exceptions import InvalidRequest
from app.soap.namespaces import TNS, qname


def child_text(
    element: etree._Element,
    local_name: str,
    *,
    required: bool = True,
    default: str | None = None,
) -> str | None:
    child = element.find(qname(local_name))
    if child is None or child.text is None:
        if required:
            raise InvalidRequest(f"{local_name} is required")
        return default
    return child.text.strip()


def child_int(
    element: etree._Element,
    local_name: str,
    *,
    required: bool = True,
    default: int | None = None,
) -> int:
    raw = child_text(element, local_name, required=required)
    if raw is None:
        if default is None:
            raise InvalidRequest(f"{local_name} is required")
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise InvalidRequest(f"{local_name} must be an integer") from exc


def request_context(operation: etree._Element) -> RequestContext:
    node = operation.find(qname("context"))
    if node is None:
        raise InvalidRequest("context is required")
    return RequestContext(
        correlation_id=child_text(node, "correlationId") or "",
        idempotency_key=child_text(
            node, "idempotencyKey", required=False, default=None
        ),
        caller_service=child_text(node, "callerService") or "",
        actor_id=child_text(node, "actorId", required=False, default=None),
        schema_version=child_text(node, "schemaVersion") or "",
    )


def seat_ids(operation: etree._Element) -> tuple[str, ...]:
    parent = operation.find(qname("seatIds"))
    if parent is None:
        raise InvalidRequest("seatIds is required")
    return tuple(
        node.text.strip()
        for node in parent.findall(qname("seatId"))
        if node.text and node.text.strip()
    )


def operation_name(operation: etree._Element) -> str:
    namespace, local = (
        etree.QName(operation).namespace,
        etree.QName(operation).localname,
    )
    if namespace != TNS:
        raise InvalidRequest("SOAP operation namespace is invalid")
    if not local.endswith("Request"):
        raise InvalidRequest("SOAP request element is invalid")
    return local.removesuffix("Request")


def iso_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
