"""Create authoritative Seat Inventory schema.

Revision ID: 0001
Revises:
Create Date: 2026-07-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None
SCHEMA = "seat"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "inventory_versions",
        sa.Column("event_id", sa.String(length=128), primary_key=True),
        sa.Column("inventory_version", sa.BigInteger(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "reservations",
        sa.Column("reservation_id", sa.String(length=36), primary_key=True),
        sa.Column("booking_id", sa.String(length=128), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("extend_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "resource_version", sa.BigInteger(), server_default="1", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','CONFIRMED','RELEASED','EXPIRED')",
            name="ck_reservation_status",
        ),
        sa.CheckConstraint("extend_count >= 0", name="ck_reservation_extend_count"),
        sa.UniqueConstraint("booking_id", name="uq_reservation_booking"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_reservations_status_expiry",
        "reservations",
        ["status", "expires_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_reservations_event_status",
        "reservations",
        ["event_id", "status"],
        schema=SCHEMA,
    )

    op.create_table(
        "seats",
        sa.Column("event_id", sa.String(length=128), primary_key=True),
        sa.Column("seat_id", sa.String(length=128), primary_key=True),
        sa.Column("section", sa.String(length=80), nullable=False),
        sa.Column("row_label", sa.String(length=40), nullable=False),
        sa.Column("seat_number", sa.String(length=40), nullable=False),
        sa.Column("ticket_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_reservation_id", sa.String(length=36), nullable=True),
        sa.Column(
            "resource_version", sa.BigInteger(), server_default="1", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('AVAILABLE','HELD','SOLD','BLOCKED')",
            name="ck_seat_status",
        ),
        sa.CheckConstraint(
            "(status = 'HELD' AND current_reservation_id IS NOT NULL) "
            "OR (status <> 'HELD' AND current_reservation_id IS NULL)",
            name="ck_seat_hold_owner",
        ),
        sa.ForeignKeyConstraint(
            ["current_reservation_id"],
            [f"{SCHEMA}.reservations.reservation_id"],
            name="fk_seat_current_reservation",
            ondelete="RESTRICT",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_seats_event_status",
        "seats",
        ["event_id", "status"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_seats_current_reservation",
        "seats",
        ["current_reservation_id"],
        unique=False,
        schema=SCHEMA,
        postgresql_where=sa.text("current_reservation_id IS NOT NULL"),
    )

    op.create_table(
        "reservation_items",
        sa.Column("reservation_id", sa.String(length=36), primary_key=True),
        sa.Column("event_id", sa.String(length=128), primary_key=True),
        sa.Column("seat_id", sa.String(length=128), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            [f"{SCHEMA}.reservations.reservation_id"],
            name="fk_reservation_item_reservation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "seat_id"],
            [f"{SCHEMA}.seats.event_id", f"{SCHEMA}.seats.seat_id"],
            name="fk_reservation_item_seat",
            ondelete="RESTRICT",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_reservation_items_event_seat",
        "reservation_items",
        ["event_id", "seat_id"],
        schema=SCHEMA,
    )

    op.create_table(
        "idempotency_records",
        sa.Column("scope", sa.String(length=80), primary_key=True),
        sa.Column("idempotency_key", sa.String(length=128), primary_key=True),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('COMPLETED')", name="ck_idempotency_status"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_idempotency_expiry",
        "idempotency_records",
        ["expires_at"],
        schema=SCHEMA,
    )

    op.create_table(
        "seat_audit",
        sa.Column("audit_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("seat_id", sa.String(length=128), nullable=True),
        sa.Column("reservation_id", sa.String(length=36), nullable=True),
        sa.Column("booking_id", sa.String(length=128), nullable=True),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("previous_status", sa.String(length=20), nullable=True),
        sa.Column("new_status", sa.String(length=20), nullable=True),
        sa.Column("reason_code", sa.String(length=80), nullable=True),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("caller_service", sa.String(length=128), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("resource_version", sa.BigInteger(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_seat_audit_correlation",
        "seat_audit",
        ["correlation_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_seat_audit_reservation_time",
        "seat_audit",
        ["reservation_id", "occurred_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_seat_audit_event_seat_time",
        "seat_audit",
        ["event_id", "seat_id", "occurred_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("seat_audit", schema=SCHEMA)
    op.drop_table("idempotency_records", schema=SCHEMA)
    op.drop_table("reservation_items", schema=SCHEMA)
    op.drop_table("seats", schema=SCHEMA)
    op.drop_table("reservations", schema=SCHEMA)
    op.drop_table("inventory_versions", schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
