from app import create_app
from app.config import Config
from app.models.project import ProjectManager


class StubSummarizerClient:
    def chat_json_value(self, messages, temperature=0.2, max_tokens=4096):
        return {
            "summary_text": "第2章摘要：沈夜继续追查镜湖真相。",
            "start_anchor": "沈夜承接上章压力继续推进。",
            "end_anchor": "顾行舟即将现身。",
            "key_events": [{"summary": "沈夜在废塔中找到新线索。"}],
            "open_threads": [{"thread_key": "镜湖真相", "summary": "镜湖真相仍未查清。"}],
            "character_state_updates": [{"name": "沈夜", "state": "active", "summary": "继续调查。"}],
            "relationship_updates": [{"source": "沈夜", "target": "顾行舟", "state": "conflict", "summary": "双方张力升级。"}],
            "timeline_note": "第二天夜间",
            "key_entities": [{"name": "沈夜", "entity_type": "character"}],
        }


class StubRouter:
    def build_client(self, module_key):
        assert module_key == "novel_chapter_summarizer"
        return StubSummarizerClient()


def _configure_storage(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    ProjectManager.PROJECTS_DIR = str(upload_root / "projects")


def test_draft_finalize_generates_and_persists_chapter_card(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    monkeypatch.setattr("app.api.novel.LlmRouter", lambda: StubRouter())
    app = create_app()
    client = app.test_client()

    project = ProjectManager.create_project("定稿章节卡测试")
    ProjectManager.save_project_json(project.project_id, "story_memory.json", {"world_rules": ["镜湖引擎会记录识海残痕。"]})
    ProjectManager.save_project_json(
        project.project_id,
        "chapter_cards.json",
        {
            "chapter_count": 1,
            "chapters": [
                {
                    "chapter_id": "chapter_0001",
                    "chapter_order": 1,
                    "title": "起疑",
                    "summary_text": "第1章摘要：沈夜拿到密信。",
                    "start_anchor": "密信落到沈夜手中。",
                    "end_anchor": "他决定前往废塔。",
                    "key_events": [{"summary": "密信重新点燃镜湖旧案。"}],
                    "open_threads": [{"thread_key": "镜湖真相", "summary": "镜湖真相仍未查清。"}],
                    "character_state_updates": [{"name": "沈夜", "state": "active", "summary": "开始调查。"}],
                    "relationship_updates": [],
                    "timeline_note": "第一天清晨",
                    "key_entities": [{"name": "沈夜", "entity_type": "character"}],
                }
            ],
        },
    )

    response = client.post(
        "/api/novel/draft/finalize",
        json={
            "project_id": project.project_id,
            "chapter_order": 2,
            "chapter_id": "chapter_0002",
            "title": "废塔",
            "chapter_text": "沈夜潜入废塔，准备继续追查镜湖真相。",
        },
    )

    assert response.status_code == 200, response.get_json()
    payload = response.get_json()["data"]
    assert payload["chapter_order"] == 2

    cards = ProjectManager.load_project_json(project.project_id, "chapter_cards.json")
    assert cards["chapter_count"] == 2
    assert cards["chapters"][1]["chapter_id"] == "chapter_0002"
    assert cards["chapters"][1]["summary_text"].startswith("第2章摘要")

    continuity = ProjectManager.load_project_json(project.project_id, "chapter_continuity.json")
    assert continuity["chapter_count"] == 2
    assert continuity["chapters"][1]["order"] == 2
