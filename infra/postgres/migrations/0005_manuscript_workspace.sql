BEGIN;

ALTER TABLE manuscript_blocks
  ADD COLUMN IF NOT EXISTS scene_id UUID,
  ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active',
  ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS updated_by UUID REFERENCES users(user_id),
  ADD COLUMN IF NOT EXISTS source_writer_run_id UUID;

ALTER TABLE manuscript_blocks
  DROP CONSTRAINT IF EXISTS manuscript_blocks_status_check,
  ADD CONSTRAINT manuscript_blocks_status_check
    CHECK (status IN ('active', 'deleted')),
  DROP CONSTRAINT IF EXISTS manuscript_blocks_version_check,
  ADD CONSTRAINT manuscript_blocks_version_check CHECK (version > 0),
  DROP CONSTRAINT IF EXISTS manuscript_blocks_tags_check,
  ADD CONSTRAINT manuscript_blocks_tags_check CHECK (array_position(tags, NULL) IS NULL),
  DROP CONSTRAINT IF EXISTS manuscript_blocks_workspace_identity_key,
  ADD CONSTRAINT manuscript_blocks_workspace_identity_key UNIQUE (tenant_id, project_id, block_id),
  DROP CONSTRAINT IF EXISTS manuscript_blocks_source_writer_run_fk,
  ADD CONSTRAINT manuscript_blocks_source_writer_run_fk
    FOREIGN KEY (source_writer_run_id) REFERENCES writer_runs(run_id) ON DELETE SET NULL;

UPDATE manuscript_blocks AS block
SET source_writer_run_id = draft.run_id,
    updated_by = COALESCE(block.updated_by, block.created_by)
FROM writer_drafts AS draft
WHERE block.source_draft_id = draft.draft_id
  AND block.tenant_id = draft.tenant_id
  AND block.project_id = draft.project_id;

DO $reconcile$
DECLARE
  invalid_chapters BIGINT;
  invalid_scenes BIGINT;
  mismatched_locations BIGINT;
  unresolved_locations BIGINT;
