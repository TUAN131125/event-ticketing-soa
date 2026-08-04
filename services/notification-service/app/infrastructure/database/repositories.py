"""Cac implementation THAT cua EventDeliveryRepository/TemplateRepository.

- InMemory*: dung dict trong bo nho, chi dung cho unit test.
- Postgres*: doc/ghi that qua SQLAlchemy + models.py.
"""
from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.domain.entities import Delivery, DeliveryAttempt, InboundEvent, Template
from app.domain.enums import Channel, DeliveryStatus, EventType
from app.domain.exceptions import DuplicateEventError, NotificationDomainError
from app.infrastructure.database.models import (
    DeliveryAttemptModel,
    DeliveryModel,
    InboundEventModel,
    TemplateModel,
    delivery_id_seq,
)
from app.infrastructure.database.session import session_scope
from app.repositories.interfaces import EventDeliveryRepository, TemplateRepository

PK_INBOUND_EVENTS = "inbound_events_pkey"


class InMemoryEventDeliveryRepository(EventDeliveryRepository):
    """Chi dung trong tests/unit."""

    def __init__(self) -> None:
        self._events: dict[str, InboundEvent] = {}
        self._deliveries: dict[str, Delivery] = {}
        self._attempts: list[DeliveryAttempt] = []
        self._next = 1

    def event_exists(self, event_id: str) -> bool:
        return event_id in self._events

    def get_event(self, event_id: str) -> Optional[InboundEvent]:
        return self._events.get(event_id)

    def add_event(self, event: InboundEvent) -> None:
        if event.event_id in self._events:
            raise DuplicateEventError(event.event_id)
        self._events[event.event_id] = event

    def add_delivery(self, delivery: Delivery) -> None:
        self._deliveries[delivery.id] = delivery

    def get_delivery(self, delivery_id: str) -> Optional[Delivery]:
        return self._deliveries.get(delivery_id)

    def list_deliveries(self) -> Iterable[Delivery]:
        return list(self._deliveries.values())

    def update_delivery(self, delivery: Delivery) -> None:
        self._deliveries[delivery.id] = delivery

    def add_attempt(self, attempt: DeliveryAttempt) -> None:
        self._attempts.append(attempt)

    def next_delivery_id(self) -> str:
        delivery_id = f"DLV{self._next:06d}"
        self._next += 1
        return delivery_id


class InMemoryTemplateRepository(TemplateRepository):
    def __init__(self) -> None:
        self._templates: dict[str, Template] = {}

    def get(self, code: str) -> Optional[Template]:
        return self._templates.get(code)

    def save(self, template: Template) -> None:
        self._templates[template.code] = template


def _event_to_entity(row: InboundEventModel) -> InboundEvent:
    return InboundEvent(
        event_id=row.event_id,
        event_type=EventType(row.event_type),
        schema_version=row.schema_version,
        correlation_id=row.correlation_id,
        aggregate_id=row.aggregate_id,
        payload=row.payload,
        received_at=row.received_at,
    )


