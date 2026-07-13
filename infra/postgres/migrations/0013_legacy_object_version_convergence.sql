BEGIN;

LOCK TABLE legacy_artifact_imports IN ACCESS EXCLUSIVE MODE;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM legacy_artifact_imports
    WHERE created_by_import
      AND created_version_id IS NULL
      AND status NOT IN ('pending', 'orphaned', 'deleted')
  ) THEN
    RAISE EXCEPTION '0013 requires reconciliation of active legacy object rows without version ownership';
  END IF;
END
$$;

ALTER TABLE legacy_artifact_imports
  ADD CONSTRAINT legacy_artifact_imports_version_ownership_check
  CHECK (
    NOT created_by_import
    OR created_version_id IS NOT NULL
    OR status IN ('pending', 'orphaned', 'deleted')
  );

COMMIT;
