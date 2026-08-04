"""Ho tro xu ly header Idempotency-Key cho POST/PUT theo dung
contracts/openapi/customer-service.yaml (parameter IdempotencyKey,
required: true tren createCustomer, replaceCustomer, updateCustomerConsent,
deactivateCustomer).

Cach dung o tang API (api/v1/resources.py, api/v1/admin.py):

    cached = idempotency_store.get(idempotency_key)
    if cached is not None:
        status_code, body = cached
        return JSONResponse(status_code=status_code, content=body)
    ... xu ly binh thuong, tao response_body ...
    idempotency_store.save(idempotency_key, status_code, response_body)
    return response

Pham vi MVP: chi luu (status, body) theo key, KHONG kiem tra request body
co giong het lan truoc khong (day du hon thi can hash ca body de phat hien
"tai su dung key cho request khac noi dung" - la loi nghiep vu can bao
409, nhung ngoai pham vi MVP hien tai, ghi nhan la gap con lai).
"""
from app.repositories.interfaces import IdempotencyStore

__all__ = ["IdempotencyStore"]
