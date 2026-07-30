"""Locking policy.

All integrity locks are PostgreSQL transaction locks. This module intentionally
contains no process-local or Redis lock implementation.
"""

from app.domain.rules import advisory_lock_id, normalize_seat_ids

__all__ = ["advisory_lock_id", "normalize_seat_ids"]
