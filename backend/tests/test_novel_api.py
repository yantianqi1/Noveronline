"""Integration tests for /api/novel routes (extends existing coverage)."""

from __future__ import annotations

import os


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


def test_seed_analysis_get_404(tmp_path, monkeypatch):
    client, _ = _setup(tmp_path, monkeypatch)
    resp = client.get("/api/novel/seed-analysis/proj_nonexistent")
    assert resp.status_code == 404


def test_reviewer_rules_roundtrip(tmp_path, monkeypatch):
    client, project = _create_project_with_seed(tmp_path, monkeypatch)
    pid = project.project_id

    # Get default
    resp = client.get(f"/api/novel/reviewer-rules?project_id={pid}")
    assert resp.status_code == 200
    assert resp.json()["data"]["is_custom"] is False

    # Save custom
    resp = client.put("/api/novel/reviewer-rules", json={"project_id": pid, "custom_prompt": "自定义审稿规则"})
    assert resp.status_code == 200

    # Verify
    resp = client.get(f"/api/novel/reviewer-rules?project_id={pid}")
    assert resp.json()["data"]["custom_prompt"] == "自定义审稿规则"
    assert resp.json()["data"]["is_custom"] is True


def test_plot_inspiration_requires_creator_prompt(tmp_path, monkeypatch):
    client, project = _create_project_with_seed(tmp_path, monkeypatch)

    resp = client.post(
        "/api/novel/plot/inspiration",
        json={"project_id": project.project_id, "creator_prompt": ""},
    )
    assert resp.status_code == 400
