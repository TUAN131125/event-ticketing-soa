"""Authentication resources."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, Security, status

from app.application.service import IdentityService
from app.config import Settings
from app.dependencies import current_principal, get_context, get_service, refresh_cookie
from app.domain.value_objects import Principal, RequestContext
from app.schemas.requests import LoginRequest, RegisterRequest
from app.schemas.responses import TokenResponse, UserResponse
from app.security.csrf import (
    CSRF_COOKIE,
    REFRESH_COOKIE,
    new_csrf_token,
    verify_cookie_request,
)


def _set_auth_cookies(
    response: Response,
    settings: Settings,
    refresh_token: str,
    csrf_token: str,
    max_age: int,
) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/auth",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/auth",
    )


def _clear_auth_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/auth",
    )
    response.delete_cookie(
        CSRF_COOKIE,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/auth",
    )


def create_resources_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["authentication"])

    @router.post(
        "/register",
        response_model=UserResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="register",
    )
    def register(
        body: RegisterRequest,
        request: Request,
        service: IdentityService = Depends(get_service),
        context: RequestContext = Depends(get_context),
    ) -> UserResponse:
        user = service.register(body.email, body.password.get_secret_value(), context)
        return UserResponse.from_view(user)

    @router.post("/login", response_model=TokenResponse, operation_id="login")
    def login(
        body: LoginRequest,
        response: Response,
        service: IdentityService = Depends(get_service),
        context: RequestContext = Depends(get_context),
    ) -> TokenResponse:
        outcome = service.login(body.email, body.password.get_secret_value(), context)
        csrf_token = new_csrf_token()
        _set_auth_cookies(
            response,
            settings,
            outcome.token_pair.refresh_token,
            csrf_token,
            settings.refresh_token_ttl_seconds,
        )
        return TokenResponse.from_pair(outcome.token_pair, csrf_token)

    @router.post("/refresh", response_model=TokenResponse, operation_id="refresh")
    def refresh(
        request: Request,
        response: Response,
        refresh_value: str | None = Security(refresh_cookie),
        service: IdentityService = Depends(get_service),
        context: RequestContext = Depends(get_context),
    ) -> TokenResponse:
        verify_cookie_request(request, settings)
        raw_token = refresh_value or request.cookies.get(REFRESH_COOKIE)
        if not raw_token:
            from app.domain.exceptions import InvalidRefreshToken

            raise InvalidRefreshToken()
        outcome = service.refresh(raw_token, context)
        csrf_token = new_csrf_token()
        _set_auth_cookies(
            response,
            settings,
            outcome.token_pair.refresh_token,
            csrf_token,
            settings.refresh_token_ttl_seconds,
        )
        return TokenResponse.from_pair(outcome.token_pair, csrf_token)

    @router.post(
        "/logout", status_code=status.HTTP_204_NO_CONTENT, operation_id="logout"
    )
    def logout(
        request: Request,
        response: Response,
        refresh_value: str | None = Security(refresh_cookie),
        service: IdentityService = Depends(get_service),
        context: RequestContext = Depends(get_context),
    ) -> Response:
        verify_cookie_request(request, settings)
        service.logout(refresh_value or request.cookies.get(REFRESH_COOKIE), context)
        _clear_auth_cookies(response, settings)
        response.status_code = status.HTTP_204_NO_CONTENT
        return response

    @router.get("/me", response_model=UserResponse, operation_id="currentPrincipal")
    def me(
        principal: Principal = Depends(current_principal),
        service: IdentityService = Depends(get_service),
    ) -> UserResponse:
        return UserResponse.from_view(service.current_user(principal))

    return router
