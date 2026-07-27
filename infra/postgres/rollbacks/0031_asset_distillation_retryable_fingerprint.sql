BEGIN;

DROP INDEX IF EXISTS idx_manuscript_asset_distillation_fingerprint_replay;

ALTER TABLE manuscript_asset_distillation_requests
  ADD CONSTRAINT manuscript_asset_distillation_tenant_id_project_id_input_fi_key
  UNIQUE (tenant_id, project_id, input_fingerprint, extractor_contract_version);

DELETE FROM mirofish_schema_migrations
WHERE version = '0031_asset_distillation_retryable_fingerprint';

COMMIT;
