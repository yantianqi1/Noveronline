from app.models.project import ProjectManager
from app.models.worldline import WorldlineSession, WorldlineBranch
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


def _make_project(tmp_path):
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    project = ProjectManager.create_project("测试小说项目")
    project.graph_id = "graph_demo"
    project.analysis_goal = "观察主角与宗门关系在变量注入后的变化"
    ProjectManager.save_project(project)
    return project


def _seed_session(store: WorldStateStore, tmp_path):
    project = _make_project(tmp_path)
    container_dir = ProjectManager._get_project_dir(project.project_id)

    session = WorldlineSession(
        session_id="wl_session_seed",
        project_id=project.project_id,
        graph_id="graph_demo",
        simulation_goal="观察主角与宗门关系在变量注入后的变化",
        focus_question="如果主角提前得知宗门阴谋，会如何演变",
        branch_count=1,
        branches=[
            WorldlineBranch(
                branch_id="branch_1",
                title="提前觉察线",
                core_change="主角在第一幕提前察觉宗门阴谋",
                key_agents=["主角", "宗门长老"],
                actor_states={
                    "沈夜": {
                        "status": "active",
                        "drive": "查清真相",
                        "role": "主角",
                    }
                },
            )
        ],
    )
    store.save_session(str(container_dir), session)
    return project, container_dir, session.session_id


def test_create_session_builds_branch_state_from_story_seed(tmp_path):
    project = _make_project(tmp_path)
    store = WorldStateStore()
    engine = _make_engine(store)

    archives = [
        {
            "entity_uuid": "char_1",
            "entity_name": "沈夜",
            "entity_type": "Character",
            "importance_tier": "protagonist",
            "entity_role": "主角",
            "core_drive": "查清真相",
            "relationship_summary": "与宗门长老互相试探",
            "agent_behavior_hint": "在压力下会主动调查",
        },
        {
            "entity_uuid": "org_1",
            "entity_name": "玄霄宗",
            "entity_type": "Organization",
            "importance_tier": "major",
            "entity_role": "核心势力",
            "core_drive": "维持内部秩序",
            "relationship_summary": "掌控主角命运",
            "agent_behavior_hint": "优先压制异常信息",
        },
    ]

    session, _ = engine.create_session(
        graph_id="graph_demo",
        project_id=project.project_id,
        focus_question="如果主角提前知道宗门布局",
        archives=archives,
        branch_count=1,
        variables=["密信泄露"],
        config={
            "simulation_goal": "观察提前知情如何改变势力博弈",
            "timeline_focus": ["入门试炼", "长老议会"],
            "agent_behavior_axes": ["求生", "权力博弈"],
            "world_variables": [
                {"name": "密信泄露", "description": "主角提前拿到密信", "impact_axis": "信息差"}
            ],
            "branch_hypotheses": [
                {
                    "branch_id": "branch_1",
                    "title": "密信泄露线",
                    "core_change": "主角提前掌握阴谋线索",
                    "key_agents": ["沈夜", "玄霄宗"],
                    "expected_conflicts": ["试炼提前失控"],
                    "narrative_value": "更适合推演智斗剧情",
                }
            ],
        },
    )

    assert session.project_id == project.project_id
    assert session.graph_id == "graph_demo"
    assert session.branch_count == 1
    assert session.branches[0].actor_states["沈夜"]["drive"] == "查清真相"
    assert session.branches[0].organization_states["玄霄宗"]["role"] == "核心势力"
    assert session.world_variables[0].name == "密信泄露"


def test_step_branch_consumes_pending_changes_and_appends_timeline_event(tmp_path):
    store = WorldStateStore()
    engine = _make_engine(store)
    project, _, session_id = _seed_session(store, tmp_path)

    engine.inject_variable(
        session_id=session_id,
        project_id=project.project_id,
        branch_id="branch_1",
        name="长老受伤",
        description="权力真空提前出现",
        impact_axis="权力结构",
    )
    engine.inject_action(
        session_id=session_id,
        project_id=project.project_id,
        branch_id="branch_1",
        actor="沈夜",
        action="秘密接触外门弟子",
        intent="寻找证人",
    )

    updated = engine.step(
        session_id=session_id,
        project_id=project.project_id,
        branch_id="branch_1",
    )

    branch = updated.branches[0]
    assert branch.current_step == 1
    assert len(branch.timeline) == 1
    assert branch.timeline[-1].event_type == "evolution"
    assert branch.pending_variables == []
    assert branch.pending_actions == []
    assert branch.actor_states["沈夜"]["last_action"] == "秘密接触外门弟子"


def test_list_sessions_reads_saved_index(tmp_path):
    project = _make_project(tmp_path)
    store = WorldStateStore()
    engine = _make_engine(store)

    session, _ = engine.create_session(
        graph_id="graph_demo",
        project_id=project.project_id,
        focus_question="公开调查会引发什么后果",
        branch_count=1,
        archives=[
            {
                "entity_uuid": "char_1",
                "entity_name": "林雾",
                "entity_type": "Character",
                "importance_tier": "major",
                "entity_role": "调查者",
                "core_drive": "追查失踪案",
                "relationship_summary": "与公司高层关系紧张",
                "agent_behavior_hint": "先调查再对抗",
            }
        ],
        config={
            "simulation_goal": "观察失踪案的多世界线后果",
            "timeline_focus": ["调查开始"],
            "agent_behavior_axes": ["信任", "信息控制"],
            "world_variables": [],
            "branch_hypotheses": [
                {
                    "branch_id": "branch_1",
                    "title": "公开调查线",
                    "core_change": "主角公开调查公司",
                    "key_agents": ["林雾"],
                    "expected_conflicts": ["高层反制"],
                    "narrative_value": "适合推进悬疑线",
                }
            ],
        },
    )

    sessions = engine.list_sessions(project_id=project.project_id)

    assert session.session_id in [item["session_id"] for item in sessions]
