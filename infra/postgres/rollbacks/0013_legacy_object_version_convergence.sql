BEGIN;

LOCK TABLE legacy_artifact_imports IN ACCESS EXCLUSIVE MODE;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM legacy_artifact_imports LIMIT 1) THEN
    RAISE EXCEPTION '0013 rollback requires an empty legacy_artifact_imports ledger';
  END IF;
END
$$;

ALTER TABLE legacy_artifact_imports
  DROP CONSTRAINT legacy_artifact_imports_version_ownership_check;

COMMIT;
