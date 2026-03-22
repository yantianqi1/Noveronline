import sqlite3

from app import create_app
from app.config import Config
from app.api import worldline_interaction
from app.models.project import ProjectManager
from app.models.worldline import WorldlineBranch, WorldlineSession
from app.services.world_state_store import WorldStateStore


def _configure_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    ProjectManager.PROJECTS_DIR = str(tmp_path / "uploads" / "projects")


def _create_project_with_seed(tmp_path, monkeypatch):
    _configure_paths(tmp_path, monkeypatch)
    project = ProjectManager.create_project("世界线 Runtime 测试")
    project.graph_id = "graph_runtime_demo"
    project.analysis_goal = "观察主角与宗门关系在平行世界中的演化"
    ProjectManager.save_project(project)
    ProjectManager.save_project_json(
        project.project_id,
        "seed_analysis.json",
        {
            "characters": [
                {
                    "name": "沈夜",
                    "importance_tier": "protagonist",
                    "identity_hint": "主角",
                    "profile_summary": "正在调查宗门隐秘",
                },
                {
                    "name": "秦昭",
                    "importance_tier": "major",
                    "identity_hint": "游走于多方势力之间",
                    "profile_summary": "与主角互相试探",
                },
            ],
            "organizations": [
                {
                    "name": "玄霄宗",
                    "importance_tier": "major",
                    "organization_type": "sect",
                    "summary": "掌控试炼与秩序",
                }
            ],
            "relations": [
                {
                    "source": "沈夜",
                    "target": "玄霄宗",
                    "relation_type": "tension",
                }
            ],
        },
    )
    return project


def _runtime_db_path(project_id: str) -> str:
    return f"{ProjectManager._get_project_dir(project_id)}/worldlines/runtime.sqlite3"


def _create_session(client, project_id: str) -> str:
    response = client.post(
        "/api/worldline/session/create",
        json={"project_id": project_id, "branch_count": 1, "variables": ["密信提前泄露"]},
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]["session_id"]


