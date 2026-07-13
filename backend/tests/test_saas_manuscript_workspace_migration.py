from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "infra" / "postgres" / "migrations" / "0005_manuscript_workspace.sql"
HARDENING = ROOT / "infra" / "postgres" / "migrations" / "0008_writer_manuscript_hardening.sql"


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _table(sql: str, name: str) -> str:
    match = re.search(
        rf"CREATE TABLE IF NOT EXISTS {name}\s*\((.*?)\);",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, f"{name} table is missing"
    return match.group(1)


def test_manuscript_blocks_gain_workspace_fields_and_frozen_foreign_keys() -> None:
    sql = _sql()
    for field in ("scene_id UUID", "status TEXT", "tags TEXT[]", "version INTEGER", "updated_by UUID", "source_writer_run_id UUID"):
        assert field in sql
    assert "REFERENCES chapters(tenant_id, project_id, chapter_id)" in sql
    assert "REFERENCES scenes(tenant_id, project_id, scene_id)" in sql
    assert "idx_manuscript_blocks_active_order" in sql
    assert "WHERE status = 'active'" in sql


def test_clean_migration_reconciles_legacy_locations_before_validating_foreign_keys() -> None:
    sql = _sql()
    normalized = re.sub(r"\s+", " ", sql.lower())
    reconcile_at = normalized.index("manuscript block fk reconcile")
    add_fk_at = normalized.index("add constraint manuscript_blocks_chapter_fk")
    validate_at = normalized.index("validate constraint manuscript_blocks_chapter_fk")
    assert reconcile_at < add_fk_at < validate_at
    assert "not valid" in normalized[add_fk_at:validate_at]
    assert "scene_id is null or chapter_id is not null" in normalized
    assert "references scenes(tenant_id, project_id, chapter_id, scene_id)" in normalized
    assert "raise exception 'manuscript block fk reconcile failed" in normalized


def test_upgrade_hardening_is_transactional_repeatable_and_explainable() -> None:
    sql = HARDENING.read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", sql.lower())
    assert normalized.startswith("begin;") and normalized.strip().endswith("commit;")
    assert "drop constraint if exists chapters_project_order_key" in normalized
    assert "create unique index if not exists chapters_project_active_order_key" in normalized
    assert "create unique index if not exists scenes_chapter_active_order_key" in normalized
    assert "manuscript block fk reconcile" in normalized
    assert "drop constraint if exists manuscript_blocks_scene_fk" in normalized
    assert "not valid" in normalized
    assert "validate constraint manuscript_blocks_scene_fk" in normalized
    assert "revoke update, delete on chapter_versions, scene_versions, book_run_events from mirofish_app" in normalized
    assert "revoke delete on outline_versions from mirofish_app" in normalized


def test_block_versions_are_scoped_immutable_snapshots() -> None:
    sql = _sql()
    table = _table(sql, "manuscript_block_versions")
    for field in ("content_text", "tags", "version_number", "snapshot_reason", "restored_from_version_id", "created_by"):
        assert field in table
    assert "UNIQUE (tenant_id, project_id, block_id, version_number)" in table
    assert "BEFORE UPDATE OR DELETE ON manuscript_block_versions" in sql
    assert "manuscript block versions are immutable" in sql
    assert "pg_trigger_depth() > 1" in sql


def test_completed_export_requires_real_artifact_state() -> None:
    table = _table(_sql(), "manuscript_exports")
    for field in ("artifact_sha256", "artifact_size_bytes", "artifact_object_ref", "block_count", "completed_at"):
        assert field in table
    assert "status <> 'completed'" in table
    assert "artifact_sha256 ~ '^[0-9a-f]{64}$'" in table
    assert "artifact_size_bytes > 0" in table
    assert "block_count > 0" in table


def test_commands_and_dedup_enforce_candidate_only_boundaries() -> None:
    sql = _sql()
    commands = _table(sql, "writer_command_runs")
    for command in ("complete_outline", "align_words", "scan_lexicon", "fill_relationships", "continue_chapter"):
        assert command in commands
    assert "UNIQUE (tenant_id, project_id, request_id)" in commands
    assert "input_fingerprint" in commands
    patterns = _table(sql, "writer_dedup_patterns")
    assert "lifecycle TEXT NOT NULL DEFAULT 'candidate'" in patterns
    assert "enabled BOOLEAN NOT NULL DEFAULT FALSE" in patterns
    assert "lifecycle = 'accepted' AND enabled = TRUE" in patterns


def test_all_new_tables_force_rls_and_grant_app_role() -> None:
    sql = _sql()
    for table in ("manuscript_block_versions", "manuscript_exports", "writer_command_runs", "writer_dedup_patterns"):
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in sql
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in sql
        assert f"tenant_isolation_{table}" in sql
        assert f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO mirofish_app" in sql
    assert "current_setting('app.current_tenant_id', true)" in sql
