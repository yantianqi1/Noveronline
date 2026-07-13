BEGIN;

CREATE TABLE legacy_artifact_imports (
  tenant_id UUID NOT NULL,
  object_id UUID NOT NULL,
  import_id UUID NOT NULL,
  project_id UUID NOT NULL,
  object_kind TEXT NOT NULL CHECK (object_kind IN ('project_artifact', 'archive_source')),
  source_table TEXT NOT NULL CHECK (source_table IN ('project_artifacts', 'archive_sources')),
  artifact_kind TEXT NOT NULL CHECK (artifact_kind <> ''),
  source_key_hash TEXT NOT NULL CHECK (source_key_hash ~ '^[0-9a-f]{64}$'),
  project_name TEXT,
  source_mtime TIMESTAMPTZ,
  legacy_synced_at TIMESTAMPTZ,
  source_basename TEXT,
  path_hash TEXT CHECK (path_hash IS NULL OR path_hash ~ '^[0-9a-f]{64}$'),
  object_key TEXT CHECK (
    object_key IS NULL OR object_key ~ '^projects/[0-9a-f-]{36}/legacy-imports/[0-9a-f-]{36}/(project_artifact|archive_source)/[0-9a-f]{64}/[0-9a-f]{64}$'
  ),
  sha256 TEXT CHECK (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'),
  size_bytes BIGINT CHECK (size_bytes IS NULL OR size_bytes >= 0),
  media_type TEXT CHECK (media_type IS NULL OR media_type <> ''),
  status TEXT NOT NULL CHECK (
    status IN ('pending', 'verified', 'metadata_only', 'delete_pending', 'orphaned', 'deleted')
  ),
  created_by_import BOOLEAN NOT NULL,
  last_error_code TEXT,
  verified_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, object_id),
  UNIQUE (tenant_id, import_id, object_id),
  UNIQUE (tenant_id, import_id, source_table, source_key_hash),
  UNIQUE (tenant_id, object_key),
  CHECK (
    (object_kind = 'project_artifact' AND source_table = 'project_artifacts')
    OR (object_kind = 'archive_source' AND source_table = 'archive_sources')
  ),
  CHECK (
    (status = 'metadata_only' AND object_key IS NULL AND sha256 IS NULL
      AND size_bytes IS NULL AND media_type IS NULL AND NOT created_by_import)
    OR status <> 'metadata_only'
  ),
  CHECK (
    (object_key IS NULL AND sha256 IS NULL AND size_bytes IS NULL AND media_type IS NULL
      AND status IN ('metadata_only', 'deleted'))
    OR (object_key IS NOT NULL AND sha256 IS NOT NULL AND size_bytes IS NOT NULL AND media_type IS NOT NULL)
  ),
  FOREIGN KEY (tenant_id, project_id)
    REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE INDEX idx_legacy_artifact_imports_import_status
  ON legacy_artifact_imports (tenant_id, import_id, status);

ALTER TABLE legacy_artifact_imports ENABLE ROW LEVEL SECURITY;
ALTER TABLE legacy_artifact_imports FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_legacy_artifact_imports
  ON legacy_artifact_imports
  USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

REVOKE ALL ON legacy_artifact_imports FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON legacy_artifact_imports TO mirofish_app;

COMMIT;
