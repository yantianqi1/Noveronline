"""Tests for worldline event adopt/edit/query APIs and auto-evolve candidate behavior."""

import json
import pytest

from app.models.project import ProjectManager
from app.models.worldline import WorldEvent, WorldlineBranch, WorldlineSession, VariableInjection
from app.services.world_state_store import WorldStateStore
from app.services.worldline_event_service import WorldlineEventService


def _make_project(tmp_path):
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    project = ProjectManager.create_project("test_adopt_project")
    project.graph_id = "graph_adopt"
    project.analysis_goal = "test"
    ProjectManager.save_project(project)
    return project


def _seed_session_with_candidates(store, tmp_path):
    project = _make_project(tmp_path)
    container_dir = str(ProjectManager._get_project_dir(project.project_id))

    session = WorldlineSession(
        session_id="ws_adopt_test",
        project_id=project.project_id,
        graph_id="graph_adopt",
        simulation_goal="test",
        focus_question="test",
        branch_count=1,
        branches=[
            WorldlineBranch(
                branch_id="main",
                title="当前世界",
                core_change="test",
                key_agents=["A"],
                actor_states={"A": {"status": "active", "drive": "test"}},
                timeline=[
                    WorldEvent(
                        event_id="evt_seed",
                        step=0,
                        title="seed",
                        summary="seed event",
                        event_type="seed",
                        status="canon",
                    ),
                    WorldEvent(
                        event_id="evt_c1",
                        step=1,
                        title="candidate 1",
                        summary="first candidate",
                        event_type="evolution",
                        status="candidate",
                        confidence="high",
                        confidence_reason="archive based",
                        event_source="archive_based",
                    ),
                    WorldEvent(
                        event_id="evt_c2",
                        step=1,
                        title="candidate 2",
                        summary="second candidate",
                        event_type="evolution",
                        status="candidate",
                        confidence="medium",
                        confidence_reason="context match",
                        event_source="context_based",
                    ),
                    WorldEvent(
                        event_id="evt_c3",
                        step=1,
                        title="candidate 3",
                        summary="third candidate",
                        event_type="evolution",
                        status="candidate",
                        confidence="low",
                        confidence_reason="creative extension",
                        event_source="creative",
                    ),
                ],
            )
        ],
    )
    store.save_session(container_dir, session)
    return project, container_dir, session.session_id


# --- Event Service Tests ---

def test_adopt_events_marks_candidates_as_canon(tmp_path):
    store = WorldStateStore()
    service = WorldlineEventService(store=store)
    project, container_dir, session_id = _seed_session_with_candidates(store, tmp_path)

    session = store.load_session(session_id, project_id=project.project_id)
    result = service.adopt_events(session, container_dir, ["evt_c1", "evt_c2"], "canon")

    assert result["action"] == "canon"
    assert result["changed_count"] == 2

    # Verify events are now canon
    reloaded = store.load_session(session_id, project_id=project.project_id)
    branch = reloaded.branches[0]
    statuses = {e.event_id: e.status for e in branch.timeline}
    assert statuses["evt_c1"] == "canon"
    assert statuses["evt_c2"] == "canon"
    assert statuses["evt_c3"] == "candidate"


def test_adopt_events_marks_candidates_as_rejected(tmp_path):
    store = WorldStateStore()
    service = WorldlineEventService(store=store)
    project, container_dir, session_id = _seed_session_with_candidates(store, tmp_path)

    session = store.load_session(session_id, project_id=project.project_id)
    result = service.adopt_events(session, container_dir, ["evt_c3"], "rejected")

    assert result["action"] == "rejected"
    assert result["changed_count"] == 1

    reloaded = store.load_session(session_id, project_id=project.project_id)
    statuses = {e.event_id: e.status for e in reloaded.branches[0].timeline}
    assert statuses["evt_c3"] == "rejected"


def test_adopt_events_rejects_invalid_action(tmp_path):
    store = WorldStateStore()
    service = WorldlineEventService(store=store)
    project, container_dir, session_id = _seed_session_with_candidates(store, tmp_path)

    session = store.load_session(session_id, project_id=project.project_id)
    with pytest.raises(ValueError, match="must be 'canon' or 'rejected'"):
        service.adopt_events(session, container_dir, ["evt_c1"], "invalid")


def test_adopt_events_rejects_empty_ids(tmp_path):
    store = WorldStateStore()
    service = WorldlineEventService(store=store)
    project, container_dir, session_id = _seed_session_with_candidates(store, tmp_path)

    session = store.load_session(session_id, project_id=project.project_id)
    with pytest.raises(ValueError, match="must not be empty"):
        service.adopt_events(session, container_dir, [], "canon")


def test_adopt_events_ignores_non_candidate_events(tmp_path):
    store = WorldStateStore()
    service = WorldlineEventService(store=store)
    project, container_dir, session_id = _seed_session_with_candidates(store, tmp_path)

    session = store.load_session(session_id, project_id=project.project_id)
    with pytest.raises(ValueError, match="No matching candidate events"):
        service.adopt_events(session, container_dir, ["evt_seed"], "canon")


def test_edit_event_updates_summary_and_marks_canon(tmp_path):
    store = WorldStateStore()
    service = WorldlineEventService(store=store)
    project, container_dir, session_id = _seed_session_with_candidates(store, tmp_path)

    session = store.load_session(session_id, project_id=project.project_id)
    result = service.edit_event(session, container_dir, "evt_c1", "modified consequence text")

    assert result["event_id"] == "evt_c1"
    assert result["status"] == "canon"
    assert result["summary"] == "modified consequence text"

    reloaded = store.load_session(session_id, project_id=project.project_id)
    event = next(e for e in reloaded.branches[0].timeline if e.event_id == "evt_c1")
    assert event.summary == "modified consequence text"
    assert event.status == "canon"


def test_edit_event_rejects_non_candidate(tmp_path):
    store = WorldStateStore()
    service = WorldlineEventService(store=store)
    project, container_dir, session_id = _seed_session_with_candidates(store, tmp_path)

    session = store.load_session(session_id, project_id=project.project_id)
    with pytest.raises(ValueError, match="Only candidate events"):
        service.edit_event(session, container_dir, "evt_seed", "new text")


def test_list_candidate_events(tmp_path):
    store = WorldStateStore()
    service = WorldlineEventService(store=store)
    project, container_dir, session_id = _seed_session_with_candidates(store, tmp_path)

    session = store.load_session(session_id, project_id=project.project_id)
    candidates = service.list_candidate_events(session)
    assert len(candidates) == 3
    assert all(c["status"] == "candidate" for c in candidates)


def test_list_candidate_events_by_step(tmp_path):
    store = WorldStateStore()
    service = WorldlineEventService(store=store)
    project, container_dir, session_id = _seed_session_with_candidates(store, tmp_path)

    session = store.load_session(session_id, project_id=project.project_id)
    candidates = service.list_candidate_events(session, step=1)
    assert len(candidates) == 3

    candidates_step0 = service.list_candidate_events(session, step=0)
    assert len(candidates_step0) == 0  # seed is canon


def test_list_canon_events(tmp_path):
    store = WorldStateStore()
    service = WorldlineEventService(store=store)
    project, container_dir, session_id = _seed_session_with_candidates(store, tmp_path)

    session = store.load_session(session_id, project_id=project.project_id)
    canon = service.list_canon_events(session)
    assert len(canon) == 1  # only the seed event
    assert canon[0]["event_id"] == "evt_seed"