def test_create_session_materializes_runtime_agents_and_snapshots(tmp_path, monkeypatch):
    project = _create_project_with_seed(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()

    session_id = _create_session(client, project.project_id)
    roster_response = client.get(f"/api/worldline/session/{session_id}/agents")

    assert roster_response.status_code == 200, roster_response.get_json()
    data = roster_response.get_json()["data"]
    assert data["agents"]
    character = next(item for item in data["agents"] if item["agent_kind"] == "character")
    assert character["agent_id"] != character["display_name"]
    assert character["state_version"] == 1
    assert character["state_source"] in {"seed_analysis", "session_bootstrap"}
    assert character["last_action_at"] is None
    assert character["last_dialogue_at"] is None

    connection = sqlite3.connect(_runtime_db_path(project.project_id))
    try:
        registry_count = connection.execute("SELECT COUNT(*) FROM agent_registry").fetchone()[0]
        snapshot_count = connection.execute("SELECT COUNT(*) FROM agent_state_snapshots").fetchone()[0]
    finally:
        connection.close()

    assert registry_count >= 3
    assert snapshot_count >= 3


def test_agent_action_transitions_from_queued_to_applied_and_records_history(tmp_path, monkeypatch):
    project = _create_project_with_seed(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()

    session_id = _create_session(client, project.project_id)
    roster = client.get(f"/api/worldline/session/{session_id}/agents").get_json()["data"]["agents"]
    actor = next(item for item in roster if item["agent_kind"] == "character")

    action_response = client.post(
        f"/api/worldline/session/{session_id}/agent-action",
        json={"agent_id": actor["agent_id"], "action": "秘密接触外门弟子"},
    )

    assert action_response.status_code == 200, action_response.get_json()
    action_event_id = action_response.get_json()["data"]["action_event_id"]
    assert action_event_id

    queued_response = client.get(
        f"/api/worldline/session/{session_id}/agent-actions",
        query_string={"agent_id": actor["agent_id"]},
    )
    assert queued_response.status_code == 200, queued_response.get_json()
    queued_event = next(item for item in queued_response.get_json()["data"]["items"] if item["action_event_id"] == action_event_id)
    assert queued_event["status"] == "queued"

    step_response = client.post(f"/api/worldline/session/{session_id}/step", json={"steps": 1})
    assert step_response.status_code == 200, step_response.get_json()

    applied_response = client.get(
        f"/api/worldline/session/{session_id}/agent-actions",
        query_string={"agent_id": actor["agent_id"]},
    )
    applied_event = next(item for item in applied_response.get_json()["data"]["items"] if item["action_event_id"] == action_event_id)
    assert applied_event["status"] == "applied"

    history_response = client.get(
        f"/api/worldline/session/{session_id}/agent-history",
        query_string={"agent_id": actor["agent_id"]},
    )
    assert history_response.status_code == 200, history_response.get_json()
    history = history_response.get_json()["data"]
    assert history["actions"][0]["action_event_id"] == action_event_id
    assert history["snapshots"]


def test_agent_dialogue_persists_history_and_llm_mode_requires_binding(tmp_path, monkeypatch):
    project = _create_project_with_seed(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()

    class MissingBindingRouter:
        def build_client(self, module_key):
            raise ValueError("世界线 Agent 对话 未配置 LLM 渠道和模型；请先在全局设施面板完成绑定，或显式传入 use_llm=False")

    monkeypatch.setattr(worldline_interaction.character_agent_service, "llm_router", MissingBindingRouter())

    session_id = _create_session(client, project.project_id)
    roster = client.get(f"/api/worldline/session/{session_id}/agents").get_json()["data"]["agents"]
    actor = next(item for item in roster if item["agent_kind"] == "character")

    dialogue_response = client.post(
        f"/api/worldline/session/{session_id}/agent-dialogue",
        json={"agent_id": actor["agent_id"], "message": "你今晚会公开证据吗？"},
    )

    assert dialogue_response.status_code == 200, dialogue_response.get_json()
    payload = dialogue_response.get_json()["data"]
    assert payload["dialogue_id"]
    assert payload["generator_mode"] == "template"
    assert payload["model_name"] == ""

    dialogue_list = client.get(
        f"/api/worldline/session/{session_id}/agent-dialogues",
        query_string={"agent_id": actor["agent_id"]},
    )
    assert dialogue_list.status_code == 200, dialogue_list.get_json()
    logged = dialogue_list.get_json()["data"]["items"]
    assert logged[0]["dialogue_id"] == payload["dialogue_id"]

    llm_response = client.post(
        f"/api/worldline/session/{session_id}/agent-dialogue",
        json={"agent_id": actor["agent_id"], "message": "你怎么看今晚局势？", "mode": "llm"},
    )
    assert llm_response.status_code == 400, llm_response.get_json()
    assert "worldline_agent_dialogue" in llm_response.get_json()["error"]


def test_agent_dialogue_llm_mode_succeeds_when_router_returns_client(tmp_path, monkeypatch):
    project = _create_project_with_seed(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()

    class FakeLlmClient:
        model = "fake-worldline-model"

        def chat(self, messages, temperature=0.7, max_tokens=4096, response_format=None):
            return "今晚我不会公开证据，我要先确认谁在盯着我们。"

    class FakeRouter:
        def build_client(self, module_key):
            assert module_key == "worldline_agent_dialogue"
            return FakeLlmClient()

    monkeypatch.setattr(worldline_interaction.character_agent_service, "llm_router", FakeRouter())

    session_id = _create_session(client, project.project_id)
    roster = client.get(f"/api/worldline/session/{session_id}/agents").get_json()["data"]["agents"]
    actor = next(item for item in roster if item["agent_kind"] == "character")

    llm_response = client.post(
        f"/api/worldline/session/{session_id}/agent-dialogue",
        json={"agent_id": actor["agent_id"], "message": "你怎么看今晚局势？", "mode": "llm"},
    )

    assert llm_response.status_code == 200, llm_response.get_json()
    payload = llm_response.get_json()["data"]
    assert payload["generator_mode"] == "llm"
    assert payload["model_name"] == "fake-worldline-model"
    assert "不会公开证据" in payload["result"]["reply"]

    dialogue_list = client.get(
        f"/api/worldline/session/{session_id}/agent-dialogues",
        query_string={"agent_id": actor["agent_id"]},
    )
    assert dialogue_list.status_code == 200, dialogue_list.get_json()
    logged = dialogue_list.get_json()["data"]["items"]
    assert logged[0]["dialogue_id"] == payload["dialogue_id"]
    assert logged[0]["generator_mode"] == "llm"
    assert logged[0]["model_name"] == "fake-worldline-model"


def test_existing_session_bootstraps_runtime_db_from_session_json(tmp_path, monkeypatch):
    project = _create_project_with_seed(tmp_path, monkeypatch)
    store = WorldStateStore()
    container_dir = ProjectManager._get_project_dir(project.project_id)
    session = WorldlineSession(
        session_id="ws_existing",
        project_id=project.project_id,
        graph_id=project.graph_id,
        simulation_goal=project.analysis_goal,
        focus_question=project.analysis_goal,
        branch_count=1,
        branches=[
            WorldlineBranch(
                branch_id="branch_1",
                title="旧会话",
                core_change="旧世界线",
                actor_states={"沈夜": {"status": "active", "drive": "查清真相", "role": "主角"}},
                organization_states={"玄霄宗": {"status": "active", "drive": "维持秩序", "role": "宗门"}},
                relationship_states=[{"source": "沈夜", "target": "玄霄宗", "change": "stable"}],
            )
        ],
    )
    store.save_session(container_dir, session)
    app = create_app()
    client = app.test_client()

    response = client.get(f"/api/worldline/session/{session.session_id}/agents", query_string={"project_id": project.project_id})

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["data"]["agents"]
    assert sqlite3.connect(_runtime_db_path(project.project_id)).execute("SELECT COUNT(*) FROM agent_registry").fetchone()[0] >= 3
