"""资产库 SQLite 存储层。

每个 ``AssetsStorage`` 实例绑定一个 SQLite 文件：
- 全局层：``backend/uploads/system/assets_library.sqlite3``
- 项目层：``backend/uploads/projects/<pid>/assets/project_assets.sqlite3``

两层 schema 完全一致，由上层 ``AssetsService`` 选择路由。
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from ...config import Config


GLOBAL_SCOPE = "global"
PROJECT_SCOPE = "project"


ASSETS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS assets (
    asset_id     TEXT PRIMARY KEY,
    scope        TEXT NOT NULL,
    project_id   TEXT,
    asset_type   TEXT NOT NULL,
    category     TEXT NOT NULL DEFAULT '',
    title        TEXT NOT NULL,
    summary      TEXT NOT NULL DEFAULT '',
    content      TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    tags_json    TEXT NOT NULL DEFAULT '[]',
    source_kind  TEXT NOT NULL DEFAULT '',
    source_ref   TEXT NOT NULL DEFAULT '',
    enabled      INTEGER NOT NULL DEFAULT 1,
    pinned       INTEGER NOT NULL DEFAULT 0,
    word_count   INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
)
"""

ASSET_LINKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS asset_links (
    src_asset_id TEXT NOT NULL,
    dst_asset_id TEXT NOT NULL,
    relation     TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    PRIMARY KEY (src_asset_id, dst_asset_id, relation)
)
"""

INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_assets_type_enabled ON assets(asset_type, enabled)",
    "CREATE INDEX IF NOT EXISTS idx_assets_category     ON assets(category)",
    "CREATE INDEX IF NOT EXISTS idx_assets_project      ON assets(project_id, asset_type)",
    "CREATE INDEX IF NOT EXISTS idx_assets_updated      ON assets(updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_asset_links_src     ON asset_links(src_asset_id)",
    "CREATE INDEX IF NOT EXISTS idx_asset_links_dst     ON asset_links(dst_asset_id)",
)

FTS_STATEMENTS = (
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS assets_fts USING fts5(
        title, summary, content, category, tags_json,
        content='assets', content_rowid='rowid', tokenize='trigram'
    )
    """,
)

TRIGGER_STATEMENTS = (
    """
    CREATE TRIGGER IF NOT EXISTS assets_ai AFTER INSERT ON assets BEGIN
        INSERT INTO assets_fts(rowid, title, summary, content, category, tags_json)
        VALUES (new.rowid, new.title, new.summary, new.content, new.category, new.tags_json);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS assets_au AFTER UPDATE ON assets BEGIN
        INSERT INTO assets_fts(assets_fts, rowid, title, summary, content, category, tags_json)
        VALUES ('delete', old.rowid, old.title, old.summary, old.content, old.category, old.tags_json);
        INSERT INTO assets_fts(rowid, title, summary, content, category, tags_json)
        VALUES (new.rowid, new.title, new.summary, new.content, new.category, new.tags_json);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS assets_ad AFTER DELETE ON assets BEGIN
        INSERT INTO assets_fts(assets_fts, rowid, title, summary, content, category, tags_json)
        VALUES ('delete', old.rowid, old.title, old.summary, old.content, old.category, old.tags_json);
    END
    """,
)


class AssetsStorage:
    """单一 SQLite 文件的资产库存储。"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.ensure_schema()

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    @classmethod
    def global_db_path(cls) -> str:
        upload_root = Config.UPLOAD_FOLDER
        return os.path.join(upload_root, "system", Config.ASSETS_GLOBAL_DB_FILENAME)

    @classmethod
    def project_db_path(cls, project_id: str) -> str:
        # Reads Config.UPLOAD_FOLDER on every call so tests that monkey-patch
        # the upload root see the new path immediately.
        project_dir = os.path.join(Config.UPLOAD_FOLDER, "projects", project_id)
        return os.path.join(project_dir, "assets", Config.ASSETS_PROJECT_DB_FILENAME)

    @classmethod
    def for_global(cls) -> "AssetsStorage":
        return cls(cls.global_db_path())

    @classmethod
    def for_project(cls, project_id: str) -> "AssetsStorage":
        if not project_id:
            raise ValueError("project_id is required for project-scoped assets storage")
        return cls(cls.project_db_path(project_id))

    # ------------------------------------------------------------------
    # Connection / schema
    # ------------------------------------------------------------------

    def ensure_schema(self) -> None:
        self._ensure_parent_dir()
        with self.connect() as conn:
            conn.execute(ASSETS_TABLE_SQL)
            conn.execute(ASSET_LINKS_TABLE_SQL)
            for stmt in INDEX_STATEMENTS:
                conn.execute(stmt)
            for stmt in FTS_STATEMENTS:
                conn.execute(stmt)
            for stmt in TRIGGER_STATEMENTS:
                conn.execute(stmt)
            conn.commit()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self._ensure_parent_dir()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_parent_dir(self) -> None:
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
