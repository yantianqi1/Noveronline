"""世界线 prepare 产物 SQLite 存储。"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from typing import Dict, Iterator, List, Optional


CREATE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS prepare_runs (
        prepare_id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        project_id TEXT,
        graph_id TEXT NOT NULL,
        session_scope TEXT NOT NULL,
        status TEXT NOT NULL,
        stage TEXT NOT NULL,
        can_start INTEGER NOT NULL DEFAULT 0,
        focus_question TEXT NOT NULL,
        branch_count INTEGER NOT NULL,
        source_summary_json TEXT NOT NULL,
        source_json TEXT NOT NULL,
        world_variables_json TEXT NOT NULL,
        input_payload_json TEXT NOT NULL,
        source_archive_ids_json TEXT NOT NULL,
        source_project_ids_json TEXT NOT NULL,
        source_archive_count INTEGER NOT NULL DEFAULT 0,
        started_session_id TEXT NOT NULL DEFAULT '',
        error TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prepared_agent_dossiers (
        prepare_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        agent_kind TEXT NOT NULL,
        display_name TEXT NOT NULL,
        source_archive_id TEXT NOT NULL DEFAULT '',
        source_entity_uuid TEXT NOT NULL DEFAULT '',
        importance_tier TEXT NOT NULL,
        template_key TEXT NOT NULL,
        template_version TEXT NOT NULL,
        template_sections_json TEXT NOT NULL,
        model_name TEXT NOT NULL,
        validation_errors_json TEXT NOT NULL,
        public_profile_json TEXT NOT NULL,
        private_profile_json TEXT NOT NULL,
        runtime_seed_state_json TEXT NOT NULL,
        relationship_view_json TEXT NOT NULL,
        memory_seed_summary_json TEXT NOT NULL,
        source_evidence_summary_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (prepare_id, agent_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prepare_event_log (
        event_id TEXT PRIMARY KEY,
        prepare_id TEXT NOT NULL,
        stage TEXT NOT NULL,
        level TEXT NOT NULL,
        message TEXT NOT NULL,
        detail_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
)

INDEX_STATEMENTS = (
    # 事件日志排序
    "CREATE INDEX IF NOT EXISTS idx_event_log_prepare "
    "ON prepare_event_log(prepare_id, created_at ASC)",
    # 按 task_id 查找 prepare_runs
    "CREATE INDEX IF NOT EXISTS idx_prepare_runs_task "
    "ON prepare_runs(task_id)",
)

JSON_FIELDS = {
    "source_summary_json": "source_summary",
    "source_json": "source",
    "world_variables_json": "world_variables",
    "input_payload_json": "input_payload",
    "source_archive_ids_json": "source_archive_ids",
    "source_project_ids_json": "source_project_ids",
    "template_sections_json": "template_sections",
    "validation_errors_json": "validation_errors",
    "public_profile_json": "public_profile",
    "private_profile_json": "private_profile",
    "runtime_seed_state_json": "runtime_seed_state",
    "relationship_view_json": "relationship_view",
    "memory_seed_summary_json": "memory_seed_summary",
    "source_evidence_summary_json": "source_evidence_summary",
    "detail_json": "detail",
}


class WorldlinePrepareStorage:
    DB_FILENAME = "prepare.sqlite3"

    def __init__(self, container_dir: str):
        self.db_path = os.path.join(container_dir, "worldlines", self.DB_FILENAME)
        self.ensure_schema()

    def ensure_schema(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self.connect() as connection:
            for statement in CREATE_STATEMENTS:
                connection.execute(statement)
            for statement in INDEX_STATEMENTS:
                connection.execute(statement)
            connection.commit()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def save_run(self, payload: Dict[str, object]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO prepare_runs (
                    prepare_id, task_id, project_id, graph_id, session_scope, status, stage, can_start,
                    focus_question, branch_count, source_summary_json, source_json, world_variables_json,
                    input_payload_json, source_archive_ids_json, source_project_ids_json, source_archive_count,
                    started_session_id, error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(prepare_id) DO UPDATE SET
                    task_id = excluded.task_id,
                    project_id = excluded.project_id,
                    graph_id = excluded.graph_id,
                    session_scope = excluded.session_scope,
                    status = excluded.status,
                    stage = excluded.stage,
                    can_start = excluded.can_start,
                    focus_question = excluded.focus_question,
                    branch_count = excluded.branch_count,
                    source_summary_json = excluded.source_summary_json,
                    source_json = excluded.source_json,
                    world_variables_json = excluded.world_variables_json,
                    input_payload_json = excluded.input_payload_json,
                    source_archive_ids_json = excluded.source_archive_ids_json,
                    source_project_ids_json = excluded.source_project_ids_json,
                    source_archive_count = excluded.source_archive_count,
                    started_session_id = excluded.started_session_id,
                    error = excluded.error,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    payload["prepare_id"],
                    payload["task_id"],
                    payload.get("project_id"),
                    payload["graph_id"],
                    payload["session_scope"],
                    payload["status"],
                    payload["stage"],
                    int(bool(payload.get("can_start"))),
                    payload["focus_question"],
                    payload["branch_count"],
                    json.dumps(payload.get("source_summary", {}), ensure_ascii=False),
                    json.dumps(payload.get("source", {}), ensure_ascii=False),
                    json.dumps(payload.get("world_variables", []), ensure_ascii=False),
                    json.dumps(payload.get("input_payload", {}), ensure_ascii=False),
                    json.dumps(payload.get("source_archive_ids", []), ensure_ascii=False),
                    json.dumps(payload.get("source_project_ids", []), ensure_ascii=False),
                    int(payload.get("source_archive_count", 0)),
                    payload.get("started_session_id", ""),
                    payload.get("error"),
                    payload["created_at"],
                    payload["updated_at"],
                ),
            )
            connection.commit()

    def get_run(self, prepare_id: str) -> Optional[Dict[str, object]]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM prepare_runs WHERE prepare_id = ?",
                (prepare_id,),
            ).fetchone()
        return self._decode_row(row) if row else None

    def save_dossier(self, prepare_id: str, payload: Dict[str, object]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO prepared_agent_dossiers (
                    prepare_id, agent_id, agent_kind, display_name, source_archive_id, source_entity_uuid,
                    importance_tier, template_key, template_version, template_sections_json, model_name,
                    validation_errors_json, public_profile_json, private_profile_json, runtime_seed_state_json,
                    relationship_view_json, memory_seed_summary_json, source_evidence_summary_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(prepare_id, agent_id) DO UPDATE SET
                    agent_kind = excluded.agent_kind,
                    display_name = excluded.display_name,
                    source_archive_id = excluded.source_archive_id,
                    source_entity_uuid = excluded.source_entity_uuid,
                    importance_tier = excluded.importance_tier,
                    template_key = excluded.template_key,
                    template_version = excluded.template_version,
                    template_sections_json = excluded.template_sections_json,
                    model_name = excluded.model_name,
                    validation_errors_json = excluded.validation_errors_json,
                    public_profile_json = excluded.public_profile_json,
                    private_profile_json = excluded.private_profile_json,
                    runtime_seed_state_json = excluded.runtime_seed_state_json,
                    relationship_view_json = excluded.relationship_view_json,
                    memory_seed_summary_json = excluded.memory_seed_summary_json,
                    source_evidence_summary_json = excluded.source_evidence_summary_json,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    prepare_id,
                    payload["agent_id"],
                    payload["agent_kind"],
                    payload["display_name"],
                    str(payload.get("source_archive_id") or ""),
                    str(payload.get("source_entity_uuid") or ""),
                    payload["importance_tier"],
                    payload["template_key"],
                    payload["template_version"],
                    json.dumps(payload.get("template_sections", []), ensure_ascii=False),
                    payload["model_name"],
                    json.dumps(payload.get("validation_errors", []), ensure_ascii=False),
                    json.dumps(payload.get("public_profile", {}), ensure_ascii=False),
                    json.dumps(payload.get("private_profile", {}), ensure_ascii=False),
                    json.dumps(payload.get("runtime_seed_state", {}), ensure_ascii=False),
                    json.dumps(payload.get("relationship_view", {}), ensure_ascii=False),
                    json.dumps(payload.get("memory_seed_summary", []), ensure_ascii=False),
                    json.dumps(payload.get("source_evidence_summary", []), ensure_ascii=False),
                    payload["created_at"],
                    payload["updated_at"],
                ),
            )
            connection.commit()

    def list_dossiers(self, prepare_id: str) -> List[Dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM prepared_agent_dossiers WHERE prepare_id = ? ORDER BY display_name ASC",
                (prepare_id,),
            ).fetchall()
        return [self._decode_row(row) for row in rows]

    def get_dossier(self, prepare_id: str, agent_id: str) -> Optional[Dict[str, object]]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM prepared_agent_dossiers WHERE prepare_id = ? AND agent_id = ?",
                (prepare_id, agent_id),
            ).fetchone()
        return self._decode_row(row) if row else None

    def append_event(self, payload: Dict[str, object]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO prepare_event_log (event_id, prepare_id, stage, level, message, detail_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["event_id"],
                    payload["prepare_id"],
                    payload["stage"],
                    payload["level"],
                    payload["message"],
                    json.dumps(payload.get("detail", {}), ensure_ascii=False),
                    payload["created_at"],
                ),
            )
            connection.commit()

    def list_events(self, prepare_id: str) -> List[Dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM prepare_event_log WHERE prepare_id = ? ORDER BY created_at ASC",
                (prepare_id,),
            ).fetchall()
        return [self._decode_row(row) for row in rows]

    def _decode_row(self, row) -> Dict[str, object]:
        payload = dict(row)
        for source_key, target_key in JSON_FIELDS.items():
            if source_key not in payload:
                continue
            payload[target_key] = json.loads(payload[source_key] or "null")
            del payload[source_key]
        if "can_start" in payload:
            payload["can_start"] = bool(payload["can_start"])
        return payload
