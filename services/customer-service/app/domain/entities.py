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
    resource_version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls, customer_id: str, name: str, email: str, phone: str) -> "Customer":
        now = datetime.now(timezone.utc)
        return cls(
            id=customer_id,
            name=name,
            email=email,
            phone=phone,
            status=CustomerStatus.ACTIVE,
            resource_version=1,
            created_at=now,
            updated_at=now,
        )

    def _bump_version(self) -> None:
        # Moi lan Customer resource thuc su thay doi (contact info hoac
        # status), tang resourceVersion len 1 va cap nhat updated_at - day
        # la co che optimistic concurrency ma header If-Match dua vao de
        # phat hien "ai do da sua truoc ban" (xem application/commands/
        # update_customer.py va deactivate_customer.py).
        self.resource_version += 1
        self.updated_at = datetime.now(timezone.utc)

    def update_contact(self, name: str | None = None, email: str | None = None,
                        phone: str | None = None) -> None:
        if name is not None:
            self.name = name
        if email is not None:
            self.email = email
        if phone is not None:
            self.phone = phone
        self._bump_version()

    def deactivate(self) -> None:
        self.status = CustomerStatus.INACTIVE
        self._bump_version()
