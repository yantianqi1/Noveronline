#!/bin/sh
set -eu

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
compose_file="$script_dir/../docker-compose.yml"
timeout_seconds="${COMPOSE_HEALTH_TIMEOUT_SECONDS:-300}"
services="postgres redis temporal minio api web agent-runtime agent-runtime-seed agent-runtime-asset agent-runtime-graph agent-runtime-worldline agent-runtime-character agent-runtime-reviewer agent-runtime-writer-planning legacy-import-worker pi-agent-runtime worker-readiness"

diagnose() {
  echo "compose readiness failed; sanitized status and recent logs follow" >&2
  docker compose -f "$compose_file" ps -a >&2 || true
  docker compose -f "$compose_file" logs --no-color --tail=40 $services 2>&1 \
    | "$script_dir/redact-compose-diagnostics.sh" >&2 || true
}

service_ready() {
  container_id="$(docker compose -f "$compose_file" ps -q "$1")"
  [ -n "$container_id" ] || return 1
  state="$(docker inspect -f '{{.State.Status}}' "$container_id" 2>/dev/null)"
  health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$container_id" 2>/dev/null)"
  [ "$state" = "running" ] && [ "$health" = "healthy" ]
}

trap diagnose INT TERM HUP
deadline=$(( $(date +%s) + timeout_seconds ))
while :; do
  pending=""
  for service in $services; do
    if ! service_ready "$service"; then
      pending="$pending $service"
    fi
  done
  if [ -z "$pending" ]; then
    break
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "timed out waiting for:$pending" >&2
    diagnose
    exit 1
  fi
  sleep 3
done

docker compose -f "$compose_file" exec -T postgres \
  pg_isready -q -U "${POSTGRES_USER:-mirofish}" -d "${POSTGRES_DB:-mirofish}"
[ "$(docker compose -f "$compose_file" exec -T redis redis-cli ping)" = "PONG" ]
docker compose -f "$compose_file" exec -T temporal \
  temporal operator cluster health --address temporal:7233 >/dev/null
docker compose -f "$compose_file" exec -T minio \
  curl -fsS http://127.0.0.1:9000/minio/health/ready >/dev/null
docker compose -f "$compose_file" exec -T api \
  wget -q -O - http://127.0.0.1:8080/healthz | grep -q '"status":"ok"'
docker compose -f "$compose_file" exec -T web \
  wget -q --spider http://127.0.0.1:3000/login

echo "compose health ready: API, Web, PostgreSQL, Temporal, MinIO, Redis, Pi and Python worker queues"
