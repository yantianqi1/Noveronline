from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "infra" / "postgres" / "migrations" / "0018_manuscript_asset_distillation.sql"
ROLLBACK = ROOT / "infra" / "postgres" / "rollbacks" / "0018_manuscript_asset_distillation.sql"
BOOTSTRAP = ROOT / "infra" / "scripts" / "bootstrap-compose-database.sh"
READINESS = ROOT / "apps" / "api" / "cmd" / "api" / "readiness.go"


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


def test_migration_is_transactional_and_additive() -> None:
    sql = _sql()
    normalized = re.sub(r"\s+", " ", sql.lower())
    assert normalized.startswith("begin;") and normalized.strip().endswith("commit;")
    assert "drop table" not in normalized
    assert "0018_manuscript_asset_distillation" in MIGRATION.name


def test_four_target_tables_exist_with_required_columns() -> None:
    sql = _sql()
    settings = _table(sql, "project_asset_distillation_settings")
    assert "trigger_mode TEXT NOT NULL DEFAULT 'manual'" in settings
    assert "'off'" in settings and "'after_adoption'" in settings and "'chapter_complete'" in settings
    assert "enabled_asset_types TEXT[]" in settings

    requests = _table(sql, "manuscript_asset_distillation_requests")
    assert "source_manifest_jsonb JSONB NOT NULL" in requests
    assert "input_fingerprint TEXT NOT NULL" in requests
    assert "dispatch_status TEXT NOT NULL DEFAULT 'pending'" in requests
    assert "UNIQUE (tenant_id, project_id, run_id)" in requests
    assert "UNIQUE (tenant_id, project_id, input_fingerprint, extractor_contract_version)" in requests
    assert "NOT (source_manifest_jsonb ? 'content_text')" in requests

    proposals = _table(sql, "asset_candidate_proposals")
    assert "candidate_asset_id UUID PRIMARY KEY" in proposals
    assert "'create'" in proposals and "'update'" in proposals
    assert "'staging'" in proposals and "'pending'" in proposals and "'stale'" in proposals
    assert "normalized_identity TEXT NOT NULL" in proposals

    evidence = _table(sql, "asset_candidate_evidence")
    assert "evidence_text TEXT NOT NULL" in evidence
    assert "content_sha256 TEXT NOT NULL" in evidence
    assert "start_offset INTEGER NOT NULL" in evidence
    assert "end_offset INTEGER NOT NULL" in evidence


def test_adopt_snapshot_reason_and_pending_identity_uniqueness() -> None:
    sql = _sql()
    assert "snapshot_reason IN ('adopt', 'update', 'delete', 'move', 'tag', 'restore')" in sql
    assert "asset_candidate_proposals_pending_identity_key" in sql
    assert "WHERE review_status = 'pending'" in sql


def test_existing_projects_default_manual_not_auto() -> None:
    sql = _sql()
    assert "'manual'" in sql
    assert "ON CONFLICT (tenant_id, project_id) DO NOTHING" in sql
    # Backfill for existing projects must not silently opt them into after_adoption.
    backfill = sql[sql.index("INSERT INTO project_asset_distillation_settings") :]
    assert "'manual'" in backfill
    assert "'after_adoption'" not in backfill.split("CREATE TABLE")[0]


def test_force_rls_and_evidence_without_delete_grant() -> None:
    sql = _sql()
    for table in (
        "project_asset_distillation_settings",
        "manuscript_asset_distillation_requests",
        "asset_candidate_proposals",
        "asset_candidate_evidence",
    ):
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in sql
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in sql
        assert f"tenant_isolation_{table}" in sql
        assert "app.current_tenant_id" in sql
    assert "GRANT SELECT, INSERT ON asset_candidate_evidence TO mirofish_app" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON asset_candidate_evidence" not in sql
    assert "GRANT DELETE ON asset_candidate_evidence" not in sql
    assert "claim_manuscript_asset_distillation_outbox" in sql
    assert "SECURITY DEFINER" in sql


def test_rollback_and_bootstrap_sentinel_are_wired() -> None:
    rollback = ROLLBACK.read_text(encoding="utf-8")
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    readiness = READINESS.read_text(encoding="utf-8")
    assert "DROP TABLE IF EXISTS asset_candidate_evidence" in rollback
    assert "0018_manuscript_asset_distillation" in rollback
    assert "0018_*)" in bootstrap
    assert "project_asset_distillation_settings" in bootstrap
    assert 'latestRequiredMigration = "0032_email_verification"' in readiness
    assert "requiredMigrationCount  = 32" in readiness or "requiredMigrationCount = 32" in readiness
