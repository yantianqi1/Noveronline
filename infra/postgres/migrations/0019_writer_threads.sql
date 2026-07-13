BEGIN;

-- 0019: Persistent Writer Agent threads + messages + approval decisions.
-- Additive only. FORCE RLS + app-role grants. Messages are append-oriented.
-- Also expands writer_runs.mode to include revise (selection-driven edits).

ALTER TABLE writer_runs
  DROP CONSTRAINT IF EXISTS writer_runs_mode_check;

ALTER TABLE writer_runs
  ADD CONSTRAINT writer_runs_mode_check
    CHECK (mode IN ('draft', 'continue', 'outline', 'review', 'revise'));

CREATE TABLE IF NOT EXISTS writer_threads (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  thread_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT,
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'archived')),
  created_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
  updated_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, thread_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_writer_threads_project_updated
  ON writer_threads (tenant_id, project_id, updated_at DESC)
  WHERE status = 'active';

CREATE TABLE IF NOT EXISTS writer_thread_messages (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  thread_id UUID NOT NULL,
  role TEXT NOT NULL
    CHECK (role IN ('user', 'agent', 'system', 'approval')),
  body TEXT NOT NULL CHECK (btrim(body) <> ''),
  run_id UUID REFERENCES writer_runs(run_id) ON DELETE SET NULL,
  sequence BIGINT NOT NULL CHECK (sequence > 0),
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(metadata_jsonb) = 'object'),
  created_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, message_id),
  UNIQUE (tenant_id, project_id, thread_id, sequence),
  FOREIGN KEY (tenant_id, project_id, thread_id)
    REFERENCES writer_threads(tenant_id, project_id, thread_id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE,
  CONSTRAINT writer_thread_messages_metadata_no_private_check
    CHECK (
      NOT (metadata_jsonb ? 'api_key')
      AND NOT (metadata_jsonb ? 'credential_ref')
      AND NOT (metadata_jsonb ? 'prompt')
      AND NOT (metadata_jsonb ? 'raw_body')
    )
);

CREATE INDEX IF NOT EXISTS idx_writer_thread_messages_thread_seq
  ON writer_thread_messages (tenant_id, project_id, thread_id, sequence);

CREATE TABLE IF NOT EXISTS writer_approvals (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  approval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES writer_runs(run_id) ON DELETE CASCADE,
  thread_id UUID,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'approved', 'rejected')),
  action TEXT NOT NULL CHECK (btrim(action) <> ''),
  summary TEXT NOT NULL CHECK (btrim(summary) <> ''),
  consequence TEXT NOT NULL DEFAULT '',
  reversible BOOLEAN NOT NULL DEFAULT false,
  decided_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
  decided_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, approval_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id, thread_id)
    REFERENCES writer_threads(tenant_id, project_id, thread_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_writer_approvals_run_status
  ON writer_approvals (tenant_id, project_id, run_id, status);

-- Grants + FORCE RLS
REVOKE ALL ON writer_threads FROM PUBLIC, mirofish_app;
REVOKE ALL ON writer_thread_messages FROM PUBLIC, mirofish_app;
REVOKE ALL ON writer_approvals FROM PUBLIC, mirofish_app;

GRANT SELECT, INSERT, UPDATE ON writer_threads TO mirofish_app;
GRANT SELECT, INSERT ON writer_thread_messages TO mirofish_app;
GRANT SELECT, INSERT, UPDATE ON writer_approvals TO mirofish_app;

ALTER TABLE writer_threads ENABLE ROW LEVEL SECURITY;
ALTER TABLE writer_threads FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_writer_threads ON writer_threads;
CREATE POLICY tenant_isolation_writer_threads
ON writer_threads
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

ALTER TABLE writer_thread_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE writer_thread_messages FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_writer_thread_messages ON writer_thread_messages;
CREATE POLICY tenant_isolation_writer_thread_messages
ON writer_thread_messages
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

ALTER TABLE writer_approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE writer_approvals FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_writer_approvals ON writer_approvals;
CREATE POLICY tenant_isolation_writer_approvals
ON writer_approvals
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

COMMIT;
