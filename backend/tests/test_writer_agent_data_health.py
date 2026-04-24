"""Tests for writer-agent data health self-check (Task 4 of 2026-04-19 optimization).

The orchestrator runs ``_collect_data_health_issues`` before the retrieval
planner fires, so the frontend can show a "your project is missing data X"
banner instead of letting the user stare at a silently-degraded writer run.

These are DB-only tests — they don't start the LLM router or the agent loop.
"""

from __future__ import annotations

from app.database import get_engine
from app.repositories.graph_repo import GraphRepository
from app.repositories.narrative_repo import NarrativeRepository
from app.repositories.worldline_session_repo import WorldlineSessionRepository
from app.services.writer_agent.orchestrator import _collect_data_health_issues


def _issue_codes(issues: list[dict]) -> set[str]:
    return {i["code"] for i in issues}


def test_empty_project_reports_all_three_issues():
    issues = _collect_data_health_issues("proj_blank")
    codes = _issue_codes(issues)
    assert "narrative_arcs_empty" in codes
    assert "story_graph_missing" in codes
    assert "worldline_sessions_empty" in codes


def test_severity_warning_for_core_tables():
    """narrative + graph are 'warning' severity; worldline is 'info'."""
    issues = _collect_data_health_issues("proj_blank_severity")
    by_code = {i["code"]: i for i in issues}
    assert by_code["narrative_arcs_empty"]["severity"] == "warning"
    assert by_code["story_graph_missing"]["severity"] == "warning"
    assert by_code["worldline_sessions_empty"]["severity"] == "info"


def test_narrative_arcs_populated_clears_that_issue():
    project_id = "proj_has_narrative"
    repo = NarrativeRepository(get_engine())
    repo.upsert_narrative_arc(
        project_id,
        {
            "arc_id": "arc_1",
            "summary": "something",
            "covered_segments_json": "[]",
            "created_at": "2026-04-18T00:00:00",
        },
    )
    issues = _collect_data_health_issues(project_id)
    codes = _issue_codes(issues)
    assert "narrative_arcs_empty" not in codes
    # Graph + worldline still missing
    assert "story_graph_missing" in codes
    assert "worldline_sessions_empty" in codes


def test_graph_populated_clears_that_issue():
    project_id = "proj_has_graph"
    repo = GraphRepository(get_engine())
    repo.save_snapshot(
        project_id,
        graph_id="g1",
        snapshot_data={
            "graph_name": "test",
            "built_at": "2026-04-18",
            "build_version": "v1",
            "nodes": [],
            "edges": [],
        },
    )
    issues = _collect_data_health_issues(project_id)
    codes = _issue_codes(issues)
    assert "story_graph_missing" not in codes


def test_worldline_session_clears_that_issue():
    project_id = "proj_has_worldline"
    repo = WorldlineSessionRepository(get_engine())
    repo.save_session(
        {
            "session_id": "sess_xyz",
            "project_id": project_id,
            "graph_id": "g",
            "simulation_goal": "",
            "focus_question": "",
            "branch_count": 0,
            "label": "Test",
            "prepare_id": "",
            "session_scope": "project",
            "status": "running",
            "branches": [],
            "world_variables": [],
            "timeline_focus": [],
            "agent_behavior_axes": [],
            "source_summary": {},
            "source_archive_ids": [],
            "source_project_ids": [],
            "source_archive_count": 0,
            "created_at": "2026-04-18T00:00:00",
            "updated_at": "2026-04-18T00:00:00",
        }
    )
    issues = _collect_data_health_issues(project_id)
    codes = _issue_codes(issues)
    assert "worldline_sessions_empty" not in codes


def test_issue_payload_has_title_and_hint():
    issues = _collect_data_health_issues("proj_payload_shape")
    for issue in issues:
        assert issue["title"]
        assert issue["hint"]
        assert issue["severity"] in {"info", "warning"}
