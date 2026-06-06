from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from sqlalchemy import select

from migrations.sqlite_extractors.worldline_runtime import (
    list_agent_actions,
    list_agent_dialogues,
    list_agent_state_snapshots,
    list_relation_events,
    list_session_agents,
)


DEFAULT_TIMESTAMP = datetime(2026, 4, 11, tzinfo=timezone.utc)
ID_DIGEST_LENGTH = 16


@dataclass(frozen=True)
class WorldlineRuntimeImportResult:
    imported: bool
    anomalies: tuple[str, ...]


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


def _session_exists(connection, tables: dict, session_id: str) -> bool:
    row = connection.execute(
        select(tables["worldline_sessions"].c.session_id).where(
            tables["worldline_sessions"].c.session_id == session_id
        )
    ).first()
    return row is not None


def _project_id_for_session(connection, tables: dict, session_id: str) -> str | None:
    row = connection.execute(
        select(tables["worldline_sessions"].c.project_id).where(
            tables["worldline_sessions"].c.session_id == session_id
        )
    ).first()
    return row.project_id if row is not None else None


def _find_entity_id(connection, tables: dict, project_id: str | None, entity_uuid: str | None) -> str | None:
    if not project_id or not entity_uuid:
        return None
    row = connection.execute(
        select(tables["entities"].c.entity_id).where(
            tables["entities"].c.project_id == project_id,
            tables["entities"].c.entity_uuid == entity_uuid,
        )
    ).first()
    return row.entity_id if row is not None else None


def _find_archive_id(connection, tables: dict, archive_id: str | None) -> str | None:
    if not archive_id:
        return None
    row = connection.execute(
        select(tables["archives"].c.archive_id).where(tables["archives"].c.archive_id == archive_id)
    ).first()
    return row.archive_id if row is not None else None


def _load_selected_branches(runtime_path: Path) -> tuple[dict[str, str], tuple[str, ...]]:
    selected: dict[str, str] = {}
    anomalies: list[str] = []
    session_files = sorted((runtime_path.parent / "sessions").glob("*/session.json"))
    for session_path in session_files:
        payload = json.loads(session_path.read_text(encoding="utf-8"))
        branches = payload.get("branches", [])
        if not branches:
            anomalies.append(f"{payload.get('session_id', session_path.parent.name)}: missing branches in session.json")
            continue
        branch_id = branches[0].get("branch_id") or "main"
        session_id = payload["session_id"]
        selected[session_id] = branch_id
        ignored = [item.get("branch_id") or "unknown" for item in branches[1:]]
        if branch_id != "main" or ignored:
            anomalies.append(
                f"{session_id}: imported legacy branch {branch_id} as current_world; ignored {len(ignored)} extra branches"
            )
    if not selected:
        anomalies.append(f"{runtime_path.as_posix()}: no companion session.json found for runtime import")
    return selected, tuple(anomalies)


def _import_session_agents(connection, tables: dict, runtime_path: Path, selected_branches: dict[str, str]) -> tuple[dict[tuple[str, str], str], tuple[str, ...]]:
    agent_ids: dict[tuple[str, str], str] = {}
    anomalies: list[str] = []
    for row in list_session_agents(runtime_path):
        if selected_branches.get(row["session_id"]) != row["branch_id"]:
            continue
        if not _session_exists(connection, tables, row["session_id"]):
            anomalies.append(f"{row['session_id']}: runtime session agents skipped because session row is missing")
            continue
        project_id = _project_id_for_session(connection, tables, row["session_id"])
        session_agent_id = _stable_id("sag", f"{row['session_id']}:{row['agent_id']}")
        agent_ids[(row["session_id"], row["agent_id"])] = session_agent_id
        _insert_if_missing(
            connection,
            tables["session_agents"],
            {
                "session_agent_id": session_agent_id,
                "session_id": row["session_id"],
                "agent_id": row["agent_id"],
                "archive_id": _find_archive_id(connection, tables, row["source_archive_id"]),
                "entity_id": _find_entity_id(connection, tables, project_id, row["source_entity_uuid"]),
                "agent_kind": row["agent_kind"],
                "display_name": row["display_name"],
                "role": row["role"] or None,
                "drive": row["drive"] or None,
                "tension": row["tension"] or None,
                "status": row["status"] or None,
                "summary": row["summary"] or None,
                "can_chat": bool(row["can_chat"]),
                "can_act": bool(row["can_act"]),
                "state_json": row["state_json"] or "{}",
                "state_source": row["state_source"] or None,
                "state_version": row["state_version"],
                "source_ref": row["source_ref"] or None,
                "last_action_at": _parse_timestamp(row["last_action_at"]),
                "last_dialogue_at": _parse_timestamp(row["last_dialogue_at"]),
                "created_at": _parse_timestamp(row["created_at"]),
                "updated_at": _parse_timestamp(row["updated_at"]),
            },
            "session_agent_id",
        )
    return agent_ids, tuple(anomalies)


