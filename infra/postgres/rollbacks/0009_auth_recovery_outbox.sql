BEGIN;

DROP FUNCTION IF EXISTS auth_recovery_expire(TIMESTAMPTZ);
DROP FUNCTION IF EXISTS auth_recovery_complete(TEXT, TEXT, TIMESTAMPTZ, TEXT);
DROP FUNCTION IF EXISTS auth_recovery_finish_delivery(UUID, TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ);
DROP FUNCTION IF EXISTS auth_recovery_claim_delivery(TEXT, INTEGER);
DROP FUNCTION IF EXISTS auth_recovery_request(TEXT, TEXT, BYTEA, TEXT, TIMESTAMPTZ);

ALTER TABLE password_reset_tokens DISABLE ROW LEVEL SECURITY;
ALTER TABLE password_reset_delivery_attempts DISABLE ROW LEVEL SECURITY;
ALTER TABLE auth_security_audit_logs DISABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT, UPDATE, DELETE ON password_reset_tokens TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON password_reset_delivery_attempts TO mirofish_app;
GRANT INSERT ON auth_security_audit_logs TO mirofish_app;

DROP TABLE IF EXISTS password_reset_delivery_outbox;

CREATE OR REPLACE FUNCTION reject_manuscript_block_version_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
    RETURN OLD;
  END IF;
  RAISE EXCEPTION 'manuscript block versions are immutable';
END;
$$;

ALTER TABLE manuscript_blocks
  DROP CONSTRAINT IF EXISTS manuscript_blocks_source_writer_run_scope_fk,
  DROP CONSTRAINT IF EXISTS manuscript_blocks_source_draft_scope_fk,
  ADD CONSTRAINT manuscript_blocks_source_writer_run_scope_fk
    FOREIGN KEY (tenant_id, project_id, source_writer_run_id)
    REFERENCES writer_runs(tenant_id, project_id, run_id) ON DELETE RESTRICT,
  ADD CONSTRAINT manuscript_blocks_source_draft_scope_fk
    FOREIGN KEY (tenant_id, project_id, source_draft_id)
    REFERENCES writer_drafts(tenant_id, project_id, draft_id) ON DELETE RESTRICT;

ALTER TABLE manuscript_block_versions
  DROP CONSTRAINT IF EXISTS manuscript_block_versions_source_writer_run_scope_fk,
  DROP CONSTRAINT IF EXISTS manuscript_block_versions_source_draft_scope_fk,
  ADD CONSTRAINT manuscript_block_versions_source_writer_run_scope_fk
    FOREIGN KEY (tenant_id, project_id, source_writer_run_id)
    REFERENCES writer_runs(tenant_id, project_id, run_id) ON DELETE RESTRICT,
  ADD CONSTRAINT manuscript_block_versions_source_draft_scope_fk
    FOREIGN KEY (tenant_id, project_id, source_draft_id)
    REFERENCES writer_drafts(tenant_id, project_id, draft_id) ON DELETE RESTRICT;

COMMIT;
