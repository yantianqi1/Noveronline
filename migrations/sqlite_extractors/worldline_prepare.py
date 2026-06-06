from __future__ import annotations

import sqlite3
from pathlib import Path


def _fetch_rows(database_path: Path, query: str) -> tuple[dict, ...]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(query).fetchall()
    finally:
        connection.close()
    return tuple(dict(row) for row in rows)


def list_prepare_runs(database_path: Path) -> tuple[dict, ...]:
    return _fetch_rows(
        database_path,
        """
        select prepare_id, project_id, session_scope, status, focus_question, started_session_id, created_at, updated_at
        from prepare_runs
        order by created_at asc
        """,
    )


def list_prepared_agent_dossiers(database_path: Path) -> tuple[dict, ...]:
    return _fetch_rows(
        database_path,
        """
        select prepare_id, agent_id, agent_kind, display_name, template_key, template_version, created_at, updated_at
        from prepared_agent_dossiers
        order by created_at asc
        """,
    )
