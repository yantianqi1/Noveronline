"""章节卡元数据 SQLite 存储。"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from ..config import Config
from ..models.project import ProjectManager


CHAPTER_META_DB_FILENAME = "chapter_meta.sqlite3"

CHAPTER_META_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS chapter_meta (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL,
        chapter_order INTEGER NOT NULL,
        chapter_id TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL DEFAULT '',
        summary_text TEXT NOT NULL DEFAULT '',
        timeline_note TEXT NOT NULL DEFAULT '',
        start_anchor TEXT NOT NULL DEFAULT '',
        end_anchor TEXT NOT NULL DEFAULT '',
        open_threads_json TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
"""

CHAPTER_HISTORY_ITEM_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS chapter_history_item (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL,
        chapter_order INTEGER NOT NULL,
        chapter_id TEXT NOT NULL DEFAULT '',
        item_type TEXT NOT NULL,
        subject_key TEXT NOT NULL DEFAULT '',
        summary_text TEXT NOT NULL DEFAULT '',
        related_entities_json TEXT NOT NULL DEFAULT '[]',
        thread_key TEXT NOT NULL DEFAULT '',
        source_kind TEXT NOT NULL DEFAULT '',
        source_ref TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
"""

CHAPTER_META_COLUMNS = {
    "chapter_order": "INTEGER NOT NULL DEFAULT 0",
    "chapter_id": "TEXT NOT NULL DEFAULT ''",
    "title": "TEXT NOT NULL DEFAULT ''",
    "summary_text": "TEXT NOT NULL DEFAULT ''",
    "timeline_note": "TEXT NOT NULL DEFAULT ''",
    "start_anchor": "TEXT NOT NULL DEFAULT ''",
    "end_anchor": "TEXT NOT NULL DEFAULT ''",
    "open_threads_json": "TEXT NOT NULL DEFAULT '[]'",
    "created_at": "TEXT NOT NULL DEFAULT ''",
    "updated_at": "TEXT NOT NULL DEFAULT ''",
}

CHAPTER_HISTORY_ITEM_COLUMNS = {
    "project_id": "TEXT NOT NULL DEFAULT ''",
    "chapter_order": "INTEGER NOT NULL DEFAULT 0",
    "chapter_id": "TEXT NOT NULL DEFAULT ''",
    "item_type": "TEXT NOT NULL DEFAULT ''",
    "subject_key": "TEXT NOT NULL DEFAULT ''",
    "summary_text": "TEXT NOT NULL DEFAULT ''",
    "related_entities_json": "TEXT NOT NULL DEFAULT '[]'",
    "thread_key": "TEXT NOT NULL DEFAULT ''",
    "source_kind": "TEXT NOT NULL DEFAULT ''",
    "source_ref": "TEXT NOT NULL DEFAULT ''",
    "created_at": "TEXT NOT NULL DEFAULT ''",
    "updated_at": "TEXT NOT NULL DEFAULT ''",
}

INDEX_STATEMENTS = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_chapter_meta_unique ON chapter_meta(project_id, chapter_order)",
    "CREATE INDEX IF NOT EXISTS idx_chapter_meta_project ON chapter_meta(project_id, chapter_order ASC)",
    "CREATE INDEX IF NOT EXISTS idx_history_project_order ON chapter_history_item(project_id, chapter_order ASC)",
    "CREATE INDEX IF NOT EXISTS idx_history_project_type ON chapter_history_item(project_id, item_type)",
    "CREATE INDEX IF NOT EXISTS idx_history_thread ON chapter_history_item(project_id, thread_key)",
)


class ChapterMetaStorage:
    """管理章节卡相关 SQLite 连接和 schema。"""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or self.default_db_path()
        self.ensure_schema()

    @classmethod
    def default_db_path(cls) -> str:
        project_root = (
            os.path.dirname(ProjectManager.PROJECTS_DIR)
            if getattr(ProjectManager, "PROJECTS_DIR", "")
            else ""
        )
        upload_root = project_root or Config.UPLOAD_FOLDER
        return os.path.join(upload_root, "system", CHAPTER_META_DB_FILENAME)

    def ensure_schema(self) -> None:
        self._ensure_parent_dir()
        with self.connect() as connection:
            self._ensure_table(connection, "chapter_meta", CHAPTER_META_TABLE_SQL, CHAPTER_META_COLUMNS)
            self._ensure_table(
                connection,
                "chapter_history_item",
                CHAPTER_HISTORY_ITEM_TABLE_SQL,
                CHAPTER_HISTORY_ITEM_COLUMNS,
            )
            self._backfill_legacy_columns(connection)
            for statement in INDEX_STATEMENTS:
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

    def _ensure_table(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        create_sql: str,
        expected_columns: dict[str, str],
    ) -> None:
        connection.execute(create_sql)
        existing = self._column_names(connection, table_name)
        for name, column_sql in expected_columns.items():
            if name in existing:
                continue
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {name} {column_sql}")

    def _column_names(self, connection: sqlite3.Connection, table_name: str) -> set[str]:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {row["name"] for row in rows}

    def _backfill_legacy_columns(self, connection: sqlite3.Connection) -> None:
        columns = self._column_names(connection, "chapter_meta")
        if "chapter_index" not in columns or "chapter_order" not in columns:
            return
        connection.execute(
            """
            UPDATE chapter_meta
            SET chapter_order = chapter_index
            WHERE chapter_order = 0
            """
        )

    def _ensure_parent_dir(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
