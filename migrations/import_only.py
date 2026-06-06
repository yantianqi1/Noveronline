from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

from sqlalchemy import MetaData, select

from migrations.db_runtime import build_engine, load_metadata
from migrations.import_plan import ImportPlanEntry, build_import_plan
from migrations.object_registry_plan import build_object_registry_plan
from migrations.sqlite_extractors.archive_library import (
    list_archives,
    list_memories,
    list_memory_events,
)
from migrations.sqlite_extractors.llm_facility import (
    list_llm_channels,
    list_llm_models,
    list_llm_module_bindings,
)
from migrations.sqlite_extractors.chapter_meta import (
    list_chapter_history_items,
    list_chapter_meta,
)
from migrations.sqlite_extractors.task_runtime import list_task_runs
from migrations.task_runtime_importer import import_task_runtime_row
from migrations.sqlite_extractors.worldline_prepare import (
    list_prepare_runs,
    list_prepared_agent_dossiers,
)
from migrations.worldline_runtime_importer import import_worldline_runtime


LEGACY_WORKSPACE_ID = "legacy-workspace"
ID_DIGEST_LENGTH = 16
DEFAULT_TIMESTAMP = datetime(2026, 4, 11, tzinfo=timezone.utc)


@dataclass(frozen=True)
class ImportOnlyReport:
    metadata: MetaData
    workspace_count: int
    project_count: int
    artifact_object_count: int
    manuscript_count: int
    artifact_count: int
    skipped_rebuild_refs: tuple[str, ...]
    anomalies: tuple[str, ...]
    blocked_targets: tuple[str, ...]


def _stable_id(prefix: str, seed: str) -> str:
    digest = __import__("hashlib").sha256(seed.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:ID_DIGEST_LENGTH]}"


def _load_project_payload(uploads_root: Path, relative_path: str) -> dict:
    return json.loads((uploads_root / relative_path).read_text(encoding="utf-8"))


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


def _ensure_workspace(connection, tables: dict) -> None:
    table = tables["workspaces"]
    _insert_if_missing(
        connection,
        table,
        {
            "workspace_id": LEGACY_WORKSPACE_ID,
            "name": "Legacy Imported Workspace",
            "created_at": DEFAULT_TIMESTAMP,
            "updated_at": DEFAULT_TIMESTAMP,
        },
        "workspace_id",
    )


def _import_project(connection, tables: dict, uploads_root: Path, entry: ImportPlanEntry) -> None:
    payload = _load_project_payload(uploads_root, entry.relative_path)
    _ensure_workspace(connection, tables)
    _insert_if_missing(
        connection,
        tables["projects"],
        {
            "project_id": payload["project_id"],
            "workspace_id": LEGACY_WORKSPACE_ID,
            "name": payload.get("name", payload["project_id"]),
            "legacy_status": payload.get("status"),
            "analysis_summary": payload.get("analysis_summary"),
            "created_at": _parse_timestamp(payload.get("created_at")),
            "updated_at": _parse_timestamp(payload.get("updated_at") or payload.get("created_at")),
        },
        "project_id",
    )


def _insert_artifact_object(connection, tables: dict, plan_entry) -> str:
    artifact_object_id = _stable_id("obj", plan_entry.relative_path)
    _insert_if_missing(
        connection,
        tables["artifact_objects"],
        {
            "artifact_object_id": artifact_object_id,
            "bucket": plan_entry.bucket,
            "storage_key": plan_entry.storage_key,
            "source_relative_path": plan_entry.relative_path,
            "sha256": plan_entry.sha256,
            "size_bytes": plan_entry.size_bytes,
            "content_type": plan_entry.content_type,
            "created_at": DEFAULT_TIMESTAMP,
            "updated_at": DEFAULT_TIMESTAMP,
        },
        "artifact_object_id",
    )
    return artifact_object_id


