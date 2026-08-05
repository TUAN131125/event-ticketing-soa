from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from typing import Any

import httpx
from lxml import etree

from app.contract_freeze import EXPECTED_CATALOG_SHA, EXPECTED_FREEZE_ID
from app.domain.errors import (
    AmbiguousOutcome,
    BusinessFault,
    DependencyFailure,
    EsbError,
)
from app.domain.models import RequestContext
from app.ports.repositories import TraceRepository
from app.resilience.policies import ResilienceExecutor, RetryClass

SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
NS = "urn:event-ticketing:seat-inventory:v1"
logger = logging.getLogger(__name__)


class SeatSoapAdapter:
    normalized_contract = (
        "seat-inventory",
        "seat-inventory.wsdl",
        EXPECTED_FREEZE_ID,
        EXPECTED_CATALOG_SHA,
    )
    provider_contract = "contracts/seat-inventory.wsdl"

    def __init__(
        self,
        endpoint: str,
        http: httpx.AsyncClient,
        resilience: ResilienceExecutor,
        xsd_path: str,
        service_token: str | None = None,
        traces: TraceRepository | None = None,
    ) -> None:
        self.endpoint, self.http, self.resilience = endpoint, http, resilience
        self.schema = etree.XMLSchema(etree.parse(xsd_path))
        self.service_token = service_token
        self.traces = traces

    async def check_availability(self, event_id: str, seat_ids: Sequence[str], context: RequestContext) -> Mapping[str, Any]:
        body = {
            "eventId": event_id,
            "seatIds": list(seat_ids),
        }
        return await self._call("CheckAvailability", body, None, context, RetryClass.SAFE_READ)

    async def reserve_seats(self, payload: Mapping[str, Any], idempotency_key: str, context: RequestContext) -> Mapping[str, Any]:
        return await self._call(
            "ReserveSeats",
            payload,
            idempotency_key,
            context,
            RetryClass.IDEMPOTENT_COMMAND,
            ambiguous=True,
        )

    async def get_reservation(self, reservation_id: str, context: RequestContext) -> Mapping[str, Any]:
        if not reservation_id:
            raise ValueError("GetReservation requires reservationId")
        return await self._call(
            "GetReservation",
            {"reservationId": reservation_id},
            None,
            context,
            RetryClass.SAFE_READ,
        )

    async def confirm_seats(
        self,
        reservation_id: str,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> Mapping[str, Any]:
        return await self._call(
            "ConfirmSeats",
            {"reservationId": reservation_id, "expectedVersion": expected_version},
            idempotency_key,
            context,
            RetryClass.IDEMPOTENT_COMMAND,
        )

    async def release_seats(
        self,
        reservation_id: str,
        reason: str,
        idempotency_key: str,
        context: RequestContext,
    ) -> Mapping[str, Any]:
        return await self._call(
            "ReleaseSeats",
            {"reservationId": reservation_id, "reasonCode": reason},
            idempotency_key,
            context,
            RetryClass.IDEMPOTENT_COMMAND,
        )

    async def _call(
        self,
        operation: str,
        payload: Mapping[str, Any],
        idempotency_key: str | None,
        context: RequestContext,
        retry: RetryClass,
        ambiguous: bool = False,
    ) -> Mapping[str, Any]:
        service_token = self.service_token
        if not service_token:
            raise DependencyFailure(
                "SEAT_AUTH_CONFIGURATION_INVALID",
                "Seat provider credential is not configured.",
                503,
                False,
            )
        request = self._request_element(operation, payload, idempotency_key, context)
        try:
            self.schema.assertValid(request)
        except etree.DocumentInvalid as exc:
            raise DependencyFailure(
                "INVALID_SOAP_REQUEST",
                "Seat provider request does not match its published contract.",
                503,
                False,
            ) from exc
        envelope = etree.Element(etree.QName(SOAP, "Envelope"), nsmap={"soap": SOAP, "tns": NS})
        body = etree.SubElement(envelope, etree.QName(SOAP, "Body"))
        body.append(request)
        raw = etree.tostring(envelope, xml_declaration=True, encoding="UTF-8")

        async def invoke() -> Mapping[str, Any]:
            try:
                response = await self.http.post(
                    self.endpoint,
                    content=raw,
                    headers={
                        "Content-Type": "text/xml; charset=utf-8",
                        "SOAPAction": f"{NS}/{operation}",
                        "X-Service-Token": service_token,
                    },
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if ambiguous:
                    raise AmbiguousOutcome(operation) from exc
                raise DependencyFailure("SEAT_UNAVAILABLE", "Seat service unavailable.", 503, True) from exc
            return self._parse(operation, response.content, response.status_code)

        started = time.perf_counter()
        try:
            result = await self.resilience.execute(invoke, retry, context)
        except EsbError as exc:
            await self._observe(operation, context, "FAILURE", started, exc.code)
            raise
        except Exception:
            await self._observe(operation, context, "FAILURE", started, "SEAT_DEPENDENCY_FAILURE")
            raise
        await self._observe(operation, context, "SUCCESS", started)
        return result

    async def _observe(
        self,
        operation: str,
        context: RequestContext,
        outcome: str,
        started: float,
        error_code: str | None = None,
    ) -> None:
        duration_ms = max(0, int((time.perf_counter() - started) * 1000))
        fields = {
            "correlationId": context.correlation_id,
            "traceId": context.trace_id,
            "workflowId": context.workflow_id,
            "operation": operation,
            "provider": "seat-inventory-service",
            "step": operation,
            "outcome": outcome,
            "duration": duration_ms,
        }
        logger.info("provider_call", extra=fields)
        if self.traces is not None:
            try:
                await self.traces.append(
                    context.correlation_id,
                    "seat-inventory-service",
                    operation,
                    outcome,
                    duration_ms,
                    error_code,
                )
            except Exception as exc:  # noqa: BLE001 -- telemetry failure must not fail a provider call
                logger.warning(
                    "trace_persistence_failed",
                    extra={
                        **fields,
                        "outcome": "TRACE_WRITE_FAILED",
                        "errorType": type(exc).__name__,
                    },
                )

    def _request_element(
        self,
        operation: str,
        payload: Mapping[str, Any],
        idempotency_key: str | None,
        context: RequestContext,
    ) -> etree._Element:
        root = etree.Element(etree.QName(NS, f"{operation}Request"), nsmap={"tns": NS})
        ctx = etree.SubElement(root, etree.QName(NS, "context"))
        self._text(ctx, "correlationId", context.correlation_id)
        if idempotency_key:
            self._text(ctx, "idempotencyKey", idempotency_key)
        self._text(ctx, "callerService", "booking-orchestrator")
        self._text(ctx, "schemaVersion", "1.0")
        source = {k: v for k, v in payload.items() if k != "requestContext"}
        for key, value in source.items():
            if key == "seatIds":
                wrapper = etree.SubElement(root, etree.QName(NS, "seatIds"))
                for seat in value:
                    seat_id = seat.get("seatId") if isinstance(seat, Mapping) else seat
                    self._text(wrapper, "seatId", str(seat_id))
            elif key == "ttlSeconds":
                self._text(root, "holdSeconds", str(value))
            else:
                self._text(root, key, str(value))
        return root

    @staticmethod
    def _text(parent: etree._Element, name: str, value: str) -> None:
        node = etree.SubElement(parent, etree.QName(NS, name))
        node.text = value

    def _parse(self, operation: str, raw: bytes, status: int) -> Mapping[str, Any]:
        try:
            parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
            root = etree.fromstring(raw, parser=parser)
        except etree.XMLSyntaxError as exc:
            raise DependencyFailure(
                "INVALID_SOAP_RESPONSE",
                "Seat service returned malformed XML.",
                503,
                True,
            ) from exc
        fault = root.find(f".//{{{SOAP}}}Fault")
        if fault is not None:
            detail = fault.find(f".//{{{NS}}}SeatInventoryFault")
            code = detail.findtext(f"{{{NS}}}code") if detail is not None else "SEAT_INVENTORY_FAULT"
            message = detail.findtext(f"{{{NS}}}message") if detail is not None else "Seat operation failed."
            retryable = detail.findtext(f"{{{NS}}}retryable") == "true" if detail is not None else False
            raise BusinessFault(str(code), str(message), 409, retryable, {"soapFaultCode": code})
        response = next((node for node in root.findall(f".//{{{SOAP}}}Body/*")), None)
        if response is None or status >= 400 or etree.QName(response).localname != f"{operation}Response":
            raise DependencyFailure(
                "INVALID_SOAP_RESPONSE",
                "Seat service returned an invalid response.",
                503,
                True,
            )
        try:
            self.schema.assertValid(response)
            if operation == "CheckAvailability":
                return {
                    "correlationId": self._required(response, "correlationId"),
                    "eventId": self._required(response, "eventId"),
                    "available": self._required(response, "available") == "true",
                    "availableSeatIds": self._seat_id_list(response, "availableSeatIds"),
                    "unavailableSeatIds": self._seat_id_list(response, "unavailableSeatIds"),
                    "checkedAt": self._required(response, "checkedAt"),
                }
            reservation = response.find(f"{{{NS}}}reservation")
            if reservation is None:
                raise ValueError("reservation is missing")
            return {
                "reservationId": self._required(reservation, "reservationId"),
                "bookingId": self._required(reservation, "bookingId"),
                "eventId": self._required(reservation, "eventId"),
                "seatIds": self._seat_id_list(reservation, "seatIds"),
                "status": self._required(reservation, "status"),
                "expiresAt": self._required(reservation, "expiresAt"),
                "extendCount": int(self._required(reservation, "extendCount")),
                "resourceVersion": int(self._required(reservation, "resourceVersion")),
                "createdAt": self._required(reservation, "createdAt"),
                "updatedAt": self._required(reservation, "updatedAt"),
            }
        except (etree.DocumentInvalid, TypeError, ValueError) as exc:
            raise DependencyFailure(
                "INVALID_SOAP_RESPONSE",
                "Seat service returned a response that violates its published contract.",
                503,
                True,
            ) from exc

    @staticmethod
    def _required(parent: etree._Element, name: str) -> str:
        value = parent.findtext(f"{{{NS}}}{name}")
        if value is None or value == "":
            raise ValueError(f"{name} is missing")
        return value

    @staticmethod
    def _seat_id_list(parent: etree._Element, name: str) -> list[str]:
        wrapper = parent.find(f"{{{NS}}}{name}")
        if wrapper is None:
            raise ValueError(f"{name} is missing")
        return [value for node in wrapper.findall(f"{{{NS}}}seatId") if (value := node.text)]
