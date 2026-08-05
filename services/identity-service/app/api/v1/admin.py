"""Administrator-only HTTP resources."""

from uuid import UUID

from fastapi import APIRouter, Depends, Path

from app.application.service import IdentityService
from app.dependencies import admin_principal, get_context, get_service
from app.domain.enums import RoleAction
from app.domain.value_objects import Principal, RequestContext
from app.schemas.requests import RoleChangeRequest
from app.schemas.responses import RoleChangeResponse


def create_admin_router() -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["administration"])

    @router.post(
        "/users/{userId}/roles",
        response_model=RoleChangeResponse,
        operation_id="changeIdentityUserRole",
        responses={401: {}, 403: {}, 404: {}, 422: {}, 500: {}, 503: {}},
    )
    def change_role(
        body: RoleChangeRequest,
        user_id: UUID = Path(alias="userId"),
        actor: Principal = Depends(admin_principal),
        service: IdentityService = Depends(get_service),
        context: RequestContext = Depends(get_context),
    ) -> RoleChangeResponse:
        result = service.change_role(
            actor=actor,
            target_user_id=str(user_id),
            role_name=body.role.value,
            action=RoleAction(body.action),
            context=context,
        )
        return RoleChangeResponse.from_result(result)

    return router
