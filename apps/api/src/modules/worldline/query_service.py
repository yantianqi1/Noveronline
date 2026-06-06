from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.engine import Engine

from src.shared.db.base import metadata


def _isoformat(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _resolve_session_agent(connection, session_id: str, agent_id: str):
    agents = metadata.tables["session_agents"]
    stmt = select(agents).where(agents.c.session_id == session_id, agents.c.agent_id == agent_id)
    return connection.execute(stmt).first()


def _load_actions(connection, session_id: str, session_agent_id: str | None):
    actions = metadata.tables["agent_actions"]
    agents = metadata.tables["session_agents"]
    stmt = (
        select(actions, agents.c.agent_id, agents.c.display_name)
        .join(agents, actions.c.session_agent_id == agents.c.session_agent_id)
        .where(actions.c.session_id == session_id)
        .order_by(actions.c.queued_at.desc())
    )
    if session_agent_id is not None:
        stmt = stmt.where(actions.c.session_agent_id == session_agent_id)
    rows = connection.execute(stmt).all()
    return [
        {
            "action_id": row.action_id,
            "action_event_id": row.action_id,
            "agent_id": row.agent_id,
            "display_name": row.display_name,
            "action": row.action,
            "intent": row.intent,
            "target": row.target,
            "source": row.source,
            "status": row.status,
            "detail_json": row.detail_json,
            "queued_at": _isoformat(row.queued_at),
            "applied_at": _isoformat(row.applied_at),
            "discarded_at": _isoformat(row.discarded_at),
        }
        for row in rows
    ]


def _load_dialogues(connection, session_id: str, session_agent_id: str | None):
    dialogues = metadata.tables["agent_dialogues"]
    agents = metadata.tables["session_agents"]
    stmt = (
        select(dialogues, agents.c.agent_id, agents.c.display_name)
        .join(agents, dialogues.c.session_agent_id == agents.c.session_agent_id)
        .where(dialogues.c.session_id == session_id)
        .order_by(dialogues.c.created_at.desc())
    )
    if session_agent_id is not None:
        stmt = stmt.where(dialogues.c.session_agent_id == session_agent_id)
    rows = connection.execute(stmt).all()
    return [
        {
            "dialogue_id": row.dialogue_id,
            "agent_id": row.agent_id,
            "display_name": row.display_name,
            "message": row.user_message,
            "reply": row.reply,
            "generator_mode": row.generator_mode,
            "model_name": row.model_name,
            "context_summary": row.context_summary,
            "created_at": _isoformat(row.created_at),
        }
        for row in rows
    ]


def _load_snapshots(connection, session_id: str, session_agent_id: str):
    snapshots = metadata.tables["agent_state_snapshots"]
    stmt = (
        select(snapshots)
        .where(snapshots.c.session_id == session_id, snapshots.c.session_agent_id == session_agent_id)
        .order_by(snapshots.c.state_version.desc(), snapshots.c.created_at.desc())
    )
    rows = connection.execute(stmt).all()
    return [
        {
            "snapshot_id": row.snapshot_id,
            "state_version": row.state_version,
            "status": row.status,
            "reason": row.reason,
            "state_json": row.state_json,
            "created_at": _isoformat(row.created_at),
        }
        for row in rows
    ]


def _load_relation_events(connection, session_id: str, session_agent_id: str | None):
    relations = metadata.tables["relation_events"]
    stmt = select(relations).where(relations.c.session_id == session_id).order_by(relations.c.created_at.desc())
    if session_agent_id is not None:
        stmt = stmt.where(
            or_(
                relations.c.relation_session_agent_id == session_agent_id,
                relations.c.source_session_agent_id == session_agent_id,
                relations.c.target_session_agent_id == session_agent_id,
            )
        )
    rows = connection.execute(stmt).all()
    return [
        {
            "relation_event_id": row.relation_event_id,
            "source_name": row.source_name,
            "target_name": row.target_name,
            "change": row.change,
            "note": row.note,
            "status": row.status,
            "last_action": row.last_action,
            "state_json": row.state_json,
            "created_at": _isoformat(row.created_at),
        }
        for row in rows
    ]


def fetch_session_agent(engine: Engine, session_id: str, agent_id: str) -> dict | None:
    with engine.connect() as connection:
        row = _resolve_session_agent(connection, session_id, agent_id)
        if row is None:
            return None
        actions = _load_actions(connection, session_id, row.session_agent_id)
        dialogues = _load_dialogues(connection, session_id, row.session_agent_id)
        snapshots = _load_snapshots(connection, session_id, row.session_agent_id)
    return {
        "session_agent_id": row.session_agent_id,
        "session_id": row.session_id,
        "agent_id": row.agent_id,
        "archive_id": row.archive_id,
        "entity_id": row.entity_id,
        "agent_kind": row.agent_kind,
        "display_name": row.display_name,
        "role": row.role,
        "drive": row.drive,
        "tension": row.tension,
        "status": row.status,
        "summary": row.summary,
        "can_chat": row.can_chat,
        "can_act": row.can_act,
        "state_json": row.state_json,
        "state_source": row.state_source,
        "state_version": row.state_version,
        "source_ref": row.source_ref,
        "last_action_at": _isoformat(row.last_action_at),
        "last_dialogue_at": _isoformat(row.last_dialogue_at),
        "history_counts": {
            "action_count": len(actions),
            "dialogue_count": len(dialogues),
            "snapshot_count": len(snapshots),
        },
    }


def fetch_agent_history(engine: Engine, session_id: str, agent_id: str) -> dict | None:
    with engine.connect() as connection:
        row = _resolve_session_agent(connection, session_id, agent_id)
        if row is None:
            return None
        return {
            "agent": {
                "agent_id": row.agent_id,
                "display_name": row.display_name,
                "agent_kind": row.agent_kind,
                "status": row.status,
            },
            "actions": _load_actions(connection, session_id, row.session_agent_id),
            "dialogues": _load_dialogues(connection, session_id, row.session_agent_id),
            "snapshots": _load_snapshots(connection, session_id, row.session_agent_id),
            "relations": _load_relation_events(connection, session_id, row.session_agent_id),
        }


def fetch_agent_actions(engine: Engine, session_id: str, agent_id: str | None) -> list[dict] | None:
    with engine.connect() as connection:
        row = _resolve_session_agent(connection, session_id, agent_id) if agent_id else None
        if agent_id and row is None:
            return None
        return _load_actions(connection, session_id, row.session_agent_id if row is not None else None)


def fetch_agent_dialogues(engine: Engine, session_id: str, agent_id: str | None) -> list[dict] | None:
    with engine.connect() as connection:
        row = _resolve_session_agent(connection, session_id, agent_id) if agent_id else None
        if agent_id and row is None:
            return None
        return _load_dialogues(connection, session_id, row.session_agent_id if row is not None else None)


def fetch_relation_history(engine: Engine, session_id: str, agent_id: str | None) -> list[dict] | None:
    with engine.connect() as connection:
        row = _resolve_session_agent(connection, session_id, agent_id) if agent_id else None
        if agent_id and row is None:
            return None
        return _load_relation_events(connection, session_id, row.session_agent_id if row is not None else None)


def fetch_session_events(engine: Engine, session_id: str, status: str | None) -> list[dict]:
    events = metadata.tables["timeline_events"]
    stmt = select(events).where(events.c.session_id == session_id).order_by(events.c.step_no.asc(), events.c.created_at.asc())
    if status is not None:
        stmt = stmt.where(events.c.status == status)
    with engine.connect() as connection:
        rows = connection.execute(stmt).all()
    return [
        {
            "timeline_event_id": row.timeline_event_id,
            "session_id": row.session_id,
            "world_state_id": row.world_state_id,
            "step_no": row.step_no,
            "event_type": row.event_type,
            "title": row.title,
            "summary": row.summary,
            "status": row.status,
            "created_at": _isoformat(row.created_at),
        }
        for row in rows
    ]
