"""Health check - tach rieng /health/live va /health/ready dung khop
hop dong (Giai doan 5): liveness khong cham dependency, readiness co
kiem tra ket noi DB va migration da chay chua."""
from fastapi import APIRouter, Response

from app.infrastructure.database.session import database_ready

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def liveness():
    return {"service": "notification-service", "status": "UP"}


@router.get("/ready")
def readiness(response: Response):
    if database_ready():
        return {"service": "notification-service", "status": "READY"}
    response.status_code = 503
    return {"service": "notification-service", "status": "NOT_READY"}
