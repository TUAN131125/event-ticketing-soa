"""Bo sung contract compliance - resourceVersion/updatedAt cho optimistic
concurrency, bang consents, bang idempotency_records.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) resource_version + updated_at tren bang customers (optimistic
    # concurrency theo header If-Match trong contracts/openapi/
    # customer-service.yaml).
    op.add_column(
        "customers",
        sa.Column("resource_version", sa.Integer(), nullable=False, server_default="1"),
        schema="customer",
    )
    op.add_column(
        "customers",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        schema="customer",
    )
    # Backfill updated_at cho ban ghi da ton tai (vd C001 seed tu 0001)
    # bang chinh created_at cua no, roi moi dat NOT NULL.
    op.execute("UPDATE customer.customers SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column("customers", "updated_at", nullable=False, schema="customer")

    # 2) Bang consents - tai nguyen con cua customer, endpoint POST
    # /customers/{id}/consents.
    op.create_table(
        "consents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "customer_id",
            sa.String(),
            sa.ForeignKey("customer.customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("customer_id", "channel", name="uq_consent_customer_channel"),
        schema="customer",
    )

    # 3) Bang idempotency_records - luu response da xu ly theo
    # Idempotency-Key, dung cho POST/PUT/consents/deactivate.
    op.create_table(
        "idempotency_records",
        sa.Column("idempotency_key", sa.String(), primary_key=True),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="customer",
    )


def downgrade() -> None:
    op.drop_table("idempotency_records", schema="customer")
    op.drop_table("consents", schema="customer")
    op.drop_column("customers", "updated_at", schema="customer")
    op.drop_column("customers", "resource_version", schema="customer")
