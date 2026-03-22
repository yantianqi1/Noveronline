"""任务运行态 SQLite 存储。"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from ..config import Config


CREATE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS task_runs (
        task_id TEXT PRIMARY KEY,
        task_type TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        progress INTEGER NOT NULL,
        message TEXT NOT NULL,
        result_json TEXT,
        error TEXT,
        metadata_json TEXT NOT NULL,
        progress_detail_json TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_task_runs_type_created_at ON task_runs(task_type, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_task_runs_status_updated_at ON task_runs(status, updated_at DESC)",
)


class TaskStorage:
    """管理任务持久化数据库。"""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or self.default_db_path()
        self.ensure_schema()

    @classmethod
    def default_db_path(cls) -> str:
        return os.path.join(Config.UPLOAD_FOLDER, "system", "task_runtime.sqlite3")

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

