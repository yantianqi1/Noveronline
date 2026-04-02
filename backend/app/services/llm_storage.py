"""LLM 设施 SQLite 存储。"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from ..config import Config


CREATE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS llm_channels (
        channel_key TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        base_url TEXT NOT NULL,
        api_key TEXT NOT NULL,
        max_concurrency INTEGER NOT NULL DEFAULT 4,
        is_enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        last_sync_at TEXT,
        last_sync_status TEXT NOT NULL DEFAULT 'idle',
        last_sync_error TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS llm_models (
        channel_key TEXT NOT NULL,
        model_id TEXT NOT NULL,
        owned_by TEXT,
        fetched_at TEXT NOT NULL,
        raw_payload TEXT NOT NULL,
        PRIMARY KEY (channel_key, model_id),
        FOREIGN KEY (channel_key) REFERENCES llm_channels(channel_key) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS llm_module_bindings (
        module_key TEXT PRIMARY KEY,
        channel_key TEXT NOT NULL,
        model_id TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (channel_key) REFERENCES llm_channels(channel_key) ON DELETE CASCADE
    )
    """,
)


class LlmStorage:
    """管理 LLM 设施配置数据库连接与建表。"""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or self.default_db_path()
        self.ensure_schema()

    @classmethod
    def default_db_path(cls) -> str:
        return os.path.join(
            Config.UPLOAD_FOLDER,
            "system",
            Config.LLM_FACILITY_DB_FILENAME,
        )

    def ensure_schema(self) -> None:
        self._ensure_parent_dir()
        with self.connect() as connection:
            for statement in CREATE_STATEMENTS:
                connection.execute(statement)
            self._ensure_llm_channel_columns(connection)
            connection.commit()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self._ensure_parent_dir()
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def _ensure_parent_dir(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _ensure_llm_channel_columns(self, connection: sqlite3.Connection) -> None:
        existing = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(llm_channels)").fetchall()
        }
        if "max_concurrency" not in existing:
            connection.execute(
                """
                ALTER TABLE llm_channels
                ADD COLUMN max_concurrency INTEGER NOT NULL DEFAULT 4
                """
            )
