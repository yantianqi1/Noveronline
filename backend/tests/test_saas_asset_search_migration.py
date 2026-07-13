from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = ROOT / "infra" / "postgres" / "migrations" / "0002_assets_hybrid_search.sql"


def _migration_sql() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def _table_block(sql: str, table_name: str) -> str:
    match = re.search(
        rf"CREATE TABLE IF NOT EXISTS {table_name}\s*\((.*?)\);",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, f"{table_name} table is missing"
    return match.group(1)


def test_asset_search_migration_adds_pgvector_and_weighted_fts() -> None:
    sql = _migration_sql()

    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert re.search(r"ADD COLUMN IF NOT EXISTS search_vector\s+TSVECTOR", sql, re.IGNORECASE)
    assert "idx_global_search_index_search_vector" in sql
    assert "USING GIN (search_vector)" in sql
    for weight in ("'A'", "'B'", "'C'", "'D'"):
        assert f"setweight(" in sql and weight in sql


def test_asset_embeddings_contract_is_model_and_dimension_explicit() -> None:
    table_sql = _table_block(_migration_sql(), "asset_embeddings")

    for column in (
        "tenant_id",
        "embedding_id",
        "asset_id",
        "project_id",
        "embedding_model",
        "dimensions",
        "embedding VECTOR",
        "content_sha256",
        "reindex_batch_id",
        "source_updated_at",
        "created_at",
        "updated_at",
    ):
        assert column in table_sql
    assert "UNIQUE (tenant_id, project_id, asset_id, embedding_model)" in table_sql
    assert "vector_dims(embedding) = dimensions" in table_sql
    assert "idx_asset_embeddings_tenant_project_model" in _migration_sql()


def test_asset_embeddings_forces_tenant_rls_and_app_role_grants() -> None:
    sql = _migration_sql()

    assert "ALTER TABLE asset_embeddings ENABLE ROW LEVEL SECURITY" in sql
    assert "ALTER TABLE asset_embeddings FORCE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY tenant_isolation_asset_embeddings" in sql
    assert "current_setting('app.current_tenant_id', true)" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON asset_embeddings TO mirofish_app" in sql
