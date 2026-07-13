#!/bin/sh
set -eu

: "${COMPOSE_AUTH_FIXTURE_PASSWORD:?COMPOSE_AUTH_FIXTURE_PASSWORD is required}"

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
compose_file="$script_dir/../docker-compose.yml"

docker compose -f "$compose_file" exec -T postgres \
  psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:-mirofish}" -d "${POSTGRES_DB:-mirofish}" \
  --set=fixture_password="$COMPOSE_AUTH_FIXTURE_PASSWORD" <<'SQL' >/dev/null
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

INSERT INTO users (user_id, email, display_name, status)
VALUES (
  'a3000000-0000-4000-8000-000000000001',
  'compose-auth@example.test',
  'Compose Auth Recovery',
  'active'
);

INSERT INTO user_password_credentials (user_id, password_hash, status)
VALUES (
  'a3000000-0000-4000-8000-000000000001',
  crypt(:'fixture_password', gen_salt('bf', 8)),
  'active'
);

INSERT INTO users (user_id, email, display_name, status)
VALUES (
  'a3000000-0000-4000-8000-000000000002',
  'compose-foreign@example.test',
  'Compose Foreign Tenant',
  'active'
);

INSERT INTO user_password_credentials (user_id, password_hash, status)
VALUES (
  'a3000000-0000-4000-8000-000000000002',
  crypt(:'fixture_password', gen_salt('bf', 8)),
  'active'
);

INSERT INTO tenants (tenant_id, name, slug, tenant_type, status)
VALUES (
  'b3000000-0000-4000-8000-000000000001',
  'Compose Recovery Tenant',
  'compose-recovery',
  'personal',
  'active'
)
ON CONFLICT (tenant_id) DO UPDATE
SET name = EXCLUDED.name, slug = EXCLUDED.slug, status = EXCLUDED.status;

INSERT INTO tenant_memberships (tenant_id, user_id, role, status)
VALUES (
  'b3000000-0000-4000-8000-000000000001',
  'a3000000-0000-4000-8000-000000000001',
  'owner',
  'active'
)
ON CONFLICT (tenant_id, user_id) DO UPDATE
SET role = EXCLUDED.role, status = EXCLUDED.status;

INSERT INTO tenants (tenant_id, name, slug, tenant_type, status)
VALUES (
  'b3000000-0000-4000-8000-000000000002',
  'Compose Foreign Tenant',
  'compose-foreign',
  'personal',
  'active'
)
ON CONFLICT (tenant_id) DO UPDATE
SET name = EXCLUDED.name, slug = EXCLUDED.slug, status = EXCLUDED.status;

INSERT INTO tenant_memberships (tenant_id, user_id, role, status)
VALUES (
  'b3000000-0000-4000-8000-000000000002',
  'a3000000-0000-4000-8000-000000000002',
  'owner',
  'active'
)
ON CONFLICT (tenant_id, user_id) DO UPDATE
SET role = EXCLUDED.role, status = EXCLUDED.status;

INSERT INTO projects (tenant_id, project_id, title, status, created_by)
VALUES (
  'b3000000-0000-4000-8000-000000000002',
  'c3000000-0000-4000-8000-000000000002',
  'Compose Foreign Project',
  'active',
  'a3000000-0000-4000-8000-000000000002'
)
ON CONFLICT (tenant_id, project_id) DO UPDATE
SET title = EXCLUDED.title, status = EXCLUDED.status;

INSERT INTO project_members (tenant_id, project_id, user_id, role, status)
VALUES (
  'b3000000-0000-4000-8000-000000000002',
  'c3000000-0000-4000-8000-000000000002',
  'a3000000-0000-4000-8000-000000000002',
  'project_owner',
  'active'
)
ON CONFLICT (tenant_id, project_id, user_id) DO UPDATE
SET role = EXCLUDED.role, status = EXCLUDED.status;

