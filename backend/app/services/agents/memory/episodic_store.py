"""Agent session 级经验记忆存储。"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from ....database import get_engine
from ....repositories.worldline_runtime_repo import WorldlineRuntimeRepository
from .store_support import memory_row, now_iso


class EpisodicMemoryStore:
    """session / branch 级经验记忆。"""

    def __init__(self, repo: Optional[WorldlineRuntimeRepository] = None):
        self._repo = repo or WorldlineRuntimeRepository(get_engine())

    def insert(
        self,
        container_dir: str,
        session_id: str,
        branch_id: str,
        agent_id: str,
        archive_id: str,
        memory_type: str,
        summary: str,
        detail: Dict[str, Any],
        source_kind: str,
        source_ref_id: str,
        normalized_subject: str,
        salience: float,
        project_id: str = "",
    ) -> str:
        memory_id = f"mem_{uuid.uuid4().hex[:16]}"
        created_at = now_iso()
        self._repo.save_episodic_memory({
            "memory_id": memory_id,
            "project_id": project_id,
            "session_id": session_id,
            "branch_id": branch_id,
            "agent_id": agent_id,
            "archive_id": archive_id or "",
            "memory_type": memory_type,
            "summary": summary,
            "detail_json": json.dumps(detail, ensure_ascii=False),
            "source_kind": source_kind,
            "source_ref_id": source_ref_id,
            "normalized_subject": normalized_subject,
            "salience": salience,
            "created_at": created_at,
            "updated_at": created_at,
        })
        return memory_id

    def list_memories(
        self,
        container_dir: str,
        session_id: str,
        branch_id: str,
        agent_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        rows = self._repo.list_episodic_memory(session_id, agent_id, limit=max(1, min(limit, 100)))
        return [memory_row(row, "session") for row in rows]

