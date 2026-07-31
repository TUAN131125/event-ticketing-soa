"""Use case: tao su kien moi (mac dinh trang thai DRAFT, chua mo ban)."""
from app.domain.entities import Event
from app.domain.value_objects import TicketType
from app.repositories.interfaces import EventRepository


def create_event(repo: EventRepository, name: str, location: str, start_time: str,
                  ticket_types: list[TicketType]) -> Event:
    event_id = repo.next_id()
    event = Event.create(event_id, name, location, start_time, ticket_types)
    repo.add(event)
    return event
