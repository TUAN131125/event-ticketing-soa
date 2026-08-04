"""Gom tat ca router con cua Event Service."""

from fastapi import APIRouter

from app.api import health
from app.api.v1 import resources

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(resources.router)