INSERT INTO projects (tenant_id, project_id, title, status, created_by)
VALUES (
  'b3000000-0000-4000-8000-000000000001',
  'c3000000-0000-4000-8000-000000000001',
  'Compose Recovery Project',
  'active',
  'a3000000-0000-4000-8000-000000000001'
)
ON CONFLICT (tenant_id, project_id) DO UPDATE
SET title = EXCLUDED.title, status = EXCLUDED.status;

INSERT INTO project_members (tenant_id, project_id, user_id, role, status)
VALUES (
  'b3000000-0000-4000-8000-000000000001',
  'c3000000-0000-4000-8000-000000000001',
  'a3000000-0000-4000-8000-000000000001',
  'project_owner',
  'active'
)
ON CONFLICT (tenant_id, project_id, user_id) DO UPDATE
SET role = EXCLUDED.role, status = EXCLUDED.status;

INSERT INTO workflow_runs (
  tenant_id, run_id, workflow_type, project_id, status, progress, started_by,
  temporal_workflow_id, result_jsonb
)
VALUES (
  'b3000000-0000-4000-8000-000000000001',
  'd3000000-0000-4000-8000-000000000001',
  'writer_run',
  'c3000000-0000-4000-8000-000000000001',
  'completed',
  100,
  'a3000000-0000-4000-8000-000000000001',
  'compose-recovery-writer-run',
  '{"recovery_fixture":true}'::jsonb
)
ON CONFLICT (run_id) DO UPDATE
SET status = EXCLUDED.status, progress = EXCLUDED.progress,
    temporal_workflow_id = EXCLUDED.temporal_workflow_id,
    result_jsonb = EXCLUDED.result_jsonb, updated_at = now();

INSERT INTO writer_runs (
  tenant_id, run_id, workflow_run_id, project_id, mode, status, instruction,
  options_jsonb, created_by
)
VALUES (
  'b3000000-0000-4000-8000-000000000001',
  'd3000000-0000-4000-8000-000000000001',
  'd3000000-0000-4000-8000-000000000001',
  'c3000000-0000-4000-8000-000000000001',
  'draft',
  'completed',
  'compose recovery fixture',
  '{"recovery_fixture":true}'::jsonb,
  'a3000000-0000-4000-8000-000000000001'
)
ON CONFLICT (run_id) DO UPDATE
SET status = EXCLUDED.status, options_jsonb = EXCLUDED.options_jsonb, updated_at = now();

INSERT INTO workflow_events (
  tenant_id, event_id, run_id, workflow_type, project_id, event_type, sequence,
  payload_jsonb
)
VALUES (
  'b3000000-0000-4000-8000-000000000001',
  'd3000000-0000-4000-8000-000000000002',
  'd3000000-0000-4000-8000-000000000001',
  'writer_run',
  'c3000000-0000-4000-8000-000000000001',
  'writer.run.completed',
  1,
  '{"recovery_fixture":true,"draft_id":"e3000000-0000-4000-8000-000000000001"}'::jsonb
)
ON CONFLICT (tenant_id, run_id, sequence) DO UPDATE
SET event_type = EXCLUDED.event_type, payload_jsonb = EXCLUDED.payload_jsonb;

INSERT INTO writer_drafts (
  tenant_id, draft_id, run_id, project_id, content_text, word_count, status
)
VALUES (
  'b3000000-0000-4000-8000-000000000001',
  'e3000000-0000-4000-8000-000000000001',
  'd3000000-0000-4000-8000-000000000001',
  'c3000000-0000-4000-8000-000000000001',
  'Compose recovery fixture draft.',
  4,
  'candidate'
)
ON CONFLICT (draft_id) DO UPDATE
SET content_text = EXCLUDED.content_text, word_count = EXCLUDED.word_count,
    status = EXCLUDED.status, updated_at = now();

COMMIT;
SQL

echo "disposable compose auth and recovery fixture ready"
