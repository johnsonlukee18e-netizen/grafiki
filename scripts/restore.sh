#!/usr/bin/env bash
#
# Restore a dump created by scripts/backup.sh.
#
#   ./scripts/restore.sh backups/nurse_nurse_20260906_020000.sql.gz
#
# The application should be stopped first:
#   docker compose stop backend
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <backup.sql.gz>" >&2
  exit 2
fi

DUMP="$1"
[[ -f "$DUMP" ]] || { echo "ERROR: no such file: $DUMP" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONTAINER="${POSTGRES_CONTAINER:-nurse_postgres}"

if [[ -f "$PROJECT_DIR/.env" ]]; then
  # shellcheck disable=SC1091
  set -a && source "$PROJECT_DIR/.env" && set +a
fi
DB_USER="${POSTGRES_USER:-nurse}"
DB_NAME="${POSTGRES_DB:-nurse}"

echo "This will OVERWRITE the contents of database '$DB_NAME'."
read -r -p "Type the database name to confirm: " answer
[[ "$answer" == "$DB_NAME" ]] || { echo "Aborted."; exit 1; }

echo "[restore] loading $DUMP into $DB_NAME"
gunzip -c "$DUMP" | docker exec -i "$CONTAINER" psql \
    --username="$DB_USER" --dbname="$DB_NAME" --set ON_ERROR_STOP=on

echo "[restore] done - start the API again: docker compose up -d backend"
