"""Enum trang thai su kien - khop enum `status` trong OpenAPI Event schema
(Giai doan 5, contracts/openapi/event-service.yaml).

Luu y: ENDED ton tai trong enum nhung KHONG co endpoint mutation nao dat
duoc trang thai nay qua API baseline hien tai (paths chi co
publish/pause/cancel) - danh cho co che tu dong (vi du scheduled job khi
saleEndsAt da qua) se bo sung sau, xem "Quyet dinh con mo" trong dac ta.
"""

from enum import Enum


class EventStatus(str, Enum):
    DRAFT = "DRAFT"
    ON_SALE = "ON_SALE"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    ENDED = "ENDED"
