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


def list_archives(database_path: Path) -> tuple[dict, ...]:
    return _fetch_rows(
        database_path,
        """
        select archive_id, project_id, entity_uuid, entity_name, entity_type, agent_kind,
               importance_tier, selected_importance_tier, template_key, template_version, synced_at
        from archive_library
        order by synced_at asc
        """,
    )


def list_memories(database_path: Path) -> tuple[dict, ...]:
    return _fetch_rows(
        database_path,
        """
        select memory_id, archive_id, memory_type, normalized_subject, summary,
               created_at, updated_at, memory_layer, status
        from archive_agent_memory
        order by created_at asc
        """,
    )


def list_memory_events(database_path: Path) -> tuple[dict, ...]:
    return _fetch_rows(
        database_path,
        """
        select event_id, memory_id, archive_id, event_type, summary, created_at
        from archive_agent_memory_events
        order by created_at asc
        """,
    )
