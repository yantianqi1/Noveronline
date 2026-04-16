"""Test archive memory timeline via LongTermMemoryStore with in-memory engine."""

from sqlalchemy import create_engine

from app.database import init_db
from app.repositories.archive_repo import ArchiveRepository
from app.services.agents.memory import LongTermMemoryStore


def _make_engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    return engine


def _seed_legacy_memory(repo: ArchiveRepository) -> None:
    """Insert a legacy-style canon memory row for testing."""
    repo.upsert_memory({
        "memory_id": "ltm_legacy",
        "project_id": "proj_test",
        "archive_id": "archive_demo",
        "agent_id": "agent_demo",
        "memory_type": "strategy",
        "normalized_subject": "公开密信",
        "summary": "沈夜决定公开一页密信。",
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
    # Simulate the bootstrap_legacy event
    import uuid
    repo.log_memory_event({
        "event_id": f"evt_{uuid.uuid4().hex[:12]}",
        "project_id": "proj_test",
        "memory_id": "ltm_legacy",
        "archive_id": "archive_demo",
        "normalized_subject": "公开密信",
        "memory_type": "strategy",
        "event_type": "bootstrap_legacy",
        "memory_layer": "canon",
        "status": "active",
        "version": 1,
        "parent_memory_id": "",
        "source_session_id": "",
        "source_branch_id": "",
        "summary": "沈夜决定公开一页密信。",
        "evidence_json": "[]",
        "created_at": "2026-03-20T10:00:00",
    })


def test_archive_memory_timeline_exposes_active_heads_and_event_chain():
    engine = _make_engine()
    repo = ArchiveRepository(engine)
    _seed_legacy_memory(repo)

    store = LongTermMemoryStore(repo=repo)
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
        project_id="proj_test",
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
