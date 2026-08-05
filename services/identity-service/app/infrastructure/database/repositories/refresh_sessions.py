"""Refresh-session persistence operations."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.domain.enums import SessionRevokeReason
from app.infrastructure.database.models import RefreshSessionModel


class RefreshSessionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, refresh_session: RefreshSessionModel) -> None:
        self._session.add(refresh_session)

    def find_by_token_hash(
        self, token_hash: str, *, for_update: bool = False
    ) -> RefreshSessionModel | None:
        statement = select(RefreshSessionModel).where(
            RefreshSessionModel.token_hash == token_hash
        )
        if for_update:
            statement = statement.with_for_update()
        return self._session.scalar(statement)

    def revoke_family(
        self,
        family_id: str,
        *,
        now: datetime,
        reason: SessionRevokeReason,
    ) -> int:
        result = self._session.execute(
            update(RefreshSessionModel)
            .where(
                RefreshSessionModel.family_id == family_id,
                RefreshSessionModel.revoked_at.is_(None),
            )
            .values(revoked_at=now, revoke_reason=reason.value)
        )
        return int(result.rowcount or 0)

    def active_count(self) -> int:
        now = datetime.now(UTC)
        value = self._session.scalar(
            select(func.count())
            .select_from(RefreshSessionModel)
            .where(
                RefreshSessionModel.revoked_at.is_(None),
                RefreshSessionModel.expires_at > now,
            )
        )
        return int(value or 0)
