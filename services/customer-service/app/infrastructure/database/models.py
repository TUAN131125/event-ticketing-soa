"""SQLAlchemy ORM model - khop voi bang customers duoc tao trong
migrations/versions/. Day la nguon su that duy nhat cho cau truc bang
(khong con phu thuoc database/schemas/customer_schema.sql o repo goc,
file do van la placeholder o cap toan he thong - moi service tu quan ly
schema cua minh qua Alembic, giong seat-inventory-service).
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Sequence, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# Sequence rieng cho schema "customer", dung de sinh id dang C001, C002, ...
# ngay tai tang database - tranh dung id giua nhieu instance/worker cua
# service khi chay voi nhieu uvicorn worker hoac nhieu container.
customer_id_seq = Sequence(
    "customer_id_seq", start=1, schema="customer"
)


class CustomerModel(Base):
    __tablename__ = "customers"
    __table_args__ = {"schema": "customer"}

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    phone = Column(String, nullable=False)
    status = Column(String, nullable=False, default="ACTIVE")
    created_at = Column(DateTime(timezone=True), nullable=False)
