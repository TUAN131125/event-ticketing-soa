"""Cac implementation THAT cua CustomerRepository.

- InMemoryCustomerRepository: dung dict trong bo nho, chi con dung cho
  unit test (nhanh, khong can Postgres chay san). KHONG con duoc dung
  trong app that (xem dependencies.py).
- PostgresCustomerRepository: doc/ghi that qua SQLAlchemy + models.py,
  moi phuong thuc tu mo/dong 1 session (session_scope) nen an toan khi
  FastAPI goi dong thoi nhieu request cung luc (moi request 1 session
  rieng, khong chia se ket noi).
"""
from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.domain.entities import Customer
from app.domain.enums import CustomerStatus
from app.domain.exceptions import DuplicateEmailError
from app.infrastructure.database.models import CustomerModel, customer_id_seq
from app.infrastructure.database.session import session_scope
from app.repositories.interfaces import CustomerRepository


class InMemoryCustomerRepository(CustomerRepository):
    """Chi dung trong tests/unit - khong dung trong app that nua."""

    def __init__(self) -> None:
        self._data: dict[str, Customer] = {}
        self._next = 1
        seed = Customer.create("C001", "Nguyen Van An", "an@example.com", "0901234567")
        self._data[seed.id] = seed
        self._next = 2

    def add(self, customer: Customer) -> None:
        self._data[customer.id] = customer

    def get(self, customer_id: str) -> Optional[Customer]:
        return self._data.get(customer_id)

    def get_by_email(self, email: str) -> Optional[Customer]:
        for c in self._data.values():
            if c.email.lower() == email.lower():
                return c
        return None

    def update(self, customer: Customer) -> None:
        self._data[customer.id] = customer

    def list_all(self) -> Iterable[Customer]:
        return list(self._data.values())

    def next_id(self) -> str:
        customer_id = f"C{self._next:03d}"
        self._next += 1
        return customer_id


def _to_entity(row: CustomerModel) -> Customer:
    return Customer(
        id=row.id,
        name=row.name,
        email=row.email,
        phone=row.phone,
        status=CustomerStatus(row.status),
        created_at=row.created_at,
    )


class PostgresCustomerRepository(CustomerRepository):
    """Repository that, ket noi PostgreSQL qua SQLAlchemy Core/ORM."""

    def add(self, customer: Customer) -> None:
        # Kiem tra trung email o tang application (ensure_email_unique) chi
        # chan duoc phan lon truong hop, van con khe ho race condition khi
        # 2 request tao cung email gan nhu dong thoi. UNIQUE constraint
        # tren cot email (migration 0001) la hang rao cuoi cung dam bao
        # integrity that su - IntegrityError o day duoc dich lai thanh loi
        # domain quen thuoc de middleware/error_handler.py xu ly nhu binh
        # thuong (van tra 409, khong lo ra loi 500 tho).
        try:
            with session_scope() as session:
                session.add(
                    CustomerModel(
                        id=customer.id,
                        name=customer.name,
                        email=customer.email,
                        phone=customer.phone,
                        status=customer.status.value,
                        created_at=customer.created_at,
                    )
                )
        except IntegrityError as exc:
            raise DuplicateEmailError(customer.email) from exc

    def get(self, customer_id: str) -> Optional[Customer]:
        with session_scope() as session:
            row = session.get(CustomerModel, customer_id)
            return _to_entity(row) if row is not None else None

    def get_by_email(self, email: str) -> Optional[Customer]:
        with session_scope() as session:
            stmt = select(CustomerModel).where(CustomerModel.email.ilike(email))
            row = session.execute(stmt).scalar_one_or_none()
            return _to_entity(row) if row is not None else None

    def update(self, customer: Customer) -> None:
        try:
            with session_scope() as session:
                row = session.get(CustomerModel, customer.id)
                if row is None:
                    # Phong thu: neu vi ly do nao do ban ghi khong con ton
                    # tai, coi nhu upsert de khong lam mat du lieu da xac
                    # thuc o tang domain.
                    session.add(
                        CustomerModel(
                            id=customer.id,
                            name=customer.name,
                            email=customer.email,
                            phone=customer.phone,
                            status=customer.status.value,
                            created_at=customer.created_at,
                        )
                    )
                    return
                row.name = customer.name
                row.email = customer.email
                row.phone = customer.phone
                row.status = customer.status.value
        except IntegrityError as exc:
            raise DuplicateEmailError(customer.email) from exc

    def list_all(self) -> Iterable[Customer]:
        with session_scope() as session:
            rows = session.execute(select(CustomerModel)).scalars().all()
            return [_to_entity(row) for row in rows]

    def next_id(self) -> str:
        # Dung PostgreSQL SEQUENCE de sinh so thu tu duy nhat ngay tai
        # tang database - an toan khi nhieu worker/container cung goi
        # dong thoi (khac voi bien dem trong bo nho cua ban InMemory).
        with session_scope() as session:
            next_value = session.execute(select(customer_id_seq.next_value())).scalar_one()
            return f"C{next_value:03d}"
