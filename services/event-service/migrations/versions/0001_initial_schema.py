"""Initial schema - event schema, events/ticket_types/event_audit/
idempotency_keys, khop OpenAPI Giai doan 5 (venue/startsAt/saleStartsAt/
saleEndsAt/resourceVersion, Money cho ticket type, audit va idempotency).

Revision ID: 0001
Revises:
Create Date: 2026-08-04
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
        sa.Column("venue", sa.String(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sale_starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sale_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="DRAFT"),
        sa.Column("resource_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="event",
    )

    op.create_table(
        "ticket_types",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "event_id", sa.String(),
            sa.ForeignKey("event.events.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="VND"),
        schema="event",
    )
    op.create_index(
        "ix_event_ticket_types_event_id", "ticket_types", ["event_id"], schema="event"
    )

    op.create_table(
        "event_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        schema="event",
    )
    op.create_index(
        "ix_event_event_audit_event_id", "event_audit", ["event_id"], schema="event"
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("scope", sa.String(), primary_key=True),
        sa.Column("request_hash", sa.String(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="event",
    )

    # Seed EV001 (ON_SALE san) de tuong thich voi du lieu demo/Postman cu.
    op.execute(
        """
        INSERT INTO event.events
            (id, name, venue, starts_at, sale_starts_at, sale_ends_at,
             status, resource_version, created_at)
        VALUES (
            'EV001', 'Dem nhac mua he', 'Nha hat Thanh pho',
            '2026-08-20T19:30:00+07:00', '2026-07-01T00:00:00+07:00',
            '2026-08-20T18:00:00+07:00', 'ON_SALE', 1, now()
        )
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO event.ticket_types (event_id, code, name, amount_minor, currency)
        SELECT 'EV001', v.code, v.name, v.amount_minor, 'VND'
        FROM (VALUES
            ('VIP', 'Ve VIP', 1500000),
            ('STANDARD', 'Ve Standard', 500000)
        ) AS v(code, name, amount_minor)
        WHERE NOT EXISTS (
            SELECT 1 FROM event.ticket_types WHERE event_id = 'EV001'
        )
        """
    )
    op.execute("SELECT setval('event.event_id_seq', 1, true)")


def downgrade() -> None:
    op.drop_table("idempotency_keys", schema="event")
    op.drop_table("event_audit", schema="event")
    op.drop_table("ticket_types", schema="event")
    op.drop_table("events", schema="event")
    op.execute("DROP SEQUENCE IF EXISTS event.event_id_seq")
    op.execute("DROP SCHEMA IF EXISTS event CASCADE")
