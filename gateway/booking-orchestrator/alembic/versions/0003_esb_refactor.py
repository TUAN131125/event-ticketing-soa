"""Create the v2 ESB persistence tables introduced by the orchestrator refactor.

Revision ID: 0003_esb_refactor
Revises: 0002_reconciliation_lease

The refactor replaced the per-aggregate relational model with three document tables that
app.persistence.repositories.PostgresRepository reads and writes directly. This revision
promotes migrations/versions/0002_esb_refactor.sql into the Alembic chain.

The pre-refactor tables (workflow, workflow_step, idempotency_record, trace_step,
outbox_message, reconciliation_job) are intentionally left in place. No code path in the
current runtime reads them, but they can hold in-flight state from a deployment that has
not yet been drained, so dropping them is not provably safe here. Removing them belongs
in a separate, explicitly sequenced cleanup revision.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_esb_refactor"
down_revision = "0002_reconciliation_lease"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "esb_workflows_v2",
        sa.Column("workflow_id", sa.String(64), primary_key=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("correlation_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index(
        "ix_esb_workflows_v2_correlation_id",
        "esb_workflows_v2",
        ["correlation_id"],
    )
    op.create_index("ix_esb_workflows_v2_status", "esb_workflows_v2", ["status"])

    op.create_table(
        "esb_outbox_v2",
        sa.Column("message_id", sa.String(64), primary_key=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("next_attempt_at", sa.Float(), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    # The relay claims work with `state = 'PENDING' AND next_attempt_at <= now`, so the
    # composite index is what keeps that scan bounded.
    op.create_index(
        "ix_esb_outbox_v2_due",
        "esb_outbox_v2",
        ["state", "next_attempt_at"],
    )

    op.create_table(
        "esb_ws_ticket_v2",
        sa.Column("cache_key", sa.String(256), primary_key=True),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index(
        "ix_esb_ws_ticket_v2_expires_at",
        "esb_ws_ticket_v2",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_esb_ws_ticket_v2_expires_at", table_name="esb_ws_ticket_v2")
    op.drop_table("esb_ws_ticket_v2")
    op.drop_index("ix_esb_outbox_v2_due", table_name="esb_outbox_v2")
    op.drop_table("esb_outbox_v2")
    op.drop_index("ix_esb_workflows_v2_status", table_name="esb_workflows_v2")
    op.drop_index("ix_esb_workflows_v2_correlation_id", table_name="esb_workflows_v2")
    op.drop_table("esb_workflows_v2")
