"""Payment API router composition."""

from fastapi import APIRouter

from app.api.v1 import admin, provider, resources


def create_api_router() -> APIRouter:
    router = APIRouter()
    # Static provider callback must be registered before /payments/{payment_id}.
    router.include_router(provider.router)
    router.include_router(resources.router)
    router.include_router(admin.router)
    return router