def _import_object_bound_entry(connection, tables: dict, import_entry: ImportPlanEntry, object_entry) -> None:
    artifact_object_id = _insert_artifact_object(connection, tables, object_entry)
    project_id = object_entry.owner_id
    filename = Path(import_entry.relative_path).name
    if import_entry.target == "manuscripts+artifact_objects":
        _insert_if_missing(
            connection,
            tables["manuscripts"],
            {
                "manuscript_id": _stable_id("man", import_entry.relative_path),
                "project_id": project_id,
                "artifact_object_id": artifact_object_id,
                "original_filename": filename,
                "content_type": object_entry.content_type or "application/octet-stream",
                "storage_key": object_entry.storage_key,
                "size_bytes": object_entry.size_bytes,
                "created_at": DEFAULT_TIMESTAMP,
                "updated_at": DEFAULT_TIMESTAMP,
            },
            "manuscript_id",
        )
        return
    _insert_if_missing(
        connection,
        tables["artifacts"],
        {
            "artifact_id": _stable_id("art", import_entry.relative_path),
            "project_id": project_id,
            "artifact_object_id": artifact_object_id,
            "artifact_type": filename,
            "semantic_type": import_entry.target,
            "storage_key": object_entry.storage_key,
            "sha256": object_entry.sha256,
            "size_bytes": object_entry.size_bytes,
            "content_type": object_entry.content_type,
            "created_at": DEFAULT_TIMESTAMP,
            "updated_at": DEFAULT_TIMESTAMP,
        },
        "artifact_id",
    )


def _count_rows(connection, tables: dict, table_name: str) -> int:
    return len(connection.execute(select(tables[table_name])).all())


def _project_exists(connection, tables: dict, project_id: str | None) -> bool:
    if not project_id:
        return False
    row = connection.execute(
        select(tables["projects"].c.project_id).where(tables["projects"].c.project_id == project_id)
    ).first()
    return row is not None


def _entry_project_id(relative_path: str) -> str | None:
    parts = Path(relative_path).parts
    if len(parts) >= 2 and parts[0] == "projects":
        return parts[1]
    return None


def _secret_ref(api_key: str) -> str:
    return f"secret://legacy-llm/{_stable_id('key', api_key)}"


def _import_llm_facility(connection, tables: dict, database_path: Path) -> None:
    provider_ids: dict[str, str] = {}
    channel_ids: dict[str, str] = {}
    model_ids: dict[tuple[str, str], str] = {}
    for row in list_llm_channels(database_path):
        provider_id = _stable_id("llmp", row["channel_key"])
        channel_id = _stable_id("llmc", row["channel_key"])
        provider_ids[row["channel_key"]] = provider_id
        channel_ids[row["channel_key"]] = channel_id
        _insert_if_missing(
            connection,
            tables["llm_providers"],
            {
                "llm_provider_id": provider_id,
                "provider_key": row["channel_key"],
                "provider_type": "openai-compatible",
                "name": row["name"],
                "base_url": row["base_url"],
                "auth_secret_ref": _secret_ref(row["api_key"]),
                "status": "active" if row["is_enabled"] else "disabled",
                "created_at": _parse_timestamp(row["created_at"]),
                "updated_at": _parse_timestamp(row["updated_at"]),
            },
            "llm_provider_id",
        )
        _insert_if_missing(
            connection,
            tables["llm_channels"],
            {
                "llm_channel_id": channel_id,
                "llm_provider_id": provider_id,
                "channel_key": row["channel_key"],
                "name": row["name"],
                "max_concurrency": row["max_concurrency"],
                "timeout_ms": 60000,
                "is_enabled": bool(row["is_enabled"]),
                "created_at": _parse_timestamp(row["created_at"]),
                "updated_at": _parse_timestamp(row["updated_at"]),
            },
            "llm_channel_id",
        )
    for row in list_llm_models(database_path):
        model_id = _stable_id("llmm", f"{row['channel_key']}:{row['model_id']}")
        model_ids[(row["channel_key"], row["model_id"])] = model_id
        _insert_if_missing(
            connection,
            tables["llm_models"],
            {
                "llm_model_id": model_id,
                "llm_channel_id": channel_ids[row["channel_key"]],
                "provider_model_id": row["model_id"],
                "display_name": row["model_id"],
                "synced_at": _parse_timestamp(row["fetched_at"]),
            },
            "llm_model_id",
        )
    for row in list_llm_module_bindings(database_path):
        _insert_if_missing(
            connection,
            tables["llm_module_bindings"],
            {
                "llm_module_binding_id": _stable_id("llmb", row["module_key"]),
                "module_key": row["module_key"],
                "llm_channel_id": channel_ids[row["channel_key"]],
                "llm_model_id": model_ids[(row["channel_key"], row["model_id"])],
                "updated_at": _parse_timestamp(row["updated_at"]),
            },
            "llm_module_binding_id",
        )


