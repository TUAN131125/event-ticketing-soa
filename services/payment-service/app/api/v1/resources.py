"""Canonical Payment create, get and provider callback endpoints."""

from decimal import Decimal
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Path,
    Request,
    Response,
    Security,
    status,
)
from fastapi.security import APIKeyHeader
from libs.platform_http import etag
from libs.platform_security import HmacAuthenticationError

from app.application.service import PaymentService
from app.dependencies import get_service
from app.domain.value_objects import RequestContext
from app.middleware.authentication import require_internal_caller
from app.schemas.requests import CreatePaymentRequest, ProviderCallbackRequest
from app.schemas.responses import PaymentResponse

router = APIRouter(tags=["payments"])
PROVIDER_HMAC = APIKeyHeader(
    name="X-Provider-Signature", auto_error=False, scheme_name="providerHmac"
)


@router.post(
    "/payments",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createPayment",
)
def create(
    body: CreatePaymentRequest,
    response: Response,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    payment = service.create(
        context,
        idempotency_key=idempotency_key,
        booking_id=body.booking_id,
        customer_id="SERVICE",
        amount=Decimal(body.amount.amount_minor),
        currency=body.amount.currency,
        payment_method=body.method_token,
        provider="local-provider",
    )
    response.headers["ETag"] = etag(payment.resource_version)
    return PaymentResponse.from_entity(payment)


@router.get(
    "/payments/{paymentId}",
    response_model=PaymentResponse,
    operation_id="getPayment",
)
def get(
    payment_id: Annotated[str, Path(alias="paymentId")],
    response: Response,
    context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    payment = service.get(payment_id)
    response.headers["ETag"] = etag(payment.resource_version)
    return PaymentResponse.from_entity(payment)


async def _verify_provider_hmac(
    request: Request,
    signature: Annotated[str | None, Security(PROVIDER_HMAC)],
) -> None:
    try:
        request.app.state.provider_hmac_verifier.verify(
            timestamp=request.headers.get("X-Provider-Timestamp"),
            signature=signature,
            body=await request.body(),
        )
    except HmacAuthenticationError as exc:
        raise HTTPException(
            status_code=401, detail="Provider authentication failed"
        ) from exc


@router.post(
    "/payments/provider-callback",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="receiveProviderCallback",
    dependencies=[Depends(_verify_provider_hmac)],
    openapi_extra={
        "parameters": [
            {
                "name": "X-Provider-Timestamp",
                "in": "header",
                "required": True,
                "schema": {
                    "type": "string",
                    "format": "date-time",
                    "pattern": r"(?:Z|\+00:00)$",
                },
            }
        ]
    },
)
def provider_callback(
    body: ProviderCallbackRequest,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    service: PaymentService = Depends(get_service),
) -> Response:
    service.get(body.payment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
