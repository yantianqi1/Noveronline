#!/bin/sh
set -eu

: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${TEMPORAL_DB:?TEMPORAL_DB is required}"
: "${TEMPORAL_VISIBILITY_DB:?TEMPORAL_VISIBILITY_DB is required}"

export PGPASSWORD="$POSTGRES_PASSWORD"
for database_name in "$TEMPORAL_DB" "$TEMPORAL_VISIBILITY_DB"; do
  psql -v ON_ERROR_STOP=1 -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d postgres \
    --set=database_name="$database_name" <<'SQL' >/dev/null
SELECT format('CREATE DATABASE %I', :'database_name')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'database_name')
\gexec
SQL
done

echo "Temporal databases ready"
