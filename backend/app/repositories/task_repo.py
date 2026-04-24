"""Task runtime repository."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import Engine, insert, select, update

from app.tables.task import task_runs

from .base import BaseRepository


ACTIVE_TASK_STATUSES = ("pending", "processing")


class TaskRepository(BaseRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine)
        self.table = task_runs

    def get_task(self, task_id: str) -> dict | None:
        statement = select(self.table).where(self.table.c.task_id == task_id).limit(1)
        with self.connect() as connection:
            return self.row_to_dict(connection.execute(statement).fetchone())

    def update_task(self, values: dict) -> None:
        with self.connect() as connection:
            exists = connection.execute(
                select(self.table).where(self.table.c.task_id == values["task_id"]).limit(1)
            ).fetchone()
            connection.execute(self._statement(values, exists is not None))

    def mark_stale_tasks_failed(self, error_message: str) -> list[str]:
        """Mark all pending/processing tasks as failed.

        Called during server startup: any task that was still running when
        the previous process exited leaves a zombie row behind (status =
        processing) with no actual Python thread driving it. The frontend's
        polling loop would otherwise happily rejoin those zombies and sit
        there forever showing "no progress". Fail them up-front so the UI
        can show an actionable error and surface the "重新开始" path.
        """
        now = datetime.now().isoformat()
        with self.connect() as connection:
            rows = connection.execute(
                select(self.table.c.task_id, self.table.c.progress_detail_json).where(
                    self.table.c.status.in_(ACTIVE_TASK_STATUSES)
                )
            ).fetchall()
            if not rows:
                return []
            stale_ids: list[str] = []
            for row in rows:
                task_id = row[0]
                stale_ids.append(task_id)
                progress_detail = self._inject_failure_event(row[1], error_message, now)
                connection.execute(
                    update(self.table)
                    .where(self.table.c.task_id == task_id)
                    .values(
                        status="failed",
                        updated_at=now,
                        error=error_message,
                        message=error_message,
                        progress_detail_json=progress_detail,
                    )
                )
            return stale_ids

    def _inject_failure_event(self, progress_detail_json: str | None, message: str, timestamp: str) -> str:
        """Append a synthetic failure entry to progress_detail.timeline."""
        try:
            detail = json.loads(progress_detail_json) if progress_detail_json else {}
        except (TypeError, ValueError):
            detail = {}
        if not isinstance(detail, dict):
            detail = {}
        timeline = detail.get("timeline")
        if not isinstance(timeline, list):
            timeline = []
        timeline.append({
            "id": f"evt_startup_recovery_{timestamp}",
            "timestamp": timestamp,
            "stage": "failed",
            "level": "error",
            "status": "failed",
            "title": "任务已中断",
            "detail": message,
            "meta": {"kind": "task", "step_id": "", "step_kind": "", "group_key": "", "group_label": "", "has_trace": False},
        })
        detail["timeline"] = timeline
        detail["active_stage"] = {
            "key": "failed",
            "label": "任务已中断",
            "progress": int(detail.get("active_stage", {}).get("progress", 0)) if isinstance(detail.get("active_stage"), dict) else 0,
            "status": "failed",
        }
        return json.dumps(detail, ensure_ascii=False)

    def _statement(self, values: dict, exists: bool):
        if exists:
            return update(self.table).where(self.table.c.task_id == values["task_id"]).values(**values)
        return insert(self.table).values(**values)
