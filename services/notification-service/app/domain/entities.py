"""Entity thuan nghiep vu cua Notification Service.

Khong phu thuoc FastAPI, khong phu thuoc database, khong phu thuoc cach
gui email that su (do la viec cua app/providers) - day la quy tac cot loi
cua Clean Architecture, giong het Customer Service/Event Service.
"""
from dataclasses import dataclass
from datetime import UTC, datetime

from app.domain.enums import DeliveryStatus, NotificationType


@dataclass
class Delivery:
    id: str
    type: NotificationType
    correlation_id: str
    to_email: str
    subject: str
    body: str
    status: DeliveryStatus
    created_at: datetime

    @classmethod
    def create(
        cls,
        delivery_id: str,
        type_: NotificationType,
        correlation_id: str,
        to_email: str,
        subject: str,
        body: str,
        status: DeliveryStatus = DeliveryStatus.SENT,
    ) -> "Delivery":
        return cls(
            id=delivery_id,
            type=type_,
            correlation_id=correlation_id,
            to_email=to_email,
            subject=subject,
            body=body,
            status=status,
            created_at=datetime.now(UTC),
        )
