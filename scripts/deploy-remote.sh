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

cd "$APP_DIR"

echo "== backup before deploy =="
# A failing backup stops the deployment rather than being ignored.
# Invoked through bash so a checkout that lost the executable bit (Windows
# commits do not record it) still deploys instead of dying with exit 126.
bash ./scripts/backup.sh

echo "== fetching $GIT_REF =="
git fetch --all --prune
git checkout --detach "$GIT_REF"

echo "== building images =="
docker compose build

echo "== starting (migrations run in the backend entrypoint) =="
docker compose up -d --remove-orphans

echo "== waiting for the API to become healthy =="
status="starting"
for _ in $(seq 1 "$HEALTH_RETRIES"); do
  status="$(docker inspect -f '{{.State.Health.Status}}' nurse_backend 2>/dev/null || echo starting)"
  [ "$status" = "healthy" ] && break
  sleep 5
done

if [ "$status" != "healthy" ]; then
  echo "ERROR: backend did not become healthy (status: $status)" >&2
  docker compose logs --tail 100 backend >&2
  exit 1
fi

echo "== smoke test =="
docker compose exec -T backend curl -fsS http://127.0.0.1:8000/api/health
echo

echo "== pruning dangling images =="
docker image prune -f >/dev/null

echo "== deployed $(git rev-parse --short HEAD) =="
