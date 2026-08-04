"""Bam dia chi nhan (email/so dien thoai) truoc khi luu xuong DB.

Muc 4.2 dac ta SVC-08: "PII trong payload chi toi thieu; co retention
policy". Cot notification.deliveries.destination_hash trong SQL baseline
(Giai doan 5) la char(64) - luu SHA-256 hex cua dia chi that, KHONG luu
plaintext. Dia chi that (tu payload webhook) chi ton tai trong bo nho
trong luc xu ly 1 request, dung de goi provider.send() roi bi bo di -
khong bao gio ghi xuong DB.
"""
import hashlib


def hash_destination(destination: str) -> str:
    return hashlib.sha256(destination.strip().lower().encode("utf-8")).hexdigest()
