"""Gom tat ca router con cua Event Service."""
from fastapi import APIRouter

from app.api import health
from app.api.v1 import admin, resources

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(resources.router)
api_router.include_router(admin.router)
