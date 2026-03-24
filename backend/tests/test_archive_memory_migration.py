import sqlite3

from app.config import Config
from app.models.project import ProjectManager
from app.services.archive_library_storage import ArchiveLibraryStorage


def _configure_storage(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    ProjectManager.PROJECTS_DIR = str(upload_root / "projects")
    return upload_root


def test_archive_memory_storage_migrates_legacy_rows_to_v2(tmp_path, monkeypatch):
    upload_root = _configure_storage(tmp_path, monkeypatch)
    db_dir = upload_root / "system"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / Config.ARCHIVE_LIBRARY_DB_FILENAME
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE archive_agent_memory (
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
        """
    )
    connection.execute(
        """
        INSERT INTO archive_agent_memory (
            memory_id, archive_id, agent_id, memory_type, normalized_subject, summary,
            detail_json, source_kind, source_ref_id, salience, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "ltm_legacy",
            "archive_demo",
            "agent_demo",
            "strategy",
            "公开密信",
            "沈夜决定公开一页密信。",
            "{}",
            "action_applied",
            "action_1",
            0.8,
            "2026-03-20T10:00:00",
            "2026-03-20T10:00:00",
        ),
    )
    connection.commit()
    connection.close()

    storage = ArchiveLibraryStorage(str(db_path))
    with storage.connect() as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(archive_agent_memory)").fetchall()
        }
        row = connection.execute(
            "SELECT memory_layer, status, version, adopted_at FROM archive_agent_memory WHERE memory_id = ?",
            ("ltm_legacy",),
        ).fetchone()
        events = connection.execute(
            "SELECT event_type, memory_layer, status, version FROM archive_agent_memory_events WHERE memory_id = ?",
            ("ltm_legacy",),
        ).fetchall()

    assert {"memory_layer", "status", "version", "parent_memory_id", "source_session_id", "source_branch_id", "evidence_json", "adopted_at", "rejected_at"} <= columns
    assert row["memory_layer"] == "canon"
    assert row["status"] == "active"
    assert row["version"] == 1
    assert row["adopted_at"] == "2026-03-20T10:00:00"
    assert len(events) == 1
    assert events[0]["event_type"] == "bootstrap_legacy"
