import time
import threading

from app import create_app
from app.config import Config
from app.models.project import ProjectManager
from app.utils.llm_json import normalize_json_object


def _configure_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    ProjectManager.PROJECTS_DIR = str(tmp_path / "uploads" / "projects")


def _create_project_with_seed(tmp_path, monkeypatch):
    _configure_paths(tmp_path, monkeypatch)
    project = ProjectManager.create_project("世界线 Prepare 测试")
    project.graph_id = "graph_prepare_demo"
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
                    "target": "秦昭",
                    "relation_type": "ally",
                },
                {
                    "source": "沈夜",
                    "target": "玄霄宗",
                    "relation_type": "tension",
                },
            ],
        },
    )
    return project


def _wait_for_task(client, task_id: str, timeout_seconds: float = 5.0):
    deadline = time.time() + timeout_seconds
    last_payload = None
    while time.time() < deadline:
        response = client.get(f"/api/project/task/{task_id}")
        assert response.status_code == 200, response.get_json()
        last_payload = response.get_json()["data"]
        if last_payload["status"] in {"completed", "failed"}:
            return last_payload
        time.sleep(0.05)
    raise AssertionError(f"任务未在时限内完成: {task_id} / {last_payload}")


class _FakePrepareClient:
    model = "fake-prepare-model"

    def chat_json(self, messages, temperature=0.4, max_tokens=1600):
        payload = self.chat_json_value(messages, temperature=temperature, max_tokens=max_tokens)
        return normalize_json_object(payload, "LLM响应")

    def chat_json_value(self, messages, temperature=0.4, max_tokens=1600):
        prompt = messages[-1]["content"]
        if "玄霄宗" in prompt:
            return {
                "public_profile": {
                    "identity": "玄霄宗，掌控试炼秩序的宗门",
                    "public_stance": "维持表面秩序",
                    "behavior_style": "先压制再观察",
                },
                "private_profile": {
                    "hidden_goal": "找出密信源头后清除隐患",
                    "secrets": ["宗门高层知道密信部分真相"],
                },
                "runtime_seed_state": {
                    "role": "sect",
                    "status": "active",
                    "drive": "维持宗门秩序",
                    "tension": "担心内情外泄",
                    "public_stance": "维稳",
                },
                "relationship_view": {
                    "stance": "对主角保持警惕",
                    "trusted_entities": [],
                    "feared_entities": ["沈夜"],
                },
                "memory_seed_summary": ["密信泄露已经影响宗门声望"],
                "source_evidence_summary": ["seed_analysis: 玄霄宗 summary"],
            }
        if "沈夜 × 玄霄宗" in prompt:
            return {
                "public_profile": {
                    "identity": "沈夜与玄霄宗之间的关键关系",
                    "public_stance": "关系紧绷",
                    "behavior_style": "一有刺激就放大张力",
                },
                "private_profile": {
                    "hidden_goal": "推动双方尽快摊牌",
                    "secrets": ["双方都误判了对方底牌"],
                },
                "runtime_seed_state": {
                    "role": "关系推动者",
                    "status": "active",
                    "drive": "推动关系继续演化",
                    "tension": "双方互不信任",
                    "history": "曾在试炼事件中形成裂痕",
                    "power_dynamic": "玄霄宗掌握制度优势",
                    "trust_level": "低",
                    "conflict_trigger": "密信真相被公开",
                    "stability_forecast": "短期内继续恶化",
                },
                "relationship_view": {
                    "stance": "冲突升温",
                    "trusted_entities": [],
                    "feared_entities": ["玄霄宗"],
                },
                "memory_seed_summary": ["双方关系已被密信事件推向临界点"],
                "source_evidence_summary": ["seed_analysis: 沈夜 -> 玄霄宗 tension"],
            }
        return {
            "public_profile": {
                "identity": "沈夜，调查宗门隐秘的主角",
                "public_stance": "谨慎试探",
                "behavior_style": "先取证再行动",
            },
            "private_profile": {
                "hidden_goal": "找到宗门高层与密信的真实联系",
                "secrets": ["只给作者看：沈夜怀疑秦昭在隐藏关键证据"],
            },
            "runtime_seed_state": {
                "role": "主角",
                "status": "active",
                "drive": "追查密信真相",
                "tension": "不知道谁在暗中盯梢",
                "personality": "冷静克制",
                "skills": ["调查", "潜伏"],
                "loyalty": "真相",
                "secrets": ["沈夜怀疑秦昭"],
            },
            "relationship_view": {
                "stance": "对玄霄宗保持敌意",
                "trusted_entities": ["苏半夏"],
                "feared_entities": ["玄霄宗"],
            },
            "memory_seed_summary": ["密信提前泄露改变了沈夜的行动节奏"],
            "source_evidence_summary": ["seed_analysis: 沈夜 profile_summary"],
        }


