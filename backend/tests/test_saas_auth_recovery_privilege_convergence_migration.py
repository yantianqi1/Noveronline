from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "infra" / "postgres" / "migrations" / "0010_auth_recovery_privilege_convergence.sql"


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_forward_migration_revokes_every_sensitive_table_from_public_and_app_role() -> None:
    sql = _sql()
    for table in (
        "password_reset_tokens",
        "password_reset_delivery_attempts",
        "password_reset_delivery_outbox",
        "auth_security_audit_logs",
    ):
        assert f"REVOKE ALL PRIVILEGES ON TABLE {table} FROM PUBLIC, mirofish_app" in sql
    assert "auth recovery sensitive table privileges remain exposed" in sql
    assert "grantee IN ('PUBLIC', 'mirofish_app')" in sql


def test_forward_migration_fails_before_revoke_without_security_definer_functions() -> None:
    sql = _sql()
    preflight, revoke = sql.index("FOREACH function_signature"), sql.index("REVOKE ALL PRIVILEGES ON TABLE")
    assert preflight < revoke
    assert "pg_proc" in sql[preflight:revoke]
    assert "prosecdef" in sql[preflight:revoke]
    assert "requires SECURITY DEFINER functions" in sql[preflight:revoke]


def test_only_safe_recovery_functions_are_regranted_to_app_role() -> None:
    sql = _sql()
    signatures = (
        "auth_recovery_request(TEXT, TEXT, BYTEA, TEXT, TIMESTAMPTZ)",
        "auth_recovery_claim_delivery(TEXT, INTEGER)",
        "auth_recovery_finish_delivery(UUID, TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ)",
        "auth_recovery_complete(TEXT, TEXT, TIMESTAMPTZ, TEXT)",
        "auth_recovery_expire(TIMESTAMPTZ)",
    )
    for signature in signatures:
        assert f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC, mirofish_app" in sql
        assert f"GRANT EXECUTE ON FUNCTION {signature} TO mirofish_app" in sql
    assert len(re.findall(r"GRANT\s+EXECUTE\s+ON\s+FUNCTION", sql, flags=re.IGNORECASE)) == len(signatures)
    assert not re.search(r"GRANT\s+(?:SELECT|INSERT|UPDATE|DELETE).*TABLE", sql, flags=re.IGNORECASE)


def test_forward_migration_is_transactional_and_has_no_destructive_rollback() -> None:
    sql = _sql().strip()
    assert sql.startswith("BEGIN;")
    assert sql.endswith("COMMIT;")
    assert "DROP TABLE" not in sql
    assert "DROP FUNCTION" not in sql
    assert not (ROOT / "infra" / "postgres" / "rollbacks" / "0010_auth_recovery_privilege_convergence.sql").exists()
