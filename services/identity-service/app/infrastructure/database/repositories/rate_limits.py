"""Persistent login rate limiting."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.infrastructure.database.models import AuthRateLimitModel
from app.infrastructure.database.repositories.audit import stable_hash
from app.infrastructure.database.repositories.clock import database_now


class LoginRateLimitRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _bucket_key(subject: str, client_ip: str) -> str:
        return stable_hash(f"LOGIN:{stable_hash(subject)}:{client_ip}")

    def consume(
        self,
        *,
        subject: str,
        client_ip: str,
        window_seconds: int,
        limit: int,
    ) -> int | None:
        now = database_now(self._session)
        subject_hash = stable_hash(subject)
        bucket_key = self._bucket_key(subject, client_ip)
        self._session.execute(
            insert(AuthRateLimitModel)
            .values(
                bucket_key=bucket_key,
                action="LOGIN",
                subject_hash=subject_hash,
                window_started_at=now,
                attempts=0,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=["bucket_key"])
        )
        bucket = self._session.scalar(
            select(AuthRateLimitModel)
            .where(AuthRateLimitModel.bucket_key == bucket_key)
            .with_for_update()
        )
        if bucket is None:
            raise RuntimeError("Rate-limit bucket could not be created")
        if bucket.blocked_until is not None and bucket.blocked_until > now:
            return max(1, int((bucket.blocked_until - now).total_seconds()))
        if now - bucket.window_started_at >= timedelta(seconds=window_seconds):
            bucket.window_started_at = now
            bucket.attempts = 0
            bucket.blocked_until = None
        bucket.attempts += 1
        bucket.updated_at = now
        if bucket.attempts > limit:
            bucket.blocked_until = now + timedelta(seconds=window_seconds)
            return window_seconds
        return None

    def reset(self, *, subject: str, client_ip: str) -> None:
        self._session.execute(
            delete(AuthRateLimitModel).where(
                AuthRateLimitModel.bucket_key == self._bucket_key(subject, client_ip)
            )
        )
