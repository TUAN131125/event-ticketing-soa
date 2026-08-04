"""SQLAlchemy ORM model - moi service tu quan ly schema rieng qua Alembic.
Nguon su that duy nhat cho cau truc bang la migrations/versions/, khop voi
contracts/openapi/customer-service.yaml (GD5): schema Customer co
resourceVersion, consents la tai nguyen con rieng cua khach hang.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Sequence,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()

customer_id_seq = Sequence("customer_id_seq", start=1, schema="customer")


class CustomerModel(Base):
    __tablename__ = "customers"
    __table_args__ = {"schema": "customer"}

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    phone = Column(String, nullable=False)
    status = Column(String, nullable=False, default="ACTIVE")
    resource_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class ConsentModel(Base):
    """Tai nguyen con cua Customer - trang thai dong y nhan thong bao theo
    tung kenh (EMAIL/SMS). Endpoint: POST /customers/{id}/consents."""

    __tablename__ = "consents"
    __table_args__ = (
        UniqueConstraint("customer_id", "channel", name="uq_consent_customer_channel"),
        {"schema": "customer"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(
        String, ForeignKey("customer.customers.id", ondelete="CASCADE"), nullable=False
    )
    channel = Column(String, nullable=False)
    granted = Column(Boolean, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class IdempotencyRecordModel(Base):
    """Luu response da xu ly theo Idempotency-Key, dam bao request lap lai
    (ESB retry do timeout) khong tao thao tac trung. Xem resilience/
    idempotency.py cho phan logic doc/ghi bang nay."""

    __tablename__ = "idempotency_records"
    __table_args__ = {"schema": "customer"}

    idempotency_key = Column(String, primary_key=True)
    response_status = Column(Integer, nullable=False)
    response_body = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
