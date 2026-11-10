#!/bin/sh
set -eu

usage() {
  cat <<'EOF'
Usage: run-live-test-stack.sh [--app] -- command [args...]

Runs a command against a disposable local Compose project. The project uses a
unique PostgreSQL database and named volumes, then is destroyed with `down -v`
on every exit path. --app also starts the API and Web services.
EOF
}

start_app=0
if [ "${1:-}" = "--app" ]; then
  start_app=1
  shift
fi
if [ "${1:-}" != "--" ]; then
  usage >&2
  exit 2
fi
shift
if [ "$#" -eq 0 ]; then
  usage >&2
  exit 2
fi

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
compose_file="$script_dir/../docker-compose.yml"
run_id="$(date +%s)_$$"

eval "$(python3 <<'PY'
import socket

names = (
    "POSTGRES_PORT", "REDIS_PORT", "TEMPORAL_PORT", "TEMPORAL_UI_PORT",
    "MINIO_API_PORT", "MINIO_CONSOLE_PORT", "API_PORT", "WEB_PORT",
)
sockets = []
try:
    for name in names:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sockets.append(sock)
        print(f"{name}={sock.getsockname()[1]}")
finally:
    for sock in sockets:
        sock.close()
PY
)"

export COMPOSE_PROJECT_NAME="mirofish-saas-live-$run_id"
export POSTGRES_DB="mirofish_test_$run_id"
export POSTGRES_PORT REDIS_PORT TEMPORAL_PORT TEMPORAL_UI_PORT
export MINIO_API_PORT MINIO_CONSOLE_PORT API_PORT WEB_PORT
export MIROFISH_DEPLOYMENT_ENV=local
export MIROFISH_ENABLE_DEVELOPMENT_AUTH=0
export TEMPORAL_CORS_ORIGINS="http://127.0.0.1:$WEB_PORT"

cleanup() {
  docker compose -f "$compose_file" -p "$COMPOSE_PROJECT_NAME" down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM

docker compose -f "$compose_file" -p "$COMPOSE_PROJECT_NAME" up -d --wait postgres redis temporal minio
docker compose -f "$compose_file" -p "$COMPOSE_PROJECT_NAME" run --rm schema-init
docker compose -f "$compose_file" -p "$COMPOSE_PROJECT_NAME" run --rm minio-init
docker compose -f "$compose_file" -p "$COMPOSE_PROJECT_NAME" exec -T postgres \
  psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:-mirofish}" -d postgres \
  -c "ALTER DATABASE \"$POSTGRES_DB\" SET \"mirofish.live_test\" = 'on'" >/dev/null

if [ "$start_app" -eq 1 ]; then
  # API readiness requires every workflow/activity poller. Start the workers
  # alongside API/Web so a fresh namespace can become ready.
  docker compose -f "$compose_file" -p "$COMPOSE_PROJECT_NAME" up -d --build --wait
fi

admin_url="postgresql://${POSTGRES_USER:-mirofish}:${POSTGRES_PASSWORD:-mirofish_dev_password}@127.0.0.1:$POSTGRES_PORT/$POSTGRES_DB?sslmode=disable&application_name=mirofish-live-test"
runtime_url="postgresql://${APP_DATABASE_USER:-mirofish_runtime}:${APP_DATABASE_PASSWORD:-mirofish_runtime_dev_password}@127.0.0.1:$POSTGRES_PORT/$POSTGRES_DB?sslmode=disable&application_name=mirofish-live-test"
export MIROFISH_LIVE_TEST_DATABASE_URL="$admin_url"
export MIROFISH_LIVE_TEST_RUNTIME_DATABASE_URL="$runtime_url"
export MIROFISH_LIVE_TEST_COMPOSE_PROJECT="$COMPOSE_PROJECT_NAME"
export MIROFISH_LIVE_TEST_POSTGRES_USER="${POSTGRES_USER:-mirofish}"

for variable in \
  MIROFISH_ASSET_CATALOG_LIVE_DATABASE_URL \
  MIROFISH_ASSET_DISTILLATION_LIVE_DATABASE_URL \
  MIROFISH_ASSET_REINDEX_LIVE_DATABASE_URL \
  MIROFISH_ASSET_SEARCH_LIVE_DATABASE_URL \
  MIROFISH_AUTH_LIVE_DATABASE_URL \
  MIROFISH_AUTH_RECOVERY_LIVE_DATABASE_URL \
  MIROFISH_CHARACTER_PROPOSAL_LIVE_DATABASE_URL \
  MIROFISH_COLLABORATION_LIVE_DATABASE_URL \
  MIROFISH_EMPTY_PROJECT_WRITER_LIVE_DATABASE_URL \
  MIROFISH_GRAPH_LIVE_DATABASE_URL \
  MIROFISH_LLM_ADMIN_LIVE_DATABASE_URL \
  MIROFISH_LLM_BINDINGS_LIVE_DATABASE_URL \
  MIROFISH_LLM_CATALOG_LIVE_DATABASE_URL \
  MIROFISH_LLM_LIVE_DATABASE_URL \
  MIROFISH_LLM_MODEL_SYNC_LIVE_DATABASE_URL \
  MIROFISH_LLM_SETTINGS_LIVE_DATABASE_URL \
  MIROFISH_MANUSCRIPT_WORKSPACE_LIVE_DATABASE_URL \
  MIROFISH_PI_WRITER_LIVE_DATABASE_URL \
  MIROFISH_REGISTRATION_LIVE_DATABASE_URL \
  MIROFISH_SEED_LIVE_DATABASE_URL \
  MIROFISH_SEED_RETRY_LIVE_DATABASE_URL \
  MIROFISH_WORLDLINE_LIVE_DATABASE_URL \
  MIROFISH_WORLDLINE_PREPARATION_LIVE_DATABASE_URL \
  MIROFISH_WRITER_EXPORT_LIVE_DATABASE_URL \
  MIROFISH_WRITER_LIVE_DATABASE_URL \
  MIROFISH_WRITER_WORKSPACE_LIVE_DATABASE_URL
do
  export "$variable=$admin_url"
done

"$@"
