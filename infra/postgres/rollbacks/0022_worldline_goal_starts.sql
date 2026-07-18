BEGIN;

LOCK TABLE worldline_goal_starts IN ACCESS EXCLUSIVE MODE;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM worldline_goal_starts LIMIT 1) THEN
    RAISE EXCEPTION '0022 rollback requires an empty worldline_goal_starts table';
  END IF;
END $$;

REVOKE ALL ON worldline_goal_starts FROM mirofish_app;
DROP TABLE IF EXISTS worldline_goal_starts;

COMMIT;
