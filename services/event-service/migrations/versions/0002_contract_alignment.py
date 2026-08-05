"""Align Event persistence with the canonical contract.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("events", "location", new_column_name="venue", schema="event")
    op.alter_column("events", "start_time", new_column_name="starts_at", schema="event")
    op.execute(
        "ALTER TABLE event.events ALTER COLUMN starts_at TYPE timestamptz "
        "USING starts_at::timestamptz"
    )
    op.add_column(
        "events",
        sa.Column("sale_starts_at", sa.DateTime(timezone=True)),
        schema="event",
    )
    op.add_column(
        "events", sa.Column("sale_ends_at", sa.DateTime(timezone=True)), schema="event"
    )
    op.add_column(
        "events",
        sa.Column("resource_version", sa.Integer(), server_default="1", nullable=False),
        schema="event",
    )
    op.add_column(
        "events",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="event",
    )
    op.execute(
        "UPDATE event.events SET sale_starts_at = now() - interval '1 day', "
        "sale_ends_at = starts_at - interval '1 hour'"
    )
    op.alter_column("events", "sale_starts_at", nullable=False, schema="event")
    op.alter_column("events", "sale_ends_at", nullable=False, schema="event")
    op.alter_column("ticket_types", "type", new_column_name="code", schema="event")
    op.alter_column(
        "ticket_types", "price", new_column_name="amount_minor", schema="event"
    )
    op.add_column("ticket_types", sa.Column("name", sa.String()), schema="event")
    op.add_column(
        "ticket_types",
        sa.Column("currency", sa.String(), server_default="VND", nullable=False),
        schema="event",
    )
    op.execute("UPDATE event.ticket_types SET name = code")
    op.alter_column("ticket_types", "name", nullable=False, schema="event")


def downgrade() -> None:
    op.drop_column("ticket_types", "currency", schema="event")
    op.drop_column("ticket_types", "name", schema="event")
    op.alter_column(
        "ticket_types", "amount_minor", new_column_name="price", schema="event"
    )
    op.alter_column("ticket_types", "code", new_column_name="type", schema="event")
    op.drop_column("events", "updated_at", schema="event")
    op.drop_column("events", "resource_version", schema="event")
    op.drop_column("events", "sale_ends_at", schema="event")
    op.drop_column("events", "sale_starts_at", schema="event")
    op.execute(
        "ALTER TABLE event.events ALTER COLUMN starts_at TYPE varchar "
        "USING starts_at::text"
    )
    op.alter_column("events", "starts_at", new_column_name="start_time", schema="event")
    op.alter_column("events", "venue", new_column_name="location", schema="event")
