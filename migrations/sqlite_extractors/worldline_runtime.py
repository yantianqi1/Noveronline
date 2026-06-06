from __future__ import annotations

import json
from pathlib import Path
import sqlite3


def _fetch_rows(database_path: Path, query: str) -> list[dict]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(query).fetchall()
    finally:
        connection.close()
    return [dict(row) for row in rows]


def list_session_agents(database_path: Path) -> list[dict]:
    return _fetch_rows(
        database_path,
        """
        select session_id, branch_id, agent_id, agent_kind, display_name, source_ref, role, drive, tension,
               status, summary, can_chat, can_act, state_json, state_source, state_version, last_action_at,
               last_dialogue_at, source_archive_id, source_entity_uuid, created_at, updated_at
        from agent_registry
        order by session_id, branch_id, agent_kind, display_name
        """,
    )


def list_agent_actions(database_path: Path) -> list[dict]:
    return _fetch_rows(
        database_path,
        """
        select action_event_id, session_id, branch_id, agent_id, display_name, action, intent, target, source,
               status, detail_json, created_at, applied_at, discarded_at
        from agent_action_log
        order by session_id, branch_id, created_at
        """,
    )


def list_agent_dialogues(database_path: Path) -> list[dict]:
    return _fetch_rows(
        database_path,
        """
        select dialogue_id, session_id, branch_id, agent_id, display_name, message, reply, generator_mode,
               model_name, context_summary, created_at
        from agent_dialogue_log
        order by session_id, branch_id, created_at
        """,
    )


def list_agent_state_snapshots(database_path: Path) -> list[dict]:
    return _fetch_rows(
        database_path,
        """
        select snapshot_id, session_id, branch_id, agent_id, state_version, status, reason, state_json, created_at
        from agent_state_snapshots
        order by session_id, branch_id, state_version, created_at
        """,
    )


def list_relation_events(database_path: Path) -> list[dict]:
    rows = _fetch_rows(
        database_path,
        """
        select relation_event_id, session_id, branch_id, agent_id, source_agent_id, target_agent_id, source_name,
               target_name, change, note, status, last_action, state_json, created_at
        from relation_state_log
        order by session_id, branch_id, created_at
        """,
    )
    for row in rows:
        json.loads(row["state_json"] or "{}")
    return rows
