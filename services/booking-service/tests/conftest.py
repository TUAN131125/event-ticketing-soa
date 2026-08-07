"""Test-session environment for the Booking suites.

app/main.py builds a module-level application at import time, so the Service JWT settings
must exist in the environment before any test module imports it. The values point at the
per-session test keypair in tests/service_jwt.py - never at production key material.
"""

import os

from tests.service_jwt import AUDIENCE, CALLER, ISSUER, public_key_base64

os.environ.setdefault("BOOKING_APP_ENV", "test")
os.environ.setdefault("BOOKING_SERVICE_JWT_ISSUER", ISSUER)
os.environ.setdefault("BOOKING_SERVICE_JWT_AUDIENCE", AUDIENCE)
os.environ.setdefault("BOOKING_SERVICE_JWT_PUBLIC_KEY_BASE64", public_key_base64())
os.environ.setdefault("BOOKING_ALLOWED_SERVICE_SUBJECTS", CALLER)
