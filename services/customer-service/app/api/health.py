"""Health check endpoint - khop dung contracts/openapi/customer-service.yaml
(/health/live va /health/ready, tach rieng theo dung quy uoc Kubernetes-style
health probe). /health cu (khong con trong contract) van giu lai vi phia
sau tro thang ve /health/live, tranh lam vo cac cong cu monitoring da tro
vao duong cu neu co."""
from fastapi import APIRouter, Response, status

from app.infrastructure.database.session import database_ready

router = APIRouter()


@router.get("/health")
@router.get("/health/live")
def live():
    """Liveness: chi tra loi la process con song, KHONG kiem tra
    dependency (database). Dung de container orchestrator biet co can
    restart container hay khong."""
    return {"service": "customer-service", "status": "UP"}


@router.get("/health/ready")
def ready(response: Response):
    """Readiness: kiem tra ket noi database va da chay migration chua
    (database_ready() trong infrastructure/database/session.py). Tra 503
    neu chua san sang - dung de load balancer biet co nen dua traffic vao
    instance nay hay khong."""
    if database_ready():
        return {"service": "customer-service", "status": "READY"}
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"service": "customer-service", "status": "NOT_READY"}
