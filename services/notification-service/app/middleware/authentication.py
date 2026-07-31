"""Xac thuc request goi vao Notification Service.

Chua trien khai trong MVP: hien tai service chap nhan moi request webhook
(chi duoc goi noi bo qua ESB trong kien truc dinh huong, xem DOC-01 -
"Client khong nen goi truc tiep service nghiep vu"). Ham duoi day la diem
noi de sau nay them kiem tra JWT/service-to-service token neu nhom trien
khai Identity Service, hoac chu ky webhook (xem security/webhook_signature.py).
"""
from fastapi import Request


async def verify_internal_caller(request: Request) -> bool:
    """Placeholder co chu dich: luon cho phep trong MVP."""
    return True
