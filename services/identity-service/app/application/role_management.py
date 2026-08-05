"""Role administration and administrator bootstrap use cases."""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from app.application.metrics import record_failure, record_success
from app.application.registration import RegistrationUseCase
from app.domain.entities import RoleChange, UserView
from app.domain.enums import (
    AuditAction,
    AuditReason,
    AuditResult,
    RoleAction,
    RoleName,
)
from app.domain.exceptions import (
    EmailAlreadyExists,
    Forbidden,
    IdentityError,
    RoleNotFound,
    UserNotFound,
)
from app.domain.policies import is_self_admin_revoke
from app.domain.rules import normalize_email
from app.domain.value_objects import Principal, RequestContext
from app.infrastructure.database.repositories import (
    AuditRepository,
    UserRepository,
    database_now,
)


class RoleManagementUseCase:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        registration: RegistrationUseCase,
    ) -> None:
        self._sessions = session_factory
        self._registration = registration

    def change_role(
        self,
        *,
        actor: Principal,
        target_user_id: str,
        role_name: str,
        action: RoleAction,
        context: RequestContext,
    ) -> RoleChange:
        pending_error: IdentityError | None = None
        result: RoleChange | None = None

        with self._sessions() as session, session.begin():
            users = UserRepository(session)
            audit = AuditRepository(session)
            target = users.find_by_id(target_user_id, for_update=True)
            if target is None:
                audit.record(
                    context,
                    action=AuditAction.ROLE_CHANGE,
                    result=AuditResult.FAILURE,
                    reason=AuditReason.USER_NOT_FOUND,
                    actor_id=actor.user_id,
                )
                pending_error = UserNotFound()
            elif not users.role_exists(role_name):
                audit.record(
                    context,
                    action=AuditAction.ROLE_CHANGE,
                    result=AuditResult.FAILURE,
                    reason=AuditReason.ROLE_NOT_FOUND,
                    actor_id=actor.user_id,
                    target_user_id=target_user_id,
                )
                pending_error = RoleNotFound()
            elif is_self_admin_revoke(
                actor_user_id=actor.user_id,
                target_user_id=target_user_id,
                role_name=role_name,
                action=action,
            ):
                audit.record(
                    context,
                    action=AuditAction.ROLE_CHANGE,
                    result=AuditResult.FAILURE,
                    reason=AuditReason.SELF_ADMIN_REVOKE_FORBIDDEN,
                    actor_id=actor.user_id,
                    target_user_id=target_user_id,
                )
                pending_error = Forbidden(
                    "An administrator cannot revoke own ADMIN role"
                )
            else:
                existing = users.assigned_role(target_user_id, role_name)
                changed = False
                if action == RoleAction.ASSIGN and existing is None:
                    users.assign_role(
                        target_user_id,
                        role_name,
                        assigned_by=actor.user_id,
                    )
                    changed = True
                elif action == RoleAction.REVOKE and existing is not None:
                    users.revoke_role(existing)
                    changed = True
                if changed:
                    target.token_version += 1
                    target.updated_at = database_now(session)
                    session.flush()
                audit.record(
                    context,
                    action=AuditAction.ROLE_CHANGE,
                    result=AuditResult.SUCCESS if changed else AuditResult.NO_CHANGE,
                    actor_id=actor.user_id,
                    target_user_id=target_user_id,
                    metadata={"role": role_name, "action": action.value},
                )
                result = RoleChange(
                    user=users.view(target),
                    role=role_name,
                    action=action,
                    changed=changed,
                )

        if pending_error is not None:
            record_failure("role_change", pending_error)
            raise pending_error
        if result is None:
            raise RuntimeError("Role change completed without a result")
        record_success("role_change")
        return result

    def bootstrap_admin(
        self, email: str, password: str, context: RequestContext
    ) -> UserView:
        try:
            user = self._registration.execute(email, password, context)
        except EmailAlreadyExists:
            _, normalized = normalize_email(email)
            with self._sessions() as session:
                users = UserRepository(session)
                existing = users.find_by_normalized_email(normalized)
                if existing is None:
                    raise
                user = users.view(existing)

        with self._sessions() as session, session.begin():
            users = UserRepository(session)
            model = users.find_by_id(user.user_id, for_update=True)
            if model is None:
                raise UserNotFound()
            existing_role = users.assigned_role(model.user_id, RoleName.ADMIN)
            if existing_role is None:
                users.assign_role(
                    model.user_id,
                    RoleName.ADMIN,
                    assigned_by=None,
                )
                model.token_version += 1
                model.updated_at = database_now(session)
            AuditRepository(session).record(
                context,
                action=AuditAction.BOOTSTRAP_ADMIN,
                result=(
                    AuditResult.SUCCESS
                    if existing_role is None
                    else AuditResult.NO_CHANGE
                ),
                target_user_id=model.user_id,
            )
            session.flush()
            return users.view(model)
