"""项目持久化管理。"""

import json
import os
import shutil
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..config import Config
from .project_types import Project, ProjectStatus


class ProjectManager:
    PROJECTS_DIR = os.path.join(Config.UPLOAD_FOLDER, "projects")

    @classmethod
    def _ensure_projects_dir(cls) -> None:
        os.makedirs(cls.PROJECTS_DIR, exist_ok=True)

    @classmethod
    def _get_project_dir(cls, project_id: str) -> str:
        return os.path.join(cls.PROJECTS_DIR, project_id)

    @classmethod
    def _get_project_meta_path(cls, project_id: str) -> str:
        return os.path.join(cls._get_project_dir(project_id), "project.json")

    @classmethod
    def _get_project_files_dir(cls, project_id: str) -> str:
        return os.path.join(cls._get_project_dir(project_id), "files")

    @classmethod
    def _get_project_text_path(cls, project_id: str) -> str:
        return os.path.join(cls._get_project_dir(project_id), "extracted_text.txt")

    @classmethod
    def _get_project_json_path(cls, project_id: str, filename: str) -> str:
        return os.path.join(cls._get_project_dir(project_id), filename)

    @classmethod
    def create_project(cls, name: str = "Unnamed Project") -> Project:
        cls._ensure_projects_dir()
        project_id = f"proj_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        project = Project(
            project_id=project_id,
            name=name,
            status=ProjectStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
        os.makedirs(cls._get_project_dir(project_id), exist_ok=True)
        os.makedirs(cls._get_project_files_dir(project_id), exist_ok=True)
        cls.save_project(project)
        return project

    @classmethod
    def save_project(cls, project: Project) -> None:
        project.updated_at = datetime.now().isoformat()
        with open(cls._get_project_meta_path(project.project_id), "w", encoding="utf-8") as file_obj:
            json.dump(project.to_dict(), file_obj, ensure_ascii=False, indent=2)

    @classmethod
    def get_project(cls, project_id: str) -> Optional[Project]:
        meta_path = cls._get_project_meta_path(project_id)
        if not os.path.exists(meta_path):
            return None
        with open(meta_path, "r", encoding="utf-8") as file_obj:
            return Project.from_dict(json.load(file_obj))

    @classmethod
    def list_projects(cls, limit: int = 50) -> List[Project]:
        cls._ensure_projects_dir()
        projects = [project for project_id in os.listdir(cls.PROJECTS_DIR) if (project := cls.get_project(project_id))]
        projects.sort(key=lambda item: item.created_at, reverse=True)
        return projects[:limit]

    @classmethod
    def find_project_by_task_id(cls, task_id: str) -> Optional[Project]:
        if not task_id:
            return None
        for project in cls.list_projects(limit=500):
            if task_id in {project.seed_task_id, project.graph_build_task_id}:
                return project
        return None

    @classmethod
    def delete_project(cls, project_id: str) -> bool:
        project_dir = cls._get_project_dir(project_id)
        if not os.path.exists(project_dir):
            return False
        shutil.rmtree(project_dir)
        return True

    @classmethod
    def save_file_to_project(cls, project_id: str, file_storage, original_filename: str) -> Dict[str, str]:
        files_dir = cls._get_project_files_dir(project_id)
        os.makedirs(files_dir, exist_ok=True)
        extension = os.path.splitext(original_filename)[1].lower()
        saved_filename = f"{uuid.uuid4().hex[:8]}{extension}"
        path = os.path.join(files_dir, saved_filename)
        file_storage.save(path)
        return {
            "original_filename": original_filename,
            "saved_filename": saved_filename,
            "path": path,
            "size": os.path.getsize(path),
        }

    @classmethod
    def save_extracted_text(cls, project_id: str, text: str) -> None:
        with open(cls._get_project_text_path(project_id), "w", encoding="utf-8") as file_obj:
            file_obj.write(text)

    @classmethod
    def get_extracted_text(cls, project_id: str) -> Optional[str]:
        text_path = cls._get_project_text_path(project_id)
        if not os.path.exists(text_path):
            return None
        with open(text_path, "r", encoding="utf-8") as file_obj:
            return file_obj.read()

    @classmethod
    def get_project_files(cls, project_id: str) -> List[str]:
        files_dir = cls._get_project_files_dir(project_id)
        if not os.path.exists(files_dir):
            return []
        return [
            os.path.join(files_dir, filename)
            for filename in os.listdir(files_dir)
            if os.path.isfile(os.path.join(files_dir, filename))
        ]

    @classmethod
    def save_project_json(cls, project_id: str, filename: str, payload: Dict[str, Any]) -> str:
        path = cls._get_project_json_path(project_id, filename)
        with open(path, "w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False, indent=2)
        return path

    @classmethod
    def load_project_json(cls, project_id: str, filename: str) -> Optional[Dict[str, Any]]:
        path = cls._get_project_json_path(project_id, filename)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as file_obj:
            return json.load(file_obj)


__all__ = ["Project", "ProjectManager", "ProjectStatus"]
