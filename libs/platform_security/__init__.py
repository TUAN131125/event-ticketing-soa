"""Small, domain-free security primitives shared by platform services."""

from .service_jwt import (
    ServiceAuthenticationError,
    ServiceJwtSigner,
    ServiceJwtSigningSettings,
    ServiceJwtValidationSettings,
    ServiceJwtVerifier,
    ServicePrincipal,
    load_key_material,
)
from .webhook_hmac import (
    HmacAuthenticationError,
    HmacRequestVerifier,
    sign_hmac_request,
)

__all__ = [
    "HmacAuthenticationError",
    "HmacRequestVerifier",
    "ServiceAuthenticationError",
    "ServiceJwtSigner",
    "ServiceJwtSigningSettings",
    "ServiceJwtValidationSettings",
    "ServiceJwtVerifier",
    "ServicePrincipal",
    "load_key_material",
    "sign_hmac_request",
]
