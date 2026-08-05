"""Allow canonical UNKNOWN payment state.

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
    op.alter_column(
        "payments",
        "payment_method",
        type_=sa.String(200),
        existing_type=sa.String(40),
        schema="payment",
    )
    op.drop_constraint("ck_payment_status", "payments", schema="payment", type_="check")
    op.create_check_constraint(
        "ck_payment_status",
        "payments",
        "status IN ('PENDING','AUTHORIZED','CAPTURED','FAILED','CANCELLED','PARTIALLY_REFUNDED','REFUNDED','UNKNOWN')",
        schema="payment",
    )


def downgrade() -> None:
    op.execute("UPDATE payment.payments SET status = 'FAILED' WHERE status = 'UNKNOWN'")
    op.drop_constraint("ck_payment_status", "payments", schema="payment", type_="check")
    op.create_check_constraint(
        "ck_payment_status",
        "payments",
        "status IN ('PENDING','AUTHORIZED','CAPTURED','FAILED','CANCELLED','PARTIALLY_REFUNDED','REFUNDED')",
        schema="payment",
    )
    op.alter_column(
        "payments",
        "payment_method",
        type_=sa.String(40),
        existing_type=sa.String(200),
        schema="payment",
    )
