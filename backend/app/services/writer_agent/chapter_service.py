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
        # Snapshot old outline before overwriting
        outline_label = kwargs.pop("outline_label", "")
        if "outline_json" in kwargs:
            ch = self.db.get_chapter_by_id(project_id, chapter_id)
            old_outline = (ch or {}).get("outline_json", "[]")
            if old_outline and (old_outline != "[]" or outline_label):
                self.db.save_outline_version(project_id, chapter_id, old_outline, label=outline_label)
        self.db.update_chapter(project_id, chapter_id, **kwargs)
        return {"chapter_id": chapter_id, "updated": True}

    def delete_chapter(self, project_id: str, chapter_id: str):
        self.db.delete_chapter(project_id, chapter_id)

    def list_outline_versions(self, project_id: str, chapter_id: str) -> list:
        return self.db.list_outline_versions(project_id, chapter_id)

    def restore_outline_version(self, project_id: str, chapter_id: str, version_id: str) -> dict:
        target = self.db.get_outline_version(project_id, version_id)
        if not target:
            raise ValueError(f"Version {version_id} not found")
        # Snapshot current value before restoring
        ch = self.db.get_chapter_by_id(project_id, chapter_id)
        current_outline = (ch or {}).get("outline_json", "[]")
        if current_outline and current_outline != "[]":
            self.db.save_outline_version(project_id, chapter_id, current_outline, label="回退前快照")
        self.db.update_chapter(project_id, chapter_id, outline_json=target["outline_json"])
        return {"chapter_id": chapter_id, "restored_version_id": version_id}
