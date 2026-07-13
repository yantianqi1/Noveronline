BEGIN;

LOCK TABLE legacy_artifact_imports IN ACCESS EXCLUSIVE MODE;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM legacy_artifact_imports LIMIT 1) THEN
    RAISE EXCEPTION '0012 rollback requires an empty legacy_artifact_imports ledger';
  END IF;
END
$$;

ALTER TABLE legacy_artifact_imports
  DROP CONSTRAINT legacy_artifact_imports_created_version_id_check,
  DROP COLUMN created_version_id;

COMMIT;
