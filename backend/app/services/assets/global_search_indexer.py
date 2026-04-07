"""全局 FTS 搜索索引。

把所有 silo 的可搜索条目镜像到 ``backend/uploads/system/global_search.sqlite3``
中的 ``global_index`` 表，并建一个 FTS5 trigram 虚表用于快速搜索。

设计原则：
- **镜像，不写源** —— 索引出问题时只重建索引即可，不会破坏任何 silo。
- **以 UnifiedAssetView 为单一数据接入** —— 任何 source 修改 reader 后，
  ``reindex_project`` 立刻能跟上。
- **失败显式** —— 不静默吞错，按 CLAUDE.md 让异常向上抛。
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterable, Iterator

from ...config import Config
from .unified_asset_view import ALL_SOURCES, UnifiedAssetView


GLOBAL_SEARCH_DB_FILENAME = "global_search.sqlite3"

_FTS_TOKEN_RE = re.compile(r"[\s,;，；、]+")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _build_match(query: str) -> str:
    tokens = [t for t in _FTS_TOKEN_RE.split(query.strip()) if len(t) >= 3]
    if not tokens:
        return ""
    return " AND ".join(f'"{t}"' for t in tokens)


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS global_index (
        source       TEXT NOT NULL,
        source_ref   TEXT NOT NULL,
        project_id   TEXT,
        entity_type  TEXT NOT NULL DEFAULT '',
        title        TEXT NOT NULL DEFAULT '',
        body         TEXT NOT NULL DEFAULT '',
        tags         TEXT NOT NULL DEFAULT '',
        updated_at   TEXT NOT NULL DEFAULT '',
        payload_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (source, source_ref)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_gi_project ON global_index(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_gi_source  ON global_index(source)",
    "CREATE INDEX IF NOT EXISTS idx_gi_type    ON global_index(entity_type)",
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS global_index_fts USING fts5(
        title, body, tags, entity_type,
        content='global_index', content_rowid='rowid', tokenize='trigram'
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS gi_ai AFTER INSERT ON global_index BEGIN
        INSERT INTO global_index_fts(rowid, title, body, tags, entity_type)
        VALUES (new.rowid, new.title, new.body, new.tags, new.entity_type);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS gi_au AFTER UPDATE ON global_index BEGIN
        INSERT INTO global_index_fts(global_index_fts, rowid, title, body, tags, entity_type)
        VALUES ('delete', old.rowid, old.title, old.body, old.tags, old.entity_type);
        INSERT INTO global_index_fts(rowid, title, body, tags, entity_type)
        VALUES (new.rowid, new.title, new.body, new.tags, new.entity_type);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS gi_ad AFTER DELETE ON global_index BEGIN
        INSERT INTO global_index_fts(global_index_fts, rowid, title, body, tags, entity_type)
        VALUES ('delete', old.rowid, old.title, old.body, old.tags, old.entity_type);
    END
    """,
)


