"""Create the authoritative booking schema.

Revision ID: 0001
Revises:
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS booking")
    op.execute("CREATE SEQUENCE booking.booking_id_seq START WITH 1")

    op.create_table(
        "bookings",
        sa.Column("booking_id", sa.String(32), primary_key=True),
        sa.Column("customer_id", sa.String(128), nullable=False),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("reservation_id", sa.String(128), nullable=False),
        sa.Column("payment_method", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("payment_status", sa.String(20), nullable=False),
        sa.Column("total_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("payment_id", sa.String(128), nullable=True),
        sa.Column("failure_code", sa.String(128), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("resource_version", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING','CONFIRMED','FAILED','CANCELLED')",
            name="ck_booking_status",
        ),
        sa.CheckConstraint(
            "payment_status IN ('PENDING','SUCCEEDED','FAILED','REFUNDED')",
            name="ck_booking_payment_status",
        ),
        sa.CheckConstraint("total_amount >= 0", name="ck_booking_total_amount"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_booking_currency"),
        sa.CheckConstraint("resource_version >= 1", name="ck_booking_version"),
        sa.CheckConstraint(
            "(status = 'PENDING' AND payment_status = 'PENDING' "
            "AND payment_id IS NULL) OR "
            "(status = 'CONFIRMED' AND payment_status = 'SUCCEEDED' "
            "AND payment_id IS NOT NULL AND confirmed_at IS NOT NULL) OR "
            "(status = 'FAILED' AND payment_status = 'FAILED' "
            "AND failure_code IS NOT NULL AND failure_reason IS NOT NULL) OR "
            "(status = 'CANCELLED' AND cancellation_reason IS NOT NULL "
            "AND cancelled_at IS NOT NULL "
            "AND payment_status IN ('PENDING','FAILED','REFUNDED'))",
            name="ck_booking_state_consistency",
        ),
        sa.UniqueConstraint("reservation_id", name="uq_booking_reservation"),
        schema="booking",
    )
    op.create_index(
        "ix_booking_customer_created",
        "bookings",
        ["customer_id", "created_at"],
        schema="booking",
    )
    op.create_index(
        "ix_booking_event_status",
        "bookings",
        ["event_id", "status"],
        schema="booking",
    )
    op.create_index(
        "ix_booking_status_created",
        "bookings",
        ["status", "created_at"],
        schema="booking",
    )

    op.create_table(
        "booking_items",
        sa.Column("booking_id", sa.String(32), nullable=False),
        sa.Column("seat_id", sa.String(128), nullable=False),
        sa.Column("ticket_type", sa.String(128), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint("unit_price >= 0", name="ck_booking_item_price"),
        sa.ForeignKeyConstraint(
            ["booking_id"],
            ["booking.bookings.booking_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("booking_id", "seat_id"),
        schema="booking",
    )

    op.create_table(
        "idempotency_records",
        sa.Column("scope", sa.String(80), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("response_body", postgresql.JSONB(), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status = 'COMPLETED'", name="ck_booking_idempotency_status"
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_booking_idempotency_expiry"
        ),
        sa.PrimaryKeyConstraint("scope", "idempotency_key"),
        schema="booking",
    )
    op.create_index(
        "ix_booking_idempotency_expiry",
        "idempotency_records",
        ["expires_at"],
        schema="booking",
    )

    op.create_table(
        "booking_audit",
        sa.Column("audit_id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("booking_id", sa.String(32), nullable=False),
        sa.Column("operation", sa.String(80), nullable=False),
        sa.Column("previous_status", sa.String(20), nullable=True),
        sa.Column("new_status", sa.String(20), nullable=False),
        sa.Column("caller_service", sa.String(128), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=True),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("resource_version", sa.BigInteger(), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint("resource_version >= 1", name="ck_booking_audit_version"),
        sa.UniqueConstraint(
            "booking_id", "resource_version", name="uq_booking_audit_version"
        ),
        schema="booking",
    )
    op.create_index(
        "ix_booking_audit_booking_time",
        "booking_audit",
        ["booking_id", "occurred_at"],
        schema="booking",
    )
    op.create_index(
        "ix_booking_audit_correlation",
        "booking_audit",
        ["correlation_id"],
        schema="booking",
    )

    op.create_table(
        "outbox_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("aggregate_id", sa.String(32), nullable=False),
        sa.Column(
            "aggregate_type", sa.String(40), nullable=False, server_default="Booking"
        ),
        sa.Column("aggregate_version", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publish_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint("aggregate_version >= 1", name="ck_booking_outbox_version"),
        sa.CheckConstraint("publish_attempts >= 0", name="ck_booking_outbox_attempts"),
        sa.UniqueConstraint(
            "aggregate_id",
            "aggregate_version",
            name="uq_booking_outbox_aggregate_version",
        ),
        schema="booking",
    )
    op.create_index(
        "ix_booking_outbox_unpublished",
        "outbox_events",
        ["occurred_at"],
        unique=False,
        schema="booking",
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("outbox_events", schema="booking")
    op.drop_table("booking_audit", schema="booking")
    op.drop_table("idempotency_records", schema="booking")
    op.drop_table("booking_items", schema="booking")
    op.drop_table("bookings", schema="booking")
    op.execute("DROP SEQUENCE IF EXISTS booking.booking_id_seq")
