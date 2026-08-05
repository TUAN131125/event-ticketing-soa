"""Loi thuoc domain - khong phu thuoc HTTP status code."""


class CustomerNotFoundError(Exception):
    def __init__(self, customer_id: str):
        self.customer_id = customer_id
        super().__init__(f"Khong tim thay khach hang: {customer_id}")


class DuplicateEmailError(Exception):
    def __init__(self, email: str):
        self.email = email
        super().__init__(f"Email da ton tai: {email}")


class PreconditionFailedError(Exception):
    """Raised when If-Match does not match the current resource version."""


class IdentityMappingConflictError(Exception):
    """Raised when either side of an identity mapping is already linked."""
