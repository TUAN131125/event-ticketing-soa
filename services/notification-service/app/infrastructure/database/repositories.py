"""Cac implementation THAT cua DeliveryRepository.

- InMemoryDeliveryRepository: dung dict trong bo nho, chi con dung cho
  unit test (nhanh, khong can Postgres chay san). KHONG con duoc dung
  trong app that (xem dependencies.py). Day cung chinh la nang cap so
  voi ban MVP truoc day (InMemoryDeliveryLogRepository + DeduplicationStore
  rieng bang set) - gio gop lai lam mot, unique constraint dam nhiem viec
  chong trung correlationId thay vi 1 set rieng trong bo nho.
- PostgresDeliveryRepository: doc/ghi that qua SQLAlchemy + models.py,
  moi phuong thuc tu mo/dong 1 session (session_scope) nen an toan khi
  FastAPI goi dong thoi nhieu request cung luc.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.domain.entities import Delivery
from app.domain.enums import DeliveryStatus, NotificationType
from app.domain.exceptions import DuplicateCorrelationError
from app.infrastructure.database.models import DeliveryModel, delivery_id_seq
from app.infrastructure.database.session import session_scope
from app.repositories.interfaces import DeliveryRepository


class InMemoryDeliveryRepository(DeliveryRepository):
    """Chi dung trong tests/unit - khong dung trong app that nua."""

    def __init__(self) -> None:
        self._data: dict[str, Delivery] = {}
        self._by_correlation: set[str] = set()
        self._next = 1

    def add(self, delivery: Delivery) -> None:
        if delivery.correlation_id in self._by_correlation:
            raise DuplicateCorrelationError(delivery.correlation_id)
        self._data[delivery.id] = delivery
        self._by_correlation.add(delivery.correlation_id)

    def get(self, delivery_id: str) -> Delivery | None:
        return self._data.get(delivery_id)

    def exists_by_correlation_id(self, correlation_id: str) -> bool:
        return correlation_id in self._by_correlation

    def list_all(self) -> Iterable[Delivery]:
        return list(self._data.values())

    def next_id(self) -> str:
        delivery_id = f"N{self._next:06d}"
        self._next += 1
        return delivery_id


def _to_entity(row: DeliveryModel) -> Delivery:
    return Delivery(
        id=row.id,
        type=NotificationType(row.type),
        correlation_id=row.correlation_id,
        to_email=row.to_email,
        subject=row.subject,
        body=row.body,
        status=DeliveryStatus(row.status),
        created_at=row.created_at,
    )


class PostgresDeliveryRepository(DeliveryRepository):
    """Repository that, ket noi PostgreSQL qua SQLAlchemy Core/ORM."""

    def add(self, delivery: Delivery) -> None:
        # Kiem tra trung correlationId o tang application
        # (ensure_correlation_not_duplicate / exists_by_correlation_id) chi
        # chan duoc phan lon truong hop, van con khe ho race condition khi
        # ESB goi lai webhook 2 lan gan nhu dong thoi. UNIQUE constraint
        # tren cot correlation_id (migration 0001) la hang rao cuoi cung
        # dam bao integrity that su - IntegrityError o day duoc dich lai
        # thanh loi domain quen thuoc, KHONG lo ra thanh HTTP 500 (xem
        # application/commands/handle_booking_confirmed.py: bat loi nay va
        # tra ve status "DUPLICATE_IGNORED" nhu webhook idempotent binh
        # thuong, dung hop dong voi ban MVP truoc day).
        try:
            with session_scope() as session:
                session.add(
                    DeliveryModel(
                        id=delivery.id,
                        type=delivery.type.value,
                        correlation_id=delivery.correlation_id,
                        to_email=delivery.to_email,
                        subject=delivery.subject,
                        body=delivery.body,
                        status=delivery.status.value,
                        created_at=delivery.created_at,
                    )
                )
        except IntegrityError as exc:
            raise DuplicateCorrelationError(delivery.correlation_id) from exc

    def get(self, delivery_id: str) -> Delivery | None:
        with session_scope() as session:
            row = session.get(DeliveryModel, delivery_id)
            return _to_entity(row) if row is not None else None

    def exists_by_correlation_id(self, correlation_id: str) -> bool:
        with session_scope() as session:
            stmt = select(DeliveryModel.id).where(
                DeliveryModel.correlation_id == correlation_id
            )
            return session.execute(stmt).scalar_one_or_none() is not None

    def list_all(self) -> Iterable[Delivery]:
        with session_scope() as session:
            stmt = select(DeliveryModel).order_by(DeliveryModel.created_at)
            rows = session.execute(stmt).scalars().all()
            return [_to_entity(row) for row in rows]

    def next_id(self) -> str:
        # Dung PostgreSQL SEQUENCE de sinh so thu tu duy nhat ngay tai
        # tang database - an toan khi nhieu worker/container cung goi
        # dong thoi (khac voi bien dem trong bo nho cua ban InMemory).
        with session_scope() as session:
            next_value = session.execute(
                select(delivery_id_seq.next_value())
            ).scalar_one()
            return f"N{next_value:06d}"
