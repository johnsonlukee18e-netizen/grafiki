#!/usr/bin/env bash
#
# Refresh nginx/cloudflare-real-ip.conf from Cloudflare's published ranges.
#
#   ./scripts/update-cloudflare-ips.sh
#   sudo cp nginx/cloudflare-real-ip.conf /etc/nginx/conf.d/
#   sudo nginx -t && sudo systemctl reload nginx
#
# Cloudflare adds ranges from time to time. A stale list is not a cosmetic
# problem: requests arriving from a range that is missing here keep the
# Cloudflare address as $remote_addr, so those visitors all share one rate
# limiting bucket and the access log records the proxy instead of the client.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-$(dirname "$SCRIPT_DIR")/nginx/cloudflare-real-ip.conf}"

fetch() {
  curl -fsS --max-time 20 "$1"
}

echo "[cloudflare] downloading current ranges..."
v4="$(fetch https://www.cloudflare.com/ips-v4)"
v6="$(fetch https://www.cloudflare.com/ips-v6)"

# Refuse to write a truncated file - an empty list would silently disable the
# real-IP recovery instead of failing loudly.
if [ "$(printf '%s\n' "$v4" | grep -c '/')" -lt 5 ] \
   || [ "$(printf '%s\n' "$v6" | grep -c '/')" -lt 3 ]; then
  echo "ERROR: the downloaded list looks truncated - keeping the existing file." >&2
  exit 1
fi

tmp="$(mktemp)"
{
  echo "# Restores the real visitor address when traffic arrives through Cloudflare."
  echo "# Without it \$remote_addr is a Cloudflare address for every request, so any"
  echo "# rate limiting or logging on the host would treat all visitors as one client."
  echo "#"
  echo "# Include it inside the http {} block (or a server {} block) of the host nginx:"
  echo "#     include /etc/nginx/conf.d/cloudflare-real-ip.conf;"
  echo "#"
  echo "# Cloudflare changes these ranges occasionally - refresh with"
  echo "#     ./scripts/update-cloudflare-ips.sh"
  echo "# Generated from https://www.cloudflare.com/ips-v4 and /ips-v6 on $(date -u +%Y-%m-%d)"
  echo ""
  printf '%s\n' "$v4" | while read -r range; do
    [ -n "$range" ] && echo "set_real_ip_from $range;"
  done
  echo ""
  printf '%s\n' "$v6" | while read -r range; do
    [ -n "$range" ] && echo "set_real_ip_from $range;"
  done
  echo ""
  echo "real_ip_header CF-Connecting-IP;"
} > "$tmp"

mv "$tmp" "$TARGET"
echo "[cloudflare] wrote $(grep -c set_real_ip_from "$TARGET") ranges to $TARGET"
echo "[cloudflare] remember to copy it to the host nginx and reload."
