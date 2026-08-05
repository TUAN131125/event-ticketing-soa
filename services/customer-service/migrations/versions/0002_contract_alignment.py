"""Add canonical Customer resource metadata and identity mappings.

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
    op.alter_column("customers", "phone", schema="customer", nullable=True)
    op.add_column(
        "customers",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="customer",
    )
    op.add_column(
        "customers",
        sa.Column("resource_version", sa.Integer(), server_default="1", nullable=False),
        schema="customer",
    )
    op.create_table(
        "customer_consents",
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customer.customers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("customer_id", "channel"),
        schema="customer",
    )
    op.create_table(
        "identity_mappings",
        sa.Column("identity_subject", sa.String(), primary_key=True),
        sa.Column("customer_id", sa.String(), nullable=False, unique=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("resource_version", sa.Integer(), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customer.customers.id"], ondelete="CASCADE"
        ),
        schema="customer",
    )


def downgrade() -> None:
    op.drop_table("identity_mappings", schema="customer")
    op.drop_table("customer_consents", schema="customer")
    op.drop_column("customers", "resource_version", schema="customer")
    op.drop_column("customers", "updated_at", schema="customer")
    op.alter_column("customers", "phone", schema="customer", nullable=False)
