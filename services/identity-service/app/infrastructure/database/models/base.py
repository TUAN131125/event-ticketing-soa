"""Shared SQLAlchemy metadata for the Identity schema."""

from sqlalchemy.orm import DeclarativeBase

SCHEMA = "identity"


class Base(DeclarativeBase):
    """Base class for all Identity schema models."""
