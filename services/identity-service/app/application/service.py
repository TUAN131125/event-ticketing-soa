"""Public application facade for Identity use cases."""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from app.application.authentication import AuthenticationUseCase
from app.application.outcomes import LoginOutcome
from app.application.registration import RegistrationUseCase
from app.application.role_management import RoleManagementUseCase
from app.application.session_issuer import TokenSessionIssuer
from app.application.session_management import SessionManagementUseCase
from app.config import Settings
from app.domain.entities import RoleChange, UserView
from app.domain.enums import RoleAction
from app.domain.value_objects import Principal, RequestContext
from app.infrastructure.database.repositories import RefreshSessionRepository
from app.security.passwords import PasswordService
from app.security.tokens import TokenService


class IdentityService:
    """Stable facade used by HTTP handlers, scripts and integration tests.

    The facade preserves the service's public Python API while delegating each
    business capability to a focused use case. Transaction boundaries remain in
    the delegated use cases.
    """

    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        password_service: PasswordService,
        token_service: TokenService,
    ) -> None:
        self.settings = settings
        self._session_factory = session_factory
        self._token_service = token_service

        session_issuer = TokenSessionIssuer(settings, token_service)
        registration = RegistrationUseCase(session_factory, password_service)
        self._registration = registration
        self._authentication = AuthenticationUseCase(
            settings,
            session_factory,
            password_service,
            token_service,
            session_issuer,
        )
        self._session_management = SessionManagementUseCase(
            session_factory,
            token_service,
            session_issuer,
        )
        self._role_management = RoleManagementUseCase(session_factory, registration)

    @property
    def tokens(self) -> TokenService:
        """Compatibility accessor for tests and operator tooling."""

        return self._token_service

    def register(self, email: str, password: str, context: RequestContext) -> UserView:
        return self._registration.execute(email, password, context)

    def login(self, email: str, password: str, context: RequestContext) -> LoginOutcome:
        return self._authentication.login(email, password, context)

    def refresh(self, raw_refresh_token: str, context: RequestContext) -> LoginOutcome:
        return self._session_management.refresh(raw_refresh_token, context)

    def logout(self, raw_refresh_token: str | None, context: RequestContext) -> None:
        self._session_management.logout(raw_refresh_token, context)

    def authenticate_access_token(self, token: str) -> Principal:
        return self._authentication.authenticate_access_token(token)

    def current_user(self, principal: Principal) -> UserView:
        return self._authentication.current_user(principal)

    def change_role(
        self,
        *,
        actor: Principal,
        target_user_id: str,
        role_name: str,
        action: RoleAction,
        context: RequestContext,
    ) -> RoleChange:
        return self._role_management.change_role(
            actor=actor,
            target_user_id=target_user_id,
            role_name=role_name,
            action=action,
            context=context,
        )

    def bootstrap_admin(
        self, email: str, password: str, context: RequestContext
    ) -> UserView:
        return self._role_management.bootstrap_admin(email, password, context)

    def jwks(self) -> dict[str, list[dict[str, str]]]:
        return self._token_service.jwks()

    def active_refresh_session_count(self) -> int:
        with self._session_factory() as session:
            return RefreshSessionRepository(session).active_count()
