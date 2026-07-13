from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "infra" / "postgres" / "migrations" / "0011_legacy_artifact_imports.sql"
ROLLBACK = ROOT / "infra" / "postgres" / "rollbacks" / "0011_legacy_artifact_imports.sql"
VERSION_MIGRATION = (
    ROOT
    / "infra"
    / "postgres"
    / "migrations"
    / "0012_legacy_object_version_ownership.sql"
)
VERSION_ROLLBACK = (
    ROOT
    / "infra"
    / "postgres"
    / "rollbacks"
    / "0012_legacy_object_version_ownership.sql"
)
CONVERGENCE_MIGRATION = (
    ROOT
    / "infra"
    / "postgres"
    / "migrations"
    / "0013_legacy_object_version_convergence.sql"
)
CONVERGENCE_ROLLBACK = (
    ROOT
    / "infra"
    / "postgres"
    / "rollbacks"
    / "0013_legacy_object_version_convergence.sql"
)


def _sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_legacy_object_manifest_stores_hashes_and_private_lifecycle_state() -> None:
    sql = _sql(MIGRATION)
    table = re.search(
        r"CREATE TABLE legacy_artifact_imports\s*\((.*?)\);",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert table
    body = table.group(1)
    for required in (
        "source_table TEXT NOT NULL",
        "artifact_kind TEXT NOT NULL",
        "source_key_hash TEXT NOT NULL",
        "project_name TEXT",
        "source_mtime TIMESTAMPTZ",
        "legacy_synced_at TIMESTAMPTZ",
        "source_basename TEXT",
        "path_hash TEXT",
        "object_key TEXT",
        "sha256 TEXT",
        "size_bytes BIGINT",
        "media_type TEXT",
        "created_by_import BOOLEAN NOT NULL",
        "last_error_code TEXT",
    ):
        assert required in body
    assert "pending" in body
    assert "verified" in body
    assert "metadata_only" in body
    assert "delete_pending" in body
    assert "orphaned" in body
    assert "deleted" in body
    assert "file_path" not in body
    assert "payload" not in body
    assert "source_text" not in body
    assert "^projects/[0-9a-f-]{36}/legacy-imports/" in body


def test_legacy_object_manifest_has_forced_rls_and_no_public_grant() -> None:
    sql = _sql(MIGRATION)
    assert "ALTER TABLE legacy_artifact_imports ENABLE ROW LEVEL SECURITY" in sql
    assert "ALTER TABLE legacy_artifact_imports FORCE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY tenant_isolation_legacy_artifact_imports" in sql
    assert "current_setting('app.current_tenant_id', true)" in sql
    assert "REVOKE ALL ON legacy_artifact_imports FROM PUBLIC" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON legacy_artifact_imports TO mirofish_app" in sql


def test_legacy_object_manifest_has_scope_and_idempotency_constraints() -> None:
    sql = _sql(MIGRATION)
    assert "PRIMARY KEY (tenant_id, object_id)" in sql
    assert "UNIQUE (tenant_id, import_id, object_id)" in sql
    assert "UNIQUE (tenant_id, import_id, source_table, source_key_hash)" in sql
    assert "UNIQUE (tenant_id, object_key)" in sql
    assert "object_kind = 'project_artifact' AND source_table = 'project_artifacts'" in sql
    assert "object_kind = 'archive_source' AND source_table = 'archive_sources'" in sql
    assert "FOREIGN KEY (tenant_id, project_id)" in sql
    assert "REFERENCES projects(tenant_id, project_id)" in sql


def test_0011_rollback_only_removes_legacy_object_manifest() -> None:
    sql = _sql(ROLLBACK)
    assert "LOCK TABLE legacy_artifact_imports IN ACCESS EXCLUSIVE MODE" in sql
    assert "IF EXISTS (SELECT 1 FROM legacy_artifact_imports LIMIT 1)" in sql
    assert "rollback requires an empty legacy_artifact_imports ledger" in sql
    assert "REVOKE ALL ON legacy_artifact_imports FROM mirofish_app" in sql
    assert "DROP TABLE IF EXISTS legacy_artifact_imports" in sql
    assert sql.count("DROP TABLE") == 1
    for forbidden in ("projects", "source_files", "project_text_artifacts", "audit_logs"):
        assert f"DROP TABLE IF EXISTS {forbidden}" not in sql


def test_0012_tracks_exact_created_object_version_and_rolls_back_guarded() -> None:
    migration = _sql(VERSION_MIGRATION)
    rollback = _sql(VERSION_ROLLBACK)

    assert "ADD COLUMN created_version_id TEXT" in migration
    assert "legacy_artifact_imports_created_version_id_check" in migration
    assert "LOCK TABLE legacy_artifact_imports IN ACCESS EXCLUSIVE MODE" in rollback
    assert "0012 rollback requires an empty legacy_artifact_imports ledger" in rollback
    assert "DROP COLUMN created_version_id" in rollback


def test_0013_fails_closed_for_unowned_active_versions_and_adds_constraint() -> None:
    migration = _sql(CONVERGENCE_MIGRATION)
    rollback = _sql(CONVERGENCE_ROLLBACK)

    assert "LOCK TABLE legacy_artifact_imports IN ACCESS EXCLUSIVE MODE" in migration
    assert "created_by_import" in migration
    assert "created_version_id IS NULL" in migration
    assert "status NOT IN ('pending', 'orphaned', 'deleted')" in migration
    assert "legacy_artifact_imports_version_ownership_check" in migration
    assert "0013 rollback requires an empty legacy_artifact_imports ledger" in rollback
