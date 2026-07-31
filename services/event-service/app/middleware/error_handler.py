"""Chuan hoa loi domain thanh HTTP response."""
from fastapi import Request
from fastapi.responses import JSONResponse

from app.domain.exceptions import EventNotFoundError, InvalidStateTransitionError


async def event_not_found_handler(request: Request, exc: EventNotFoundError):
    return JSONResponse(
        status_code=404,
        content={"error": "EVENT_NOT_FOUND", "detail": str(exc),
                 "correlationId": getattr(request.state, "correlation_id", None)},
    )


async def invalid_transition_handler(request: Request, exc: InvalidStateTransitionError):
    return JSONResponse(
        status_code=409,
        content={"error": "INVALID_STATE_TRANSITION", "detail": str(exc),
                 "correlationId": getattr(request.state, "correlation_id", None)},
    )
