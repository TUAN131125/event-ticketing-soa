"""Health check endpoint."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    return {"service": "notification-service", "status": "UP"}
