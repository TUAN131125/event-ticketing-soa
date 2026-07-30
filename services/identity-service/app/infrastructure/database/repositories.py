"""Small repository helpers that keep SQL details out of use cases."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.domain.entities import UserView
from app.domain.value_objects import RequestContext
from app.infrastructure.database.models import (
    AuthAuditModel,
    AuthRateLimitModel,
    RefreshSessionModel,
    UserModel,
    UserRoleModel,
)


def database_now(session: Session) -> datetime:
    value = session.scalar(select(func.clock_timestamp()))
    if not isinstance(value, datetime):
        raise RuntimeError("Database clock is unavailable")
    return value


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def roles_for_user(session: Session, user_id: str) -> tuple[str, ...]:
    return tuple(
        session.scalars(
            select(UserRoleModel.role_name)
            .where(UserRoleModel.user_id == user_id)
            .order_by(UserRoleModel.role_name)
        ).all()
    )


def to_user_view(session: Session, user: UserModel) -> UserView:
    return UserView(
        user_id=user.user_id,
        email=user.email,
        status=user.status,
        roles=roles_for_user(session, user.user_id),
        token_version=user.token_version,
        created_at=user.created_at,
    )


def write_audit(
    session: Session,
    context: RequestContext,
    *,
    action: str,
    result: str,
    reason: str | None = None,
    actor_id: str | None = None,
    target_user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuthAuditModel(
            action=action,
            result=result,
            reason=reason,
            actor_id=actor_id,
            target_user_id=target_user_id,
            correlation_id=context.correlation_id,
            trace_id=context.trace_id,
            ip_hash=stable_hash(context.client_ip) if context.client_ip else None,
            metadata_json=metadata or {},
        )
    )


def consume_login_attempt(
    session: Session,
    *,
    subject: str,
    client_ip: str,
    window_seconds: int,
    limit: int,
) -> int | None:
    now = database_now(session)
    subject_hash = stable_hash(subject)
    bucket_key = stable_hash(f"LOGIN:{subject_hash}:{client_ip}")
    session.execute(
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
    bucket = session.scalar(
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


def reset_login_attempts(session: Session, *, subject: str, client_ip: str) -> None:
    bucket_key = stable_hash(f"LOGIN:{stable_hash(subject)}:{client_ip}")
    session.execute(
        delete(AuthRateLimitModel).where(AuthRateLimitModel.bucket_key == bucket_key)
    )


def revoke_family(
    session: Session,
    family_id: str,
    *,
    now: datetime,
    reason: str,
) -> int:
    result = session.execute(
        update(RefreshSessionModel)
        .where(
            RefreshSessionModel.family_id == family_id,
            RefreshSessionModel.revoked_at.is_(None),
        )
        .values(revoked_at=now, revoke_reason=reason)
    )
    return int(result.rowcount or 0)


def active_refresh_session_count(session: Session) -> int:
    now = datetime.now(UTC)
    value = session.scalar(
        select(func.count())
        .select_from(RefreshSessionModel)
        .where(
            RefreshSessionModel.revoked_at.is_(None),
            RefreshSessionModel.expires_at > now,
        )
    )
    return int(value or 0)
