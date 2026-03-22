"""全局主档案库服务。"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from ..models.project import ProjectManager
from .archive_library_storage import ArchiveLibraryStorage


SEARCH_FIELDS = (
    "entity_name",
    "entity_role",
    "core_drive",
    "hidden_tension",
    "relationship_summary",
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _bool_to_int(value: Any) -> int:
    return 1 if bool(value) else 0


def _archive_path(project_id: str) -> str:
    return ProjectManager._get_project_json_path(project_id, "narrative_archives.json")


def _row_to_archive(row) -> Dict[str, Any]:
    return {
        "archive_id": row["archive_id"],
        "project_id": row["project_id"],
        "project_name": row["project_name"],
        "entity_uuid": row["entity_uuid"],
        "entity_name": row["entity_name"],
        "entity_type": row["entity_type"],
        "importance_tier": row["importance_tier"],
        "entity_role": row["entity_role"],
        "core_drive": row["core_drive"],
        "surface_mask": row["surface_mask"],
        "hidden_tension": row["hidden_tension"],
        "relationship_summary": row["relationship_summary"],
        "agent_behavior_hint": row["agent_behavior_hint"],
        "human_ai_relation_tag": row["human_ai_relation_tag"],
        "can_act_as_agent": bool(row["can_act_as_agent"]),
        "notable_risks": json.loads(row["notable_risks"] or "[]"),
        "synced_at": row["synced_at"],
    }


class ArchiveLibraryService:
    """提供项目档案同步与全局检索能力。"""

    def __init__(self, storage: Optional[ArchiveLibraryStorage] = None):
        self.storage = storage or ArchiveLibraryStorage()

    @staticmethod
    def build_archive_id(project_id: str, entity_uuid: str) -> str:
        if not project_id or not entity_uuid:
            raise ValueError("project_id 和 entity_uuid 不能为空")
        digest = hashlib.sha1(f"{project_id}:{entity_uuid}".encode("utf-8")).hexdigest()[:16]
        return f"archive_{digest}"

    def list_archives(
        self,
        q: str = "",
        project_id: str = "",
        entity_type: str = "",
        importance_tier: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        self.sync_incremental()
        filters, params = self._search_filters(q, project_id, entity_type, importance_tier)
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        with self.storage.connect() as connection:
            count_sql = f"SELECT COUNT(*) AS total FROM archive_library WHERE {' AND '.join(filters)}"
            total = connection.execute(count_sql, params).fetchone()["total"]
            query_sql = f"""
                SELECT * FROM archive_library
                WHERE {' AND '.join(filters)}
                ORDER BY synced_at DESC, project_name ASC, entity_name ASC
                LIMIT ? OFFSET ?
            """
            rows = connection.execute(query_sql, [*params, limit, offset]).fetchall()
        items = [_row_to_archive(row) for row in rows]
        return {"items": items, "count": len(items), "total": total, "limit": limit, "offset": offset}

    def get_archive(self, archive_id: str) -> Dict[str, Any]:
        self.sync_incremental()
        with self.storage.connect() as connection:
            row = connection.execute(
                "SELECT * FROM archive_library WHERE archive_id = ?",
                (archive_id,),
            ).fetchone()
        if not row:
            raise ValueError(f"档案不存在: {archive_id}")
        return _row_to_archive(row)

    def resolve_archives(self, archive_ids: List[str]) -> List[Dict[str, Any]]:
        if not archive_ids:
            raise ValueError("请提供 archive_ids")
        self.sync_incremental()
        placeholders = ",".join("?" for _ in archive_ids)
        query = f"SELECT * FROM archive_library WHERE archive_id IN ({placeholders})"
        with self.storage.connect() as connection:
            rows = connection.execute(query, archive_ids).fetchall()
        records = {_row_to_archive(row)["archive_id"]: _row_to_archive(row) for row in rows}
        missing = [archive_id for archive_id in archive_ids if archive_id not in records]
        if missing:
            raise ValueError(f"以下档案不存在: {', '.join(missing)}")
        return [records[archive_id] for archive_id in archive_ids]

    def reindex(self) -> int:
        with self.storage.connect() as connection:
            connection.execute("DELETE FROM archive_library")
            connection.execute("DELETE FROM archive_sources")
            connection.commit()
        return self.sync_incremental(force=True)

    def sync_project_archives(self, project_id: str, force: bool = False) -> List[Dict[str, Any]]:
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")
        count = self._sync_projects([project], force=force)
        if count < 0:
            raise ValueError("档案同步失败")
        return self.list_archives(project_id=project_id, limit=500)["items"]

    def sync_incremental(self, force: bool = False) -> int:
        return self._sync_projects(self._iter_projects(), force=force)

    def _iter_projects(self) -> List[Any]:
        ProjectManager._ensure_projects_dir()
        projects: List[Any] = []
        for project_id in os.listdir(ProjectManager.PROJECTS_DIR):
            project = ProjectManager.get_project(project_id)
            if project:
                projects.append(project)
        return projects

    def _sync_projects(self, projects: Iterable[Any], force: bool) -> int:
        known_ids = set()
        synced = 0
        with self.storage.connect() as connection:
            for project in projects:
                path = _archive_path(project.project_id)
                known_ids.add(project.project_id)
                if not os.path.exists(path):
                    self._delete_project_records(connection, project.project_id)
                    continue
                file_mtime = os.path.getmtime(path)
                if not force and self._is_unchanged(connection, project.project_id, file_mtime):
                    continue
                payload = ProjectManager.load_project_json(project.project_id, "narrative_archives.json") or {}
                self._replace_project_archives(connection, project, payload, path, file_mtime)
            self._prune_deleted_sources(connection, known_ids)
            connection.commit()
            synced = connection.execute("SELECT COUNT(*) AS total FROM archive_library").fetchone()["total"]
        return synced

    def _search_filters(
        self,
        q: str,
        project_id: str,
        entity_type: str,
        importance_tier: str,
    ) -> tuple[List[str], List[Any]]:
        filters = ["1 = 1"]
        params: List[Any] = []
        if project_id:
            filters.append("project_id = ?")
            params.append(project_id)
        if entity_type:
            filters.append("entity_type = ?")
            params.append(entity_type)
        if importance_tier:
            filters.append("importance_tier = ?")
            params.append(importance_tier)
        if q.strip():
            keyword = f"%{q.strip()}%"
            clauses = [f"{field} LIKE ?" for field in SEARCH_FIELDS]
            filters.append(f"({' OR '.join(clauses)})")
            params.extend(keyword for _ in SEARCH_FIELDS)
        return filters, params

    def _replace_project_archives(
        self,
        connection,
        project: Any,
        payload: Dict[str, Any],
        file_path: str,
        file_mtime: float,
    ) -> None:
        archives = payload.get("archives")
        if not isinstance(archives, list):
            raise ValueError(f"{project.project_id} 的 narrative_archives.json 缺少 archives 列表")
        self._delete_project_records(connection, project.project_id)
        for archive in archives:
            entity_uuid = str(archive.get("entity_uuid") or "").strip()
            if not entity_uuid:
                raise ValueError(f"{project.project_id} 的档案缺少 entity_uuid")
            record = self._archive_record(project, archive)
            connection.execute(
                """
                INSERT INTO archive_library (
                    archive_id, project_id, project_name, entity_uuid, entity_name, entity_type,
                    importance_tier, entity_role, core_drive, surface_mask, hidden_tension,
                    relationship_summary, agent_behavior_hint, human_ai_relation_tag,
                    can_act_as_agent, notable_risks, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                record,
            )
        connection.execute(
            """
            INSERT INTO archive_sources (project_id, project_name, file_path, file_mtime, synced_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                project_name = excluded.project_name,
                file_path = excluded.file_path,
                file_mtime = excluded.file_mtime,
                synced_at = excluded.synced_at
            """,
            (project.project_id, project.name, file_path, file_mtime, _now()),
        )

    def _archive_record(self, project: Any, archive: Dict[str, Any]) -> tuple[Any, ...]:
        archive_id = self.build_archive_id(project.project_id, str(archive.get("entity_uuid")))
        return (
            archive_id,
            project.project_id,
            project.name,
            str(archive.get("entity_uuid") or ""),
            str(archive.get("entity_name") or ""),
            str(archive.get("entity_type") or ""),
            str(archive.get("importance_tier") or "supporting"),
            str(archive.get("entity_role") or ""),
            str(archive.get("core_drive") or ""),
            str(archive.get("surface_mask") or ""),
            str(archive.get("hidden_tension") or ""),
            str(archive.get("relationship_summary") or ""),
            str(archive.get("agent_behavior_hint") or ""),
            str(archive.get("human_ai_relation_tag") or "none"),
            _bool_to_int(archive.get("can_act_as_agent", True)),
            json.dumps(archive.get("notable_risks") or [], ensure_ascii=False),
            _now(),
        )

    def _is_unchanged(self, connection, project_id: str, file_mtime: float) -> bool:
        row = connection.execute(
            "SELECT file_mtime FROM archive_sources WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return bool(row) and float(row["file_mtime"]) >= float(file_mtime)

    def _delete_project_records(self, connection, project_id: str) -> None:
        connection.execute("DELETE FROM archive_library WHERE project_id = ?", (project_id,))
        connection.execute("DELETE FROM archive_sources WHERE project_id = ?", (project_id,))

    def _prune_deleted_sources(self, connection, project_ids: set[str]) -> None:
        rows = connection.execute("SELECT project_id FROM archive_sources").fetchall()
        for row in rows:
            project_id = row["project_id"]
            if project_id not in project_ids:
                self._delete_project_records(connection, project_id)
