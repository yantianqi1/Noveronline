from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.engine import Engine

from src.shared.db.base import metadata


def _isoformat(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _resolve_session_agent(connection, session_id: str, agent_id: str):
    agents = metadata.tables["session_agents"]
    stmt = select(agents).where(agents.c.session_id == session_id, agents.c.agent_id == agent_id)
    return connection.execute(stmt).first()


def _session_memories(connection, session_id: str, session_agent_id: str, agent_id: str, display_name: str) -> list[dict]:
    actions = metadata.tables["agent_actions"]
    dialogues = metadata.tables["agent_dialogues"]
    action_rows = connection.execute(
        select(actions)
        .where(actions.c.session_id == session_id, actions.c.session_agent_id == session_agent_id)
        .order_by(actions.c.queued_at.desc())
    ).all()
    dialogue_rows = connection.execute(
        select(dialogues)
        .where(dialogues.c.session_id == session_id, dialogues.c.session_agent_id == session_agent_id)
        .order_by(dialogues.c.created_at.desc())
    ).all()
    items = [
        {
            "memory_id": f"session-action:{row.action_id}",
            "memory_type": "strategy",
            "memory_layer": "session",
            "status": row.status,
            "normalized_subject": agent_id,
            "summary": f"{row.action}；意图：{row.intent}" if row.intent else row.action,
            "created_at": _isoformat(row.queued_at),
            "source": "agent_action",
            "display_name": display_name,
        }
        for row in action_rows
    ]
    items.extend(
        {
            "memory_id": f"session-dialogue:{row.dialogue_id}",
            "memory_type": "fact",
            "memory_layer": "session",
            "status": "observed",
            "normalized_subject": agent_id,
            "summary": f"问：{row.user_message} 答：{row.reply}",
            "created_at": _isoformat(row.created_at),
            "source": "agent_dialogue",
            "display_name": display_name,
        }
        for row in dialogue_rows
    )
    return items


def _archive_memories(connection, archive_id: str | None) -> tuple[list[dict], list[dict]]:
    if not archive_id:
        return [], []
    memories = metadata.tables["memories"]
    rows = connection.execute(
        select(memories).where(memories.c.archive_id == archive_id).order_by(memories.c.updated_at.desc())
    ).all()
    long_term = []
    candidate = []
    for row in rows:
        payload = {
            "memory_id": row.memory_id,
            "memory_type": row.memory_type,
            "memory_layer": row.memory_layer,
            "status": row.status,
            "normalized_subject": row.normalized_subject,
            "summary": row.summary,
            "created_at": _isoformat(row.created_at),
            "updated_at": _isoformat(row.updated_at),
            "source": "archive_memory",
        }
        if row.memory_layer == "candidate" or row.status == "candidate":
            candidate.append(payload)
            continue
        long_term.append(payload)
    return long_term, candidate


def fetch_agent_memory(engine: Engine, session_id: str, agent_id: str) -> dict | None:
    with engine.connect() as connection:
        row = _resolve_session_agent(connection, session_id, agent_id)
        if row is None:
            return None
        session_memories = _session_memories(connection, session_id, row.session_agent_id, row.agent_id, row.display_name)
        long_term_memories, candidate_memories = _archive_memories(connection, row.archive_id)
    return {
        "agent": {
            "agent_id": row.agent_id,
            "display_name": row.display_name,
            "archive_id": row.archive_id,
        },
        "session_memories": session_memories,
        "long_term_memories": long_term_memories,
        "candidate_memories": candidate_memories,
    }


def fetch_agent_memory_context(engine: Engine, session_id: str, agent_id: str, message: str | None) -> dict | None:
    payload = fetch_agent_memory(engine, session_id, agent_id)
    if payload is None:
        return None
    lines = []
    debug_hits = []
    for bucket, title in (
        ("session_memories", "运行时记忆"),
        ("long_term_memories", "长期记忆"),
        ("candidate_memories", "候选记忆"),
    ):
        items = payload[bucket]
        if not items:
            continue
        lines.append(f"## {title}")
        for item in items[:6]:
            lines.append(f"- [{item['memory_type']}/{item['memory_layer']}] {item['summary']}")
            debug_hits.append({"bucket": bucket, "memory_id": item["memory_id"], "summary": item["summary"]})
    if message:
        lines.append(f"## 用户问题\n- {message}")
    return {
        "agent": payload["agent"],
        "rendered_context": "\n".join(lines),
        "debug_hits": debug_hits,
    }
