from app import create_app
from app.config import Config
from app.models.project import ProjectManager
from app.services.agents.memory import LongTermMemoryStore


def _configure_storage(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    ProjectManager.PROJECTS_DIR = str(upload_root / "projects")


def _create_project_with_archive(name: str = "V2 档案项目"):
    project = ProjectManager.create_project(name)
    ProjectManager.save_project_json(
        project.project_id,
        "narrative_archives.json",
        {
            "project_id": project.project_id,
            "project_name": project.name,
            "graph_id": project.graph_id,
            "count": 1,
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
                    "core_drive": "查清真相",
                    "surface_mask": "冷静",
                    "hidden_tension": "担心失控",
                    "relationship_summary": "与秦昭暂时联手",
                    "agent_behavior_hint": "先查证再出手",
                    "human_ai_relation_tag": "human",
                    "notable_risks": ["冲动公开"],
                    "can_act_as_agent": True,
                }
            ],
        },
    )
    return project


def test_v2_archive_routes_list_detail_and_reindex_match_legacy_contract(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()
    project = _create_project_with_archive()

    list_response = client.get(
        "/api/v2/archives",
        query_string={"project_id": project.project_id, "entity_type": "character"},
    )
    assert list_response.status_code == 200, list_response.get_json()
    payload = list_response.get_json()["data"]
    assert payload["total"] == 1
    assert payload["items"][0]["entity_name"] == "沈夜"
    archive_id = payload["items"][0]["archive_id"]

    detail_response = client.get(f"/api/v2/archives/{archive_id}")
    assert detail_response.status_code == 200, detail_response.get_json()
    detail = detail_response.get_json()["data"]
    assert detail["archive_id"] == archive_id
    assert detail["template_key"] == "character.protagonist.v1"

    reindex_response = client.post("/api/v2/archive-maintenance/reindex")
    assert reindex_response.status_code == 200, reindex_response.get_json()
    assert reindex_response.get_json()["data"]["count"] == 1


def test_v2_archive_memory_routes_list_timeline_adopt_and_reject(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()
    project = _create_project_with_archive("V2 记忆项目")

    library_response = client.get(
        "/api/v2/archives",
        query_string={"project_id": project.project_id},
    )
    assert library_response.status_code == 200, library_response.get_json()
    archive_id = library_response.get_json()["data"]["items"][0]["archive_id"]

    store = LongTermMemoryStore()
    candidate_id = store.append_candidate(
        archive_id=archive_id,
        agent_id=archive_id,
        memory_type="strategy",
        summary="沈夜决定先公开一页密信试探众人反应。",
        detail={"intent": "试探各方底牌"},
        source_kind="action_applied",
        source_ref_id="action_1",
        normalized_subject="公开密信",
        salience=0.9,
        source_session_id="session_demo",
        source_branch_id="main",
        evidence=[{"snippet": "先公开一页密信"}],
    )
    rejected_id = store.append_candidate(
        archive_id=archive_id,
        agent_id=archive_id,
        memory_type="strategy",
        summary="沈夜决定继续隐瞒密信来源。",
        detail={"intent": "避免立即失控"},
        source_kind="action_applied",
        source_ref_id="action_2",
        normalized_subject="隐瞒密信来源",
        salience=0.7,
        source_session_id="session_demo",
        source_branch_id="main",
        evidence=[{"snippet": "继续隐瞒密信来源"}],
    )

    list_response = client.get(f"/api/v2/archives/{archive_id}/memories")
    assert list_response.status_code == 200, list_response.get_json()
    memory_payload = list_response.get_json()["data"]
    assert memory_payload["candidate_count"] == 2
    assert {item["memory_id"] for item in memory_payload["items"]} == {
        candidate_id,
        rejected_id,
    }

    adopt_response = client.post(
        f"/api/v2/archives/{archive_id}/memory-adoptions",
        json={"memory_id": candidate_id},
    )
    assert adopt_response.status_code == 200, adopt_response.get_json()
    adopted_memory = adopt_response.get_json()["data"]["memory"]
    assert adopted_memory["memory_layer"] == "canon"
    canon_id = adopted_memory["memory_id"]

    reject_response = client.post(
        f"/api/v2/archives/{archive_id}/memory-rejections",
        json={"memory_id": rejected_id},
    )
    assert reject_response.status_code == 200, reject_response.get_json()
    assert reject_response.get_json()["data"]["memory"]["status"] == "rejected"

    canon_response = client.get(
        f"/api/v2/archives/{archive_id}/memories",
        query_string={"layer": "canon", "status": "active"},
    )
    assert canon_response.status_code == 200, canon_response.get_json()
    assert canon_response.get_json()["data"]["items"][0]["memory_id"] == canon_id

    timeline_response = client.get(
        f"/api/v2/archives/{archive_id}/memory-events",
        query_string={"normalized_subject": "公开密信"},
    )
    assert timeline_response.status_code == 200, timeline_response.get_json()
    timeline = timeline_response.get_json()["data"]
    assert timeline["subject"] == "公开密信"
    assert timeline["active_canon"]["memory_id"] == canon_id
    assert timeline["events"]
