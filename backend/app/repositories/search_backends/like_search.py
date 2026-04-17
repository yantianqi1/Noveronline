"""Portable LIKE-based search backend (default fallback)."""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import Engine, and_, desc, or_, select

from app.tables.search import global_index

from .base import SearchBackend, SearchResult, row_to_result


class LikeBackend(SearchBackend):
    name = "like"

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
        tbl = global_index
        like_pattern = f"%{query}%"
        clauses = [or_(tbl.c.title.like(like_pattern), tbl.c.body.like(like_pattern))]
        if project_id:
            clauses.append(tbl.c.project_id == project_id)
        if sources:
            clauses.append(tbl.c.source.in_(list(sources)))
        if entity_types:
            clauses.append(tbl.c.entity_type.in_(list(entity_types)))
        stmt = (
            select(tbl)
            .where(and_(*clauses))
            .order_by(desc(tbl.c.updated_at))
            .limit(limit)
            .offset(offset)
        )
        with engine.connect() as conn:
            rows = [dict(r._mapping) for r in conn.execute(stmt).fetchall()]
        return [row_to_result(row) for row in rows]


__all__ = ["LikeBackend"]
