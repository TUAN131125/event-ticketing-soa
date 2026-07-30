"""FastAPI SOAP transport with contract validation and safe faults."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import APIRouter, Header, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from app.config import Settings
from app.domain.exceptions import InternalFailure, InvalidRequest, SeatInventoryError
from app.observability.metrics import (
    OPERATION_DURATION,
    OPERATION_TOTAL,
    SOAP_FAULT_TOTAL,
)
from app.observability.tracing import (
    get_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)
from app.security.service_authentication import authenticate_service
from app.security.xml_hardening import parse_soap
from app.soap.envelope import soap_envelope
from app.soap.faults import soap_fault
from app.soap.operations import dispatch
from app.soap.types import operation_name, request_context

LOGGER = logging.getLogger(__name__)
CONTRACT_DIR = Path(__file__).resolve().parents[2] / "contracts"


def create_soap_router(settings: Settings) -> APIRouter:
    router = APIRouter()

    @router.get("/seat-inventory.xsd", include_in_schema=False)
    async def xsd() -> Response:
        content = (CONTRACT_DIR / "seat-inventory.xsd").read_text(encoding="utf-8")
        return Response(content=content, media_type="application/xml")

    @router.get("/soap", include_in_schema=False)
    async def wsdl(request: Request) -> Response:
        if "wsdl" not in request.query_params:
            return Response(status_code=405)
        content = (CONTRACT_DIR / "seat-inventory.wsdl").read_text(encoding="utf-8")
        content = content.replace(
            "http://localhost:8003/soap", settings.soap_public_url
        )
        return Response(content=content, media_type="text/xml")

    @router.post("/soap", include_in_schema=False)
    async def soap_endpoint(
        request: Request,
        x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
        soap_action: str | None = Header(default=None, alias="SOAPAction"),
    ) -> Response:
        started = time.perf_counter()
        name = "Unknown"
        token = None
        try:
            authenticate_service(x_service_token, settings.service_token)
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    declared_size = int(content_length)
                except ValueError as exc:
                    raise InvalidRequest("Content-Length is invalid") from exc
                if declared_size > settings.max_xml_bytes:
                    raise InvalidRequest(
                        "SOAP request exceeds the configured payload limit"
                    )
            payload = await request.body()
            operation = parse_soap(payload, settings.max_xml_bytes)
            name = operation_name(operation)
            context = request_context(operation)
            token = set_correlation_id(context.correlation_id)
            if soap_action:
                normalized_action = soap_action.strip().strip('"').rsplit("/", 1)[-1]
                if normalized_action != name:
                    raise InvalidRequest("SOAPAction does not match the body operation")
            result = await run_in_threadpool(dispatch, operation, settings)
            OPERATION_TOTAL.labels(name, "success").inc()
            LOGGER.info(
                "SOAP operation completed",
                extra={
                    "operation": name,
                    "result": "SUCCESS",
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            return Response(content=soap_envelope(result), media_type="text/xml")
        except SeatInventoryError as exc:
            OPERATION_TOTAL.labels(name, "fault").inc()
            SOAP_FAULT_TOTAL.labels(exc.code, str(exc.retryable).lower()).inc()
            LOGGER.warning(
                "SOAP operation rejected",
                extra={"operation": name, "result": "FAULT", "error_code": exc.code},
            )
            return Response(
                content=soap_fault(exc, get_correlation_id()),
                status_code=500,
                media_type="text/xml",
            )
        except Exception:
            error = InternalFailure()
            OPERATION_TOTAL.labels(name, "error").inc()
            SOAP_FAULT_TOTAL.labels(error.code, "false").inc()
            LOGGER.exception(
                "SOAP operation failed",
                extra={"operation": name, "result": "ERROR", "error_code": error.code},
            )
            return Response(
                content=soap_fault(error, get_correlation_id()),
                status_code=500,
                media_type="text/xml",
            )
        finally:
            OPERATION_DURATION.labels(name).observe(time.perf_counter() - started)
            if token is not None:
                reset_correlation_id(token)

    return router
