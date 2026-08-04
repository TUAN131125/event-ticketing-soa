"""Health check - /health/live va /health/ready theo OpenAPI Giai doan 5
(thay cho /health don gian truoc day; giu them /health de tuong thich
nguoc voi script/dashboard cu neu co)."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.infrastructure.database.session import database_ready

router = APIRouter()


@router.get("/health")
def health_legacy():
    return {"service": "event-service", "status": "UP"}


@router.get("/health/live")
def liveness():
    return {"status": "UP"}


@router.get("/health/ready")
def readiness():
    if database_ready():
        return {"status": "READY"}
    return JSONResponse(
        status_code=503,
        content={
            "correlationId": "n/a",
            "error": {
                "code": "SERVICE_UNAVAILABLE",
                "message": "Database chua san sang",
                "retryable": True,
            },
        },
    )
