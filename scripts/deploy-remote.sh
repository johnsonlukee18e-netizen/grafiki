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

# --- TLS ------------------------------------------------------------------
# Read one setting without sourcing .env (which would execute it).
TLS_TERMINATION="$(sed -n 's/^[[:space:]]*TLS_TERMINATION[[:space:]]*=[[:space:]]*//p' .env \
                   | tail -1 | tr -d '"'"'"'[:space:]')"
TLS_TERMINATION="${TLS_TERMINATION:-container}"

if [ "$TLS_TERMINATION" = "host" ]; then
  echo "== TLS is terminated by the host proxy - skipping the certificate check =="
# nginx refuses to start without them, and it would fail long after the
# backend looked fine - say so up front instead.
elif [ ! -s nginx/certs/fullchain.pem ] || [ ! -s nginx/certs/privkey.pem ]; then
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
# tee keeps the progress visible; PIPESTATUS carries the real exit code, which
# a plain pipe would swallow.
set +e
docker compose up -d --remove-orphans 2>&1 | tee /tmp/nurse-up.log
up_code=${PIPESTATUS[0]}
set -e
if [ "$up_code" -ne 0 ]; then
  if grep -q 'address already in use' /tmp/nurse-up.log; then
    echo "ERROR: another service on this host already owns port 80 or 443." >&2
    echo "  This stack ships its own nginx container, so a distribution web" >&2
    echo "  server has to give the port back. Find the owner with:" >&2
    echo "    ss -tlnp '( sport = :80 or sport = :443 )'" >&2
    echo "  and disable it (disable, not just stop - it would return on reboot):" >&2
    echo "    systemctl disable --now nginx" >&2
    echo "    systemctl disable --now apache2" >&2
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
wait_for nurse_nginx 12

echo "== smoke test =="
docker compose exec -T backend curl -fsS http://127.0.0.1:8000/api/health
echo

echo "== pruning dangling images =="
docker image prune -f >/dev/null

docker compose ps
echo "== deployed $(git rev-parse --short HEAD) =="
