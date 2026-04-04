"""
世界线状态存储。
项目会话保存在项目目录，混合档案等全局会话保存在独立全局空间。
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..models.project import ProjectManager
from ..models.worldline import WorldlineSession


class WorldStateStore:
    @property
    def projects_dir(self) -> str:
        return ProjectManager.PROJECTS_DIR

    @property
    def global_root(self) -> str:
        path = os.path.join(Config.UPLOAD_FOLDER, "system", "global_worldlines")
        os.makedirs(path, exist_ok=True)
        return path

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

    def save_session(self, container_dir: str, session: WorldlineSession) -> str:
        session.updated_at = datetime.now().isoformat()
        path = self._session_file(container_dir, session.session_id)
        with open(path, "w", encoding="utf-8") as file_obj:
            json.dump(session.to_dict(), file_obj, ensure_ascii=False, indent=2)
        self._upsert_index(container_dir, session)
        return path

    def load_session(
        self,
        session_id: str,
        project_id: Optional[str] = None,
        graph_id: Optional[str] = None,
    ) -> Optional[WorldlineSession]:
        for container_dir in self._candidate_containers(project_id, graph_id):
            path = os.path.join(container_dir, "worldlines", "sessions", session_id, "session.json")
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as file_obj:
                return WorldlineSession.from_dict(json.load(file_obj))
        return None

    def list_sessions(
        self,
        project_id: Optional[str] = None,
        graph_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        sessions: List[Dict[str, Any]] = []
        for container_dir in self._candidate_containers(project_id, graph_id):
            index_file = self._index_file(container_dir)
            if not os.path.exists(index_file):
                continue
            with open(index_file, "r", encoding="utf-8") as file_obj:
                sessions.extend(json.load(file_obj).get("sessions", []))
        sessions.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return sessions[:limit]

    def load_json_if_exists(self, container_dir: str, filename: str) -> Optional[Dict[str, Any]]:
        path = os.path.join(container_dir, filename)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as file_obj:
            return json.load(file_obj)

    def _candidate_containers(self, project_id: Optional[str], graph_id: Optional[str]) -> List[str]:
        if project_id:
            return [ProjectManager._get_project_dir(project_id)]
        if graph_id:
            containers = [self._graph_container(graph_id)]
            match_project = self._find_project_by_graph_id(graph_id)
            if match_project:
                containers.append(ProjectManager._get_project_dir(match_project.project_id))
            containers.append(self._mixed_container())
            return self._dedupe(containers)
        containers = self._project_containers() + self._global_containers()
        return self._dedupe(containers)

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

    def _find_project_by_graph_id(self, graph_id: str) -> Optional[Any]:
        for project in ProjectManager.list_projects(limit=1000):
            if project.graph_id == graph_id:
                return project
        return None

    def _worldlines_root(self, container_dir: str) -> str:
        path = os.path.join(container_dir, "worldlines")
        os.makedirs(path, exist_ok=True)
        return path

    def _sessions_root(self, container_dir: str) -> str:
        path = os.path.join(self._worldlines_root(container_dir), "sessions")
        os.makedirs(path, exist_ok=True)
        return path

    def _session_dir(self, container_dir: str, session_id: str) -> str:
        path = os.path.join(self._sessions_root(container_dir), session_id)
        os.makedirs(path, exist_ok=True)
        return path

    def _session_file(self, container_dir: str, session_id: str) -> str:
        return os.path.join(self._session_dir(container_dir, session_id), "session.json")

    def _index_file(self, container_dir: str) -> str:
        return os.path.join(self._worldlines_root(container_dir), "index.json")

    def _upsert_index(self, container_dir: str, session: WorldlineSession) -> None:
        index_file = self._index_file(container_dir)
        payload: Dict[str, Any] = {"sessions": []}
        if os.path.exists(index_file):
            with open(index_file, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)
        sessions = payload.get("sessions", [])
        record = {
            "session_id": session.session_id,
            "project_id": session.project_id,
            "graph_id": session.graph_id,
            "label": session.label,
            "simulation_goal": session.simulation_goal,
            "branch_count": session.branch_count,
            "session_scope": session.session_scope,
            "status": session.status,
            "source_archive_ids": session.source_archive_ids,
            "source_project_ids": session.source_project_ids,
            "source_archive_count": session.source_archive_count,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }
        for idx, item in enumerate(sessions):
            if item.get("session_id") != session.session_id:
                continue
            sessions[idx] = record
            break
        else:
            sessions.append(record)
        sessions.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        with open(index_file, "w", encoding="utf-8") as file_obj:
            json.dump({"sessions": sessions}, file_obj, ensure_ascii=False, indent=2)

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

    def _dedupe(self, values: List[str]) -> List[str]:
        seen = set()
        items: List[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            items.append(value)
        return items
