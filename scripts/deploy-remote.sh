#!/usr/bin/env bash
#
# Runs ON THE VPS. GitHub Actions pipes this file into `bash -s` over SSH
# (see .github/workflows/deploy.yml). It can also be run by hand:
#
#   APP_DIR=/opt/nurse-scheduler GIT_REF=main ./scripts/deploy-remote.sh
#
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/nurse-scheduler}"
GIT_REF="${GIT_REF:-main}"
HEALTH_RETRIES="${HEALTH_RETRIES:-30}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-nurse_postgres}"

cd "$APP_DIR"

if [ ! -f .env ]; then
  echo "ERROR: $APP_DIR/.env is missing." >&2
  echo "  Create it from the template before the first deployment:" >&2
  echo "    cp .env.example .env && nano .env" >&2
  exit 1
fi

# --- backup ---------------------------------------------------------------
# There is nothing to back up on the very first deployment, so the absence of
# a running database is not an error. When the database *is* running the
# backup is mandatory and a failure aborts the deployment.
echo "== backup before deploy =="
if docker ps --format '{{.Names}}' | grep -qx "$POSTGRES_CONTAINER"; then
  # Invoked through bash so a checkout that lost the executable bit (git on
  # Windows does not record it) still deploys instead of dying with exit 126.
  bash ./scripts/backup.sh
else
  echo "  '$POSTGRES_CONTAINER' is not running - first deployment, nothing to back up."
fi

# --- code -----------------------------------------------------------------
echo "== fetching $GIT_REF =="
git fetch --all --prune
git checkout --detach "$GIT_REF"

# --- TLS ------------------------------------------------------------------
# nginx refuses to start without them, and it would fail long after the
# backend looked fine - say so up front instead.
if [ ! -s nginx/certs/fullchain.pem ] || [ ! -s nginx/certs/privkey.pem ]; then
  echo "ERROR: TLS certificate missing in $APP_DIR/nginx/certs/." >&2
  echo "  Expected fullchain.pem and privkey.pem (see README -> HTTPS i domena)." >&2
  echo "  For a first smoke test a self-signed pair is enough:" >&2
  echo "    ./scripts/dev-certs.sh your-domain.example" >&2
  exit 1
fi

# --- build and start ------------------------------------------------------
echo "== building images =="
docker compose build

echo "== starting (migrations run in the backend entrypoint) =="
docker compose up -d --remove-orphans

# --- health ---------------------------------------------------------------
# A container without a healthcheck only has to be running; one with a
# healthcheck has to report healthy.
wait_for() {
  local name="$1" retries="${2:-$HEALTH_RETRIES}" state health
  for _ in $(seq 1 "$retries"); do
    state="$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null | tr -d '\r\n')"
    health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
              "$name" 2>/dev/null | tr -d '\r\n')"
    state="${state:-missing}"
    health="${health:-none}"
    [ "$health" = "healthy" ] && return 0
    [ "$health" = "none" ] && [ "$state" = "running" ] && return 0
    sleep 5
  done
  echo "ERROR: $name is not ready (state=$state health=$health)" >&2
  docker logs --tail 80 "$name" >&2 || true
  return 1
}

echo "== waiting for the containers =="
wait_for nurse_postgres 24
wait_for nurse_backend "$HEALTH_RETRIES"
wait_for nurse_frontend 12
wait_for nurse_nginx 12

echo "== smoke test =="
docker compose exec -T backend curl -fsS http://127.0.0.1:8000/api/health
echo

echo "== pruning dangling images =="
docker image prune -f >/dev/null

docker compose ps
echo "== deployed $(git rev-parse --short HEAD) =="
