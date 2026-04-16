"""Agent 长期记忆存储。"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

from ....database import get_engine
from ....repositories.archive_repo import ArchiveRepository
from .store_support import event_row, memory_row, now_iso


class LongTermMemoryStore:
    """跨 session 长期记忆。"""

    def __init__(self, repo: Optional[ArchiveRepository] = None):
        self._repo = repo or ArchiveRepository(get_engine())

    def _resolve_project_id(self, archive_id: str, project_id: str = "") -> str:
        """Return *project_id*, falling back to the archive_library row."""
        if project_id:
            return project_id
        row = self._repo.get_archive(archive_id)
        return row["project_id"] if row else ""

    def append_candidate(
        self,
        archive_id: str,
        agent_id: str,
        memory_type: str,
        summary: str,
        detail: Dict[str, Any],
        source_kind: str,
        source_ref_id: str,
        normalized_subject: str,
        salience: float,
        source_session_id: str = "",
        source_branch_id: str = "",
        evidence: Optional[List[Dict[str, Any]]] = None,
        project_id: str = "",
    ) -> str:
        if not archive_id:
            raise ValueError("archive_id 不能为空")
        resolved_pid = self._resolve_project_id(archive_id, project_id)
        # Supersede existing active candidates for same subject
        targets = self._repo.find_active_supersede_targets(archive_id, memory_type, normalized_subject, ("candidate",))
        for row in targets:
            self._update_memory_status(row["memory_id"], "superseded", "supersede_active", row)
        memory_id = self._insert_memory(
            project_id=resolved_pid,
            archive_id=archive_id,
            agent_id=agent_id,
            memory_type=memory_type,
            summary=summary,
            detail=detail,
            source_kind=source_kind,
            source_ref_id=source_ref_id,
            normalized_subject=normalized_subject,
            salience=salience,
            memory_layer="candidate",
            status="active",
            parent_memory_id="",
            source_session_id=source_session_id,
            source_branch_id=source_branch_id,
            evidence=evidence or [],
        )
        return memory_id

    def promote_to_canon(self, archive_id: str, memory_id: str) -> Dict[str, Any]:
        candidate = self._repo.get_memory_by_archive(archive_id, memory_id)
        if not candidate:
            raise ValueError(f"候选记忆不存在: {memory_id}")
        if candidate["memory_layer"] != "candidate":
            raise ValueError("只能采纳 candidate 记忆")
        if candidate["status"] == "rejected":
            raise ValueError("candidate 记忆已被驳回，不能再次采纳")
        if candidate["status"] != "active":
            raise ValueError("candidate 记忆已被采纳或替换，不能重复采纳")
        # Supersede existing active canons
        targets = self._repo.find_active_supersede_targets(archive_id, candidate["memory_type"], candidate["normalized_subject"], ("canon",))
        for row in targets:
            self._update_memory_status(row["memory_id"], "superseded", "supersede_active", row)
        self._update_memory_status(candidate["memory_id"], "superseded", "candidate_adopted", candidate)
        canon_id = self._insert_memory(
            project_id=candidate.get("project_id", ""),
            archive_id=archive_id,
            agent_id=candidate["agent_id"],
            memory_type=candidate["memory_type"],
            summary=candidate["summary"],
            detail=json.loads(candidate["detail_json"] or "{}"),
            source_kind=candidate["source_kind"],
            source_ref_id=candidate["source_ref_id"],
            normalized_subject=candidate["normalized_subject"],
            salience=float(candidate["salience"] or 0.0),
            memory_layer="canon",
            status="active",
            parent_memory_id=candidate["memory_id"],
            source_session_id=candidate.get("source_session_id", ""),
            source_branch_id=candidate.get("source_branch_id", ""),
            evidence=json.loads(candidate["evidence_json"] or "[]"),
            adopted_at=now_iso(),
            event_type="promote_to_canon",
        )
        return self.list_memory(archive_id, canon_id)

    def reject_candidate(self, archive_id: str, memory_id: str) -> Dict[str, Any]:
        candidate = self._repo.get_memory_by_archive(archive_id, memory_id)
        if not candidate:
            raise ValueError(f"候选记忆不存在: {memory_id}")
        if candidate["memory_layer"] != "candidate":
            raise ValueError("只能驳回 candidate 记忆")
        if candidate["status"] == "rejected":
            raise ValueError("candidate 记忆已被驳回")
        if candidate["status"] != "active":
            raise ValueError("candidate 记忆已被采纳或替换，不能再驳回")
        self._update_memory_status(memory_id, "rejected", "reject_candidate", candidate, rejected_at=now_iso())
        return self.list_memory(archive_id, memory_id)

    def supersede_canon(self, archive_id: str, memory_id: str) -> Dict[str, Any]:
        memory = self._repo.get_memory_by_archive(archive_id, memory_id)
        if not memory:
            raise ValueError(f"长期记忆不存在: {memory_id}")
        self._update_memory_status(memory_id, "superseded", "supersede_canon", memory)
        return self.list_memory(archive_id, memory_id)

    def list_active_memories(
        self,
        archive_id: str,
        layers: Tuple[str, ...] = ("canon",),
        limit: int = 20,
        statuses: Tuple[str, ...] = ("active",),
    ) -> List[Dict[str, Any]]:
        if not archive_id:
            return []
        rows = self._repo.list_active_memory(archive_id, layers=layers, statuses=statuses, limit=max(1, min(limit, 100)))
        return [memory_row(row, "long_term") for row in rows]

    def list_memories(self, archive_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        return self.list_active_memories(archive_id, layers=("canon",), limit=limit)

    def list_memory_timeline(
        self,
        archive_id: str,
        memory_id: str = "",
        normalized_subject: str = "",
    ) -> Dict[str, Any]:
        subject = normalized_subject
        if memory_id and not subject:
            row = self._repo.get_memory_by_archive(archive_id, memory_id)
            if not row:
                raise ValueError(f"长期记忆不存在: {memory_id}")
            subject = row["normalized_subject"]
        if not subject:
            raise ValueError("请提供 memory_id 或 normalized_subject")
        memories = self._repo.list_memory_by_subject(archive_id, subject)
        events = self._repo.list_memory_events(archive_id, normalized_subject=subject)
        memory_payloads = [memory_row(row, "long_term") for row in memories]
        event_payloads = [event_row(row) for row in events]
        active_canon = next(
            (
                item for item in memory_payloads
                if item["memory_layer"] == "canon" and item["status"] == "active"
            ),
            None,
        )
        active_candidates = [
            item for item in memory_payloads
            if item["memory_layer"] == "candidate" and item["status"] == "active"
        ]
        return {
            "archive_id": archive_id,
            "subject": subject,
            "head_memories": memory_payloads[:3],
            "active_canon": active_canon,
            "active_candidates": active_candidates,
            "memories": memory_payloads,
            "events": event_payloads,
        }

    def list_memory(self, archive_id: str, memory_id: str) -> Dict[str, Any]:
        row = self._repo.get_memory_by_archive(archive_id, memory_id)
        if not row:
            raise ValueError(f"长期记忆不存在: {memory_id}")
        return memory_row(row, "long_term")

    def _insert_memory(self, **kwargs) -> str:
        now = now_iso()
        memory_id = f"ltm_{uuid.uuid4().hex[:16]}"
        version = self._repo.max_memory_version(kwargs["archive_id"], kwargs["memory_type"], kwargs["normalized_subject"]) + 1
        adopted_at = kwargs.get("adopted_at")
        event_type = kwargs.get("event_type", "append_candidate")
        pid = kwargs.get("project_id", "")
        self._repo.upsert_memory({
            "memory_id": memory_id,
            "project_id": pid,
            "archive_id": kwargs["archive_id"],
            "agent_id": kwargs["agent_id"],
            "memory_type": kwargs["memory_type"],
            "normalized_subject": kwargs["normalized_subject"],
            "summary": kwargs["summary"],
            "detail_json": json.dumps(kwargs["detail"], ensure_ascii=False),
            "source_kind": kwargs["source_kind"],
            "source_ref_id": kwargs["source_ref_id"],
            "salience": kwargs["salience"],
            "created_at": now,
            "updated_at": now,
            "memory_layer": kwargs["memory_layer"],
            "status": kwargs["status"],
            "version": version,
            "parent_memory_id": kwargs.get("parent_memory_id", ""),
            "source_session_id": kwargs.get("source_session_id", ""),
            "source_branch_id": kwargs.get("source_branch_id", ""),
            "evidence_json": json.dumps(kwargs.get("evidence") or [], ensure_ascii=False),
            "adopted_at": adopted_at,
            "rejected_at": None,
        })
        self._repo.log_memory_event({
            "event_id": f"evt_{uuid.uuid4().hex[:16]}",
            "project_id": pid,
            "memory_id": memory_id,
            "archive_id": kwargs["archive_id"],
            "normalized_subject": kwargs["normalized_subject"],
            "memory_type": kwargs["memory_type"],
            "event_type": event_type,
            "memory_layer": kwargs["memory_layer"],
            "status": kwargs["status"],
            "version": version,
            "parent_memory_id": kwargs.get("parent_memory_id", ""),
            "source_session_id": kwargs.get("source_session_id", ""),
            "source_branch_id": kwargs.get("source_branch_id", ""),
            "summary": kwargs["summary"],
            "evidence_json": json.dumps(kwargs.get("evidence") or [], ensure_ascii=False),
            "created_at": now,
        })
        return memory_id

    def _update_memory_status(
        self,
        memory_id: str,
        status: str,
        event_type: str,
        row: Dict[str, Any],
        rejected_at: Optional[str] = None,
    ) -> None:
        now = now_iso()
        self._repo.update_memory_status(memory_id, status, updated_at=now, rejected_at=rejected_at)
        self._repo.log_memory_event({
            "event_id": f"evt_{uuid.uuid4().hex[:16]}",
            "project_id": row.get("project_id", ""),
            "memory_id": memory_id,
            "archive_id": row["archive_id"],
            "normalized_subject": row["normalized_subject"],
            "memory_type": row["memory_type"],
            "event_type": event_type,
            "memory_layer": row["memory_layer"],
            "status": status,
            "version": int(row.get("version") or 1),
            "parent_memory_id": row.get("parent_memory_id", ""),
            "source_session_id": row.get("source_session_id", ""),
            "source_branch_id": row.get("source_branch_id", ""),
            "summary": row.get("summary", ""),
            "evidence_json": row.get("evidence_json", "[]"),
            "created_at": now,
        })
