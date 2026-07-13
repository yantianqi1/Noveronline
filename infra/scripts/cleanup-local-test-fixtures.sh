#!/bin/sh
set -eu

usage() {
  cat <<'EOF'
Usage: cleanup-local-test-fixtures.sh [--apply]

Audits known local test fixtures by default. Pass --apply to delete only rows
whose UUID and exact fixture marker both match the built-in allowlist.

Safety gates:
  - Every mode requires MIROFISH_DEPLOYMENT_ENV=local.
  - Direct mode requires MIROFISH_FIXTURE_CLEANUP_DATABASE_URL to use a
    localhost, 127.0.0.1, or ::1 PostgreSQL host.
  - staging and production deployment environments are always rejected.
EOF
}

apply=0
case "${1:-}" in
  "") ;;
  --apply) apply=1 ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    echo "unknown argument: $1" >&2
    usage >&2
    exit 2
    ;;
esac

if [ "$#" -gt 1 ]; then
  echo "only one optional argument is accepted" >&2
  usage >&2
  exit 2
fi

deployment_env="${MIROFISH_DEPLOYMENT_ENV:-}"
cleanup_database_url="${MIROFISH_FIXTURE_CLEANUP_DATABASE_URL:-}"

case "$deployment_env" in
	local) ;;
	staging|production)
		echo "fixture cleanup is disabled for $deployment_env environments" >&2
		exit 1
		;;
	*)
		echo "set MIROFISH_DEPLOYMENT_ENV=local before auditing or deleting fixtures" >&2
		exit 1
		;;
esac

if [ -n "$cleanup_database_url" ]; then
  if ! python3 - "$cleanup_database_url" <<'PY'
import sys
from urllib.parse import parse_qsl, urlsplit

try:
    parsed = urlsplit(sys.argv[1])
except ValueError:
    raise SystemExit(1)

if parsed.scheme not in {"postgres", "postgresql"}:
    raise SystemExit(1)
if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
    raise SystemExit(1)
if not parsed.path or parsed.path == "/":
    raise SystemExit(1)
if parsed.fragment:
    raise SystemExit(1)

# libpq accepts connection-routing keywords in a URI query. Restrict the
# cleanup URL to non-routing options so a loopback authority cannot be paired
# with a remote hostaddr, service file, or alternate database.
allowed_query_parameters = {"application_name", "connect_timeout", "sslmode"}
for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
    if key.lower() not in allowed_query_parameters:
        raise SystemExit(1)
PY
  then
    echo "MIROFISH_FIXTURE_CLEANUP_DATABASE_URL must name an explicit loopback PostgreSQL database" >&2
    exit 1
	fi
fi

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
compose_file="$script_dir/../docker-compose.yml"

run_psql() {
  if [ -n "$cleanup_database_url" ]; then
    psql -X -q -v ON_ERROR_STOP=1 -P pager=off "$@" "$cleanup_database_url"
  else
    docker compose -f "$compose_file" exec -T postgres \
      psql -X -q -v ON_ERROR_STOP=1 -P pager=off \
      -U "${POSTGRES_USER:-mirofish}" -d "${POSTGRES_DB:-mirofish}" "$@"
  fi
}

if [ "$apply" -eq 1 ]; then
  echo "mode=apply (transactional deletion enabled)"
else
  echo "mode=preview (no persistent changes; pass --apply to delete)"
fi

run_psql -v cleanup_apply="$apply" <<'SQL'
BEGIN ISOLATION LEVEL SERIALIZABLE;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SELECT pg_advisory_xact_lock(hashtextextended('mirofish-local-fixture-cleanup', 0));

CREATE TEMP TABLE cleanup_fixture_tenants (
  tenant_id UUID PRIMARY KEY,
  expected_slug TEXT NOT NULL UNIQUE
) ON COMMIT DROP;

