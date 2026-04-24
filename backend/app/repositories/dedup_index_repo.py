"""DedupIndex repository — writer agent anti-repetition pattern store.

Populated by :class:`DedupExtractor` after each scene commit; consumed by
the writer orchestrator just before prompt assembly to surface patterns
already used N-or-more times in earlier chapters.

The underlying table uses a UNIQUE(project_id, pattern_type, pattern_text)
constraint so calling ``add_patterns`` with the same phrase twice collapses
into a ``count`` bump rather than creating duplicate rows.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, and_, select, update

from app.tables.novel import dedup_index

from .base import ProjectScopedRepository


# Canonical pattern types emitted by the LLM extractor. Kept here so callers
# (service + tests) agree on vocabulary; the column itself is unconstrained
# string because future extractors may add types without a migration.
PATTERN_TYPES = (
    "opening_phrase",
    "figurative_phrase",
    "action_verb",
    "sentence_starter",
    "scene_template",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DedupIndexRepository(ProjectScopedRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine, dedup_index)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_patterns(
        self,
        project_id: str,
        chapter_order: int,
        scene_id: str | None,
        patterns: Mapping[str, Mapping[str, int]],
    ) -> int:
        """Insert-or-bump a batch of patterns.

        ``patterns`` shape::

            {"figurative_phrase": {"像一滴浓稠的墨": 2, "眼中的世界是重叠的": 1},
             "opening_phrase":    {"黄昏总是走得很慢": 1}}

        Returns the number of rows affected (inserted + updated).
        """
        if not patterns:
            return 0
        now = _now()
        written = 0
        with self.connect() as conn:
            for pattern_type, text_counts in patterns.items():
                for text, count in text_counts.items():
                    text_clean = (text or "").strip()
                    if not text_clean:
                        continue
                    existing = conn.execute(
                        select(dedup_index).where(
                            and_(
                                dedup_index.c.project_id == project_id,
                                dedup_index.c.pattern_type == pattern_type,
                                dedup_index.c.pattern_text == text_clean,
                            )
                        )
                    ).fetchone()
                    if existing is None:
                        conn.execute(
                            dedup_index.insert().values(
                                id=f"dd_{uuid.uuid4().hex[:12]}",
                                project_id=project_id,
                                chapter_order=int(chapter_order),
                                scene_id=scene_id or None,
                                pattern_type=pattern_type,
                                pattern_text=text_clean,
                                count=max(1, int(count)),
                                first_seen_at=now,
                                last_seen_at=now,
                                created_at=now,
                                updated_at=now,
                            )
                        )
                    else:
                        conn.execute(
                            update(dedup_index)
                            .where(dedup_index.c.id == existing.id)
                            .values(
                                count=existing.count + max(1, int(count)),
                                last_seen_at=now,
                                updated_at=now,
                                # Keep chapter_order as the earliest occurrence
                                # so constraint queries up_to_chapter still hit.
                                chapter_order=min(existing.chapter_order, int(chapter_order)),
                            )
                        )
                    written += 1
        return written

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_constraints(
        self,
        project_id: str,
        up_to_chapter: int | None = None,
        *,
        min_count: int = 2,
        per_type_limit: int = 15,
    ) -> dict[str, list[tuple[str, int]]]:
        """Return high-frequency patterns grouped by type.

        Only patterns first seen at or before ``up_to_chapter`` (inclusive)
        with ``count >= min_count`` are returned, ordered by count DESC.
        Each pattern type is capped at ``per_type_limit`` entries so a
        runaway extractor can't flood the writer prompt.
        """
        clauses = [dedup_index.c.project_id == project_id, dedup_index.c.count >= min_count]
        if up_to_chapter is not None:
            clauses.append(dedup_index.c.chapter_order <= int(up_to_chapter))
        stmt = (
            select(
                dedup_index.c.pattern_type,
                dedup_index.c.pattern_text,
                dedup_index.c.count,
            )
            .where(and_(*clauses))
            .order_by(dedup_index.c.count.desc(), dedup_index.c.pattern_text)
        )
        result: dict[str, list[tuple[str, int]]] = {ptype: [] for ptype in PATTERN_TYPES}
        with self.connect() as conn:
            for row in conn.execute(stmt).fetchall():
                bucket = result.setdefault(row.pattern_type, [])
                if len(bucket) < per_type_limit:
                    bucket.append((row.pattern_text, int(row.count)))
        return result

    def list_all(self, project_id: str) -> list[dict[str, Any]]:
        """Debug / admin helper — raw rows ordered by chapter_order."""
        stmt = (
            select(dedup_index)
            .where(dedup_index.c.project_id == project_id)
            .order_by(dedup_index.c.chapter_order, dedup_index.c.pattern_type)
        )
        with self.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt).fetchall()]

    # ------------------------------------------------------------------
    # Delete / purge
    # ------------------------------------------------------------------

    def purge_chapter(self, project_id: str, chapter_order: int) -> int:
        return self.delete_one(project_id, chapter_order=int(chapter_order))

    def purge_scene(self, project_id: str, scene_id: str) -> int:
        if not scene_id:
            return 0
        return self.delete_one(project_id, scene_id=scene_id)

    def purge_project(self, project_id: str) -> int:
        from sqlalchemy import delete as _delete

        with self.connect() as conn:
            result = conn.execute(
                _delete(dedup_index).where(dedup_index.c.project_id == project_id)
            )
            return result.rowcount or 0
