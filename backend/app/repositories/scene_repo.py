"""Scene repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, and_, delete, insert, select, update

from app.tables.novel import chapter_content, scenes

from .base import ProjectScopedRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SceneRepository(ProjectScopedRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine, scenes)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_scenes(self, project_id: str, chapter_id: str) -> list[dict[str, Any]]:
        """List scenes for a chapter, ordered by scene_order."""
        stmt = (
            select(
                scenes.c.scene_id,
                scenes.c.scene_order,
                scenes.c.title,
                scenes.c.word_count,
                scenes.c.status,
            )
            .where(
                and_(
                    scenes.c.project_id == project_id,
                    scenes.c.chapter_id == chapter_id,
                )
            )
            .order_by(scenes.c.scene_order)
        )
        with self.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt).fetchall()]

    def get_scene(self, project_id: str, scene_id: str) -> dict[str, Any] | None:
        return self.get_one(project_id, scene_id=scene_id)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def upsert_scene(self, project_id: str, values: dict[str, Any]) -> None:
        """Upsert a scene by scene_id. Auto-computes word_count from content."""
        if "content" in values:
            values["word_count"] = len(values["content"])
        now = _now()
        values.setdefault("created_at", now)
        values["updated_at"] = now
        self.upsert_by_keys(project_id, values, ("scene_id",))

    def delete_scene(self, project_id: str, scene_id: str) -> int:
        return self.delete_one(project_id, scene_id=scene_id)

    # ------------------------------------------------------------------
    # Reorder
    # ------------------------------------------------------------------

    def reorder_scenes(
        self, project_id: str, chapter_id: str, scene_ids: list[str],
    ) -> None:
        """Two-pass reorder: negative temporaries first to avoid UNIQUE conflicts."""
        now = _now()
        with self.connect() as conn:
            # Pass 1: shift all to negative scene_order
            for idx, sid in enumerate(scene_ids):
                conn.execute(
                    update(scenes)
                    .where(
                        and_(
                            scenes.c.scene_id == sid,
                            scenes.c.chapter_id == chapter_id,
                        )
                    )
                    .values(scene_order=-(idx + 1), updated_at=now)
                )
            # Pass 2: assign final positions
            for idx, sid in enumerate(scene_ids):
                conn.execute(
                    update(scenes)
                    .where(
                        and_(
                            scenes.c.scene_id == sid,
                            scenes.c.chapter_id == chapter_id,
                        )
                    )
                    .values(scene_order=idx)
                )

    # ------------------------------------------------------------------
    # Cross-chapter recent scenes
    # ------------------------------------------------------------------

    def get_recent_scenes(
        self,
        project_id: str,
        chapter_id: str,
        scene_order: int,
        count: int = 2,
    ) -> list[dict[str, Any]]:
        """Get *count* scenes before *scene_order*, crossing chapter boundaries if needed."""
        result: list[dict[str, Any]] = []

        with self.connect() as conn:
            # Scenes in current chapter before the given position
            rows = conn.execute(
                select(scenes)
                .where(
                    and_(
                        scenes.c.project_id == project_id,
                        scenes.c.chapter_id == chapter_id,
                        scenes.c.scene_order < scene_order,
                    )
                )
                .order_by(scenes.c.scene_order.desc())
                .limit(count)
            ).fetchall()
            result.extend(dict(r._mapping) for r in rows)

            if len(result) < count:
                # Find current chapter to get its chapter_order
                cur = conn.execute(
                    select(chapter_content).where(
                        and_(
                            chapter_content.c.project_id == project_id,
                            chapter_content.c.chapter_id == chapter_id,
                        )
                    ).limit(1)
                ).fetchone()

                if cur is not None:
                    # Find the previous chapter
                    prev = conn.execute(
                        select(chapter_content)
                        .where(
                            and_(
                                chapter_content.c.project_id == project_id,
                                chapter_content.c.chapter_order < cur.chapter_order,
                            )
                        )
                        .order_by(chapter_content.c.chapter_order.desc())
                        .limit(1)
                    ).fetchone()

                    if prev is not None:
                        remaining = count - len(result)
                        extra = conn.execute(
                            select(scenes)
                            .where(
                                and_(
                                    scenes.c.project_id == project_id,
                                    scenes.c.chapter_id == prev.chapter_id,
                                )
                            )
                            .order_by(scenes.c.scene_order.desc())
                            .limit(remaining)
                        ).fetchall()
                        result.extend(dict(r._mapping) for r in extra)

        # Return in chronological order
        result.reverse()
        return result

    # ------------------------------------------------------------------
    # Compilation
    # ------------------------------------------------------------------

    def compile_chapter_scenes(self, project_id: str, chapter_id: str) -> None:
        """Concatenate all scene contents by scene_order, update chapter_content."""
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
