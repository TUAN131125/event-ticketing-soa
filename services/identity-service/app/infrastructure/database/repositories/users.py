"""User and role persistence operations."""

from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.domain.entities import UserView
from app.infrastructure.database.models import RoleModel, UserModel, UserRoleModel


class UserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_normalized_email(
        self, normalized_email: str, *, for_update: bool = False
    ) -> UserModel | None:
        statement: Select[tuple[UserModel]] = select(UserModel).where(
            UserModel.normalized_email == normalized_email
        )
        if for_update:
            statement = statement.with_for_update()
        return self._session.scalar(statement)

    def find_by_id(self, user_id: str, *, for_update: bool = False) -> UserModel | None:
        if not for_update:
            return self._session.get(UserModel, user_id)
        return self._session.scalar(
            select(UserModel)
            .where(UserModel.user_id == user_id)
            .with_for_update()
        )

    def add(self, user: UserModel) -> None:
        self._session.add(user)

    def role_exists(self, role_name: str) -> bool:
        return self._session.get(RoleModel, role_name) is not None

    def assigned_role(self, user_id: str, role_name: str) -> UserRoleModel | None:
        return self._session.get(
            UserRoleModel,
            {"user_id": user_id, "role_name": role_name},
        )

    def assign_role(
        self, user_id: str, role_name: str, *, assigned_by: str | None
    ) -> UserRoleModel:
        assignment = UserRoleModel(
            user_id=user_id,
            role_name=role_name,
            assigned_by=assigned_by,
        )
        self._session.add(assignment)
        return assignment

    def revoke_role(self, assignment: UserRoleModel) -> None:
        self._session.delete(assignment)

    def roles_for(self, user_id: str) -> tuple[str, ...]:
        return tuple(
            self._session.scalars(
                select(UserRoleModel.role_name)
                .where(UserRoleModel.user_id == user_id)
                .order_by(UserRoleModel.role_name)
            ).all()
        )

    def view(self, user: UserModel) -> UserView:
        return UserView(
            user_id=user.user_id,
            email=user.email,
            status=user.status,
            roles=self.roles_for(user.user_id),
            token_version=user.token_version,
            created_at=user.created_at,
        )
