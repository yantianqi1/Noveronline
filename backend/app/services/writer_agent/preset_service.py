"""Preset CRUD service layer."""
import uuid
from app.database import get_engine
from app.repositories.preset_repo import PresetRepository


class PresetService:
    def __init__(self):
        engine = get_engine()
        self._presets = PresetRepository(engine)

    def list_presets(self, project_id: str = None) -> list:
        """List presets for a project (includes global presets)."""
        if not project_id:
            return []
        # PresetRepository.list_presets already merges project + global presets
        return self._presets.list_presets(project_id)

    def create_preset(self, project_id: str, name: str, system_prompt: str,
                      description: str = "", is_default: int = 0) -> dict:
        preset_id = f"preset_{uuid.uuid4().hex[:12]}"
        self._presets.create_preset(
            project_id, preset_id,
            name=name, system_prompt=system_prompt,
            description=description, is_default=is_default,
        )
        return {"preset_id": preset_id, "name": name, "project_id": project_id}

    def update_preset(self, project_id: str, preset_id: str, **kwargs) -> dict:
        self._presets.update_preset(project_id, preset_id, **kwargs)
        return {"preset_id": preset_id, "updated": True}

    def delete_preset(self, project_id: str, preset_id: str):
        self._presets.delete_preset(project_id, preset_id)
