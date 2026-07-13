#!/bin/sh
set -eu

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
compose_file="$script_dir/../docker-compose.yml"

docker compose -f "$compose_file" exec -T postgres \
  psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:-mirofish}" -d "${POSTGRES_DB:-mirofish}" <<'SQL' >/dev/null
BEGIN;
DELETE FROM tenants
WHERE tenant_id IN (
  'b3000000-0000-4000-8000-000000000001',
  'b3000000-0000-4000-8000-000000000002'
);
DELETE FROM users
WHERE user_id IN (
  'a3000000-0000-4000-8000-000000000001',
  'a3000000-0000-4000-8000-000000000002'
);
COMMIT;
SQL

echo "disposable compose auth and recovery fixture removed"
