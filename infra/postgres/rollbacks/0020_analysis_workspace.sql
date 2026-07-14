BEGIN;

LOCK TABLE analysis_candidates IN ACCESS EXCLUSIVE MODE;
LOCK TABLE analysis_workspace_files IN ACCESS EXCLUSIVE MODE;
LOCK TABLE analysis_runs IN ACCESS EXCLUSIVE MODE;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM analysis_candidates LIMIT 1) THEN
    RAISE EXCEPTION '0020 rollback requires an empty analysis_candidates table';
  END IF;
  IF EXISTS (SELECT 1 FROM analysis_workspace_files LIMIT 1) THEN
    RAISE EXCEPTION '0020 rollback requires an empty analysis_workspace_files table';
  END IF;
  IF EXISTS (SELECT 1 FROM analysis_runs LIMIT 1) THEN
    RAISE EXCEPTION '0020 rollback requires an empty analysis_runs table';
  END IF;
END $$;

REVOKE ALL ON analysis_candidates FROM mirofish_app;
REVOKE ALL ON analysis_workspace_files FROM mirofish_app;
REVOKE ALL ON analysis_runs FROM mirofish_app;

DROP TABLE IF EXISTS analysis_candidates;
DROP TABLE IF EXISTS analysis_workspace_files;
DROP TABLE IF EXISTS analysis_runs;

COMMIT;
