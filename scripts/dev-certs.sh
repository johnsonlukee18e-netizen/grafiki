#!/usr/bin/env bash
# Generate a self-signed certificate so the full HTTPS stack can be tested
# locally. NEVER use these files in production - use Let's Encrypt (see README).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="$(dirname "$SCRIPT_DIR")/nginx/certs"
DOMAIN="${1:-localhost}"

mkdir -p "$CERT_DIR"

# Git Bash on Windows would rewrite "/CN=..." into a path; exclude just that
# argument (a plain MSYS_NO_PATHCONV=1 would break the output paths too).
export MSYS2_ARG_CONV_EXCL="/CN=;subjectAltName="

openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
  -keyout "$CERT_DIR/privkey.pem" \
  -out "$CERT_DIR/fullchain.pem" \
  -subj "/CN=$DOMAIN" \
  -addext "subjectAltName=DNS:$DOMAIN,DNS:localhost,IP:127.0.0.1"

chmod 600 "$CERT_DIR/privkey.pem"
echo "Self-signed certificate for '$DOMAIN' written to $CERT_DIR"
