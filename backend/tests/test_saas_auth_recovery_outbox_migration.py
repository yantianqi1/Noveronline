from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "infra/postgres/migrations/0009_auth_recovery_outbox.sql"
ROLLBACK = ROOT / "infra/postgres/rollbacks/0009_auth_recovery_outbox.sql"


def _sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_outbox_is_encrypted_leased_and_retryable() -> None:
    sql = _sql(MIGRATION)
    table = re.search(
        r"CREATE TABLE(?: IF NOT EXISTS)? password_reset_delivery_outbox\s*\((.*?)\);",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert table
    body = table.group(1)
    for field in (
        "reset_token_id UUID NOT NULL UNIQUE",
        "token_ciphertext BYTEA NOT NULL",
        "attempt_count INTEGER NOT NULL",
        "lease_owner TEXT",
        "lease_expires_at TIMESTAMPTZ",
        "next_attempt_at TIMESTAMPTZ NOT NULL",
        "last_error_code TEXT",
    ):
        assert field in body
    assert "queued', 'processing', 'delivered', 'dead" in body
    assert not re.search(r"\btoken\s+TEXT\b", body, re.IGNORECASE)


def test_recovery_tables_are_only_accessible_through_narrow_functions() -> None:
    sql = _sql(MIGRATION)
    for table in (
        "password_reset_tokens",
        "password_reset_delivery_attempts",
        "password_reset_delivery_outbox",
        "auth_security_audit_logs",
    ):
        assert f"REVOKE ALL ON {table} FROM mirofish_app" in sql
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in sql
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in sql
    for function in (
        "auth_recovery_request",
        "auth_recovery_claim_delivery",
        "auth_recovery_finish_delivery",
        "auth_recovery_complete",
        "auth_recovery_expire",
    ):
        assert f"CREATE OR REPLACE FUNCTION {function}" in sql
        assert re.search(
            rf"CREATE OR REPLACE FUNCTION {function}.*?SECURITY DEFINER.*?SET search_path = public, pg_temp",
            sql,
            flags=re.IGNORECASE | re.DOTALL,
        )
        assert re.search(rf"GRANT EXECUTE ON FUNCTION {function}\(.*?\) TO mirofish_app", sql, re.IGNORECASE)
    assert "attempt_count INTEGER" in sql
    assert "CREATE TABLE IF NOT EXISTS password_reset_delivery_outbox" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_password_reset_delivery_outbox_claim" in sql


def test_request_and_completion_functions_keep_public_results_metadata_only() -> None:
    sql = _sql(MIGRATION)
    request = re.search(r"CREATE OR REPLACE FUNCTION auth_recovery_request.*?\$request\$;", sql, re.DOTALL)
    complete = re.search(r"CREATE OR REPLACE FUNCTION auth_recovery_complete.*?\$complete\$;", sql, re.DOTALL)
    assert request and complete
    assert "RETURNS TABLE(account_matched BOOLEAN, reset_token_id UUID)" in request.group(0)
    assert "RETURNS TEXT" in complete.group(0)
    assert "FOR UPDATE" in complete.group(0)
    assert "UPDATE user_sessions" in complete.group(0)
    assert "password_hash" in complete.group(0)


def test_scoped_source_foreign_keys_preserve_set_null_semantics() -> None:
    sql = _sql(MIGRATION)
    assert "CREATE OR REPLACE FUNCTION reject_manuscript_block_version_mutation" in sql
    assert "pg_trigger_depth() > 1" in sql
    assert "to_jsonb(NEW) - 'source_draft_id' - 'source_writer_run_id'" in sql
    for constraint, source_column in (
        ("manuscript_blocks_source_writer_run_scope_fk", "source_writer_run_id"),
        ("manuscript_blocks_source_draft_scope_fk", "source_draft_id"),
        ("manuscript_block_versions_source_writer_run_scope_fk", "source_writer_run_id"),
        ("manuscript_block_versions_source_draft_scope_fk", "source_draft_id"),
    ):
        assert f"DROP CONSTRAINT IF EXISTS {constraint}" in sql
        block = re.search(
            rf"ADD CONSTRAINT {constraint}.*?ON DELETE SET NULL \({source_column}\)",
            sql,
            re.DOTALL,
        )
        assert block
        assert f"ON DELETE SET NULL ({source_column})" in block.group(0)


def test_rollback_restores_pre_0009_permissions_and_constraints() -> None:
    sql = _sql(ROLLBACK)
    assert "DROP TABLE IF EXISTS password_reset_delivery_outbox" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON password_reset_tokens TO mirofish_app" in sql
    assert "ON DELETE RESTRICT" in sql
    assert "CREATE OR REPLACE FUNCTION reject_manuscript_block_version_mutation" in sql
    for function in (
        "auth_recovery_request",
        "auth_recovery_claim_delivery",
        "auth_recovery_finish_delivery",
        "auth_recovery_complete",
        "auth_recovery_expire",
    ):
        assert f"DROP FUNCTION IF EXISTS {function}" in sql
