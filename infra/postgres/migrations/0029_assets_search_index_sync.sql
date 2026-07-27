-- Index-on-write for the asset recall substrate (writer recall audit P0-1).
--
-- Before this migration only the Python seed pipeline wrote global_search_index,
-- so every asset produced by the Go control plane (pi_analysis imports,
-- manuscript distillation adoptions, catalog edits, character console
-- proposals) was structurally unreachable by search_assets — the recall SQL
-- inner-joins from this index. The trigger keeps the index in the SAME
-- transaction as the asset write for every producer, present and future, and
-- the backfill below indexes the assets written before it existed.
--
-- Row shape mirrors the asset_reindex projection in
-- apps/agent-runtime/mirofish_agents/temporal/assets.py so reindex runs stay
-- idempotent over trigger-written rows.

CREATE OR REPLACE FUNCTION assets_search_index_sync() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  -- Only project-scoped assets are searchable; a NULL project_id cannot hit
  -- the (tenant_id, project_id, source, source_ref) unique key.
  IF NEW.scope IS DISTINCT FROM 'project' OR NEW.project_id IS NULL THEN
    RETURN NEW;
  END IF;
  INSERT INTO global_search_index (
    tenant_id, source, source_ref, project_id, entity_type, title, body, tags_jsonb, payload_jsonb
  )
  VALUES (
    NEW.tenant_id,
    'asset',
    NEW.asset_id::text,
    NEW.project_id,
    NEW.asset_type,
    NEW.title,
    btrim(COALESCE(NEW.summary, '') || E'\n' || COALESCE(NEW.content_text, '')),
    CASE WHEN jsonb_typeof(NEW.tags_jsonb) = 'array' THEN NEW.tags_jsonb ELSE '[]'::jsonb END,
    (
      CASE
        WHEN jsonb_typeof(NEW.payload_jsonb) = 'object' THEN NEW.payload_jsonb
        ELSE '{}'::jsonb
      END
    ) || jsonb_strip_nulls(jsonb_build_object(
           'asset_type', NEW.asset_type,
           'asset_id', NEW.asset_id,
           'summary', NEW.summary
         ))
  )
  ON CONFLICT (tenant_id, project_id, source, source_ref)
  DO UPDATE SET
    entity_type = EXCLUDED.entity_type,
    title = EXCLUDED.title,
    body = EXCLUDED.body,
    tags_jsonb = EXCLUDED.tags_jsonb,
    payload_jsonb = EXCLUDED.payload_jsonb,
    updated_at = now();
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION assets_search_index_cleanup() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF OLD.project_id IS NULL THEN
    RETURN OLD;
  END IF;
  DELETE FROM global_search_index
   WHERE tenant_id = OLD.tenant_id
     AND project_id = OLD.project_id
     AND source = 'asset'
     AND source_ref = OLD.asset_id::text;
  RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trg_assets_search_index_sync ON assets;
CREATE TRIGGER trg_assets_search_index_sync
AFTER INSERT OR UPDATE ON assets
FOR EACH ROW
EXECUTE FUNCTION assets_search_index_sync();

DROP TRIGGER IF EXISTS trg_assets_search_index_cleanup ON assets;
CREATE TRIGGER trg_assets_search_index_cleanup
AFTER DELETE ON assets
FOR EACH ROW
EXECUTE FUNCTION assets_search_index_cleanup();

-- Backfill the assets written before index-on-write existed (runs as the
-- migration admin, so RLS does not filter the sweep).
INSERT INTO global_search_index (
  tenant_id, source, source_ref, project_id, entity_type, title, body, tags_jsonb, payload_jsonb
)
SELECT
  asset.tenant_id,
  'asset',
  asset.asset_id::text,
  asset.project_id,
  asset.asset_type,
  asset.title,
  btrim(COALESCE(asset.summary, '') || E'\n' || COALESCE(asset.content_text, '')),
  CASE WHEN jsonb_typeof(asset.tags_jsonb) = 'array' THEN asset.tags_jsonb ELSE '[]'::jsonb END,
  (
    CASE
      WHEN jsonb_typeof(asset.payload_jsonb) = 'object' THEN asset.payload_jsonb
      ELSE '{}'::jsonb
    END
  ) || jsonb_strip_nulls(jsonb_build_object(
         'asset_type', asset.asset_type,
         'asset_id', asset.asset_id,
         'summary', asset.summary
       ))
FROM assets asset
WHERE asset.scope = 'project'
  AND asset.project_id IS NOT NULL
ON CONFLICT (tenant_id, project_id, source, source_ref)
DO UPDATE SET
  entity_type = EXCLUDED.entity_type,
  title = EXCLUDED.title,
  body = EXCLUDED.body,
  tags_jsonb = EXCLUDED.tags_jsonb,
  payload_jsonb = EXCLUDED.payload_jsonb,
  updated_at = now();
