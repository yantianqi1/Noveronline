#!/bin/sh
set -eu

: "${BACKUP_ROOT:?BACKUP_ROOT is required}"
: "${MIROFISH_OBJECT_STORAGE_BUCKET:?MIROFISH_OBJECT_STORAGE_BUCKET is required}"

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
base_compose="$script_dir/../docker-compose.yml"
override_compose="${MIROFISH_COMPOSE_OVERRIDE:-$script_dir/../compose.staging.yml}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="$BACKUP_ROOT/$timestamp"
umask 077
mkdir -p "$backup_dir/objects"

cleanup() { rm -rf "$backup_dir/objects"; }
trap cleanup EXIT INT TERM HUP

hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else shasum -a 256 "$1"; fi
}

capture_table_inventory() {
  output="$1"
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
  ' >"$output"
}

capture_table_inventory "$backup_dir/TABLE_ROW_CONTENT_HASHES.before"

docker compose -f "$base_compose" -f "$override_compose" exec -T postgres \
  pg_dump -U "${POSTGRES_USER:?POSTGRES_USER is required}" \
  -d "${POSTGRES_DB:?POSTGRES_DB is required}" --format=custom --no-owner \
  >"$backup_dir/postgres.dump"

capture_table_inventory "$backup_dir/TABLE_ROW_CONTENT_HASHES.after"
cmp -s "$backup_dir/TABLE_ROW_CONTENT_HASHES.before" "$backup_dir/TABLE_ROW_CONTENT_HASHES.after" || {
  echo "backup refused: PostgreSQL content changed while the dump was captured" >&2
  exit 1
}
mv "$backup_dir/TABLE_ROW_CONTENT_HASHES.after" "$backup_dir/TABLE_ROW_CONTENT_HASHES"
rm -f "$backup_dir/TABLE_ROW_CONTENT_HASHES.before"
sed 's/:[0-9a-f]\{64\}$//' "$backup_dir/TABLE_ROW_CONTENT_HASHES" >"$backup_dir/TABLE_ROW_COUNTS"

docker compose -f "$base_compose" -f "$override_compose" run --rm -T --no-deps \
  -v "$backup_dir/objects:/backup/objects" --entrypoint sh minio-init -c \
  'set -eu; mc alias set backup http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null; mc mirror --overwrite "backup/$MIROFISH_OBJECT_STORAGE_BUCKET" /backup/objects >/dev/null'

object_inventory() {
  root="$1"
  find "$root" -type f | LC_ALL=C sort | while IFS= read -r object; do
    relative=${object#"$root"/}
    key_hash=$(printf '%s' "$relative" | openssl dgst -sha256 -r | awk '{print $1}')
    content_hash=$(hash_file "$object" | awk '{print $1}')
    size=$(wc -c <"$object" | tr -d ' ')
    printf '%s %s %s\n' "$key_hash" "$content_hash" "$size"
  done
}
object_inventory "$backup_dir/objects" >"$backup_dir/OBJECT_SHA256_INVENTORY"

tar -C "$backup_dir" -czf "$backup_dir/minio-objects.tar.gz" objects
rm -rf "$backup_dir/objects"

(
  cd "$backup_dir"
  hash_file postgres.dump
  hash_file minio-objects.tar.gz
  hash_file TABLE_ROW_COUNTS
  hash_file TABLE_ROW_CONTENT_HASHES
  hash_file OBJECT_SHA256_INVENTORY
) >"$backup_dir/SHA256SUMS"

cat >"$backup_dir/manifest.txt" <<EOF
schema_version=1
created_at=$timestamp
postgres_database=$POSTGRES_DB
object_bucket=$MIROFISH_OBJECT_STORAGE_BUCKET
rpo_target_hours=${BACKUP_RPO_HOURS:-24}
rto_target_hours=${BACKUP_RTO_HOURS:-4}
EOF
(cd "$backup_dir" && hash_file manifest.txt) >>"$backup_dir/SHA256SUMS"
chmod -R go-rwx "$backup_dir"
echo "backup complete: $backup_dir"
