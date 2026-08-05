"""Create access and refresh token pairs inside an existing transaction."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.application.outcomes import LoginOutcome
from app.config import Settings
from app.domain.entities import TokenPair
from app.domain.value_objects import RequestContext
from app.infrastructure.database.models import RefreshSessionModel, UserModel
from app.infrastructure.database.repositories import (
    RefreshSessionRepository,
    UserRepository,
)
from app.security.tokens import TokenService


class TokenSessionIssuer:
    def __init__(self, settings: Settings, token_service: TokenService) -> None:
        self._settings = settings
        self._tokens = token_service

    def issue(
        self,
        session: Session,
        user: UserModel,
        roles: tuple[str, ...],
        context: RequestContext,
        *,
        now: datetime,
        family_id: str,
        parent_session_id: str | None,
    ) -> LoginOutcome:
        raw_refresh = self._tokens.generate_refresh_token()
        refresh_session = RefreshSessionModel(
            session_id=str(uuid.uuid4()),
            user_id=user.user_id,
            token_hash=self._tokens.hash_refresh_token(raw_refresh),
            family_id=family_id,
            parent_session_id=parent_session_id,
            expires_at=now
            + timedelta(seconds=self._settings.refresh_token_ttl_seconds),
            user_agent_hash=self._tokens.user_agent_hash(context.user_agent),
            created_at=now,
        )
        RefreshSessionRepository(session).add(refresh_session)
        session.flush()
        access_token = self._tokens.issue_access_token(
            user_id=user.user_id,
            roles=roles,
            token_version=user.token_version,
            now=now,
        )
        return LoginOutcome(
            token_pair=TokenPair(
                access_token=access_token,
                refresh_token=raw_refresh,
                access_expires_in=self._settings.access_token_ttl_seconds,
                refresh_expires_at=refresh_session.expires_at,
                user=UserRepository(session).view(user),
            ),
            session_id=refresh_session.session_id,
        )
