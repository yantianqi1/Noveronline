from app import create_app
from app.models.project import ProjectManager


def _create_project_with_seed(tmp_path):
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    project = ProjectManager.create_project("世界线 Agent 名册测试")
    project.graph_id = "graph_agent_demo"
    project.analysis_goal = "观察主角与宗门关系在平行世界中的演化"
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
                    "profile_summary": "正在调查宗门隐秘",
                },
                {
                    "name": "秦昭",
                    "importance_tier": "major",
                    "identity_hint": "游走于多方势力之间",
                    "profile_summary": "与主角互相试探",
                },
                {
                    "name": "苏半夏",
                    "importance_tier": "supporting",
                    "identity_hint": "医者与见证人",
                    "profile_summary": "负责稳住局势并保留关键证据",
                },
            ],
            "organizations": [
                {
                    "name": "玄霄宗",
                    "importance_tier": "major",
                    "organization_type": "sect",
                    "summary": "掌控试炼与秩序",
                }
            ],
            "relations": [
                {
                    "source": "沈夜",
                    "target": "秦昭",
                    "relation_type": "ally",
                },
                {
                    "source": "秦昭",
                    "target": "苏半夏",
                    "relation_type": "ally",
                },
                {
                    "source": "沈夜",
                    "target": "玄霄宗",
                    "relation_type": "tension",
                },
                {
                    "source": "秦昭",
                    "target": "玄霄宗",
                    "relation_type": "tension",
                }
            ],
        },
    )
    return project


def _create_session(client, project_id: str) -> str:
    response = client.post(
        "/api/worldline/session/create",
        json={"project_id": project_id, "branch_count": 1, "variables": ["密信提前泄露"]},
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]["session_id"]


def test_worldline_agent_roster_lists_character_org_and_relation_agents(tmp_path):
    project = _create_project_with_seed(tmp_path)
    app = create_app()
    client = app.test_client()
    session_id = _create_session(client, project.project_id)

    response = client.get(f"/api/worldline/session/{session_id}/agents")

    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert data["counts"]["character"] >= 2
    assert data["counts"]["organization"] >= 1
    assert data["counts"]["relationship"] >= 1
    source_agent = next(item for item in data["agents"] if item["display_name"] == "沈夜")
    target_agent = next(item for item in data["agents"] if item["display_name"] == "玄霄宗")
    relation_agent = next(item for item in data["agents"] if item["display_name"] == "沈夜 × 玄霄宗")
    assert relation_agent["agent_id"] == f"relation::{source_agent['agent_id']}::{target_agent['agent_id']}"
    assert relation_agent["state_version"] == 1


def test_relation_agent_supports_dialogue_and_action(tmp_path):
    project = _create_project_with_seed(tmp_path)
    app = create_app()
    client = app.test_client()
    session_id = _create_session(client, project.project_id)

    roster_resp = client.get(f"/api/worldline/session/{session_id}/agents")
    assert roster_resp.status_code == 200, roster_resp.get_json()
    relation_agent = next(
        item for item in roster_resp.get_json()["data"]["agents"] if item["display_name"] == "沈夜 × 玄霄宗"
    )

    dialogue_resp = client.post(
        f"/api/worldline/session/{session_id}/agent-dialogue",
        json={
            "agent_id": relation_agent["agent_id"],
            "message": "如果你们之间的关系继续恶化，会发生什么？",
        },
    )
    assert dialogue_resp.status_code == 200, dialogue_resp.get_json()
    reply = dialogue_resp.get_json()["data"]["result"]["reply"]
    assert "沈夜 × 玄霄宗" in reply

    action_resp = client.post(
        f"/api/worldline/session/{session_id}/agent-action",
        json={
            "agent_id": relation_agent["agent_id"],
            "action": "公开撕裂双方信任",
        },
    )
    assert action_resp.status_code == 200, action_resp.get_json()

    step_resp = client.post(f"/api/worldline/session/{session_id}/step", json={"steps": 1})
    assert step_resp.status_code == 200, step_resp.get_json()

    session_resp = client.get(f"/api/worldline/session/{session_id}")
    assert session_resp.status_code == 200, session_resp.get_json()
    branch = session_resp.get_json()["data"]["branches"][0]
    relation = next(
        item for item in branch["relationship_states"]
        if item["source"] == "沈夜" and item["target"] == "玄霄宗"
    )
    assert relation["last_action"] == "公开撕裂双方信任"
    assert relation["status"] == "engaged"


def test_step_endpoint_accepts_evolution_intensity_and_custom_depth(tmp_path):
    project = _create_project_with_seed(tmp_path)
    app = create_app()
    client = app.test_client()
    session_id = _create_session(client, project.project_id)

    action_resp = client.post(
        f"/api/worldline/session/{session_id}/agent-action",
        json={"agent_id": "沈夜", "action": "提前公开密信"},
    )
    assert action_resp.status_code == 200, action_resp.get_json()

    step_resp = client.post(
        f"/api/worldline/session/{session_id}/step",
        json={"steps": 1, "evolution_intensity": "low", "custom_depth": 1},
    )
    assert step_resp.status_code == 200, step_resp.get_json()
    summary = step_resp.get_json()["data"]["branch_summaries"][0]
    assert summary["evolution_intensity"] == "low"
    assert summary["evolution_depth"] == 1

    session_resp = client.get(f"/api/worldline/session/{session_id}")
    assert session_resp.status_code == 200, session_resp.get_json()
    branch = session_resp.get_json()["data"]["branches"][0]
    assert branch["evolution_intensity"] == "low"
    assert branch["evolution_depth"] == 1
    assert branch["actor_states"]["秦昭"]["status"] == "engaged"
    assert branch["actor_states"]["苏半夏"]["last_event"] == "seed"
