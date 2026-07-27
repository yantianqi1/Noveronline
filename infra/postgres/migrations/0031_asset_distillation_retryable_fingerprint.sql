BEGIN;

-- Fingerprints deduplicate active or completed work in the admission transaction.
-- Failed/cancelled attempts must not permanently prevent a fresh distillation run.
ALTER TABLE manuscript_asset_distillation_requests
  DROP CONSTRAINT IF EXISTS manuscript_asset_distillation_tenant_id_project_id_input_fi_key;

CREATE INDEX IF NOT EXISTS idx_manuscript_asset_distillation_fingerprint_replay
  ON manuscript_asset_distillation_requests (
    tenant_id,
    project_id,
    input_fingerprint,
    extractor_contract_version,
    created_at DESC
  );

COMMIT;
