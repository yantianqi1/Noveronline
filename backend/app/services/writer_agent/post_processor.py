"""Post-processor: saves scene, updates chapter, optional consistency check."""

import json
import logging
from typing import Optional

from sqlalchemy import and_, select

from app.database import get_engine
from app.repositories.scene_repo import SceneRepository
from app.repositories.chapter_repo import ChapterRepository
from app.tables.novel import scenes as scenes_table

logger = logging.getLogger(__name__)


class PostProcessor:
    def __init__(self):
        engine = get_engine()
        self._engine = engine
        self._scenes = SceneRepository(engine)
        self._chapters = ChapterRepository(engine)

    def _resolve_scene_order(
        self, project_id: str, chapter_id: str, scene_id: str, requested_order: int,
    ) -> int:
        """Pick a safe scene_order for the incoming scene.

        If the caller's *scene_id* already exists (upsert path), keep the
        requested order. Otherwise, if the (chapter_id, scene_order) slot is
        taken by a different scene_id, shift this one to the end of the chapter
        so we don't collide with the UNIQUE(chapter_id, scene_order) constraint.
        This matters because the frontend defaults scene_order to 1 whenever
        no scene is selected, and pressing "生成" again after a previous run
        would otherwise crash with IntegrityError.
        """
        if not chapter_id:
            return requested_order
        with self._engine.connect() as conn:
            # If this scene_id already exists, upsert will update in place; keep the order.
            existing_self = conn.execute(
                select(scenes_table.c.scene_order).where(
                    and_(
                        scenes_table.c.project_id == project_id,
                        scenes_table.c.scene_id == scene_id,
                    )
                )
            ).fetchone()
            if existing_self is not None:
                return requested_order

            # Check whether the requested slot is free.
            slot_holder = conn.execute(
                select(scenes_table.c.scene_id).where(
                    and_(
                        scenes_table.c.project_id == project_id,
                        scenes_table.c.chapter_id == chapter_id,
                        scenes_table.c.scene_order == requested_order,
                    )
                )
            ).fetchone()
            if slot_holder is None:
                return requested_order

            # Slot is taken by a different scene — assign next free order.
            max_row = conn.execute(
                select(scenes_table.c.scene_order).where(
                    and_(
                        scenes_table.c.project_id == project_id,
                        scenes_table.c.chapter_id == chapter_id,
                    )
                ).order_by(scenes_table.c.scene_order.desc()).limit(1)
            ).fetchone()
            return (max_row[0] if max_row else 0) + 1

    def process(
        self,
        project_id: str,
        chapter_id: str,
        scene_order: int,
        scene_id: str,
        content: str,
        writing_brief: Optional[dict] = None,
        title: str = "",
        pov_entity_id: Optional[str] = None,
        location: Optional[str] = None,
        involved_entities_json: str = "[]",
    ) -> dict:
        """
        Save generated content as a scene and recompile the chapter.

        Returns:
            {"scene_id": str, "word_count": int, "warnings": []}
        """
        # Ensure chapter exists (auto-create if needed)
        if chapter_id:
            self._chapters.ensure_chapter(project_id, chapter_id)

        # Auto-resolve scene_order to avoid UNIQUE(chapter_id, scene_order) collision
        # when the frontend posts a default order that's already occupied.
        safe_order = self._resolve_scene_order(project_id, chapter_id, scene_id, scene_order)

        # Save the scene
        self._scenes.upsert_scene(
            project_id=project_id,
            values={
                "scene_id": scene_id,
                "chapter_id": chapter_id,
                "scene_order": safe_order,
                "title": title,
                "content": content,
                "pov_entity_id": pov_entity_id,
                "location": location,
                "involved_entities_json": involved_entities_json,
                "status": "draft",
                "writing_brief_json": json.dumps(writing_brief, ensure_ascii=False) if writing_brief else None,
            },
        )

        # Recompile chapter content from all scenes
        self._chapters.compile_chapter(project_id, chapter_id)

        word_count = len(content)

        return {
            "scene_id": scene_id,
            "scene_order": safe_order,
            "word_count": word_count,
            "warnings": [],
        }
