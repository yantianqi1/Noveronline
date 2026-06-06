from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.engine import Engine

from src.shared.db.base import metadata


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_memory(row) -> dict:
    return {
        "memory_id": row.memory_id,
        "archive_id": row.archive_id,
        "memory_type": row.memory_type,
        "memory_layer": row.memory_layer,
        "status": row.status,
        "normalized_subject": row.normalized_subject,
        "summary": row.summary,
        "created_at": row.created_at.isoformat() if hasattr(row.created_at, "isoformat") else row.created_at,
        "updated_at": row.updated_at.isoformat() if hasattr(row.updated_at, "isoformat") else row.updated_at,
    }


def _fetch_archive(connection, archive_id: str):
    archives = metadata.tables["archives"]
    return connection.execute(select(archives).where(archives.c.archive_id == archive_id)).first()


def _fetch_memory(connection, archive_id: str, memory_id: str):
    memories = metadata.tables["memories"]
    stmt = select(memories).where(memories.c.archive_id == archive_id, memories.c.memory_id == memory_id)
    return connection.execute(stmt).first()


def _log_event(connection, archive_id: str, memory_id: str, event_type: str, actor_ref: str) -> None:
    events = metadata.tables["memory_events"]
    connection.execute(
        events.insert().values(
            memory_event_id=f"evt_{uuid.uuid4().hex[:16]}",
            memory_id=memory_id,
            archive_id=archive_id,
            event_type=event_type,
            actor_type="api",
            actor_ref=actor_ref,
            created_at=_now(),
        )
    )


def _update_memory(connection, memory_id: str, **values) -> None:
    memories = metadata.tables["memories"]
    connection.execute(memories.update().where(memories.c.memory_id == memory_id).values(**values))


def adopt_archive_memory(engine: Engine, archive_id: str, memory_id: str, actor_ref: str) -> dict:
    memories = metadata.tables["memories"]
    with engine.begin() as connection:
        if _fetch_archive(connection, archive_id) is None:
            raise ValueError("archive 不存在")
        memory = _fetch_memory(connection, archive_id, memory_id)
        if memory is None:
            raise ValueError("候选记忆不存在")
        if memory.memory_layer != "candidate":
            raise ValueError("只能采纳 candidate 记忆")
        if memory.status == "rejected":
            raise ValueError("candidate 记忆已被驳回，不能再次采纳")
        if memory.status != "active":
            raise ValueError("candidate 记忆已被采纳或替换，不能重复采纳")

        superseded = connection.execute(
            select(memories).where(
                memories.c.archive_id == archive_id,
                memories.c.memory_type == memory.memory_type,
                memories.c.normalized_subject == memory.normalized_subject,
                memories.c.memory_layer == "canon",
                memories.c.status == "active",
            )
        ).all()
        for row in superseded:
            _update_memory(connection, row.memory_id, status="superseded", updated_at=_now())
            _log_event(connection, archive_id, row.memory_id, "supersede_canon", actor_ref)

        _update_memory(connection, memory_id, memory_layer="canon", status="active", updated_at=_now())
        _log_event(connection, archive_id, memory_id, "promote_to_canon", actor_ref)
        adopted = _fetch_memory(connection, archive_id, memory_id)
    return {"archive_id": archive_id, "memory": _serialize_memory(adopted)}


def reject_archive_memory(engine: Engine, archive_id: str, memory_id: str, actor_ref: str) -> dict:
    with engine.begin() as connection:
        if _fetch_archive(connection, archive_id) is None:
            raise ValueError("archive 不存在")
        memory = _fetch_memory(connection, archive_id, memory_id)
        if memory is None:
            raise ValueError("候选记忆不存在")
        if memory.memory_layer != "candidate":
            raise ValueError("只能驳回 candidate 记忆")
        if memory.status == "rejected":
            raise ValueError("candidate 记忆已被驳回")
        if memory.status != "active":
            raise ValueError("candidate 记忆已被采纳或替换，不能再驳回")

        _update_memory(connection, memory_id, status="rejected", updated_at=_now())
        _log_event(connection, archive_id, memory_id, "reject_candidate", actor_ref)
        rejected = _fetch_memory(connection, archive_id, memory_id)
    return {"archive_id": archive_id, "memory": _serialize_memory(rejected)}
