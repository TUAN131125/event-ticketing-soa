#!/bin/sh
set -eu

private_key_path="${IDENTITY_PRIVATE_KEY_PATH:-/app/keys/private.pem}"
public_key_path="${IDENTITY_PUBLIC_KEY_PATH:-/app/keys/public.pem}"

if [ ! -s "$private_key_path" ] || [ ! -s "$public_key_path" ]; then
  python scripts/generate_keys.py \
    --private-key "$private_key_path" \
    --public-key "$public_key_path"
fi

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
