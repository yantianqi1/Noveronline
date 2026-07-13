BEGIN;

-- 0018: Zero-start Writer manuscript asset distillation tables, adopt snapshot reason,
-- project defaults. Additive only; no candidate data backfill.

-- ---------------------------------------------------------------------------
-- Manuscript version snapshot reason: allow initial adopt snapshots
-- ---------------------------------------------------------------------------
ALTER TABLE manuscript_block_versions
  DROP CONSTRAINT IF EXISTS manuscript_block_versions_snapshot_reason_check;

ALTER TABLE manuscript_block_versions
  ADD CONSTRAINT manuscript_block_versions_snapshot_reason_check
    CHECK (snapshot_reason IN ('adopt', 'update', 'delete', 'move', 'tag', 'restore'));

-- ---------------------------------------------------------------------------
-- project_asset_distillation_settings
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS project_asset_distillation_settings (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  trigger_mode TEXT NOT NULL DEFAULT 'manual'
    CHECK (trigger_mode IN ('off', 'manual', 'after_adoption', 'chapter_complete')),
  enabled_asset_types TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  created_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
  updated_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, project_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE,
  CONSTRAINT project_asset_distillation_settings_types_null_check
    CHECK (array_position(enabled_asset_types, NULL) IS NULL)
);

-- Existing projects stay manual to avoid unannounced auto provider spend.
INSERT INTO project_asset_distillation_settings (
  tenant_id,
  project_id,
  trigger_mode,
  enabled_asset_types,
  created_by,
  updated_by
)
SELECT
  project.tenant_id,
  project.project_id,
  'manual',
  ARRAY[]::TEXT[],
  project.created_by,
  project.created_by
FROM projects AS project
ON CONFLICT (tenant_id, project_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- manuscript_asset_distillation_requests (metadata-only outbox)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS manuscript_asset_distillation_requests (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  request_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  trigger_kind TEXT NOT NULL
    CHECK (trigger_kind IN (
      'draft_adoption',
      'manuscript_update',
      'manuscript_restore',
      'chapter_complete',
      'manual'
    )),
  source_manifest_jsonb JSONB NOT NULL,
  input_fingerprint TEXT NOT NULL
    CHECK (input_fingerprint ~ '^[0-9a-f]{64}$'),
  extractor_contract_version INTEGER NOT NULL CHECK (extractor_contract_version > 0),
  dispatch_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (dispatch_status IN ('pending', 'dispatched', 'cancelled')),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  next_attempt_at TIMESTAMPTZ,
  last_dispatch_error_code TEXT
    CHECK (last_dispatch_error_code IS NULL OR btrim(last_dispatch_error_code) <> ''),
  requested_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, run_id),
  UNIQUE (tenant_id, project_id, input_fingerprint, extractor_contract_version),
  UNIQUE (tenant_id, project_id, request_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE,
  CONSTRAINT manuscript_asset_distillation_requests_manifest_object_check
    CHECK (jsonb_typeof(source_manifest_jsonb) = 'object'),
  CONSTRAINT manuscript_asset_distillation_requests_manifest_no_body_check
    CHECK (
      NOT (source_manifest_jsonb ? 'content_text')
      AND NOT (source_manifest_jsonb ? 'body')
      AND NOT (source_manifest_jsonb ? 'evidence_text')
      AND NOT (source_manifest_jsonb ? 'prompt')
      AND NOT (source_manifest_jsonb ? 'quote')
    )
);

CREATE INDEX IF NOT EXISTS idx_manuscript_asset_distillation_requests_dispatch
  ON manuscript_asset_distillation_requests (
    tenant_id,
    dispatch_status,
    next_attempt_at NULLS FIRST,
    created_at
  )
  WHERE dispatch_status = 'pending';

CREATE INDEX IF NOT EXISTS idx_manuscript_asset_distillation_requests_project
  ON manuscript_asset_distillation_requests (tenant_id, project_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- asset_candidate_proposals
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asset_candidate_proposals (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  candidate_asset_id UUID PRIMARY KEY REFERENCES assets(asset_id) ON DELETE CASCADE,
  request_id UUID NOT NULL,
  operation TEXT NOT NULL CHECK (operation IN ('create', 'update')),
  target_asset_id UUID,
  expected_target_version INTEGER CHECK (expected_target_version IS NULL OR expected_target_version > 0),
  normalized_identity TEXT NOT NULL CHECK (btrim(normalized_identity) <> ''),
  confidence NUMERIC CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  review_status TEXT NOT NULL DEFAULT 'staging'
    CHECK (review_status IN (
      'staging',
      'pending',
      'accepted',
      'rejected',
      'superseded',
      'stale',
      'conflict'
    )),
  accepted_asset_id UUID,
  decision_note TEXT,
  reviewed_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
  reviewed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, candidate_asset_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id, request_id)
    REFERENCES manuscript_asset_distillation_requests(tenant_id, project_id, request_id)
    ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id, candidate_asset_id)
    REFERENCES assets(tenant_id, project_id, asset_id)
    ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id, target_asset_id)
    REFERENCES assets(tenant_id, project_id, asset_id)
    ON DELETE SET NULL,
  FOREIGN KEY (tenant_id, project_id, accepted_asset_id)
    REFERENCES assets(tenant_id, project_id, asset_id)
    ON DELETE SET NULL,
  CONSTRAINT asset_candidate_proposals_update_target_check
    CHECK (
      (operation = 'create' AND target_asset_id IS NULL AND expected_target_version IS NULL)
      OR (operation = 'update' AND (
        target_asset_id IS NOT NULL
        OR review_status IN ('staging', 'conflict', 'stale', 'superseded', 'rejected')
      ))
    ),
  CONSTRAINT asset_candidate_proposals_decision_consistency_check
    CHECK (
      (review_status = 'accepted' AND accepted_asset_id IS NOT NULL AND reviewed_at IS NOT NULL)
      OR (review_status = 'rejected' AND reviewed_at IS NOT NULL)
      OR (review_status NOT IN ('accepted', 'rejected'))
    )
);