class _FakeDialogueClient:
    model = "fake-dialogue-model"
    messages = []

    def chat(self, messages, temperature=0.7, max_tokens=900):
        self.messages.append(messages)
        return "我会继续按自己的判断推进。"


class _ParallelPrepareClient:
    model = "parallel-prepare-model"
    max_concurrency = 3

    def __init__(self, *, fail_on: str = ""):
        self.fail_on = fail_on
        self._lock = threading.Lock()
        self.active_calls = 0
        self.max_active_calls = 0

    def chat_json(self, messages, temperature=0.4, max_tokens=1600):
        payload = self.chat_json_value(messages, temperature=temperature, max_tokens=max_tokens)
        return normalize_json_object(payload, "LLM响应")

    def chat_json_value(self, messages, temperature=0.4, max_tokens=1600):
        prompt = messages[-1]["content"]
        if self.fail_on and self.fail_on in prompt:
            raise RuntimeError(f"parallel dossier failure: {self.fail_on}")
        with self._lock:
            self.active_calls += 1
            self.max_active_calls = max(self.max_active_calls, self.active_calls)
        try:
            time.sleep(0.05)
            return _FakePrepareClient().chat_json_value(messages, temperature=temperature, max_tokens=max_tokens)
        finally:
            with self._lock:
                self.active_calls -= 1


class _ListWrappedPrepareClient(_FakePrepareClient):
    def chat_json_value(self, messages, temperature=0.4, max_tokens=1600):
        return [super().chat_json_value(messages, temperature=temperature, max_tokens=max_tokens)]


class _FakeRouter:
    def __init__(self):
        self.dialogue_client = _FakeDialogueClient()

    def build_client(self, module_key):
        if module_key == "worldline_agent_prepare":
            return _FakePrepareClient()
        if module_key == "worldline_agent_dialogue":
            return self.dialogue_client
        raise AssertionError(f"unexpected module: {module_key}")


