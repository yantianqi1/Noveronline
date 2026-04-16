"""Post-processor: saves scene, updates chapter, optional consistency check."""

import json
import logging
from typing import Optional

from app.database import get_engine
from app.repositories.scene_repo import SceneRepository
from app.repositories.chapter_repo import ChapterRepository

logger = logging.getLogger(__name__)


class PostProcessor:
    def __init__(self):
        engine = get_engine()
        self._scenes = SceneRepository(engine)
        self._chapters = ChapterRepository(engine)

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

        # Save the scene
        self._scenes.upsert_scene(
            project_id=project_id,
            values={
                "scene_id": scene_id,
                "chapter_id": chapter_id,
                "scene_order": scene_order,
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
            "word_count": word_count,
            "warnings": [],
        }
