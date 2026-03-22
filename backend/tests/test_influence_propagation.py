from app.models.worldline import AgentAction, WorldlineBranch, WorldlineSession
from app.services.influence_propagation import InfluencePropagationModel
from app.services.worldline_branch_service import WorldlineBranchService


def _build_states():
    actor_states = {
        "沈夜": {"importance_tier": "protagonist", "status": "active", "drive": "查真相", "tension": "暴露风险", "role": "主角", "last_event": "seed"},
        "秦昭": {"importance_tier": "major", "status": "active", "drive": "寻找平衡", "tension": "多方拉扯", "role": "盟友", "last_event": "seed"},
        "苏半夏": {"importance_tier": "supporting", "status": "active", "drive": "保护同伴", "tension": "线索不足", "role": "医者", "last_event": "seed"},
        "路人甲": {"importance_tier": "minor", "status": "active", "drive": "自保", "tension": "卷入冲突", "role": "旁观者", "last_event": "seed"},
    }
    organization_states = {
        "玄霄宗": {"importance_tier": "major", "status": "active", "drive": "维持秩序", "tension": "内部失控", "role": "宗门", "last_event": "seed"},
    }
    relationship_states = [
        {"source": "沈夜", "target": "秦昭", "change": "ally"},
        {"source": "秦昭", "target": "苏半夏", "change": "ally"},
        {"source": "苏半夏", "target": "路人甲", "change": "co_occurrence"},
        {"source": "秦昭", "target": "玄霄宗", "change": "tension"},
    ]
    return actor_states, organization_states, relationship_states


def test_influence_propagation_respects_decay_and_depth():
    model = InfluencePropagationModel()
    actor_states, organization_states, relationship_states = _build_states()

    affected = model.propagate(
        actor_name="沈夜",
        action_weight=1.0,
        actor_states=actor_states,
        organization_states=organization_states,
        relationship_states=relationship_states,
        max_depth=2,
    )

    affected_map = {item["entity"]: item for item in affected}

    assert affected[0]["entity"] == "沈夜"
    assert affected_map["沈夜"]["influence"] == 1.0
    assert affected_map["秦昭"]["influence"] == 0.35
    assert affected_map["苏半夏"]["influence"] == 0.1
    assert affected_map["玄霄宗"]["influence"] == 0.175
    assert "路人甲" not in affected_map


def test_worldline_branch_service_applies_propagation_by_intensity():
    actor_states, organization_states, relationship_states = _build_states()
    branch = WorldlineBranch(
        branch_id="branch_1",
        title="测试分支",
        core_change="沈夜提前出手",
        actor_states={name: dict(state) for name, state in actor_states.items()},
        organization_states={name: dict(state) for name, state in organization_states.items()},
        relationship_states=[dict(item) for item in relationship_states],
        pending_actions=[
            AgentAction(action_id="act_1", agent_id="character::沈夜", actor="沈夜", action="公开密信", intent="逼对手表态")
        ],
    )
    session = WorldlineSession(
        session_id="ws_test",
        project_id="proj_test",
        graph_id="graph_test",
        simulation_goal="测试影响传播",
        focus_question="沈夜公开密信会波及谁",
        branch_count=1,
        branches=[branch],
    )
    service = WorldlineBranchService(influence_model=InfluencePropagationModel())

    service.advance_branch(branch, session, evolution_intensity="low")

    assert branch.evolution_intensity == "low"
    assert branch.evolution_depth == 1
    assert branch.actor_states["沈夜"]["last_action"] == "公开密信"
    assert branch.actor_states["秦昭"]["status"] == "engaged"
    assert branch.actor_states["苏半夏"]["last_event"] == "seed"
