import io
import time

from app import create_app
from app.models.project import ProjectManager


class StubLlmClient:
    def __init__(self, module_key: str):
        self.module_key = module_key

    def chat_json_value(self, messages, temperature=0.3, max_tokens=4096):
        if self.module_key == "local_block_facts":
            return [{
                "local_events": [
                    "沈夜在玄霄宗山门前跪了一夜等候密信",
                    "苏半夏替沈夜拆开来自白泽司的密信",
                ],
                "local_entities": [
                    "沈夜",
                    "苏半夏",
                    "玄霄宗",
                    "白泽司",
                ],
                "local_relationship_changes": [
                    "苏半夏协助沈夜拆阅密信，表现出协作关系",
                ],
                "local_threads": [
                    "密信线继续推进",
                ],
                "unresolved_refs": [
                    "白泽司的具体性质仍需确认",
                ],
                "local_summary": "沈夜拿到密信，并在苏半夏帮助下确认镜湖线索。",
                "evidence_spans": [
                    "沈夜在玄霄宗山门前跪了一夜，只为等一封来自白泽司的密信",
                ],
            }]
        if self.module_key == "contextual_block_analysis":
            return [{
                "plot_summary": "沈夜拿到密信后，镜湖主线正式启动。",
                "character_state_updates": [
                    "沈夜保持主动",
                    "苏半夏提供协助",
                ],
                "relationship_updates": [
                    "沈夜与苏半夏形成协作",
                ],
                "thread_updates": [
                    "密信线继续推进",
                ],
                "block_end_state": "沈夜决定继续追查镜湖真相",
            }]
        if self.module_key == "novel_chapter_summarizer":
            return [{
                "summary_text": "本章围绕密信与镜湖线索展开，沈夜开始进入主线调查。",
                "start_anchor": "沈夜承接前情继续追查白泽司密信。",
                "end_anchor": "镜湖真相仍未明朗，下一章冲突继续升级。",
                "key_events": [
                    {"summary": "沈夜拿到密信。"},
                    {"summary": "镜湖线索被正式点燃。"},
                ],
                "open_threads": [
                    {"thread_key": "镜湖真相", "summary": "镜湖真相仍待继续追查。"},
                ],
                "character_state_updates": [
                    {"name": "沈夜", "state": "active", "summary": "继续主动推进调查。"},
                ],
                "relationship_updates": [
                    {"source": "沈夜", "target": "苏半夏", "state": "ally", "summary": "二人形成协作。"},
                ],
                "timeline_note": "剧情仍发生在同一段连续时序中。",
                "key_entities": [
                    {"name": "沈夜", "entity_type": "character"},
                    {"name": "苏半夏", "entity_type": "character"},
                    {"name": "白泽司", "entity_type": "organization"},
                ],
            }]
        return [{
            "entity_types": [
                {"name": "Character", "description": "Named story character", "attributes": [], "examples": ["沈夜"]},
                {"name": "Organization", "description": "Story organization", "attributes": [], "examples": ["玄霄宗"]},
                {"name": "Faction", "description": "Faction", "attributes": [], "examples": ["白泽司"]},
                {"name": "PlotEvent", "description": "Plot event", "attributes": [], "examples": ["密信曝光"]},
            ],
            "edge_types": [
                {
                    "name": "KNOWS",
                    "description": "Characters know each other",
                    "source_targets": [{"source": "Character", "target": "Character"}],
                    "attributes": [],
                }
            ],
            "analysis_summary": "已生成测试用 ontology。",
            "story_focus": ["追查镜湖真相"],
        }]


def _wait_for_task(client, task_id: str, timeout: float = 15.0):
    deadline = time.time() + timeout
    latest = None
    while time.time() < deadline:
        response = client.get(f"/api/project/task/{task_id}")
        assert response.status_code == 200, response.get_json()
        latest = response.get_json()["data"]
        if latest["status"] in {"completed", "failed"}:
            return latest
        time.sleep(0.05)
    raise AssertionError(f"任务超时未完成: {task_id}, latest={latest}")


def test_async_seed_pipeline_normalizes_loose_llm_payloads(tmp_path, monkeypatch):
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")

    monkeypatch.setattr(
        "app.services.llm_router.LlmRouter.build_client",
        lambda self, module_key: StubLlmClient(module_key),
    )
    monkeypatch.setattr(
        "app.services.llm_router.LlmRouter.model_name_for_stage",
        lambda self, stage: "stub-model",
    )

    app = create_app()
    client = app.test_client()
    novel_text = "\n\n".join(
        [
            "第1章 山门雪夜\n沈夜在玄霄宗山门前跪了一夜，只为等一封来自白泽司的密信。",
            "第2章 密信开封\n苏半夏替沈夜拆开密信，信中提到镜湖引擎能够读取修士识海残痕。",
            "第3章 谷口对峙\n顾行舟、林雁回与霍承安同时逼近镜湖谷，沈夜必须决定公开真相还是继续潜伏。",
        ]
    )

    response = client.post(
        "/api/project/seed/extract",
        data={
            "analysis_goal": "提取角色、组织与关系并用于平行世界推演",
            "project_name": "LLM 松散 JSON 归一化",
            "use_llm": "true",
            "files": (io.BytesIO(novel_text.encode("utf-8")), "loose-llm.txt"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 202, response.get_json()

    payload = response.get_json()["data"]
    task = _wait_for_task(client, payload["task_id"])
    assert task["status"] == "completed", task

    seed_analysis = task["result"]["seed_analysis"]
    assert seed_analysis["character_count"] >= 2, task["result"]
    assert seed_analysis["organization_count"] >= 1, task["result"]
