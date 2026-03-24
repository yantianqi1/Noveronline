from app.config import Config
from app.models.project import ProjectManager
from app.services.chapter_context_pack_builder import ChapterContextPackBuilder
import pytest


def _configure_storage(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    ProjectManager.PROJECTS_DIR = str(upload_root / "projects")


def _create_project_with_writer_artifacts():
    project = ProjectManager.create_project("写作上下文测试")
    ProjectManager.save_project_json(
        project.project_id,
        "chapter_segments.json",
        {
            "chapter_count": 3,
            "chapters": [
                {"chapter_id": "chapter_0001", "order": 1, "title": "风雪将起", "content": "沈夜收到密信。"},
                {"chapter_id": "chapter_0002", "order": 2, "title": "试炼前夜", "content": "秦昭带沈夜潜入废塔。"},
                {"chapter_id": "chapter_0003", "order": 3, "title": "镜湖对峙", "content": "顾行舟现身。"},
            ],
        },
    )
    ProjectManager.save_project_json(
        project.project_id,
        "seed_analysis.json",
        {
            "characters": [
                {"name": "沈夜", "importance_tier": "protagonist"},
                {"name": "秦昭", "importance_tier": "major"},
                {"name": "顾行舟", "importance_tier": "major"},
            ],
            "organizations": [{"name": "玄霄宗", "importance_tier": "major"}],
        },
    )
    ProjectManager.save_project_json(
        project.project_id,
        "story_memory.json",
        {
            "block_count": 2,
            "entity_registry": {
                "沈夜": {"name": "沈夜", "entity_type": "character", "summary": "追查镜湖旧案"},
                "秦昭": {"name": "秦昭", "entity_type": "character", "summary": "熟悉回声会暗线"},
            },
            "alias_map": {"夜哥": "沈夜"},
            "relationship_ledger": [
                {
                    "source": "沈夜",
                    "target": "秦昭",
                    "changes": [{"block_id": "block_0001", "change": "ally", "evidence": ["两人暂时联手"]}],
                }
            ],
            "event_timeline": [
                {
                    "event_id": "event_1",
                    "chapter_id": "chapter_0001",
                    "block_id": "block_0001",
                    "summary": "沈夜得到密信，怀疑父亲之死另有隐情。",
                    "characters": ["沈夜"],
                    "organizations": ["玄霄宗"],
                },
                {
                    "event_id": "event_2",
                    "chapter_id": "chapter_0002",
                    "block_id": "block_0001",
                    "summary": "秦昭带沈夜潜入废塔，启动镜湖引擎残响。",
                    "characters": ["沈夜", "秦昭"],
                    "organizations": ["玄霄宗"],
                },
            ],
            "open_threads": [
                {
                    "thread_key": "镜湖真相",
                    "status": "open",
                    "summary": "镜湖引擎与沈临川之死之间的联系仍未查清。",
                    "chapter_id": "chapter_0002",
                    "block_id": "block_0001",
                }
            ],
            "world_rules": ["镜湖引擎可以读取修士识海残痕。", "被引擎记录的念头可能成为审判证词。"],
            "block_summaries": [
                {"block_id": "block_0001", "summary": "沈夜与秦昭追查镜湖旧案。"},
                {"block_id": "block_0002", "summary": "顾行舟准备在镜湖谷收束局面。"},
            ],
        },
    )
    ProjectManager.save_project_json(
        project.project_id,
        "chapter_continuity.json",
        {
            "chapter_count": 3,
            "global_summary": "沈夜沿着密信线索逼近镜湖真相。",
            "chapters": [
                {
                    "chapter_id": "chapter_0001",
                    "order": 1,
                    "title": "风雪将起",
                    "head_context": "沈夜刚拿到密信。",
                    "core_conflicts": ["沈夜怀疑玄霄宗与白泽司联手掩盖旧案。"],
                    "key_characters": ["沈夜"],
                    "key_organizations": ["玄霄宗"],
                    "tail_hooks": ["秦昭主动提出潜入废塔。"],
                    "continuity_summary": "沈夜拿到密信，并被引向废塔线索。",
                },
                {
                    "chapter_id": "chapter_0002",
                    "order": 2,
                    "title": "试炼前夜",
                    "head_context": "秦昭带沈夜来到废塔前。",
                    "core_conflicts": ["废塔中的残响警告顾行舟已更改试炼顺序。"],
                    "key_characters": ["沈夜", "秦昭"],
                    "key_organizations": ["玄霄宗"],
                    "tail_hooks": ["顾行舟可能在镜湖谷现身。"],
                    "continuity_summary": "废塔残响把冲突推向镜湖谷。",
                },
                {
                    "chapter_id": "chapter_0003",
                    "order": 3,
                    "title": "镜湖对峙",
                    "head_context": "顾行舟在镜湖谷现身。",
                    "core_conflicts": ["三方势力同时逼近，沈夜必须决定是否公开真相。"],
                    "key_characters": ["沈夜", "顾行舟"],
                    "key_organizations": ["玄霄宗"],
                    "tail_hooks": ["沈夜准备让被埋起来的人先说话。"],
                    "continuity_summary": "镜湖谷的对峙决定下一条世界线走向。",
                },
            ],
        },
    )
    ProjectManager.save_project_json(
        project.project_id,
        "consistency_report.json",
        {
            "conflict_count": 1,
            "ambiguity_count": 1,
            "conflicts": [
                {
                    "kind": "post_death_activity",
                    "name": "沈临川",
                    "death_block_id": "block_0001",
                    "activity_block_id": "block_0002",
                    "evidence": ["残响中再次出现沈临川的声音。"],
                }
            ],
            "ambiguities": [
                {
                    "block_id": "block_0001",
                    "alias": "夜哥",
                    "candidate_names": ["沈夜", "沈临川"],
                    "reason": "称呼可能混淆两代人。",
                }
            ],
            "summary": "发现 2 条连续性风险。",
        },
    )
    return project


def test_chapter_context_pack_builder_builds_writer_ready_project_pack(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    project = _create_project_with_writer_artifacts()

    pack = ChapterContextPackBuilder().build(
        {
            "scope_type": "project_chapter",
            "project_id": project.project_id,
            "chapter_order": 2,
            "pov_character": "沈夜",
            "writing_goal": "产出第二章场景卡",
            "scene_focus": "废塔残响",
            "include_candidates": False,
        }
    )

    assert pack["context_scope"]["scope_type"] == "project_chapter"
    assert pack["context_scope"]["chapter_id"] == "chapter_0002"
    assert pack["must_know"]
    assert pack["warnings"]
    assert 2 <= len(pack["scene_candidates"]) <= 5
    assert "写作目标" in pack["writer_prompt_block"]
    assert "必须延续的事实" in pack["writer_prompt_block"]
    assert any(item["category"] == "world_rule" for item in pack["must_know"])
    assert any(item["category"] == "consistency_risk" for item in pack["warnings"])
    assert all(item["memory_layer"] == "canon" for item in pack["must_know"])
    assert pack["debug_trace"]


def test_chapter_context_pack_builder_requires_pov_and_chapter_selector(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    project = _create_project_with_writer_artifacts()
    builder = ChapterContextPackBuilder()

    with pytest.raises(ValueError, match="pov_character"):
        builder.build(
            {
                "scope_type": "project_chapter",
                "project_id": project.project_id,
                "chapter_order": 2,
                "writing_goal": "产出第二章场景卡",
            }
        )

    with pytest.raises(ValueError, match="chapter_id 或 chapter_order"):
        builder.build(
            {
                "scope_type": "project_chapter",
                "project_id": project.project_id,
                "pov_character": "沈夜",
                "writing_goal": "产出第二章场景卡",
            }
        )
