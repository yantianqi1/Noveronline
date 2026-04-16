"""Chapter repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, and_, delete, func, insert, select, update

from app.tables.novel import (
    chapter_content,
    chapter_meta,
    scenes,
    segment_summaries,
    volume_summaries,
)

from .base import ProjectScopedRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Columns that live in chapter_content vs chapter_meta
_CONTENT_COLS = {"chapter_order", "title", "content", "word_count", "status"}
_META_COLS = {
    "summary", "outline_json", "timeline_note", "open_threads_json",
    "pov_character", "key_events_json", "character_state_updates_json",
    "relationship_updates_json", "start_anchor", "end_anchor",
}

# chapter_meta columns to include in joins (everything except chapter_id to avoid collision)
_META_SELECT_COLS = [
    chapter_meta.c.summary,
    chapter_meta.c.outline_json,
    chapter_meta.c.timeline_note,
    chapter_meta.c.open_threads_json,
    chapter_meta.c.pov_character,
    chapter_meta.c.key_events_json,
    chapter_meta.c.character_state_updates_json,
    chapter_meta.c.relationship_updates_json,
    chapter_meta.c.start_anchor,
    chapter_meta.c.end_anchor,
]

# chapter_content columns excluding 'content' (for list / non-content queries)
_CONTENT_NO_BODY = [
    chapter_content.c.chapter_id,
    chapter_content.c.project_id,
    chapter_content.c.chapter_order,
    chapter_content.c.title,
    chapter_content.c.word_count,
    chapter_content.c.status,
    chapter_content.c.created_at,
    chapter_content.c.updated_at,
]


def _joined_select(include_content: bool):
    """Build a SELECT from chapter_content LEFT JOIN chapter_meta."""
    if include_content:
        cols = [chapter_content] + _META_SELECT_COLS
    else:
        cols = _CONTENT_NO_BODY + _META_SELECT_COLS

    return (
        select(*cols).select_from(
            chapter_content.outerjoin(
                chapter_meta,
                chapter_content.c.chapter_id == chapter_meta.c.chapter_id,
            )
        )
    )


class ChapterRepository(ProjectScopedRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine, chapter_content)
        self.meta = ProjectScopedRepository(engine, chapter_meta)
        self.segments = ProjectScopedRepository(engine, segment_summaries)
        self.volumes = ProjectScopedRepository(engine, volume_summaries)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_chapter(
        self, project_id: str, chapter_id: str, include_content: bool = False,
    ) -> dict[str, Any] | None:
        """Get chapter by chapter_id with LEFT JOIN on chapter_meta."""
        stmt = (
            _joined_select(include_content)
            .where(
                and_(
                    chapter_content.c.project_id == project_id,
                    chapter_content.c.chapter_id == chapter_id,
                )
            )
            .limit(1)
        )
        with self.connect() as conn:
            return self.row_to_dict(conn.execute(stmt).fetchone())

    def get_chapter_by_order(
        self, project_id: str, chapter_order: int, include_content: bool = False,
    ) -> dict[str, Any] | None:
        """Get chapter by chapter_order with LEFT JOIN on chapter_meta."""
        stmt = (
            _joined_select(include_content)
            .where(
                and_(
                    chapter_content.c.project_id == project_id,
                    chapter_content.c.chapter_order == chapter_order,
                )
            )
            .limit(1)
        )
        with self.connect() as conn:
            return self.row_to_dict(conn.execute(stmt).fetchone())

    def list_chapters(self, project_id: str) -> list[dict[str, Any]]:
        """List all chapters (no content body) ordered by chapter_order."""
        stmt = (
            _joined_select(include_content=False)
            .where(chapter_content.c.project_id == project_id)
            .order_by(chapter_content.c.chapter_order)
        )
        with self.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt).fetchall()]

    # ------------------------------------------------------------------
    # Create / Update / Delete
    # ------------------------------------------------------------------

    def create_chapter(
        self,
        project_id: str,
        chapter_id: str,
        chapter_order: int,
        title: str = "",
    ) -> None:
        """Insert into chapter_content (draft) AND chapter_meta."""
        now = _now()
        with self.connect() as conn:
            conn.execute(
                insert(chapter_content).values(
                    chapter_id=chapter_id,
                    project_id=project_id,
                    chapter_order=chapter_order,
                    title=title,
                    content="",
                    word_count=0,
                    status="draft",
                    created_at=now,
                    updated_at=now,
                )
            )
            conn.execute(
                insert(chapter_meta).values(
                    chapter_id=chapter_id,
                    project_id=project_id,
                    updated_at=now,
                )
            )

    def update_chapter(self, project_id: str, chapter_id: str, **kwargs: Any) -> None:
        """Split kwargs into content vs meta columns and update the appropriate tables."""
        now = _now()

        with self.connect() as conn:
            cc_updates = {k: v for k, v in kwargs.items() if k in _CONTENT_COLS}
            if cc_updates:
                cc_updates["updated_at"] = now
                conn.execute(
                    update(chapter_content)
                    .where(
                        and_(
                            chapter_content.c.project_id == project_id,
                            chapter_content.c.chapter_id == chapter_id,
                        )
                    )
                    .values(**cc_updates)
                )

            cm_updates = {k: v for k, v in kwargs.items() if k in _META_COLS}
            if cm_updates:
                cm_updates["updated_at"] = now
                conn.execute(
                    update(chapter_meta)
                    .where(
                        and_(
                            chapter_meta.c.project_id == project_id,
                            chapter_meta.c.chapter_id == chapter_id,
                        )
                    )
                    .values(**cm_updates)
                )

    def delete_chapter(self, project_id: str, chapter_id: str) -> int:
        """Delete from chapter_content (CASCADE deletes meta)."""
        stmt = delete(chapter_content).where(
            and_(
                chapter_content.c.project_id == project_id,
                chapter_content.c.chapter_id == chapter_id,
            )
        )
        with self.connect() as conn:
            result = conn.execute(stmt)
            return result.rowcount or 0

    # ------------------------------------------------------------------
    # Ensure / auto-create
    # ------------------------------------------------------------------

    def ensure_chapter(
        self, project_id: str, chapter_id: str, chapter_order: int = 0,
    ) -> None:
        """Create chapter if it doesn't already exist. Auto-assigns MAX+1 order if 0."""
        with self.connect() as conn:
            existing = conn.execute(
                select(chapter_content.c.chapter_id).where(
                    and_(
                        chapter_content.c.project_id == project_id,
                        chapter_content.c.chapter_id == chapter_id,
                    )
                ).limit(1)
            ).fetchone()
            if existing:
                return

            if not chapter_order:
                row = conn.execute(
                    select(func.coalesce(func.max(chapter_content.c.chapter_order), 0) + 1)
                    .where(chapter_content.c.project_id == project_id)
                ).fetchone()
                chapter_order = row[0] if row else 1

            now = _now()
            conn.execute(
                insert(chapter_content).values(
                    chapter_id=chapter_id,
                    project_id=project_id,
                    chapter_order=chapter_order,
                    title="",
                    content="",
                    word_count=0,
                    status="draft",
                    created_at=now,
                    updated_at=now,
                )
            )
            conn.execute(
                insert(chapter_meta).prefix_with("OR IGNORE").values(
                    chapter_id=chapter_id,
                    project_id=project_id,
                    updated_at=now,
                )
            )

    # ------------------------------------------------------------------
    # Compilation
    # ------------------------------------------------------------------

    def compile_chapter(self, project_id: str, chapter_id: str) -> None:
        """Concatenate all scenes by scene_order into chapter_content."""
        now = _now()
        with self.connect() as conn:
            rows = conn.execute(
                select(scenes.c.content)
                .where(
                    and_(
                        scenes.c.project_id == project_id,
                        scenes.c.chapter_id == chapter_id,
                    )
                )
                .order_by(scenes.c.scene_order)
            ).fetchall()

            full_content = "\n\n".join(r.content for r in rows)
            word_count = len(full_content)

            conn.execute(
                update(chapter_content)
                .where(
                    and_(
                        chapter_content.c.project_id == project_id,
                        chapter_content.c.chapter_id == chapter_id,
                    )
                )
                .values(content=full_content, word_count=word_count, updated_at=now)
            )
