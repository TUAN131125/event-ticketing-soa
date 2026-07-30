"""Create or promote an administrator using explicit operator input."""

from __future__ import annotations

import argparse
import getpass
import os

from app.application.service import IdentityService
from app.config import get_settings
from app.domain.value_objects import RequestContext
from app.infrastructure.database.session import get_session_factory
from app.security.passwords import PasswordService
from app.security.tokens import TokenService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default=os.getenv("IDENTITY_ADMIN_EMAIL"))
    args = parser.parse_args()
    email = args.email or input("Admin email: ").strip()
    password = os.getenv("IDENTITY_ADMIN_PASSWORD") or getpass.getpass(
        "Admin password: "
    )
    settings = get_settings()
    service = IdentityService(
        settings,
        get_session_factory(settings),
        PasswordService(settings),
        TokenService(settings),
    )
    context = RequestContext(
        correlation_id="bootstrap-admin",
        trace_id="0" * 32,
        client_ip="operator",
        user_agent="bootstrap-admin",
    )
    user = service.bootstrap_admin(email, password, context)
    print(f"Admin ready: {user.user_id} ({user.email})")


if __name__ == "__main__":
    main()
