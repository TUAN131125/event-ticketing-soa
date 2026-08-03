"""State-changing endpoints called by the booking orchestrator."""

from fastapi import APIRouter, Depends, Header

from app.application.service import BookingService
from app.dependencies import get_service
from app.domain.value_objects import RequestContext
from app.middleware.authentication import require_internal_caller
from app.observability.metrics import COMMAND_TOTAL
from app.schemas.requests import (
    CancelBookingRequest,
    ConfirmBookingRequest,
    FailBookingRequest,
)
from app.schemas.responses import BookingResponse

router = APIRouter(prefix="/bookings", tags=["booking-commands"])


@router.post(
    "/{booking_id}/confirm",
    response_model=BookingResponse,
    operation_id="confirmBooking",
)
def confirm(
    booking_id: str,
    body: ConfirmBookingRequest,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=128
    ),
    context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> BookingResponse:
    try:
        result = service.confirm(
            context,
            idempotency_key=idempotency_key,
            booking_id=booking_id,
            payment_id=body.payment_id,
            expected_version=body.expected_version,
        )
        COMMAND_TOTAL.labels("confirm", "success").inc()
        return BookingResponse.from_entity(result)
    except Exception:
        COMMAND_TOTAL.labels("confirm", "failure").inc()
        raise


@router.post(
    "/{booking_id}/fail",
    response_model=BookingResponse,
    operation_id="failBooking",
)
def fail(
    booking_id: str,
    body: FailBookingRequest,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=128
    ),
    context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> BookingResponse:
    try:
        result = service.fail(
            context,
            idempotency_key=idempotency_key,
            booking_id=booking_id,
            failure_code=body.failure_code,
            reason=body.reason,
            expected_version=body.expected_version,
        )
        COMMAND_TOTAL.labels("fail", "success").inc()
        return BookingResponse.from_entity(result)
    except Exception:
        COMMAND_TOTAL.labels("fail", "failure").inc()
        raise


@router.post(
    "/{booking_id}/cancel",
    response_model=BookingResponse,
    operation_id="cancelBooking",
)
def cancel(
    booking_id: str,
    body: CancelBookingRequest,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=128
    ),
    context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> BookingResponse:
    try:
        result = service.cancel(
            context,
            idempotency_key=idempotency_key,
            booking_id=booking_id,
            reason=body.reason,
            expected_version=body.expected_version,
            payment_status=body.payment_status,
        )
        COMMAND_TOTAL.labels("cancel", "success").inc()
        return BookingResponse.from_entity(result)
    except Exception:
        COMMAND_TOTAL.labels("cancel", "failure").inc()
        raise
