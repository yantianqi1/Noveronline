"""全局主档案库 SQLite 存储。"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from ..config import Config
from ..models.project import ProjectManager


ARCHIVE_LIBRARY_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS archive_library (
        archive_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        project_name TEXT NOT NULL,
        entity_uuid TEXT NOT NULL,
        entity_name TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        agent_kind TEXT NOT NULL DEFAULT 'generic',
        importance_tier TEXT NOT NULL,
        recommended_importance_tier TEXT NOT NULL DEFAULT 'supporting',
        selected_importance_tier TEXT NOT NULL DEFAULT 'supporting',
        template_key TEXT NOT NULL DEFAULT 'generic.supporting.v1',
        template_version TEXT NOT NULL DEFAULT 'v1',
        entity_role TEXT NOT NULL,
        core_drive TEXT NOT NULL,
        surface_mask TEXT NOT NULL,
        hidden_tension TEXT NOT NULL,
        relationship_summary TEXT NOT NULL,
        agent_behavior_hint TEXT NOT NULL,
        human_ai_relation_tag TEXT NOT NULL,
        can_act_as_agent INTEGER NOT NULL DEFAULT 1,
        notable_risks_json TEXT NOT NULL DEFAULT '[]',
        template_sections_json TEXT NOT NULL DEFAULT '[]',
        template_payload_json TEXT NOT NULL DEFAULT '{}',
        template_metadata_json TEXT NOT NULL DEFAULT '{}',
        synced_at TEXT NOT NULL
    )
"""

TABLE_STATEMENTS = (
    ARCHIVE_LIBRARY_TABLE_SQL,
    """
    CREATE TABLE IF NOT EXISTS archive_sources (
        project_id TEXT PRIMARY KEY,
        project_name TEXT NOT NULL,
        file_path TEXT NOT NULL,
        file_mtime REAL NOT NULL,
        synced_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS archive_agent_memory (
        memory_id TEXT PRIMARY KEY,
        archive_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        memory_type TEXT NOT NULL,
        normalized_subject TEXT NOT NULL,
        summary TEXT NOT NULL,
        detail_json TEXT NOT NULL,
        source_kind TEXT NOT NULL,
        source_ref_id TEXT NOT NULL,
        salience REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS archive_agent_memory_events (
        event_id TEXT PRIMARY KEY,
        memory_id TEXT NOT NULL,
        archive_id TEXT NOT NULL,
        normalized_subject TEXT NOT NULL,
        memory_type TEXT NOT NULL,
        event_type TEXT NOT NULL,
        memory_layer TEXT NOT NULL,
        status TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        parent_memory_id TEXT NOT NULL DEFAULT '',
        source_session_id TEXT NOT NULL DEFAULT '',
        source_branch_id TEXT NOT NULL DEFAULT '',
        summary TEXT NOT NULL DEFAULT '',
        evidence_json TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL
    )
    """,
)

INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_archive_library_project_id ON archive_library(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_archive_library_entity_type ON archive_library(entity_type)",
    "CREATE INDEX IF NOT EXISTS idx_archive_library_agent_kind ON archive_library(agent_kind)",
    "CREATE INDEX IF NOT EXISTS idx_archive_library_importance_tier ON archive_library(importance_tier)",
    "CREATE INDEX IF NOT EXISTS idx_archive_library_template_key ON archive_library(template_key)",
    "CREATE INDEX IF NOT EXISTS idx_archive_library_entity_name ON archive_library(entity_name)",
    "CREATE INDEX IF NOT EXISTS idx_archive_agent_memory_archive_id ON archive_agent_memory(archive_id)",
    "CREATE INDEX IF NOT EXISTS idx_archive_agent_memory_layer_status ON archive_agent_memory(archive_id, memory_layer, status, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_archive_agent_memory_subject ON archive_agent_memory(archive_id, normalized_subject, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_archive_agent_memory_parent ON archive_agent_memory(parent_memory_id)",
    "CREATE INDEX IF NOT EXISTS idx_archive_agent_memory_events_archive ON archive_agent_memory_events(archive_id, normalized_subject, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_archive_agent_memory_events_memory ON archive_agent_memory_events(memory_id, created_at DESC)",
)

