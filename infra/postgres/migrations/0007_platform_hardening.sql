BEGIN;

CREATE TABLE auth_abuse_rate_limits (
  scope_key_hash TEXT PRIMARY KEY CHECK (scope_key_hash ~ '^[0-9a-f]{64}$'),
  action TEXT NOT NULL CHECK (btrim(action) <> ''),
  window_started_at TIMESTAMPTZ NOT NULL,
  request_count BIGINT NOT NULL DEFAULT 0 CHECK (request_count >= 0),
  blocked_until TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (blocked_until IS NULL OR blocked_until >= window_started_at)
);

CREATE INDEX idx_auth_abuse_rate_limits_cleanup
  ON auth_abuse_rate_limits (updated_at, blocked_until);
REVOKE ALL ON auth_abuse_rate_limits FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON auth_abuse_rate_limits TO mirofish_app;

ALTER TABLE llm_models
  ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT TRUE;
CREATE INDEX IF NOT EXISTS idx_llm_models_enabled_scope
  ON llm_models (tenant_id, channel_id, model_id)
  WHERE enabled = TRUE;

-- Fail before installing scoped source constraints if an older database contains
-- references that were legal under the original single-column foreign keys.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM manuscript_blocks AS block
    JOIN writer_runs AS run ON run.run_id = block.source_writer_run_id
    WHERE block.source_writer_run_id IS NOT NULL
      AND (run.tenant_id, run.project_id) IS DISTINCT FROM (block.tenant_id, block.project_id)
  ) OR EXISTS (
    SELECT 1
    FROM manuscript_blocks AS block
    JOIN writer_drafts AS draft ON draft.draft_id = block.source_draft_id
    WHERE block.source_draft_id IS NOT NULL
      AND (draft.tenant_id, draft.project_id) IS DISTINCT FROM (block.tenant_id, block.project_id)
  ) OR EXISTS (
    SELECT 1
    FROM manuscript_block_versions AS version
    JOIN writer_runs AS run ON run.run_id = version.source_writer_run_id
    WHERE version.source_writer_run_id IS NOT NULL
      AND (run.tenant_id, run.project_id) IS DISTINCT FROM (version.tenant_id, version.project_id)
  ) OR EXISTS (
    SELECT 1
    FROM manuscript_block_versions AS version
    JOIN writer_drafts AS draft ON draft.draft_id = version.source_draft_id
    WHERE version.source_draft_id IS NOT NULL
      AND (draft.tenant_id, draft.project_id) IS DISTINCT FROM (version.tenant_id, version.project_id)
  ) THEN
    RAISE EXCEPTION 'platform hardening preflight failed: manuscript source ownership mismatch';
  END IF;
END;
$$;

ALTER TABLE writer_runs
  ADD CONSTRAINT writer_runs_scope_key UNIQUE (tenant_id, project_id, run_id);
ALTER TABLE writer_drafts
  ADD CONSTRAINT writer_drafts_scope_key UNIQUE (tenant_id, project_id, draft_id);

ALTER TABLE manuscript_blocks
  ADD CONSTRAINT manuscript_blocks_source_writer_run_scope_fk
    FOREIGN KEY (tenant_id, project_id, source_writer_run_id)
    REFERENCES writer_runs(tenant_id, project_id, run_id) ON DELETE RESTRICT NOT VALID,
  ADD CONSTRAINT manuscript_blocks_source_draft_scope_fk
    FOREIGN KEY (tenant_id, project_id, source_draft_id)
    REFERENCES writer_drafts(tenant_id, project_id, draft_id) ON DELETE RESTRICT NOT VALID;

ALTER TABLE manuscript_block_versions
  ADD CONSTRAINT manuscript_block_versions_source_writer_run_scope_fk
    FOREIGN KEY (tenant_id, project_id, source_writer_run_id)
    REFERENCES writer_runs(tenant_id, project_id, run_id) ON DELETE RESTRICT NOT VALID,
  ADD CONSTRAINT manuscript_block_versions_source_draft_scope_fk
    FOREIGN KEY (tenant_id, project_id, source_draft_id)
    REFERENCES writer_drafts(tenant_id, project_id, draft_id) ON DELETE RESTRICT NOT VALID;

ALTER TABLE manuscript_blocks
  VALIDATE CONSTRAINT manuscript_blocks_source_writer_run_scope_fk,
  VALIDATE CONSTRAINT manuscript_blocks_source_draft_scope_fk;
ALTER TABLE manuscript_block_versions
  VALIDATE CONSTRAINT manuscript_block_versions_source_writer_run_scope_fk,
  VALIDATE CONSTRAINT manuscript_block_versions_source_draft_scope_fk;

ALTER TABLE collaboration_invitations
  ADD CONSTRAINT collaboration_invitations_tenant_invitation_key UNIQUE (tenant_id, invitation_id);
ALTER TABLE collaboration_delivery_attempts
  ADD CONSTRAINT collaboration_delivery_attempts_invitation_scope_fk
    FOREIGN KEY (tenant_id, invitation_id)
    REFERENCES collaboration_invitations(tenant_id, invitation_id) ON DELETE CASCADE NOT VALID;
ALTER TABLE collaboration_delivery_attempts
  VALIDATE CONSTRAINT collaboration_delivery_attempts_invitation_scope_fk;

COMMIT;
