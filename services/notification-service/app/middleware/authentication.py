"""Authentication dependencies for Notification internal APIs and webhooks."""

from typing import Annotated, cast

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from libs.platform_security import (
    HmacAuthenticationError,
    ServiceAuthenticationError,
    ServicePrincipal,
)

SERVICE_JWT = HTTPBearer(auto_error=False, scheme_name="ServiceJwt")
WEBHOOK_HMAC = APIKeyHeader(
    name="X-Webhook-Signature", auto_error=False, scheme_name="WebhookHmac"
)


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


async def require_webhook_hmac(
    request: Request,
    signature: Annotated[str | None, Security(WEBHOOK_HMAC)],
) -> None:
    try:
        request.app.state.webhook_verifier.verify(
            timestamp=request.headers.get("X-Webhook-Timestamp"),
            signature=signature,
            body=await request.body(),
        )
    except HmacAuthenticationError as exc:
        raise HTTPException(
            status_code=401, detail="Webhook authentication failed"
        ) from exc
