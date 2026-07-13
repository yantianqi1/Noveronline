#!/bin/sh
set -eu

: "${BACKUP_ROOT:?BACKUP_ROOT is required}"
: "${RESTORE_DRILL_DISPOSABLE:?RESTORE_DRILL_DISPOSABLE must be set}"
[ "$RESTORE_DRILL_DISPOSABLE" = "1" ] || {
  echo "restore drill refused: target must be explicitly disposable" >&2
  exit 1
}

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
before_rows="$(docker compose -f "$script_dir/../docker-compose.yml" -f "${MIROFISH_COMPOSE_OVERRIDE:-$script_dir/../compose.staging.yml}" exec -T postgres psql -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FROM projects")"
"$script_dir/backup-postgres-minio.sh"
latest="$(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d | sort | tail -1)"
[ -n "$latest" ]
RESTORE_BACKUP_DIR="$latest" RESTORE_CONFIRM=destroy-disposable-state \
  RESTORE_DRILL_DISPOSABLE=1 "$script_dir/restore-postgres-minio.sh"
after_rows="$(docker compose -f "$script_dir/../docker-compose.yml" -f "${MIROFISH_COMPOSE_OVERRIDE:-$script_dir/../compose.staging.yml}" exec -T postgres psql -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FROM projects")"
[ "$before_rows" = "$after_rows" ] || { echo "restore verification failed: project row count differs" >&2; exit 1; }

echo "backup/restore drill passed: hashes, PostgreSQL rows and object archive restored"
