"""Integration test - can PostgreSQL that dang chay (xem conftest.py).
Chay bang: pytest tests/integration -m integration

Test nhung thu InMemoryEventRepository KHONG the bao dam: sequence sinh
id dung tai tang DB, ticket_types (bang con) duoc luu/doc dung kem theo
event cha, va du lieu con lai sau khi "restart" (engine moi, ket noi
moi).
"""

from __future__ import annotations

import pytest

from app.domain.entities import Event
from app.domain.enums import EventStatus
from app.domain.value_objects import TicketType
from app.infrastructure.database.repositories import PostgresEventRepository

pytestmark = pytest.mark.integration


def test_next_id_increments_via_db_sequence(
    postgres_repo: PostgresEventRepository,
) -> None:
    assert postgres_repo.next_id() == "EV001"
    assert postgres_repo.next_id() == "EV002"
    assert postgres_repo.next_id() == "EV003"


def test_add_and_get_round_trip_with_ticket_types(
    postgres_repo: PostgresEventRepository,
) -> None:
    event = Event.create(
        "EV001",
        "Hoi cho cong nghe",
        "SECC Quan 7",
        "2026-09-10T09:00:00",
        [TicketType("VIP", 2000000), TicketType("STANDARD", 700000)],
    )
    postgres_repo.add(event)

    fetched = postgres_repo.get("EV001")
    assert fetched is not None
    assert fetched.name == "Hoi cho cong nghe"
    assert fetched.status == EventStatus.DRAFT
    assert {(t.type, t.price) for t in fetched.ticket_types} == {
        ("VIP", 2000000),
        ("STANDARD", 700000),
    }


def test_get_missing_returns_none(postgres_repo: PostgresEventRepository) -> None:
    assert postgres_repo.get("EV999") is None


def test_update_persists_state_transition(
    postgres_repo: PostgresEventRepository,
) -> None:
    event = Event.create(
        "EV001",
        "Live show",
        "San khau Trung tam",
        "2026-10-01T20:00:00",
        [TicketType("STANDARD", 300000)],
    )
    postgres_repo.add(event)

    event.status = EventStatus.ON_SALE
    postgres_repo.update(event)

    fetched = postgres_repo.get("EV001")
    assert fetched is not None
    assert fetched.status == EventStatus.ON_SALE
    # ticket_types khong bi dong toi boi update() nhu da thiet ke.
    assert [t.type for t in fetched.ticket_types] == ["STANDARD"]


def test_data_survives_new_engine_connection(
    postgres_repo: PostgresEventRepository,
) -> None:
    """Khac biet cot loi so voi InMemoryEventRepository: du lieu phai con
    nguyen khi mo mot ket noi/engine hoan toan moi (mo phong service
    restart)."""
    from app.infrastructure.database.session import dispose_engine

    postgres_repo.add(
        Event.create(
            "EV001",
            "Ton tai sau restart",
            "Dia diem A",
            "2026-11-01T19:00:00",
            [TicketType("VIP", 1000000)],
        )
    )

    dispose_engine()  # dong het connection pool hien tai

    fresh_repo = PostgresEventRepository()
    fetched = fresh_repo.get("EV001")
    assert fetched is not None
    assert fetched.name == "Ton tai sau restart"
    assert len(fetched.ticket_types) == 1


def test_list_all_returns_every_event_with_its_own_ticket_types(
    postgres_repo: PostgresEventRepository,
) -> None:
    postgres_repo.add(
        Event.create(
            "EV001",
            "A",
            "Dia diem A",
            "2026-08-01T19:00:00",
            [TicketType("VIP", 1000000)],
        )
    )
    postgres_repo.add(
        Event.create(
            "EV002",
            "B",
            "Dia diem B",
            "2026-08-02T19:00:00",
            [TicketType("STANDARD", 200000), TicketType("VIP", 900000)],
        )
    )

    events = {e.id: e for e in postgres_repo.list_all()}
    assert set(events) == {"EV001", "EV002"}
    assert len(events["EV001"].ticket_types) == 1
    assert len(events["EV002"].ticket_types) == 2


def test_cascade_delete_removes_ticket_types_with_event(
    postgres_repo: PostgresEventRepository,
) -> None:
    """ticket_types.event_id co ON DELETE CASCADE - xoa truc tiep o tang
    SQL phai keo theo xoa het ticket_types con lai (repository hien tai
    khong co use case delete(), nhung migration phai dam bao rang buoc
    nay dung cho tuong lai / thao tac thu cong)."""
    from sqlalchemy import text

    from app.infrastructure.database.session import session_scope

    postgres_repo.add(
        Event.create(
            "EV001",
            "Se bi xoa",
            "Dia diem X",
            "2026-12-01T19:00:00",
            [TicketType("VIP", 500000)],
        )
    )

    with session_scope() as session:
        session.execute(text("DELETE FROM event.events WHERE id = 'EV001'"))

    with session_scope() as session:
        remaining = session.execute(
            text("SELECT count(*) FROM event.ticket_types WHERE event_id = 'EV001'")
        ).scalar_one()
    assert remaining == 0
