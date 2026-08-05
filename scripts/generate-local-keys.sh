#!/bin/sh
set -eu

secret_directory="${1:-local-secrets}"

if [ -e "$secret_directory/identity-private.pem" ] || \
   [ -e "$secret_directory/esb-internal-private.pem" ] || \
   [ -e "$secret_directory/esb-ws-ticket-private.pem" ]; then
  printf '%s\n' "Refusing to overwrite existing local signing keys in $secret_directory" >&2
  exit 1
fi

mkdir -p "$secret_directory"
umask 077

generate_pair() {
  name="$1"
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
    -out "$secret_directory/$name-private.pem"
  openssl rsa -pubout -in "$secret_directory/$name-private.pem" \
    -out "$secret_directory/$name-public.pem"
}

generate_pair identity
generate_pair esb-internal
generate_pair esb-ws-ticket
printf '%s\n' "Created local signing keys in $secret_directory"
