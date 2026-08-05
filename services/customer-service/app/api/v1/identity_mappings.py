"""Canonical Customer-owned identity mapping boundary."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Response
from libs.platform_http import etag

from app.api.v1.resources import _version
from app.application.commands.manage_identity_mapping import (
    link_identity,
    resolve_identity,
    unlink_identity,
)
from app.dependencies import get_repository
from app.middleware.authentication import require_service_principal
from app.repositories.interfaces import CustomerRepository
from app.schemas.requests import IdentityLinkRequest
from app.schemas.responses import IdentityMappingResponse

router = APIRouter(
    prefix="/internal",
    tags=["identity-mappings"],
    dependencies=[Depends(require_service_principal)],
)


@router.put(
    "/customers/{customerId}/identity-link",
    response_model=IdentityMappingResponse,
    operation_id="linkCustomerIdentitySubject",
)
def link(
    customer_id: Annotated[str, Path(alias="customerId")],
    payload: IdentityLinkRequest,
    response: Response,
    correlation_id: Annotated[
        str, Header(alias="X-Correlation-ID", min_length=16, max_length=64)
    ],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    if_match: Annotated[str, Header(alias="If-Match", pattern=r'^"[1-9][0-9]*"$')],
    repo: CustomerRepository = Depends(get_repository),
) -> IdentityMappingResponse:
    mapping = link_identity(
        repo, customer_id, payload.identity_subject, _version(if_match)
    )
    response.headers["ETag"] = etag(mapping.resource_version)
    return IdentityMappingResponse.from_entity(mapping)


@router.delete(
    "/customers/{customerId}/identity-link",
    response_model=IdentityMappingResponse,
    operation_id="unlinkCustomerIdentitySubject",
)
def unlink(
    customer_id: Annotated[str, Path(alias="customerId")],
    response: Response,
    correlation_id: Annotated[
        str, Header(alias="X-Correlation-ID", min_length=16, max_length=64)
    ],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    if_match: Annotated[str, Header(alias="If-Match", pattern=r'^"[1-9][0-9]*"$')],
    repo: CustomerRepository = Depends(get_repository),
) -> IdentityMappingResponse:
    mapping = unlink_identity(repo, customer_id, _version(if_match))
    response.headers["ETag"] = etag(mapping.resource_version)
    return IdentityMappingResponse.from_entity(mapping)


@router.get(
    "/identity-mappings/{identitySubject}",
    response_model=IdentityMappingResponse,
    operation_id="resolveCustomerIdentityMapping",
)
def resolve(
    identity_subject: Annotated[str, Path(alias="identitySubject")],
    response: Response,
    correlation_id: Annotated[
        str, Header(alias="X-Correlation-ID", min_length=16, max_length=64)
    ],
    repo: CustomerRepository = Depends(get_repository),
) -> IdentityMappingResponse:
    mapping = resolve_identity(repo, identity_subject)
    if mapping is None:
        raise HTTPException(status_code=404, detail="Identity mapping not found")
    response.headers["ETag"] = etag(mapping.resource_version)
    return IdentityMappingResponse.from_entity(mapping)
