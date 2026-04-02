"""Preset CRUD service layer."""
import uuid
from .novel_db import NovelDB


class PresetService:
    def __init__(self):
        self.db = NovelDB()

    def list_presets(self, project_id: str = None) -> list:
        """List presets for a project (includes global presets)."""
        # Get project-level presets from novel.sqlite3
        project_presets = []
        if project_id:
            project_presets = self.db.list_presets(project_id)

        # Get global presets from platform.sqlite3
        global_presets = self._load_global_presets()

        # Merge: project presets first, then globals not already overridden
        project_ids = {p["preset_id"] for p in project_presets}
        merged = list(project_presets)
        for gp in global_presets:
            if gp["preset_id"] not in project_ids:
                merged.append(gp)
        return merged

    def create_preset(self, project_id: str, name: str, system_prompt: str,
                      description: str = "", is_default: int = 0) -> dict:
        preset_id = f"preset_{uuid.uuid4().hex[:12]}"
        self.db.create_preset(project_id, preset_id, name, system_prompt, description, is_default)
        return {"preset_id": preset_id, "name": name, "project_id": project_id}

    def update_preset(self, project_id: str, preset_id: str, **kwargs) -> dict:
        self.db.update_preset(project_id, preset_id, **kwargs)
        return {"preset_id": preset_id, "updated": True}

    def delete_preset(self, project_id: str, preset_id: str):
        self.db.delete_preset(project_id, preset_id)

    def _load_global_presets(self) -> list:
        """Load global presets from platform.sqlite3."""
        import os
        import sqlite3
        from ...config import Config

        db_path = os.path.join(Config.UPLOAD_FOLDER, "system", "llm_facility.sqlite3")
        if not os.path.exists(db_path):
            return []
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM writer_presets WHERE project_id IS NULL ORDER BY is_default DESC, name"
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []
