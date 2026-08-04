"""Loi thuoc domain - khong phu thuoc HTTP status code."""


class CustomerNotFoundError(Exception):
    def __init__(self, customer_id: str):
        self.customer_id = customer_id
        super().__init__(f"Khong tim thay khach hang: {customer_id}")


class DuplicateEmailError(Exception):
    def __init__(self, email: str):
        self.email = email
        super().__init__(f"Email da ton tai: {email}")


class VersionConflictError(Exception):
    """Nem ra khi header If-Match khong khop resourceVersion hien tai -
    dung cho optimistic concurrency theo dung contracts/openapi/
    customer-service.yaml (parameter IfMatch, response 409 Conflict)."""

    def __init__(self, customer_id: str, expected: int, provided: int):
        self.customer_id = customer_id
        self.expected = expected
        self.provided = provided
        super().__init__(
            f"If-Match khong khop: khach hang {customer_id} dang o "
            f"resourceVersion={expected}, request gui If-Match={provided}"
        )


class InvalidIfMatchError(Exception):
    """Header If-Match sai dinh dang - spec yeu cau dung pattern ^\"[0-9]+\"$."""

    def __init__(self, raw_value: str | None):
        self.raw_value = raw_value
        super().__init__(f"Header If-Match khong hop le: {raw_value!r}")
