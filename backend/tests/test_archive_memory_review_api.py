from app import create_app
from app.config import Config
from app.models.project import ProjectManager
from app.services.agent_memory_stores import LongTermMemoryStore


def _configure_storage(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    ProjectManager.PROJECTS_DIR = str(upload_root / "projects")


def _create_project_with_archive():
    project = ProjectManager.create_project("记忆审核项目")
    ProjectManager.save_project_json(
        project.project_id,
        "narrative_archives.json",
        {
            "project_id": project.project_id,
            "project_name": project.name,
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


def test_archive_memory_review_api_lists_adopts_and_rejects_candidates(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    project = _create_project_with_archive()
    app = create_app()
    client = app.test_client()

    library_response = client.get(f"/api/archive/library?project_id={project.project_id}")
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

    list_response = client.get(f"/api/archive/library/{archive_id}/memory")
    assert list_response.status_code == 200, list_response.get_json()
    payload = list_response.get_json()["data"]
    assert payload["items"]
    assert payload["canon_count"] == 0
    assert payload["candidate_count"] == 1
    assert payload["items"][0]["memory_layer"] == "candidate"

    adopt_response = client.post(f"/api/archive/library/{archive_id}/memory/{candidate_id}/adopt")
    assert adopt_response.status_code == 200, adopt_response.get_json()
    adopted = adopt_response.get_json()["data"]["memory"]
    assert adopted["memory_layer"] == "canon"
    assert adopted["status"] == "active"

    repeated_adopt_response = client.post(f"/api/archive/library/{archive_id}/memory/{candidate_id}/adopt")
    assert repeated_adopt_response.status_code == 400, repeated_adopt_response.get_json()
    assert "已被采纳" in repeated_adopt_response.get_json()["error"]

    second_candidate_id = store.append_candidate(
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
    reject_response = client.post(f"/api/archive/library/{archive_id}/memory/{second_candidate_id}/reject")
    assert reject_response.status_code == 200, reject_response.get_json()
    rejected = reject_response.get_json()["data"]["memory"]
    assert rejected["status"] == "rejected"

    adopt_rejected_response = client.post(f"/api/archive/library/{archive_id}/memory/{second_candidate_id}/adopt")
    assert adopt_rejected_response.status_code == 400, adopt_rejected_response.get_json()
    assert "已被驳回" in adopt_rejected_response.get_json()["error"]

    replacement_candidate_id = store.append_candidate(
        archive_id=archive_id,
        agent_id=archive_id,
        memory_type="strategy",
        summary="沈夜决定改为在众目睽睽下公开密信残页。",
        detail={"intent": "把冲突推到台面"},
        source_kind="action_applied",
        source_ref_id="action_3",
        normalized_subject="公开密信",
        salience=0.95,
        source_session_id="session_demo",
        source_branch_id="main",
        evidence=[{"snippet": "在众目睽睽下公开密信残页"}],
    )
    replacement_adopt_response = client.post(f"/api/archive/library/{archive_id}/memory/{replacement_candidate_id}/adopt")
    assert replacement_adopt_response.status_code == 200, replacement_adopt_response.get_json()

    canon_list_response = client.get(
        f"/api/archive/library/{archive_id}/memory",
        query_string={"layer": "canon", "status": "active"},
    )
    assert canon_list_response.status_code == 200, canon_list_response.get_json()
    canon_payload = canon_list_response.get_json()["data"]
    canon_items = [item for item in canon_payload["items"] if item["normalized_subject"] == "公开密信"]
    assert len(canon_items) == 1
    assert canon_payload["items"][0]["memory_layer"] == "canon"

    timeline_response = client.get(
        f"/api/archive/library/{archive_id}/memory/timeline",
        query_string={"normalized_subject": "公开密信"},
    )
    assert timeline_response.status_code == 200, timeline_response.get_json()
    timeline = timeline_response.get_json()["data"]
    assert timeline["subject"] == "公开密信"
    assert timeline["active_canon"]["memory_layer"] == "canon"
    assert timeline["active_candidates"] == []
    assert timeline["events"]
