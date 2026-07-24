-- Semantic recall over prior manuscript prose (doc 41 §4.3).
-- Mirrors asset_embeddings so the writer can run pgvector similarity over
-- non-adjacent manuscript blocks (foreshadowing, callbacks) instead of only the
-- immediate scene window. Populated by the asset_reindex workflow.

CREATE TABLE IF NOT EXISTS manuscript_block_embeddings (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  embedding_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  block_id UUID NOT NULL REFERENCES manuscript_blocks(block_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  embedding_model TEXT NOT NULL CHECK (btrim(embedding_model) <> ''),
  dimensions INTEGER NOT NULL CHECK (dimensions > 0),
  embedding VECTOR NOT NULL,
  content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  reindex_batch_id TEXT NOT NULL CHECK (btrim(reindex_batch_id) <> ''),
  source_updated_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, block_id, embedding_model),
  FOREIGN KEY (tenant_id, project_id, block_id)
    REFERENCES manuscript_blocks(tenant_id, project_id, block_id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id)
    REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE,
  CHECK (vector_dims(embedding) = dimensions)
);

CREATE INDEX IF NOT EXISTS idx_manuscript_block_embeddings_tenant_project_model
  ON manuscript_block_embeddings (tenant_id, project_id, embedding_model, dimensions, block_id);

CREATE INDEX IF NOT EXISTS idx_manuscript_block_embeddings_reindex_batch
  ON manuscript_block_embeddings (tenant_id, project_id, reindex_batch_id);

ALTER TABLE manuscript_block_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE manuscript_block_embeddings FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_manuscript_block_embeddings ON manuscript_block_embeddings;
CREATE POLICY tenant_isolation_manuscript_block_embeddings
ON manuscript_block_embeddings
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

GRANT SELECT, INSERT, UPDATE, DELETE ON manuscript_block_embeddings TO mirofish_app;