INSERT INTO cleanup_fixture_tenants (tenant_id, expected_slug) VALUES
  ('20000000-0000-0000-0000-000000000001', 'rls-tenant-a'),
  ('20000000-0000-0000-0000-000000000002', 'rls-tenant-b'),
  ('00000000-0000-0000-0000-000000000101', 'seed-smoke'),
  ('00000000-0000-0000-0000-000000000201', 'seed-smoke-2'),
  ('a8100000-0000-4000-8000-000000000001', 'llm-admin-live-a'),
  ('a8100000-0000-4000-8000-000000000002', 'llm-admin-live-b'),
  ('11111111-1111-1111-1111-111111111111', 'worldline-live'),
  ('71000000-0000-4000-8000-000000000001', 'llm-quota-live-a'),
  ('71000000-0000-4000-8000-000000000002', 'llm-quota-live-b'),
  ('71111111-1111-1111-1111-111111111111', 'seed-live'),
  ('00000000-0000-4000-8000-000000000502', 'web-live-seed-fixture'),
  ('b3000000-0000-4000-8000-000000000001', 'compose-recovery'),
  ('b3000000-0000-4000-8000-000000000002', 'compose-foreign'),
  ('91000000-0000-4000-8000-000000000002', 'assets-browser-disposable'),
  ('91000000-0000-4000-8000-000000000007', 'assets-browser-foreign'),
  ('81000000-0000-4000-8000-000000000002', 'graph-browser-disposable'),
  ('c1000000-0000-4000-8000-000000000002', 'writer-browser'),
  ('27000000-0000-4000-8000-000000000001', 'collab-live'),
  ('27000000-0000-4000-8000-000000000003', 'collab-foreign');

CREATE TEMP TABLE cleanup_fixture_users (
  user_id UUID PRIMARY KEY,
  expected_email TEXT NOT NULL UNIQUE
) ON COMMIT DROP;

INSERT INTO cleanup_fixture_users (user_id, expected_email) VALUES
  ('10000000-0000-0000-0000-000000000002', 'rls-b@example.invalid'),
  ('00000000-0000-0000-0000-000000000102', 'seed-smoke@example.test'),
  ('00000000-0000-0000-0000-000000000202', 'seed-smoke-2@example.test'),
  ('10000000-0000-0000-0000-000000000552', 'volume-smoke@example.invalid'),
  ('10000000-0000-0000-0000-000000000652', 'volume-smoke-final@example.invalid'),
  ('10000000-0000-0000-0000-000000000752', 'entity-label-smoke@example.invalid'),
  ('10000000-0000-0000-0000-000000000852', 'entity-label-smoke-final@example.invalid'),
  ('72222222-2222-2222-2222-222222222222', 'seed-live@example.test'),
  ('82222222-2222-2222-2222-222222222222', 'seed-go-live@example.test'),
  ('8976e54c-bbe5-4540-8b4e-0c8094f0219d', 'graph-live@example.test'),
  ('93333333-3333-4333-8333-333333333333', 'writer-export-go-live@example.test'),
  ('7ecfdb14-8ad1-471c-9b1f-e53632ca073c', 'graph-go-live@example.test'),
  ('a3333333-3333-4333-8333-333333333333', 'pi-writer-live@example.test'),
  ('00000000-0000-4000-8000-000000000501', 'web-live-seed-fixture@example.test'),
  ('22222222-2222-2222-2222-222222222222', 'worldline-live@example.test'),
  ('a5555555-5555-4555-8555-555555555555', 'writer-workspace-live@example.test'),
  ('a8500000-0000-4000-8000-000000000001', 'llm-admin-owner@example.test'),
  ('a8500000-0000-4000-8000-000000000002', 'llm-admin-billing@example.test'),
  ('a8500000-0000-4000-8000-000000000003', 'llm-admin-viewer@example.test'),
  ('a3000000-0000-4000-8000-000000000001', 'compose-auth@example.test'),
  ('a3000000-0000-4000-8000-000000000002', 'compose-foreign@example.test'),
  ('a3000000-0000-4000-8000-000000000003', 'platform-invitee@example.test'),
  ('91000000-0000-4000-8000-000000000001', 'assets-browser-disposable@example.test'),
  ('81000000-0000-4000-8000-000000000001', 'graph-browser-disposable@example.test'),
  ('c1000000-0000-4000-8000-000000000001', 'writer-browser@example.test'),
  ('27000000-0000-4000-8000-000000000011', 'owner@example.test'),
  ('27000000-0000-4000-8000-000000000012', 'invitee@example.test'),
  ('27000000-0000-4000-8000-000000000013', 'foreign@example.test'),
  ('27000000-0000-4000-8000-000000000014', 'suspended@example.test');

CREATE TEMP VIEW cleanup_valid_tenants AS
SELECT tenant.tenant_id
FROM tenants AS tenant
JOIN cleanup_fixture_tenants AS fixture
  ON fixture.tenant_id = tenant.tenant_id
 AND fixture.expected_slug = tenant.slug;

CREATE TEMP VIEW cleanup_valid_users AS
SELECT app_user.user_id
FROM users AS app_user
JOIN cleanup_fixture_users AS fixture
  ON fixture.user_id = app_user.user_id
 AND fixture.expected_email = lower(app_user.email);

