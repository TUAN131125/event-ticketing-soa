from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from lxml import etree

from app.domain.errors import EsbError
from app.domain.models import RequestContext
from app.resilience.policies import ResiliencePolicy

SEAT_NAMESPACE = "urn:event-ticketing:seat:v1"
SOAP_NAMESPACE = "http://schemas.xmlsoap.org/soap/envelope/"
NSMAP = {"soap": SOAP_NAMESPACE, "seat": SEAT_NAMESPACE}


def _qualified(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


class SeatSoapAdapter:
    """REST-facing SOAP mediator that emits the canonical Seat Inventory v1 XML."""

    def __init__(
        self,
        endpoint_url: str,
        policy: ResiliencePolicy,
        *,
        credentials=None,
        audience: str = "seat-inventory-service",
        dependency_timeout_seconds: float = 4.0,
        xsd_path: Path | None = None,
    ) -> None:
        self.endpoint_url = endpoint_url.rstrip("/")
        self.policy = policy
        self.credentials = credentials
        self.audience = audience
        self.dependency_timeout_seconds = dependency_timeout_seconds
        self.schema = self._load_schema(xsd_path)


    def _service_token(self) -> str:
        if self.credentials is None:
            return ""
        if isinstance(self.credentials, str):
            return self.credentials
        token = getattr(self.credentials, "token", None)
        return str(token(self.audience)) if token is not None else ""

    @staticmethod
    def _load_schema(xsd_path: Path | None) -> etree.XMLSchema | None:
        # A configured path that is not there is a deployment fault, not a reason to run
        # unvalidated: silently dropping validation is how a schema mismatch reaches
        # production. Only an explicitly unset path disables it, which is what the unit
        # tests that exercise transport behaviour alone rely on.
        if xsd_path is None:
            return None
        if not xsd_path.is_file():
            raise RuntimeError(
                f"Seat Inventory XSD not found at {xsd_path}; "
                "set ESB_SEAT_PROVIDER_XSD_PATH to the canonical seat-inventory.xsd"
            )
        return etree.XMLSchema(etree.parse(str(xsd_path)))

    def _request_context(
        self,
        parent: etree._Element,
        ctx: RequestContext,
        idempotency_key: str | None,
    ) -> None:
        context = etree.SubElement(parent, _qualified(SEAT_NAMESPACE, "context"))
        self._text(context, "correlationId", ctx.correlation_id)
        self._text(context, "traceparent", ctx.traceparent)
        if idempotency_key:
            self._text(context, "idempotencyKey", idempotency_key)
        self._text(context, "callerService", "booking-orchestrator")
        self._text(context, "schemaVersion", 1)

    @staticmethod
    def _text(parent: etree._Element, name: str, value: object) -> None:
        element = etree.SubElement(parent, _qualified(SEAT_NAMESPACE, name))
        element.text = str(value)

    def _seat_references(
        self,
        parent: etree._Element,
        references: list[dict[str, str]],
    ) -> None:
        box = etree.SubElement(parent, _qualified(SEAT_NAMESPACE, "seatIds"))
        for reference in references:
            seat = etree.SubElement(box, _qualified(SEAT_NAMESPACE, "seat"))
            self._text(seat, "seatId", reference["seatId"])
            self._text(seat, "ticketTypeCode", reference["ticketTypeCode"])

    def _seat_definitions(
        self,
        parent: etree._Element,
        definitions: list[dict[str, str]],
    ) -> None:
        box = etree.SubElement(parent, _qualified(SEAT_NAMESPACE, "seats"))
        for definition in definitions:
            seat = etree.SubElement(box, _qualified(SEAT_NAMESPACE, "seat"))
            for name in (
                "seatId",
                "section",
                "rowLabel",
                "seatNumber",
                "ticketTypeCode",
                "status",
            ):
                value = definition.get(name)
                if value is not None:
                    self._text(seat, name, value)

    def _envelope(
        self,
        operation: str,
        ctx: RequestContext,
        *,
        idempotency_key: str | None = None,
        values: dict[str, object] | None = None,
        seat_references: list[dict[str, str]] | None = None,
        seat_definitions: list[dict[str, str]] | None = None,
        trailing_values: dict[str, object] | None = None,
    ) -> bytes:
        envelope = etree.Element(
            _qualified(SOAP_NAMESPACE, "Envelope"),
            nsmap=NSMAP,
        )
        body = etree.SubElement(envelope, _qualified(SOAP_NAMESPACE, "Body"))
        request = etree.SubElement(
            body,
            _qualified(SEAT_NAMESPACE, f"{operation}Request"),
        )
        self._request_context(request, ctx, idempotency_key)
        for name, value in (values or {}).items():
            if value is not None:
                self._text(request, name, value)
        if seat_references is not None:
            self._seat_references(request, seat_references)
        if seat_definitions is not None:
            self._seat_definitions(request, seat_definitions)
        for name, value in (trailing_values or {}).items():
            if value is not None:
                self._text(request, name, value)

        if self.schema is not None:
            self.schema.assertValid(request)
        return etree.tostring(
            envelope,
            xml_declaration=True,
            encoding="utf-8",
        )

    @staticmethod
    def _coerce(name: str, value: str | None) -> object:
        if value is None:
            return None
        if name in {
            "available",
            "retryable",
        }:
            return value.lower() == "true"
        if name in {
            "resourceVersion",
            "inventoryVersion",
            "configuredSeatCount",
            "expiredCount",
            "schemaVersion",
        }:
            try:
                return int(value)
            except ValueError:
                return value
        return value

    @classmethod
    def _element_value(cls, element: etree._Element) -> object:
        children = list(element)
        if not children:
            return cls._coerce(etree.QName(element).localname, element.text)

        result: dict[str, object] = {}
        for child in children:
            key = etree.QName(child).localname
            value = cls._element_value(child)
            previous = result.get(key)
            if previous is None:
                result[key] = value
            elif isinstance(previous, list):
                previous.append(value)
            else:
                result[key] = [previous, value]
        return result

    def _parse(self, payload: bytes) -> dict[str, Any]:
        try:
            root = etree.fromstring(payload)
        except etree.XMLSyntaxError as exc:
            raise EsbError(
                "SEAT_PROTOCOL_ERROR",
                "Seat Inventory returned invalid SOAP XML",
                502,
                True,
            ) from exc

        fault = root.find(f".//{_qualified(SOAP_NAMESPACE, 'Fault')}")
        if fault is not None:
            detail = fault.find("detail")
            provider_fault = (
                detail.find(f".//{_qualified(SEAT_NAMESPACE, 'SeatServiceFault')}")
                if detail is not None
                else None
            )
            parsed = (
                self._element_value(provider_fault)
                if provider_fault is not None
                else {"message": "".join(fault.itertext()).strip()}
            )
            if not isinstance(parsed, dict):
                parsed = {"message": str(parsed)}
            raise EsbError(
                str(parsed.get("code") or "SEAT_SOAP_FAULT"),
                str(parsed.get("message") or "Seat Inventory returned a SOAP Fault"),
                409,
                bool(parsed.get("retryable", False)),
                parsed,
            )

        body = root.find(f".//{_qualified(SOAP_NAMESPACE, 'Body')}")
        if body is None or len(body) != 1:
            raise EsbError(
                "SEAT_PROTOCOL_ERROR",
                "Seat Inventory SOAP response has no operation body",
                502,
                True,
            )
        operation_response = body[0]
        if self.schema is not None:
            self.schema.assertValid(operation_response)
        parsed = self._element_value(operation_response)
        return parsed if isinstance(parsed, dict) else {"value": parsed}

    async def _call(
        self,
        operation: str,
        request_xml: bytes,
        ctx: RequestContext,
        *,
        mode: str,
    ) -> dict[str, Any]:
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f"{SEAT_NAMESPACE}/{operation}",
            "X-Correlation-ID": ctx.correlation_id,
            "traceparent": ctx.traceparent,
        }
        service_token = self._service_token()
        if service_token:
            headers["Authorization"] = f"Bearer {service_token}"

        async def dispatch() -> dict[str, Any]:
            async with httpx.AsyncClient(timeout=None) as client:
                response = await client.post(
                    self.endpoint_url,
                    content=request_xml,
                    headers=headers,
                )
                if response.content:
                    try:
                        parsed = self._parse(response.content)
                    except EsbError:
                        raise
                    except etree.DocumentInvalid as exc:
                        raise EsbError(
                            "SEAT_SCHEMA_VIOLATION",
                            "Seat Inventory response violates the canonical XSD",
                            502,
                            False,
                        ) from exc
                else:
                    parsed = {}
                if response.status_code >= 400:
                    raise EsbError(
                        "SEAT_DEPENDENCY_ERROR",
                        f"Seat Inventory returned HTTP {response.status_code}",
                        502 if response.status_code >= 500 else response.status_code,
                        response.status_code >= 500,
                        parsed,
                    )
                return parsed

        import time

        deadline = min(
            ctx.deadline_monotonic,
            time.monotonic() + self.dependency_timeout_seconds,
        )
        return await self.policy.execute(
            "seat",
            dispatch,
            mode=mode,
            deadline=deadline,
        )

    async def get_seat_map(
        self, event_id: str, ctx: RequestContext
    ) -> dict[str, Any]:
        request = self._envelope(
            "GetSeatMap",
            ctx,
            values={"eventId": event_id},
        )
        return await self._call("GetSeatMap", request, ctx, mode="safe_read")

    async def check_availability(
        self,
        event_id: str,
        seat_references: list[dict[str, str]],
        ctx: RequestContext,
    ) -> dict[str, Any]:
        request = self._envelope(
            "CheckAvailability",
            ctx,
            values={"eventId": event_id},
            seat_references=seat_references,
        )
        return await self._call(
            "CheckAvailability",
            request,
            ctx,
            mode="safe_read",
        )

    async def reserve(
        self,
        booking_id: str,
        event_id: str,
        seat_references: list[dict[str, str]],
        ttl_seconds: int,
        idempotency_key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]:
        request = self._envelope(
            "ReserveSeats",
            ctx,
            idempotency_key=idempotency_key,
            values={
                "bookingId": booking_id,
                "eventId": event_id,
            },
            seat_references=seat_references,
            trailing_values={"ttlSeconds": ttl_seconds},
        )
        return await self._call(
            "ReserveSeats",
            request,
            ctx,
            mode="idempotent_command",
        )

    async def confirm(
        self,
        reservation_id: str,
        expected_version: int,
        idempotency_key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]:
        request = self._envelope(
            "ConfirmSeats",
            ctx,
            idempotency_key=idempotency_key,
            values={
                "reservationId": reservation_id,
                "expectedVersion": expected_version,
            },
        )
        return await self._call(
            "ConfirmSeats",
            request,
            ctx,
            mode="idempotent_command",
        )

    async def release(
        self,
        reservation_id: str,
        reason_code: str,
        idempotency_key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]:
        request = self._envelope(
            "ReleaseSeats",
            ctx,
            idempotency_key=idempotency_key,
            values={
                "reservationId": reservation_id,
                "reasonCode": reason_code,
            },
        )
        return await self._call(
            "ReleaseSeats",
            request,
            ctx,
            mode="idempotent_command",
        )
    async def configure_inventory(
        self,
        event_id: str,
        inventory_version: int,
        seats: list[dict[str, str]],
        idempotency_key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]:
        request = self._envelope(
            "ConfigureInventory",
            ctx,
            idempotency_key=idempotency_key,
            values={
                "eventId": event_id,
                "inventoryVersion": inventory_version,
            },
            seat_definitions=seats,
        )
        return await self._call(
            "ConfigureInventory",
            request,
            ctx,
            mode="idempotent_command",
        )