ARCHIVE_LIBRARY_COLUMNS = (
    ("agent_kind", "TEXT NOT NULL DEFAULT 'generic'"),
    ("recommended_importance_tier", "TEXT NOT NULL DEFAULT 'supporting'"),
    ("selected_importance_tier", "TEXT NOT NULL DEFAULT 'supporting'"),
    ("template_key", "TEXT NOT NULL DEFAULT 'generic.supporting.v1'"),
    ("template_version", "TEXT NOT NULL DEFAULT 'v1'"),
    ("notable_risks_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("template_sections_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("template_payload_json", "TEXT NOT NULL DEFAULT '{}'"),
    ("template_metadata_json", "TEXT NOT NULL DEFAULT '{}'"),
)

ARCHIVE_AGENT_MEMORY_COLUMNS = (
    ("memory_layer", "TEXT NOT NULL DEFAULT 'canon'"),
    ("status", "TEXT NOT NULL DEFAULT 'active'"),
    ("version", "INTEGER NOT NULL DEFAULT 1"),
    ("parent_memory_id", "TEXT NOT NULL DEFAULT ''"),
    ("source_session_id", "TEXT NOT NULL DEFAULT ''"),
    ("source_branch_id", "TEXT NOT NULL DEFAULT ''"),
    ("evidence_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("adopted_at", "TEXT"),
    ("rejected_at", "TEXT"),
)


class ArchiveLibraryStorage:
    """管理全局主档案库连接和建表。"""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or self.default_db_path()
        self.ensure_schema()

    @classmethod
    def default_db_path(cls) -> str:
        project_root = os.path.dirname(ProjectManager.PROJECTS_DIR) if getattr(ProjectManager, "PROJECTS_DIR", "") else ""
        upload_root = project_root or Config.UPLOAD_FOLDER
        return os.path.join(
            upload_root,
            "system",
            Config.ARCHIVE_LIBRARY_DB_FILENAME,
        )

    def ensure_schema(self) -> None:
        self._ensure_parent_dir()
        with self.connect() as connection:
            for statement in TABLE_STATEMENTS:
                connection.execute(statement)
            self._ensure_archive_library_columns(connection)
            self._ensure_archive_agent_memory_columns(connection)
            self._migrate_legacy_archive_library(connection)
            self._migrate_archive_agent_memory_v2(connection)
            for statement in INDEX_STATEMENTS:
                connection.execute(statement)
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

    def _ensure_archive_library_columns(self, connection: sqlite3.Connection) -> None:
        existing = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(archive_library)").fetchall()
        }
        for name, definition in ARCHIVE_LIBRARY_COLUMNS:
            if name in existing:
                continue
            connection.execute(f"ALTER TABLE archive_library ADD COLUMN {name} {definition}")

    def _ensure_archive_agent_memory_columns(self, connection: sqlite3.Connection) -> None:
        existing = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(archive_agent_memory)").fetchall()
        }
        for name, definition in ARCHIVE_AGENT_MEMORY_COLUMNS:
            if name in existing:
                continue
            connection.execute(f"ALTER TABLE archive_agent_memory ADD COLUMN {name} {definition}")

    def _migrate_legacy_archive_library(self, connection: sqlite3.Connection) -> None:
        existing = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(archive_library)").fetchall()
        }
        if "notable_risks" not in existing:
            return
        migrated_table = "archive_library__migrated"
        connection.execute(f"DROP TABLE IF EXISTS {migrated_table}")
        connection.execute(ARCHIVE_LIBRARY_TABLE_SQL.replace("archive_library", migrated_table, 1))
        migration_sql = """
            INSERT INTO __TABLE__ (
                archive_id, project_id, project_name, entity_uuid, entity_name, entity_type,
                agent_kind, importance_tier, recommended_importance_tier, selected_importance_tier,
                template_key, template_version, entity_role, core_drive, surface_mask, hidden_tension,
                relationship_summary, agent_behavior_hint, human_ai_relation_tag,
                can_act_as_agent, notable_risks_json, template_sections_json, template_payload_json,
                template_metadata_json, synced_at
            )
            SELECT
                archive_id, project_id, project_name, entity_uuid, entity_name, entity_type,
                COALESCE(agent_kind, 'generic'), importance_tier,
                COALESCE(recommended_importance_tier, importance_tier, 'supporting'),
                COALESCE(selected_importance_tier, importance_tier, 'supporting'),
                COALESCE(template_key, 'generic.supporting.v1'), COALESCE(template_version, 'v1'),
                entity_role, core_drive, surface_mask, hidden_tension, relationship_summary,
                agent_behavior_hint, human_ai_relation_tag, COALESCE(can_act_as_agent, 1),
                CASE
                    WHEN TRIM(COALESCE(notable_risks_json, '')) NOT IN ('', '[]') THEN notable_risks_json
                    WHEN TRIM(COALESCE(notable_risks, '')) = '' THEN '[]'
                    ELSE notable_risks
                END,
                COALESCE(template_sections_json, '[]'),
                COALESCE(template_payload_json, '{}'),
                COALESCE(template_metadata_json, '{}'),
                synced_at
            FROM archive_library
        """
        connection.execute(migration_sql.replace("__TABLE__", migrated_table))
        connection.execute("DROP TABLE archive_library")
        connection.execute(f"ALTER TABLE {migrated_table} RENAME TO archive_library")

    def _migrate_archive_agent_memory_v2(self, connection: sqlite3.Connection) -> None:
        connection.execute("DROP INDEX IF EXISTS idx_archive_agent_memory_identity")
        connection.execute(
            """
            UPDATE archive_agent_memory
            SET memory_layer = COALESCE(NULLIF(memory_layer, ''), 'canon'),
                status = COALESCE(NULLIF(status, ''), 'active'),
                version = COALESCE(version, 1),
                parent_memory_id = COALESCE(parent_memory_id, ''),
                source_session_id = COALESCE(source_session_id, ''),
                source_branch_id = COALESCE(source_branch_id, ''),
                evidence_json = CASE
                    WHEN TRIM(COALESCE(evidence_json, '')) = '' THEN '[]'
                    ELSE evidence_json
                END,
                adopted_at = COALESCE(adopted_at, created_at)
            """
        )
        rows = connection.execute(
            """
            SELECT memory_id, archive_id, normalized_subject, memory_type, memory_layer, status, version, created_at, summary, evidence_json
            FROM archive_agent_memory
            WHERE memory_id NOT IN (SELECT memory_id FROM archive_agent_memory_events)
            """
        ).fetchall()
        for row in rows:
            connection.execute(
                """
                INSERT INTO archive_agent_memory_events (
                    event_id, memory_id, archive_id, normalized_subject, memory_type,
                    event_type, memory_layer, status, version, parent_memory_id,
                    source_session_id, source_branch_id, summary, evidence_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', '', ?, ?, ?)
                """,
                (
                    f"evt_bootstrap_{row['memory_id']}",
                    row["memory_id"],
                    row["archive_id"],
                    row["normalized_subject"],
                    row["memory_type"],
                    "bootstrap_legacy",
                    row["memory_layer"],
                    row["status"],
                    row["version"],
                    row["summary"],
                    row["evidence_json"],
                    row["created_at"],
                ),
            )