def test_worldline_prepare_materializes_dossiers_and_start_uses_prepare_snapshot(tmp_path, monkeypatch):
    project = _create_project_with_seed(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()

    from app.api import worldline_prepare

    fake_router = _FakeRouter()
    monkeypatch.setattr(worldline_prepare.worldline_prepare_service, "llm_router", fake_router)

    prepare_response = client.post(
        "/api/worldline/session/prepare",
        json={"project_id": project.project_id, "variables": ["密信提前泄露"]},
    )
    assert prepare_response.status_code == 202, prepare_response.get_json()
    prepare_payload = prepare_response.get_json()["data"]
    assert prepare_payload["prepare_id"]
    assert prepare_payload["task_id"]

    task = _wait_for_task(client, prepare_payload["task_id"])
    assert task["status"] == "completed", task

    status_response = client.get(f"/api/worldline/session/prepare/{prepare_payload['prepare_id']}")
    assert status_response.status_code == 200, status_response.get_json()
    status_payload = status_response.get_json()["data"]
    assert status_payload["status"] == "ready"
    assert status_payload["can_start"] is True

    agents_response = client.get(f"/api/worldline/session/prepare/{prepare_payload['prepare_id']}/agents")
    assert agents_response.status_code == 200, agents_response.get_json()
    agent_items = agents_response.get_json()["data"]["agents"]
    assert len(agent_items) >= 3
    protagonist = next(item for item in agent_items if item["display_name"] == "沈夜")
    assert protagonist["model_name"] == "fake-prepare-model"
    assert protagonist["public_profile"]["identity"]
    assert protagonist["private_profile"]["hidden_goal"]
    assert protagonist["runtime_seed_state"]["drive"] == "追查密信真相"

    start_response = client.post(
        f"/api/worldline/session/prepare/{prepare_payload['prepare_id']}/start",
        json={"project_id": project.project_id},
    )
    assert start_response.status_code == 200, start_response.get_json()
    start_payload = start_response.get_json()["data"]
    assert start_payload["session_id"]
    assert start_payload["prepare_id"] == prepare_payload["prepare_id"]

    detail_response = client.get(
        f"/api/worldline/session/{start_payload['session_id']}/agents/{protagonist['agent_id']}"
    )
    assert detail_response.status_code == 200, detail_response.get_json()
    detail_payload = detail_response.get_json()["data"]
    assert detail_payload["baseline_dossier"]["prepare_id"] == prepare_payload["prepare_id"]
    assert detail_payload["baseline_dossier"]["private_profile"]["hidden_goal"]
    assert detail_payload["current_agent"]["display_name"] == "沈夜"
    assert detail_payload["history"]["snapshots"]


def test_worldline_prepare_failure_surfaces_task_error_and_blocks_start(tmp_path, monkeypatch):
    project = _create_project_with_seed(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()

    from app.api import worldline_prepare

    class MissingRouter:
        def build_client(self, module_key):
            raise ValueError(f"{module_key} 未绑定可用模型")

    monkeypatch.setattr(worldline_prepare.worldline_prepare_service, "llm_router", MissingRouter())

    prepare_response = client.post(
        "/api/worldline/session/prepare",
        json={"project_id": project.project_id, "variables": ["密信提前泄露"]},
    )
    assert prepare_response.status_code == 202, prepare_response.get_json()
    prepare_payload = prepare_response.get_json()["data"]

    task = _wait_for_task(client, prepare_payload["task_id"])
    assert task["status"] == "failed", task
    assert "worldline_agent_prepare" in (task["error"] or "")

    status_response = client.get(f"/api/worldline/session/prepare/{prepare_payload['prepare_id']}")
    assert status_response.status_code == 200, status_response.get_json()
    assert status_response.get_json()["data"]["status"] == "failed"
    assert status_response.get_json()["data"]["can_start"] is False

    start_response = client.post(f"/api/worldline/session/prepare/{prepare_payload['prepare_id']}/start")
    assert start_response.status_code == 400, start_response.get_json()


def test_agent_dialogue_context_does_not_leak_other_agent_private_profile(tmp_path, monkeypatch):
    project = _create_project_with_seed(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()

    from app.api import worldline_prepare, worldline_interaction

    fake_router = _FakeRouter()
    monkeypatch.setattr(worldline_prepare.worldline_prepare_service, "llm_router", fake_router)
    monkeypatch.setattr(worldline_interaction.character_agent_service, "llm_router", fake_router)

    prepare_response = client.post(
        "/api/worldline/session/prepare",
        json={"project_id": project.project_id, "variables": ["密信提前泄露"]},
    )
    prepare_payload = prepare_response.get_json()["data"]
    task = _wait_for_task(client, prepare_payload["task_id"])
    assert task["status"] == "completed", task

    start_response = client.post(f"/api/worldline/session/prepare/{prepare_payload['prepare_id']}/start")
    assert start_response.status_code == 200, start_response.get_json()
    session_id = start_response.get_json()["data"]["session_id"]

    roster = client.get(f"/api/worldline/session/{session_id}/agents").get_json()["data"]["agents"]
    actor = next(item for item in roster if item["display_name"] == "沈夜")

    dialogue_response = client.post(
        f"/api/worldline/session/{session_id}/agent-dialogue",
        json={"agent_id": actor["agent_id"], "message": "你打算怎么处理今晚的局势？", "mode": "llm"},
    )
    assert dialogue_response.status_code == 200, dialogue_response.get_json()

    prompt_text = str(fake_router.dialogue_client.messages[-1])
    assert "只给作者看：沈夜怀疑秦昭在隐藏关键证据" in prompt_text
    assert "宗门高层知道密信部分真相" not in prompt_text


def test_worldline_prepare_materializes_dossiers_in_parallel(tmp_path, monkeypatch):
    project = _create_project_with_seed(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()

    from app.api import worldline_prepare

    parallel_client = _ParallelPrepareClient()

    class ParallelRouter:
        def build_client(self, module_key):
            if module_key != "worldline_agent_prepare":
                raise AssertionError(f"unexpected module: {module_key}")
            return parallel_client

    monkeypatch.setattr(worldline_prepare.worldline_prepare_service, "llm_router", ParallelRouter())

    prepare_response = client.post(
        "/api/worldline/session/prepare",
        json={"project_id": project.project_id, "variables": ["密信提前泄露"]},
    )
    assert prepare_response.status_code == 202, prepare_response.get_json()

    task = _wait_for_task(client, prepare_response.get_json()["data"]["task_id"])
    assert task["status"] == "completed", task
    assert parallel_client.max_active_calls >= 2


def test_worldline_prepare_parallel_worker_failure_fails_entire_prepare(tmp_path, monkeypatch):
    project = _create_project_with_seed(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()

    from app.api import worldline_prepare

    parallel_client = _ParallelPrepareClient(fail_on="玄霄宗")

    class ParallelRouter:
        def build_client(self, module_key):
            if module_key != "worldline_agent_prepare":
                raise AssertionError(f"unexpected module: {module_key}")
            return parallel_client

    monkeypatch.setattr(worldline_prepare.worldline_prepare_service, "llm_router", ParallelRouter())

    prepare_response = client.post(
        "/api/worldline/session/prepare",
        json={"project_id": project.project_id, "variables": ["密信提前泄露"]},
    )
    assert prepare_response.status_code == 202, prepare_response.get_json()
    prepare_payload = prepare_response.get_json()["data"]

    task = _wait_for_task(client, prepare_payload["task_id"])
    assert task["status"] == "failed", task
    assert "parallel dossier failure" in (task["error"] or "")

    status_response = client.get(f"/api/worldline/session/prepare/{prepare_payload['prepare_id']}")
    assert status_response.status_code == 200, status_response.get_json()
    assert status_response.get_json()["data"]["status"] == "failed"

    start_response = client.post(f"/api/worldline/session/prepare/{prepare_payload['prepare_id']}/start")
    assert start_response.status_code == 400, start_response.get_json()


def test_worldline_prepare_accepts_single_object_list_payload(tmp_path, monkeypatch):
    project = _create_project_with_seed(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()

    from app.api import worldline_prepare

    class ListWrappedRouter:
        def build_client(self, module_key):
            if module_key != "worldline_agent_prepare":
                raise AssertionError(f"unexpected module: {module_key}")
            return _ListWrappedPrepareClient()

    monkeypatch.setattr(worldline_prepare.worldline_prepare_service, "llm_router", ListWrappedRouter())

    prepare_response = client.post(
        "/api/worldline/session/prepare",
        json={"project_id": project.project_id, "variables": ["密信提前泄露"]},
    )
    assert prepare_response.status_code == 202, prepare_response.get_json()
    prepare_payload = prepare_response.get_json()["data"]

    task = _wait_for_task(client, prepare_payload["task_id"])
    assert task["status"] == "completed", task

    agents_response = client.get(f"/api/worldline/session/prepare/{prepare_payload['prepare_id']}/agents")
    assert agents_response.status_code == 200, agents_response.get_json()
    assert len(agents_response.get_json()["data"]["agents"]) >= 3
