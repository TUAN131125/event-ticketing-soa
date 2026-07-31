"""REST endpoint cho nghiep vu Customer - tang API, chi lam nhiem vu nhan
request/tra response, moi logic thuc su nam o tang application/domain."""
from fastapi import APIRouter, Depends, status

from app.application.commands.create_customer import create_customer
from app.application.commands.get_customer import get_customer
from app.application.commands.update_customer import update_customer
from app.dependencies import get_repository
from app.repositories.interfaces import CustomerRepository
from app.schemas.requests import CustomerCreateRequest, CustomerUpdateRequest
from app.schemas.responses import CustomerResponse

router = APIRouter(prefix="/customers", tags=["customers"])


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create(payload: CustomerCreateRequest, repo: CustomerRepository = Depends(get_repository)):
    customer = create_customer(repo, payload.name, payload.email, payload.phone)
    return CustomerResponse.from_entity(customer)


@router.get("/{customer_id}", response_model=CustomerResponse)
def get(customer_id: str, repo: CustomerRepository = Depends(get_repository)):
    customer = get_customer(repo, customer_id)
    return CustomerResponse.from_entity(customer)


@router.put("/{customer_id}", response_model=CustomerResponse)
def update(customer_id: str, payload: CustomerUpdateRequest,
           repo: CustomerRepository = Depends(get_repository)):
    customer = update_customer(
        repo, customer_id, name=payload.name, email=payload.email, phone=payload.phone
    )
    return CustomerResponse.from_entity(customer)


@router.get("/{customer_id}/exists")
def exists(customer_id: str, repo: CustomerRepository = Depends(get_repository)):
    """Endpoint tien loi de ESB kiem tra nhanh khach hang co ton tai khong."""
    return {"exists": repo.get(customer_id) is not None}
