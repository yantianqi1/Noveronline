from __future__ import annotations

import sqlite3
from pathlib import Path


def list_task_runs(database_path: Path) -> tuple[dict, ...]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            select task_id, task_type, status, created_at, updated_at, progress, message, result_json, error,
                   metadata_json, progress_detail_json
            from task_runs
            order by created_at asc
            """
        ).fetchall()
    finally:
        connection.close()
    return tuple(dict(row) for row in rows)