BEGIN
  SELECT count(*) INTO invalid_chapters
  FROM manuscript_blocks AS block
  WHERE block.chapter_id IS NOT NULL
    AND NOT EXISTS (
      SELECT 1 FROM chapters AS chapter
      WHERE chapter.tenant_id = block.tenant_id
        AND chapter.project_id = block.project_id
        AND chapter.chapter_id = block.chapter_id
    );
  SELECT count(*) INTO invalid_scenes
  FROM manuscript_blocks AS block
  WHERE block.scene_id IS NOT NULL
    AND NOT EXISTS (
      SELECT 1 FROM scenes AS scene
      WHERE scene.tenant_id = block.tenant_id
        AND scene.project_id = block.project_id
        AND scene.scene_id = block.scene_id
    );
  SELECT count(*) INTO mismatched_locations
  FROM manuscript_blocks AS block
  JOIN scenes AS scene
    ON scene.tenant_id = block.tenant_id
   AND scene.project_id = block.project_id
   AND scene.scene_id = block.scene_id
  WHERE block.chapter_id IS DISTINCT FROM scene.chapter_id;

  UPDATE manuscript_blocks AS block
  SET chapter_id = scene.chapter_id
  FROM scenes AS scene
  WHERE scene.tenant_id = block.tenant_id
    AND scene.project_id = block.project_id
    AND scene.scene_id = block.scene_id
    AND block.chapter_id IS DISTINCT FROM scene.chapter_id;

  UPDATE manuscript_blocks AS block
  SET scene_id = NULL
  WHERE block.scene_id IS NOT NULL
    AND NOT EXISTS (
      SELECT 1 FROM scenes AS scene
      WHERE scene.tenant_id = block.tenant_id
        AND scene.project_id = block.project_id
        AND scene.scene_id = block.scene_id
    );

  UPDATE manuscript_blocks AS block
  SET chapter_id = draft.chapter_id
  FROM writer_drafts AS draft
  JOIN chapters AS chapter
    ON chapter.tenant_id = draft.tenant_id
   AND chapter.project_id = draft.project_id
   AND chapter.chapter_id = draft.chapter_id
  WHERE block.source_draft_id = draft.draft_id
    AND block.tenant_id = draft.tenant_id
    AND block.project_id = draft.project_id
    AND (block.chapter_id IS NULL OR NOT EXISTS (
      SELECT 1 FROM chapters AS current_chapter
      WHERE current_chapter.tenant_id = block.tenant_id
        AND current_chapter.project_id = block.project_id
        AND current_chapter.chapter_id = block.chapter_id
    ));

  UPDATE manuscript_blocks AS block
  SET chapter_id = NULL
  WHERE block.chapter_id IS NOT NULL
    AND NOT EXISTS (
      SELECT 1 FROM chapters AS chapter
      WHERE chapter.tenant_id = block.tenant_id
        AND chapter.project_id = block.project_id
        AND chapter.chapter_id = block.chapter_id
    );

  UPDATE manuscript_blocks AS block
  SET scene_id = draft.scene_id,
      chapter_id = scene.chapter_id
  FROM writer_drafts AS draft
  JOIN scenes AS scene
    ON scene.tenant_id = draft.tenant_id
   AND scene.project_id = draft.project_id
   AND scene.scene_id = draft.scene_id
  WHERE block.source_draft_id = draft.draft_id
    AND block.tenant_id = draft.tenant_id
    AND block.project_id = draft.project_id
    AND block.scene_id IS NULL
    AND (block.chapter_id IS NULL OR block.chapter_id = scene.chapter_id);

  SELECT count(*) INTO unresolved_locations
  FROM manuscript_blocks AS block
  LEFT JOIN chapters AS chapter
    ON chapter.tenant_id = block.tenant_id
   AND chapter.project_id = block.project_id
   AND chapter.chapter_id = block.chapter_id
  LEFT JOIN scenes AS scene
    ON scene.tenant_id = block.tenant_id
   AND scene.project_id = block.project_id
   AND scene.chapter_id = block.chapter_id
   AND scene.scene_id = block.scene_id
  WHERE (block.chapter_id IS NOT NULL AND chapter.chapter_id IS NULL)
     OR (block.scene_id IS NOT NULL AND scene.scene_id IS NULL);
  IF unresolved_locations > 0 THEN
    RAISE EXCEPTION 'manuscript block FK reconcile failed: % unresolved locations', unresolved_locations;
  END IF;
  RAISE NOTICE 'manuscript block FK reconcile: invalid_chapters=%, invalid_scenes=%, mismatched_locations=%',
    invalid_chapters, invalid_scenes, mismatched_locations;
END
$reconcile$;

