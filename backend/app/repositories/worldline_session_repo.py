"""Worldline session repository — DB-backed session metadata + serialization.

Replaces the filesystem layer in ``WorldStateStore`` for session
persistence. Every session's full ``WorldlineSession.to_dict()`` payload
lives in ``session_data_json``; commonly-filtered fields (project_id,
graph_id, session_scope, status, timestamps, source_* counts) are
duplicated as real columns so list-and-filter queries remain cheap.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, and_, delete, desc, insert, select, update

from app.tables.worldline import worldline_sessions

from .base import BaseRepository


def _now_iso() -> str:
    return datetime.now().isoformat()


class WorldlineSessionRepository(BaseRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine)

    def save_session(self, session_dict: dict[str, Any]) -> None:
        session_id = session_dict["session_id"]
        if not session_id:
            raise ValueError("session_id is required")
        now = _now_iso()
        created_at = session_dict.get("created_at") or now
        session_dict = {**session_dict, "updated_at": now, "created_at": created_at}
        values = {
            "session_id": session_id,
            "project_id": session_dict.get("project_id"),
            "graph_id": session_dict.get("graph_id") or "",
            "session_scope": session_dict.get("session_scope") or "project",
            "label": session_dict.get("label") or "",
            "prepare_id": session_dict.get("prepare_id") or "",
            "status": session_dict.get("status") or "running",
            "simulation_goal": session_dict.get("simulation_goal") or "",
            "focus_question": session_dict.get("focus_question") or "",
            "branch_count": int(session_dict.get("branch_count") or 1),
            "source_archive_count": int(session_dict.get("source_archive_count") or 0),
            "source_archive_ids_json": json.dumps(
                list(session_dict.get("source_archive_ids") or []), ensure_ascii=False
            ),
            "source_project_ids_json": json.dumps(
                list(session_dict.get("source_project_ids") or []), ensure_ascii=False
            ),
            "session_data_json": json.dumps(session_dict, ensure_ascii=False),
            "created_at": created_at,
            "updated_at": now,
        }
        with self.connect() as conn:
            existing = conn.execute(
                select(worldline_sessions.c.session_id)
                .where(worldline_sessions.c.session_id == session_id)
                .limit(1)
            ).fetchone()
            if existing:
                conn.execute(
                    update(worldline_sessions)
                    .where(worldline_sessions.c.session_id == session_id)
                    .values(**values)
                )
            else:
                conn.execute(insert(worldline_sessions).values(**values))

    def load_session(self, session_id: str) -> dict[str, Any] | None:
        if not session_id:
            return None
        stmt = (
            select(worldline_sessions.c.session_data_json)
            .where(worldline_sessions.c.session_id == session_id)
            .limit(1)
        )
        with self.connect() as conn:
            row = conn.execute(stmt).fetchone()
        if row is None:
            return None
        payload = row[0]
        return json.loads(payload) if payload else None

    def list_sessions(
        self,
        *,
        project_id: str | None = None,
        graph_id: str | None = None,
        session_scope: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        clauses = []
        if project_id is not None:
            clauses.append(worldline_sessions.c.project_id == project_id)
        if graph_id is not None:
            clauses.append(worldline_sessions.c.graph_id == graph_id)
        if session_scope is not None:
            clauses.append(worldline_sessions.c.session_scope == session_scope)
        stmt = select(worldline_sessions).order_by(desc(worldline_sessions.c.updated_at)).limit(limit)
        if clauses:
            stmt = stmt.where(and_(*clauses))
        with self.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [self._row_to_summary(row) for row in rows]

    def delete_session(self, session_id: str) -> int:
        if not session_id:
            return 0
        stmt = delete(worldline_sessions).where(worldline_sessions.c.session_id == session_id)
        with self.connect() as conn:
            result = conn.execute(stmt)
        return result.rowcount or 0

    def _row_to_summary(self, row) -> dict[str, Any]:
        mapping = row._mapping
        return {
            "session_id": mapping["session_id"],
            "project_id": mapping["project_id"],
            "graph_id": mapping["graph_id"],
            "label": mapping["label"],
            "simulation_goal": mapping["simulation_goal"],
            "branch_count": mapping["branch_count"],
            "session_scope": mapping["session_scope"],
            "status": mapping["status"],
            "source_archive_ids": json.loads(mapping["source_archive_ids_json"] or "[]"),
            "source_project_ids": json.loads(mapping["source_project_ids_json"] or "[]"),
            "source_archive_count": mapping["source_archive_count"],
            "created_at": mapping["created_at"],
            "updated_at": mapping["updated_at"],
        }


__all__ = ["WorldlineSessionRepository"]
