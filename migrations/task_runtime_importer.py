from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json

from sqlalchemy import select


DEFAULT_TIMESTAMP = datetime(2026, 4, 11, tzinfo=timezone.utc)
ID_DIGEST_LENGTH = 16
TERMINAL_STEP_STATUSES = {"completed", "failed", "cancelled"}


@dataclass(frozen=True)
class TaskRuntimeImportResult:
    workflow_run_id: str
    step_count: int
    event_count: int


def _stable_id(prefix: str, seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:ID_DIGEST_LENGTH]}"


def _parse_timestamp(raw_value: str | None) -> datetime:
    if not raw_value:
        return DEFAULT_TIMESTAMP
    normalized = raw_value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _insert_if_missing(connection, table, values: dict, key_column: str) -> None:
    existing = connection.execute(
        select(table.c[key_column]).where(table.c[key_column] == values[key_column])
    ).first()
    if existing is None:
        connection.execute(table.insert().values(**values))


def _task_project_id(row: dict, tables: dict, connection) -> str | None:
    metadata_payload = json.loads(row["metadata_json"] or "{}")
    project_id = metadata_payload.get("project_id")
    if not project_id:
        return None
    existing = connection.execute(
        select(tables["projects"].c.project_id).where(tables["projects"].c.project_id == project_id)
    ).first()
    return project_id if existing is not None else None


def _timeline_by_stage(row: dict) -> list[dict]:
    grouped: dict[str, dict] = {}
    for item in _timeline_items(row):
        stage = item.get("stage") or "unknown"
        timestamp = _parse_timestamp(item.get("timestamp"))
        current = grouped.setdefault(
            stage,
            {
                "step_key": stage,
                "stage": stage,
                "status": item.get("status") or "pending",
                "message": item.get("detail") or item.get("title"),
                "started_at": timestamp,
                "finished_at": None,
            },
        )
        current["status"] = item.get("status") or current["status"]
        current["message"] = item.get("detail") or item.get("title") or current["message"]
        current["started_at"] = min(current["started_at"], timestamp)
        if current["status"] in TERMINAL_STEP_STATUSES:
            current["finished_at"] = timestamp
    return [grouped[key] for key in grouped]


def _step_progress(row: dict, step: dict) -> int:
    if step["status"] in TERMINAL_STEP_STATUSES:
        return 100
    progress_detail = json.loads(row["progress_detail_json"] or "{}")
    return row["progress"] if progress_detail.get("active_stage") == step["stage"] else 0


def _timeline_items(row: dict) -> list[dict]:
    return json.loads(row["progress_detail_json"] or "{}").get("timeline", [])


def _step_elapsed_ms(step: dict) -> int | None:
    if step["finished_at"] is None or step["started_at"] is None:
        return None
    return int((step["finished_at"] - step["started_at"]).total_seconds() * 1000)


def _event_type(row: dict, item: dict, index: int, count: int) -> str:
    if index == 0:
        return "operation.started"
    if index == count - 1 and row["status"] == "completed":
        return "operation.completed"
    if index == count - 1 and row["status"] == "failed":
        return "operation.failed"
    if item.get("meta", {}).get("kind") == "stage":
        return "operation.step.updated"
    return "operation.progress"


def _insert_events(connection, tables: dict, workflow_run_id: str, row: dict) -> int:
    items = _timeline_items(row)
    for index, item in enumerate(items):
        _insert_if_missing(
            connection,
            tables["workflow_events"],
            {
                "workflow_event_id": item.get("id") or _stable_id("wfe", f"{row['task_id']}:{index}"),
                "workflow_run_id": workflow_run_id,
                "event_type": _event_type(row, item, index, len(items)),
                "stage": item.get("stage"),
                "level": item.get("level"),
                "status": item.get("status"),
                "title": item.get("title") or "",
                "detail": item.get("detail"),
                "payload_json": json.dumps(item, ensure_ascii=False),
                "emitted_at": _parse_timestamp(item.get("timestamp")),
            },
            "workflow_event_id",
        )
    return len(items)


def import_task_runtime_row(connection, tables: dict, row: dict) -> TaskRuntimeImportResult:
    workflow_run_id = _stable_id("wfr", row["task_id"])
    _insert_if_missing(
        connection,
        tables["workflow_runs"],
        {
            "workflow_run_id": workflow_run_id,
            "project_id": _task_project_id(row, tables, connection),
            "legacy_task_id": row["task_id"],
            "workflow_type": row["task_type"],
            "status": row["status"],
            "progress_percent": row["progress"],
            "last_message": row["message"],
            "input_snapshot": row["metadata_json"],
            "last_error": row["error"],
            "created_at": _parse_timestamp(row["created_at"]),
            "updated_at": _parse_timestamp(row["updated_at"]),
        },
        "workflow_run_id",
    )
    steps = _timeline_by_stage(row)
    for step in steps:
        _insert_if_missing(
            connection,
            tables["workflow_steps"],
            {
                "workflow_step_id": _stable_id("wfs", f"{row['task_id']}:{step['step_key']}"),
                "workflow_run_id": workflow_run_id,
                "step_key": step["step_key"],
                "stage": step["stage"],
                "status": step["status"],
                "progress_percent": _step_progress(row, step),
                "message": step["message"],
                "started_at": step["started_at"],
                "finished_at": step["finished_at"],
                "elapsed_ms": _step_elapsed_ms(step),
            },
            "workflow_step_id",
        )
    return TaskRuntimeImportResult(
        workflow_run_id=workflow_run_id,
        step_count=len(steps),
        event_count=_insert_events(connection, tables, workflow_run_id, row),
    )
