"""资产库业务服务。

封装双层 (global / project) 存储的 CRUD、过滤、FTS 搜索、批量启停、批量分类。
所有 ``search_*`` 默认只返回 ``enabled=1`` 的资产，便于 agent 工具直接调用。
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime
from typing import Any, Iterable

from .assets_storage import AssetsStorage, GLOBAL_SCOPE, PROJECT_SCOPE


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id() -> str:
    return f"asset_{uuid.uuid4().hex[:16]}"


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for k in ("payload_json", "tags_json"):
        raw = d.get(k)
        if isinstance(raw, str) and raw:
            try:
                d[k.removesuffix("_json")] = json.loads(raw)
            except json.JSONDecodeError:
                d[k.removesuffix("_json")] = raw
        else:
            d[k.removesuffix("_json")] = [] if k == "tags_json" else {}
    d["enabled"] = bool(d.get("enabled"))
    d["pinned"] = bool(d.get("pinned"))
    return d


_FTS_TOKEN_RE = re.compile(r"[\s,;，；、]+")


def _build_fts_match(query: str) -> str:
    """Convert a free-form query into an FTS5 MATCH expression.

    Splits on whitespace/punctuation, drops short tokens that the trigram
    tokenizer cannot match, and AND-joins the rest. Returns ``""`` if the
    query has no usable terms — callers should fall back to LIKE.
    """
    # FTS5 trigram tokenizer needs ≥3 codepoints per term to produce any trigram.
    tokens = [t for t in _FTS_TOKEN_RE.split(query.strip()) if len(t) >= 3]
    if not tokens:
        return ""
    quoted = [f'"{t}"' for t in tokens]
    return " AND ".join(quoted)


# ----------------------------------------------------------------------
# Service
# ----------------------------------------------------------------------


class AssetsService:
    """双层资产库的业务入口。"""

    def __init__(self) -> None:
        self._global = AssetsStorage.for_global()
        self._project_cache: dict[str, AssetsStorage] = {}

    # -- routing -------------------------------------------------------

    def _store(self, scope: str, project_id: str | None) -> AssetsStorage:
        if scope == GLOBAL_SCOPE:
            return self._global
        if scope == PROJECT_SCOPE:
            if not project_id:
                raise ValueError("project scope requires project_id")
            store = self._project_cache.get(project_id)
            if store is None:
                store = AssetsStorage.for_project(project_id)
                self._project_cache[project_id] = store
            return store
        raise ValueError(f"invalid scope: {scope}")

    # -- create / update / delete --------------------------------------

    def create(
        self,
        *,
        scope: str,
        asset_type: str,
        title: str,
        project_id: str | None = None,
        category: str = "",
        summary: str = "",
        content: str = "",
        payload: dict | None = None,
        tags: list[str] | None = None,
        source_kind: str = "manual",
        source_ref: str = "",
        enabled: bool = True,
        pinned: bool = False,
        asset_id: str | None = None,
    ) -> dict[str, Any]:
        if not title.strip():
            raise ValueError("title is required")
        if scope == PROJECT_SCOPE and not project_id:
            raise ValueError("project scope requires project_id")
        store = self._store(scope, project_id)
        now = _now()
        aid = asset_id or _new_id()
        word_count = len(content or "")
        with store.connect() as conn:
            conn.execute(
                """
                INSERT INTO assets (
                    asset_id, scope, project_id, asset_type, category, title,
                    summary, content, payload_json, tags_json,
                    source_kind, source_ref, enabled, pinned, word_count,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    aid,
                    scope,
                    project_id if scope == PROJECT_SCOPE else None,
                    asset_type,
                    category or "",
                    title,
                    summary or "",
                    content or "",
                    json.dumps(payload or {}, ensure_ascii=False),
                    json.dumps(tags or [], ensure_ascii=False),
                    source_kind or "",
                    source_ref or "",
                    1 if enabled else 0,
                    1 if pinned else 0,
                    word_count,
                    now,
                    now,
                ),
            )
            conn.commit()
        return self.get(aid, scope=scope, project_id=project_id) or {}

    def update(
        self,
        asset_id: str,
        *,
        scope: str,
        project_id: str | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        allowed = {
            "asset_type", "category", "title", "summary", "content",
            "source_kind", "source_ref",
        }
        sets: list[str] = []
        params: list[Any] = []
        for key, value in fields.items():
            if key in allowed:
                sets.append(f"{key} = ?")
                params.append(value if value is not None else "")
            elif key == "payload":
                sets.append("payload_json = ?")
                params.append(json.dumps(value or {}, ensure_ascii=False))
            elif key == "tags":
                sets.append("tags_json = ?")
                params.append(json.dumps(value or [], ensure_ascii=False))
            elif key == "enabled":
                sets.append("enabled = ?")
                params.append(1 if value else 0)
            elif key == "pinned":
                sets.append("pinned = ?")
                params.append(1 if value else 0)
        if "content" in fields:
            sets.append("word_count = ?")
            params.append(len(fields.get("content") or ""))
        if not sets:
            return self.get(asset_id, scope=scope, project_id=project_id) or {}
        sets.append("updated_at = ?")
        params.append(_now())
        params.append(asset_id)
        store = self._store(scope, project_id)
        with store.connect() as conn:
            conn.execute(
                f"UPDATE assets SET {', '.join(sets)} WHERE asset_id = ?",
                params,
            )
            conn.commit()
        return self.get(asset_id, scope=scope, project_id=project_id) or {}

    def delete(
        self,
        asset_id: str,
        *,
        scope: str,
        project_id: str | None = None,
    ) -> bool:
        store = self._store(scope, project_id)
        with store.connect() as conn:
            cur = conn.execute("DELETE FROM assets WHERE asset_id = ?", (asset_id,))
            conn.execute(
                "DELETE FROM asset_links WHERE src_asset_id = ? OR dst_asset_id = ?",
                (asset_id, asset_id),
            )
            conn.commit()
            return cur.rowcount > 0

    # -- read ----------------------------------------------------------

    def get(
        self,
        asset_id: str,
        *,
        scope: str,
        project_id: str | None = None,
    ) -> dict[str, Any] | None:
        store = self._store(scope, project_id)
        with store.connect() as conn:
            row = conn.execute(
                "SELECT * FROM assets WHERE asset_id = ?", (asset_id,)
            ).fetchone()
        return _row_to_dict(row) if row else None

    def find(self, asset_id: str, project_id: str | None = None) -> dict[str, Any] | None:
        """Look up an asset across both layers (project first, then global)."""
        if project_id:
            row = self.get(asset_id, scope=PROJECT_SCOPE, project_id=project_id)
            if row:
                return row
        return self.get(asset_id, scope=GLOBAL_SCOPE)

    def list(
        self,
        *,
        scope: str,
        project_id: str | None = None,
        asset_type: str | None = None,
        category: str | None = None,
        enabled_only: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        store = self._store(scope, project_id)
        clauses: list[str] = []
        params: list[Any] = []
        if asset_type:
            clauses.append("asset_type = ?")
            params.append(asset_type)
        if category is not None:
            clauses.append("category = ?")
            params.append(category)
        if enabled_only:
            clauses.append("enabled = 1")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        with store.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM assets
                {where}
                ORDER BY pinned DESC, updated_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def search(
        self,
        query: str,
        *,
        scope: str,
        project_id: str | None = None,
        asset_type: str | None = None,
        category: str | None = None,
        enabled_only: bool = True,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """FTS search within a single layer.

        Falls back to LIKE if the query has no trigram-eligible tokens.
        """
        store = self._store(scope, project_id)
        match_expr = _build_fts_match(query)
        rows: list[sqlite3.Row]
        with store.connect() as conn:
            if match_expr:
                sql = """
                    SELECT a.*, snippet(assets_fts, 2, '<b>', '</b>', '...', 32) AS snippet
                    FROM assets_fts
                    JOIN assets a ON a.rowid = assets_fts.rowid
                    WHERE assets_fts MATCH ?
                """
                params: list[Any] = [match_expr]
                if asset_type:
                    sql += " AND a.asset_type = ?"
                    params.append(asset_type)
                if category is not None:
                    sql += " AND a.category = ?"
                    params.append(category)
                if enabled_only:
                    sql += " AND a.enabled = 1"
                sql += " LIMIT ?"
                params.append(limit)
                rows = conn.execute(sql, params).fetchall()
            else:
                like = f"%{query}%"
                sql = """
                    SELECT a.*, SUBSTR(a.content, 1, 96) AS snippet
                    FROM assets a
                    WHERE (a.title LIKE ? OR a.summary LIKE ? OR a.content LIKE ?)
                """
                params = [like, like, like]
                if asset_type:
                    sql += " AND a.asset_type = ?"
                    params.append(asset_type)
                if category is not None:
                    sql += " AND a.category = ?"
                    params.append(category)
                if enabled_only:
                    sql += " AND a.enabled = 1"
                sql += " ORDER BY a.updated_at DESC LIMIT ?"
                params.append(limit)
                rows = conn.execute(sql, params).fetchall()
        results = []
        for r in rows:
            d = _row_to_dict(r)
            d["snippet"] = r["snippet"] if "snippet" in r.keys() else ""
            results.append(d)
        return results

    def search_merged(
        self,
        query: str,
        *,
        project_id: str | None = None,
        asset_type: str | None = None,
        category: str | None = None,
        enabled_only: bool = True,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search project layer + global layer, merged. Project hits come first."""
        merged: list[dict[str, Any]] = []
        if project_id:
            merged.extend(
                self.search(
                    query,
                    scope=PROJECT_SCOPE,
                    project_id=project_id,
                    asset_type=asset_type,
                    category=category,
                    enabled_only=enabled_only,
                    limit=limit,
                )
            )
        merged.extend(
            self.search(
                query,
                scope=GLOBAL_SCOPE,
                asset_type=asset_type,
                category=category,
                enabled_only=enabled_only,
                limit=limit,
            )
        )
        return merged[:limit]

    def list_merged(
        self,
        *,
        project_id: str | None = None,
        asset_type: str | None = None,
        category: str | None = None,
        enabled_only: bool = False,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        if project_id:
            merged.extend(
                self.list(
                    scope=PROJECT_SCOPE,
                    project_id=project_id,
                    asset_type=asset_type,
                    category=category,
                    enabled_only=enabled_only,
                    limit=limit,
                )
            )
        merged.extend(
            self.list(
                scope=GLOBAL_SCOPE,
                asset_type=asset_type,
                category=category,
                enabled_only=enabled_only,
                limit=limit,
            )
        )
        return merged

    # -- batch ops -----------------------------------------------------

    def batch_set_enabled(
        self,
        asset_ids: Iterable[str],
        enabled: bool,
        *,
        scope: str,
        project_id: str | None = None,
    ) -> int:
        ids = list(asset_ids)
        if not ids:
            return 0
        store = self._store(scope, project_id)
        placeholders = ",".join("?" * len(ids))
        with store.connect() as conn:
            cur = conn.execute(
                f"UPDATE assets SET enabled = ?, updated_at = ? WHERE asset_id IN ({placeholders})",
                [1 if enabled else 0, _now(), *ids],
            )
            conn.commit()
            return cur.rowcount

    def batch_set_category(
        self,
        asset_ids: Iterable[str],
        category: str,
        *,
        scope: str,
        project_id: str | None = None,
    ) -> int:
        ids = list(asset_ids)
        if not ids:
            return 0
        store = self._store(scope, project_id)
        placeholders = ",".join("?" * len(ids))
        with store.connect() as conn:
            cur = conn.execute(
                f"UPDATE assets SET category = ?, updated_at = ? WHERE asset_id IN ({placeholders})",
                [category or "", _now(), *ids],
            )
            conn.commit()
            return cur.rowcount

    # -- links ---------------------------------------------------------

    def link(
        self,
        src_asset_id: str,
        dst_asset_id: str,
        relation: str,
        *,
        scope: str,
        project_id: str | None = None,
    ) -> None:
        store = self._store(scope, project_id)
        with store.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO asset_links
                    (src_asset_id, dst_asset_id, relation, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (src_asset_id, dst_asset_id, relation, _now()),
            )
            conn.commit()

    def list_links(
        self,
        src_asset_id: str,
        *,
        scope: str,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        store = self._store(scope, project_id)
        with store.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM asset_links WHERE src_asset_id = ?",
                (src_asset_id,),
            ).fetchall()
        return [dict(r) for r in rows]
