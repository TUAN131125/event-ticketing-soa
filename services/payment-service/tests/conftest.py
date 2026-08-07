"""Test-session environment for the Payment suites.

app/main.py builds a module-level application at import time, so the Service JWT settings
must exist in the environment before any test module imports it. The values point at the
per-session test keypair in tests/service_jwt.py - never at production key material.
"""

import os

from tests.service_jwt import AUDIENCE, CALLER, ISSUER, public_key_base64

# "local" keeps the module-level app in app/main.py constructible without production-grade
# secrets. Individual suites still build their own Settings via tests.factories.
os.environ.setdefault("PAYMENT_APP_ENV", "local")
os.environ.setdefault("PAYMENT_SERVICE_JWT_ISSUER", ISSUER)
os.environ.setdefault("PAYMENT_SERVICE_JWT_AUDIENCE", AUDIENCE)
os.environ.setdefault("PAYMENT_SERVICE_JWT_PUBLIC_KEY_BASE64", public_key_base64())
os.environ.setdefault("PAYMENT_ALLOWED_SERVICE_SUBJECTS", CALLER)
