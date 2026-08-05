#!/bin/sh
set -eu

material_directory="/tmp/identity-signing"
private_target="$material_directory/private.pem"
public_target="$material_directory/public.pem"

fail() {
  printf '%s\n' "identity-service startup failed: $1" >&2
  exit 1
}

materialize_key() {
  label="$1"
  source_path="$2"
  encoded_value="$3"
  target_path="$4"

  if [ -n "$source_path" ] && [ -n "$encoded_value" ]; then
    fail "provide only one ${label} key source: file path or Base64"
  fi
  if [ -n "$source_path" ]; then
    [ -s "$source_path" ] || fail "${label} key file is missing or empty: $source_path"
    cp "$source_path" "$target_path"
  elif [ -n "$encoded_value" ]; then
    if ! printf '%s' "$encoded_value" | base64 -d >"$target_path"; then
      fail "${label} key Base64 value is invalid"
    fi
    [ -s "$target_path" ] || fail "${label} key Base64 value decoded to an empty file"
  else
    fail "${label} signing key is required"
  fi
  chmod 0600 "$target_path"
}

umask 077
mkdir -p "$material_directory"

materialize_key \
  "private" \
  "${IDENTITY_PRIVATE_KEY_FILE:-${IDENTITY_PRIVATE_KEY_PATH:-}}" \
  "${IDENTITY_PRIVATE_KEY_BASE64:-}" \
  "$private_target"
materialize_key \
  "public" \
  "${IDENTITY_PUBLIC_KEY_FILE:-${IDENTITY_PUBLIC_KEY_PATH:-}}" \
  "${IDENTITY_PUBLIC_KEY_BASE64:-}" \
  "$public_target"

export IDENTITY_PRIVATE_KEY_PATH="$private_target"
export IDENTITY_PUBLIC_KEY_PATH="$public_target"

exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8009 --proxy-headers