ALTER TABLE manuscript_blocks
  DROP CONSTRAINT IF EXISTS manuscript_blocks_location_check,
  ADD CONSTRAINT manuscript_blocks_location_check
    CHECK (scene_id IS NULL OR chapter_id IS NOT NULL) NOT VALID,
  DROP CONSTRAINT IF EXISTS manuscript_blocks_chapter_fk,
  ADD CONSTRAINT manuscript_blocks_chapter_fk
    FOREIGN KEY (tenant_id, project_id, chapter_id)
    REFERENCES chapters(tenant_id, project_id, chapter_id) ON DELETE RESTRICT NOT VALID,
  DROP CONSTRAINT IF EXISTS manuscript_blocks_scene_fk,
  ADD CONSTRAINT manuscript_blocks_scene_fk
    FOREIGN KEY (tenant_id, project_id, chapter_id, scene_id)
    REFERENCES scenes(tenant_id, project_id, chapter_id, scene_id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE manuscript_blocks VALIDATE CONSTRAINT manuscript_blocks_location_check;
ALTER TABLE manuscript_blocks VALIDATE CONSTRAINT manuscript_blocks_chapter_fk;
ALTER TABLE manuscript_blocks VALIDATE CONSTRAINT manuscript_blocks_scene_fk;

ALTER TABLE manuscript_blocks
  DROP CONSTRAINT IF EXISTS manuscript_blocks_tenant_id_project_id_block_order_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_manuscript_blocks_active_order
  ON manuscript_blocks (tenant_id, project_id, block_order)
  WHERE status = 'active';

CREATE TABLE IF NOT EXISTS manuscript_block_versions (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  block_id UUID NOT NULL,
  version_number INTEGER NOT NULL CHECK (version_number > 0),
  chapter_id UUID,
  scene_id UUID,
  status TEXT NOT NULL CHECK (status IN ('active', 'deleted')),
  tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  block_order INTEGER NOT NULL CHECK (block_order >= 0),
  content_text TEXT NOT NULL,
  word_count INTEGER NOT NULL DEFAULT 0 CHECK (word_count >= 0),
  pov_entity_id UUID,
  source_draft_id UUID,
  source_writer_run_id UUID,
  snapshot_reason TEXT NOT NULL CHECK (snapshot_reason IN ('update', 'delete', 'move', 'tag', 'restore')),
  restored_from_version_id UUID,
  created_by UUID NOT NULL REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, block_id, version_number),
  UNIQUE (tenant_id, project_id, version_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id, block_id) REFERENCES manuscript_blocks(tenant_id, project_id, block_id) ON DELETE RESTRICT,
  CONSTRAINT manuscript_block_versions_location_check CHECK (scene_id IS NULL OR chapter_id IS NOT NULL),
  CONSTRAINT manuscript_block_versions_chapter_fk FOREIGN KEY (tenant_id, project_id, chapter_id) REFERENCES chapters(tenant_id, project_id, chapter_id) ON DELETE RESTRICT,
  CONSTRAINT manuscript_block_versions_scene_fk FOREIGN KEY (tenant_id, project_id, chapter_id, scene_id) REFERENCES scenes(tenant_id, project_id, chapter_id, scene_id) ON DELETE RESTRICT,
  FOREIGN KEY (source_draft_id) REFERENCES writer_drafts(draft_id) ON DELETE SET NULL,
  FOREIGN KEY (source_writer_run_id) REFERENCES writer_runs(run_id) ON DELETE SET NULL,
  FOREIGN KEY (tenant_id, project_id, restored_from_version_id)
    REFERENCES manuscript_block_versions(tenant_id, project_id, version_id) ON DELETE RESTRICT
);

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

DROP TRIGGER IF EXISTS manuscript_block_versions_immutable ON manuscript_block_versions;
CREATE TRIGGER manuscript_block_versions_immutable
BEFORE UPDATE OR DELETE ON manuscript_block_versions
FOR EACH ROW EXECUTE FUNCTION reject_manuscript_block_version_mutation();

