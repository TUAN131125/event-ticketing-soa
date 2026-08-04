"""EVT-03: Liet ke su kien, loc theo status + phan trang."""

from app.domain.entities import Event
from app.domain.enums import EventStatus
from app.repositories.interfaces import EventRepository


def list_events(
    repo: EventRepository, status: EventStatus | None, page: int, page_size: int
) -> tuple[list[Event], int]:
    return repo.list(status, page, page_size)