CREATE INDEX IF NOT EXISTS idx_asset_candidate_proposals_request_status
  ON asset_candidate_proposals (tenant_id, project_id, request_id, review_status);

CREATE INDEX IF NOT EXISTS idx_asset_candidate_proposals_project_status_created
  ON asset_candidate_proposals (tenant_id, project_id, review_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_asset_candidate_proposals_target
  ON asset_candidate_proposals (tenant_id, project_id, target_asset_id)
  WHERE target_asset_id IS NOT NULL;

-- One current pending identity per project fact.
CREATE UNIQUE INDEX IF NOT EXISTS asset_candidate_proposals_pending_identity_key
  ON asset_candidate_proposals (tenant_id, project_id, normalized_identity)
  WHERE review_status = 'pending';

-- ---------------------------------------------------------------------------
-- asset_candidate_evidence (private, FORCE RLS)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asset_candidate_evidence (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  candidate_asset_id UUID NOT NULL,
  block_id UUID NOT NULL,
  block_version INTEGER NOT NULL CHECK (block_version > 0),
  content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  start_offset INTEGER NOT NULL CHECK (start_offset >= 0),
  end_offset INTEGER NOT NULL,
  evidence_text TEXT NOT NULL CHECK (btrim(evidence_text) <> ''),
  confidence NUMERIC CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, candidate_asset_id, block_id, block_version, start_offset, end_offset),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id, candidate_asset_id)
    REFERENCES assets(tenant_id, project_id, asset_id)
    ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id, candidate_asset_id)
    REFERENCES asset_candidate_proposals(tenant_id, project_id, candidate_asset_id)
    ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id, block_id)
    REFERENCES manuscript_blocks(tenant_id, project_id, block_id)
    ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, block_id, block_version)
    REFERENCES manuscript_block_versions(tenant_id, project_id, block_id, version_number)
    ON DELETE RESTRICT,
  CONSTRAINT asset_candidate_evidence_span_check CHECK (end_offset > start_offset)
);

CREATE INDEX IF NOT EXISTS idx_asset_candidate_evidence_candidate
  ON asset_candidate_evidence (tenant_id, project_id, candidate_asset_id);

CREATE INDEX IF NOT EXISTS idx_asset_candidate_evidence_block_version
  ON asset_candidate_evidence (tenant_id, project_id, block_id, block_version);

-- ---------------------------------------------------------------------------
-- Grants and FORCE RLS
-- ---------------------------------------------------------------------------
REVOKE ALL ON project_asset_distillation_settings FROM PUBLIC, mirofish_app;
REVOKE ALL ON manuscript_asset_distillation_requests FROM PUBLIC, mirofish_app;
REVOKE ALL ON asset_candidate_proposals FROM PUBLIC, mirofish_app;
REVOKE ALL ON asset_candidate_evidence FROM PUBLIC, mirofish_app;

GRANT SELECT, INSERT, UPDATE ON project_asset_distillation_settings TO mirofish_app;
GRANT SELECT, INSERT, UPDATE ON manuscript_asset_distillation_requests TO mirofish_app;
GRANT SELECT, INSERT, UPDATE ON asset_candidate_proposals TO mirofish_app;
-- Evidence is append-oriented private provenance; no app DELETE grant.
GRANT SELECT, INSERT ON asset_candidate_evidence TO mirofish_app;

ALTER TABLE project_asset_distillation_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_asset_distillation_settings FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_project_asset_distillation_settings ON project_asset_distillation_settings;
CREATE POLICY tenant_isolation_project_asset_distillation_settings
ON project_asset_distillation_settings
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

ALTER TABLE manuscript_asset_distillation_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE manuscript_asset_distillation_requests FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_manuscript_asset_distillation_requests ON manuscript_asset_distillation_requests;
CREATE POLICY tenant_isolation_manuscript_asset_distillation_requests
ON manuscript_asset_distillation_requests
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

ALTER TABLE asset_candidate_proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE asset_candidate_proposals FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_asset_candidate_proposals ON asset_candidate_proposals;
CREATE POLICY tenant_isolation_asset_candidate_proposals
ON asset_candidate_proposals
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

ALTER TABLE asset_candidate_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE asset_candidate_evidence FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_asset_candidate_evidence ON asset_candidate_evidence;
CREATE POLICY tenant_isolation_asset_candidate_evidence
ON asset_candidate_evidence
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

-- Cross-tenant outbox claim for API dispatcher (metadata only, no evidence/body).
CREATE OR REPLACE FUNCTION claim_manuscript_asset_distillation_outbox(p_limit INTEGER DEFAULT 10)
RETURNS TABLE (
  tenant_id UUID,
  request_id UUID,
  project_id UUID,
  run_id UUID,
  trigger_kind TEXT,
  attempt_count INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN QUERY
  SELECT r.tenant_id, r.request_id, r.project_id, r.run_id, r.trigger_kind, r.attempt_count
  FROM manuscript_asset_distillation_requests AS r
  WHERE r.dispatch_status = 'pending'
    AND (r.next_attempt_at IS NULL OR r.next_attempt_at <= now())
  ORDER BY r.created_at
  LIMIT GREATEST(COALESCE(p_limit, 10), 1)
  FOR UPDATE OF r SKIP LOCKED;
END;
$$;

REVOKE ALL ON FUNCTION claim_manuscript_asset_distillation_outbox(INTEGER) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION claim_manuscript_asset_distillation_outbox(INTEGER) TO mirofish_app;

COMMIT;