CREATE TEMP TABLE cleanup_marker_conflicts (
  conflict_type TEXT NOT NULL,
  allowlisted_id UUID NOT NULL,
  expected_marker TEXT NOT NULL,
  actual_value TEXT NOT NULL
) ON COMMIT DROP;

INSERT INTO cleanup_marker_conflicts
SELECT 'workspace_uuid_marker_mismatch', fixture.tenant_id, fixture.expected_slug, tenant.slug
FROM cleanup_fixture_tenants AS fixture
JOIN tenants AS tenant ON tenant.tenant_id = fixture.tenant_id
WHERE tenant.slug <> fixture.expected_slug
UNION ALL
SELECT 'workspace_marker_owned_by_other_uuid', fixture.tenant_id, fixture.expected_slug, tenant.tenant_id::TEXT
FROM cleanup_fixture_tenants AS fixture
JOIN tenants AS tenant ON tenant.slug = fixture.expected_slug
WHERE tenant.tenant_id <> fixture.tenant_id
UNION ALL
SELECT 'user_uuid_marker_mismatch', fixture.user_id, fixture.expected_email, app_user.email
FROM cleanup_fixture_users AS fixture
JOIN users AS app_user ON app_user.user_id = fixture.user_id
WHERE lower(app_user.email) <> fixture.expected_email
UNION ALL
SELECT 'user_marker_owned_by_other_uuid', fixture.user_id, fixture.expected_email, app_user.user_id::TEXT
FROM cleanup_fixture_users AS fixture
JOIN users AS app_user ON lower(app_user.email) = fixture.expected_email
WHERE app_user.user_id <> fixture.user_id;

SELECT conflict_type, allowlisted_id, expected_marker, actual_value
FROM cleanup_marker_conflicts
ORDER BY conflict_type, allowlisted_id;

CREATE TEMP TABLE cleanup_plan_counts (
  category TEXT PRIMARY KEY,
  row_count BIGINT NOT NULL
) ON COMMIT DROP;

INSERT INTO cleanup_plan_counts (category, row_count)
SELECT 'sessions', count(*)
FROM user_sessions
WHERE user_id IN (SELECT user_id FROM cleanup_valid_users)
UNION ALL
SELECT 'user_credentials', count(*)
FROM user_password_credentials
WHERE user_id IN (SELECT user_id FROM cleanup_valid_users)
UNION ALL
SELECT 'projects', count(*)
FROM projects
WHERE tenant_id IN (SELECT tenant_id FROM cleanup_valid_tenants)
UNION ALL
SELECT 'workspaces', count(*)
FROM cleanup_valid_tenants
UNION ALL
SELECT 'users', count(*)
FROM cleanup_valid_users;

DO $cleanup_counts$
DECLARE
  fixture_tenant_ids UUID[];
  candidate RECORD;
  candidate_count BIGINT;
  dependent_count BIGINT := 0;
BEGIN
  SELECT array_agg(tenant_id) INTO fixture_tenant_ids FROM cleanup_valid_tenants;
  IF fixture_tenant_ids IS NOT NULL THEN
    FOR candidate IN
      SELECT namespace.nspname AS schema_name, relation.relname AS table_name
      FROM pg_class AS relation
      JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
      JOIN pg_attribute AS attribute ON attribute.attrelid = relation.oid
      WHERE namespace.nspname = current_schema()
        AND relation.relkind IN ('r', 'p')
        AND attribute.attname = 'tenant_id'
        AND attribute.attnum > 0
        AND NOT attribute.attisdropped
        AND relation.oid NOT IN ('tenants'::regclass, 'projects'::regclass)
    LOOP
      EXECUTE format(
        'SELECT count(*) FROM %I.%I WHERE tenant_id = ANY ($1)',
        candidate.schema_name,
        candidate.table_name
      ) INTO candidate_count USING fixture_tenant_ids;
      dependent_count := dependent_count + candidate_count;
    END LOOP;
  END IF;
  INSERT INTO cleanup_plan_counts (category, row_count)
  VALUES ('tenant_dependent_rows', dependent_count);
END
$cleanup_counts$;

SELECT CASE WHEN :'cleanup_apply' = '1' THEN 'apply' ELSE 'preview' END AS mode,
       category,
       row_count
FROM cleanup_plan_counts
ORDER BY category;

\if :cleanup_apply
DO $cleanup_guard$
DECLARE
  marker_conflict_count BIGINT;
