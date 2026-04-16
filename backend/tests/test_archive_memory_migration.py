"""Test that archive_agent_memory table created by SQLAlchemy has all v2 columns."""

from sqlalchemy import create_engine, inspect

from app.database import init_db
from app.repositories.archive_repo import ArchiveRepository


def test_archive_memory_table_has_v2_columns():
    """Verify the archive_agent_memory table schema includes all v2 columns."""
    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)

    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("archive_agent_memory")}

    expected_v2 = {
        "memory_layer", "status", "version", "parent_memory_id",
        "source_session_id", "source_branch_id", "evidence_json",
        "adopted_at", "rejected_at",
    }
    assert expected_v2 <= columns, f"Missing v2 columns: {expected_v2 - columns}"


def test_archive_memory_events_table_exists():
    """Verify the archive_agent_memory_events table is created."""
    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)

    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    assert "archive_agent_memory_events" in table_names


def test_archive_repo_upsert_and_read_memory():
    """Verify ArchiveRepository can insert and read back a memory row."""
    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    repo = ArchiveRepository(engine)

    repo.upsert_memory({
        "memory_id": "ltm_test",
        "project_id": "proj_test",
        "archive_id": "archive_demo",
        "agent_id": "agent_demo",
        "memory_type": "strategy",
        "normalized_subject": "test_subject",
        "summary": "test summary",
        "detail_json": "{}",
        "source_kind": "action_applied",
        "source_ref_id": "action_1",
        "salience": 0.8,
        "memory_layer": "canon",
        "status": "active",
        "version": 1,
        "parent_memory_id": "",
        "source_session_id": "",
        "source_branch_id": "",
        "evidence_json": "[]",
        "adopted_at": "2026-03-20T10:00:00",
        "rejected_at": None,
        "created_at": "2026-03-20T10:00:00",
        "updated_at": "2026-03-20T10:00:00",
    })

    row = repo.get_memory("ltm_test")
    assert row is not None
    assert row["memory_layer"] == "canon"
    assert row["status"] == "active"
    assert row["version"] == 1
    assert row["adopted_at"] == "2026-03-20T10:00:00"
