from app import create_app
from app.config import Config
from app.models.project import ProjectManager


def _configure_storage(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    ProjectManager.PROJECTS_DIR = str(upload_root / "projects")


def _save_archive_payload(project):
    ProjectManager.save_project_json(
        project.project_id,
        "narrative_archives.json",
        {
            "project_id": project.project_id,
            "project_name": project.name,
            "count": 2,
            "entity_types": ["Character"],
            "archives": [
                {
                    "entity_uuid": "char_shenye",
                    "entity_name": "沈夜",
                    "entity_type": "Character",
                    "agent_kind": "character",
                    "importance_tier": "protagonist",
                    "recommended_importance_tier": "protagonist",
                    "selected_importance_tier": "protagonist",
                    "template_key": "character.protagonist.v1",
                    "template_version": "v1",
                    "template_sections": ["identity", "motivation", "state"],
                    "template_payload": {"identity": {"entity_name": "沈夜"}},
                    "template_metadata": {"source": "test"},
                    "entity_role": "主角",
                    "core_drive": "查清镜湖真相",
                    "surface_mask": "冷静",
                    "hidden_tension": "担心被玄霄宗反制",
                    "relationship_summary": "与秦昭暂时联手",
                    "agent_behavior_hint": "先查证再出手",
                    "human_ai_relation_tag": "human",
                    "notable_risks": ["过早公开"],
                    "can_act_as_agent": True,
                },
                {
                    "entity_uuid": "char_qinzhao",
                    "entity_name": "秦昭",
                    "entity_type": "Character",
                    "agent_kind": "character",
                    "importance_tier": "major",
                    "recommended_importance_tier": "major",
                    "selected_importance_tier": "major",
                    "template_key": "character.major.v1",
                    "template_version": "v1",
                    "template_sections": ["identity", "motivation", "state"],
                    "template_payload": {"identity": {"entity_name": "秦昭"}},
                    "template_metadata": {"source": "test"},
                    "entity_role": "盟友",
                    "core_drive": "保持筹码优势",
                    "surface_mask": "从容",
                    "hidden_tension": "与回声会旧账未清",
                    "relationship_summary": "与沈夜结成暂时同盟",
                    "agent_behavior_hint": "先试探",
                    "human_ai_relation_tag": "human",
                    "notable_risks": ["立场未稳"],
                    "can_act_as_agent": True,
                },
            ],
        },
    )


def _seed_writer_project(project):
    ProjectManager.save_project_json(
        project.project_id,
        "chapter_segments.json",
        {
            "chapter_count": 2,
            "chapters": [
                {"chapter_id": "chapter_0001", "order": 1, "title": "起疑", "content": "沈夜得到密信。"},
                {"chapter_id": "chapter_0002", "order": 2, "title": "废塔", "content": "秦昭带沈夜潜入废塔。"},
            ],
        },
    )
    ProjectManager.save_project_json(
        project.project_id,
        "seed_analysis.json",
        {
            "characters": [{"name": "沈夜"}, {"name": "秦昭"}],
            "organizations": [{"name": "玄霄宗"}],
        },
    )
    ProjectManager.save_project_json(
        project.project_id,
        "story_memory.json",
        {
            "block_count": 1,
            "entity_registry": {"沈夜": {"name": "沈夜"}, "秦昭": {"name": "秦昭"}},
            "alias_map": {},
            "relationship_ledger": [
                {
                    "source": "沈夜",
                    "target": "秦昭",
                    "changes": [{"block_id": "block_0001", "change": "ally", "evidence": ["合作潜入废塔"]}],
                }
            ],
            "event_timeline": [
                {
                    "event_id": "event_1",
                    "chapter_id": "chapter_0002",
                    "block_id": "block_0001",
                    "summary": "废塔残响警告顾行舟已调整试炼顺序。",
                    "characters": ["沈夜", "秦昭"],
                    "organizations": ["玄霄宗"],
                }
            ],
            "open_threads": [
                {
                    "thread_key": "镜湖真相",
                    "status": "open",
                    "summary": "顾行舟如何利用镜湖引擎仍未查明。",
                    "chapter_id": "chapter_0002",
                    "block_id": "block_0001",
                }
            ],
            "world_rules": ["镜湖引擎会记录修士识海残痕。"],
            "block_summaries": [{"block_id": "block_0001", "summary": "沈夜与秦昭在废塔听见残响警告。"}],
        },
    )
    ProjectManager.save_project_json(
        project.project_id,
        "chapter_continuity.json",
        {
            "chapter_count": 2,
            "global_summary": "沈夜逐步逼近镜湖真相。",
            "chapters": [
                {
                    "chapter_id": "chapter_0001",
                    "order": 1,
                    "title": "起疑",
                    "head_context": "沈夜刚拿到密信。",
                    "core_conflicts": ["密信指向玄霄宗旧案。"],
                    "key_characters": ["沈夜"],
                    "key_organizations": ["玄霄宗"],
                    "tail_hooks": ["秦昭现身。"],
                    "continuity_summary": "密信让沈夜转向废塔线索。",
                },
                {
                    "chapter_id": "chapter_0002",
                    "order": 2,
                    "title": "废塔",
                    "head_context": "秦昭带沈夜潜入废塔。",
                    "core_conflicts": ["顾行舟已调整试炼顺序。"],
                    "key_characters": ["沈夜", "秦昭"],
                    "key_organizations": ["玄霄宗"],
                    "tail_hooks": ["镜湖谷可能提前封锁。"],
                    "continuity_summary": "废塔残响把冲突推向镜湖谷。",
                },
            ],
        },
    )
    ProjectManager.save_project_json(
        project.project_id,
        "consistency_report.json",
        {
            "conflict_count": 0,
            "ambiguity_count": 1,
            "conflicts": [],
            "ambiguities": [{"alias": "夜哥", "candidate_names": ["沈夜", "沈临川"], "reason": "别名歧义"}],
            "summary": "存在 1 条歧义。",
        },
    )
    _save_archive_payload(project)


def test_chapter_context_options_and_project_pack_api(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    project = ProjectManager.create_project("API 写作上下文")
    _seed_writer_project(project)
    app = create_app()
    client = app.test_client()

    options_response = client.get(f"/api/novel/chapter-context/options?project_id={project.project_id}")
    assert options_response.status_code == 200, options_response.get_json()
    options_data = options_response.get_json()["data"]
    assert options_data["project_id"] == project.project_id
    assert len(options_data["chapters"]) == 2
    assert "沈夜" in options_data["pov_characters"]

    pack_response = client.post(
        "/api/novel/chapter-context",
        json={
            "scope_type": "project_chapter",
            "project_id": project.project_id,
            "chapter_order": 2,
            "pov_character": "沈夜",
            "writing_goal": "生成废塔场景卡",
            "scene_focus": "废塔残响",
        },
    )
    assert pack_response.status_code == 200, pack_response.get_json()
    pack = pack_response.get_json()["data"]
    assert pack["context_scope"]["chapter_id"] == "chapter_0002"
    assert pack["must_know"]
    assert pack["writer_prompt_block"]


def test_chapter_context_api_supports_worldline_branch_scope(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    project = ProjectManager.create_project("世界线写作上下文")
    project.analysis_goal = "观察镜湖谷对峙后的世界变化"
    ProjectManager.save_project(project)
    _seed_writer_project(project)
    app = create_app()
    client = app.test_client()

    session_response = client.post(
        "/api/worldline/session/create",
        json={"project_id": project.project_id, "branch_count": 1, "variables": ["顾行舟提前现身"]},
    )
    assert session_response.status_code == 200, session_response.get_json()
    session_id = session_response.get_json()["data"]["session_id"]

    pack_response = client.post(
        "/api/novel/chapter-context",
        json={
            "scope_type": "worldline_branch",
            "project_id": project.project_id,
            "session_id": session_id,
            "branch_id": "main",
            "pov_character": "沈夜",
            "writing_goal": "生成世界线分支场景卡",
            "scene_focus": "顾行舟现身后的对峙",
        },
    )
    assert pack_response.status_code == 200, pack_response.get_json()
    pack = pack_response.get_json()["data"]
    assert pack["context_scope"]["scope_type"] == "worldline_branch"
    assert pack["must_know"]
    assert any(item["category"] == "worldline_event" for item in pack["must_know"])
    assert any(item["category"] == "world_rule" for item in pack["must_know"])
    assert any(item["category"] == "consistency_risk" for item in pack["warnings"])
    assert all(item["memory_layer"] == "canon" for item in pack["must_know"] + pack["should_know"] + pack["warnings"])


def test_chapter_context_api_validates_required_scope_fields(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    project = ProjectManager.create_project("上下文参数校验")
    _seed_writer_project(project)
    app = create_app()
    client = app.test_client()

    missing_pov_response = client.post(
        "/api/novel/chapter-context",
        json={
            "scope_type": "worldline_branch",
            "project_id": project.project_id,
            "session_id": "ws_demo",
            "branch_id": "main",
            "writing_goal": "生成世界线分支场景卡",
        },
    )
    assert missing_pov_response.status_code == 400, missing_pov_response.get_json()
    assert "pov_character" in missing_pov_response.get_json()["error"]

    missing_chapter_response = client.post(
        "/api/novel/chapter-context",
        json={
            "scope_type": "project_chapter",
            "project_id": project.project_id,
            "pov_character": "沈夜",
            "writing_goal": "生成废塔场景卡",
        },
    )
    assert missing_chapter_response.status_code == 400, missing_chapter_response.get_json()
    assert "chapter_id 或 chapter_order" in missing_chapter_response.get_json()["error"]
