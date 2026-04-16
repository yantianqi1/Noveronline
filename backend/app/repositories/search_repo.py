"""Search repository.

Replaces global_search_indexer.py data-access with SQLAlchemy Core
through the unified database engine.

Table: global_index (composite PK: source + source_ref)

This repository handles CRUD and LIKE-based search. The original FTS5
trigram virtual table (global_index_fts) is a SQLite-specific feature
that cannot be expressed portably in SQLAlchemy Core; the search method
uses LIKE filtering instead, which works across SQLite and PostgreSQL.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

from sqlalchemy import Engine, and_, delete, desc, insert, or_, select, update

from app.tables.search import global_index

from .base import BaseRepository


class SearchRepository(BaseRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine)
        self.table = global_index

    # ------------------------------------------------------------------
    # 1. upsert  (bulk upsert by source + source_ref)
    # ------------------------------------------------------------------

    def upsert(self, items: Iterable[dict[str, Any]]) -> int:
        """Bulk upsert into global_index keyed by (source, source_ref).

        Each item dict must contain at least ``source`` and ``source_ref``.
        Returns the number of rows written.
        """
        tbl = self.table
        rows = list(items)
        if not rows:
            return 0

        with self.connect() as conn:
            for item in rows:
                source = item["source"]
                source_ref = item["source_ref"]

                # Normalize tags list to space-separated string
                tags = item.get("tags") or []
                if isinstance(tags, list):
                    tags_str = " ".join(str(t) for t in tags)
                else:
                    tags_str = str(tags)

                # Build body from summary + payload JSON
                body = (
                    (item.get("summary") or "")
                    + "\n"
                    + json.dumps(item.get("payload") or {}, ensure_ascii=False)
                )

                payload = {
                    "source": source,
                    "source_ref": source_ref,
                    "project_id": item.get("project_id"),
                    "entity_type": item.get("entity_type") or "",
                    "title": item.get("title") or "",
                    "body": body,
                    "tags": tags_str,
                    "updated_at": item.get("updated_at") or "",
                    "payload_json": json.dumps(item.get("payload") or {}, ensure_ascii=False),
                }

                where = and_(
                    tbl.c.source == source,
                    tbl.c.source_ref == source_ref,
                )
                existing = conn.execute(select(tbl).where(where).limit(1)).fetchone()
                if existing:
                    conn.execute(update(tbl).where(where).values(**payload))
                else:
                    conn.execute(insert(tbl).values(**payload))

        return len(rows)

    # ------------------------------------------------------------------
    # 2. delete  (single entry by source + source_ref)
    # ------------------------------------------------------------------

    def delete(self, source: str, source_ref: str) -> bool:
        tbl = self.table
        where = and_(tbl.c.source == source, tbl.c.source_ref == source_ref)
        with self.connect() as conn:
            result = conn.execute(delete(tbl).where(where))
            return (result.rowcount or 0) > 0

    # ------------------------------------------------------------------
    # 3. delete_project  (all entries for a project, optional source filter)
    # ------------------------------------------------------------------

    def delete_project(
        self,
        project_id: str,
        source: str | None = None,
    ) -> int:
        tbl = self.table
        clauses = [tbl.c.project_id == project_id]
        if source:
            clauses.append(tbl.c.source == source)
        with self.connect() as conn:
            result = conn.execute(delete(tbl).where(and_(*clauses)))
            return result.rowcount or 0

    # ------------------------------------------------------------------
    # 4. search  (LIKE-based with optional filters)
    # ------------------------------------------------------------------

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
        """LIKE-based search across title and body with optional filters."""
        tbl = self.table
        like_pattern = f"%{query}%"
        clauses = [
            or_(
                tbl.c.title.like(like_pattern),
                tbl.c.body.like(like_pattern),
            )
        ]
        if project_id:
            clauses.append(tbl.c.project_id == project_id)
        if sources:
            src_list = list(sources)
            clauses.append(tbl.c.source.in_(src_list))
        if entity_types:
            et_list = list(entity_types)
            clauses.append(tbl.c.entity_type.in_(et_list))

        stmt = (
            select(tbl)
            .where(and_(*clauses))
            .order_by(desc(tbl.c.updated_at))
            .limit(limit)
            .offset(offset)
        )
        with self.connect() as conn:
            rows = conn.execute(stmt).fetchall()

        results: list[dict[str, Any]] = []
        for r in rows:
            r_dict = dict(r._mapping)
            payload: dict[str, Any] = {}
            try:
                payload = json.loads(r_dict.get("payload_json") or "{}") or {}
            except (json.JSONDecodeError, TypeError):
                payload = {}

            body_text = r_dict.get("body") or ""
            tags_text = r_dict.get("tags") or ""

            results.append({
                "source": r_dict["source"],
                "source_ref": r_dict["source_ref"],
                "project_id": r_dict.get("project_id"),
                "entity_type": r_dict.get("entity_type", ""),
                "title": r_dict.get("title", ""),
                "summary": body_text.split("\n", 1)[0],
                "tags": tags_text.split() if tags_text else [],
                "updated_at": r_dict.get("updated_at", ""),
                "payload": payload,
                "snippet": body_text[:96] if body_text else "",
            })
        return results