BEGIN
  SELECT count(*) INTO marker_conflict_count FROM cleanup_marker_conflicts;
  IF marker_conflict_count <> 0 THEN
    RAISE EXCEPTION 'fixture marker validation failed for % allowlisted row(s)', marker_conflict_count;
  END IF;

	IF EXISTS (
    SELECT 1 FROM cleanup_fixture_users
    WHERE user_id = '10000000-0000-0000-0000-000000000001'::UUID
       OR expected_email = 'admin@qq.com'
  ) THEN
    RAISE EXCEPTION 'protected administrator is present in the cleanup allowlist';
  END IF;

  IF EXISTS (
    SELECT 1 FROM cleanup_fixture_tenants
    WHERE tenant_id = '10000000-0000-0000-0000-000000000101'::UUID
  ) THEN
    RAISE EXCEPTION 'protected personal workspace is present in the cleanup allowlist';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM projects
    WHERE project_id = '10000000-0000-0000-0000-000000000201'::UUID
      AND tenant_id IN (SELECT tenant_id FROM cleanup_valid_tenants)
  ) THEN
    RAISE EXCEPTION 'protected personal project would be deleted';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM cleanup_valid_users AS fixture_user
    JOIN users AS app_user ON app_user.user_id = fixture_user.user_id
    WHERE lower(app_user.email) = 'admin@qq.com'
  ) THEN
		RAISE EXCEPTION 'protected administrator marker resolved to a cleanup user';
	END IF;

	IF NOT EXISTS (
		SELECT 1 FROM users
		WHERE user_id = '10000000-0000-0000-0000-000000000001'::UUID
		  AND lower(email) = 'admin@qq.com'
	) OR NOT EXISTS (
		SELECT 1 FROM tenants
		WHERE tenant_id = '10000000-0000-0000-0000-000000000101'::UUID
	) OR NOT EXISTS (
		SELECT 1 FROM projects
		WHERE tenant_id = '10000000-0000-0000-0000-000000000101'::UUID
		  AND project_id = '10000000-0000-0000-0000-000000000201'::UUID
	) THEN
		RAISE EXCEPTION 'protected local administrator workspace anchor is missing';
	END IF;

  IF EXISTS (
    SELECT 1
    FROM cleanup_valid_users AS fixture_user
    JOIN tenant_memberships AS membership ON membership.user_id = fixture_user.user_id
    WHERE membership.tenant_id NOT IN (SELECT tenant_id FROM cleanup_valid_tenants)
  ) OR EXISTS (
    SELECT 1
    FROM cleanup_valid_users AS fixture_user
    JOIN project_members AS membership ON membership.user_id = fixture_user.user_id
    WHERE membership.tenant_id NOT IN (SELECT tenant_id FROM cleanup_valid_tenants)
  ) THEN
    RAISE EXCEPTION 'a fixture user is attached to a non-fixture workspace';
  END IF;

  IF NOT has_table_privilege(current_user, 'users', 'DELETE')
     OR NOT has_table_privilege(current_user, 'tenants', 'DELETE')
     OR NOT has_table_privilege(current_user, 'projects', 'DELETE')
     OR NOT has_table_privilege(current_user, 'user_sessions', 'DELETE') THEN
    RAISE EXCEPTION 'database role lacks fixture cleanup privileges';
  END IF;
END
$cleanup_guard$;

CREATE TEMP TABLE cleanup_applied_counts (
  category TEXT PRIMARY KEY,
  row_count BIGINT NOT NULL
) ON COMMIT DROP;

WITH deleted AS (
  DELETE FROM user_sessions
  WHERE user_id IN (SELECT user_id FROM cleanup_valid_users)
  RETURNING 1
)
INSERT INTO cleanup_applied_counts SELECT 'sessions', count(*) FROM deleted;

WITH deleted AS (
  DELETE FROM projects
  WHERE tenant_id IN (SELECT tenant_id FROM cleanup_valid_tenants)
  RETURNING 1
)
INSERT INTO cleanup_applied_counts SELECT 'projects', count(*) FROM deleted;

WITH deleted AS (
  DELETE FROM tenants
  WHERE tenant_id IN (SELECT tenant_id FROM cleanup_valid_tenants)
  RETURNING 1
)
INSERT INTO cleanup_applied_counts SELECT 'workspaces', count(*) FROM deleted;

WITH deleted AS (
  DELETE FROM users
  WHERE user_id IN (SELECT user_id FROM cleanup_valid_users)
  RETURNING 1
)
INSERT INTO cleanup_applied_counts SELECT 'users', count(*) FROM deleted;

SELECT 'deleted' AS mode, category, row_count
FROM cleanup_applied_counts
ORDER BY category;
COMMIT;
\else
ROLLBACK;
\endif
SQL

if [ "$apply" -eq 1 ]; then
  echo "fixture cleanup committed"
else
  echo "preview complete; database transaction rolled back"
fi
