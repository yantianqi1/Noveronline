"""世界线 agent 运行态 SQLite 存储。"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator


CREATE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS agent_registry (
        session_id TEXT NOT NULL,
        branch_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        agent_kind TEXT NOT NULL,
        display_name TEXT NOT NULL,
        source_ref TEXT NOT NULL,
        role TEXT NOT NULL,
        drive TEXT NOT NULL,
        tension TEXT NOT NULL,
        status TEXT NOT NULL,
        summary TEXT NOT NULL,
        can_chat INTEGER NOT NULL,
        can_act INTEGER NOT NULL,
        state_json TEXT NOT NULL,
        state_source TEXT NOT NULL,
        state_version INTEGER NOT NULL,
        last_action_at TEXT,
        last_dialogue_at TEXT,
        source_archive_id TEXT,
        source_entity_uuid TEXT,
        importance_tier TEXT NOT NULL DEFAULT 'supporting',
        template_key TEXT NOT NULL DEFAULT 'generic.supporting.v1',
        template_version TEXT NOT NULL DEFAULT 'v1',
        template_sections_json TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (session_id, branch_id, agent_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_state_snapshots (
        snapshot_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        branch_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        state_version INTEGER NOT NULL,
        status TEXT NOT NULL,
        reason TEXT NOT NULL,
        state_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_action_log (
        action_event_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        branch_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        display_name TEXT NOT NULL,
        action TEXT NOT NULL,
        intent TEXT NOT NULL,
        target TEXT NOT NULL,
        source TEXT NOT NULL,
        status TEXT NOT NULL,
        detail_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        applied_at TEXT,
        discarded_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_dialogue_log (
        dialogue_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        branch_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        display_name TEXT NOT NULL,
        message TEXT NOT NULL,
        reply TEXT NOT NULL,
        generator_mode TEXT NOT NULL,
        model_name TEXT NOT NULL,
        context_summary TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS relation_state_log (
        relation_event_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        branch_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        source_agent_id TEXT NOT NULL,
        target_agent_id TEXT NOT NULL,
        source_name TEXT NOT NULL,
        target_name TEXT NOT NULL,
        change TEXT NOT NULL,
        note TEXT NOT NULL,
        status TEXT NOT NULL,
        last_action TEXT NOT NULL,
        state_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_episodic_memory (
        memory_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        branch_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        archive_id TEXT NOT NULL DEFAULT '',
        memory_type TEXT NOT NULL,
        summary TEXT NOT NULL,
        detail_json TEXT NOT NULL,
        source_kind TEXT NOT NULL,
        source_ref_id TEXT NOT NULL,
        normalized_subject TEXT NOT NULL,
        salience REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
)

AGENT_REGISTRY_COLUMNS = (
    ("importance_tier", "TEXT NOT NULL DEFAULT 'supporting'"),
    ("template_key", "TEXT NOT NULL DEFAULT 'generic.supporting.v1'"),
    ("template_version", "TEXT NOT NULL DEFAULT 'v1'"),
    ("template_sections_json", "TEXT NOT NULL DEFAULT '[]'"),
)


class WorldlineRuntimeStorage:
    """管理单个容器下的 worldline runtime 数据库。"""

    DB_FILENAME = "runtime.sqlite3"

    def __init__(self, container_dir: str):
        self.db_path = os.path.join(container_dir, "worldlines", self.DB_FILENAME)
        self.ensure_schema()

    def ensure_schema(self) -> None:
        self._ensure_parent_dir()
        with self.connect() as connection:
            for statement in CREATE_STATEMENTS:
                connection.execute(statement)
            self._ensure_agent_registry_columns(connection)
            connection.commit()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self._ensure_parent_dir()
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def _ensure_parent_dir(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _ensure_agent_registry_columns(self, connection: sqlite3.Connection) -> None:
        existing = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(agent_registry)").fetchall()
        }
        for name, definition in AGENT_REGISTRY_COLUMNS:
            if name in existing:
                continue
            connection.execute(f"ALTER TABLE agent_registry ADD COLUMN {name} {definition}")
