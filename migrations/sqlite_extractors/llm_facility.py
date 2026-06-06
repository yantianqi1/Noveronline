from __future__ import annotations

import sqlite3
from pathlib import Path


def _fetch_rows(database_path: Path, query: str) -> tuple[dict, ...]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(query).fetchall()
    finally:
        connection.close()
    return tuple(dict(row) for row in rows)


def list_llm_channels(database_path: Path) -> tuple[dict, ...]:
    return _fetch_rows(
        database_path,
        """
        select channel_key, name, base_url, api_key, max_concurrency, is_enabled, created_at, updated_at
        from llm_channels
        order by created_at asc
        """,
    )


def list_llm_models(database_path: Path) -> tuple[dict, ...]:
    return _fetch_rows(
        database_path,
        """
        select channel_key, model_id, owned_by, fetched_at, raw_payload
        from llm_models
        order by fetched_at asc
        """,
    )


def list_llm_module_bindings(database_path: Path) -> tuple[dict, ...]:
    return _fetch_rows(
        database_path,
        """
        select module_key, channel_key, model_id, updated_at
        from llm_module_bindings
        order by updated_at asc
        """,
    )
