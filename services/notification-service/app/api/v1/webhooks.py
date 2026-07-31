"""Webhook endpoint - noi ESB goi toi sau khi co su kien nghiep vu.

Luon tra HTTP 200 kem truong "status" ("SENT" / "DUPLICATE_IGNORED") -
day la dung hop dong webhook idempotent: khong bao gio tra 4xx/5xx cho
truong hop trung lap, de ESB khong hieu nham la loi va retry vo han.
"""
from fastapi import APIRouter, Depends

from app.application.commands.handle_booking_confirmed import handle_booking_confirmed
from app.application.commands.handle_booking_failed import handle_booking_failed
from app.dependencies import get_provider, get_repository
from app.providers.email_provider import EmailProvider
from app.repositories.interfaces import DeliveryRepository
from app.schemas.requests import BookingConfirmedPayload, BookingFailedPayload
from app.schemas.responses import WebhookResultResponse

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/booking-confirmed", response_model=WebhookResultResponse)
def booking_confirmed(
    payload: BookingConfirmedPayload,
    repo: DeliveryRepository = Depends(get_repository),
    provider: EmailProvider = Depends(get_provider),
):
    status_ = handle_booking_confirmed(repo, provider, payload.model_dump())
    return WebhookResultResponse(status=status_)


@router.post("/booking-failed", response_model=WebhookResultResponse)
def booking_failed(
    payload: BookingFailedPayload,
    repo: DeliveryRepository = Depends(get_repository),
    provider: EmailProvider = Depends(get_provider),
):
    status_ = handle_booking_failed(repo, provider, payload.model_dump())
    return WebhookResultResponse(status=status_)
