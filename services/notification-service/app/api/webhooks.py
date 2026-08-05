"""Webhook endpoint - noi ESB goi toi sau khi co su kien nghiep vu."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.consumers.booking_confirmed import handle_booking_confirmed
from app.consumers.booking_failed import handle_booking_failed
from app.delivery.deduplication import DeduplicationStore
from app.dependencies import get_dedup_store, get_delivery_log, get_provider
from app.providers.email_provider import EmailProvider
from app.repositories.interfaces import DeliveryLogRepository

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class BookingConfirmedPayload(BaseModel):
    event: str
    correlationId: str
    bookingId: str
    customerEmail: str
    ticketIds: list[str] = []


class BookingFailedPayload(BaseModel):
    event: str
    correlationId: str
    bookingId: str
    customerEmail: str = ""
    reason: str = ""


@router.post("/booking-confirmed")
def booking_confirmed(
    payload: BookingConfirmedPayload,
    provider: EmailProvider = Depends(get_provider),
    dedup: DeduplicationStore = Depends(get_dedup_store),
    delivery_log: DeliveryLogRepository = Depends(get_delivery_log),
):
    status_ = handle_booking_confirmed(
        payload.model_dump(), provider, dedup, delivery_log
    )
    return {"status": status_}


@router.post("/booking-failed")
def booking_failed(
    payload: BookingFailedPayload,
    provider: EmailProvider = Depends(get_provider),
    dedup: DeduplicationStore = Depends(get_dedup_store),
    delivery_log: DeliveryLogRepository = Depends(get_delivery_log),
):
    status_ = handle_booking_failed(payload.model_dump(), provider, dedup, delivery_log)
    return {"status": status_}
