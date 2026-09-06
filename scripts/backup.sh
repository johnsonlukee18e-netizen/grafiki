#!/usr/bin/env bash
#
# PostgreSQL backup for the nurse scheduler.
#
#   ./scripts/backup.sh                 # dump into ./backups
#   BACKUP_DIR=/srv/backups ./scripts/backup.sh
#   RETENTION_DAYS=30 ./scripts/backup.sh
#
# Restore instructions are in README.md ("Kopie zapasowe").
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
CONTAINER="${POSTGRES_CONTAINER:-nurse_postgres}"

# Credentials come from the project .env (never hardcode them here).
if [[ -f "$PROJECT_DIR/.env" ]]; then
  # shellcheck disable=SC1091
  set -a && source "$PROJECT_DIR/.env" && set +a
fi

DB_USER="${POSTGRES_USER:-nurse}"
DB_NAME="${POSTGRES_DB:-nurse}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
TARGET="$BACKUP_DIR/nurse_${DB_NAME}_${STAMP}.sql.gz"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "ERROR: container '$CONTAINER' is not running." >&2
  exit 1
fi

echo "[backup] dumping $DB_NAME from $CONTAINER -> $TARGET"
# --clean --if-exists makes the dump restorable onto an existing database.
docker exec "$CONTAINER" pg_dump \
    --username="$DB_USER" \
    --dbname="$DB_NAME" \
    --clean --if-exists --no-owner --no-privileges \
  | gzip -9 > "$TARGET"

if [[ ! -s "$TARGET" ]]; then
  echo "ERROR: the dump is empty - backup failed." >&2
  rm -f "$TARGET"
  exit 1
fi

# Fail loudly if the archive is corrupt rather than discovering it at restore.
gzip -t "$TARGET"

chmod 600 "$TARGET"
echo "[backup] OK: $(du -h "$TARGET" | cut -f1) $TARGET"

echo "[backup] removing dumps older than ${RETENTION_DAYS} days"
find "$BACKUP_DIR" -name 'nurse_*.sql.gz' -type f -mtime "+${RETENTION_DAYS}" -print -delete

echo "[backup] done"
