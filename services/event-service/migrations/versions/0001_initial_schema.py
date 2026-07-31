"""Initial schema - event schema, id sequence, bang events va ticket_types

Revision ID: 0001
Revises:
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS event")
    op.execute("CREATE SEQUENCE IF NOT EXISTS event.event_id_seq START 1")

    op.create_table(
        "events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("location", sa.String(), nullable=False),
        sa.Column("start_time", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="event",
    )

    op.create_table(
        "ticket_types",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "event_id",
            sa.String(),
            sa.ForeignKey("event.events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        schema="event",
    )
    op.create_index(
        "ix_event_ticket_types_event_id",
        "ticket_types",
        ["event_id"],
        schema="event",
    )

    # Seed EV001 de giu tuong thich voi ban InMemory truoc day (event demo
    # dung trong Postman collection / test thu cong) - da ON_SALE san,
    # kem 2 loai ve VIP/STANDARD giong seed cu.
    op.execute(
        """
        INSERT INTO event.events (id, name, location, start_time, status, created_at)
        VALUES ('EV001', 'Dem nhac mua he', 'Nha hat Thanh pho',
                '2026-08-20T19:30:00', 'ON_SALE', now())
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO event.ticket_types (event_id, type, price)
        SELECT 'EV001', v.type, v.price
        FROM (VALUES ('VIP', 1500000), ('STANDARD', 500000)) AS v(type, price)
        WHERE NOT EXISTS (
            SELECT 1 FROM event.ticket_types WHERE event_id = 'EV001'
        )
        """
    )
    # Dam bao sequence khong sinh trung EV001 da seed thu cong o tren.
    op.execute("SELECT setval('event.event_id_seq', 1, true)")


def downgrade() -> None:
    op.drop_table("ticket_types", schema="event")
    op.drop_table("events", schema="event")
    op.execute("DROP SEQUENCE IF EXISTS event.event_id_seq")
    op.execute("DROP SCHEMA IF EXISTS event CASCADE")
