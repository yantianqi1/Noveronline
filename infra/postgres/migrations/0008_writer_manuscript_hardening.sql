BEGIN;

ALTER TABLE chapters DROP CONSTRAINT IF EXISTS chapters_project_order_key;
ALTER TABLE scenes DROP CONSTRAINT IF EXISTS scenes_chapter_order_key;
CREATE UNIQUE INDEX IF NOT EXISTS chapters_project_active_order_key
  ON chapters (tenant_id, project_id, chapter_order)
  WHERE status <> 'archived';
CREATE UNIQUE INDEX IF NOT EXISTS scenes_chapter_active_order_key
  ON scenes (tenant_id, project_id, chapter_id, scene_order)
  WHERE status <> 'archived';

ALTER TABLE manuscript_blocks
  ADD COLUMN IF NOT EXISTS scene_id UUID,
  ADD COLUMN IF NOT EXISTS updated_by UUID REFERENCES users(user_id),
  ADD COLUMN IF NOT EXISTS source_writer_run_id UUID;

UPDATE manuscript_blocks AS block
SET source_writer_run_id = COALESCE(block.source_writer_run_id, draft.run_id),
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
  invalid_version_locations BIGINT;
BEGIN
  SELECT count(*) INTO invalid_chapters FROM manuscript_blocks AS block
  WHERE block.chapter_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM chapters AS chapter WHERE chapter.tenant_id=block.tenant_id AND chapter.project_id=block.project_id AND chapter.chapter_id=block.chapter_id);
  SELECT count(*) INTO invalid_scenes FROM manuscript_blocks AS block
  WHERE block.scene_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM scenes AS scene WHERE scene.tenant_id=block.tenant_id AND scene.project_id=block.project_id AND scene.scene_id=block.scene_id);
  SELECT count(*) INTO mismatched_locations FROM manuscript_blocks AS block
  JOIN scenes AS scene ON scene.tenant_id=block.tenant_id AND scene.project_id=block.project_id AND scene.scene_id=block.scene_id
  WHERE block.chapter_id IS DISTINCT FROM scene.chapter_id;

  UPDATE manuscript_blocks AS block SET chapter_id=scene.chapter_id
  FROM scenes AS scene
  WHERE scene.tenant_id=block.tenant_id AND scene.project_id=block.project_id AND scene.scene_id=block.scene_id
    AND block.chapter_id IS DISTINCT FROM scene.chapter_id;
  UPDATE manuscript_blocks AS block SET scene_id=NULL
  WHERE block.scene_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM scenes AS scene WHERE scene.tenant_id=block.tenant_id AND scene.project_id=block.project_id AND scene.scene_id=block.scene_id);
  UPDATE manuscript_blocks AS block SET chapter_id=draft.chapter_id
  FROM writer_drafts AS draft
  JOIN chapters AS chapter ON chapter.tenant_id=draft.tenant_id AND chapter.project_id=draft.project_id AND chapter.chapter_id=draft.chapter_id
  WHERE block.source_draft_id=draft.draft_id AND block.tenant_id=draft.tenant_id AND block.project_id=draft.project_id
    AND (block.chapter_id IS NULL OR NOT EXISTS (
      SELECT 1 FROM chapters AS current_chapter WHERE current_chapter.tenant_id=block.tenant_id AND current_chapter.project_id=block.project_id AND current_chapter.chapter_id=block.chapter_id));
  UPDATE manuscript_blocks AS block SET chapter_id=NULL
  WHERE block.chapter_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM chapters AS chapter WHERE chapter.tenant_id=block.tenant_id AND chapter.project_id=block.project_id AND chapter.chapter_id=block.chapter_id);
  UPDATE manuscript_blocks AS block SET scene_id=draft.scene_id, chapter_id=scene.chapter_id
  FROM writer_drafts AS draft
  JOIN scenes AS scene ON scene.tenant_id=draft.tenant_id AND scene.project_id=draft.project_id AND scene.scene_id=draft.scene_id
  WHERE block.source_draft_id=draft.draft_id AND block.tenant_id=draft.tenant_id AND block.project_id=draft.project_id
    AND block.scene_id IS NULL AND (block.chapter_id IS NULL OR block.chapter_id=scene.chapter_id);

  SELECT count(*) INTO unresolved_locations
  FROM manuscript_blocks AS block
  LEFT JOIN chapters AS chapter ON chapter.tenant_id=block.tenant_id AND chapter.project_id=block.project_id AND chapter.chapter_id=block.chapter_id
  LEFT JOIN scenes AS scene ON scene.tenant_id=block.tenant_id AND scene.project_id=block.project_id AND scene.chapter_id=block.chapter_id AND scene.scene_id=block.scene_id
  WHERE (block.chapter_id IS NOT NULL AND chapter.chapter_id IS NULL) OR (block.scene_id IS NOT NULL AND scene.scene_id IS NULL);
  IF unresolved_locations > 0 THEN
    RAISE EXCEPTION 'manuscript block FK reconcile failed: % unresolved locations', unresolved_locations;
  END IF;

  IF to_regclass('manuscript_block_versions') IS NOT NULL THEN
    SELECT count(*) INTO invalid_version_locations
    FROM manuscript_block_versions AS version
    LEFT JOIN chapters AS chapter ON chapter.tenant_id=version.tenant_id AND chapter.project_id=version.project_id AND chapter.chapter_id=version.chapter_id
    LEFT JOIN scenes AS scene ON scene.tenant_id=version.tenant_id AND scene.project_id=version.project_id AND scene.chapter_id=version.chapter_id AND scene.scene_id=version.scene_id
    WHERE (version.chapter_id IS NOT NULL AND chapter.chapter_id IS NULL) OR (version.scene_id IS NOT NULL AND scene.scene_id IS NULL);
    IF invalid_version_locations > 0 THEN
      RAISE EXCEPTION 'manuscript block version location gate failed: % immutable snapshots', invalid_version_locations;
    END IF;
  END IF;
  RAISE NOTICE 'manuscript block FK reconcile: invalid_chapters=%, invalid_scenes=%, mismatched_locations=%', invalid_chapters, invalid_scenes, mismatched_locations;
