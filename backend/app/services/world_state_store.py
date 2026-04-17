"""
世界线状态存储。

Phase E (2026-04-17):
    Session 元数据（原 ``sessions/<sid>/session.json`` + ``index.json``）
    已迁入 ``worldline_sessions`` 表。本类的 ``save_session`` /
    ``load_session`` / ``list_sessions`` 都转调
    :class:`WorldlineSessionRepository`；``container_dir`` 参数保留是为
    了兼容引擎里现有的调用签名（以及 ``load_json_if_exists`` 仍读取
    项目目录下的其他 artefact 文件），但对 session 数据本身不再使用。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..models.project import ProjectManager
from ..models.worldline import WorldlineSession


class WorldStateStore:
    def __init__(self) -> None:
        self._repo = None

    @property
    def projects_dir(self) -> str:
        return ProjectManager.PROJECTS_DIR

    @property
    def global_root(self) -> str:
        path = os.path.join(Config.UPLOAD_FOLDER, "system", "global_worldlines")
        os.makedirs(path, exist_ok=True)
        return path

    # ------------------------------------------------------------------
    # Session persistence (DB-backed)
    # ------------------------------------------------------------------

    def _get_repo(self):
        """Lazy repo binding — keeps the store constructable before
        ``init_db()`` has ever run and always uses the current engine."""
        from ..database import get_engine
        from ..repositories.worldline_session_repo import WorldlineSessionRepository

        return WorldlineSessionRepository(get_engine())

    def save_session(self, container_dir: str, session: WorldlineSession) -> str:
        """Persist a session.

        ``container_dir`` is accepted for backward compatibility with
        callers in ``worldline_engine`` / ``worldline_event_service`` /
        ``worldline_prepare_service`` but is no longer read from or
        written to — all state is stored in ``worldline_sessions``.
        """
        del container_dir  # deprecated, unused
        self._get_repo().save_session(session.to_dict())
        return f"db:worldline_sessions/{session.session_id}"

    def load_session(
        self,
        session_id: str,
        project_id: Optional[str] = None,
        graph_id: Optional[str] = None,
    ) -> Optional[WorldlineSession]:
        """Load a session by id.

        ``project_id`` / ``graph_id`` hints are kept for signature
        compatibility; ``session_id`` is globally unique in the DB so
        they're no longer needed to disambiguate.
        """
        del project_id, graph_id
        payload = self._get_repo().load_session(session_id)
        if payload is None:
            return None
        return WorldlineSession.from_dict(payload)

    def list_sessions(
        self,
        project_id: Optional[str] = None,
        graph_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        return self._get_repo().list_sessions(project_id=project_id, graph_id=graph_id, limit=limit)

    # ------------------------------------------------------------------
    # Container resolution (still filesystem-based: used by other
    # worldline artefacts and for graph_id→project lookup)
    # ------------------------------------------------------------------

    def resolve_container(
        self,
        project_id: Optional[str],
        graph_id: str,
        session_scope: str = "project",
    ) -> Tuple[Optional[str], str]:
        if session_scope == "global":
            container_dir = self._mixed_container()
            return None, container_dir
        if project_id:
            project = ProjectManager.get_project(project_id)
            if not project:
                raise ValueError(f"项目不存在: {project_id}")
            container_dir = ProjectManager._get_project_dir(project_id)
            os.makedirs(container_dir, exist_ok=True)
            return project_id, container_dir
        match_project = self._find_project_by_graph_id(graph_id)
        if match_project:
            container_dir = ProjectManager._get_project_dir(match_project.project_id)
            os.makedirs(container_dir, exist_ok=True)
            return match_project.project_id, container_dir
        return None, self._graph_container(graph_id)

    def load_json_if_exists(self, container_dir: str, filename: str) -> Optional[Dict[str, Any]]:
        """Read an adjacent JSON artefact (non-session) from the project
        directory. Sessions are in the DB — this helper is for other
        files like ``seed_analysis.json`` / ``reading_notes.json`` / etc.
        that callers pass through ``resolve_container``'s returned path."""
        path = os.path.join(container_dir, filename)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as file_obj:
            return json.load(file_obj)

    # ------------------------------------------------------------------
    # Internal helpers retained for container path resolution
    # ------------------------------------------------------------------

    def _find_project_by_graph_id(self, graph_id: str) -> Optional[Any]:
        for project in ProjectManager.list_projects(limit=1000):
            if project.graph_id == graph_id:
                return project
        return None

    def _candidate_containers(self, project_id: Optional[str], graph_id: Optional[str]) -> List[str]:
        """Candidate filesystem directories when a caller still needs a
        path to read non-session artefacts (e.g. ``seed_analysis.json``)
        rather than a DB-backed session."""
        if project_id:
            return [ProjectManager._get_project_dir(project_id)]
        if graph_id:
            containers = [self._graph_container(graph_id)]
            match_project = self._find_project_by_graph_id(graph_id)
            if match_project:
                containers.append(ProjectManager._get_project_dir(match_project.project_id))
            containers.append(self._mixed_container())
            return self._dedupe(containers)
        return self._dedupe(self._project_containers() + self._global_containers())

    def _project_containers(self) -> List[str]:
        ProjectManager._ensure_projects_dir()
        return [
            os.path.join(self.projects_dir, item)
            for item in os.listdir(self.projects_dir)
            if os.path.isdir(os.path.join(self.projects_dir, item))
        ]

    def _global_containers(self) -> List[str]:
        containers = [self._mixed_container()]
        graphs_root = self._graphs_root()
        containers.extend(
            os.path.join(graphs_root, item)
            for item in os.listdir(graphs_root)
            if os.path.isdir(os.path.join(graphs_root, item))
        )
        return containers

    def _dedupe(self, values: List[str]) -> List[str]:
        seen: set[str] = set()
        items: List[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            items.append(value)
        return items

    def _mixed_container(self) -> str:
        path = os.path.join(self.global_root, "mixed")
        os.makedirs(path, exist_ok=True)
        return path

    def _graphs_root(self) -> str:
        path = os.path.join(self.global_root, "graphs")
        os.makedirs(path, exist_ok=True)
        return path

    def _graph_container(self, graph_id: str) -> str:
        safe_graph_id = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in graph_id)
        path = os.path.join(self._graphs_root(), safe_graph_id)
        os.makedirs(path, exist_ok=True)
        return path
