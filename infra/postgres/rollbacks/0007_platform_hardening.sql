BEGIN;

ALTER TABLE collaboration_delivery_attempts
  DROP CONSTRAINT IF EXISTS collaboration_delivery_attempts_invitation_scope_fk;
ALTER TABLE collaboration_invitations
  DROP CONSTRAINT IF EXISTS collaboration_invitations_tenant_invitation_key;

ALTER TABLE manuscript_block_versions
  DROP CONSTRAINT IF EXISTS manuscript_block_versions_source_writer_run_scope_fk,
  DROP CONSTRAINT IF EXISTS manuscript_block_versions_source_draft_scope_fk;
ALTER TABLE manuscript_blocks
  DROP CONSTRAINT IF EXISTS manuscript_blocks_source_writer_run_scope_fk,
  DROP CONSTRAINT IF EXISTS manuscript_blocks_source_draft_scope_fk;
ALTER TABLE writer_drafts DROP CONSTRAINT IF EXISTS writer_drafts_scope_key;
ALTER TABLE writer_runs DROP CONSTRAINT IF EXISTS writer_runs_scope_key;

DROP INDEX IF EXISTS idx_llm_models_enabled_scope;
ALTER TABLE llm_models DROP COLUMN IF EXISTS enabled;
DROP TABLE IF EXISTS auth_abuse_rate_limits;

COMMIT;
