from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.engine import Engine

from src.shared.db.base import metadata


def _isoformat(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _normalize_operation_status(value: str) -> str:
    return {"completed": "succeeded", "error": "failed"}.get(value, value)


def _normalize_step_status(value: str) -> str:
    return {"completed": "succeeded", "active": "running"}.get(value, value)


def _load_operation_row(connection, operation_id: str):
    runs = metadata.tables["workflow_runs"]
    stmt = select(runs).where(
        or_(runs.c.workflow_run_id == operation_id, runs.c.legacy_task_id == operation_id)
    )
    return connection.execute(stmt).first()


def _serialize_step(row) -> dict:
    return {
        "step_id": row.workflow_step_id,
        "stage": row.stage,
        "status": _normalize_step_status(row.status),
        "progress_percent": row.progress_percent,
        "message": row.message,
        "started_at": _isoformat(row.started_at),
        "finished_at": _isoformat(row.finished_at),
        "elapsed_ms": row.elapsed_ms,
    }


def _load_steps(connection, workflow_run_id: str) -> list[dict]:
    steps = metadata.tables["workflow_steps"]
    stmt = (
        select(steps)
        .where(steps.c.workflow_run_id == workflow_run_id)
        .order_by(steps.c.started_at.asc().nulls_last(), steps.c.step_key.asc())
    )
    rows = connection.execute(stmt).all()
    return [_serialize_step(row) for row in rows]


def fetch_operation_events(engine: Engine, operation_id: str) -> list[dict] | None:
    events = metadata.tables["workflow_events"]
    with engine.connect() as connection:
        row = _load_operation_row(connection, operation_id)
        if row is None:
            return None
        rows = connection.execute(
            select(events)
            .where(events.c.workflow_run_id == row.workflow_run_id)
            .order_by(events.c.emitted_at.asc(), events.c.workflow_event_id.asc())
        ).all()
    return [
        {
            "event_id": item.workflow_event_id,
            "operation_id": row.workflow_run_id,
            "type": item.event_type,
            "emitted_at": _isoformat(item.emitted_at),
            "payload": {
                "stage": item.stage,
                "level": item.level,
                "status": item.status,
                "title": item.title,
                "detail": item.detail,
                "raw": item.payload_json,
            },
        }
        for item in rows
    ]


def fetch_operation(engine: Engine, operation_id: str, trace_id: str) -> dict | None:
    with engine.connect() as connection:
        row = _load_operation_row(connection, operation_id)
        if row is None:
            return None
        steps = _load_steps(connection, row.workflow_run_id)
    return {
        "operation_id": row.workflow_run_id,
        "trace_id": trace_id,
        "status": _normalize_operation_status(row.status),
        "progress_percent": row.progress_percent,
        "message": row.last_message,
        "retryable": False,
        "created_at": _isoformat(row.created_at),
        "updated_at": _isoformat(row.updated_at),
        "steps": steps,
    }


def fetch_operation_step(engine: Engine, operation_id: str, step_id: str, trace_id: str) -> tuple[dict | None, bool]:
    steps = metadata.tables["workflow_steps"]
    with engine.connect() as connection:
        row = _load_operation_row(connection, operation_id)
        if row is None:
            return None, False
        step_row = connection.execute(
            select(steps).where(
                steps.c.workflow_run_id == row.workflow_run_id,
                or_(steps.c.workflow_step_id == step_id, steps.c.step_key == step_id),
            )
        ).first()
        if step_row is None:
            return None, True
    return {
        "operation_id": row.workflow_run_id,
        "trace_id": trace_id,
        "status": _normalize_operation_status(row.status),
        "progress_percent": row.progress_percent,
        "message": row.last_message,
        "retryable": False,
        "created_at": _isoformat(row.created_at),
        "updated_at": _isoformat(row.updated_at),
        "steps": [_serialize_step(step_row)],
    }, True
