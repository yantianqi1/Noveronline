import sqlite3

from app.config import Config
from app.models.project import ProjectManager
from app.services.agents.memory import LongTermMemoryStore
from app.services.archive_library_storage import ArchiveLibraryStorage


def _configure_storage(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    ProjectManager.PROJECTS_DIR = str(upload_root / "projects")
    return upload_root


def test_archive_memory_timeline_exposes_active_heads_and_event_chain(tmp_path, monkeypatch):
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
    store = LongTermMemoryStore(storage=storage)
    candidate_id = store.append_candidate(
        archive_id="archive_demo",
        agent_id="agent_demo",
        memory_type="strategy",
        summary="沈夜决定改为先公开半页密信。",
        detail={"intent": "缩小试探范围"},
        source_kind="action_applied",
        source_ref_id="action_2",
        normalized_subject="公开密信",
        salience=0.9,
        source_session_id="session_demo",
        source_branch_id="main",
        evidence=[{"snippet": "先公开半页密信"}],
    )
    store.promote_to_canon("archive_demo", candidate_id)

    timeline = store.list_memory_timeline("archive_demo", normalized_subject="公开密信")

    assert timeline["subject"] == "公开密信"
    assert timeline["active_canon"]["memory_layer"] == "canon"
    assert timeline["active_canon"]["status"] == "active"
    assert timeline["active_candidates"] == []
    assert timeline["head_memories"]
    assert timeline["memories"]
    assert timeline["events"]
    assert any(event["event_type"] == "bootstrap_legacy" for event in timeline["events"])
    assert any(event["event_type"] == "promote_to_canon" for event in timeline["events"])
    assert any(event["parent_memory_id"] == candidate_id for event in timeline["events"])
    assert all("summary" in event for event in timeline["events"])
