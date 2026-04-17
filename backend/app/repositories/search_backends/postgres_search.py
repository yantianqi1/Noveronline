"""PostgreSQL trigram backend.

Uses ``pg_trgm``'s ``%`` similarity operator when the extension is
installed, falling back to ``ILIKE`` otherwise. Kept intentionally
small — Task 10 (real Postgres container integration) owns the
performance-tuned variant.
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import Engine, text

from .base import SearchBackend, SearchResult, row_to_result
from .like_search import LikeBackend


class PostgresTrigramBackend(SearchBackend):
    name = "postgres_trgm"

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
        if not query or not query.strip():
            return []
        if not self._has_pg_trgm(engine):
            return self._fallback.search(
                engine, query,
                project_id=project_id, sources=sources, entity_types=entity_types,
                limit=limit, offset=offset,
            )

        params: dict[str, object] = {
            "query": query,
            "limit": limit,
            "offset": offset,
        }
        where_clauses = ["(title %% :query OR body %% :query)"]
        if project_id:
            where_clauses.append("project_id = :project_id")
            params["project_id"] = project_id
        if sources:
            src_list = list(sources)
            placeholders = []
            for idx, value in enumerate(src_list):
                key = f"src_{idx}"
                placeholders.append(f":{key}")
                params[key] = value
            where_clauses.append(f"source IN ({', '.join(placeholders)})")
        if entity_types:
            et_list = list(entity_types)
            placeholders = []
            for idx, value in enumerate(et_list):
                key = f"et_{idx}"
                placeholders.append(f":{key}")
                params[key] = value
            where_clauses.append(f"entity_type IN ({', '.join(placeholders)})")

        sql = (
            "SELECT *, similarity(coalesce(title, '') || ' ' || coalesce(body, ''), :query) AS _score "
            "FROM global_index "
            f"WHERE {' AND '.join(where_clauses)} "
            "ORDER BY _score DESC, updated_at DESC "
            "LIMIT :limit OFFSET :offset"
        )
        with engine.connect() as conn:
            rows = [dict(r._mapping) for r in conn.execute(text(sql), params).fetchall()]
        return [row_to_result(row) for row in rows]

    def _has_pg_trgm(self, engine: Engine) -> bool:
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
                ).fetchone()
        except Exception:
            return False
        return row is not None


__all__ = ["PostgresTrigramBackend"]
