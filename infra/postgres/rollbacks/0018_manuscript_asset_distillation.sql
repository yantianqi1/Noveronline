BEGIN;

DROP POLICY IF EXISTS tenant_isolation_asset_candidate_evidence ON asset_candidate_evidence;
DROP POLICY IF EXISTS tenant_isolation_asset_candidate_proposals ON asset_candidate_proposals;
DROP POLICY IF EXISTS tenant_isolation_manuscript_asset_distillation_requests ON manuscript_asset_distillation_requests;
DROP POLICY IF EXISTS tenant_isolation_project_asset_distillation_settings ON project_asset_distillation_settings;

DROP TABLE IF EXISTS asset_candidate_evidence;
DROP TABLE IF EXISTS asset_candidate_proposals;
DROP TABLE IF EXISTS manuscript_asset_distillation_requests;
DROP TABLE IF EXISTS project_asset_distillation_settings;

ALTER TABLE manuscript_block_versions
  DROP CONSTRAINT IF EXISTS manuscript_block_versions_snapshot_reason_check;

ALTER TABLE manuscript_block_versions
  ADD CONSTRAINT manuscript_block_versions_snapshot_reason_check
    CHECK (snapshot_reason IN ('update', 'delete', 'move', 'tag', 'restore'));

DELETE FROM mirofish_schema_migrations
WHERE version = '0018_manuscript_asset_distillation';

COMMIT;
