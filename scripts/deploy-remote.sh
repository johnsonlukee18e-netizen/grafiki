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
if ! git fetch --all --prune 2>/tmp/nurse-fetch.err; then
  sed 's/^/  /' /tmp/nurse-fetch.err >&2
  if grep -q 'could not read Username' /tmp/nurse-fetch.err; then
    echo "ERROR: this server cannot authenticate to GitHub." >&2
    echo "  The repository is private and was cloned over HTTPS, but a deployment" >&2
    echo "  runs without a terminal, so git has no way to ask for credentials." >&2
    echo "  Switch the remote to a read-only deploy key:" >&2
    echo "    ssh-keygen -t ed25519 -C 'grafiki-repo' -f ~/.ssh/github_repo -N ''" >&2
    echo "    cat ~/.ssh/github_repo.pub   # add it under Settings -> Deploy keys" >&2
    echo "    printf 'Host github.com\\n  IdentityFile ~/.ssh/github_repo\\n  IdentitiesOnly yes\\n' >> ~/.ssh/config" >&2
    echo "    ssh -T git@github.com        # accept the host key once" >&2
    echo "    git remote set-url origin git@github.com:OWNER/REPO.git" >&2
  fi
  exit 1
fi
git checkout --detach "$GIT_REF"

# --- build and start ------------------------------------------------------
echo "== building images =="
docker compose build

echo "== starting (migrations run in the backend entrypoint) =="
# tee keeps the progress visible; PIPESTATUS carries the real exit code, which
# a plain pipe would swallow.
set +e
docker compose up -d --remove-orphans 2>&1 | tee /tmp/nurse-up.log
up_code=${PIPESTATUS[0]}
set -e
if [ "$up_code" -ne 0 ]; then
  if grep -q 'address already in use' /tmp/nurse-up.log; then
    echo "ERROR: BACKEND_PORT or FRONTEND_PORT is already taken on this host." >&2
    echo "  This stack only binds to 127.0.0.1, never to 80/443, so it should" >&2
    echo "  never collide with an existing web server - but another instance of" >&2
    echo "  this same stack, or something else on the same port, still can:" >&2
    echo "    ss -tlnp '( sport = :8000 or sport = :8080 )'" >&2
    echo "  set BACKEND_PORT / FRONTEND_PORT in .env to free ones and retry." >&2
  fi
  exit "$up_code"
fi

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

echo "== smoke test =="
docker compose exec -T backend curl -fsS http://127.0.0.1:8000/api/health
echo

echo "== pruning dangling images =="
docker image prune -f >/dev/null

docker compose ps
echo "== deployed $(git rev-parse --short HEAD) =="