def _import_archive_library(connection, tables: dict, database_path: Path) -> None:
    archive_project_ids: dict[str, str] = {}
    for row in list_archives(database_path):
        entity_id = _stable_id("ent", f"{row['project_id']}:{row['entity_uuid']}")
        archive_project_ids[row["archive_id"]] = row["project_id"]
        _insert_if_missing(
            connection,
            tables["entities"],
            {
                "entity_id": entity_id,
                "project_id": row["project_id"],
                "entity_uuid": row["entity_uuid"],
                "entity_kind": row["entity_type"],
                "canonical_name": row["entity_name"],
                "display_name": row["entity_name"],
                "summary": "",
                "created_at": _parse_timestamp(row["synced_at"]),
                "updated_at": _parse_timestamp(row["synced_at"]),
            },
            "entity_id",
        )
        _insert_if_missing(
            connection,
            tables["archives"],
            {
                "archive_id": row["archive_id"],
                "project_id": row["project_id"],
                "entity_id": entity_id,
                "archive_type": row["entity_type"],
                "agent_kind": row["agent_kind"],
                "importance_tier": row["importance_tier"],
                "selected_importance_tier": row["selected_importance_tier"],
                "template_key": row["template_key"],
                "template_version": row["template_version"],
                "created_at": _parse_timestamp(row["synced_at"]),
                "updated_at": _parse_timestamp(row["synced_at"]),
            },
            "archive_id",
        )
    for row in list_memories(database_path):
        _insert_if_missing(
            connection,
            tables["memories"],
            {
                "memory_id": row["memory_id"],
                "project_id": archive_project_ids[row["archive_id"]],
                "archive_id": row["archive_id"],
                "memory_type": row["memory_type"],
                "memory_layer": row["memory_layer"],
                "status": row["status"],
                "normalized_subject": row["normalized_subject"],
                "summary": row["summary"],
                "created_at": _parse_timestamp(row["created_at"]),
                "updated_at": _parse_timestamp(row["updated_at"]),
            },
            "memory_id",
        )
    for row in list_memory_events(database_path):
        _insert_if_missing(
            connection,
            tables["memory_events"],
            {
                "memory_event_id": row["event_id"],
                "memory_id": row["memory_id"],
                "archive_id": row["archive_id"],
                "event_type": row["event_type"],
                "actor_type": "migration",
                "actor_ref": "legacy-archive-library",
                "created_at": _parse_timestamp(row["created_at"]),
            },
            "memory_event_id",
        )


