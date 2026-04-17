"""Search repository.

Replaces global_search_indexer.py data-access with SQLAlchemy Core
through the unified database engine.

Table: global_index (composite PK: source + source_ref)

Write-path and delete-path are dialect-neutral SQLAlchemy Core.
Read-path (``search``) is delegated to a dialect-specific backend via
``search_backends.select_backend`` — SQLite FTS5, PostgreSQL pg_trgm,
or the portable LIKE fallback.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

from sqlalchemy import Engine, and_, delete, insert, or_, select, update

from app.tables.search import global_index

from .base import BaseRepository
from .search_backends import SearchBackend, select_backend


class SearchRepository(BaseRepository):
    def __init__(self, engine: Engine, *, backend: SearchBackend | None = None):
        super().__init__(engine)
        self.table = global_index
        self._backend = backend or select_backend(engine)

    @property
    def backend_name(self) -> str:
        return self._backend.name

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
    # 4. search  (dialect-specific backend routing)
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
        """Delegate the search to the dialect-specific backend."""
        results = self._backend.search(
            self.engine,
            query,
            project_id=project_id,
            sources=sources,
            entity_types=entity_types,
            limit=limit,
            offset=offset,
        )
        return [item.to_dict() for item in results]
