#!/bin/sh
# Wait for PostgreSQL, apply migrations, then start the API.
set -eu

echo "[entrypoint] waiting for the database..."
python - <<'PY'
import sys
import time

from sqlalchemy import create_engine, text

from app.config import settings

deadline = time.time() + 120
last_error = None
while time.time() < deadline:
    try:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
        print("[entrypoint] database is ready")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001 - we retry on anything
        last_error = exc
        time.sleep(2)

print(f"[entrypoint] database unreachable after 120s: {last_error}", file=sys.stderr)
sys.exit(1)
PY

echo "[entrypoint] applying migrations..."
alembic upgrade head

if [ "${SEED_ON_START:-false}" = "true" ]; then
  echo "[entrypoint] seeding base data..."
  if [ "${SEED_DEMO:-false}" = "true" ]; then
    python -m app.seed --demo
  else
    python -m app.seed
  fi
fi

echo "[entrypoint] starting: $*"
exec "$@"
