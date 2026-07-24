-- Spoiler gate for writer recall (doc 41 §4.5).
-- reveal_after_chapter_order gates an asset out of writer recall until the
-- author is writing at or past that chapter. NULL (the default) means always
-- visible — existing assets are unaffected. The writer composer's search_assets
-- enforces this as a third filter alongside enabled + lifecycle, so an
-- unrevealed killer's motive or a not-yet-introduced character never leaks into
-- the writing context.

ALTER TABLE assets
  ADD COLUMN IF NOT EXISTS reveal_after_chapter_order INTEGER CHECK (
    reveal_after_chapter_order IS NULL OR reveal_after_chapter_order >= 0
  );

-- Partial index for the gated recall path (only the small gated subset is indexed).
CREATE INDEX IF NOT EXISTS idx_assets_reveal_gate
  ON assets (tenant_id, project_id, reveal_after_chapter_order)
  WHERE reveal_after_chapter_order IS NOT NULL;
