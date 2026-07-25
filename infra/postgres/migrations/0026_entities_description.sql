-- Entity long-form description for richer asset bodies.
-- Sequential reading previously captured only a one-line state_summary per
-- entity, so the asset library "正文" (content_text) had nothing detailed to
-- show. The reading module now also emits a multi-sentence Chinese
-- `description` (identity, temperament, motive, relation to the main plot);
-- it is stored here and projected into assets.content_text by the seed asset
-- indexer. Nullable so existing rows and partial extractions stay valid.

ALTER TABLE entities
  ADD COLUMN IF NOT EXISTS description TEXT;
