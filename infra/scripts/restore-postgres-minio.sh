#!/bin/sh
set -eu

: "${RESTORE_BACKUP_DIR:?RESTORE_BACKUP_DIR is required}"
: "${RESTORE_CONFIRM:?RESTORE_CONFIRM is required}"
: "${RESTORE_DRILL_DISPOSABLE:?RESTORE_DRILL_DISPOSABLE is required}"
: "${MIROFISH_DEPLOYMENT_ENV:?MIROFISH_DEPLOYMENT_ENV is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${MIROFISH_OBJECT_STORAGE_BUCKET:?MIROFISH_OBJECT_STORAGE_BUCKET is required}"
[ "$RESTORE_CONFIRM" = "destroy-disposable-state" ] || {
  echo "restore refused: RESTORE_CONFIRM must equal destroy-disposable-state" >&2
  exit 1
}
[ "$RESTORE_DRILL_DISPOSABLE" = "1" ] || {
  echo "restore refused: RESTORE_DRILL_DISPOSABLE must equal 1" >&2
  exit 1
}
[ "$MIROFISH_DEPLOYMENT_ENV" != "production" ] || {
  echo "restore refused: this drill script cannot target production" >&2
  exit 1
}
: "${APP_DATABASE_USER:?APP_DATABASE_USER is required}"
: "${APP_DATABASE_PASSWORD:?APP_DATABASE_PASSWORD is required}"

backup_dir="$(CDPATH= cd -- "$RESTORE_BACKUP_DIR" && pwd)"
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
base_compose="$script_dir/../docker-compose.yml"
override_compose="${MIROFISH_COMPOSE_OVERRIDE:-$script_dir/../compose.staging.yml}"
for name in postgres.dump minio-objects.tar.gz manifest.txt SHA256SUMS TABLE_ROW_COUNTS TABLE_ROW_CONTENT_HASHES OBJECT_SHA256_INVENTORY; do
  [ -f "$backup_dir/$name" ] || { echo "restore refused: missing $name" >&2; exit 1; }
done

if command -v sha256sum >/dev/null 2>&1; then
  (cd "$backup_dir" && sha256sum -c SHA256SUMS)
else
  (cd "$backup_dir" && shasum -a 256 -c SHA256SUMS)
fi
grep -qx "postgres_database=$POSTGRES_DB" "$backup_dir/manifest.txt"
grep -qx "object_bucket=$MIROFISH_OBJECT_STORAGE_BUCKET" "$backup_dir/manifest.txt"

docker compose -f "$base_compose" -f "$override_compose" exec -T postgres \
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
  --set=target_database="$POSTGRES_DB" --set=target_owner="$POSTGRES_USER" <<'SQL' >/dev/null
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = :'target_database' AND pid <> pg_backend_pid();
SELECT format('DROP DATABASE IF EXISTS %I', :'target_database')
\gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'target_database', :'target_owner')
\gexec
SQL

docker compose -f "$base_compose" -f "$override_compose" exec -T postgres \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --exit-on-error --no-owner \
  <"$backup_dir/postgres.dump"

