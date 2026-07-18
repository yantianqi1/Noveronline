BEGIN;

-- 0022: Worldline goal-start orchestration — Pi cast planner then prepare + session.
-- Additive only. FORCE RLS + app-role grants.

CREATE TABLE IF NOT EXISTS worldline_goal_starts (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_run_id UUID REFERENCES workflow_runs(run_id) ON DELETE SET NULL,
  project_id UUID NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued', 'casting', 'preparing', 'starting', 'ready', 'failed', 'cancelled')),
  module_key TEXT NOT NULL DEFAULT 'worldline_cast_planner',
  goal TEXT NOT NULL DEFAULT '',
  anchor_path_id UUID,
  agent_refs_jsonb JSONB NOT NULL DEFAULT '[]'::jsonb
    CHECK (jsonb_typeof(agent_refs_jsonb) = 'array'),
  source_refs_jsonb JSONB NOT NULL DEFAULT '[]'::jsonb
    CHECK (jsonb_typeof(source_refs_jsonb) = 'array'),
  rationale TEXT NOT NULL DEFAULT '',
  prepare_id UUID,
  session_id UUID,
  options_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(options_jsonb) = 'object'),
  result_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(result_jsonb) = 'object'),
  error_code TEXT,
  error_message TEXT,
  created_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, run_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_worldline_goal_starts_project_status
  ON worldline_goal_starts (tenant_id, project_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_worldline_goal_starts_workflow_run
  ON worldline_goal_starts (tenant_id, workflow_run_id)
  WHERE workflow_run_id IS NOT NULL;

REVOKE ALL ON worldline_goal_starts FROM PUBLIC, mirofish_app;
GRANT SELECT, INSERT, UPDATE ON worldline_goal_starts TO mirofish_app;

ALTER TABLE worldline_goal_starts ENABLE ROW LEVEL SECURITY;
ALTER TABLE worldline_goal_starts FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_worldline_goal_starts ON worldline_goal_starts;
CREATE POLICY tenant_isolation_worldline_goal_starts
ON worldline_goal_starts
FOR ALL
TO mirofish_app
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

COMMIT;
