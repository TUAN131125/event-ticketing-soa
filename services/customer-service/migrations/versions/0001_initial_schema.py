"""Initial schema - customer schema, id sequence, bang customers

Revision ID: 0001
Revises:
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS customer")
    op.execute("CREATE SEQUENCE IF NOT EXISTS customer.customer_id_seq START 1")

    op.create_table(
        "customers",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("phone", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="customer",
    )
    # Ghi chu: sa.Column(..., unique=True) o tren da tu tao unique
    # constraint "customers_email_key" - khong can tao them index rieng.

    # Seed C001 de giu tuong thich voi ban InMemory truoc day (customer
    # demo dung trong Postman collection / test thu cong).
    op.execute(
        """
        INSERT INTO customer.customers (id, name, email, phone, status, created_at)
        VALUES ('C001', 'Nguyen Van An', 'an@example.com', '0901234567', 'ACTIVE', now())
        ON CONFLICT (id) DO NOTHING
        """
    )
    # Dam bao sequence khong sinh trung C001 da seed thu cong o tren.
    op.execute("SELECT setval('customer.customer_id_seq', 1, true)")


def downgrade() -> None:
    op.drop_table("customers", schema="customer")
    op.execute("DROP SEQUENCE IF EXISTS customer.customer_id_seq")
    op.execute("DROP SCHEMA IF EXISTS customer CASCADE")
