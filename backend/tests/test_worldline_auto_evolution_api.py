import asyncio
import time

from app import create_app
from app.api_fastapi import worldline
from app.config import Config
from app.models.project import ProjectManager
from app.models.task import TaskManager, TaskStatus
from app.services.worldline_auto_evolution_support import resolve_steps


WAIT_TIMEOUT_SECONDS = 10.0
POLL_INTERVAL_SECONDS = 0.05


def reset_task_manager() -> None:
    TaskManager._instance = None


def configure_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    ProjectManager.PROJECTS_DIR = str(tmp_path / "uploads" / "projects")
    reset_task_manager()


def create_project_with_seed(tmp_path, monkeypatch):
    configure_paths(tmp_path, monkeypatch)
    project = ProjectManager.create_project("世界线自动演化测试")
    project.graph_id = "graph_auto_evolve_demo"
    project.analysis_goal = "观察角色在变量扰动下的自主演化"
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
                    "profile_summary": "正试图公开宗门秘闻。",
                },
                {
                    "name": "秦昭",
                    "importance_tier": "major",
                    "identity_hint": "关键盟友",
                    "profile_summary": "擅长在多方之间游走试探。",
                },
            ],
            "organizations": [
                {
                    "name": "玄霄宗",
                    "importance_tier": "major",
                    "organization_type": "sect",
                    "summary": "掌控秩序与试炼。",
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


def create_session(client, project_id: str, branch_count: int = 1) -> str:
    response = client.post(
        "/api/worldline/session/create",
        json={
            "project_id": project_id,
            "branch_count": branch_count,
            "variables": ["密信提前泄露"],
        },
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]["session_id"]


def wait_for_task(task_id: str, timeout: float = WAIT_TIMEOUT_SECONDS):
    deadline = time.time() + timeout
    manager = TaskManager()
    latest = None
    while time.time() < deadline:
        latest = asyncio.run(manager.get_task(task_id))
        if latest and latest.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            return latest
        time.sleep(POLL_INTERVAL_SECONDS)
    latest_payload = latest.to_dict() if latest else None
    raise AssertionError(f"自动演化任务超时未完成: {task_id}, latest={latest_payload}")


class ScriptedJsonClient:
    def __init__(self, model: str, payloads):
        self.model = model
        self.payloads = list(payloads)
        self.call_count = 0

    def _next_payload(self):
        index = min(self.call_count, len(self.payloads) - 1)
        self.call_count += 1
        return self.payloads[index]

    def chat_json(self, messages, temperature=0.3, max_tokens=4096):
        del messages, temperature, max_tokens
        return self._next_payload()

    def chat_json_value(self, messages, temperature=0.3, max_tokens=4096):
        del messages, temperature, max_tokens
        return self._next_payload()


class FakeRouter:
    def __init__(self, action_client, goal_client):
        self.action_client = action_client
        self.goal_client = goal_client

    def build_client(self, module_key):
        if module_key == "worldline_agent_action":
            return self.action_client
        if module_key == "worldline_goal_evaluator":
            return self.goal_client
        raise AssertionError(f"unexpected module_key: {module_key}")


def patch_router(monkeypatch, action_payloads, goal_payloads) -> None:
    router = FakeRouter(
        ScriptedJsonClient("fake-action-model", action_payloads),
        ScriptedJsonClient("fake-goal-model", goal_payloads),
    )
    monkeypatch.setattr(
        worldline.worldline_auto_evolution_task_service.auto_action_service,
        "llm_router",
        router,
    )


def test_auto_evolve_api_creates_single_main_world_task_and_applies_generated_actions(tmp_path, monkeypatch):
    project = create_project_with_seed(tmp_path, monkeypatch)
    patch_router(
        monkeypatch,
        action_payloads=[{"actions": [{"agent_id": "沈夜", "action": "公开密信残页", "intent": "逼出宗门反应"}]}],
        goal_payloads=[{"goal_reached": False, "reason": "首轮演化后目标尚未达成", "confidence": 0.21}],
    )
    app = create_app()
    client = app.test_client()

    session_id = create_session(client, project.project_id, branch_count=2)
    response = client.post(
        f"/api/worldline/session/{session_id}/auto-evolve",
        json={
            "project_id": project.project_id,
            "mode": "first_round",
            "goal_text": "",
            "max_steps": 4,
        },
    )

    assert response.status_code == 202, response.get_json()
    tasks = response.get_json()["data"]["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["branch_id"] == "main"

    finished = [wait_for_task(item["task_id"]) for item in tasks]
    for task in finished:
        assert task.status == TaskStatus.COMPLETED
        assert task.result["branch_id"] == "main"
        assert task.result["stop_reason"] == "max_steps"
        assert task.result["completed_steps"] == 1
        assert task.result["latest_event"]["step"] == 1
        assert task.result["latest_event"]["action_effects"]
        assert task.result["goal_verdict"]["goal_reached"] is False

    action_response = client.get(
        f"/api/worldline/session/{session_id}/agent-actions",
        query_string={"status": "applied"},
    )
    assert action_response.status_code == 200, action_response.get_json()
    assert action_response.get_json()["data"]["items"]


def test_auto_evolve_continuous_task_stops_when_goal_is_reached(tmp_path, monkeypatch):
    project = create_project_with_seed(tmp_path, monkeypatch)
    patch_router(
        monkeypatch,
        action_payloads=[{"actions": [{"agent_id": "沈夜", "action": "当众揭露玄霄宗密谋", "intent": "逼迫各方站队"}]}],
        goal_payloads=[{"goal_reached": True, "reason": "主角已经公开核心证据", "confidence": 0.94}],
    )
    app = create_app()
    client = app.test_client()

    session_id = create_session(client, project.project_id)
    response = client.post(
        f"/api/worldline/session/{session_id}/auto-evolve",
        json={
            "project_id": project.project_id,
            "mode": "continuous",
            "goal_text": "沈夜公开宗门证据",
            "max_steps": 5,
        },
    )

    assert response.status_code == 202, response.get_json()
    task_id = response.get_json()["data"]["tasks"][0]["task_id"]
    task = wait_for_task(task_id)

    assert task.status == TaskStatus.COMPLETED
    assert task.result["branch_id"] == "main"
    assert task.result["stop_reason"] == "goal_reached"
    assert task.result["completed_steps"] == 1
    assert task.result["goal_verdict"]["goal_reached"] is True
    assert task.result["goal_verdict"]["model_name"] == "fake-goal-model"


def test_auto_evolve_accepts_top_level_action_list_payload(tmp_path, monkeypatch):
    project = create_project_with_seed(tmp_path, monkeypatch)
    patch_router(
        monkeypatch,
        action_payloads=[[
            {"agent_id": "沈夜", "action": "公开密信残页", "intent": "逼出宗门反应"},
            {"agent_id": "秦昭", "action": "暗中联络外援", "intent": "试探外部态度"},
        ]],
        goal_payloads=[{"goal_reached": False, "reason": "首轮后继续观察", "confidence": 0.21}],
    )
    app = create_app()
    client = app.test_client()

    session_id = create_session(client, project.project_id)
    response = client.post(
        f"/api/worldline/session/{session_id}/auto-evolve",
        json={
            "project_id": project.project_id,
            "mode": "first_round",
            "goal_text": "",
            "max_steps": 1,
        },
    )

    assert response.status_code == 202, response.get_json()
    task_id = response.get_json()["data"]["tasks"][0]["task_id"]
    task = wait_for_task(task_id)

    assert task.status == TaskStatus.COMPLETED
    assert task.result["branch_id"] == "main"
    assert task.result["completed_steps"] == 1
    assert len(task.result["latest_event"]["action_effects"]) == 2


def test_auto_evolve_continuous_task_stops_when_branch_settles(tmp_path, monkeypatch):
    project = create_project_with_seed(tmp_path, monkeypatch)
    patch_router(
        monkeypatch,
        action_payloads=[
            {"actions": [{"agent_id": "秦昭", "action": "秘密联络白泽司", "intent": "试探外部态度"}]},
            {"actions": []},
        ],
        goal_payloads=[{"goal_reached": False, "reason": "目标尚未达成", "confidence": 0.2}],
    )
    app = create_app()
    client = app.test_client()

    session_id = create_session(client, project.project_id)
    response = client.post(
        f"/api/worldline/session/{session_id}/auto-evolve",
        json={
            "project_id": project.project_id,
            "mode": "continuous",
            "goal_text": "沈夜掌控局势",
            "max_steps": 5,
        },
    )

    assert response.status_code == 202, response.get_json()
    task_id = response.get_json()["data"]["tasks"][0]["task_id"]
    task = wait_for_task(task_id)

    assert task.status == TaskStatus.COMPLETED
    assert task.result["branch_id"] == "main"
    assert task.result["stop_reason"] == "settled"
    assert task.result["completed_steps"] == 2
    assert task.result["goal_verdict"]["goal_reached"] is False


def test_auto_evolve_task_records_binding_error_in_task_runtime(tmp_path, monkeypatch):
    project = create_project_with_seed(tmp_path, monkeypatch)

    class MissingBindingRouter:
        def build_client(self, module_key):
            raise ValueError(f"{module_key} 缺少绑定")

    monkeypatch.setattr(
        worldline.worldline_auto_evolution_task_service.auto_action_service,
        "llm_router",
        MissingBindingRouter(),
    )
    app = create_app()
    client = app.test_client()

    session_id = create_session(client, project.project_id)
    response = client.post(
        f"/api/worldline/session/{session_id}/auto-evolve",
        json={
            "project_id": project.project_id,
            "mode": "continuous",
            "goal_text": "沈夜掌控局势",
            "max_steps": 3,
        },
    )

    assert response.status_code == 202, response.get_json()
    task_id = response.get_json()["data"]["tasks"][0]["task_id"]
    task = wait_for_task(task_id)

    assert task.status == TaskStatus.FAILED
    assert "worldline_agent_action" in (task.error or "")


def test_resolve_steps_allows_user_defined_limits_above_twenty():
    assert resolve_steps("first_round", 90) == 1
    assert resolve_steps("continuous", 90) == 90
