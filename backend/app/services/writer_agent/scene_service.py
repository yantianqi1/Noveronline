"""Scene CRUD service layer."""
from __future__ import annotations

import uuid

from app.database import get_engine
from app.repositories.scene_repo import SceneRepository
from app.repositories.chapter_repo import ChapterRepository


class SceneService:
    def __init__(self):
        engine = get_engine()
        self._scenes = SceneRepository(engine)
        self._chapters = ChapterRepository(engine)

    def list_scenes(self, project_id: str, chapter_id: str) -> list:
        return self._scenes.list_scenes(project_id, chapter_id)

    def get_scene(self, project_id: str, scene_id: str) -> dict:
        return self._scenes.get_scene(project_id, scene_id)

    def create_scene(
        self,
        project_id: str,
        chapter_id: str,
        *,
        title: str = "",
        content: str = "",
        scene_order: int | None = None,
        pov_entity_id: str | None = None,
        location: str | None = None,
        involved_entities_json: str = "[]",
        status: str = "draft",
        writing_brief_json: str | None = None,
    ) -> dict:
        """Create a new scene under a chapter. Auto-assigns MAX(scene_order)+1 if omitted."""
        if scene_order is None:
            existing = self._scenes.list_scenes(project_id, chapter_id)
            scene_order = max((int(s.get("scene_order") or 0) for s in existing), default=0) + 1
        scene_id = f"sc_{uuid.uuid4().hex[:12]}"
        self._scenes.upsert_scene(
            project_id=project_id,
            values={
                "scene_id": scene_id,
                "chapter_id": chapter_id,
                "scene_order": int(scene_order),
                "title": title,
                "content": content,
                "pov_entity_id": pov_entity_id,
                "location": location,
                "involved_entities_json": involved_entities_json,
                "status": status,
                "writing_brief_json": writing_brief_json,
            },
        )
        return self._scenes.get_scene(project_id, scene_id) or {"scene_id": scene_id}

    def update_scene(self, project_id: str, scene_id: str, content: str = None, title: str = None) -> dict:
        scene = self._scenes.get_scene(project_id, scene_id)
        if not scene:
            raise ValueError(f"场景不存在: {scene_id}")
        self._scenes.upsert_scene(
            project_id=project_id,
            values={
                "scene_id": scene_id,
                "chapter_id": scene["chapter_id"],
                "scene_order": scene["scene_order"],
                "title": title if title is not None else scene["title"],
                "content": content if content is not None else scene["content"],
                "pov_entity_id": scene.get("pov_entity_id"),
                "location": scene.get("location"),
                "involved_entities_json": scene.get("involved_entities_json", "[]"),
                "status": scene.get("status", "draft"),
                "writing_brief_json": scene.get("writing_brief_json"),
            },
        )
        return self._scenes.get_scene(project_id, scene_id)

    def delete_scene(self, project_id: str, scene_id: str):
        self._scenes.delete_scene(project_id, scene_id)

    def reorder_scenes(self, project_id: str, chapter_id: str, scene_ids: list):
        self._scenes.reorder_scenes(project_id, chapter_id, scene_ids)

    def compile_chapter(self, project_id: str, chapter_id: str) -> dict:
        self._chapters.compile_chapter(project_id, chapter_id)
        # Return updated chapter
        ch = self._chapters.get_chapter(project_id, chapter_id, include_content=True)
        return ch or {}
