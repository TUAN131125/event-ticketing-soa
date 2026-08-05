"""Use case: lay chi tiet 1 su kien.

Ghi chu: file nay bo sung them vao application/commands/ (khong co san
trong ban scaffold ban dau) vi can thao tac doc theo id ma chua co endpoint
nao phu trach - tuong tu cach Customer Service dat get_customer.py.
"""

from app.domain.entities import Event
from app.domain.exceptions import EventNotFoundError
from app.repositories.interfaces import EventRepository


def get_event(repo: EventRepository, event_id: str) -> Event:
    event = repo.get(event_id)
    if event is None:
        raise EventNotFoundError(event_id)
    return event
