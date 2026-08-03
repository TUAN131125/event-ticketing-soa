"""Create the authoritative ticket schema.

Revision ID: 0001
Revises:
Create Date: 2026-08-03
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
    op.execute("CREATE SCHEMA IF NOT EXISTS ticket")
    op.execute("CREATE SEQUENCE ticket.ticket_id_seq START WITH 1")

    op.create_table(
        "tickets",
        sa.Column("ticket_id", sa.String(32), primary_key=True),
        sa.Column("booking_id", sa.String(128), nullable=False),
        sa.Column("customer_id", sa.String(128), nullable=False),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("payment_id", sa.String(128), nullable=False),
        sa.Column("seat_id", sa.String(128), nullable=False),
        sa.Column("seat_label", sa.String(128), nullable=False),
        sa.Column("ticket_type", sa.String(128), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("qr_version", sa.Integer(), nullable=False),
        sa.Column("resource_version", sa.BigInteger(), nullable=False),
        sa.Column(
            "issued_at",
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
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_in_gate_id", sa.String(128), nullable=True),
        sa.Column("checked_in_by", sa.String(128), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('VALID','CHECKED_IN','CANCELLED')",
            name="ck_ticket_status",
        ),
        sa.CheckConstraint("qr_version >= 1", name="ck_ticket_qr_version"),
        sa.CheckConstraint("resource_version >= 1", name="ck_ticket_version"),
        sa.CheckConstraint(
            "(status = 'VALID' AND checked_in_at IS NULL "
            "AND checked_in_gate_id IS NULL AND checked_in_by IS NULL "
            "AND cancelled_at IS NULL AND cancellation_reason IS NULL) OR "
            "(status = 'CHECKED_IN' AND checked_in_at IS NOT NULL "
            "AND checked_in_gate_id IS NOT NULL AND checked_in_by IS NOT NULL "
            "AND cancelled_at IS NULL AND cancellation_reason IS NULL) OR "
            "(status = 'CANCELLED' AND checked_in_at IS NULL "
            "AND checked_in_gate_id IS NULL AND checked_in_by IS NULL "
            "AND cancelled_at IS NOT NULL AND cancellation_reason IS NOT NULL)",
            name="ck_ticket_state_consistency",
        ),
        sa.UniqueConstraint("booking_id", "seat_id", name="uq_ticket_booking_seat"),
        schema="ticket",
    )
    op.create_index(
        "uq_ticket_active_event_seat",
        "tickets",
        ["event_id", "seat_id"],
        unique=True,
        schema="ticket",
        postgresql_where=sa.text("status <> 'CANCELLED'"),
    )
    op.create_index(
        "ix_ticket_booking", "tickets", ["booking_id", "ticket_id"], schema="ticket"
    )
    op.create_index(
        "ix_ticket_customer_issued",
        "tickets",
        ["customer_id", "issued_at"],
        schema="ticket",
    )
    op.create_index(
        "ix_ticket_event_status",
        "tickets",
        ["event_id", "status"],
        schema="ticket",
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
        sa.CheckConstraint("status = 'COMPLETED'", name="ck_ticket_idempotency_status"),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_ticket_idempotency_expiry"
        ),
        sa.PrimaryKeyConstraint("scope", "idempotency_key"),
        schema="ticket",
    )
    op.create_index(
        "ix_ticket_idempotency_expiry",
        "idempotency_records",
        ["expires_at"],
        schema="ticket",
    )

    op.create_table(
        "ticket_audit",
        sa.Column("audit_id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("ticket_id", sa.String(32), nullable=False),
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
        sa.CheckConstraint("resource_version >= 1", name="ck_ticket_audit_version"),
        sa.UniqueConstraint(
            "ticket_id", "resource_version", name="uq_ticket_audit_version"
        ),
        schema="ticket",
    )
    op.create_index(
        "ix_ticket_audit_ticket_time",
        "ticket_audit",
        ["ticket_id", "occurred_at"],
        schema="ticket",
    )
    op.create_index(
        "ix_ticket_audit_correlation",
        "ticket_audit",
        ["correlation_id"],
        schema="ticket",
    )

    op.create_table(
        "outbox_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("aggregate_id", sa.String(32), nullable=False),
        sa.Column(
            "aggregate_type", sa.String(40), nullable=False, server_default="Ticket"
        ),
        sa.Column("aggregate_version", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publish_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint("aggregate_version >= 1", name="ck_ticket_outbox_version"),
        sa.CheckConstraint("publish_attempts >= 0", name="ck_ticket_outbox_attempts"),
        sa.UniqueConstraint(
            "aggregate_id",
            "aggregate_version",
            name="uq_ticket_outbox_aggregate_version",
        ),
        schema="ticket",
    )
    op.create_index(
        "ix_ticket_outbox_unpublished",
        "outbox_events",
        ["occurred_at"],
        schema="ticket",
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("outbox_events", schema="ticket")
    op.drop_table("ticket_audit", schema="ticket")
    op.drop_table("idempotency_records", schema="ticket")
    op.drop_table("tickets", schema="ticket")
    op.execute("DROP SEQUENCE IF EXISTS ticket.ticket_id_seq")
