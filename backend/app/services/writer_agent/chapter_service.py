"""Chapter CRUD service layer."""
import uuid
from .novel_db import NovelDB


class ChapterService:
    def __init__(self):
        self.db = NovelDB()

    def list_chapters(self, project_id: str) -> list:
        return self.db.list_chapters(project_id)

    def create_chapter(self, project_id: str, title: str, chapter_order: int = None) -> dict:
        chapter_id = f"ch_{uuid.uuid4().hex[:12]}"
        if chapter_order is None:
            chapters = self.db.list_chapters(project_id)
            chapter_order = max((c["chapter_order"] for c in chapters), default=0) + 1
        self.db.create_chapter(project_id, chapter_id, chapter_order, title)
        return {"chapter_id": chapter_id, "chapter_order": chapter_order, "title": title}

    def update_chapter(self, project_id: str, chapter_id: str, **kwargs) -> dict:
        self.db.update_chapter(project_id, chapter_id, **kwargs)
        return {"chapter_id": chapter_id, "updated": True}

    def delete_chapter(self, project_id: str, chapter_id: str):
        self.db.delete_chapter(project_id, chapter_id)
