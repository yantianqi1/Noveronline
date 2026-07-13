BEGIN;

ALTER TABLE legacy_artifact_imports
  ADD COLUMN created_version_id TEXT;

ALTER TABLE legacy_artifact_imports
  ADD CONSTRAINT legacy_artifact_imports_created_version_id_check
  CHECK (created_version_id IS NULL OR created_version_id <> '');

COMMIT;