def _import_worldline_prepare(connection, tables: dict, database_path: Path) -> bool:
    try:
        rows = list_prepare_runs(database_path)
    except sqlite3.DatabaseError:
        return False
    if not rows:
        return True
    imported = False
    for row in rows:
        if row["project_id"] and not _project_exists(connection, tables, row["project_id"]):
            return False
        imported = True
        _insert_if_missing(
            connection,
            tables["worldline_preparations"],
            {
                "prepare_id": row["prepare_id"],
                "project_id": row["project_id"] or None,
                "status": row["status"],
                "session_scope": row["session_scope"],
                "focus_question": row["focus_question"],
                "started_session_id": row["started_session_id"] or None,
                "created_at": _parse_timestamp(row["created_at"]),
                "updated_at": _parse_timestamp(row["updated_at"]),
            },
            "prepare_id",
        )
    for row in list_prepared_agent_dossiers(database_path):
        _insert_if_missing(
            connection,
            tables["prepared_agent_dossiers"],
            {
                "prepared_agent_dossier_id": _stable_id("pad", f"{row['prepare_id']}:{row['agent_id']}"),
                "prepare_id": row["prepare_id"],
                "agent_id": row["agent_id"],
                "agent_kind": row["agent_kind"],
                "display_name": row["display_name"],
                "template_key": row["template_key"],
                "template_version": row["template_version"],
                "created_at": _parse_timestamp(row["created_at"]),
                "updated_at": _parse_timestamp(row["updated_at"]),
            },
            "prepared_agent_dossier_id",
        )
    return imported


def _import_worldline_session(connection, tables: dict, session_path: Path) -> bool:
    payload = json.loads(session_path.read_text(encoding="utf-8"))
    project_id = payload.get("project_id")
    if project_id and not _project_exists(connection, tables, project_id):
        return False
    session_id = payload["session_id"]
    created_at = _parse_timestamp(payload.get("created_at"))
    updated_at = _parse_timestamp(payload.get("updated_at") or payload.get("created_at"))
    _insert_if_missing(
        connection,
        tables["worldline_sessions"],
        {
            "session_id": session_id,
            "project_id": project_id or None,
            "session_scope": payload.get("session_scope", "project"),
            "simulation_goal": payload.get("simulation_goal", ""),
            "focus_question": payload.get("focus_question", ""),
            "status": payload.get("status", "running"),
            "created_from_prepare_run_id": payload.get("prepare_id") or None,
            "created_at": created_at,
            "updated_at": updated_at,
        },
        "session_id",
    )
    branches = payload.get("branches", [])
    main_branch = branches[0] if branches else {}
    world_state_id = _stable_id("wst", f"{session_id}:1")
    _insert_if_missing(
        connection,
        tables["world_states"],
        {
            "world_state_id": world_state_id,
            "session_id": session_id,
            "version_no": 1,
            "is_current": True,
            "created_at": updated_at,
        },
        "world_state_id",
    )
    for event in main_branch.get("timeline", []):
        _insert_if_missing(
            connection,
            tables["timeline_events"],
            {
                "timeline_event_id": event["event_id"],
                "session_id": session_id,
                "world_state_id": world_state_id,
                "step_no": event.get("step", 0),
                "event_type": event.get("event_type", "evolution"),
                "title": event.get("title", ""),
                "summary": event.get("summary", ""),
                "status": event.get("status", "canon"),
                "created_at": _parse_timestamp(event.get("created_at")),
            },
            "timeline_event_id",
        )
    return True


def _import_task_runtime(connection, tables: dict, database_path: Path) -> None:
    for row in list_task_runs(database_path):
        import_task_runtime_row(connection, tables, row)


def _import_chapter_meta(connection, tables: dict, database_path: Path) -> None:
    for row in list_chapter_meta(database_path):
        _insert_if_missing(
            connection,
            tables["chapters"],
            {
                "chapter_id": row["chapter_id"],
                "project_id": row["project_id"],
                "chapter_order": row["chapter_order"],
                "title": row["title"],
                "summary_text": row["summary_text"],
                "timeline_note": row["timeline_note"],
                "created_at": _parse_timestamp(row["created_at"]),
                "updated_at": _parse_timestamp(row["updated_at"]),
            },
            "chapter_id",
        )
    for row in list_chapter_history_items(database_path):
        _insert_if_missing(
            connection,
            tables["chapter_history_items"],
            {
                "chapter_history_item_id": _stable_id(
                    "chi", f"{row['project_id']}:{row['chapter_id']}:{row['item_type']}:{row['summary_text']}"
                ),
                "project_id": row["project_id"],
                "chapter_id": row["chapter_id"],
                "chapter_order": row["chapter_order"],
                "item_type": row["item_type"],
                "subject_key": row["subject_key"],
                "summary_text": row["summary_text"],
                "created_at": _parse_timestamp(row["created_at"]),
                "updated_at": _parse_timestamp(row["updated_at"]),
            },
            "chapter_history_item_id",
        )


