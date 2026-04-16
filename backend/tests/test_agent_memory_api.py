import asyncio
import sqlite3
import time

from app import create_app
from app.api_fastapi import worldline
from app.config import Config
from app.database import get_engine
from app.models.project import ProjectManager
from app.models.task import TaskManager, TaskStatus


WAIT_TIMEOUT_SECONDS = 10.0
POLL_INTERVAL_SECONDS = 0.05


def _configure_paths(tmp_path, monkeypatch) -> None:
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    ProjectManager.PROJECTS_DIR = str(upload_root / "projects")
    TaskManager._instance = None


def _archive_payload(project, archives):
    return {
        "project_id": project.project_id,
        "project_name": project.name,
        "count": len(archives),
        "entity_types": sorted({item["entity_type"] for item in archives}),
        "archives": archives,
    }


def _make_archive(entity_uuid: str, entity_name: str, entity_type: str, importance_tier: str):
    agent_kind = "organization" if entity_type == "Organization" else "character"
    return {
        "entity_uuid": entity_uuid,
        "entity_name": entity_name,
        "entity_type": entity_type,
        "agent_kind": agent_kind,
        "importance_tier": importance_tier,
        "recommended_importance_tier": importance_tier,
        "selected_importance_tier": importance_tier,
        "template_key": f"{agent_kind}.{importance_tier}.v1",
        "template_version": "v1",
        "template_sections": ["identity", "motivation", "state"],
        "template_payload": {
            "identity": {"entity_name": entity_name},
            "motivation": {"core_drive": f"{entity_name} 的目标"},
            "state": {"status": "active"},
        },
        "template_metadata": {"source": "test_fixture", "version": "v1"},
        "entity_role": f"{entity_name} 的定位",
        "core_drive": f"{entity_name} 的目标",
        "surface_mask": f"{entity_name} 的外在形象",
        "hidden_tension": f"{entity_name} 的隐藏矛盾",
        "relationship_summary": f"{entity_name} 的关系摘要",
        "agent_behavior_hint": f"{entity_name} 的行动倾向",
        "human_ai_relation_tag": "human" if entity_type == "Character" else "none",
        "notable_risks": ["风险A"],
        "can_act_as_agent": True,
    }


def _create_project_with_archives(tmp_path, monkeypatch):
    _configure_paths(tmp_path, monkeypatch)
    project = ProjectManager.create_project("Agent Memory 测试")
    project.graph_id = "graph_memory_demo"
    project.analysis_goal = "观察角色在持续演化中的长期记忆"
    ProjectManager.save_project(project)
    ProjectManager.save_project_json(
        project.project_id,
        "seed_analysis.json",
        {
            "characters": [
                {"name": "沈夜", "importance_tier": "protagonist", "identity_hint": "主角", "profile_summary": "追查宗门真相"},
                {"name": "秦昭", "importance_tier": "major", "identity_hint": "盟友", "profile_summary": "善于试探局势"},
            ],
            "organizations": [
                {"name": "玄霄宗", "importance_tier": "major", "organization_type": "sect", "summary": "掌控秩序"}
            ],
            "relations": [{"source": "沈夜", "target": "玄霄宗", "relation_type": "tension"}],
        },
    )
    archives = [
        _make_archive("char_shenye", "沈夜", "Character", "protagonist"),
        _make_archive("char_qinzhao", "秦昭", "Character", "major"),
        _make_archive("org_xuanxiao", "玄霄宗", "Organization", "major"),
    ]
    ProjectManager.save_project_json(
        project.project_id,
        "narrative_archives.json",
        _archive_payload(project, archives),
    )
    return project


def _create_session(client, project_id: str) -> str:
    response = client.post(
        "/api/worldline/session/create",
        json={"project_id": project_id, "branch_count": 1, "variables": ["密信提前泄露"]},
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]["session_id"]


def _agent_by_name(client, session_id: str, name: str):
    agents = client.get(f"/api/worldline/session/{session_id}/agents").get_json()["data"]["agents"]
    return next(item for item in agents if item["display_name"] == name)


