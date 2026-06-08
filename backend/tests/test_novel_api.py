"""Integration tests for /api/novel routes (extends existing coverage)."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path


def _settings(tmp_path, **overrides):
    from app.config import Settings

    values = {
        "DATABASE_URL": f"sqlite:///{tmp_path / 'data' / 'mirofish.db'}",
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        "ADMIN_SECRET": "",
        "DEBUG": True,
    }
    values.update(overrides)
    return Settings(**values)


def _setup(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.config import Config
    from app.main import create_app
    from app.models.project import ProjectManager

    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    ProjectManager.PROJECTS_DIR = str(tmp_path / "uploads" / "projects")
    os.makedirs(ProjectManager.PROJECTS_DIR, exist_ok=True)

    app = create_app(settings=_settings(tmp_path))
    client = TestClient(app)
    return client, ProjectManager


def _create_project_with_seed(tmp_path, monkeypatch):
    client, pm = _setup(tmp_path, monkeypatch)
    project = pm.create_project("Novel Test")
    project.analysis_goal = "分析角色关系"
    pm.save_project(project)
    pm.save_project_json(
        project.project_id,
        "seed_analysis.json",
        {
            "characters": [
                {"name": "沈夜", "importance_tier": "protagonist", "identity_hint": "主角", "profile_summary": "追查宗门真相"},
            ],
            "organizations": [],
            "relations": [],
        },
    )
    return client, project


def test_seed_analysis_get(tmp_path, monkeypatch):
    client, project = _create_project_with_seed(tmp_path, monkeypatch)

    resp = client.get(f"/api/novel/seed-analysis/{project.project_id}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["characters"][0]["name"] == "沈夜"


def test_seed_analysis_get_reads_structured_tables_without_artifact(tmp_path, monkeypatch):
    from app.database import get_engine
    from app.repositories.entity_repo import EntityRepository
    from app.repositories.project_artifact_repo import ProjectArtifactRepository
    from app.repositories.relationship_repo import RelationshipRepository

    client, pm = _setup(tmp_path, monkeypatch)
    project = pm.create_project("DB-only Seed")
    now = datetime.now().isoformat()
    entities = EntityRepository(get_engine())
    entities.upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "core_drive": "查清镜湖真相",
            "profile_json": json.dumps(
                {"identity_hint": "镜湖调查者"},
                ensure_ascii=False,
            ),
            "created_at": now,
            "updated_at": now,
        },
    )
    entities.upsert_entity(
        project.project_id,
        {
            "entity_id": "org_mirror_lake",
            "name": "镜湖盟",
            "entity_type": "organization",
            "importance_tier": "major",
            "summary": "暗中保存镜湖旧案档案的组织。",
            "created_at": now,
            "updated_at": now,
        },
    )
    RelationshipRepository(get_engine()).upsert_relationship(
        project.project_id,
        {
            "relation_id": "rel_shenye_mirror_lake",
            "source_id": "char_shenye",
            "target_id": "org_mirror_lake",
            "relation_type": "investigates",
            "description": "沈夜追查镜湖盟保存的地下档案。",
            "updated_at": now,
        },
    )

    resp = client.get(f"/api/novel/seed-analysis/{project.project_id}")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["characters"] == [
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "importance_tier": "protagonist",
            "identity_hint": "镜湖调查者",
            "profile_summary": "追查镜湖旧案的主角。",
            "core_drive": "查清镜湖真相",
            "current_objective": "",
        }
    ]
    assert data["organizations"] == [
        {
            "entity_id": "org_mirror_lake",
            "name": "镜湖盟",
            "importance_tier": "major",
            "organization_type": "organization",
            "summary": "暗中保存镜湖旧案档案的组织。",
        }
    ]
    assert data["relations"] == [
        {
            "relation_id": "rel_shenye_mirror_lake",
            "source": "沈夜",
            "target": "镜湖盟",
            "source_id": "char_shenye",
            "target_id": "org_mirror_lake",
            "relation_type": "investigates",
            "description": "沈夜追查镜湖盟保存的地下档案。",
            "evidence": ["沈夜追查镜湖盟保存的地下档案。"],
            "evolution_chain": [],
        }
    ]
    assert data["character_count"] == 1
    assert data["organization_count"] == 1
    assert data["relation_count"] == 1
    assert ProjectArtifactRepository(get_engine()).load(project.project_id, "seed_analysis") is None
    assert not (
        Path(pm.PROJECTS_DIR) / project.project_id / "seed_analysis.json"
    ).exists()


def test_seed_analysis_get_prefers_structured_core_and_keeps_artifact_extras(
    tmp_path, monkeypatch
):
    from app.database import get_engine
    from app.repositories.entity_repo import EntityRepository
    from app.repositories.project_artifact_repo import ProjectArtifactRepository

    client, pm = _setup(tmp_path, monkeypatch)
    project = pm.create_project("Merged Seed Read Model")
    now = datetime.now().isoformat()
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "core_drive": "查清镜湖真相",
            "created_at": now,
            "updated_at": now,
        },
    )
    ProjectArtifactRepository(get_engine()).save(
        project.project_id,
        "seed_analysis",
        {
            "characters": [
                {
                    "name": "旧角色",
                    "importance_tier": "minor",
                    "profile_summary": "旧 artifact 中的过时角色。",
                }
            ],
            "organizations": [],
            "relations": [],
            "chapter_beats": [{"title": "密信"}],
        },
    )

    resp = client.get(f"/api/novel/seed-analysis/{project.project_id}")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [item["name"] for item in data["characters"]] == ["沈夜"]
    assert data["characters"][0]["core_drive"] == "查清镜湖真相"
    assert data["chapter_beats"] == [{"title": "密信"}]
    assert data["character_count"] == 1


def test_generate_archives_reads_agent_profiles_from_entities_without_artifact(
    tmp_path, monkeypatch
):
    from app.database import get_engine
    from app.repositories.entity_repo import EntityRepository
    from app.repositories.project_artifact_repo import ProjectArtifactRepository

    client, pm = _setup(tmp_path, monkeypatch)
    project = pm.create_project("DB-only Agent Profiles")
    now = datetime.now().isoformat()
    profile = {
        "basic_info": {"name": "沈夜", "identity": "镜湖调查者"},
        "personality": {
            "core_traits": ["冷静", "谨慎"],
            "values": "守护真相",
            "fears": "害怕线索被提前抹除",
        },
        "capabilities": {"skills": ["追踪线索", "解读旧档案"]},
        "knowledge_boundary": {"believes_wrongly": ["秦昭完全可信"]},
        "motivation": {
            "ultimate_goal": "查清镜湖真相",
            "current_objective": "打开地下档案",
            "internal_conflict": "在信任与怀疑之间摇摆",
        },
    }
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "profile_json": json.dumps(profile, ensure_ascii=False),
            "created_at": now,
            "updated_at": now,
        },
    )

    resp = client.post(
        "/api/novel/archives/generate",
        json={"project_id": project.project_id, "use_llm": False},
    )

    assert resp.status_code == 200
    archives = resp.json()["data"]["archives"]
    shenye = next(item for item in archives if item["entity_name"] == "沈夜")
    assert "agent_profile" in shenye["template_sections"]
    assert shenye["core_drive"] == "在信任与怀疑之间摇摆"
    assert (
        shenye["template_payload"]["agent_profile"]["motivation"]["current_objective"]
        == "打开地下档案"
    )
    assert shenye["template_payload"]["behavior"]["skills"] == ["追踪线索", "解读旧档案"]
    assert ProjectArtifactRepository(get_engine()).load(project.project_id, "agent_profiles") is None
    assert not (
        Path(pm.PROJECTS_DIR) / project.project_id / "agent_profiles.json"
    ).exists()


def test_agent_profiles_read_model_uses_structured_profiles_without_artifact_fallback(
    tmp_path, monkeypatch
):
    from app.database import get_engine
    from app.repositories.entity_repo import EntityRepository
    from app.repositories.project_artifact_repo import ProjectArtifactRepository
    from app.repositories.project_artifact_repo import ProjectArtifactRepository as ArtifactRepo
    from app.services.seed_analysis_read_model import load_agent_profiles_for_project

    _client, pm = _setup(tmp_path, monkeypatch)
    project = pm.create_project("Merged Agent Profiles")
    now = datetime.now().isoformat()
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "profile_json": json.dumps(
                {
                    "basic_info": {"name": "沈夜", "identity": "镜湖调查者"},
                    "motivation": {"current_objective": "打开地下档案"},
                },
                ensure_ascii=False,
            ),
            "created_at": now,
            "updated_at": now,
        },
    )
    ProjectArtifactRepository(get_engine()).save(
        project.project_id,
        "agent_profiles",
        {
            "profiles": {
                "沈夜": {
                    "basic_info": {"name": "沈夜", "identity": "旧档案"},
                    "motivation": {"current_objective": "沿用旧线索"},
                },
                "秦昭": {
                    "basic_info": {"name": "秦昭", "identity": "旧盟友"},
                    "motivation": {"current_objective": "隐藏证据"},
                },
            }
        },
    )

    def fail_on_artifact_read(self, project_id: str, artifact_key: str):
        if artifact_key == "agent_profiles":
            raise AssertionError("agent profile read model must not read project_artifacts")
        return None

    monkeypatch.setattr(ArtifactRepo, "load", fail_on_artifact_read)
    profiles = load_agent_profiles_for_project(project.project_id)

    assert profiles["沈夜"]["basic_info"]["identity"] == "镜湖调查者"
    assert profiles["沈夜"]["motivation"]["current_objective"] == "打开地下档案"
    assert "秦昭" not in profiles


def test_seed_analysis_get_404(tmp_path, monkeypatch):
    client, _ = _setup(tmp_path, monkeypatch)
    resp = client.get("/api/novel/seed-analysis/proj_nonexistent")
    assert resp.status_code == 404


def test_seed_analysis_post_persists_generated_seed_to_structured_tables(
    tmp_path, monkeypatch
):
    from app.database import get_engine
    from app.repositories.entity_repo import EntityRepository
    from app.repositories.relationship_repo import RelationshipRepository
    from app.services import novel_seed_analyzer

    client, pm = _setup(tmp_path, monkeypatch)
    project = pm.create_project("Manual Seed")
    pm.save_extracted_text(project.project_id, "沈夜追查镜湖盟保存的地下档案。")

    class FakeSeedAnalyzer:
        def analyze_text(self, *, text: str, analysis_goal: str, project_name: str):
            assert "镜湖盟" in text
            return {
                "characters": [
                    {
                        "name": "沈夜",
                        "importance_tier": "protagonist",
                        "identity_hint": "镜湖调查者",
                        "profile_summary": "追查镜湖旧案的主角。",
                        "core_drive": "查清镜湖真相",
                    }
                ],
                "organizations": [
                    {
                        "name": "镜湖盟",
                        "importance_tier": "major",
                        "organization_type": "organization",
                        "summary": "暗中保存镜湖旧案档案的组织。",
                    }
                ],
                "relations": [
                    {
                        "source": "沈夜",
                        "target": "镜湖盟",
                        "relation_type": "investigates",
                        "evidence": ["沈夜追查镜湖盟保存的地下档案。"],
                    }
                ],
            }

    monkeypatch.setattr(novel_seed_analyzer, "NovelSeedAnalyzer", FakeSeedAnalyzer)

    resp = client.post(
        "/api/novel/seed-analysis",
        json={"project_id": project.project_id, "analysis_goal": "追踪镜湖旧案"},
    )

    assert resp.status_code == 200
    entities = EntityRepository(get_engine())
    shenye = entities.get_entity_by_name(project.project_id, "沈夜")
    mirror_lake = entities.get_entity_by_name(project.project_id, "镜湖盟")
    assert shenye["entity_type"] == "character"
    assert shenye["core_drive"] == "查清镜湖真相"
    assert mirror_lake["entity_type"] == "organization"

    relations = RelationshipRepository(get_engine()).list_relationships(
        project.project_id,
    )
    assert len(relations) == 1
    assert relations[0]["source_id"] == shenye["entity_id"]
    assert relations[0]["target_id"] == mirror_lake["entity_id"]
    assert relations[0]["relation_type"] == "investigates"


def test_reviewer_rules_roundtrip(tmp_path, monkeypatch):
    from app.database import get_engine
    from app.repositories.meta_repo import MetaRepository
    from app.repositories.project_artifact_repo import ProjectArtifactRepository

    client, project = _create_project_with_seed(tmp_path, monkeypatch)
    pid = project.project_id

    # Get default
    resp = client.get(f"/api/novel/reviewer-rules?project_id={pid}")
    assert resp.status_code == 200
    assert resp.json()["data"]["is_custom"] is False

    # Save custom
    resp = client.put("/api/novel/reviewer-rules", json={"project_id": pid, "custom_prompt": "自定义审稿规则"})
    assert resp.status_code == 200
    assert ProjectArtifactRepository(get_engine()).load(pid, "reviewer_rules") is None
    project_payload = MetaRepository(get_engine()).load_project_payload(pid)
    assert project_payload["settings"]["reviewer_rules"]["custom_prompt"] == "自定义审稿规则"

    # Verify
    resp = client.get(f"/api/novel/reviewer-rules?project_id={pid}")
    assert resp.json()["data"]["custom_prompt"] == "自定义审稿规则"
    assert resp.json()["data"]["is_custom"] is True


def test_reviewer_rules_get_does_not_read_artifact_fallback(tmp_path, monkeypatch):
    from app.database import get_engine
    from app.repositories.project_artifact_repo import ProjectArtifactRepository

    client, project = _create_project_with_seed(tmp_path, monkeypatch)
    pid = project.project_id
    ProjectArtifactRepository(get_engine()).save(
        pid,
        "reviewer_rules",
        {"custom_prompt": "旧 artifact 审稿规则"},
    )

    resp = client.get(f"/api/novel/reviewer-rules?project_id={pid}")

    assert resp.status_code == 200
    assert resp.json()["data"]["custom_prompt"] == ""
    assert resp.json()["data"]["is_custom"] is False


def test_parallel_world_config_persists_to_project_settings_without_artifact(
    tmp_path, monkeypatch
):
    from app.database import get_engine
    from app.repositories.meta_repo import MetaRepository
    from app.repositories.project_artifact_repo import ProjectArtifactRepository

    client, project = _create_project_with_seed(tmp_path, monkeypatch)
    pid = project.project_id

    resp = client.post(
        "/api/novel/parallel-world/config",
        json={
            "project_id": pid,
            "variables": ["密信提前泄露"],
            "branch_count": 1,
            "use_llm": False,
        },
    )

    assert resp.status_code == 200
    config = resp.json()["data"]["config"]
    assert config["world_variables"][0]["name"] == "密信提前泄露"
    assert ProjectArtifactRepository(get_engine()).load(
        pid, "parallel_world_config"
    ) is None
    project_payload = MetaRepository(get_engine()).load_project_payload(pid)
    assert project_payload["settings"]["parallel_world_config"] == config


def test_plot_inspiration_requires_creator_prompt(tmp_path, monkeypatch):
    client, project = _create_project_with_seed(tmp_path, monkeypatch)

    resp = client.post(
        "/api/novel/plot/inspiration",
        json={"project_id": project.project_id, "creator_prompt": ""},
    )
    assert resp.status_code == 400
