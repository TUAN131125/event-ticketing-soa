"""Add UNKNOWN reconciliation, booking evidence and provider callback ledger.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payments", sa.Column("method_fingerprint", sa.String(64)), schema="payment"
    )
    op.add_column(
        "payments",
        sa.Column(
            "provider_scenario",
            sa.String(20),
            nullable=False,
            server_default="MANUAL",
        ),
        schema="payment",
    )
    op.add_column(
        "payments", sa.Column("booking_evidence_version", sa.BigInteger()), schema="payment"
    )
    op.add_column(
        "payments", sa.Column("booking_evidence_id", sa.String(128)), schema="payment"
    )
    op.add_column(
        "payments",
        sa.Column(
            "booking_evidence_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema="payment",
    )
    op.add_column(
        "payments", sa.Column("last_stable_status", sa.String(30)), schema="payment"
    )
    op.add_column(
        "payments", sa.Column("pending_operation", sa.String(20)), schema="payment"
    )
    op.add_column(
        "payments",
        sa.Column(
            "reconciliation_status",
            sa.String(20),
            nullable=False,
            server_default="NOT_REQUIRED",
        ),
        schema="payment",
    )
    op.add_column(
        "payments",
        sa.Column(
            "reconciliation_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        schema="payment",
    )
    op.add_column(
        "payments", sa.Column("reconciliation_error", sa.Text()), schema="payment"
    )
    op.add_column(
        "payments",
        sa.Column("unknown_since", sa.DateTime(timezone=True)),
        schema="payment",
    )
    op.add_column(
        "payments",
        sa.Column("reconciliation_due_at", sa.DateTime(timezone=True)),
        schema="payment",
    )
    op.add_column(
        "payments",
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True)),
        schema="payment",
    )

    op.drop_constraint("ck_payment_status", "payments", schema="payment", type_="check")
    op.drop_constraint(
        "ck_payment_state_consistency", "payments", schema="payment", type_="check"
    )
    op.create_check_constraint(
        "ck_payment_status",
        "payments",
        "status IN ('PENDING','AUTHORIZED','CAPTURED','UNKNOWN','FAILED',"
        "'CANCELLED','PARTIALLY_REFUNDED','REFUNDED')",
        schema="payment",
    )
    op.create_check_constraint(
        "ck_payment_provider_scenario",
        "payments",
        "provider_scenario IN ('MANUAL','SUCCESS','DECLINE','TIMEOUT')",
        schema="payment",
    )
    op.create_check_constraint(
        "ck_payment_reconciliation_status",
        "payments",
        "reconciliation_status IN "
        "('NOT_REQUIRED','PENDING','IN_PROGRESS','COMPLETED','FAILED')",
        schema="payment",
    )
    op.create_check_constraint(
        "ck_payment_pending_operation",
        "payments",
        "pending_operation IS NULL OR pending_operation IN "
        "('AUTHORIZE','CAPTURE','CANCEL','REFUND')",
        schema="payment",
    )
    op.create_check_constraint(
        "ck_payment_reconciliation_attempts",
        "payments",
        "reconciliation_attempts >= 0",
        schema="payment",
    )
    op.create_check_constraint(
        "ck_payment_unknown_evidence",
        "payments",
        "(status = 'UNKNOWN' AND last_stable_status IS NOT NULL "
        "AND pending_operation IS NOT NULL AND unknown_since IS NOT NULL "
        "AND reconciliation_status IN ('PENDING','IN_PROGRESS','FAILED')) OR "
        "(status <> 'UNKNOWN' AND last_stable_status IS NULL "
        "AND pending_operation IS NULL AND unknown_since IS NULL)",
        schema="payment",
    )
    op.create_check_constraint(
        "ck_payment_state_consistency",
        "payments",
        "(status = 'PENDING' AND captured_amount = 0 AND refunded_amount = 0) OR "
        "(status = 'AUTHORIZED' AND provider_reference IS NOT NULL "
        "AND authorized_at IS NOT NULL AND captured_amount = 0 "
        "AND refunded_amount = 0) OR "
        "(status = 'CAPTURED' AND provider_reference IS NOT NULL "
        "AND captured_at IS NOT NULL AND captured_amount = amount "
        "AND refunded_amount = 0) OR "
        "(status = 'UNKNOWN') OR "
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
        schema="payment",
    )
    op.create_index(
        "ix_payment_reconciliation_due",
        "payments",
        ["reconciliation_due_at"],
        schema="payment",
        postgresql_where=sa.text("status = 'UNKNOWN'"),
    )

    op.create_table(
        "provider_events",
        sa.Column("event_id", sa.String(128), primary_key=True),
        sa.Column("payment_id", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("provider_status", sa.String(30), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("provider_reference", sa.String(128)),
        sa.Column("provider_refund_reference", sa.String(128)),
        sa.Column("amount", sa.Numeric(18, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("observed_refunded_amount", sa.Numeric(18, 2)),
        sa.Column("failure_code", sa.String(128)),
        sa.Column("reason", sa.Text()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "operation IN ('AUTHORIZE','CAPTURE','CANCEL','REFUND')",
            name="ck_provider_event_operation",
        ),
        sa.CheckConstraint(
            "provider_status IN ('PENDING','AUTHORIZED','CAPTURED','UNKNOWN',"
            "'FAILED','CANCELLED','PARTIALLY_REFUNDED','REFUNDED')",
            name="ck_provider_event_status",
        ),
        sa.CheckConstraint(
            "source IN ('COMMAND','CALLBACK','RECONCILIATION','MOCK_PROVIDER')",
            name="ck_provider_event_source",
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"], ["payment.payments.payment_id"], ondelete="RESTRICT"
        ),
        schema="payment",
    )
    op.create_index(
        "ix_provider_event_payment_time",
        "provider_events",
        ["payment_id", "occurred_at"],
        schema="payment",
    )
    op.create_index(
        "ix_provider_event_reference",
        "provider_events",
        ["provider", "provider_reference"],
        schema="payment",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_event_reference", table_name="provider_events", schema="payment"
    )
    op.drop_index(
        "ix_provider_event_payment_time", table_name="provider_events", schema="payment"
    )
    op.drop_table("provider_events", schema="payment")
    op.drop_index(
        "ix_payment_reconciliation_due", table_name="payments", schema="payment"
    )
    op.drop_constraint(
        "ck_payment_unknown_evidence", "payments", schema="payment", type_="check"
    )
    op.drop_constraint(
        "ck_payment_reconciliation_attempts",
        "payments",
        schema="payment",
        type_="check",
    )
    op.drop_constraint(
        "ck_payment_pending_operation", "payments", schema="payment", type_="check"
    )
    op.drop_constraint(
        "ck_payment_reconciliation_status",
        "payments",
        schema="payment",
        type_="check",
    )
    op.drop_constraint(
        "ck_payment_provider_scenario", "payments", schema="payment", type_="check"
    )
    op.drop_constraint(
        "ck_payment_state_consistency", "payments", schema="payment", type_="check"
    )
    op.drop_constraint("ck_payment_status", "payments", schema="payment", type_="check")
    op.create_check_constraint(
        "ck_payment_status",
        "payments",
        "status IN ('PENDING','AUTHORIZED','CAPTURED','FAILED','CANCELLED',"
        "'PARTIALLY_REFUNDED','REFUNDED')",
        schema="payment",
    )
    op.create_check_constraint(
        "ck_payment_state_consistency",
        "payments",
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
        schema="payment",
    )
    for column in (
        "last_reconciled_at",
        "reconciliation_due_at",
        "unknown_since",
        "reconciliation_error",
        "reconciliation_attempts",
        "reconciliation_status",
        "pending_operation",
        "last_stable_status",
        "booking_evidence_verified",
        "booking_evidence_id",
        "booking_evidence_version",
        "provider_scenario",
        "method_fingerprint",
    ):
        op.drop_column("payments", column, schema="payment")
