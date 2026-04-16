"""全局主档案库服务。"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from ..database import get_engine
from ..models.project import ProjectManager
from ..repositories.archive_repo import ArchiveRepository


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


def _row_to_archive(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "archive_id": row["archive_id"],
        "project_id": row["project_id"],
        "project_name": row["project_name"],
        "entity_uuid": row["entity_uuid"],
        "entity_name": row["entity_name"],
        "entity_type": row["entity_type"],
        "agent_kind": row["agent_kind"],
        "importance_tier": row["importance_tier"],
        "recommended_importance_tier": row["recommended_importance_tier"],
        "selected_importance_tier": row["selected_importance_tier"],
        "template_key": row["template_key"],
        "template_version": row["template_version"],
        "entity_role": row["entity_role"],
        "core_drive": row["core_drive"],
        "surface_mask": row["surface_mask"],
        "hidden_tension": row["hidden_tension"],
        "relationship_summary": row["relationship_summary"],
        "agent_behavior_hint": row["agent_behavior_hint"],
        "human_ai_relation_tag": row["human_ai_relation_tag"],
        "can_act_as_agent": bool(row["can_act_as_agent"]),
        "notable_risks": json.loads(row["notable_risks_json"] or "[]"),
        "template_sections": json.loads(row["template_sections_json"] or "[]"),
        "template_payload": json.loads(row["template_payload_json"] or "{}"),
        "template_metadata": json.loads(row["template_metadata_json"] or "{}"),
        "synced_at": row["synced_at"],
    }


class ArchiveLibraryService:
    """提供项目档案同步与全局检索能力。"""

    def __init__(self, repo: Optional[ArchiveRepository] = None):
        self._repo = repo or ArchiveRepository(get_engine())

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
        agent_kind: str = "",
        importance_tier: str = "",
        template_key: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        self.sync_incremental()
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        if q.strip():
            # Use the repo's search_archives for keyword filtering,
            # then apply remaining facet filters in Python.
            all_results = self._repo.search_archives(
                q.strip(),
                project_id=project_id or None,
                limit=500,
            )
            # Apply additional filters not supported by search_archives
            filtered = all_results
            if entity_type:
                filtered = [r for r in filtered if r.get("entity_type") == entity_type]
            if agent_kind:
                filtered = [r for r in filtered if r.get("agent_kind") == agent_kind]
            if importance_tier:
                filtered = [r for r in filtered if r.get("importance_tier") == importance_tier]
            if template_key:
                filtered = [r for r in filtered if r.get("template_key") == template_key]
            total = len(filtered)
            page = filtered[offset:offset + limit]
            items = [_row_to_archive(row) for row in page]
        else:
            total = self._repo.count_archives(
                project_id=project_id or None,
                entity_type=entity_type or None,
                importance_tier=importance_tier or None,
                agent_kind=agent_kind or None,
                template_key=template_key or None,
            )
            rows = self._repo.list_archives(
                project_id=project_id or None,
                entity_type=entity_type or None,
                importance_tier=importance_tier or None,
                agent_kind=agent_kind or None,
                template_key=template_key or None,
                limit=limit,
                offset=offset,
            )
            items = [_row_to_archive(row) for row in rows]
        return {"items": items, "count": len(items), "total": total, "limit": limit, "offset": offset}

    def get_archive(self, archive_id: str) -> Dict[str, Any]:
        self.sync_incremental()
        row = self._repo.get_archive(archive_id)
        if not row:
            raise ValueError(f"档案不存在: {archive_id}")
        return _row_to_archive(row)

    def resolve_archives(self, archive_ids: List[str]) -> List[Dict[str, Any]]:
        if not archive_ids:
            raise ValueError("请提供 archive_ids")
        self.sync_incremental()
        rows = self._repo.resolve_archives(archive_ids)
        records = {_row_to_archive(r)["archive_id"]: _row_to_archive(r) for r in rows}
        missing = [archive_id for archive_id in archive_ids if archive_id not in records]
        if missing:
            raise ValueError(f"以下档案不存在: {', '.join(missing)}")
        return [records[archive_id] for archive_id in archive_ids]

    def reindex(self) -> int:
        # Delete all archives and sources, then resync
        for source in self._repo.list_sources():
            self._repo.delete_archives_by_project(source["project_id"])
            self._repo.delete_source(source["project_id"])
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
        for project in projects:
            path = _archive_path(project.project_id)
            known_ids.add(project.project_id)
            if not os.path.exists(path):
                self._delete_project_records(project.project_id)
                continue
            file_mtime = os.path.getmtime(path)
            if not force and self._is_unchanged(project.project_id, file_mtime):
                continue
            payload = ProjectManager.load_project_json(project.project_id, "narrative_archives.json") or {}
            self._replace_project_archives(project, payload, path, file_mtime)
        self._prune_deleted_sources(known_ids)
        return self._repo.count_archives()

    def _replace_project_archives(
        self,
        project: Any,
        payload: Dict[str, Any],
        file_path: str,
        file_mtime: float,
    ) -> None:
        archives = payload.get("archives")
        if not isinstance(archives, list):
            raise ValueError(f"{project.project_id} 的 narrative_archives.json 缺少 archives 列表")
        self._delete_project_records(project.project_id)
        for archive in archives:
            entity_uuid = str(archive.get("entity_uuid") or "").strip()
            if not entity_uuid:
                raise ValueError(f"{project.project_id} 的档案缺少 entity_uuid")
            record = self._archive_record(project, archive)
            self._repo.upsert_archive(record)
        self._repo.upsert_source({
            "project_id": project.project_id,
            "project_name": project.name,
            "file_path": file_path,
            "file_mtime": file_mtime,
            "synced_at": _now(),
        })

    def _archive_record(self, project: Any, archive: Dict[str, Any]) -> Dict[str, Any]:
        archive_id = self.build_archive_id(project.project_id, str(archive.get("entity_uuid")))
        return {
            "archive_id": archive_id,
            "project_id": project.project_id,
            "project_name": project.name,
            "entity_uuid": str(archive.get("entity_uuid") or ""),
            "entity_name": str(archive.get("entity_name") or ""),
            "entity_type": str(archive.get("entity_type") or ""),
            "agent_kind": str(archive.get("agent_kind") or "generic"),
            "importance_tier": str(archive.get("importance_tier") or "supporting"),
            "recommended_importance_tier": str(archive.get("recommended_importance_tier") or archive.get("importance_tier") or "supporting"),
            "selected_importance_tier": str(archive.get("selected_importance_tier") or archive.get("importance_tier") or "supporting"),
            "template_key": str(archive.get("template_key") or "generic.supporting.v1"),
            "template_version": str(archive.get("template_version") or "v1"),
            "entity_role": str(archive.get("entity_role") or ""),
            "core_drive": str(archive.get("core_drive") or ""),
            "surface_mask": str(archive.get("surface_mask") or ""),
            "hidden_tension": str(archive.get("hidden_tension") or ""),
            "relationship_summary": str(archive.get("relationship_summary") or ""),
            "agent_behavior_hint": str(archive.get("agent_behavior_hint") or ""),
            "human_ai_relation_tag": str(archive.get("human_ai_relation_tag") or "none"),
            "can_act_as_agent": _bool_to_int(archive.get("can_act_as_agent", True)),
            "notable_risks_json": json.dumps(archive.get("notable_risks") or [], ensure_ascii=False),
            "template_sections_json": json.dumps(archive.get("template_sections") or [], ensure_ascii=False),
            "template_payload_json": json.dumps(archive.get("template_payload") or {}, ensure_ascii=False),
            "template_metadata_json": json.dumps(archive.get("template_metadata") or {}, ensure_ascii=False),
            "synced_at": _now(),
        }

    def _is_unchanged(self, project_id: str, file_mtime: float) -> bool:
        source = self._repo.get_source(project_id)
        return bool(source) and float(source["file_mtime"]) >= float(file_mtime)

    def _delete_project_records(self, project_id: str) -> None:
        self._repo.delete_archives_by_project(project_id)
        self._repo.delete_source(project_id)

    def _prune_deleted_sources(self, project_ids: set[str]) -> None:
        for source in self._repo.list_sources():
            if source["project_id"] not in project_ids:
                self._delete_project_records(source["project_id"])
