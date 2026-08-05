"""Entity thuan nghiep vu cua Customer Service.

Khong phu thuoc FastAPI, khong phu thuoc database - day la quy tac cot loi
cua Clean Architecture: domain khong biet gi ve tang ben ngoai.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from app.domain.enums import CustomerStatus


@dataclass
class Customer:
    id: str
    name: str
    email: str
    phone: str | None
    status: CustomerStatus
    created_at: datetime
    updated_at: datetime
    resource_version: int

    @classmethod
    def create(
        cls, customer_id: str, name: str, email: str, phone: str | None
    ) -> "Customer":
        now = datetime.now(UTC)
        return cls(
            id=customer_id,
            name=name,
            email=email,
            phone=phone,
            status=CustomerStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            resource_version=1,
        )

    def update_contact(
        self,
        name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> None:
        if name is not None:
            self.name = name
        if email is not None:
            self.email = email
        if phone is not None:
            self.phone = phone
        self.updated_at = datetime.now(UTC)
        self.resource_version += 1

    def deactivate(self) -> None:
        self.status = CustomerStatus.INACTIVE
        self.updated_at = datetime.now(UTC)
        self.resource_version += 1


@dataclass
class IdentityMapping:
    identity_subject: str
    customer_id: str
    status: str
    resource_version: int
    linked_at: datetime
    updated_at: datetime
