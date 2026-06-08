from app import create_app
from app.models.project import ProjectManager

from tests.test_chapter_context_api import _configure_storage, _seed_writer_project


def test_v2_chapter_context_options_and_project_build_match_legacy_contract(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    project = ProjectManager.create_project("V2 写作上下文")
    _seed_writer_project(project)
    app = create_app()
    client = app.test_client()

    options_response = client.get(
        "/api/v2/chapter-context/options",
        query_string={"project_id": project.project_id},
    )
    assert options_response.status_code == 200, options_response.get_json()
    options_data = options_response.get_json()["data"]
    assert options_data["project_id"] == project.project_id
    assert len(options_data["chapters"]) == 2
    assert "沈夜" in options_data["pov_characters"]

    build_response = client.post(
        "/api/v2/chapter-context/builds",
        json={
            "scope_type": "project_chapter",
            "project_id": project.project_id,
            "chapter_order": 2,
            "pov_character": "沈夜",
            "writing_goal": "生成废塔场景卡",
            "scene_focus": "废塔残响",
        },
    )
    assert build_response.status_code == 200, build_response.get_json()
    pack = build_response.get_json()["data"]
    assert pack["context_scope"]["chapter_id"] == "chapter_0002"
    assert pack["must_know"]
    assert pack["writer_prompt_block"]


def test_v2_chapter_context_build_supports_worldline_scope(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    project = ProjectManager.create_project("V2 世界线写作上下文")
    project.analysis_goal = "观察镜湖谷对峙后的世界变化"
    ProjectManager.save_project(project)
    _seed_writer_project(project)
    app = create_app()
    client = app.test_client()

    session_response = client.post(
        "/api/worldline/session/create",
        json={
            "project_id": project.project_id,
            "branch_count": 1,
            "variables": ["顾行舟提前现身"],
        },
    )
    assert session_response.status_code == 200, session_response.get_json()
    session_id = session_response.get_json()["data"]["session_id"]

    build_response = client.post(
        "/api/v2/chapter-context/builds",
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
    assert build_response.status_code == 200, build_response.get_json()
    pack = build_response.get_json()["data"]
    assert pack["context_scope"]["scope_type"] == "worldline_branch"
    assert any(item["category"] == "worldline_event" for item in pack["must_know"])
    assert any(item["category"] == "world_rule" for item in pack["must_know"])


def test_v2_chapter_context_build_preserves_validation_errors(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    project = ProjectManager.create_project("V2 上下文参数校验")
    _seed_writer_project(project)
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/v2/chapter-context/builds",
        json={
            "scope_type": "project_chapter",
            "project_id": project.project_id,
            "pov_character": "沈夜",
            "writing_goal": "生成废塔场景卡",
        },
    )
    assert response.status_code == 400, response.get_json()
    assert "chapter_id 或 chapter_order" in response.get_json()["error"]
