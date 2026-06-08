import json

from app import create_app
from app.api_fastapi.worldline import _store
from app.models.task import TaskStatus
from tests.test_worldline_auto_evolution_api import (
    create_project_with_seed as _create_auto_evolve_project,
    patch_router as _patch_auto_evolve_router,
    wait_for_task as _wait_for_auto_evolve_task,
)
from tests.test_worldline_event_adopt_api import _seed_session_with_candidates

from tests.test_worldline_runtime_api import _create_project_with_seed


def test_v2_worldline_session_routes_create_list_get_and_timeline(tmp_path, monkeypatch):
    project = _create_project_with_seed(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()

    create_response = client.post(
        "/api/v2/worldlines/sessions",
        json={
            "project_id": project.project_id,
            "branch_count": 1,
            "variables": ["密信提前泄露"],
        },
    )
    assert create_response.status_code == 200, create_response.get_json()
    created = create_response.get_json()["data"]
    session_id = created["session_id"]
    assert created["project_id"] == project.project_id
    assert created["session_scope"] == "project"
    assert created["branch_count"] == 1
    assert created["current_world"]["branch_id"] == "main"

    list_response = client.get(
        "/api/v2/worldlines/sessions",
        query_string={"project_id": project.project_id},
    )
    assert list_response.status_code == 200, list_response.get_json()
    listed = list_response.get_json()["data"]
    assert listed["count"] >= 1
    assert any(item["session_id"] == session_id for item in listed["sessions"])

    detail_response = client.get(
        f"/api/v2/worldlines/sessions/{session_id}",
        query_string={"project_id": project.project_id},
    )
    assert detail_response.status_code == 200, detail_response.get_json()
    detail = detail_response.get_json()["data"]
    assert detail["session_id"] == session_id
    assert detail["current_world"]["branch_id"] == "main"
    assert detail["current_world"]["title"]

    timeline_response = client.get(
        f"/api/v2/worldlines/sessions/{session_id}/timeline",
        query_string={"project_id": project.project_id},
    )
    assert timeline_response.status_code == 200, timeline_response.get_json()
    timeline = timeline_response.get_json()["data"]
    assert timeline["session_id"] == session_id
    assert timeline["branch_id"] == "main"
    assert isinstance(timeline["events"], list)


def test_v2_worldline_retains_single_world_retired_branch_endpoints(tmp_path, monkeypatch):
    project = _create_project_with_seed(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()
    create_response = client.post(
        "/api/v2/worldlines/sessions",
        json={"project_id": project.project_id, "branch_count": 1},
    )
    assert create_response.status_code == 200, create_response.get_json()
    session_id = create_response.get_json()["data"]["session_id"]

    branches_response = client.get(f"/api/v2/worldlines/sessions/{session_id}/branches")
    assert branches_response.status_code == 410, branches_response.get_json()
    assert "单世界世界线已不再支持分支列表接口" in branches_response.get_json()["error"]

    comparison_response = client.get(f"/api/v2/worldlines/sessions/{session_id}/comparison")
    assert comparison_response.status_code == 410, comparison_response.get_json()
    assert "单世界世界线已不再支持分支对比接口" in comparison_response.get_json()["error"]


def test_v2_worldline_command_routes_inject_queue_advance_and_dialogue(tmp_path, monkeypatch):
    project = _create_project_with_seed(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()

    create_response = client.post(
        "/api/v2/worldlines/sessions",
        json={"project_id": project.project_id, "branch_count": 1},
    )
    assert create_response.status_code == 200, create_response.get_json()
    session_id = create_response.get_json()["data"]["session_id"]

    inject_response = client.post(
        f"/api/v2/worldlines/sessions/{session_id}/commands/inject-variable",
        json={"project_id": project.project_id, "variable": "密信提前泄露"},
    )
    assert inject_response.status_code == 200, inject_response.get_json()
    inject_payload = inject_response.get_json()["data"]
    assert inject_payload["message"] == "变量注入成功"
    assert inject_payload["world_variables"]

    action_response = client.post(
        f"/api/v2/worldlines/sessions/{session_id}/commands/agent-actions",
        json={"project_id": project.project_id, "actor": "沈夜", "action": "秘密接触外门弟子"},
    )
    assert action_response.status_code == 200, action_response.get_json()
    action_payload = action_response.get_json()["data"]
    assert action_payload["action_event_id"]
    assert action_payload["agent"]["display_name"] == "沈夜"

    advance_response = client.post(
        f"/api/v2/worldlines/sessions/{session_id}/commands/advance",
        json={"project_id": project.project_id, "steps": 1},
    )
    assert advance_response.status_code == 200, advance_response.get_json()
    advance_payload = advance_response.get_json()["data"]
    assert advance_payload["message"] == "世界线已推进 1 步"
    assert advance_payload["current_world"]["timeline_size"] >= 1

    dialogue_response = client.post(
        f"/api/v2/worldlines/sessions/{session_id}/commands/agent-dialogues",
        json={"project_id": project.project_id, "actor": "沈夜", "message": "你今晚会公开证据吗？"},
    )
    assert dialogue_response.status_code == 200, dialogue_response.get_json()
    dialogue_payload = dialogue_response.get_json()["data"]
    assert dialogue_payload["dialogue_id"]
    assert dialogue_payload["generator_mode"] == "template"
    assert dialogue_payload["agent"] == "沈夜"


def test_v2_worldline_projection_routes_return_agent_activity_and_memory(tmp_path, monkeypatch):
    project = _create_project_with_seed(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()

    create_response = client.post(
        "/api/v2/worldlines/sessions",
        json={"project_id": project.project_id, "branch_count": 1},
    )
    assert create_response.status_code == 200, create_response.get_json()
    session_id = create_response.get_json()["data"]["session_id"]

    action_response = client.post(
        f"/api/v2/worldlines/sessions/{session_id}/commands/agent-actions",
        json={"project_id": project.project_id, "actor": "沈夜", "action": "秘密接触外门弟子"},
    )
    assert action_response.status_code == 200, action_response.get_json()
    action_payload = action_response.get_json()["data"]
    action_event_id = action_payload["action_event_id"]
    agent_id = action_payload["agent"]["agent_id"]

    advance_response = client.post(
        f"/api/v2/worldlines/sessions/{session_id}/commands/advance",
        json={"project_id": project.project_id, "steps": 1},
    )
    assert advance_response.status_code == 200, advance_response.get_json()

    dialogue_response = client.post(
        f"/api/v2/worldlines/sessions/{session_id}/commands/agent-dialogues",
        json={"project_id": project.project_id, "actor": "沈夜", "message": "你今晚会公开证据吗？"},
    )
    assert dialogue_response.status_code == 200, dialogue_response.get_json()
    dialogue_id = dialogue_response.get_json()["data"]["dialogue_id"]

    actions_response = client.get(
        f"/api/v2/worldlines/sessions/{session_id}/agent-actions",
        query_string={"project_id": project.project_id, "agent_id": agent_id},
    )
    assert actions_response.status_code == 200, actions_response.get_json()
    actions = actions_response.get_json()["data"]["items"]
    assert any(item["action_event_id"] == action_event_id and item["status"] == "applied" for item in actions)

    dialogues_response = client.get(
        f"/api/v2/worldlines/sessions/{session_id}/agent-dialogues",
        query_string={"project_id": project.project_id, "agent_id": agent_id},
    )
    assert dialogues_response.status_code == 200, dialogues_response.get_json()
    dialogues = dialogues_response.get_json()["data"]["items"]
    assert dialogues[0]["dialogue_id"] == dialogue_id

    history_response = client.get(
        f"/api/v2/worldlines/sessions/{session_id}/agent-history",
        query_string={"project_id": project.project_id, "agent_id": agent_id},
    )
    assert history_response.status_code == 200, history_response.get_json()
    history = history_response.get_json()["data"]
    assert any(item["action_event_id"] == action_event_id for item in history["actions"])
    assert history["snapshots"]

    memory_response = client.get(
        f"/api/v2/worldlines/sessions/{session_id}/agent-memory",
        query_string={"project_id": project.project_id, "agent_id": agent_id},
    )
    assert memory_response.status_code == 200, memory_response.get_json()
    memory = memory_response.get_json()["data"]
    assert memory["agent_id"] == agent_id
    assert "session_memories" in memory
    assert "long_term_memories" in memory

    memory_context_response = client.get(
        f"/api/v2/worldlines/sessions/{session_id}/agent-memory-context",
        query_string={"project_id": project.project_id, "agent_id": agent_id, "message": "公开证据"},
    )
    assert memory_context_response.status_code == 200, memory_context_response.get_json()
    memory_context = memory_context_response.get_json()["data"]
    assert memory_context["agent_id"] == agent_id
    assert "rendered_context" in memory_context
    assert "debug_hits" in memory_context

    relations_response = client.get(
        f"/api/v2/worldlines/sessions/{session_id}/relations",
        query_string={"project_id": project.project_id, "agent_id": agent_id},
    )
    assert relations_response.status_code == 200, relations_response.get_json()
    assert relations_response.get_json()["data"]["items"] is not None

    detail_response = client.get(
        f"/api/v2/worldlines/sessions/{session_id}/agents/{agent_id}",
        query_string={"project_id": project.project_id},
    )
    assert detail_response.status_code == 200, detail_response.get_json()
    detail = detail_response.get_json()["data"]
    assert detail["agent_id"] == agent_id
    assert detail["current_agent"]["display_name"] == "沈夜"
    assert detail["history"]["snapshots"]


def test_v2_worldline_event_routes_list_adopt_and_edit_candidate_events(tmp_path):
    project, _, session_id = _seed_session_with_candidates(_store, tmp_path)
    app = create_app()
    client = app.test_client()

    candidates_response = client.get(
        f"/api/v2/worldlines/sessions/{session_id}/events",
        query_string={"project_id": project.project_id, "status": "candidate"},
    )
    assert candidates_response.status_code == 200, candidates_response.get_json()
    candidates_payload = candidates_response.get_json()["data"]
    assert candidates_payload["session_id"] == session_id
    assert candidates_payload["status"] == "candidate"
    assert candidates_payload["count"] == 3
    assert {item["event_id"] for item in candidates_payload["events"]} == {"evt_c1", "evt_c2", "evt_c3"}

    adopt_response = client.post(
        f"/api/v2/worldlines/sessions/{session_id}/event-adoptions",
        json={
            "project_id": project.project_id,
            "event_ids": ["evt_c1"],
            "action": "canon",
        },
    )
    assert adopt_response.status_code == 200, adopt_response.get_json()
    adopt_payload = adopt_response.get_json()["data"]
    assert adopt_payload["session_id"] == session_id
    assert adopt_payload["changed_count"] == 1
    assert adopt_payload["current_world"]["canon_count"] == 2
    assert adopt_payload["current_world"]["candidate_count"] == 2

    canon_response = client.get(
        f"/api/v2/worldlines/sessions/{session_id}/events",
        query_string={"project_id": project.project_id, "status": "canon"},
    )
    assert canon_response.status_code == 200, canon_response.get_json()
    canon_payload = canon_response.get_json()["data"]
    assert canon_payload["status"] == "canon"
    assert {item["event_id"] for item in canon_payload["events"]} == {"evt_seed", "evt_c1"}

    edit_response = client.post(
        f"/api/v2/worldlines/sessions/{session_id}/events/evt_c2",
        json={"project_id": project.project_id, "consequence": "modified consequence text"},
    )
    assert edit_response.status_code == 200, edit_response.get_json()
    edit_payload = edit_response.get_json()["data"]
    assert edit_payload["event_id"] == "evt_c2"
    assert edit_payload["status"] == "canon"
    assert edit_payload["summary"] == "modified consequence text"

    remaining_response = client.get(
        f"/api/v2/worldlines/sessions/{session_id}/events",
        query_string={"project_id": project.project_id, "status": "candidate", "step": 1},
    )
    assert remaining_response.status_code == 200, remaining_response.get_json()
    remaining_payload = remaining_response.get_json()["data"]
    assert [item["event_id"] for item in remaining_payload["events"]] == ["evt_c3"]


def test_v2_worldline_auto_evolutions_start_single_main_world_task(tmp_path, monkeypatch):
    project = _create_auto_evolve_project(tmp_path, monkeypatch)
    _patch_auto_evolve_router(
        monkeypatch,
        action_payloads=[{"actions": [{"agent_id": "沈夜", "action": "公开密信残页", "intent": "逼出宗门反应"}]}],
        goal_payloads=[{"goal_reached": False, "reason": "首轮演化后目标尚未达成", "confidence": 0.21}],
    )
    app = create_app()
    client = app.test_client()

    create_response = client.post(
        "/api/v2/worldlines/sessions",
        json={
            "project_id": project.project_id,
            "branch_count": 2,
            "variables": ["密信提前泄露"],
        },
    )
    assert create_response.status_code == 200, create_response.get_json()
    session_id = create_response.get_json()["data"]["session_id"]

    response = client.post(
        f"/api/v2/worldlines/sessions/{session_id}/auto-evolutions",
        json={
            "project_id": project.project_id,
            "mode": "first_round",
            "goal_text": "",
            "max_steps": 4,
        },
    )

    assert response.status_code == 202, response.get_json()
    payload = response.get_json()["data"]
    assert payload["session_id"] == session_id
    assert payload["auto_evolution_id"] == payload["tasks"][0]["task_id"]
    assert len(payload["tasks"]) == 1
    assert payload["tasks"][0]["branch_id"] == "main"

    task = _wait_for_auto_evolve_task(payload["auto_evolution_id"])
    assert task.status == TaskStatus.COMPLETED
    assert task.result["branch_id"] == "main"
    assert task.result["stop_reason"] == "max_steps"
    assert task.result["completed_steps"] == 1
    assert task.result["latest_event"]["action_effects"]


def test_v2_worldline_auto_evolution_events_stream_starts_task(tmp_path, monkeypatch):
    project = _create_auto_evolve_project(tmp_path, monkeypatch)
    _patch_auto_evolve_router(
        monkeypatch,
        action_payloads=[{"actions": [{"agent_id": "沈夜", "action": "公开密信残页", "intent": "逼出宗门反应"}]}],
        goal_payloads=[{"goal_reached": False, "reason": "首轮演化后目标尚未达成", "confidence": 0.21}],
    )
    app = create_app()
    client = app.test_client()

    create_response = client.post(
        "/api/v2/worldlines/sessions",
        json={"project_id": project.project_id, "branch_count": 1},
    )
    assert create_response.status_code == 200, create_response.get_json()
    session_id = create_response.get_json()["data"]["session_id"]

    response = client.post(
        f"/api/v2/worldlines/sessions/{session_id}/auto-evolutions/manual-run/events",
        json={
            "project_id": project.project_id,
            "mode": "first_round",
            "goal_text": "",
            "max_steps": 1,
        },
    )

    stream_text = response.data.decode("utf-8")
    assert response.status_code == 200, stream_text
    assert "event: evolve_start" in stream_text
    assert "event: evolve_task" in stream_text
    assert "event: done" in stream_text

    payloads = [
        json.loads(line.removeprefix("data: "))
        for line in stream_text.splitlines()
        if line.startswith("data: ")
    ]
    task_payload = next(item for item in payloads if item["type"] == "evolve_task")
    assert task_payload["auto_evolution_id"] == "manual-run"
    task_id = task_payload["tasks"][0]["task_id"]

    task = _wait_for_auto_evolve_task(task_id)
    assert task.status == TaskStatus.COMPLETED
    assert task.result["branch_id"] == "main"
