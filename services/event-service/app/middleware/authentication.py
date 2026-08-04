"""Xac thuc request - chua trien khai trong MVP, xem ghi chu tuong tu
o Customer Service. Diem mo rong: chi Admin moi duoc goi cac endpoint
tao/sua/doi trang thai su kien."""

from fastapi import Request


async def verify_internal_caller(request: Request) -> bool:
    return True
