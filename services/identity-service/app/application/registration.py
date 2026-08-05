"""Account registration use case."""

from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.application.metrics import record_failure, record_success
from app.domain.entities import UserView
from app.domain.enums import (
    AuditAction,
    AuditReason,
    AuditResult,
    RoleName,
    UserStatus,
)
from app.domain.exceptions import EmailAlreadyExists, IdentityError
from app.domain.rules import normalize_email, validate_password
from app.domain.value_objects import RequestContext
from app.infrastructure.database.models import UserModel
from app.infrastructure.database.repositories import AuditRepository, UserRepository
from app.security.passwords import PasswordService


class RegistrationUseCase:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        password_service: PasswordService,
    ) -> None:
        self._sessions = session_factory
        self._passwords = password_service

    def execute(self, email: str, password: str, context: RequestContext) -> UserView:
        display_email, normalized_email = normalize_email(email)
        validate_password(password)
        password_hash = self._passwords.hash(password)
        pending_error: IdentityError | None = None
        created: UserView | None = None

        try:
            with self._sessions() as session, session.begin():
                users = UserRepository(session)
                audit = AuditRepository(session)
                existing = users.find_by_normalized_email(normalized_email)
                if existing is not None:
                    audit.record(
                        context,
                        action=AuditAction.REGISTER,
                        result=AuditResult.FAILURE,
                        reason=AuditReason.EMAIL_ALREADY_EXISTS,
                        target_user_id=existing.user_id,
                    )
                    pending_error = EmailAlreadyExists()
                else:
                    user = UserModel(
                        user_id=str(uuid.uuid4()),
                        email=display_email,
                        normalized_email=normalized_email,
                        password_hash=password_hash,
                        status=UserStatus.ACTIVE,
                        token_version=1,
                        failed_login_count=0,
                    )
                    users.add(user)
                    session.flush()
                    users.assign_role(
                        user.user_id,
                        RoleName.CUSTOMER,
                        assigned_by=None,
                    )
                    session.flush()
                    audit.record(
                        context,
                        action=AuditAction.REGISTER,
                        result=AuditResult.SUCCESS,
                        target_user_id=user.user_id,
                    )
                    created = users.view(user)
        except IntegrityError as exc:
            self._audit_conflict(normalized_email, context)
            error = EmailAlreadyExists()
            record_failure("register", error)
            raise error from exc

        if pending_error is not None:
            record_failure("register", pending_error)
            raise pending_error
        if created is None:
            raise RuntimeError("Registration completed without a user")
        record_success("register")
        return created

    def _audit_conflict(
        self, normalized_email: str, context: RequestContext
    ) -> None:
        with self._sessions() as session, session.begin():
            users = UserRepository(session)
            existing = users.find_by_normalized_email(normalized_email)
            AuditRepository(session).record(
                context,
                action=AuditAction.REGISTER,
                result=AuditResult.FAILURE,
                reason=AuditReason.EMAIL_ALREADY_EXISTS,
                target_user_id=existing.user_id if existing is not None else None,
            )
