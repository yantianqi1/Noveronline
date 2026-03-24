from app import create_app
from app.models.project import ProjectManager
from app.services.world_state_store import WorldStateStore
from app.services.worldline_branch_comparison import WorldlineBranchComparisonService
from app.services.worldline_branch_service import WorldlineBranchService
from app.services.worldline_engine import WorldlineEngine
from app.services.worldline_source_loader import WorldlineSourceLoader


def _make_engine(store: WorldStateStore) -> WorldlineEngine:
    return WorldlineEngine(
        store=store,
        source_loader=WorldlineSourceLoader(store),
        branch_service=WorldlineBranchService(),
        comparison_service=WorldlineBranchComparisonService(),
    )


def _create_project_with_seed(tmp_path):
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    project = ProjectManager.create_project("世界线当前世界摘要测试")
    project.graph_id = "graph_compare_demo"
    project.analysis_goal = "观察当前世界中主角与宗门关系的演化状态"
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
                    "profile_summary": "一边调查密信，一边提防宗门试探。",
                },
                {
                    "name": "秦昭",
                    "importance_tier": "major",
                    "identity_hint": "盟友候选",
                    "profile_summary": "在各方势力之间摇摆。",
                },
            ],
            "organizations": [
                {
                    "name": "玄霄宗",
                    "importance_tier": "major",
                    "organization_type": "sect",
                    "summary": "掌控试炼与信息封锁。",
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


def _create_session(tmp_path):
    project = _create_project_with_seed(tmp_path)
    store = WorldStateStore()
    engine = _make_engine(store)
    session, _ = engine.create_session(
        project_id=project.project_id,
        graph_id=project.graph_id,
        focus_question="如果主角提前得知宗门布局，当前世界会如何推进",
        branch_count=2,
        variables=["密信提前泄露", "外门弟子倒戈"],
        config={
            "simulation_goal": "观察不同扰动如何继续改写当前世界",
            "timeline_focus": ["入门试炼", "长老议会"],
            "agent_behavior_axes": ["信息差", "阵营站队"],
            "branch_hypotheses": [
                {
                    "branch_id": "branch_1",
                    "title": "潜伏取证线",
                    "core_change": "沈夜选择暂时隐瞒密信，暗中取证。",
                    "key_agents": ["沈夜", "玄霄宗"],
                },
                {
                    "branch_id": "branch_2",
                    "title": "公开对抗线",
                    "core_change": "沈夜在试炼前公开密信，主动打乱布局。",
                    "key_agents": ["沈夜", "玄霄宗"],
                },
            ],
        },
    )
    engine.inject_action(
        session_id=session.session_id,
        project_id=project.project_id,
        branch_id="main",
        actor="沈夜",
        action="秘密接触外门证人",
        intent="补强证据",
    )
    engine.step(session.session_id, project_id=project.project_id, branch_id="main")
    engine.inject_variable(
        session_id=session.session_id,
        project_id=project.project_id,
        branch_id="main",
        name="城主府暗中介入",
        description="外部势力开始插手宗门事件。",
        impact_axis="外部势力",
    )
    engine.inject_action(
        session_id=session.session_id,
        project_id=project.project_id,
        branch_id="main",
        actor="沈夜",
        action="转移证人去城外",
        intent="保护证人",
    )
    return project, session.session_id, engine


def test_compare_branches_returns_single_main_world_snapshot(tmp_path):
    project, session_id, engine = _create_session(tmp_path)

    comparison = engine.compare_branches(
        session_id,
        {"project_id": project.project_id},
    )

    assert comparison["comparison_axes"]["branch_count"] == 1
    assert "城主府暗中介入" in comparison["comparison_axes"]["shared_variables"]
    branch = comparison["branches"][0]
    assert branch["branch_id"] == "main"
    assert branch["latest_event"]["step"] == 1
    assert branch["pending"]["variable_count"] == 1
    assert branch["pending"]["action_count"] == 1
    assert branch["pending"]["action_labels"] == ["沈夜:转移证人去城外"]
    assert branch["key_actor_states"][0]["name"] == "沈夜"
    assert branch["key_organization_states"][0]["name"] == "玄霄宗"
    assert branch["relation_highlights"][0]["source"] == "沈夜"
    assert branch["relation_highlights"][0]["target"] == "玄霄宗"


def test_branch_comparison_api_is_retired_for_single_world_mode(tmp_path):
    project, session_id, _ = _create_session(tmp_path)
    app = create_app()
    client = app.test_client()

    response = client.get(
        f"/api/worldline/session/{session_id}/comparison",
        query_string={"project_id": project.project_id},
    )

    assert response.status_code == 410, response.get_json()
    assert "单世界世界线已不再支持分支对比接口" in response.get_json()["error"]