END
$reconcile$;

ALTER TABLE manuscript_blocks
  DROP CONSTRAINT IF EXISTS manuscript_blocks_location_check,
  ADD CONSTRAINT manuscript_blocks_location_check CHECK (scene_id IS NULL OR chapter_id IS NOT NULL) NOT VALID,
  DROP CONSTRAINT IF EXISTS manuscript_blocks_chapter_fk,
  ADD CONSTRAINT manuscript_blocks_chapter_fk FOREIGN KEY (tenant_id, project_id, chapter_id)
    REFERENCES chapters(tenant_id, project_id, chapter_id) ON DELETE RESTRICT NOT VALID,
  DROP CONSTRAINT IF EXISTS manuscript_blocks_scene_fk,
  ADD CONSTRAINT manuscript_blocks_scene_fk FOREIGN KEY (tenant_id, project_id, chapter_id, scene_id)
    REFERENCES scenes(tenant_id, project_id, chapter_id, scene_id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE manuscript_blocks VALIDATE CONSTRAINT manuscript_blocks_location_check;
ALTER TABLE manuscript_blocks VALIDATE CONSTRAINT manuscript_blocks_chapter_fk;
ALTER TABLE manuscript_blocks VALIDATE CONSTRAINT manuscript_blocks_scene_fk;

ALTER TABLE manuscript_block_versions
  DROP CONSTRAINT IF EXISTS manuscript_block_versions_check,
  DROP CONSTRAINT IF EXISTS manuscript_block_versions_location_check,
  ADD CONSTRAINT manuscript_block_versions_location_check CHECK (scene_id IS NULL OR chapter_id IS NOT NULL) NOT VALID,
  DROP CONSTRAINT IF EXISTS manuscript_block_versions_tenant_id_project_id_chapter_id_fkey,
  DROP CONSTRAINT IF EXISTS manuscript_block_versions_chapter_fk,
  ADD CONSTRAINT manuscript_block_versions_chapter_fk FOREIGN KEY (tenant_id, project_id, chapter_id)
    REFERENCES chapters(tenant_id, project_id, chapter_id) ON DELETE RESTRICT NOT VALID,
  DROP CONSTRAINT IF EXISTS manuscript_block_versions_tenant_id_project_id_scene_id_fkey,
  DROP CONSTRAINT IF EXISTS manuscript_block_versions_tenant_id_project_id_chapter_id__fkey,
  DROP CONSTRAINT IF EXISTS manuscript_block_versions_scene_fk,
  ADD CONSTRAINT manuscript_block_versions_scene_fk FOREIGN KEY (tenant_id, project_id, chapter_id, scene_id)
    REFERENCES scenes(tenant_id, project_id, chapter_id, scene_id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE manuscript_block_versions VALIDATE CONSTRAINT manuscript_block_versions_location_check;
ALTER TABLE manuscript_block_versions VALIDATE CONSTRAINT manuscript_block_versions_chapter_fk;
ALTER TABLE manuscript_block_versions VALIDATE CONSTRAINT manuscript_block_versions_scene_fk;

REVOKE UPDATE, DELETE ON chapter_versions, scene_versions, book_run_events FROM mirofish_app;
REVOKE DELETE ON outline_versions FROM mirofish_app;

COMMIT;
