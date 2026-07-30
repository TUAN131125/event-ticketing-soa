"""API composition."""

from fastapi import APIRouter

from app.api.v1.admin import create_admin_router
from app.api.v1.resources import create_resources_router
from app.config import Settings


def create_api_router(settings: Settings) -> APIRouter:
    router = APIRouter()
    router.include_router(create_resources_router(settings))
    router.include_router(create_admin_router())
    return router
