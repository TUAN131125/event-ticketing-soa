"""Health check endpoint."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    return {"service": "event-service", "status": "UP"}
