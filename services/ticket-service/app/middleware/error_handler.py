"""Stable, non-leaking HTTP error envelopes."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.exceptions import InternalFailure, InvalidRequest, TicketError
from app.middleware.correlation_id import current_correlation_id

LOGGER = logging.getLogger("ticket.errors")


def _response(error: TicketError) -> JSONResponse:
    headers = {"Retry-After": "1"} if error.retryable else None
    return JSONResponse(
        status_code=error.http_status,
        headers=headers,
        content={
            "correlationId": current_correlation_id(),
            "error": {
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
                "details": error.details,
            },
        },
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(TicketError)
    async def ticket_error_handler(
        _request: Request, error: TicketError
    ) -> JSONResponse:
        LOGGER.warning(
            "Ticket request rejected",
            extra={"result": "REJECTED", "error_code": error.code},
        )
        return _response(error)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        return _response(InvalidRequest("Request body or parameters are invalid"))

    @app.exception_handler(Exception)
    async def unexpected_error_handler(
        _request: Request, _error: Exception
    ) -> JSONResponse:
        LOGGER.exception(
            "Unhandled Ticket Service error",
            extra={"result": "ERROR", "error_code": "INTERNAL_ERROR"},
        )
        return _response(InternalFailure())