def _insert_snapshots(connection, tables: dict, runtime_path: Path, selected_branches: dict[str, str], agent_ids: dict[tuple[str, str], str]) -> None:
    for row in list_agent_state_snapshots(runtime_path):
        if selected_branches.get(row["session_id"]) != row["branch_id"]:
            continue
        session_agent_id = agent_ids.get((row["session_id"], row["agent_id"]))
        if session_agent_id is None:
            continue
        _insert_if_missing(
            connection,
            tables["agent_state_snapshots"],
            {
                "snapshot_id": row["snapshot_id"],
                "session_id": row["session_id"],
                "session_agent_id": session_agent_id,
                "state_version": row["state_version"],
                "status": row["status"],
                "reason": row["reason"],
                "state_json": row["state_json"] or "{}",
                "created_at": _parse_timestamp(row["created_at"]),
            },
            "snapshot_id",
        )


def _insert_actions(connection, tables: dict, runtime_path: Path, selected_branches: dict[str, str], agent_ids: dict[tuple[str, str], str]) -> None:
    for row in list_agent_actions(runtime_path):
        if selected_branches.get(row["session_id"]) != row["branch_id"]:
            continue
        session_agent_id = agent_ids.get((row["session_id"], row["agent_id"]))
        if session_agent_id is None:
            continue
        _insert_if_missing(
            connection,
            tables["agent_actions"],
            {
                "action_id": row["action_event_id"],
                "session_id": row["session_id"],
                "session_agent_id": session_agent_id,
                "action": row["action"],
                "intent": row["intent"],
                "target": row["target"],
                "source": row["source"],
                "status": row["status"],
                "detail_json": row["detail_json"] or "{}",
                "queued_at": _parse_timestamp(row["created_at"]),
                "applied_at": _parse_timestamp(row["applied_at"]),
                "discarded_at": _parse_timestamp(row["discarded_at"]),
            },
            "action_id",
        )


def _insert_dialogues(connection, tables: dict, runtime_path: Path, selected_branches: dict[str, str], agent_ids: dict[tuple[str, str], str]) -> None:
    for row in list_agent_dialogues(runtime_path):
        if selected_branches.get(row["session_id"]) != row["branch_id"]:
            continue
        session_agent_id = agent_ids.get((row["session_id"], row["agent_id"]))
        if session_agent_id is None:
            continue
        _insert_if_missing(
            connection,
            tables["agent_dialogues"],
            {
                "dialogue_id": row["dialogue_id"],
                "session_id": row["session_id"],
                "session_agent_id": session_agent_id,
                "user_message": row["message"],
                "reply": row["reply"],
                "generator_mode": row["generator_mode"],
                "model_name": row["model_name"],
                "context_summary": row["context_summary"],
                "llm_module_binding_id": None,
                "created_at": _parse_timestamp(row["created_at"]),
            },
            "dialogue_id",
        )


def _insert_relation_events(connection, tables: dict, runtime_path: Path, selected_branches: dict[str, str], agent_ids: dict[tuple[str, str], str]) -> None:
    for row in list_relation_events(runtime_path):
        if selected_branches.get(row["session_id"]) != row["branch_id"]:
            continue
        _insert_if_missing(
            connection,
            tables["relation_events"],
            {
                "relation_event_id": row["relation_event_id"],
                "session_id": row["session_id"],
                "relation_session_agent_id": agent_ids.get((row["session_id"], row["agent_id"])),
                "source_session_agent_id": agent_ids.get((row["session_id"], row["source_agent_id"])),
                "target_session_agent_id": agent_ids.get((row["session_id"], row["target_agent_id"])),
                "source_name": row["source_name"],
                "target_name": row["target_name"],
                "change": row["change"],
                "note": row["note"],
                "status": row["status"],
                "last_action": row["last_action"] or "",
                "state_json": row["state_json"] or "{}",
                "created_at": _parse_timestamp(row["created_at"]),
            },
            "relation_event_id",
        )


def import_worldline_runtime(connection, tables: dict, runtime_path: Path) -> WorldlineRuntimeImportResult:
    try:
        selected_branches, anomalies = _load_selected_branches(runtime_path)
        if not selected_branches:
            return WorldlineRuntimeImportResult(imported=False, anomalies=anomalies)
        agent_ids, session_anomalies = _import_session_agents(connection, tables, runtime_path, selected_branches)
        _insert_snapshots(connection, tables, runtime_path, selected_branches, agent_ids)
        _insert_actions(connection, tables, runtime_path, selected_branches, agent_ids)
        _insert_dialogues(connection, tables, runtime_path, selected_branches, agent_ids)
        _insert_relation_events(connection, tables, runtime_path, selected_branches, agent_ids)
        return WorldlineRuntimeImportResult(
            imported=not session_anomalies,
            anomalies=(*anomalies, *session_anomalies),
        )
    except sqlite3.DatabaseError:
        return WorldlineRuntimeImportResult(
            imported=False,
            anomalies=(f"{runtime_path.as_posix()}: invalid runtime.sqlite3 database",),
        )
