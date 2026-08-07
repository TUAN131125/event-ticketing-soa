"""Bound reconciliation jobs by a deadline and lease them to one worker replica.

Revision ID: 0002_reconciliation_lease
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_reconciliation_lease"
down_revision = "0001_esb_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reconciliation_job",
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "reconciliation_job",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "reconciliation_job",
        sa.Column("extension_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_reconciliation_claimable",
        "reconciliation_job",
        ["state", "next_attempt_at", "locked_until"],
    )


def downgrade() -> None:
    op.drop_index("ix_reconciliation_claimable", table_name="reconciliation_job")
    op.drop_column("reconciliation_job", "extension_count")
    op.drop_column("reconciliation_job", "locked_until")
    op.drop_column("reconciliation_job", "deadline_at")
