from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "infra" / "postgres" / "migrations" / "0006_auth_collaboration.sql"


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _table(sql: str, name: str) -> str:
    match = re.search(
        rf"CREATE TABLE IF NOT EXISTS {name}\s*\((.*?)\);",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, f"{name} is missing"
    return match.group(1)


def test_invitation_and_reset_tokens_are_hash_only_and_single_use() -> None:
    sql = _sql()
    invitations = _table(sql, "collaboration_invitations")
    resets = _table(sql, "password_reset_tokens")

    for block in (invitations, resets):
        assert re.search(r"\btoken_hash\s+TEXT\s+NOT NULL\s+UNIQUE", block, re.IGNORECASE)
        assert "expires_at TIMESTAMPTZ NOT NULL" in block
        assert not re.search(r"\b(raw_)?token\s+TEXT\b", block, re.IGNORECASE)

    assert "accepted_at TIMESTAMPTZ" in invitations
    assert "revoked_at TIMESTAMPTZ" in invitations
    assert "consumed_at TIMESTAMPTZ" in resets
    assert "idx_password_reset_active_user" in sql
    assert "WHERE status = 'pending'" in sql


def test_invitation_scope_and_delivery_state_are_explicit() -> None:
    sql = _sql()
    invitations = _table(sql, "collaboration_invitations")

    for column in (
        "email_normalized",
        "tenant_role",
        "project_role",
        "invited_by",
        "request_id",
        "delivery_attempts",
        "last_delivery_error_code",
        "delivery_status",
    ):
        assert column in invitations
    assert "idx_collaboration_invites_active_tenant" in sql
    assert "idx_collaboration_invites_active_project" in sql
    assert "collaboration_delivery_attempts" in sql
    assert "password_reset_delivery_attempts" in sql
    assert "not_configured" in sql


def test_collaboration_tables_enforce_tenant_rls_and_safe_token_lookup() -> None:
    sql = _sql()
    for table in ("collaboration_invitations", "collaboration_delivery_attempts"):
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in sql
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in sql
        assert f"tenant_isolation_{table}" in sql

    assert "SECURITY DEFINER" in sql
    assert "SET search_path = public, pg_temp" in sql
    assert "REVOKE ALL ON FUNCTION collaboration_invitation_tenant_for_token(TEXT) FROM PUBLIC" in sql
    function = re.search(
        r"CREATE OR REPLACE FUNCTION collaboration_invitation_tenant_for_token.*?\$\$;",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert function
    assert "token_hash = p_token_hash" in function.group(0)
    assert "SELECT tenant_id" in function.group(0)


def test_sensitive_auth_and_collaboration_actions_have_audit_storage() -> None:
    sql = _sql()
    audit = _table(sql, "auth_security_audit_logs")
    for column in ("user_id", "actor_user_id", "action", "resource_type", "request_id", "metadata_jsonb"):
        assert column in audit
    assert "REVOKE SELECT ON auth_security_audit_logs FROM mirofish_app" in sql
    assert "GRANT INSERT ON auth_security_audit_logs TO mirofish_app" in sql
