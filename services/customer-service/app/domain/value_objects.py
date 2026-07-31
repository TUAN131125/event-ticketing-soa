"""Value object don gian cho Customer Service.

Pham vi MVP chi can chuan hoa so dien thoai; validate dinh dang email da
duoc Pydantic (EmailStr) dam nhiem o tang schemas nen khong lam lai o day.
"""
import re


class PhoneNumber:
    """Chuan hoa va kiem tra so dien thoai Viet Nam co ban."""

    _PATTERN = re.compile(r"^0\d{9}$")

    def __init__(self, raw: str):
        cleaned = raw.strip().replace(" ", "").replace("-", "")
        if not self._PATTERN.match(cleaned):
            raise ValueError(f"So dien thoai khong hop le: {raw}")
        self.value = cleaned

    def __str__(self) -> str:
        return self.value
