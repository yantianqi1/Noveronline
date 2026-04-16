"""Integration tests for /api/project routes (extends existing coverage)."""

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


def test_project_list(tmp_path, monkeypatch):
    client, pm = _setup(tmp_path, monkeypatch)

    p1 = pm.create_project("Project A")
    pm.save_project(p1)
    p2 = pm.create_project("Project B")
    pm.save_project(p2)

    resp = client.get("/api/project/list")
    assert resp.status_code == 200
    data = resp.json()["data"]
    names = {item["name"] for item in data}
    assert "Project A" in names
    assert "Project B" in names


def test_project_get_and_404(tmp_path, monkeypatch):
    client, pm = _setup(tmp_path, monkeypatch)

    project = pm.create_project("Get Test")
    pm.save_project(project)

    # Get existing
    resp = client.get(f"/api/project/{project.project_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "Get Test"

    # Get nonexistent
    resp = client.get("/api/project/proj_nonexistent")
    assert resp.status_code == 404


def test_project_graph_404_when_no_graph(tmp_path, monkeypatch):
    client, pm = _setup(tmp_path, monkeypatch)

    project = pm.create_project("No Graph")
    pm.save_project(project)

    resp = client.get(f"/api/project/{project.project_id}/graph")
    assert resp.status_code == 404


def test_build_graph_validates_project_id(tmp_path, monkeypatch):
    client, _ = _setup(tmp_path, monkeypatch)

    resp = client.post("/api/project/build-graph", json={"graph_name": "test"})
    # project_id is required in BuildGraphRequest → 400
    assert resp.status_code == 400
