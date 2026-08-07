"""Create durable ESB workflow state.

Revision ID: 0001_esb_state
"""

import sqlalchemy as sa

from alembic import op

revision = "0001_esb_state"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("public_operation", sa.String(80), nullable=False),
        sa.Column("authenticated_subject", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("phase", sa.String(40), nullable=False),
        sa.Column("booking_id", sa.String(128)),
        sa.Column("customer_id", sa.String(128)),
        sa.Column("reservation_id", sa.String(128)),
        sa.Column("reservation_version", sa.Integer()),
        sa.Column("payment_id", sa.String(128)),
        sa.Column("payment_status", sa.String(40)),
        sa.Column("ticket_ids", sa.JSON(), nullable=False),
        sa.Column("total", sa.JSON()),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_workflow_correlation_id", "workflow", ["correlation_id"])
    op.create_table(
        "workflow_step",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("workflow_id", sa.String(64), nullable=False),
        sa.Column("step", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("safe_details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_workflow_step_workflow_id", "workflow_step", ["workflow_id"])
    op.create_table(
        "idempotency_record",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("operation", sa.String(80), nullable=False),
        sa.Column("authenticated_subject", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("workflow_id", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer()),
        sa.Column("response_body", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("operation", "authenticated_subject", "idempotency_key", name="uq_idempotency_scope"),
    )
    op.create_table(
        "trace_step",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("service", sa.String(80), nullable=False),
        sa.Column("operation", sa.String(100), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trace_step_correlation_id", "trace_step", ["correlation_id"])
    op.create_table(
        "outbox_message",
        sa.Column("message_id", sa.String(64), primary_key=True),
        sa.Column("workflow_id", sa.String(64), nullable=False),
        sa.Column("destination", sa.String(40), nullable=False),
        sa.Column("message_type", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("last_error_code", sa.String(100)),
    )
    op.create_index("ix_outbox_message_workflow_id", "outbox_message", ["workflow_id"])
    op.create_table(
        "reconciliation_job",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workflow_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("last_evidence", sa.JSON(), nullable=False),
        sa.UniqueConstraint("workflow_id", "kind", "idempotency_key", name="uq_reconciliation_scope"),
    )
    op.create_index("ix_reconciliation_job_workflow_id", "reconciliation_job", ["workflow_id"])


def downgrade() -> None:
    for table in ("reconciliation_job", "outbox_message", "trace_step", "idempotency_record", "workflow_step", "workflow"):
        op.drop_table(table)