def _db_path() -> str:
    """Return the SQLite file path used by the unified engine."""
    url = str(get_engine().url)
    # url is like 'sqlite:///path/to/db'
    return url.replace("sqlite:///", "")


def _wait_for_task(task_id: str):
    deadline = time.time() + WAIT_TIMEOUT_SECONDS
    manager = TaskManager()
    latest = None
    while time.time() < deadline:
        latest = asyncio.run(manager.get_task(task_id))
        if latest and latest.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            return latest
        time.sleep(POLL_INTERVAL_SECONDS)
    latest_payload = latest.to_dict() if latest else None
    raise AssertionError(f"自动演化任务超时未完成: {task_id}, latest={latest_payload}")


def test_agent_memory_api_records_session_and_long_term_entries(tmp_path, monkeypatch):
    project = _create_project_with_archives(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()

    session_id = _create_session(client, project.project_id)
    actor = _agent_by_name(client, session_id, "沈夜")

    dialogue_response = client.post(
        f"/api/worldline/session/{session_id}/agent-dialogue",
        json={"agent_id": actor["agent_id"], "message": "今晚你会怎么行动？"},
    )
    assert dialogue_response.status_code == 200, dialogue_response.get_json()

    action_response = client.post(
        f"/api/worldline/session/{session_id}/agent-action",
        json={"agent_id": actor["agent_id"], "action": "秘密接触外门弟子", "intent": "先摸清对方底牌"},
    )
    assert action_response.status_code == 200, action_response.get_json()

    step_response = client.post(f"/api/worldline/session/{session_id}/step", json={"steps": 1})
    assert step_response.status_code == 200, step_response.get_json()

    memory_response = client.get(
        f"/api/worldline/session/{session_id}/agent-memory",
        query_string={"agent_id": actor["agent_id"]},
    )
    assert memory_response.status_code == 200, memory_response.get_json()
    payload = memory_response.get_json()["data"]
    assert payload["session_memories"]
    assert payload["long_term_memories"] == []
    assert payload["candidate_memories"]
    assert {item["memory_type"] for item in payload["session_memories"]} >= {"fact", "strategy"}
    assert all(item["memory_layer"] == "candidate" for item in payload["candidate_memories"])

    context_response = client.get(
        f"/api/worldline/session/{session_id}/agent-memory-context",
        query_string={"agent_id": actor["agent_id"], "message": "外门弟子现在可靠吗？"},
    )
    assert context_response.status_code == 200, context_response.get_json()
    context_payload = context_response.get_json()["data"]
    assert "秘密接触外门弟子" in context_payload["rendered_context"]
    assert context_payload["debug_hits"]

    db_connection = sqlite3.connect(_db_path())
    try:
        episodic_count = db_connection.execute("SELECT COUNT(*) FROM agent_episodic_memory").fetchone()[0]
        long_term_count = db_connection.execute("SELECT COUNT(*) FROM archive_agent_memory").fetchone()[0]
    finally:
        db_connection.close()

    assert episodic_count >= 3
    assert long_term_count >= 1


def test_agent_memory_persists_across_sessions_by_archive_id(tmp_path, monkeypatch):
    project = _create_project_with_archives(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()

    first_session_id = _create_session(client, project.project_id)
    first_actor = _agent_by_name(client, first_session_id, "沈夜")
    action_response = client.post(
        f"/api/worldline/session/{first_session_id}/agent-action",
        json={"agent_id": first_actor["agent_id"], "action": "公开密信残页", "intent": "逼迫宗门表态"},
    )
    assert action_response.status_code == 200, action_response.get_json()
    step_response = client.post(f"/api/worldline/session/{first_session_id}/step", json={"steps": 1})
    assert step_response.status_code == 200, step_response.get_json()

    second_session_id = _create_session(client, project.project_id)
    second_actor = _agent_by_name(client, second_session_id, "沈夜")
    memory_response = client.get(
        f"/api/worldline/session/{second_session_id}/agent-memory",
        query_string={"agent_id": second_actor["agent_id"]},
    )
    assert memory_response.status_code == 200, memory_response.get_json()
    payload = memory_response.get_json()["data"]

    assert payload["session_memories"] == []
    assert payload["long_term_memories"] == []
    assert any("公开密信残页" in item["summary"] for item in payload["candidate_memories"])


def test_template_dialogue_mentions_recalled_memory(tmp_path, monkeypatch):
    project = _create_project_with_archives(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()

    session_id = _create_session(client, project.project_id)
    actor = _agent_by_name(client, session_id, "沈夜")
    action_response = client.post(
        f"/api/worldline/session/{session_id}/agent-action",
        json={"agent_id": actor["agent_id"], "action": "秘密接触外门弟子", "intent": "摸清外部态度"},
    )
    assert action_response.status_code == 200, action_response.get_json()
    step_response = client.post(f"/api/worldline/session/{session_id}/step", json={"steps": 1})
    assert step_response.status_code == 200, step_response.get_json()

    dialogue_response = client.post(
        f"/api/worldline/session/{session_id}/agent-dialogue",
        json={"agent_id": actor["agent_id"], "message": "接下来你准备怎么办？"},
    )
    assert dialogue_response.status_code == 200, dialogue_response.get_json()
    reply = dialogue_response.get_json()["data"]["result"]["reply"]

    assert "我记得" in reply
    assert "秘密接触外门弟子" in reply


def test_auto_evolve_action_prompt_excludes_candidate_memory_by_default(tmp_path, monkeypatch):
    project = _create_project_with_archives(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()

    first_session_id = _create_session(client, project.project_id)
    first_actor = _agent_by_name(client, first_session_id, "沈夜")
    action_response = client.post(
        f"/api/worldline/session/{first_session_id}/agent-action",
        json={"agent_id": first_actor["agent_id"], "action": "公开密信残页", "intent": "逼迫宗门表态"},
    )
    assert action_response.status_code == 200, action_response.get_json()
    step_response = client.post(f"/api/worldline/session/{first_session_id}/step", json={"steps": 1})
    assert step_response.status_code == 200, step_response.get_json()

    class RecordingJsonClient:
        def __init__(self, model: str, payload: dict):
            self.model = model
            self.payload = payload
            self.messages = []

        def chat_json_value(self, messages, temperature=0.3, max_tokens=4096):
            del temperature, max_tokens
            self.messages.append(messages)
            return self.payload

        def chat_json(self, messages, temperature=0.3, max_tokens=4096):
            del temperature, max_tokens
            self.messages.append(messages)
            return self.payload

    action_client = RecordingJsonClient("fake-action-model", {"actions": []})
    goal_client = RecordingJsonClient(
        "fake-goal-model",
        {"goal_reached": False, "reason": "首轮后继续观察", "confidence": 0.2},
    )

    class FakeRouter:
        def build_client(self, module_key):
            if module_key == "worldline_agent_action":
                return action_client
            if module_key == "worldline_goal_evaluator":
                return goal_client
            raise AssertionError(f"unexpected module_key: {module_key}")

    monkeypatch.setattr(
        worldline.worldline_auto_evolution_task_service.auto_action_service,
        "llm_router",
        FakeRouter(),
    )

    second_session_id = _create_session(client, project.project_id)
    response = client.post(
        f"/api/worldline/session/{second_session_id}/auto-evolve",
        json={"project_id": project.project_id, "mode": "first_round", "goal_text": "", "max_steps": 1},
    )
    assert response.status_code == 202, response.get_json()
    task_id = response.get_json()["data"]["tasks"][0]["task_id"]
    task = _wait_for_task(task_id)

    assert task.status == TaskStatus.COMPLETED
    assert action_client.messages
    action_prompt = action_client.messages[0][1]["content"]
    assert "公开密信残页" not in action_prompt
