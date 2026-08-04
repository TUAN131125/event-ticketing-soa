"""Interface (Protocol) cho repository - domain/application chi biet
interface nay, khong biet du lieu thuc su luu o dau."""

from collections.abc import Iterable
from typing import Protocol

from app.domain.entities import Event
from app.domain.enums import EventStatus


class EventRepository(Protocol):
    def add(self, event: Event) -> None: ...
    def get(self, event_id: str) -> Event | None: ...
    def update(self, event: Event, expected_version: int) -> Event:
        """Ghi thay doi voi optimistic concurrency: neu resourceVersion
        hien tai trong DB khac expected_version, phai raise
        VersionConflictError (khong ghi de). Tra ve entity da duoc tang
        resourceVersion sau khi ghi thanh cong."""
        ...

    def list(
        self, status: EventStatus | None, page: int, page_size: int
    ) -> tuple[list[Event], int]:
        """Tra ve (trang du lieu, tong so ban ghi khop filter) - EVT-03."""
        ...

    def next_id(self) -> str: ...


class IdempotencyRepository(Protocol):
    """Luu ket qua cua 1 request theo Idempotency-Key, dam bao retry cua
    ESB voi cung key khong thuc thi lai nghiep vu (POST/PUT/publish/
    pause/cancel deu yeu cau Idempotency-Key theo contract)."""

    def get(self, scope: str) -> tuple[str, int, dict] | None:
        """Tra ve (request_hash, status_code, response_body) neu da co."""
        ...

    def save(
        self, scope: str, request_hash: str, status_code: int, response_body: dict
    ) -> None: ...


class AuditRepository(Protocol):
    """EVT-11 - ghi audit record cho moi command lam thay doi du lieu."""

    def record(self, event_id: str, actor_id: str, action: str) -> None: ...

    def list_for_event(self, event_id: str) -> Iterable[dict]: ...
