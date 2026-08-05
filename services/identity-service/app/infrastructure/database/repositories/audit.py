"""Authentication audit persistence."""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.orm import Session

from app.domain.enums import AuditAction, AuditReason, AuditResult
from app.domain.value_objects import RequestContext
from app.infrastructure.database.models import AuthAuditModel


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record(
        self,
        context: RequestContext,
        *,
        action: AuditAction,
        result: AuditResult,
        reason: AuditReason | None = None,
        actor_id: str | None = None,
        target_user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._session.add(
            AuthAuditModel(
                action=action.value,
                result=result.value,
                reason=reason.value if reason is not None else None,
                actor_id=actor_id,
                target_user_id=target_user_id,
                correlation_id=context.correlation_id,
                trace_id=context.trace_id,
                ip_hash=(stable_hash(context.client_ip) if context.client_ip else None),
                metadata_json=metadata or {},
            )
        )
