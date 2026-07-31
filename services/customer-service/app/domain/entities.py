"""Entity thuan nghiep vu cua Customer Service.

Khong phu thuoc FastAPI, khong phu thuoc database - day la quy tac cot loi
cua Clean Architecture: domain khong biet gi ve tang ben ngoai.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from app.domain.enums import CustomerStatus


@dataclass
class Customer:
    id: str
    name: str
    email: str
    phone: str
    status: CustomerStatus
    created_at: datetime

    @classmethod
    def create(cls, customer_id: str, name: str, email: str, phone: str) -> "Customer":
        return cls(
            id=customer_id,
            name=name,
            email=email,
            phone=phone,
            status=CustomerStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
        )

    def update_contact(self, name: str | None = None, email: str | None = None,
                        phone: str | None = None) -> None:
        if name is not None:
            self.name = name
        if email is not None:
            self.email = email
        if phone is not None:
            self.phone = phone

    def deactivate(self) -> None:
        self.status = CustomerStatus.INACTIVE
