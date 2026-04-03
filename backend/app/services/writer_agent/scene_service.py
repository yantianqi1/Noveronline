"""Scene CRUD service layer."""
import uuid
from .novel_db import NovelDB


class SceneService:
    def __init__(self):
        self.db = NovelDB()

    def list_scenes(self, project_id: str, chapter_id: str) -> list:
        return self.db.list_scenes(project_id, chapter_id)

    def get_scene(self, project_id: str, scene_id: str) -> dict:
        return self.db.get_scene(project_id, scene_id)

    def update_scene(self, project_id: str, scene_id: str, content: str = None, title: str = None) -> dict:
        scene = self.db.get_scene(project_id, scene_id)
        if not scene:
            raise ValueError(f"场景不存在: {scene_id}")
        self.db.upsert_scene(
            project_id=project_id,
            scene_id=scene_id,
            chapter_id=scene["chapter_id"],
            scene_order=scene["scene_order"],
            title=title if title is not None else scene["title"],
            content=content if content is not None else scene["content"],
            pov_entity_id=scene.get("pov_entity_id"),
            location=scene.get("location"),
            involved_entities_json=scene.get("involved_entities_json", "[]"),
            status=scene.get("status", "draft"),
            writing_brief_json=scene.get("writing_brief_json"),
        )
        return self.db.get_scene(project_id, scene_id)

    def delete_scene(self, project_id: str, scene_id: str):
        self.db.delete_scene(project_id, scene_id)

    def reorder_scenes(self, project_id: str, chapter_id: str, scene_ids: list):
        self.db.reorder_scenes(project_id, chapter_id, scene_ids)

    def compile_chapter(self, project_id: str, chapter_id: str) -> dict:
        self.db.compile_chapter(project_id, chapter_id)
        # Return updated chapter
        # Need to find chapter_order from chapter_id
        with self.db.connect(project_id) as conn:
            row = conn.execute(
                "SELECT chapter_order FROM chapter_content WHERE chapter_id = ?",
                (chapter_id,)
            ).fetchone()
        if row:
            return self.db.get_chapter(project_id, row["chapter_order"], include_content=True)
        return {}
