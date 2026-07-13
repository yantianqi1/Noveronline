#!/bin/sh
set -eu

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
compose_file="$script_dir/../docker-compose.yml"
api_url="${COMPOSE_RECOVERY_API_URL:-http://127.0.0.1:${API_PORT:-3888}}"
old_password="Mf-old-$(openssl rand -hex 16)"
new_password="Mf-new-$(openssl rand -hex 16)"
tenant_id="b3000000-0000-4000-8000-000000000001"
foreign_tenant_id="b3000000-0000-4000-8000-000000000002"
foreign_project_id="c3000000-0000-4000-8000-000000000002"
temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/mirofish-recovery.XXXXXX")"
chmod 700 "$temp_dir"
proof_secret="${MIROFISH_RECOVERY_CLIENT_PROOF_SECRET:-0123456789abcdef0123456789abcdef}"
client_hash="$(openssl rand -hex 32)"

cleanup() {
  rm -rf "$temp_dir"
  if [ "${COMPOSE_RECOVERY_KEEP_FIXTURE:-0}" != "1" ]; then
    "$script_dir/cleanup-compose-auth-recovery-fixture.sh" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM HUP

status_is() {
  expected="$1"
  shift
  actual="$(curl --silent --show-error --output "$temp_dir/response" --write-out '%{http_code}' "$@")"
  if [ "$actual" != "$expected" ]; then
    echo "recovery request failed: expected HTTP $expected, received $actual" >&2
    return 1
  fi
}

write_login_body() {
  printf '%s' "{\"email\":\"compose-auth@example.test\",\"password\":\"$1\"}" >"$temp_dir/login.json"
  chmod 600 "$temp_dir/login.json"
}

signed_client_proof() {
  timestamp="$(date +%s)"
  message="v1:$timestamp:$client_hash"
  signature="$(printf '%s' "$message" | openssl dgst -sha256 -hmac "$proof_secret" -r | awk '{print $1}')"
  printf '%s:%s' "$message" "$signature"
}

login() {
  jar="$1"
  write_login_body "$2"
  status_is 201 --request POST --header 'Content-Type: application/json' \
    --header "X-Mirofish-Recovery-Client: $(signed_client_proof)" \
    --data-binary "@$temp_dir/login.json" --cookie-jar "$jar" "$api_url/v1/auth/login"
  chmod 600 "$jar"
  grep -q 'mirofish_session' "$jar"
}

csrf_header() {
  jar="$1"
  header_file="$2"
  status_is 200 --cookie "$jar" "$api_url/v1/auth/csrf-token"
  csrf="$(sed -n 's/.*"csrf_token":"\([^"]*\)".*/\1/p' "$temp_dir/response")"
  [ -n "$csrf" ] || return 1
  printf 'X-CSRF-Token: %s\n' "$csrf" >"$header_file"
  chmod 600 "$header_file"
}

wait_healthy() {
  service="$1"
  for _ in $(seq 1 120); do
    container_id="$(docker compose -f "$compose_file" ps -q "$service")"
    if [ -n "$container_id" ] && [ "$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$container_id" 2>/dev/null)" = "healthy" ]; then
      return 0
    fi
    sleep 1
  done
  echo "recovery dependency did not become healthy: $service" >&2
  return 1
}

assert_recovery_privileges_converged() {
  direct_grants="$(docker compose -f "$compose_file" exec -T postgres \
    psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:-mirofish}" -d "${POSTGRES_DB:-mirofish}" -Atc \
    "SELECT count(*) FROM information_schema.role_table_grants WHERE grantee = 'mirofish_app' AND table_schema = 'public' AND table_name IN ('password_reset_tokens', 'password_reset_delivery_attempts', 'password_reset_delivery_outbox', 'auth_security_audit_logs') AND privilege_type IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE')")"
  if [ "$direct_grants" != "0" ]; then
    echo "recovery sensitive-table direct grants drifted" >&2
    return 1
  fi
}

echo "checking existing compose readiness"
"$script_dir/check-compose-health.sh"
assert_recovery_privileges_converged
COMPOSE_AUTH_FIXTURE_PASSWORD="$old_password" "$script_dir/prepare-compose-auth-recovery-fixture.sh"

login "$temp_dir/session-one.jar" "$old_password"
login "$temp_dir/session-two.jar" "$old_password"
csrf_header "$temp_dir/session-one.jar" "$temp_dir/csrf-one.header"
status_is 403 --cookie "$temp_dir/session-one.jar" --header "@$temp_dir/csrf-one.header" \
  --header "X-Tenant-Id: $foreign_tenant_id" \
  "$api_url/v1/projects/$foreign_project_id/assets"

workflow_id="compose-recovery-$(date +%s)"
workflow_input="{\"tenant_id\":\"$tenant_id\",\"project_id\":null,\"run_id\":\"$workflow_id\",\"workflow_type\":\"hello_agent\",\"actor_user_id\":null,\"module_key\":null,\"trace_id\":\"$workflow_id\",\"permissions\":{\"hello_agent\":[\"run\"]}}"
docker compose -f "$compose_file" stop agent-runtime >/dev/null
docker compose -f "$compose_file" exec -T temporal temporal workflow start \
  --address temporal:7233 --task-queue maintenance --type HelloAgentWorkflow \
  --workflow-id "$workflow_id" --input "$workflow_input" --output none
queued="$(docker compose -f "$compose_file" exec -T temporal temporal workflow describe \
  --address temporal:7233 --workflow-id "$workflow_id" --output json)"
printf '%s' "$queued" | grep -qi 'RUNNING'

echo "restarting compose stateful and application services with persistent volumes"
docker compose -f "$compose_file" restart postgres redis temporal minio >/dev/null
for service in postgres redis temporal minio; do
  wait_healthy "$service"
done
docker compose -f "$compose_file" up -d --no-deps --force-recreate api web agent-runtime agent-runtime-seed \
  agent-runtime-asset agent-runtime-graph agent-runtime-worldline agent-runtime-character \
  agent-runtime-reviewer agent-runtime-writer-planning legacy-import-worker pi-agent-runtime worker-readiness >/dev/null
docker compose -f "$compose_file" up -d >/dev/null
"$script_dir/check-compose-health.sh"
assert_recovery_privileges_converged

status_is 200 --cookie "$temp_dir/session-one.jar" "$api_url/v1/me"
for _ in $(seq 1 40); do
  recovered="$(docker compose -f "$compose_file" exec -T temporal temporal workflow describe \
    --address temporal:7233 --workflow-id "$workflow_id" --output json 2>/dev/null || true)"
  if printf '%s' "$recovered" | grep -qi 'COMPLETED'; then
    break
  fi
  sleep 2
done
printf '%s' "$recovered" | grep -qi 'COMPLETED'

cp "$temp_dir/session-one.jar" "$temp_dir/session-old.jar"
status_is 204 --request POST --cookie "$temp_dir/session-one.jar" --cookie-jar "$temp_dir/session-one.jar" \
  --header "@$temp_dir/csrf-one.header" "$api_url/v1/auth/session/rotation"
status_is 401 --cookie "$temp_dir/session-old.jar" "$api_url/v1/me"
status_is 200 --cookie "$temp_dir/session-one.jar" "$api_url/v1/me"
csrf_header "$temp_dir/session-one.jar" "$temp_dir/csrf-rotated.header"
status_is 204 --request DELETE --cookie "$temp_dir/session-one.jar" \
  --header "@$temp_dir/csrf-rotated.header" "$api_url/v1/auth/session"
status_is 401 --cookie "$temp_dir/session-one.jar" "$api_url/v1/me"

csrf_header "$temp_dir/session-two.jar" "$temp_dir/csrf-two.header"
printf '%s' "{\"current_password\":\"$old_password\",\"new_password\":\"$new_password\"}" >"$temp_dir/password.json"
chmod 600 "$temp_dir/password.json"
status_is 204 --request POST --cookie "$temp_dir/session-two.jar" \
  --header "@$temp_dir/csrf-two.header" --header 'Content-Type: application/json' \
  --data-binary "@$temp_dir/password.json" "$api_url/v1/auth/password/change"
status_is 401 --cookie "$temp_dir/session-two.jar" "$api_url/v1/me"
login "$temp_dir/session-final.jar" "$new_password"
assert_recovery_privileges_converged

echo "compose recovery passed: persisted auth, CSRF, tenant denial, rotation, logout, password revocation and queued workflow recovery"
