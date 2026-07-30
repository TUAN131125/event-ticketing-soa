from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from app.application.service import IdentityService
from app.domain.exceptions import RefreshTokenReuseDetected
from app.domain.value_objects import RequestContext
from app.infrastructure.database.models import RefreshSessionModel
from app.infrastructure.database.session import get_session_factory
from app.security.passwords import PasswordService
from app.security.tokens import TokenService


@pytest.mark.integration
@pytest.mark.concurrency
def test_concurrent_refresh_allows_only_one_success(settings):
    service = IdentityService(
        settings,
        get_session_factory(settings),
        PasswordService(settings),
        TokenService(settings),
    )
    context = RequestContext("concurrency", "2" * 32, "127.0.0.1", "pytest")
    service.register("parallel@example.com", "Correct-Horse-9!Long", context)
    original = service.login("parallel@example.com", "Correct-Horse-9!Long", context)
    raw = original.token_pair.refresh_token

    def refresh_once():
        try:
            return ("success", service.refresh(raw, context))
        except RefreshTokenReuseDetected:
            return ("reuse", None)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: refresh_once(), range(2)))
    assert sorted(result[0] for result in results) == ["reuse", "success"]
    with get_session_factory(settings)() as session:
        active = session.scalar(
            select(RefreshSessionModel).where(
                RefreshSessionModel.family_id
                == session.scalar(
                    select(RefreshSessionModel.family_id).where(
                        RefreshSessionModel.token_hash
                        == service.tokens.hash_refresh_token(raw)
                    )
                ),
                RefreshSessionModel.revoked_at.is_(None),
            )
        )
        assert active is None