restored_counts="$(mktemp "${TMPDIR:-/tmp}/mirofish-row-counts.XXXXXX")"
restored_hashes="$(mktemp "${TMPDIR:-/tmp}/mirofish-row-hashes.XXXXXX")"
docker compose -f "$base_compose" -f "$override_compose" exec -T postgres sh -c '
  set -eu
  tables=$(psql -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT quote_ident(schemaname) || '\''.'\'' || quote_ident(tablename) FROM pg_tables WHERE schemaname NOT IN ('\''pg_catalog'\'', '\''information_schema'\'') ORDER BY 1")
  for table_name in $tables; do
    psql -At -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<SQL
SET timezone TO '\''UTC'\'';
SELECT '\''$table_name'\'' || '\''='\'' || count(*) || '\'':'\'' ||
       encode(digest(COALESCE(string_agg(row_hash, CHR(10) ORDER BY row_hash), left(current_database(), 0)), '\''sha256'\''), '\''hex'\'')
FROM (
  SELECT encode(digest(to_jsonb(source_row)::text, '\''sha256'\''), '\''hex'\'') AS row_hash
  FROM $table_name AS source_row
) AS canonical_rows;
SQL
  done
' >"$restored_hashes"
sed 's/:[0-9a-f]\{64\}$//' "$restored_hashes" >"$restored_counts"
cmp -s "$backup_dir/TABLE_ROW_COUNTS" "$restored_counts" || {
  echo "restore verification failed: table row counts differ" >&2
  exit 1
}
cmp -s "$backup_dir/TABLE_ROW_CONTENT_HASHES" "$restored_hashes" || {
  echo "restore verification failed: canonical table row-content hashes differ" >&2
  exit 1
}

app_smoke="$(docker compose -f "$base_compose" -f "$override_compose" exec -T \
  -e PGPASSWORD="$APP_DATABASE_PASSWORD" postgres \
  psql -qAt -v ON_ERROR_STOP=1 -h 127.0.0.1 -U "$APP_DATABASE_USER" -d "$POSTGRES_DB" <<'SQL'
BEGIN;
SELECT app_set_tenant_context(
  'f1000000-0000-4000-8000-000000000001'::UUID,
  'f1000000-0000-4000-8000-000000000002'::UUID,
  false
);
SELECT current_user || '|' ||
       pg_has_role(current_user, 'mirofish_app', 'member') || '|' ||
       (row_security_active('projects') AND (SELECT count(*) FROM projects) = 0) || '|' ||
       (
         row_security_active('legacy_artifact_imports')
         AND has_table_privilege(
           current_user,
           'legacy_artifact_imports',
           'SELECT,INSERT,UPDATE,DELETE'
         )
         AND (SELECT count(*) FROM legacy_artifact_imports) = 0
       ) || '|' ||
       (
         SELECT count(*)
         FROM unnest(ARRAY[
           'password_reset_tokens',
           'password_reset_delivery_attempts',
           'password_reset_delivery_outbox',
           'auth_security_audit_logs'
         ]) AS sensitive(table_name)
         WHERE has_table_privilege(
           current_user,
           sensitive.table_name,
           'SELECT,INSERT,UPDATE,DELETE'
         )
       );
ROLLBACK;
SQL
)"
app_smoke="$(printf '%s\n' "$app_smoke" | tail -n 1)"
[ "$app_smoke" = "$APP_DATABASE_USER|true|true|true|0" ] || {
  echo "restore verification failed: app-role RLS or sensitive-table privilege smoke failed" >&2
  exit 1
}

restore_objects="$(mktemp -d "${TMPDIR:-/tmp}/mirofish-restore.XXXXXX")"
verify_objects="$(mktemp -d "${TMPDIR:-/tmp}/mirofish-verify.XXXXXX")"
trap 'rm -rf "$restore_objects" "$verify_objects" "$restored_counts" "$restored_hashes"' EXIT INT TERM HUP
tar -C "$restore_objects" -xzf "$backup_dir/minio-objects.tar.gz"
mkdir -p "$verify_objects/objects"
docker compose -f "$base_compose" -f "$override_compose" run --rm -T --no-deps \
  -v "$restore_objects/objects:/restore/objects:ro" --entrypoint sh minio-init -c \
  'set -eu; mc alias set restore http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null; mc rm --recursive --force "restore/$MIROFISH_OBJECT_STORAGE_BUCKET" >/dev/null 2>&1 || true; mc mb --ignore-existing "restore/$MIROFISH_OBJECT_STORAGE_BUCKET" >/dev/null; mc mirror --overwrite /restore/objects "restore/$MIROFISH_OBJECT_STORAGE_BUCKET" >/dev/null'

docker compose -f "$base_compose" -f "$override_compose" run --rm -T --no-deps \
  -v "$verify_objects:/verify" --entrypoint sh minio-init -c \
  'set -eu; mc alias set verify http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null; mc mirror --overwrite "verify/$MIROFISH_OBJECT_STORAGE_BUCKET" /verify/objects >/dev/null'

hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else shasum -a 256 "$1"; fi
}
find "$verify_objects/objects" -type f | LC_ALL=C sort | while IFS= read -r object; do
  relative=${object#"$verify_objects/objects"/}
  key_hash=$(printf '%s' "$relative" | openssl dgst -sha256 -r | awk '{print $1}')
  content_hash=$(hash_file "$object" | awk '{print $1}')
  size=$(wc -c <"$object" | tr -d ' ')
  printf '%s %s %s\n' "$key_hash" "$content_hash" "$size"
done >"$verify_objects/OBJECT_SHA256_INVENTORY"
cmp -s "$backup_dir/OBJECT_SHA256_INVENTORY" "$verify_objects/OBJECT_SHA256_INVENTORY" || {
  echo "restore verification failed: object inventory differs" >&2
  exit 1
}

echo "restore complete after database destruction, canonical row-content/count and anonymized object SHA-256 verification"
