"""Gom tat ca router con cua Notification Service lai lam mot."""
from fastapi import APIRouter

from app.api import health
from app.api.v1 import deliveries, templates, webhooks

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(webhooks.router)
api_router.include_router(deliveries.router)
api_router.include_router(templates.router)
