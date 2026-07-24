-- always_on channel for writer recall (doc 41 §4.2).
-- Core world laws and style/ban constraints must be present on EVERY writing
-- run, whether or not the retrieval context happens to name them. always_on
-- marks an asset for that unconditional, constant injection: the writer
-- composer force-injects every enabled, lifecycle-safe, spoiler-gated
-- always_on asset into the writing brief, bypassing keyword/vector relevance
-- entirely. FALSE (the default) keeps existing assets on the relevance path.

ALTER TABLE assets
  ADD COLUMN IF NOT EXISTS always_on BOOLEAN NOT NULL DEFAULT FALSE;

-- Partial index for the constant-recall path (only the small always_on subset).
CREATE INDEX IF NOT EXISTS idx_assets_always_on
  ON assets (tenant_id, project_id)
  WHERE always_on;
