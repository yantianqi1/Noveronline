"""Agent session 级经验记忆存储。"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List

from ...worldline_runtime_storage import WorldlineRuntimeStorage
from .store_support import memory_row, now_iso


class EpisodicMemoryStore:
    """session / branch 级经验记忆。"""

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
    ) -> str:
        memory_id = f"mem_{uuid.uuid4().hex[:16]}"
        created_at = now_iso()
        storage = WorldlineRuntimeStorage(container_dir)
        with storage.connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_episodic_memory (
                    memory_id, session_id, branch_id, agent_id, archive_id, memory_type,
                    summary, detail_json, source_kind, source_ref_id, normalized_subject,
                    salience, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    session_id,
                    branch_id,
                    agent_id,
                    archive_id or "",
                    memory_type,
                    summary,
                    json.dumps(detail, ensure_ascii=False),
                    source_kind,
                    source_ref_id,
                    normalized_subject,
                    salience,
                    created_at,
                    created_at,
                ),
            )
            connection.commit()
        return memory_id

    def list_memories(
        self,
        container_dir: str,
        session_id: str,
        branch_id: str,
        agent_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        storage = WorldlineRuntimeStorage(container_dir)
        with storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM agent_episodic_memory
                WHERE session_id = ? AND branch_id = ? AND agent_id = ?
                ORDER BY updated_at DESC, salience DESC
                LIMIT ?
                """,
                (session_id, branch_id, agent_id, max(1, min(limit, 100))),
            ).fetchall()
        return [memory_row(row, "session") for row in rows]

