"""Canonical Booking transition and authorization endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Path, Request, Response
from libs.platform_http import etag, parse_if_match

from app.application.service import BookingService
from app.dependencies import get_service
from app.domain.value_objects import RequestContext
from app.middleware.authentication import require_internal_caller
from app.schemas.requests import (
    BookingAccessDecisionRequest,
    ConfirmTransition,
    PaymentResultTransition,
    PaymentStartedTransition,
    ReservationTransition,
    TerminalTransition,
    TicketsTransition,
)
from app.schemas.responses import BookingAccessDecisionResponse, BookingResponse

router = APIRouter(tags=["booking-commands"])


def _transition(
    operation: str,
    booking_id: str,
    body: Any,
    if_match: str,
    idempotency_key: str,
    context: RequestContext,
    service: BookingService,
    response: Response,
) -> BookingResponse:
    booking = service.transition(
        context,
        operation=operation,
        booking_id=booking_id,
        # mode="json" keeps parsed timestamps as canonical strings so the payload is
        # both hashable for idempotency and storable in the JSONB evidence column.
        payload=body.model_dump(mode="json", by_alias=True, exclude_none=True),
        idempotency_key=idempotency_key,
        expected_version=parse_if_match(if_match),
    )
    response.headers["ETag"] = etag(booking.resource_version)
    return BookingResponse.from_entity(booking)


def _headers(
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    if_match: Annotated[str, Header(alias="If-Match", pattern=r'^"[1-9][0-9]*"$')],
) -> tuple[str, str]:
    return idempotency_key, if_match


def _install_transition(path: str, operation: str, model: type[Any]) -> None:
    async def endpoint(
        booking_id: Annotated[str, Path(alias="bookingId")],
        body: Any,
        response: Response,
        headers: tuple[str, str] = Depends(_headers),
        context: RequestContext = Depends(require_internal_caller),
        service: BookingService = Depends(get_service),
    ) -> BookingResponse:
        return _transition(
            operation,
            booking_id,
            body,
            headers[1],
            headers[0],
            context,
            service,
            response,
        )

    endpoint.__name__ = operation
    endpoint.__annotations__["body"] = model
    router.add_api_route(
        path,
        endpoint,
        methods=["POST"],
        response_model=BookingResponse,
        operation_id=operation,
    )


for _path, _operation, _model in (
    ("/bookings/{bookingId}/reservation", "bookingReservation", ReservationTransition),
    (
        "/bookings/{bookingId}/payment-started",
        "bookingPaymentStarted",
        PaymentStartedTransition,
    ),
    (
        "/bookings/{bookingId}/payment-result",
        "bookingPaymentResult",
        PaymentResultTransition,
    ),
    ("/bookings/{bookingId}/tickets", "bookingTickets", TicketsTransition),
    ("/bookings/{bookingId}/confirm", "bookingConfirm", ConfirmTransition),
    ("/bookings/{bookingId}/fail", "bookingFail", TerminalTransition),
    ("/bookings/{bookingId}/cancel", "bookingCancel", TerminalTransition),
):
    _install_transition(_path, _operation, _model)


@router.post(
    "/internal/bookings/{bookingId}/access-decisions",
    response_model=BookingAccessDecisionResponse,
    operation_id="decideBookingResourceAccess",
)
def access_decision(
    booking_id: Annotated[str, Path(alias="bookingId")],
    body: BookingAccessDecisionRequest,
    request: Request,
    correlation_id: Annotated[
        str, Header(alias="X-Correlation-ID", min_length=16, max_length=64)
    ],
    context: RequestContext = Depends(require_internal_caller),
) -> BookingAccessDecisionResponse:
    result = request.app.state.booking_access_authorizer.decide(
        booking_id=booking_id,
        identity_subject=body.identity_subject,
        roles=frozenset(body.roles),
        correlation_id=correlation_id,
    )
    return BookingAccessDecisionResponse.model_validate(result)
