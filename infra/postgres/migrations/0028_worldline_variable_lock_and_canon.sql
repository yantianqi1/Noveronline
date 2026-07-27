BEGIN;

-- 0028: Worldline loop closure — the director reads locked variables each step
-- (docs/refactor-saas/42-worldline-loop-closure-plan.md, 闭环 1). Partial index
-- keeps the locked-variables prompt query off the full session scan. Additive
-- only: no new columns, no data rewrite.

CREATE INDEX IF NOT EXISTS idx_worldline_variables_session_locked
  ON worldline_variables (tenant_id, project_id, session_id)
  WHERE locked = true;

COMMIT;
