from app import create_app
from app.config import Config
from app.models.project import ProjectManager


def _configure_storage(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    ProjectManager.PROJECTS_DIR = str(upload_root / "projects")
    return upload_root


def _create_project(name: str, analysis_goal: str = ""):
    project = ProjectManager.create_project(name)
    project.analysis_goal = analysis_goal
    ProjectManager.save_project(project)
    return project


def _archive_payload(project, archives):
    return {
        "project_id": project.project_id,
        "project_name": project.name,
        "graph_id": project.graph_id,
        "count": len(archives),
        "entity_types": sorted({item["entity_type"] for item in archives}),
        "archives": archives,
    }


def _make_archive(entity_uuid: str, entity_name: str, entity_type: str, importance_tier: str, core_drive: str):
    return {
        "entity_uuid": entity_uuid,
        "entity_name": entity_name,
        "entity_type": entity_type,
        "importance_tier": importance_tier,
        "entity_role": f"{entity_name} 的定位",
        "core_drive": core_drive,
        "surface_mask": f"{entity_name} 的外在形象",
        "hidden_tension": f"{entity_name} 的隐藏矛盾",
        "relationship_summary": f"{entity_name} 的关系摘要",
        "agent_behavior_hint": f"{entity_name} 的行动倾向",
        "human_ai_relation_tag": "human" if entity_type == "Character" else "none",
        "notable_risks": ["风险A", "风险B"],
        "can_act_as_agent": True,
    }


def _save_archives(project, archives):
    ProjectManager.save_project_json(
        project.project_id,
        "narrative_archives.json",
        _archive_payload(project, archives),
    )


def _save_seed_analysis(project):
    ProjectManager.save_project_json(
        project.project_id,
        "seed_analysis.json",
        {
            "characters": [
                {
                    "name": "沈夜",
                    "importance_tier": "protagonist",
                    "identity_hint": "主角",
                    "profile_summary": "在三方势力之间寻找真相",
                }
            ],
            "organizations": [
                {
                    "name": "玄霄宗",
                    "importance_tier": "major",
                    "organization_type": "sect",
                    "summary": "掌控试炼与秩序",
                }
            ],
            "relations": [{"source": "沈夜", "target": "玄霄宗", "relation_type": "tension"}],
        },
    )


def _create_app_client(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    app = create_app()
    return app.test_client()


def test_archive_library_indexes_existing_project_archives(tmp_path, monkeypatch):
    client = _create_app_client(tmp_path, monkeypatch)
    project_a = _create_project("甲项目", "观察主角命运")
    project_b = _create_project("乙项目", "观察宗门博弈")
    _save_archives(project_a, [_make_archive("char_1", "沈夜", "Character", "protagonist", "查清真相")])
    _save_archives(
        project_b,
        [
            _make_archive("char_1", "沈夜", "Character", "major", "夺回主动权"),
            _make_archive("org_1", "玄霄宗", "Organization", "major", "维持秩序"),
        ],
    )

    list_response = client.get("/api/archive/library")

    assert list_response.status_code == 200, list_response.get_json()
    payload = list_response.get_json()["data"]
    assert payload["count"] == 3
    shenye_items = [item for item in payload["items"] if item["entity_name"] == "沈夜"]
    assert len(shenye_items) == 2
    assert {item["project_name"] for item in shenye_items} == {"甲项目", "乙项目"}
    assert len({item["archive_id"] for item in shenye_items}) == 2

    search_response = client.get("/api/archive/library?q=秩序&entity_type=Organization&importance_tier=major")
    assert search_response.status_code == 200, search_response.get_json()
    search_items = search_response.get_json()["data"]["items"]
    assert len(search_items) == 1
    assert search_items[0]["entity_name"] == "玄霄宗"

    filter_response = client.get(f"/api/archive/library?project_id={project_a.project_id}")
    assert filter_response.status_code == 200, filter_response.get_json()
    assert filter_response.get_json()["data"]["count"] == 1

    detail_response = client.get(f"/api/archive/library/{shenye_items[0]['archive_id']}")
    assert detail_response.status_code == 200, detail_response.get_json()
    assert detail_response.get_json()["data"]["entity_name"] == "沈夜"

    reindex_response = client.post("/api/archive/library/reindex")
    assert reindex_response.status_code == 200, reindex_response.get_json()
    assert reindex_response.get_json()["data"]["count"] == 3


def test_generate_archives_syncs_global_archive_library(tmp_path, monkeypatch):
    client = _create_app_client(tmp_path, monkeypatch)
    project = _create_project("自动归档项目", "观察角色和组织演化")
    _save_seed_analysis(project)

    response = client.post("/api/novel/archives/generate", json={"project_id": project.project_id, "use_llm": False})

    assert response.status_code == 200, response.get_json()
    archives = response.get_json()["data"]["archives"]
    assert archives
    assert all(item["archive_id"] for item in archives)

    library_response = client.get(f"/api/archive/library?project_id={project.project_id}")
    assert library_response.status_code == 200, library_response.get_json()
    library_items = library_response.get_json()["data"]["items"]
    assert {item["entity_name"] for item in library_items} == {"沈夜", "玄霄宗"}


def test_worldline_session_create_accepts_archive_ids_from_single_project(tmp_path, monkeypatch):
    client = _create_app_client(tmp_path, monkeypatch)
    project = _create_project("单项目档案会话", "观察主角与宗门关系变化")
    _save_archives(
        project,
        [
            _make_archive("char_1", "沈夜", "Character", "protagonist", "查清宗门真相"),
            _make_archive("org_1", "玄霄宗", "Organization", "major", "维持内部秩序"),
        ],
    )
    library_items = client.get(f"/api/archive/library?project_id={project.project_id}").get_json()["data"]["items"]
    archive_ids = [item["archive_id"] for item in library_items]

    create_response = client.post(
        "/api/worldline/session/create",
        json={"archive_ids": archive_ids, "branch_count": 1, "variables": ["密信提前泄露"]},
    )

    assert create_response.status_code == 200, create_response.get_json()
    data = create_response.get_json()["data"]
    assert data["project_id"] == project.project_id
    assert data["session_scope"] == "project"
    assert data["source_archive_count"] == 2
    assert data["source_project_ids"] == [project.project_id]
    assert data["simulation_goal"] == "观察主角与宗门关系变化"

    session_response = client.get(f"/api/worldline/session/{data['session_id']}")
    assert session_response.status_code == 200, session_response.get_json()
    assert session_response.get_json()["data"]["session_scope"] == "project"


def test_worldline_session_create_supports_cross_project_archive_mix(tmp_path, monkeypatch):
    client = _create_app_client(tmp_path, monkeypatch)
    project_a = _create_project("甲项目", "甲项目目标")
    project_b = _create_project("乙项目", "乙项目目标")
    _save_archives(project_a, [_make_archive("char_1", "沈夜", "Character", "protagonist", "查清真相")])
    _save_archives(project_b, [_make_archive("org_1", "玄霄宗", "Organization", "major", "守住秩序")])

    archive_items = client.get("/api/archive/library").get_json()["data"]["items"]
    archive_ids = [item["archive_id"] for item in archive_items]

    create_response = client.post(
        "/api/worldline/session/create",
        json={"archive_ids": archive_ids, "branch_count": 1, "variables": ["镜湖引擎失控"]},
    )

    assert create_response.status_code == 200, create_response.get_json()
    data = create_response.get_json()["data"]
    assert data["project_id"] is None
    assert data["session_scope"] == "global"
    assert set(data["source_project_ids"]) == {project_a.project_id, project_b.project_id}
    assert data["source_archive_count"] == 2

    list_response = client.get("/api/worldline/session/list")
    assert list_response.status_code == 200, list_response.get_json()
    session_record = next(item for item in list_response.get_json()["data"]["sessions"] if item["session_id"] == data["session_id"])
    assert session_record["session_scope"] == "global"

    agents_response = client.get(f"/api/worldline/session/{data['session_id']}/agents")
    assert agents_response.status_code == 200, agents_response.get_json()
    agents = agents_response.get_json()["data"]["agents"]
    assert {item["display_name"] for item in agents if item["agent_kind"] != "relationship"} == {"沈夜", "玄霄宗"}

    action_response = client.post(
        f"/api/worldline/session/{data['session_id']}/agent-action",
        json={"agent_id": "沈夜", "action": "公开部分实验记录"},
    )
    assert action_response.status_code == 200, action_response.get_json()

    step_response = client.post(f"/api/worldline/session/{data['session_id']}/step", json={"steps": 1})
    assert step_response.status_code == 200, step_response.get_json()

    dialogue_response = client.post(
        f"/api/worldline/session/{data['session_id']}/agent-dialogue",
        json={"agent_id": "沈夜", "message": "你准备如何面对玄霄宗？"},
    )
    assert dialogue_response.status_code == 200, dialogue_response.get_json()
    assert "沈夜" in dialogue_response.get_json()["data"]["result"]["reply"]
