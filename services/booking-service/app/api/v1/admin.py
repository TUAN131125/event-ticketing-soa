"""State-changing Booking endpoints used by the ESB orchestrator.

The transport layer accepts both concurrency contracts used by existing
clients:

* legacy ``expectedVersion`` in the JSON body;
* canonical ``If-Match`` entity tag.

Both forms resolve to one application command.  Every successful mutation
returns the current aggregate version in ``ETag``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Response

from app.api.v1.http_contract import (
    OK_WITH_ETAG,
    booking_response,
    resolve_expected_version,
)
from app.application.service import BookingService
from app.dependencies import get_service
from app.domain.value_objects import CompensationEvidence, RequestContext
from app.middleware.authentication import require_internal_caller
from app.schemas.requests import (
    AttachReservationRequest,
    AttachTicketsRequest,
    CancelBookingRequest,
    CompensationResultRequest,
    ConfirmBookingRequest,
    ConfirmReservationRequest,
    EvidenceRequest,
    FailBookingRequest,
    RecordPaymentRequest,
    StartPaymentRequest,
)
from app.schemas.responses import BookingResponse

router = APIRouter(prefix="/bookings", tags=["booking-commands"])
IdempotencyKey = Header(alias="Idempotency-Key", min_length=1, max_length=128)
IfMatch = Header(default=None, alias="If-Match")


def _compensation_evidence(value: EvidenceRequest | None) -> CompensationEvidence:
    if value is None:
        return CompensationEvidence()
    return CompensationEvidence(
        reservation_released=value.reservation_released,
        payment_refunded=value.payment_refunded,
        provider_reference=value.provider_reference,
        verified_at=value.verified_at,
        details=value.details,
        resolved_payment_status=value.resolved_payment_status,
    )


@router.post(
    "/{booking_id}/reservation",
    response_model=BookingResponse,
    operation_id="attachReservation",
    responses=OK_WITH_ETAG,
)
def attach_reservation(
    booking_id: str,
    body: AttachReservationRequest,
    response: Response,
    idempotency_key: str = IdempotencyKey,
    if_match: str | None = IfMatch,
    context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> BookingResponse:
    booking = service.attach_reservation(
        context,
        idempotency_key=idempotency_key,
        booking_id=booking_id,
        reservation_id=body.reservation_id,
        expected_version=resolve_expected_version(
            body.expected_version, if_match
        ),
        expires_at=body.resolved_expires_at,
        reservation_version=body.reservation_version,
        confirmed=body.resolved_confirmed,
    )
    return booking_response(booking, response)


@router.post(
    "/{booking_id}/reservation-confirmed",
    response_model=BookingResponse,
    operation_id="confirmReservationEvidence",
    responses=OK_WITH_ETAG,
)
def confirm_reservation_evidence(
    booking_id: str,
    body: ConfirmReservationRequest,
    response: Response,
    idempotency_key: str = IdempotencyKey,
    if_match: str | None = IfMatch,
    context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> BookingResponse:
    booking = service.confirm_reservation(
        context,
        idempotency_key=idempotency_key,
        booking_id=booking_id,
        reservation_id=body.reservation_id,
        expected_version=resolve_expected_version(
            body.expected_version, if_match
        ),
        reservation_version=body.reservation_version,
    )
    return booking_response(booking, response)


@router.post(
    "/{booking_id}/payment-started",
    response_model=BookingResponse,
    operation_id="startPayment",
    responses=OK_WITH_ETAG,
)
def start_payment(
    booking_id: str,
    body: StartPaymentRequest,
    response: Response,
    idempotency_key: str = IdempotencyKey,
    if_match: str | None = IfMatch,
    context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> BookingResponse:
    booking = service.start_payment(
        context,
        idempotency_key=idempotency_key,
        booking_id=booking_id,
        payment_id=body.payment_id,
        expected_version=resolve_expected_version(
            body.expected_version, if_match
        ),
    )
    return booking_response(booking, response)


@router.post(
    "/{booking_id}/payment-result",
    response_model=BookingResponse,
    operation_id="recordPayment",
    responses=OK_WITH_ETAG,
)
def record_payment(
    booking_id: str,
    body: RecordPaymentRequest,
    response: Response,
    idempotency_key: str = IdempotencyKey,
    if_match: str | None = IfMatch,
    context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> BookingResponse:
    booking = service.record_payment(
        context,
        idempotency_key=idempotency_key,
        booking_id=booking_id,
        payment_id=body.payment_id,
        payment_status=(
            body.resolved_status if body.payment_status is not None else None
        ),
        succeeded=body.succeeded,
        expected_version=resolve_expected_version(
            body.expected_version, if_match
        ),
        provider_reference=(
            body.evidence.provider_reference if body.evidence else None
        ),
        failure_code=body.failure_code,
    )
    return booking_response(booking, response)


@router.post(
    "/{booking_id}/tickets",
    response_model=BookingResponse,
    operation_id="attachTickets",
    responses=OK_WITH_ETAG,
)
def attach_tickets(
    booking_id: str,
    body: AttachTicketsRequest,
    response: Response,
    idempotency_key: str = IdempotencyKey,
    if_match: str | None = IfMatch,
    context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> BookingResponse:
    booking = service.attach_tickets(
        context,
        idempotency_key=idempotency_key,
        booking_id=booking_id,
        ticket_ids=tuple(body.ticket_ids),
        expected_version=resolve_expected_version(
            body.expected_version, if_match
        ),
    )
    return booking_response(booking, response)


@router.post(
    "/{booking_id}/confirm",
    response_model=BookingResponse,
    operation_id="confirmBooking",
    responses=OK_WITH_ETAG,
)
def confirm(
    booking_id: str,
    body: ConfirmBookingRequest,
    response: Response,
    idempotency_key: str = IdempotencyKey,
    if_match: str | None = IfMatch,
    context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> BookingResponse:
    booking = service.confirm(
        context,
        idempotency_key=idempotency_key,
        booking_id=booking_id,
        expected_version=resolve_expected_version(
            body.expected_version, if_match
        ),
        reservation_id=body.reservation_id,
        payment_id=body.payment_id,
        payment_status=body.resolved_payment_status,
        ticket_ids=(
            tuple(body.ticket_ids) if body.ticket_ids is not None else None
        ),
        seat_confirmed=(body.evidence.seat_confirmed if body.evidence else None),
        payment_captured=(
            body.evidence.payment_captured if body.evidence else None
        ),
        tickets_issued=(body.evidence.tickets_issued if body.evidence else None),
    )
    return booking_response(booking, response)


@router.post(
    "/{booking_id}/fail",
    response_model=BookingResponse,
    operation_id="failBooking",
    responses=OK_WITH_ETAG,
)
def fail(
    booking_id: str,
    body: FailBookingRequest,
    response: Response,
    idempotency_key: str = IdempotencyKey,
    if_match: str | None = IfMatch,
    context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> BookingResponse:
    booking = service.fail(
        context,
        idempotency_key=idempotency_key,
        booking_id=booking_id,
        failure_code=body.failure_code,
        reason=body.reason or body.failure_code,
        expected_version=resolve_expected_version(
            body.expected_version, if_match
        ),
        compensation_status=body.compensation_status,
        evidence=_compensation_evidence(body.evidence),
    )
    return booking_response(booking, response)


@router.post(
    "/{booking_id}/cancel",
    response_model=BookingResponse,
    operation_id="cancelBooking",
    responses=OK_WITH_ETAG,
)
def cancel(
    booking_id: str,
    body: CancelBookingRequest,
    response: Response,
    idempotency_key: str = IdempotencyKey,
    if_match: str | None = IfMatch,
    context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> BookingResponse:
    booking = service.cancel(
        context,
        idempotency_key=idempotency_key,
        booking_id=booking_id,
        reason=body.reason,
        expected_version=resolve_expected_version(
            body.expected_version, if_match
        ),
        payment_status=body.payment_status,
        compensation_status=body.compensation_status,
        evidence=_compensation_evidence(body.evidence),
    )
    return booking_response(booking, response)


@router.post(
    "/{booking_id}/compensation-result",
    response_model=BookingResponse,
    operation_id="recordCompensationResult",
    responses=OK_WITH_ETAG,
)
def compensation_result(
    booking_id: str,
    body: CompensationResultRequest,
    response: Response,
    idempotency_key: str = IdempotencyKey,
    if_match: str | None = IfMatch,
    context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> BookingResponse:
    booking = service.record_compensation(
        context,
        idempotency_key=idempotency_key,
        booking_id=booking_id,
        expected_version=resolve_expected_version(
            body.expected_version, if_match
        ),
        compensation_status=body.compensation_status,
        evidence=_compensation_evidence(body.evidence),
        reason=body.reason,
    )
    return booking_response(booking, response)
