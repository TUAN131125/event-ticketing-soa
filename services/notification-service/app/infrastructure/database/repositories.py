"""In-memory test and PostgreSQL Notification repositories."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.domain.entities import Delivery, NotificationTemplate
from app.domain.enums import DeliveryStatus
from app.domain.exceptions import DuplicateCorrelationError
from app.infrastructure.database.models import (
    DeliveryModel,
    TemplateModel,
    delivery_id_seq,
)
from app.infrastructure.database.session import session_scope
from app.repositories.interfaces import DeliveryRepository


def _delivery(row: DeliveryModel) -> Delivery:
    return Delivery(
        id=row.id,
        event_id=row.event_id,
        channel=row.channel,
        status=DeliveryStatus(row.status),
        attempt_count=row.attempt_count,
        last_error_code=row.last_error_code,
        to_address=row.to_address,
        subject=row.subject,
        body=row.body,
        created_at=row.created_at,
        resource_version=row.resource_version,
    )


class InMemoryDeliveryRepository(DeliveryRepository):
    def __init__(self) -> None:
        self._data: dict[str, Delivery] = {}
        self._templates: dict[str, NotificationTemplate] = {}
        self._next = 1

    def add(self, delivery: Delivery) -> None:
        if self.get_by_event_id(delivery.event_id) is not None:
            raise DuplicateCorrelationError(delivery.event_id)
        self._data[delivery.id] = delivery

    def update(self, delivery: Delivery) -> None:
        self._data[delivery.id] = delivery

    def get(self, delivery_id: str) -> Delivery | None:
        return self._data.get(delivery_id)

    def get_by_event_id(self, event_id: str) -> Delivery | None:
        return next(
            (item for item in self._data.values() if item.event_id == event_id), None
        )

    def list_all(self) -> Iterable[Delivery]:
        return list(self._data.values())

    def next_id(self) -> str:
        value = f"N{self._next:06d}"
        self._next += 1
        return value

    def get_template(self, code: str) -> NotificationTemplate | None:
        return self._templates.get(code)

    def save_template(self, template: NotificationTemplate) -> None:
        self._templates[template.code] = template


class PostgresDeliveryRepository(DeliveryRepository):
    def add(self, delivery: Delivery) -> None:
        try:
            with session_scope() as session:
                session.add(DeliveryModel(**_delivery_values(delivery)))
        except IntegrityError as exc:
            raise DuplicateCorrelationError(delivery.event_id) from exc

    def update(self, delivery: Delivery) -> None:
        with session_scope() as session:
            row = session.get(DeliveryModel, delivery.id)
            if row is None:
                session.add(DeliveryModel(**_delivery_values(delivery)))
                return
            for key, value in _delivery_values(delivery).items():
                setattr(row, key, value)

    def get(self, delivery_id: str) -> Delivery | None:
        with session_scope() as session:
            row = session.get(DeliveryModel, delivery_id)
            return _delivery(row) if row is not None else None

    def get_by_event_id(self, event_id: str) -> Delivery | None:
        with session_scope() as session:
            row = session.execute(
                select(DeliveryModel).where(DeliveryModel.event_id == event_id)
            ).scalar_one_or_none()
            return _delivery(row) if row is not None else None

    def list_all(self) -> Iterable[Delivery]:
        with session_scope() as session:
            rows = (
                session.execute(
                    select(DeliveryModel).order_by(DeliveryModel.created_at)
                )
                .scalars()
                .all()
            )
            return [_delivery(row) for row in rows]

    def next_id(self) -> str:
        with session_scope() as session:
            value = session.execute(select(delivery_id_seq.next_value())).scalar_one()
            return f"N{value:06d}"

    def get_template(self, code: str) -> NotificationTemplate | None:
        with session_scope() as session:
            row = session.get(TemplateModel, code)
            if row is None:
                return None
            return NotificationTemplate(
                row.code, row.subject, row.body, row.resource_version
            )

    def save_template(self, template: NotificationTemplate) -> None:
        with session_scope() as session:
            row = session.get(TemplateModel, template.code)
            if row is None:
                session.add(
                    TemplateModel(
                        code=template.code,
                        subject=template.subject,
                        body=template.body,
                        resource_version=template.resource_version,
                    )
                )
            else:
                row.subject = template.subject
                row.body = template.body
                row.resource_version = template.resource_version


def _delivery_values(delivery: Delivery) -> dict[str, object]:
    return {
        "id": delivery.id,
        "event_id": delivery.event_id,
        "channel": delivery.channel,
        "status": delivery.status.value,
        "attempt_count": delivery.attempt_count,
        "last_error_code": delivery.last_error_code,
        "to_address": delivery.to_address,
        "subject": delivery.subject,
        "body": delivery.body,
        "created_at": delivery.created_at,
        "resource_version": delivery.resource_version,
    }
