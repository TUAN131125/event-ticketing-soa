"""Create the authoritative payment schema.

Revision ID: 0001
Revises:
Create Date: 2026-08-02
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
    op.execute("CREATE SCHEMA IF NOT EXISTS payment")
    op.execute("CREATE SEQUENCE payment.payment_id_seq START WITH 1")
    op.execute("CREATE SEQUENCE payment.refund_id_seq START WITH 1")

    op.create_table(
        "payments",
        sa.Column("payment_id", sa.String(32), primary_key=True),
        sa.Column("booking_id", sa.String(128), nullable=False),
        sa.Column("customer_id", sa.String(128), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("payment_method", sa.String(40), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("provider_reference", sa.String(128), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("captured_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("refunded_amount", sa.Numeric(18, 2), nullable=False),
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
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING','AUTHORIZED','CAPTURED','FAILED','CANCELLED',"
            "'PARTIALLY_REFUNDED','REFUNDED')",
            name="ck_payment_status",
        ),
        sa.CheckConstraint("amount > 0", name="ck_payment_amount"),
        sa.CheckConstraint("captured_amount >= 0", name="ck_payment_captured_amount"),
        sa.CheckConstraint("refunded_amount >= 0", name="ck_payment_refunded_amount"),
        sa.CheckConstraint(
            "captured_amount <= amount", name="ck_payment_captured_limit"
        ),
        sa.CheckConstraint(
            "refunded_amount <= captured_amount", name="ck_payment_refunded_limit"
        ),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_payment_currency"),
        sa.CheckConstraint("resource_version >= 1", name="ck_payment_version"),
        sa.CheckConstraint(
            "(status = 'PENDING' AND captured_amount = 0 AND refunded_amount = 0) OR "
            "(status = 'AUTHORIZED' AND provider_reference IS NOT NULL "
            "AND authorized_at IS NOT NULL AND captured_amount = 0 "
            "AND refunded_amount = 0) OR "
            "(status = 'CAPTURED' AND provider_reference IS NOT NULL "
            "AND captured_at IS NOT NULL AND captured_amount = amount "
            "AND refunded_amount = 0) OR "
            "(status = 'FAILED' AND failure_code IS NOT NULL "
            "AND failure_reason IS NOT NULL AND captured_amount = 0 "
            "AND refunded_amount = 0) OR "
            "(status = 'CANCELLED' AND cancellation_reason IS NOT NULL "
            "AND cancelled_at IS NOT NULL AND captured_amount = 0 "
            "AND refunded_amount = 0) OR "
            "(status = 'PARTIALLY_REFUNDED' AND captured_amount = amount "
            "AND refunded_amount > 0 AND refunded_amount < amount) OR "
            "(status = 'REFUNDED' AND captured_amount = amount "
            "AND refunded_amount = amount AND refunded_at IS NOT NULL)",
            name="ck_payment_state_consistency",
        ),
        sa.UniqueConstraint("booking_id", name="uq_payment_booking"),
        sa.UniqueConstraint(
            "provider", "provider_reference", name="uq_payment_provider_reference"
        ),
        schema="payment",
    )
    op.create_index(
        "ix_payment_customer_created",
        "payments",
        ["customer_id", "created_at"],
        schema="payment",
    )
    op.create_index(
        "ix_payment_status_created",
        "payments",
        ["status", "created_at"],
        schema="payment",
    )
    op.create_index(
        "ix_payment_provider_status",
        "payments",
        ["provider", "status"],
        schema="payment",
    )

    op.create_table(
        "refunds",
        sa.Column("refund_id", sa.String(32), primary_key=True),
        sa.Column("payment_id", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("provider_reference", sa.String(128), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint("amount > 0", name="ck_refund_amount"),
        sa.CheckConstraint(
            "kind IN ('REQUESTED','RECONCILIATION')", name="ck_refund_kind"
        ),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_refund_currency"),
        sa.ForeignKeyConstraint(
            ["payment_id"], ["payment.payments.payment_id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "payment_id", "idempotency_key", name="uq_refund_payment_key"
        ),
        sa.UniqueConstraint(
            "provider", "provider_reference", name="uq_refund_provider_reference"
        ),
        schema="payment",
    )
    op.create_index(
        "ix_refund_payment_created",
        "refunds",
        ["payment_id", "created_at"],
        schema="payment",
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
            "status = 'COMPLETED'", name="ck_payment_idempotency_status"
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_payment_idempotency_expiry"
        ),
        sa.PrimaryKeyConstraint("scope", "idempotency_key"),
        schema="payment",
    )
    op.create_index(
        "ix_payment_idempotency_expiry",
        "idempotency_records",
        ["expires_at"],
        schema="payment",
    )

    op.create_table(
        "payment_audit",
        sa.Column("audit_id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("payment_id", sa.String(32), nullable=False),
        sa.Column("operation", sa.String(80), nullable=False),
        sa.Column("previous_status", sa.String(30), nullable=True),
        sa.Column("new_status", sa.String(30), nullable=False),
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
        sa.CheckConstraint("resource_version >= 1", name="ck_payment_audit_version"),
        sa.UniqueConstraint(
            "payment_id", "resource_version", name="uq_payment_audit_version"
        ),
        schema="payment",
    )
    op.create_index(
        "ix_payment_audit_payment_time",
        "payment_audit",
        ["payment_id", "occurred_at"],
        schema="payment",
    )
    op.create_index(
        "ix_payment_audit_correlation",
        "payment_audit",
        ["correlation_id"],
        schema="payment",
    )

    op.create_table(
        "outbox_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("aggregate_id", sa.String(32), nullable=False),
        sa.Column(
            "aggregate_type", sa.String(40), nullable=False, server_default="Payment"
        ),
        sa.Column("aggregate_version", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publish_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint("aggregate_version >= 1", name="ck_payment_outbox_version"),
        sa.CheckConstraint("publish_attempts >= 0", name="ck_payment_outbox_attempts"),
        sa.UniqueConstraint(
            "aggregate_id",
            "aggregate_version",
            name="uq_payment_outbox_aggregate_version",
        ),
        schema="payment",
    )
    op.create_index(
        "ix_payment_outbox_unpublished",
        "outbox_events",
        ["occurred_at"],
        unique=False,
        schema="payment",
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("outbox_events", schema="payment")
    op.drop_table("payment_audit", schema="payment")
    op.drop_table("idempotency_records", schema="payment")
    op.drop_table("refunds", schema="payment")
    op.drop_table("payments", schema="payment")
    op.execute("DROP SEQUENCE IF EXISTS payment.refund_id_seq")
    op.execute("DROP SEQUENCE IF EXISTS payment.payment_id_seq")
