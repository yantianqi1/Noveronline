BEGIN;

-- 0020: Pi Analysis Workspace — analysis_runs, workspace file index, candidates.
-- Additive only. FORCE RLS + app-role grants. Object keys stay private.

CREATE TABLE IF NOT EXISTS analysis_runs (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_run_id UUID REFERENCES workflow_runs(run_id) ON DELETE SET NULL,
  project_id UUID NOT NULL,
  source_file_id UUID,
  upload_id UUID,
  mode TEXT NOT NULL DEFAULT 'full'
    CHECK (mode IN ('full', 'focused', 'resume')),
  status TEXT NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
  module_key TEXT NOT NULL DEFAULT 'analysis_planner',
  instruction TEXT NOT NULL DEFAULT '',
  hints_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(hints_jsonb) = 'object'),
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

CREATE INDEX IF NOT EXISTS idx_analysis_runs_project_status
  ON analysis_runs (tenant_id, project_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_analysis_runs_workflow_run
  ON analysis_runs (tenant_id, workflow_run_id)
  WHERE workflow_run_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS analysis_workspace_files (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  file_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL,
  path TEXT NOT NULL
    CHECK (
      path ~ '^(00-plan|10-source|20-notes|30-candidates|90-review)/[A-Za-z0-9._/-]+$'
      AND path NOT LIKE '%..%'
      AND char_length(path) <= 512
    ),
  kind TEXT NOT NULL DEFAULT 'text'
    CHECK (kind IN ('plan', 'todo', 'hints', 'source_manifest', 'source_segment', 'note', 'candidate', 'review', 'text', 'json')),
  mime_type TEXT NOT NULL DEFAULT 'text/plain',
  size_bytes BIGINT NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
  content_sha256 TEXT NOT NULL
    CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
  object_key TEXT NOT NULL
    CHECK (
      object_key ~ '^projects/[0-9a-f-]{36}/analysis/[0-9a-f-]{36}/'
      AND object_key NOT LIKE '%..%'
    ),
  content_text TEXT,
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(metadata_jsonb) = 'object'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, run_id, path),
  UNIQUE (tenant_id, project_id, file_id),
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES analysis_runs(tenant_id, project_id, run_id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE,
  CONSTRAINT analysis_workspace_files_metadata_no_private_check
    CHECK (
      NOT (metadata_jsonb ? 'api_key')
      AND NOT (metadata_jsonb ? 'credential_ref')
      AND NOT (metadata_jsonb ? 'prompt')
      AND NOT (metadata_jsonb ? 'raw_body')
    )
);

CREATE INDEX IF NOT EXISTS idx_analysis_workspace_files_run_path
  ON analysis_workspace_files (tenant_id, project_id, run_id, path);

CREATE TABLE IF NOT EXISTS analysis_candidates (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  candidate_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL,
  candidate_type TEXT NOT NULL
    CHECK (candidate_type IN (
      'character', 'relationship', 'world_rule', 'plot_thread', 'ontology', 'note_summary'
    )),
  name TEXT NOT NULL DEFAULT '',
  payload_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(payload_jsonb) = 'object'),
  status TEXT NOT NULL DEFAULT 'candidate'
    CHECK (status IN ('candidate', 'accepted', 'rejected')),
  workspace_path TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, candidate_id),
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES analysis_runs(tenant_id, project_id, run_id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_analysis_candidates_run_type
  ON analysis_candidates (tenant_id, project_id, run_id, candidate_type, status);

REVOKE ALL ON analysis_runs FROM PUBLIC, mirofish_app;
REVOKE ALL ON analysis_workspace_files FROM PUBLIC, mirofish_app;
REVOKE ALL ON analysis_candidates FROM PUBLIC, mirofish_app;

GRANT SELECT, INSERT, UPDATE ON analysis_runs TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON analysis_workspace_files TO mirofish_app;
GRANT SELECT, INSERT, UPDATE ON analysis_candidates TO mirofish_app;

ALTER TABLE analysis_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_runs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_analysis_runs ON analysis_runs;
CREATE POLICY tenant_isolation_analysis_runs
ON analysis_runs
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

ALTER TABLE analysis_workspace_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_workspace_files FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_analysis_workspace_files ON analysis_workspace_files;
CREATE POLICY tenant_isolation_analysis_workspace_files
ON analysis_workspace_files
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

ALTER TABLE analysis_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_candidates FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_analysis_candidates ON analysis_candidates;
CREATE POLICY tenant_isolation_analysis_candidates
ON analysis_candidates
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

COMMIT;
