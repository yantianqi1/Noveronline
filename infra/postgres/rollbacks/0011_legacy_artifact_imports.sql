BEGIN;

LOCK TABLE legacy_artifact_imports IN ACCESS EXCLUSIVE MODE;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM legacy_artifact_imports LIMIT 1) THEN
    RAISE EXCEPTION '0011 rollback requires an empty legacy_artifact_imports ledger';
  END IF;
END
$$;

REVOKE ALL ON legacy_artifact_imports FROM mirofish_app;
DROP TABLE IF EXISTS legacy_artifact_imports;

COMMIT;
