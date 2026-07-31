"""SQLAlchemy ORM model - khop voi bang deliveries duoc tao trong
migrations/versions/. Day la nguon su that duy nhat cho cau truc bang,
giong quy uoc cua customer-service/event-service.
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Sequence, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# Sequence rieng cho schema "notification", dung de sinh id dang N000001,
# N000002, ... ngay tai tang database - tranh dung id giua nhieu
# instance/worker cua service khi chay voi nhieu uvicorn worker.
delivery_id_seq = Sequence("delivery_id_seq", start=1, schema="notification")


class DeliveryModel(Base):
    __tablename__ = "deliveries"
    __table_args__ = {"schema": "notification"}

    id = Column(String, primary_key=True)
    type = Column(String, nullable=False)
    correlation_id = Column(String, nullable=False, unique=True)
    to_email = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="SENT")
    created_at = Column(DateTime(timezone=True), nullable=False)