def run_import_only(uploads_root: Path, database_url: str) -> ImportOnlyReport:
    metadata = load_metadata()
    engine = build_engine(database_url)
    metadata.create_all(engine)
    import_plan = build_import_plan(uploads_root)
    object_plan = build_object_registry_plan(uploads_root)
    object_entries = {entry.relative_path: entry for entry in object_plan.entries}
    blocked_targets: list[str] = []
    runtime_entries: list[ImportPlanEntry] = []
    runtime_anomalies: list[str] = []
    with engine.begin() as connection:
        tables = metadata.tables
        for entry in import_plan.entries:
            if entry.target == "session_agents+agent_state_snapshots+agent_actions+agent_dialogues+relation_events":
                runtime_entries.append(entry)
                continue
            if entry.target == "projects":
                _import_project(connection, tables, uploads_root, entry)
                continue
            if entry.target == "workflow_runs+workflow_steps":
                _import_task_runtime(connection, tables, uploads_root / entry.relative_path)
                continue
            if entry.target == "chapters+chapter_history_items":
                _import_chapter_meta(connection, tables, uploads_root / entry.relative_path)
                continue
            if entry.target == "llm_channels+llm_models+llm_module_bindings":
                _import_llm_facility(connection, tables, uploads_root / entry.relative_path)
                continue
            if entry.target == "archives+memories+memory_events":
                _import_archive_library(connection, tables, uploads_root / entry.relative_path)
                continue
            if entry.target == "worldline_preparations":
                if _import_worldline_prepare(connection, tables, uploads_root / entry.relative_path):
                    continue
            if entry.target == "worldline_sessions+world_states+timeline_events":
                if _import_worldline_session(connection, tables, uploads_root / entry.relative_path):
                    continue
            if entry.object_storage_key is not None:
                _import_object_bound_entry(connection, tables, entry, object_entries[entry.relative_path])
                continue
            blocked_targets.append(f"{entry.relative_path} -> {entry.target}")
        for entry in runtime_entries:
            result = import_worldline_runtime(connection, tables, uploads_root / entry.relative_path)
            runtime_anomalies.extend(result.anomalies)
            if result.imported:
                continue
            blocked_targets.append(f"{entry.relative_path} -> {entry.target}")
        return ImportOnlyReport(
            metadata=metadata,
            workspace_count=_count_rows(connection, tables, "workspaces"),
            project_count=_count_rows(connection, tables, "projects"),
            artifact_object_count=_count_rows(connection, tables, "artifact_objects"),
            manuscript_count=_count_rows(connection, tables, "manuscripts"),
            artifact_count=_count_rows(connection, tables, "artifacts"),
            skipped_rebuild_refs=import_plan.skipped_rebuild_refs,
            anomalies=tuple(dict.fromkeys((*import_plan.anomalies, *runtime_anomalies))),
            blocked_targets=tuple(blocked_targets),
        )


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        raise SystemExit("usage: python -m migrations.import_only <uploads_root> <database_url>")
    report = run_import_only(Path(args[0]), args[1])
    payload = {
        "workspace_count": report.workspace_count,
        "project_count": report.project_count,
        "artifact_object_count": report.artifact_object_count,
        "manuscript_count": report.manuscript_count,
        "artifact_count": report.artifact_count,
        "skipped_rebuild_refs": report.skipped_rebuild_refs,
        "anomalies": report.anomalies,
        "blocked_targets": report.blocked_targets,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
