"""Agent 长期记忆存储。"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ...archive_library_storage import ArchiveLibraryStorage
from .store_support import event_row, memory_row, now_iso


class LongTermMemoryStore:
    """跨 session 长期记忆。"""

    def __init__(self, storage: Optional[ArchiveLibraryStorage] = None):
        self.storage = storage or ArchiveLibraryStorage()

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
    ) -> str:
        if not archive_id:
            raise ValueError("archive_id 不能为空")
        with self.storage.connect() as connection:
            self._supersede_active_rows(
                connection,
                archive_id,
                memory_type,
                normalized_subject,
                ("candidate",),
            )
            memory_id = self._insert_memory(
                connection,
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
            connection.commit()
        return memory_id

    def promote_to_canon(self, archive_id: str, memory_id: str) -> Dict[str, Any]:
        with self.storage.connect() as connection:
            candidate = self._fetch_memory(connection, archive_id, memory_id)
            if not candidate:
                raise ValueError(f"候选记忆不存在: {memory_id}")
            if candidate["memory_layer"] != "candidate":
                raise ValueError("只能采纳 candidate 记忆")
            if candidate["status"] == "rejected":
                raise ValueError("candidate 记忆已被驳回，不能再次采纳")
            if candidate["status"] != "active":
                raise ValueError("candidate 记忆已被采纳或替换，不能重复采纳")
            self._supersede_active_rows(
                connection,
                archive_id,
                candidate["memory_type"],
                candidate["normalized_subject"],
                ("canon",),
            )
            self._update_memory_status(
                connection,
                candidate["memory_id"],
                "superseded",
                "candidate_adopted",
            )
            canon_id = self._insert_memory(
                connection,
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
                source_session_id=candidate["source_session_id"],
                source_branch_id=candidate["source_branch_id"],
                evidence=json.loads(candidate["evidence_json"] or "[]"),
                adopted_at=now_iso(),
                event_type="promote_to_canon",
            )
            connection.commit()
        return self.list_memory(archive_id, canon_id)

    def reject_candidate(self, archive_id: str, memory_id: str) -> Dict[str, Any]:
        with self.storage.connect() as connection:
            candidate = self._fetch_memory(connection, archive_id, memory_id)
            if not candidate:
                raise ValueError(f"候选记忆不存在: {memory_id}")
            if candidate["memory_layer"] != "candidate":
                raise ValueError("只能驳回 candidate 记忆")
            if candidate["status"] == "rejected":
                raise ValueError("candidate 记忆已被驳回")
            if candidate["status"] != "active":
                raise ValueError("candidate 记忆已被采纳或替换，不能再驳回")
            self._update_memory_status(
                connection,
                memory_id,
                "rejected",
                "reject_candidate",
                rejected_at=now_iso(),
            )
            connection.commit()
        return self.list_memory(archive_id, memory_id)

    def supersede_canon(self, archive_id: str, memory_id: str) -> Dict[str, Any]:
        with self.storage.connect() as connection:
            memory = self._fetch_memory(connection, archive_id, memory_id)
            if not memory:
                raise ValueError(f"长期记忆不存在: {memory_id}")
            self._update_memory_status(
                connection,
                memory_id,
                "superseded",
                "supersede_canon",
            )
            connection.commit()
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
        layer_placeholders = ",".join("?" for _ in layers)
        status_placeholders = ",".join("?" for _ in statuses)
        with self.storage.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM archive_agent_memory
                WHERE archive_id = ? AND status IN ({status_placeholders})
                  AND memory_layer IN ({layer_placeholders})
                ORDER BY CASE memory_layer
                    WHEN 'canon' THEN 0
                    WHEN 'candidate' THEN 1
                    ELSE 2
                END, updated_at DESC, salience DESC
                LIMIT ?
                """,
                (archive_id, *statuses, *layers, max(1, min(limit, 100))),
            ).fetchall()
        return [memory_row(row, "long_term") for row in rows]

    def list_memories(self, archive_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        return self.list_active_memories(archive_id, layers=("canon",), limit=limit)

    def list_memory_timeline(
        self,
        archive_id: str,
        memory_id: str = "",
        normalized_subject: str = "",
    ) -> Dict[str, Any]:
        with self.storage.connect() as connection:
            subject = normalized_subject
            if memory_id and not subject:
                row = self._fetch_memory(connection, archive_id, memory_id)
                if not row:
                    raise ValueError(f"长期记忆不存在: {memory_id}")
                subject = row["normalized_subject"]
            if not subject:
                raise ValueError("请提供 memory_id 或 normalized_subject")
            memories = connection.execute(
                """
                SELECT * FROM archive_agent_memory
                WHERE archive_id = ? AND normalized_subject = ?
                ORDER BY version DESC, updated_at DESC
                """,
                (archive_id, subject),
            ).fetchall()
            events = connection.execute(
                """
                SELECT * FROM archive_agent_memory_events
                WHERE archive_id = ? AND normalized_subject = ?
                ORDER BY created_at DESC
                """,
                (archive_id, subject),
            ).fetchall()
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
        with self.storage.connect() as connection:
            row = self._fetch_memory(connection, archive_id, memory_id)
        if not row:
            raise ValueError(f"长期记忆不存在: {memory_id}")
        return memory_row(row, "long_term")

    def _insert_memory(self, connection, **kwargs) -> str:
        now = now_iso()
        memory_id = f"ltm_{uuid.uuid4().hex[:16]}"
        version = self._next_version(
            connection,
            kwargs["archive_id"],
            kwargs["memory_type"],
            kwargs["normalized_subject"],
        )
        adopted_at = kwargs.get("adopted_at")
        event_type = kwargs.get("event_type", "append_candidate")
        connection.execute(
            """
            INSERT INTO archive_agent_memory (
                memory_id, archive_id, agent_id, memory_type, normalized_subject,
                summary, detail_json, source_kind, source_ref_id, salience,
                created_at, updated_at, memory_layer, status, version,
                parent_memory_id, source_session_id, source_branch_id,
                evidence_json, adopted_at, rejected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                memory_id,
                kwargs["archive_id"],
                kwargs["agent_id"],
                kwargs["memory_type"],
                kwargs["normalized_subject"],
                kwargs["summary"],
                json.dumps(kwargs["detail"], ensure_ascii=False),
                kwargs["source_kind"],
                kwargs["source_ref_id"],
                kwargs["salience"],
                now,
                now,
                kwargs["memory_layer"],
                kwargs["status"],
                version,
                kwargs.get("parent_memory_id", ""),
                kwargs.get("source_session_id", ""),
                kwargs.get("source_branch_id", ""),
                json.dumps(kwargs.get("evidence") or [], ensure_ascii=False),
                adopted_at,
            ),
        )
        self._log_event(connection, memory_id, kwargs, event_type, version, now)
        return memory_id

    def _log_event(
        self,
        connection,
        memory_id: str,
        payload: Dict[str, Any],
        event_type: str,
        version: int,
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO archive_agent_memory_events (
                event_id, memory_id, archive_id, normalized_subject, memory_type,
                event_type, memory_layer, status, version, parent_memory_id,
                source_session_id, source_branch_id, summary, evidence_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"evt_{uuid.uuid4().hex[:16]}",
                memory_id,
                payload["archive_id"],
                payload["normalized_subject"],
                payload["memory_type"],
                event_type,
                payload["memory_layer"],
                payload["status"],
                version,
                payload.get("parent_memory_id", ""),
                payload.get("source_session_id", ""),
                payload.get("source_branch_id", ""),
                payload["summary"],
                json.dumps(payload.get("evidence") or [], ensure_ascii=False),
                created_at,
            ),
        )

    def _next_version(
        self,
        connection,
        archive_id: str,
        memory_type: str,
        normalized_subject: str,
    ) -> int:
        row = connection.execute(
            """
            SELECT MAX(version) AS max_version
            FROM archive_agent_memory
            WHERE archive_id = ? AND memory_type = ? AND normalized_subject = ?
            """,
            (archive_id, memory_type, normalized_subject),
        ).fetchone()
        return int(row["max_version"] or 0) + 1

    def _fetch_memory(self, connection, archive_id: str, memory_id: str):
        return connection.execute(
            "SELECT * FROM archive_agent_memory WHERE archive_id = ? AND memory_id = ?",
            (archive_id, memory_id),
        ).fetchone()

    def _supersede_active_rows(
        self,
        connection,
        archive_id: str,
        memory_type: str,
        normalized_subject: str,
        layers: Iterable[str],
    ) -> None:
        placeholders = ",".join("?" for _ in layers)
        rows = connection.execute(
            f"""
            SELECT * FROM archive_agent_memory
            WHERE archive_id = ? AND memory_type = ? AND normalized_subject = ?
              AND status = 'active' AND memory_layer IN ({placeholders})
            """,
            (archive_id, memory_type, normalized_subject, *layers),
        ).fetchall()
        for row in rows:
            self._update_memory_status(
                connection,
                row["memory_id"],
                "superseded",
                "supersede_active",
            )

    def _update_memory_status(
        self,
        connection,
        memory_id: str,
        status: str,
        event_type: str,
        rejected_at: Optional[str] = None,
    ) -> None:
        row = connection.execute(
            "SELECT * FROM archive_agent_memory WHERE memory_id = ?",
            (memory_id,),
        ).fetchone()
        if not row:
            return
        now = now_iso()
        connection.execute(
            """
            UPDATE archive_agent_memory
            SET status = ?, updated_at = ?, rejected_at = COALESCE(?, rejected_at)
            WHERE memory_id = ?
            """,
            (status, now, rejected_at, memory_id),
        )
        self._log_event(
            connection,
            memory_id,
            {
                "archive_id": row["archive_id"],
                "normalized_subject": row["normalized_subject"],
                "memory_type": row["memory_type"],
                "memory_layer": row["memory_layer"],
                "status": status,
                "parent_memory_id": row["parent_memory_id"],
                "source_session_id": row["source_session_id"],
                "source_branch_id": row["source_branch_id"],
                "summary": row["summary"],
                "evidence": json.loads(row["evidence_json"] or "[]"),
            },
            event_type,
            int(row["version"] or 1),
            now,
        )
