from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.engine import Engine

from src.shared.db.base import metadata


VALID_EVENT_ACTIONS = {"canon", "rejected"}


def _fetch_candidate_events(connection, session_id: str, event_ids: list[str]):
    events = metadata.tables["timeline_events"]
    stmt = select(events).where(
        events.c.session_id == session_id,
        events.c.timeline_event_id.in_(event_ids),
        events.c.status == "candidate",
    )
    return connection.execute(stmt).all()


def adopt_worldline_events(engine: Engine, session_id: str, event_ids: list[str], action: str) -> dict:
    if action not in VALID_EVENT_ACTIONS:
        raise ValueError("action must be 'canon' or 'rejected'")
    if not event_ids:
        raise ValueError("event_ids must not be empty")
    events = metadata.tables["timeline_events"]
    with engine.begin() as connection:
        rows = _fetch_candidate_events(connection, session_id, event_ids)
        if not rows:
            raise ValueError("No matching candidate events")
        connection.execute(
            events.update()
            .where(
                events.c.session_id == session_id,
                events.c.timeline_event_id.in_([row.timeline_event_id for row in rows]),
            )
            .values(status=action)
        )
    return {
        "session_id": session_id,
        "action": action,
        "changed_count": len(rows),
        "event_ids": [row.timeline_event_id for row in rows],
    }


def edit_worldline_event(engine: Engine, session_id: str, event_id: str, summary: str, title: str | None) -> dict:
    events = metadata.tables["timeline_events"]
    with engine.begin() as connection:
        row = connection.execute(
            select(events).where(
                events.c.session_id == session_id,
                events.c.timeline_event_id == event_id,
            )
        ).first()
        if row is None:
            raise ValueError("Worldline event not found")
        if row.status != "candidate":
            raise ValueError("Only candidate events can be edited")
        connection.execute(
            events.update()
            .where(events.c.timeline_event_id == event_id)
            .values(
                summary=summary,
                title=title if title is not None else row.title,
                status="canon",
            )
        )
    return {
        "session_id": session_id,
        "event_id": event_id,
        "title": title if title is not None else row.title,
        "summary": summary,
        "status": "canon",
    }
