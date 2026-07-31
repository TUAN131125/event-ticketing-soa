"""Cac enum thuoc domain cua Customer Service."""
from enum import Enum


class CustomerStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
