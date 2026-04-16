import sqlite3

from app.config import Config
from app.models.project import ProjectManager
from app.services.canon_history_retriever import CanonHistoryRetriever
from app.services.chapter_meta_service import ChapterMetaService


def _configure_storage(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    ProjectManager.PROJECTS_DIR = str(upload_root / "projects")


def test_canon_history_retriever_returns_recent_anchors_and_long_range_callbacks(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    project = ProjectManager.create_project("历史召回测试")
    ProjectManager.save_project_json(
        project.project_id,
        "chapter_segments.json",
        {
            "chapter_count": 3,
            "chapters": [
                {"chapter_id": "chapter_0001", "order": 1, "title": "起疑", "content": "第1章正文"},
                {"chapter_id": "chapter_0002", "order": 2, "title": "废塔", "content": "第2章正文"},
                {"chapter_id": "chapter_0003", "order": 3, "title": "镜湖", "content": "第3章正文"},
            ],
        },
    )

    chapter_cards = {
        "chapter_count": 3,
        "chapters": [
            {
                "chapter_id": "chapter_0001",
                "chapter_order": 1,
                "title": "起疑",
                "summary_text": "沈夜拿到密信，镜湖真相被重新提起。",
                "start_anchor": "密信落到沈夜手中。",
                "end_anchor": "他决定去废塔。",
                "key_events": [{"summary": "密信指向镜湖旧案。"}],
                "open_threads": [{"thread_key": "镜湖真相", "summary": "镜湖真相仍未查清。"}],
                "character_state_updates": [{"name": "沈夜", "state": "active", "summary": "开始调查。"}],
                "relationship_updates": [],
                "timeline_note": "第一天清晨",
                "key_entities": [{"name": "沈夜", "entity_type": "character"}],
            },
            {
                "chapter_id": "chapter_0002",
                "chapter_order": 2,
                "title": "废塔",
                "summary_text": "秦昭带沈夜潜入废塔，残响提到顾行舟。",
                "start_anchor": "两人来到废塔前。",
                "end_anchor": "顾行舟可能提前现身。",
                "key_events": [{"summary": "废塔残响警告镜湖谷会出事。"}],
                "open_threads": [{"thread_key": "顾行舟布局", "summary": "顾行舟的布局仍未明朗。"}],
                "character_state_updates": [{"name": "秦昭", "state": "active", "summary": "协助潜入。"}],
                "relationship_updates": [{"source": "沈夜", "target": "秦昭", "state": "ally", "summary": "两人暂时联手。"}],
                "timeline_note": "第一天傍晚",
                "key_entities": [{"name": "秦昭", "entity_type": "character"}],
            },
            {
                "chapter_id": "chapter_0003",
                "chapter_order": 3,
                "title": "镜湖",
                "summary_text": "镜湖谷前夜，顾行舟开始收束局面。",
                "start_anchor": "镜湖谷局势骤然收紧。",
                "end_anchor": "真正的对峙即将开始。",
                "key_events": [{"summary": "顾行舟调动宗门力量。"}],
                "open_threads": [{"thread_key": "镜湖真相", "summary": "镜湖真相仍然悬而未决。"}],
                "character_state_updates": [{"name": "顾行舟", "state": "active", "summary": "开始主导局势。"}],
                "relationship_updates": [{"source": "沈夜", "target": "顾行舟", "state": "conflict", "summary": "双方冲突升级。"}],
                "timeline_note": "第二天夜间",
                "key_entities": [{"name": "顾行舟", "entity_type": "character"}],
            },
        ],
    }
    ProjectManager.save_project_json(project.project_id, "chapter_cards.json", chapter_cards)
    ProjectManager.save_project_json(
        project.project_id,
        "story_memory.json",
        {"world_rules": ["镜湖引擎会记录识海残痕。"]},
    )

    service = ChapterMetaService()
    service.replace_project_chapter_cards(
        project.project_id,
        chapter_cards["chapters"],
        world_rules=["镜湖引擎会记录识海残痕。"],
    )

    result = CanonHistoryRetriever().recall(
        project_id=project.project_id,
        current_chapter_order=4,
        pov_character="沈夜",
        scene_focus="镜湖真相",
        author_instruction="请让顾行舟和镜湖真相的压力一起升级",
    )

    assert [item["chapter_order"] for item in result["recent_anchors"]] == [1, 2, 3]
    assert result["callback_memories"]
    assert all(item["chapter_order"] < 4 for item in result["callback_memories"])
    assert result["active_threads"]
    assert result["world_rules"] == ["镜湖引擎会记录识海残痕。"]
    assert any("scene_focus" in item["selected_because"] for item in result["selection_trace"])

    # history_items are now derived on-the-fly from chapter_meta in the
    # unified DB (no longer persisted to a legacy chapter_history_item table).
    history_items = service.get_history_items(project.project_id, current_chapter_order=4)
    assert len(history_items) >= 4

