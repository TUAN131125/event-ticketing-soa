"""SQLAlchemy ORM model - khop voi bang customers duoc tao trong
migrations/versions/. Day la nguon su that duy nhat cho cau truc bang
(khong con phu thuoc database/schemas/customer_schema.sql o repo goc,
file do van la placeholder o cap toan he thong - moi service tu quan ly
schema cua minh qua Alembic, giong seat-inventory-service).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Sequence, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# Sequence rieng cho schema "customer", dung de sinh id dang C001, C002, ...
# ngay tai tang database - tranh dung id giua nhieu instance/worker cua
# service khi chay voi nhieu uvicorn worker hoac nhieu container.
customer_id_seq = Sequence("customer_id_seq", start=1, schema="customer")


class CustomerModel(Base):
    __tablename__ = "customers"
    __table_args__ = {"schema": "customer"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    resource_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CustomerConsentModel(Base):
    __tablename__ = "customer_consents"
    __table_args__ = {"schema": "customer"}

    customer_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("customer.customers.id", ondelete="CASCADE"),
        primary_key=True,
    )
    channel: Mapped[str] = mapped_column(String, primary_key=True)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)


class IdentityMappingModel(Base):
    __tablename__ = "identity_mappings"
    __table_args__ = {"schema": "customer"}

    identity_subject: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("customer.customers.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    resource_version: Mapped[int] = mapped_column(Integer, nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
