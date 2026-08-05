#!/bin/sh
set -eu

create_database_from_url() {
  database_url="$1"
  authority="${database_url#*://}"
  credentials="${authority%%@*}"
  role_name="${credentials%%:*}"
  role_password="${credentials#*:}"
  database_name="${authority#*/}"
  database_name="${database_name%%\?*}"

  if [ -z "$role_name" ] || [ "$role_password" = "$credentials" ] || [ -z "$database_name" ]; then
    printf '%s\n' "Invalid service database URL: expected scheme://user:password@host/database" >&2
    exit 1
  fi

  psql --set=ON_ERROR_STOP=1 --set=role_name="$role_name" --set=role_password="$role_password" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'role_name', :'role_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role_name') \gexec
SQL

  createdb --owner="$role_name" "$database_name"
}

: "${IDENTITY_DATABASE_URL:?IDENTITY_DATABASE_URL is required}"
: "${CUSTOMER_DATABASE_URL:?CUSTOMER_DATABASE_URL is required}"
: "${EVENT_DATABASE_URL:?EVENT_DATABASE_URL is required}"
: "${SEAT_DATABASE_URL:?SEAT_DATABASE_URL is required}"
: "${BOOKING_DATABASE_URL:?BOOKING_DATABASE_URL is required}"
: "${PAYMENT_DATABASE_URL:?PAYMENT_DATABASE_URL is required}"
: "${TICKET_DATABASE_URL:?TICKET_DATABASE_URL is required}"
: "${NOTIFICATION_DATABASE_URL:?NOTIFICATION_DATABASE_URL is required}"
: "${ESB_DATABASE_URL:?ESB_DATABASE_URL is required}"

create_database_from_url "$IDENTITY_DATABASE_URL"
create_database_from_url "$CUSTOMER_DATABASE_URL"
create_database_from_url "$EVENT_DATABASE_URL"
create_database_from_url "$SEAT_DATABASE_URL"
create_database_from_url "$BOOKING_DATABASE_URL"
create_database_from_url "$PAYMENT_DATABASE_URL"
create_database_from_url "$TICKET_DATABASE_URL"
create_database_from_url "$NOTIFICATION_DATABASE_URL"
create_database_from_url "$ESB_DATABASE_URL"
