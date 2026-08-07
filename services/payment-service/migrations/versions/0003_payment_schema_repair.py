"""Repair databases that applied an earlier edition of revision 0002.

Revision 0002 was rewritten after some environments had already applied it, so those
databases are stamped 0002 while missing everything the current 0002 adds: the
reconciliation/booking-evidence columns on ``payment.payments``, their check constraints,
the partial reconciliation index and the whole ``payment.provider_events`` ledger.
``database_ready`` requires ``provider_events``, so those databases never become ready.

Revision ID: 0003
Revises: 0002

This revision is additive and idempotent. It creates only what is genuinely absent, and it
never drops a table, a column or a row. Where an object exists but does not match what the
current schema requires, it raises rather than silently continuing — a wrong column type is
a condition a human must look at, not something a migration should paper over.

Downgrade is intentionally a no-op: everything here is also created by revision 0002, so
dropping it would corrupt a database that reached this state normally rather than by drift.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "payment"

# Exactly the columns the current revision 0002 adds to payment.payments.
PAYMENT_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    ("method_fingerprint", sa.Column("method_fingerprint", sa.String(64))),
    (
        "provider_scenario",
        sa.Column(
            "provider_scenario", sa.String(20), nullable=False, server_default="MANUAL"
        ),
    ),
    ("booking_evidence_version", sa.Column("booking_evidence_version", sa.BigInteger())),
    ("booking_evidence_id", sa.Column("booking_evidence_id", sa.String(128))),
    (
        "booking_evidence_verified",
        sa.Column(
            "booking_evidence_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    ),
    ("last_stable_status", sa.Column("last_stable_status", sa.String(30))),
    ("pending_operation", sa.Column("pending_operation", sa.String(20))),
    (
        "reconciliation_status",
        sa.Column(
            "reconciliation_status",
            sa.String(20),
            nullable=False,
            server_default="NOT_REQUIRED",
        ),
    ),
    (
        "reconciliation_attempts",
        sa.Column(
            "reconciliation_attempts", sa.Integer(), nullable=False, server_default="0"
        ),
    ),
    ("reconciliation_error", sa.Column("reconciliation_error", sa.Text())),
    ("unknown_since", sa.Column("unknown_since", sa.DateTime(timezone=True))),
    (
        "reconciliation_due_at",
        sa.Column("reconciliation_due_at", sa.DateTime(timezone=True)),
    ),
    ("last_reconciled_at", sa.Column("last_reconciled_at", sa.DateTime(timezone=True))),
)

PAYMENT_CHECKS: tuple[tuple[str, str], ...] = (
    (
        "ck_payment_provider_scenario",
        "provider_scenario IN ('MANUAL','SUCCESS','DECLINE','TIMEOUT')",
    ),
    (
        "ck_payment_reconciliation_status",
        "reconciliation_status IN "
        "('NOT_REQUIRED','PENDING','IN_PROGRESS','COMPLETED','FAILED')",
    ),
    (
        "ck_payment_pending_operation",
        "pending_operation IS NULL OR pending_operation IN "
        "('AUTHORIZE','CAPTURE','CANCEL','REFUND')",
    ),
    ("ck_payment_reconciliation_attempts", "reconciliation_attempts >= 0"),
    (
        "ck_payment_unknown_evidence",
        "(status = 'UNKNOWN' AND last_stable_status IS NOT NULL "
        "AND pending_operation IS NOT NULL AND unknown_since IS NOT NULL "
        "AND reconciliation_status IN ('PENDING','IN_PROGRESS','FAILED')) OR "
        "(status <> 'UNKNOWN' AND last_stable_status IS NULL "
        "AND pending_operation IS NULL AND unknown_since IS NULL)",
    ),
)


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _columns(table: str) -> dict[str, dict]:
    return {
        column["name"]: column
        for column in _inspector().get_columns(table, schema=SCHEMA)
    }


def _repair_payments_columns() -> None:
    existing = _columns("payments")
    for name, column in PAYMENT_COLUMNS:
        if name in existing:
            continue
        op.add_column("payments", column, schema=SCHEMA)


def _repair_payments_constraints() -> None:
    inspector = _inspector()
    present = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("payments", schema=SCHEMA)
    }
    for name, expression in PAYMENT_CHECKS:
        if name in present:
            continue
        op.create_check_constraint(name, "payments", expression, schema=SCHEMA)

    indexes = {index["name"] for index in inspector.get_indexes("payments", schema=SCHEMA)}
    if "ix_payment_reconciliation_due" not in indexes:
        op.create_index(
            "ix_payment_reconciliation_due",
            "payments",
            ["reconciliation_due_at"],
            schema=SCHEMA,
            postgresql_where=sa.text("status = 'UNKNOWN'"),
        )


def _create_provider_events() -> None:
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
        schema=SCHEMA,
    )
    op.create_index(
        "ix_provider_event_payment_time",
        "provider_events",
        ["payment_id", "occurred_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_provider_event_reference",
        "provider_events",
        ["provider", "provider_reference"],
        schema=SCHEMA,
    )


def _verify_provider_events() -> None:
    """An existing table must actually be the ledger the application expects."""
    required = {
        "event_id",
        "payment_id",
        "provider",
        "operation",
        "provider_status",
        "source",
        "payload_hash",
        "occurred_at",
        "received_at",
    }
    missing = sorted(required - set(_columns("provider_events")))
    if missing:
        raise RuntimeError(
            "payment.provider_events exists but is missing required columns: "
            + ", ".join(missing)
            + ". Resolve this by hand; this migration will not alter it blindly."
        )


def upgrade() -> None:
    _repair_payments_columns()
    _repair_payments_constraints()

    if "provider_events" in _inspector().get_table_names(schema=SCHEMA):
        _verify_provider_events()
    else:
        _create_provider_events()


def downgrade() -> None:
    """No-op on purpose.

    Every object this revision creates also belongs to revision 0002. Dropping them here
    would damage a database that arrived in this state through the normal chain, so the
    downgrade path deliberately leaves the schema alone.
    """
