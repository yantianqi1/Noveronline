"""全局主档案库 SQLite 存储。"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from ..config import Config


CREATE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS archive_library (
        archive_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        project_name TEXT NOT NULL,
        entity_uuid TEXT NOT NULL,
        entity_name TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        importance_tier TEXT NOT NULL,
        entity_role TEXT NOT NULL,
        core_drive TEXT NOT NULL,
        surface_mask TEXT NOT NULL,
        hidden_tension TEXT NOT NULL,
        relationship_summary TEXT NOT NULL,
        agent_behavior_hint TEXT NOT NULL,
        human_ai_relation_tag TEXT NOT NULL,
        can_act_as_agent INTEGER NOT NULL DEFAULT 1,
        notable_risks TEXT NOT NULL,
        synced_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS archive_sources (
        project_id TEXT PRIMARY KEY,
        project_name TEXT NOT NULL,
        file_path TEXT NOT NULL,
        file_mtime REAL NOT NULL,
        synced_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_archive_library_project_id ON archive_library(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_archive_library_entity_type ON archive_library(entity_type)",
    "CREATE INDEX IF NOT EXISTS idx_archive_library_importance_tier ON archive_library(importance_tier)",
    "CREATE INDEX IF NOT EXISTS idx_archive_library_entity_name ON archive_library(entity_name)",
)


class ArchiveLibraryStorage:
    """管理全局主档案库连接和建表。"""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or self.default_db_path()
        self.ensure_schema()

    @classmethod
    def default_db_path(cls) -> str:
        return os.path.join(
            Config.UPLOAD_FOLDER,
            "system",
            Config.ARCHIVE_LIBRARY_DB_FILENAME,
        )

    def ensure_schema(self) -> None:
        self._ensure_parent_dir()
        with self.connect() as connection:
            for statement in CREATE_STATEMENTS:
                connection.execute(statement)
            connection.commit()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self._ensure_parent_dir()
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def _ensure_parent_dir(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
