"""Unit tests for WorldlineSessionRepository."""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.database import init_db
from app.repositories.worldline_session_repo import WorldlineSessionRepository


def _build_engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    return engine


def _session_payload(session_id: str, *, project_id: str | None = "proj_a", scope: str = "project") -> dict:
    return {
        "session_id": session_id,
        "project_id": project_id,
        "graph_id": "graph_1",
        "simulation_goal": "探索分支",
        "focus_question": "主角会如何选择？",
        "branch_count": 2,
        "label": "Demo Session",
        "prepare_id": "prep_1",
        "session_scope": scope,
        "status": "running",
        "branches": [
            {"branch_id": "br_1", "title": "Branch A", "core_change": "decision-a"},
        ],
        "world_variables": [],
        "timeline_focus": [],
        "agent_behavior_axes": [],
        "source_summary": {"arc_count": 1},
        "source_archive_ids": ["arc_1", "arc_2"],
        "source_project_ids": ["proj_a"],
        "source_archive_count": 2,
        "created_at": "2026-04-17T00:00:00",
        "updated_at": "2026-04-17T00:00:00",
    }


def test_save_and_load_session_round_trips_payload():
    engine = _build_engine()
    repo = WorldlineSessionRepository(engine)
    payload = _session_payload("sess_round")

    repo.save_session(payload)
    loaded = repo.load_session("sess_round")

    assert loaded is not None
    assert loaded["session_id"] == "sess_round"
    assert loaded["project_id"] == "proj_a"
    assert loaded["simulation_goal"] == "探索分支"
    assert loaded["branches"][0]["branch_id"] == "br_1"
    assert loaded["source_archive_ids"] == ["arc_1", "arc_2"]


def test_save_session_is_idempotent_and_updates_timestamp():
    engine = _build_engine()
    repo = WorldlineSessionRepository(engine)
    repo.save_session(_session_payload("sess_idem"))
    repo.save_session({**_session_payload("sess_idem"), "status": "completed"})

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, created_at, updated_at FROM worldline_sessions WHERE session_id = :sid"),
            {"sid": "sess_idem"},
        ).fetchone()

    assert row is not None
    assert row[0] == "completed"
    # created_at remains the original value; updated_at is refreshed to now.
    assert row[1] == "2026-04-17T00:00:00"
    assert row[2] != row[1]


def test_list_sessions_filters_by_project_and_scope():
    engine = _build_engine()
    repo = WorldlineSessionRepository(engine)
    repo.save_session(_session_payload("sess_a", project_id="proj_a"))
    repo.save_session(_session_payload("sess_b", project_id="proj_b"))
    repo.save_session(_session_payload("sess_global", project_id=None, scope="global"))

    in_a = repo.list_sessions(project_id="proj_a")
    ids_a = [item["session_id"] for item in in_a]
    assert "sess_a" in ids_a and "sess_b" not in ids_a and "sess_global" not in ids_a

    global_only = repo.list_sessions(session_scope="global")
    assert [item["session_id"] for item in global_only] == ["sess_global"]


def test_delete_session_removes_row():
    engine = _build_engine()
    repo = WorldlineSessionRepository(engine)
    repo.save_session(_session_payload("sess_gone"))
    assert repo.load_session("sess_gone") is not None

    removed = repo.delete_session("sess_gone")

    assert removed == 1
    assert repo.load_session("sess_gone") is None


def test_list_sessions_orders_by_updated_at_desc():
    engine = _build_engine()
    repo = WorldlineSessionRepository(engine)
    first = _session_payload("sess_old")
    first["created_at"] = "2026-04-16T00:00:00"
    first["updated_at"] = "2026-04-16T00:00:00"
    repo.save_session(first)
    second = _session_payload("sess_new")
    second["created_at"] = "2026-04-17T00:00:00"
    second["updated_at"] = "2026-04-17T12:00:00"
    repo.save_session(second)

    listed = repo.list_sessions()
    ids = [item["session_id"] for item in listed]
    # repo.save_session overwrites updated_at to "now", so the later call wins.
    assert ids.index("sess_new") < ids.index("sess_old")
