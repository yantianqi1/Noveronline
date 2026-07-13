from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "infra" / "postgres" / "migrations" / "0007_platform_hardening.sql"
ROLLBACK = ROOT / "infra" / "postgres" / "rollbacks" / "0007_platform_hardening.sql"


def _sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_distributed_auth_abuse_buckets_store_only_hashed_scope() -> None:
    sql = _sql(MIGRATION)
    table = re.search(
        r"CREATE TABLE auth_abuse_rate_limits\s*\((.*?)\);",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert table
    body = table.group(1)
    assert "scope_key_hash TEXT PRIMARY KEY" in body
    assert "action TEXT NOT NULL" in body
    assert "window_started_at TIMESTAMPTZ NOT NULL" in body
    assert "request_count BIGINT NOT NULL" in body
    assert "blocked_until TIMESTAMPTZ" in body
    assert "updated_at TIMESTAMPTZ NOT NULL" in body
    assert "scope_key_hash ~ '^[0-9a-f]{64}$'" in body
    for forbidden in ("email", "ip_address", "raw_token"):
        assert forbidden not in body.lower()


def test_abuse_buckets_are_available_to_app_role_without_public_access() -> None:
    sql = _sql(MIGRATION)
    assert "REVOKE ALL ON auth_abuse_rate_limits FROM PUBLIC" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON auth_abuse_rate_limits TO mirofish_app" in sql


def test_provider_health_requires_an_enabled_model() -> None:
    sql = _sql(MIGRATION)
    assert "ALTER TABLE llm_models" in sql
    assert "ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT TRUE" in sql
    assert "idx_llm_models_enabled_scope" in sql


def test_upgrade_preflights_and_validates_manuscript_source_ownership() -> None:
    sql = _sql(MIGRATION)
    assert "platform hardening preflight failed: manuscript source ownership mismatch" in sql
    assert "writer_runs_scope_key" in sql
    assert "writer_drafts_scope_key" in sql
    for constraint in (
        "manuscript_blocks_source_writer_run_scope_fk",
        "manuscript_blocks_source_draft_scope_fk",
        "manuscript_block_versions_source_writer_run_scope_fk",
        "manuscript_block_versions_source_draft_scope_fk",
    ):
        assert f"ADD CONSTRAINT {constraint}" in sql
        assert f"VALIDATE CONSTRAINT {constraint}" in sql


def test_collaboration_delivery_tenant_must_match_invitation() -> None:
    sql = _sql(MIGRATION)
    assert "collaboration_invitations_tenant_invitation_key" in sql
    assert "collaboration_delivery_attempts_invitation_scope_fk" in sql
    assert "FOREIGN KEY (tenant_id, invitation_id)" in sql
    assert "REFERENCES collaboration_invitations(tenant_id, invitation_id)" in sql


def test_rollback_only_removes_0007_objects_and_constraints() -> None:
    sql = _sql(ROLLBACK)
    assert "DROP TABLE IF EXISTS auth_abuse_rate_limits" in sql
    assert "DROP COLUMN IF EXISTS enabled" in sql
    for constraint in (
        "manuscript_blocks_source_writer_run_scope_fk",
        "manuscript_blocks_source_draft_scope_fk",
        "manuscript_block_versions_source_writer_run_scope_fk",
        "manuscript_block_versions_source_draft_scope_fk",
        "collaboration_delivery_attempts_invitation_scope_fk",
    ):
        assert f"DROP CONSTRAINT IF EXISTS {constraint}" in sql
    assert "DROP TABLE" not in sql.replace("DROP TABLE IF EXISTS auth_abuse_rate_limits", "")
    assert "0006_auth_collaboration" not in sql
    assert "0005_manuscript_workspace" not in sql
