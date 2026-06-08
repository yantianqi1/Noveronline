"""项目持久化管理。"""

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
    def _get_project_files_dir(cls, project_id: str) -> str:
        return os.path.join(cls._get_project_dir(project_id), "files")

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
        _save_project_to_db(project)

    @classmethod
    def save_project_setting(cls, project_id: str, key: str, payload: Any) -> None:
        project = cls.get_project(project_id)
        if project is None:
            raise ValueError(f"项目不存在: {project_id}")
        project.settings[key] = payload
        cls.save_project(project)

    @classmethod
    def load_project_setting(cls, project_id: str, key: str) -> Optional[Any]:
        project = cls.get_project(project_id)
        if project is None or not isinstance(project.settings, dict):
            return None
        return project.settings.get(key)

    @classmethod
    def get_project(cls, project_id: str) -> Optional[Project]:
        payload = _load_project_from_db(project_id)
        if payload is None:
            return None
        return Project.from_dict(payload)

    @classmethod
    def list_projects(cls, limit: int = 50) -> List[Project]:
        projects = [Project.from_dict(payload) for payload in _list_projects_from_db(limit=limit)]
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
        deleted_rows = _delete_project_from_db(project_id)
        deleted_files = False
        if os.path.exists(project_dir):
            shutil.rmtree(project_dir)
            deleted_files = True
        return bool(deleted_rows or deleted_files)

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
        _save_extracted_text_to_db(project_id, text)

    @classmethod
    def get_extracted_text(cls, project_id: str) -> Optional[str]:
        payload = _load_artifact_from_db(project_id, "extracted_text")
        return payload if isinstance(payload, str) else None

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
        """DEPRECATED name for DB-only project artifact writes.

        New callers should use :meth:`save_project_artifact`. The legacy
        filename is accepted for API compatibility, but no filesystem JSON
        is written; legacy file imports belong in migration/import tools.
        """
        _mirror_artifact_to_db(project_id, filename, payload)
        _mirror_archive_library_to_db(project_id, filename, payload)
        return f"db://project_artifacts/{project_id}/{_artifact_key_from_filename(filename)}"

    @classmethod
    def save_project_artifact(cls, project_id: str, filename: str, payload: Any) -> None:
        """DB-only persist of a project artifact (Phase G final cut).

        Writes ``payload`` to ``project_artifacts`` keyed by
        ``(project_id, artifact_key_from_filename(filename))``. Does not
        touch the filesystem — runtime readers all go through
        ``load_project_artifact`` / ``load_project_json`` as DB-only
        accessors, so disk copies are no longer needed.

        ``filename`` may be either a legacy filename (``"seed_analysis.json"``)
        or a bare artifact key (``"seed_analysis"``).
        """
        _mirror_artifact_to_db(project_id, filename, payload)

    @classmethod
    def load_project_json(cls, project_id: str, filename: str) -> Optional[Dict[str, Any]]:
        return _load_artifact_from_db(project_id, filename)


def _mirror_artifact_to_db(project_id: str, filename: str, payload: Any) -> None:
    """Mirror a per-project JSON artifact into ``project_artifacts``.

    Writes the payload keyed by ``(project_id, artifact_key)`` so runtime
    services can read from the unified DB instead of the filesystem.
    ``get_engine()`` auto-initializes on first call if the app hasn't run
    ``init_db()`` yet, so this path works both in production and in the
    standalone unit tests that call ``save_project_json`` without an app.
    """
    from ..database import get_engine
    from ..repositories.project_artifact_repo import (
        ProjectArtifactRepository,
        artifact_key_from_filename,
    )

    engine = get_engine()
    ProjectArtifactRepository(engine).save(
        project_id, artifact_key_from_filename(filename), payload,
    )


def _artifact_key_from_filename(filename: str) -> str:
    from ..repositories.project_artifact_repo import artifact_key_from_filename

    return artifact_key_from_filename(filename)


def _save_project_to_db(project: Project) -> None:
    from ..database import get_engine
    from ..repositories.meta_repo import MetaRepository

    MetaRepository(get_engine()).save_project_payload(project.project_id, project.to_dict())


def _load_project_from_db(project_id: str) -> Optional[Dict[str, Any]]:
    from ..database import get_engine
    from ..repositories.meta_repo import MetaRepository

    return MetaRepository(get_engine()).load_project_payload(project_id)


def _list_projects_from_db(limit: int = 50) -> List[Dict[str, Any]]:
    from ..database import get_engine
    from ..repositories.meta_repo import MetaRepository

    return MetaRepository(get_engine()).list_project_payloads(limit=limit)


def _delete_project_from_db(project_id: str) -> int:
    from ..database import get_engine
    from ..repositories.meta_repo import MetaRepository

    return MetaRepository(get_engine()).delete_project_payload(project_id)


def _save_extracted_text_to_db(project_id: str, text: str) -> None:
    _mirror_artifact_to_db(project_id, "extracted_text", text)


def _load_artifact_from_db(project_id: str, filename: str) -> Optional[Any]:
    """Load a per-project JSON artifact from ``project_artifacts`` if present."""
    from ..database import get_engine
    from ..repositories.project_artifact_repo import (
        ProjectArtifactRepository,
        artifact_key_from_filename,
    )

    engine = get_engine()
    return ProjectArtifactRepository(engine).load(
        project_id, artifact_key_from_filename(filename),
    )


def _mirror_archive_library_to_db(project_id: str, filename: str, payload: Any) -> None:
    """Preserve legacy narrative archive writes while keeping DB as read source."""
    if filename != "narrative_archives.json":
        return
    if not isinstance(payload, dict):
        raise ValueError("narrative_archives.json payload 必须是对象")
    from ..services.archive_library_service import ArchiveLibraryService

    ArchiveLibraryService().write_archives_for_project(project_id, payload)


__all__ = ["Project", "ProjectManager", "ProjectStatus"]
