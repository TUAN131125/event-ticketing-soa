"""Booking API router composition."""

from fastapi import APIRouter

from app.api.v1 import admin, resources


def create_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(resources.router)
    router.include_router(admin.router)
    return router
