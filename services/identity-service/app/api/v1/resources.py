"""Authentication HTTP resources."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, Security, status

from app.api.auth_cookies import (
    clear_auth_cookies,
    disable_token_caching,
    set_auth_cookies,
)
from app.application.service import IdentityService
from app.config import Settings
from app.dependencies import current_principal, get_context, get_service, refresh_cookie
from app.domain.exceptions import InvalidRefreshToken
from app.domain.value_objects import Principal, RequestContext
from app.schemas.requests import LoginRequest, RegisterRequest
from app.schemas.responses import TokenResponse, User
from app.security.csrf import REFRESH_COOKIE, new_csrf_token, verify_cookie_request


def create_resources_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["authentication"])

    @router.post(
        "/register",
        response_model=User,
        status_code=status.HTTP_201_CREATED,
        operation_id="registerIdentityAccount",
        responses={400: {}, 409: {}, 422: {}, 500: {}, 503: {}},
    )
    def register(
        body: RegisterRequest,
        service: IdentityService = Depends(get_service),
        context: RequestContext = Depends(get_context),
    ) -> User:
        user = service.register(
            str(body.email),
            body.password.get_secret_value(),
            context,
        )
        return User.from_view(user)

    @router.post(
        "/login",
        response_model=TokenResponse,
        operation_id="loginIdentityAccount",
        responses={401: {}, 403: {}, 423: {}, 429: {}, 422: {}, 500: {}, 503: {}},
    )
    def login(
        body: LoginRequest,
        response: Response,
        service: IdentityService = Depends(get_service),
        context: RequestContext = Depends(get_context),
    ) -> TokenResponse:
        outcome = service.login(
            str(body.email),
            body.password.get_secret_value(),
            context,
        )
        csrf_token = new_csrf_token()
        set_auth_cookies(
            response,
            settings,
            refresh_token=outcome.token_pair.refresh_token,
            csrf_token=csrf_token,
            max_age=settings.refresh_token_ttl_seconds,
        )
        disable_token_caching(response)
        return TokenResponse.from_pair(outcome.token_pair, csrf_token)

    @router.post(
        "/refresh",
        response_model=TokenResponse,
        operation_id="refreshIdentitySession",
        responses={401: {}, 403: {}, 500: {}, 503: {}},
    )
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
            raise InvalidRefreshToken()
        outcome = service.refresh(raw_token, context)
        csrf_token = new_csrf_token()
        set_auth_cookies(
            response,
            settings,
            refresh_token=outcome.token_pair.refresh_token,
            csrf_token=csrf_token,
            max_age=settings.refresh_token_ttl_seconds,
        )
        disable_token_caching(response)
        return TokenResponse.from_pair(outcome.token_pair, csrf_token)

    @router.post(
        "/logout",
        status_code=status.HTTP_204_NO_CONTENT,
        operation_id="logoutIdentitySession",
        responses={403: {}, 500: {}, 503: {}},
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
        clear_auth_cookies(response, settings)
        response.status_code = status.HTTP_204_NO_CONTENT
        return response

    @router.get(
        "/me",
        response_model=User,
        operation_id="getCurrentIdentityPrincipal",
        responses={401: {}, 403: {}, 500: {}, 503: {}},
    )
    def me(
        principal: Principal = Depends(current_principal),
        service: IdentityService = Depends(get_service),
    ) -> User:
        return User.from_view(service.current_user(principal))

    return router
