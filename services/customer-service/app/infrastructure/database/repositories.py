"""Cac implementation THAT cua CustomerRepository va IdempotencyStore.

- InMemoryCustomerRepository: chi con dung cho tests/unit.
- PostgresCustomerRepository: doc/ghi that qua SQLAlchemy + models.py.
- PostgresIdempotencyStore: luu/doc response theo Idempotency-Key.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import select, update as sa_update
from sqlalchemy.exc import IntegrityError

from app.domain.entities import Customer
from app.domain.enums import ConsentChannel, CustomerStatus
from app.domain.exceptions import DuplicateEmailError, VersionConflictError
from app.infrastructure.database.models import (
    ConsentModel,
    CustomerModel,
    IdempotencyRecordModel,
    customer_id_seq,
)
from app.infrastructure.database.session import session_scope
from app.repositories.interfaces import CustomerRepository, IdempotencyStore


class InMemoryCustomerRepository(CustomerRepository):
    """Chi dung trong tests/unit - khong dung trong app that nua."""

    def __init__(self) -> None:
        self._data: dict[str, Customer] = {}
        self._consents: dict[tuple[str, str], bool] = {}
        self._next = 1
        seed = Customer.create("C001", "Nguyen Van An", "an@example.com", "0901234567")
        self._data[seed.id] = seed
        self._next = 2

    def add(self, customer: Customer) -> None:
        self._data[customer.id] = customer

    def get(self, customer_id: str) -> Optional[Customer]:
        # Tra ve BAN SAO (deepcopy), khong phai object goc dang luu trong
        # self._data - neu tra ve truc tiep, ben goi mutate entity (vd
        # customer.update_contact()) se vo tinh doi luon ban "dang luu"
        # truoc khi update() kip so sanh expected_version, lam vo hieu
        # hoa kiem tra optimistic concurrency. PostgresCustomerRepository
        # khong gap loi nay vi moi lan get() la 1 truy van SQL doc lap,
        # tu nhien tao ra 1 object Python moi.
        current = self._data.get(customer_id)
        return deepcopy(current) if current is not None else None

    def get_by_email(self, email: str) -> Optional[Customer]:
        for c in self._data.values():
            if c.email.lower() == email.lower():
                return deepcopy(c)
        return None

    def get_by_phone(self, phone: str) -> Optional[Customer]:
        for c in self._data.values():
            if c.phone == phone:
                return deepcopy(c)
        return None

    def update(self, customer: Customer, *, expected_version: int) -> None:
        current = self._data.get(customer.id)
        if current is not None and current.resource_version != expected_version:
            raise VersionConflictError(customer.id, current.resource_version, expected_version)
        self._data[customer.id] = customer

    def list_all(self) -> Iterable[Customer]:
        return list(self._data.values())

    def next_id(self) -> str:
        customer_id = f"C{self._next:03d}"
        self._next += 1
        return customer_id

    def set_consent(self, customer_id: str, channel: ConsentChannel, granted: bool) -> None:
        self._consents[(customer_id, channel.value)] = granted


def _to_entity(row: CustomerModel) -> Customer:
    return Customer(
        id=row.id,
        name=row.name,
        email=row.email,
        phone=row.phone,
        status=CustomerStatus(row.status),
        resource_version=row.resource_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class PostgresCustomerRepository(CustomerRepository):
    """Repository that, ket noi PostgreSQL qua SQLAlchemy 2.0."""

    def add(self, customer: Customer) -> None:
        try:
            with session_scope() as session:
                session.add(
                    CustomerModel(
                        id=customer.id,
                        name=customer.name,
                        email=customer.email,
                        phone=customer.phone,
                        status=customer.status.value,
                        resource_version=customer.resource_version,
                        created_at=customer.created_at,
                        updated_at=customer.updated_at,
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

    def get_by_phone(self, phone: str) -> Optional[Customer]:
        with session_scope() as session:
            stmt = select(CustomerModel).where(CustomerModel.phone == phone)
            row = session.execute(stmt).scalar_one_or_none()
            return _to_entity(row) if row is not None else None

    def update(self, customer: Customer, *, expected_version: int) -> None:
        # Optimistic concurrency that su: UPDATE ... WHERE id=? AND
        # resource_version=? trong CUNG 1 cau lenh SQL, khong phai
        # "doc roi kiem tra roi ghi" (co khe ho race condition). Neu 0 dong
        # bi anh huong, nghia la ban ghi da bi nguoi khac sua truoc do
        # (hoac khong ton tai) - ca 2 truong hop deu la loi 409 theo dung
        # ngu nghia If-Match cua HTTP.
        try:
            with session_scope() as session:
                stmt = (
                    sa_update(CustomerModel)
                    .where(
                        CustomerModel.id == customer.id,
                        CustomerModel.resource_version == expected_version,
                    )
                    .values(
                        name=customer.name,
                        email=customer.email,
                        phone=customer.phone,
                        status=customer.status.value,
                        resource_version=customer.resource_version,
                        updated_at=customer.updated_at,
                    )
                )
                result = session.execute(stmt)
                if result.rowcount == 0:
                    current = session.get(CustomerModel, customer.id)
                    current_version = current.resource_version if current else 0
                    raise VersionConflictError(customer.id, current_version, expected_version)
        except IntegrityError as exc:
            raise DuplicateEmailError(customer.email) from exc

    def list_all(self) -> Iterable[Customer]:
        with session_scope() as session:
            rows = session.execute(select(CustomerModel)).scalars().all()
            return [_to_entity(row) for row in rows]

    def next_id(self) -> str:
        with session_scope() as session:
            next_value = session.execute(select(customer_id_seq.next_value())).scalar_one()
            return f"C{next_value:03d}"

    def set_consent(self, customer_id: str, channel: ConsentChannel, granted: bool) -> None:
        with session_scope() as session:
            stmt = select(ConsentModel).where(
                ConsentModel.customer_id == customer_id,
                ConsentModel.channel == channel.value,
            )
            row = session.execute(stmt).scalar_one_or_none()
            now = datetime.now(timezone.utc)
            if row is None:
                session.add(
                    ConsentModel(
                        customer_id=customer_id,
                        channel=channel.value,
                        granted=granted,
                        updated_at=now,
                    )
                )
            else:
                row.granted = granted
                row.updated_at = now


class PostgresIdempotencyStore(IdempotencyStore):
    """Doc/ghi ket qua da xu ly theo Idempotency-Key (bang customer.
    idempotency_records) - xem repositories/interfaces.py de biet vi sao
    can co store nay."""

    def get(self, key: str) -> Optional[tuple[int, dict]]:
        with session_scope() as session:
            row = session.get(IdempotencyRecordModel, key)
            if row is None:
                return None
            return row.response_status, row.response_body

    def save(self, key: str, status_code: int, body: dict) -> None:
        # Idempotency-Key la primary key: neu 2 request trung key gan dong
        # thoi, request thua se bi IntegrityError khi INSERT - o muc do nay
        # chap nhan im lang bo qua (ban ghi dau tien thang la dung), vi ca 2
        # request deu dang xu ly CUNG 1 logical operation, khong phai loi
        # nghiep vu can bao cho client. Bat IntegrityError O NGOAI
        # session_scope() (khong phai ben trong) de session tu rollback
        # dung cach truoc khi dong - bat ben trong se de transaction o
        # trang thai "aborted" ma khong duoc dong sach.
        try:
            with session_scope() as session:
                session.add(
                    IdempotencyRecordModel(
                        idempotency_key=key,
                        response_status=status_code,
                        response_body=body,
                        created_at=datetime.now(timezone.utc),
                    )
                )
        except IntegrityError:
            pass
