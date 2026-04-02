"""Tests for WorldEvent candidate/canon/rejected status fields and event management."""

import pytest

from app.models.project import ProjectManager
from app.models.worldline import WorldEvent, WorldlineBranch, WorldlineSession
from app.services.world_state_store import WorldStateStore
from app.services.worldline_branch_comparison import WorldlineBranchComparisonService
from app.services.worldline_branch_service import WorldlineBranchService
from app.services.worldline_engine import WorldlineEngine
from app.services.worldline_source_loader import WorldlineSourceLoader


def _make_engine(store: WorldStateStore) -> WorldlineEngine:
    return WorldlineEngine(
        store=store,
        source_loader=WorldlineSourceLoader(store),
        branch_service=WorldlineBranchService(),
        comparison_service=WorldlineBranchComparisonService(),
    )


def _make_project(tmp_path):
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    project = ProjectManager.create_project("test_candidate_project")
    project.graph_id = "graph_test"
    project.analysis_goal = "test"
    ProjectManager.save_project(project)
    return project


def _seed_session(store, tmp_path):
    project = _make_project(tmp_path)
    container_dir = ProjectManager._get_project_dir(project.project_id)
    session = WorldlineSession(
        session_id="ws_candidate_test",
        project_id=project.project_id,
        graph_id="graph_test",
        simulation_goal="test",
        focus_question="test",
        branch_count=1,
        branches=[
            WorldlineBranch(
                branch_id="main",
                title="当前世界",
                core_change="test core change",
                key_agents=["A", "B"],
                actor_states={
                    "A": {"status": "active", "drive": "test", "role": "主角"},
                    "B": {"status": "active", "drive": "test", "role": "配角"},
                },
            )
        ],
    )
    store.save_session(str(container_dir), session)
    return project, container_dir, session.session_id


# --- WorldEvent model field tests ---

def test_world_event_defaults_to_canon():
    event = WorldEvent(event_id="e1", step=1, title="t", summary="s")
    assert event.status == "canon"
    assert event.confidence == "high"
    assert event.confidence_reason == ""
    assert event.event_source == "archive_based"


def test_world_event_candidate_status():
    event = WorldEvent(
        event_id="e2", step=1, title="t", summary="s",
        status="candidate",
        confidence="medium",
        confidence_reason="context match",
        event_source="context_based",
    )
    assert event.status == "candidate"
    assert event.confidence == "medium"
    d = event.to_dict()
    assert d["status"] == "candidate"
    assert d["confidence"] == "medium"
    assert d["confidence_reason"] == "context match"
    assert d["event_source"] == "context_based"


def test_world_event_from_dict_defaults_to_canon_for_legacy():
    legacy_data = {
        "event_id": "e3",
        "step": 0,
        "title": "legacy",
        "summary": "old event",
        "event_type": "seed",
    }
    event = WorldEvent.from_dict(legacy_data)
    assert event.status == "canon"
    assert event.confidence == "high"
    assert event.event_source == "archive_based"


def test_world_event_from_dict_reads_new_fields():
    data = {
        "event_id": "e4",
        "step": 2,
        "title": "new",
        "summary": "new event",
        "status": "rejected",
        "confidence": "low",
        "confidence_reason": "creative extension",
        "event_source": "creative",
    }
    event = WorldEvent.from_dict(data)
    assert event.status == "rejected"
    assert event.confidence == "low"
    assert event.confidence_reason == "creative extension"
    assert event.event_source == "creative"


def test_world_event_from_dict_migrates_source_field():
    """Old data might have 'source' instead of 'event_source'."""
    data = {
        "event_id": "e5",
        "step": 1,
        "title": "t",
        "summary": "s",
        "source": "context_based",
    }
    event = WorldEvent.from_dict(data)
    assert event.event_source == "context_based"


def test_world_event_roundtrip():
    event = WorldEvent(
        event_id="e6", step=3, title="t", summary="s",
        status="candidate",
        confidence="low",
        confidence_reason="reason",
        event_source="creative",
    )
    d = event.to_dict()
    restored = WorldEvent.from_dict(d)
    assert restored.status == "candidate"
    assert restored.confidence == "low"
    assert restored.confidence_reason == "reason"
    assert restored.event_source == "creative"


# --- Seed event gets canon status ---

def test_seed_event_is_canon(tmp_path):
    store = WorldStateStore()
    engine = _make_engine(store)
    project = _make_project(tmp_path)
    session, _ = engine.create_session(
        graph_id="graph_test",
        project_id=project.project_id,
        focus_question="test",
        branch_count=1,
        archives=[
            {
                "entity_uuid": "c1",
                "entity_name": "A",
                "entity_type": "Character",
                "importance_tier": "major",
                "entity_role": "test",
                "core_drive": "test",
                "relationship_summary": "test",
                "agent_behavior_hint": "test",
            }
        ],
    )
    branch = session.branches[0]
    seed = branch.timeline[0]
    assert seed.status == "canon"
    assert seed.confidence == "high"
    assert seed.event_source == "archive_based"


# --- Manual step produces canon events ---

def test_manual_step_produces_canon_events(tmp_path):
    store = WorldStateStore()
    engine = _make_engine(store)
    project, _, session_id = _seed_session(store, tmp_path)
    engine.inject_variable(
        session_id=session_id,
        project_id=project.project_id,
        name="test var",
        description="test description",
    )
    updated = engine.step(
        session_id=session_id,
        project_id=project.project_id,
    )
    branch = updated.branches[0]
    latest = branch.timeline[-1]
    assert latest.status == "canon"
    assert latest.event_type == "evolution"


# --- advance_branch with candidate status ---

def test_advance_branch_with_candidate_status(tmp_path):
    store = WorldStateStore()
    engine = _make_engine(store)
    project, _, session_id = _seed_session(store, tmp_path)
    session = engine.get_session(session_id, project_id=project.project_id)
    branch = session.branches[0]
    branch.pending_variables.append(
        __import__("app.models.worldline", fromlist=["VariableInjection"]).VariableInjection(
            variable_id="v1", name="test", description="test"
        )
    )
    result = engine.branch_service.advance_branch(
        branch, session,
        event_status="candidate",
        event_confidence="medium",
        event_confidence_reason="context logic",
        event_source="context_based",
    )
    new_event = result["new_event"]
    assert new_event.status == "candidate"
    assert new_event.confidence == "medium"
    assert new_event.confidence_reason == "context logic"
    assert new_event.event_source == "context_based"
