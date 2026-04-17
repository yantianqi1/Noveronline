"""SQLite FTS5 backend (uses ``global_index_fts`` trigram virtual table).

The FTS virtual table is declared with ``content='global_index'`` so it
reads its source from the base table — but it still needs to be
populated or rebuilt for rows to show up in MATCH queries. To keep
contract tests and ad-hoc callers working after ``upsert`` without
forcing the caller to maintain the FTS index, this backend transparently
triggers a ``rebuild`` on first search if the FTS table is empty.

If the query cannot be tokenised as a valid FTS5 MATCH (e.g. very short
or punctuation-only), the backend falls back to LIKE semantics via
:class:`LikeBackend` so the caller still gets a useful answer.
"""

from __future__ import annotations

import re
from typing import Iterable

from sqlalchemy import Engine, text

from .base import SearchBackend, SearchResult, row_to_result
from .like_search import LikeBackend


_SAFE_FTS_CHARS = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]+")


class SqliteFtsBackend(SearchBackend):
    name = "sqlite_fts5"

    def __init__(self) -> None:
        self._fallback = LikeBackend()

    def search(
        self,
        engine: Engine,
        query: str,
        *,
        project_id: str | None = None,
        sources: Iterable[str] | None = None,
        entity_types: Iterable[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SearchResult]:
        fts_query = self._build_fts_query(query)
        if not fts_query:
            return self._fallback.search(
                engine, query,
                project_id=project_id, sources=sources, entity_types=entity_types,
                limit=limit, offset=offset,
            )

        with engine.connect() as conn:
            self._ensure_fts_populated(conn)
            params: dict[str, object] = {
                "query": fts_query,
                "limit": limit,
                "offset": offset,
            }
            where_clauses = ["global_index_fts MATCH :query"]
            if project_id:
                where_clauses.append("g.project_id = :project_id")
                params["project_id"] = project_id
            if sources:
                sources_list = list(sources)
                placeholders = []
                for idx, value in enumerate(sources_list):
                    key = f"src_{idx}"
                    placeholders.append(f":{key}")
                    params[key] = value
                where_clauses.append(f"g.source IN ({', '.join(placeholders)})")
            if entity_types:
                etype_list = list(entity_types)
                placeholders = []
                for idx, value in enumerate(etype_list):
                    key = f"et_{idx}"
                    placeholders.append(f":{key}")
                    params[key] = value
                where_clauses.append(f"g.entity_type IN ({', '.join(placeholders)})")

            sql = (
                "SELECT g.* FROM global_index_fts "
                "JOIN global_index g ON g.rowid = global_index_fts.rowid "
                f"WHERE {' AND '.join(where_clauses)} "
                "ORDER BY g.updated_at DESC "
                "LIMIT :limit OFFSET :offset"
            )
            rows = [dict(r._mapping) for r in conn.execute(text(sql), params).fetchall()]
        return [row_to_result(row) for row in rows]

    def _build_fts_query(self, query: str) -> str:
        tokens = _SAFE_FTS_CHARS.findall(query or "")
        if not tokens:
            return ""
        return " ".join(f'"{token}"*' for token in tokens)

    def _ensure_fts_populated(self, conn) -> None:
        try:
            fts_count = conn.execute(text("SELECT count(*) FROM global_index_fts")).scalar() or 0
            base_count = conn.execute(text("SELECT count(*) FROM global_index")).scalar() or 0
        except Exception:
            return
        if base_count and not fts_count:
            conn.execute(text("INSERT INTO global_index_fts(global_index_fts) VALUES('rebuild')"))


__all__ = ["SqliteFtsBackend"]
