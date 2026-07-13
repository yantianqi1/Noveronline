from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "infra" / "postgres" / "migrations" / "0014_llm_platform_defaults.sql"
ROLLBACK = ROOT / "infra" / "postgres" / "rollbacks" / "0014_llm_platform_defaults.sql"


def _sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_platform_channels_and_models_are_read_only_to_tenant_app_role() -> None:
    sql = _sql(MIGRATION)
    for table in ("llm_channels", "llm_models"):
        assert f"CREATE POLICY platform_select_{table}" in sql
        assert f"ON {table} FOR SELECT" in sql
    assert sql.count("USING (tenant_id IS NULL)") >= 2
    assert "platform_write_llm_channels" not in sql
    assert "platform_write_llm_models" not in sql


def test_platform_defaults_have_independent_read_only_storage_and_target_guard() -> None:
    sql = _sql(MIGRATION)
    table = re.search(
        r"CREATE TABLE llm_platform_module_defaults\s*\((.*?)\);",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert table
    body = table.group(1)
    assert "module_key TEXT PRIMARY KEY" in body
    assert "channel_id UUID NOT NULL" in body
    assert "model_id TEXT NOT NULL" in body
    assert "settings_jsonb JSONB NOT NULL" in body
    assert "FOREIGN KEY (channel_id, model_id)" in body
    assert "REFERENCES llm_models(channel_id, model_id)" in body
    assert "enforce_llm_platform_default_target" in sql
    assert "channel.tenant_id IS NULL" in sql
    assert "model.tenant_id IS NULL" in sql
    assert "REVOKE ALL ON llm_platform_module_defaults FROM PUBLIC, mirofish_app" in sql
    assert "GRANT SELECT ON llm_platform_module_defaults TO mirofish_app" in sql
    assert "ALTER TABLE llm_platform_module_defaults FORCE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY select_llm_platform_module_defaults" in sql
    assert "REVOKE ALL ON FUNCTION enforce_llm_platform_default_target() FROM PUBLIC" in sql


def test_tenant_defaults_fail_closed_on_duplicates_before_partial_unique_index() -> None:
    sql = _sql(MIGRATION)
    preflight = sql.index("duplicate tenant-default LLM module bindings")
    index = sql.index("CREATE UNIQUE INDEX llm_module_bindings_tenant_default_key")
    assert preflight < index
    assert "WHERE project_id IS NULL" in sql[index:]
    assert "HAVING count(*) > 1" in sql[:index]


def test_platform_defaults_rollback_is_scoped_and_restores_original_policies() -> None:
    sql = _sql(ROLLBACK)
    assert "LOCK TABLE llm_platform_module_defaults IN ACCESS EXCLUSIVE MODE" in sql
    assert "0014 rollback requires an empty llm_platform_module_defaults table" in sql
    assert sql.index("0014 rollback requires") < sql.index("DROP TABLE IF EXISTS llm_platform_module_defaults")
    assert "DROP TABLE IF EXISTS llm_platform_module_defaults" in sql
    assert "DROP FUNCTION IF EXISTS enforce_llm_platform_default_target()" in sql
    assert "DROP POLICY IF EXISTS platform_select_llm_channels ON llm_channels" in sql
    assert "DROP POLICY IF EXISTS platform_select_llm_models ON llm_models" in sql
    assert "DROP INDEX IF EXISTS llm_module_bindings_tenant_default_key" in sql
    assert "DROP TABLE IF EXISTS llm_channels" not in sql
    assert "DROP TABLE IF EXISTS llm_models" not in sql