class GlobalSearchIndexer:
    """全局 FTS 索引。"""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or os.path.join(
            Config.UPLOAD_FOLDER, "system", GLOBAL_SEARCH_DB_FILENAME
        )
        self._ensure_schema()

    # -- connection ----------------------------------------------------
    def _ensure_schema(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._connect() as conn:
            for stmt in SCHEMA_STATEMENTS:
                conn.execute(stmt)
            conn.commit()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # -- write ---------------------------------------------------------
    def upsert(self, items: Iterable[dict[str, Any]]) -> int:
        """批量写入 unified asset DTO。``items`` 元素必须含 source/source_ref。"""
        rows = list(items)
        if not rows:
            return 0
        with self._connect() as conn:
            for it in rows:
                tags = it.get("tags") or []
                if isinstance(tags, list):
                    tags_str = " ".join(str(t) for t in tags)
                else:
                    tags_str = str(tags)
                conn.execute(
                    """
                    INSERT INTO global_index
                        (source, source_ref, project_id, entity_type, title, body, tags, updated_at, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source, source_ref) DO UPDATE SET
                        project_id  = excluded.project_id,
                        entity_type = excluded.entity_type,
                        title       = excluded.title,
                        body        = excluded.body,
                        tags        = excluded.tags,
                        updated_at  = excluded.updated_at,
                        payload_json= excluded.payload_json
                    """,
                    (
                        it["source"],
                        it["source_ref"],
                        it.get("project_id"),
                        it.get("entity_type") or "",
                        it.get("title") or "",
                        (it.get("summary") or "")
                        + "\n"
                        + json.dumps(it.get("payload") or {}, ensure_ascii=False),
                        tags_str,
                        it.get("updated_at") or _now(),
                        json.dumps(it.get("payload") or {}, ensure_ascii=False),
                    ),
                )
            conn.commit()
        return len(rows)

    def delete(self, source: str, source_ref: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM global_index WHERE source = ? AND source_ref = ?",
                (source, source_ref),
            )
            conn.commit()
            return cur.rowcount > 0

    def delete_project(self, project_id: str, source: str | None = None) -> int:
        with self._connect() as conn:
            if source:
                cur = conn.execute(
                    "DELETE FROM global_index WHERE project_id = ? AND source = ?",
                    (project_id, source),
                )
            else:
                cur = conn.execute(
                    "DELETE FROM global_index WHERE project_id = ?",
                    (project_id,),
                )
            conn.commit()
            return cur.rowcount

    def reindex_project(self, project_id: str) -> int:
        """对单个项目全量重建索引。"""
        view = UnifiedAssetView()
        result = view.list(project_id=project_id, page=1, page_size=10000)
        items = result["items"]
        # 清掉旧条目（仅这个 project 的所有 silo + 全局 assets 中归属此 project 的）
        self.delete_project(project_id)
        # 全局 assets 不一定带 project_id，需单独清并按 source 重写
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM global_index WHERE source = 'assets' AND (project_id IS NULL OR project_id = ?)",
                (project_id,),
            )
            conn.commit()
        return self.upsert(items)

    # -- read ----------------------------------------------------------
    def search(
        self,
        query: str,
        *,
        project_id: str | None = None,
        sources: Iterable[str] | None = None,
        entity_types: Iterable[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        match = _build_match(query)
        params: list[Any] = []
        with self._connect() as conn:
            if match:
                sql = """
                    SELECT g.*, snippet(global_index_fts, 1, '<b>', '</b>', '...', 24) AS snippet
                    FROM global_index_fts
                    JOIN global_index g ON g.rowid = global_index_fts.rowid
                    WHERE global_index_fts MATCH ?
                """
                params.append(match)
            else:
                like = f"%{query}%"
                sql = """
                    SELECT g.*, SUBSTR(g.body, 1, 96) AS snippet
                    FROM global_index g
                    WHERE (g.title LIKE ? OR g.body LIKE ?)
                """
                params.extend([like, like])
            if project_id:
                sql += " AND g.project_id = ?"
                params.append(project_id)
            if sources:
                src_list = list(sources)
                placeholders = ",".join("?" * len(src_list))
                sql += f" AND g.source IN ({placeholders})"
                params.extend(src_list)
            if entity_types:
                et_list = list(entity_types)
                placeholders = ",".join("?" * len(et_list))
                sql += f" AND g.entity_type IN ({placeholders})"
                params.extend(et_list)
            sql += " ORDER BY g.updated_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            rows = conn.execute(sql, params).fetchall()

        results: list[dict[str, Any]] = []
        for r in rows:
            payload = {}
            try:
                payload = json.loads(r["payload_json"]) if r["payload_json"] else {}
            except json.JSONDecodeError:
                payload = {}
            results.append(
                {
                    "source": r["source"],
                    "source_ref": r["source_ref"],
                    "project_id": r["project_id"],
                    "entity_type": r["entity_type"],
                    "title": r["title"],
                    "summary": (r["body"] or "").split("\n", 1)[0],
                    "tags": (r["tags"] or "").split() if r["tags"] else [],
                    "updated_at": r["updated_at"],
                    "payload": payload,
                    "snippet": r["snippet"] if "snippet" in r.keys() else "",
                }
            )
        return results
