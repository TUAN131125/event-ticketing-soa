"""Service JWT authentication for protected Event API calls."""

from typing import Annotated, cast

from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from libs.platform_security import ServiceAuthenticationError, ServicePrincipal

SERVICE_JWT = HTTPBearer(auto_error=False, scheme_name="ServiceJwt")


def require_service_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(SERVICE_JWT)],
) -> ServicePrincipal:
    authorization = (
        f"Bearer {credentials.credentials}" if credentials is not None else None
    )
    try:
        return cast(
            ServicePrincipal,
            request.app.state.service_jwt_verifier.verify_authorization(authorization),
        )
    except ServiceAuthenticationError as exc:
        raise HTTPException(
            status_code=401, detail="Service authentication failed"
        ) from exc
