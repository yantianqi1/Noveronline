CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE global_search_index
  ADD COLUMN IF NOT EXISTS search_vector TSVECTOR GENERATED ALWAYS AS (
    setweight(to_tsvector('simple'::regconfig, COALESCE(title, '')), 'A') ||
    setweight(to_tsvector('simple'::regconfig, COALESCE(body, '')), 'B') ||
    setweight(to_tsvector('simple'::regconfig, COALESCE(tags_jsonb::text, '')), 'C') ||
    setweight(to_tsvector('simple'::regconfig, COALESCE(payload_jsonb::text, '')), 'D')
  ) STORED;

CREATE INDEX IF NOT EXISTS idx_global_search_index_search_vector
  ON global_search_index USING GIN (search_vector);

-- Existing deployments may predate the composite asset identity constraint now
-- declared by the baseline. The index also gives the embedding FK a stable key.
CREATE UNIQUE INDEX IF NOT EXISTS idx_assets_tenant_project_asset_identity
  ON assets (tenant_id, project_id, asset_id);

CREATE TABLE IF NOT EXISTS asset_embeddings (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  embedding_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id UUID NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  embedding_model TEXT NOT NULL CHECK (btrim(embedding_model) <> ''),
  dimensions INTEGER NOT NULL CHECK (dimensions > 0),
  embedding VECTOR NOT NULL,
  content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  reindex_batch_id TEXT NOT NULL CHECK (btrim(reindex_batch_id) <> ''),
  source_updated_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, asset_id, embedding_model),
  FOREIGN KEY (tenant_id, project_id, asset_id)
    REFERENCES assets(tenant_id, project_id, asset_id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id)
    REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE,
  CHECK (vector_dims(embedding) = dimensions)
);

CREATE INDEX IF NOT EXISTS idx_asset_embeddings_tenant_project_model
  ON asset_embeddings (tenant_id, project_id, embedding_model, dimensions, asset_id);

CREATE INDEX IF NOT EXISTS idx_asset_embeddings_reindex_batch
  ON asset_embeddings (tenant_id, project_id, reindex_batch_id);

ALTER TABLE asset_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE asset_embeddings FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_asset_embeddings ON asset_embeddings;
CREATE POLICY tenant_isolation_asset_embeddings
ON asset_embeddings
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

GRANT SELECT, INSERT, UPDATE, DELETE ON asset_embeddings TO mirofish_app;