def _delivery_to_entity(row: DeliveryModel) -> Delivery:
    return Delivery(
        id=row.delivery_id,
        event_id=row.event_id,
        channel=Channel(row.channel),
        destination_hash=row.destination_hash,
        status=DeliveryStatus(row.status),
        attempt_count=row.attempt_count,
        next_attempt_at=row.next_attempt_at,
        last_error_code=row.last_error_code,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class PostgresEventDeliveryRepository(EventDeliveryRepository):
    def event_exists(self, event_id: str) -> bool:
        with session_scope() as session:
            stmt = select(InboundEventModel.event_id).where(
                InboundEventModel.event_id == event_id
            )
            return session.execute(stmt).scalar_one_or_none() is not None

    def get_event(self, event_id: str) -> Optional[InboundEvent]:
        with session_scope() as session:
            row = session.get(InboundEventModel, event_id)
            return _event_to_entity(row) if row is not None else None

    def add_event(self, event: InboundEvent) -> None:
        # inbound_events CHI co 1 constraint (PRIMARY KEY event_id), nen o
        # day IntegrityError chi co the la do trung eventId - khac voi
        # add_delivery() ben duoi, khong can phan biet nhieu constraint.
        try:
            with session_scope() as session:
                session.add(
                    InboundEventModel(
                        event_id=event.event_id,
                        event_type=event.event_type.value,
                        schema_version=event.schema_version,
                        correlation_id=event.correlation_id,
                        aggregate_id=event.aggregate_id,
                        payload=event.payload,
                        received_at=event.received_at,
                    )
                )
        except IntegrityError as exc:
            raise DuplicateEventError(event.event_id) from exc

    def add_delivery(self, delivery: Delivery) -> None:
        # QUAN TRONG (bai hoc tu bug id trung khoa chinh o phien ban
        # truoc): KHONG duoc bat IntegrityError roi doan bua la loi gi.
        # Delivery duoc tao SAU khi add_event() da thanh cong (event_id
        # chac chan ton tai va duy nhat), nen o day chi con lai 2 kha
        # nang gay IntegrityError That su bat thuong: trung khoa chinh
        # delivery_id (bug ha tang, vd sequence bi reset sai) hoac vi
        # pham FK event_id (khong nen xay ra vi da add_event() truoc).
        # Ca 2 truong hop deu la loi that, PHAI nem lai nguyen ven (HTTP
        # 500) thay vi nuot lang thanh ket qua nghiep vu sai.
        with session_scope() as session:
            session.add(
                DeliveryModel(
                    delivery_id=delivery.id,
                    event_id=delivery.event_id,
                    channel=delivery.channel.value,
                    destination_hash=delivery.destination_hash,
                    status=delivery.status.value,
                    attempt_count=delivery.attempt_count,
                    next_attempt_at=delivery.next_attempt_at,
                    last_error_code=delivery.last_error_code,
                    created_at=delivery.created_at,
                    updated_at=delivery.updated_at,
                )
            )

    def get_delivery(self, delivery_id: str) -> Optional[Delivery]:
        with session_scope() as session:
            row = session.get(DeliveryModel, delivery_id)
            return _delivery_to_entity(row) if row is not None else None

    def list_deliveries(self) -> Iterable[Delivery]:
        with session_scope() as session:
            stmt = select(DeliveryModel).order_by(DeliveryModel.created_at)
            rows = session.execute(stmt).scalars().all()
            return [_delivery_to_entity(row) for row in rows]

    def update_delivery(self, delivery: Delivery) -> None:
        with session_scope() as session:
            row = session.get(DeliveryModel, delivery.id)
            if row is None:
                raise NotificationDomainError(f"Delivery {delivery.id} bien mat khi cap nhat")
            row.status = delivery.status.value
            row.attempt_count = delivery.attempt_count
            row.next_attempt_at = delivery.next_attempt_at
            row.last_error_code = delivery.last_error_code
            row.updated_at = delivery.updated_at

    def add_attempt(self, attempt: DeliveryAttempt) -> None:
        with session_scope() as session:
            session.add(
                DeliveryAttemptModel(
                    delivery_id=attempt.delivery_id,
                    attempt_no=attempt.attempt_no,
                    status=attempt.status.value,
                    error_code=attempt.error_code,
                    occurred_at=attempt.occurred_at,
                )
            )

    def next_delivery_id(self) -> str:
        with session_scope() as session:
            next_value = session.execute(select(delivery_id_seq.next_value())).scalar_one()
            return f"DLV{next_value:06d}"


class PostgresTemplateRepository(TemplateRepository):
    def get(self, code: str) -> Optional[Template]:
        with session_scope() as session:
            row = session.get(TemplateModel, code)
            if row is None:
                return None
            return Template(
                code=row.template_code,
                subject=row.subject,
                body=row.body,
                resource_version=row.resource_version,
                updated_at=row.updated_at,
            )

    def save(self, template: Template) -> None:
        with session_scope() as session:
            row = session.get(TemplateModel, template.code)
            if row is None:
                session.add(
                    TemplateModel(
                        template_code=template.code,
                        subject=template.subject,
                        body=template.body,
                        resource_version=template.resource_version,
                        updated_at=template.updated_at,
                    )
                )
            else:
                row.subject = template.subject
                row.body = template.body
                row.resource_version = template.resource_version
                row.updated_at = template.updated_at