CREATE TABLE IF NOT EXISTS manuscript_exports (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  export_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  format TEXT NOT NULL CHECK (format IN ('txt', 'docx', 'pdf', 'epub')),
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'generating', 'completed', 'failed', 'cancelled')),
  artifact_sha256 TEXT,
  artifact_size_bytes BIGINT CHECK (artifact_size_bytes IS NULL OR artifact_size_bytes > 0),
  artifact_object_ref TEXT,
  block_count INTEGER NOT NULL DEFAULT 0 CHECK (block_count >= 0),
  request_id TEXT NOT NULL CHECK (btrim(request_id) <> ''),
  error_code TEXT,
  created_by UUID NOT NULL REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, request_id),
  UNIQUE (tenant_id, project_id, export_id),
  CHECK (
    status <> 'completed'
    OR (
      artifact_sha256 ~ '^[0-9a-f]{64}$'
      AND artifact_size_bytes > 0
      AND btrim(artifact_object_ref) <> ''
      AND block_count > 0
      AND completed_at IS NOT NULL
    )
  ),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS writer_command_runs (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  command_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  command_type TEXT NOT NULL CHECK (command_type IN (
    'complete_outline', 'align_words', 'scan_lexicon', 'fill_relationships', 'continue_chapter'
  )),
  target_chapter_id UUID,
  target_scene_id UUID,
  target_block_id UUID,
  starter_kind TEXT NOT NULL CHECK (starter_kind IN ('writer', 'workflow', 'deterministic')),
  candidate_kind TEXT NOT NULL CHECK (candidate_kind IN ('outline', 'prose', 'lexicon_match', 'relationship', 'draft')),
  status TEXT NOT NULL DEFAULT 'starting' CHECK (status IN ('starting', 'queued', 'running', 'completed', 'failed', 'cancelled')),
  workflow_run_id UUID REFERENCES workflow_runs(run_id) ON DELETE SET NULL,
  writer_run_id UUID REFERENCES writer_runs(run_id) ON DELETE SET NULL,
  request_id TEXT NOT NULL CHECK (btrim(request_id) <> ''),
  input_fingerprint TEXT NOT NULL CHECK (input_fingerprint ~ '^[0-9a-f]{64}$'),
  candidate_count INTEGER NOT NULL DEFAULT 0 CHECK (candidate_count >= 0),
  match_count INTEGER NOT NULL DEFAULT 0 CHECK (match_count >= 0),
  error_code TEXT,
  created_by UUID NOT NULL REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, request_id),
  UNIQUE (tenant_id, project_id, command_run_id),
  CHECK (NOT (workflow_run_id IS NOT NULL AND writer_run_id IS NOT NULL)),
  CHECK (status <> 'completed' OR completed_at IS NOT NULL),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id, target_chapter_id) REFERENCES chapters(tenant_id, project_id, chapter_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, target_scene_id) REFERENCES scenes(tenant_id, project_id, scene_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, target_block_id) REFERENCES manuscript_blocks(tenant_id, project_id, block_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS writer_dedup_patterns (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  pattern_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  pattern_text TEXT NOT NULL CHECK (btrim(pattern_text) <> ''),
  normalized_pattern TEXT NOT NULL CHECK (btrim(normalized_pattern) <> ''),
  pattern_kind TEXT NOT NULL CHECK (pattern_kind IN ('phrase', 'sentence_shape', 'transition', 'description')),
  lifecycle TEXT NOT NULL DEFAULT 'candidate' CHECK (lifecycle IN ('candidate', 'accepted', 'rejected')),
  enabled BOOLEAN NOT NULL DEFAULT FALSE,
  occurrence_count INTEGER NOT NULL DEFAULT 0 CHECK (occurrence_count >= 0),
  source_command_run_id UUID,
  source_workflow_run_id UUID REFERENCES workflow_runs(run_id) ON DELETE SET NULL,
  accepted_by UUID REFERENCES users(user_id),
  accepted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, normalized_pattern),
  UNIQUE (tenant_id, project_id, pattern_id),
  CHECK (
    (lifecycle = 'candidate' AND enabled = FALSE AND accepted_by IS NULL AND accepted_at IS NULL)
    OR (lifecycle = 'accepted' AND enabled = TRUE AND accepted_by IS NOT NULL AND accepted_at IS NOT NULL)
    OR (lifecycle = 'rejected' AND enabled = FALSE)
  ),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id, source_command_run_id)
    REFERENCES writer_command_runs(tenant_id, project_id, command_run_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_manuscript_blocks_scope_order
  ON manuscript_blocks (tenant_id, project_id, status, chapter_id, scene_id, block_order);
CREATE INDEX IF NOT EXISTS idx_manuscript_block_versions_block
  ON manuscript_block_versions (tenant_id, project_id, block_id, version_number DESC);
CREATE INDEX IF NOT EXISTS idx_manuscript_exports_project_status
  ON manuscript_exports (tenant_id, project_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_writer_command_runs_project_status
  ON writer_command_runs (tenant_id, project_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_writer_dedup_patterns_project_lifecycle
  ON writer_dedup_patterns (tenant_id, project_id, lifecycle, enabled, created_at DESC);

GRANT SELECT, INSERT, UPDATE, DELETE ON manuscript_block_versions TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON manuscript_exports TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON writer_command_runs TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON writer_dedup_patterns TO mirofish_app;

ALTER TABLE manuscript_block_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE manuscript_block_versions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_manuscript_block_versions ON manuscript_block_versions;
CREATE POLICY tenant_isolation_manuscript_block_versions ON manuscript_block_versions FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE manuscript_exports ENABLE ROW LEVEL SECURITY;
ALTER TABLE manuscript_exports FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_manuscript_exports ON manuscript_exports;
CREATE POLICY tenant_isolation_manuscript_exports ON manuscript_exports FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE writer_command_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE writer_command_runs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_writer_command_runs ON writer_command_runs;
CREATE POLICY tenant_isolation_writer_command_runs ON writer_command_runs FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE writer_dedup_patterns ENABLE ROW LEVEL SECURITY;
ALTER TABLE writer_dedup_patterns FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_writer_dedup_patterns ON writer_dedup_patterns;
CREATE POLICY tenant_isolation_writer_dedup_patterns ON writer_dedup_patterns FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

COMMIT;
