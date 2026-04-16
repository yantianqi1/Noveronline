"""Integration tests for /api/writer-agent CRUD routes.

Covers: chapters, scenes, presets, manuscript, outline versions.
Skips: /run and /world-update (SSE streaming, requires full orchestrator).
"""

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


def _client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.config import Config
    from app.main import create_app
    from app.models.project import ProjectManager

    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    ProjectManager.PROJECTS_DIR = str(tmp_path / "uploads" / "projects")
    os.makedirs(ProjectManager.PROJECTS_DIR, exist_ok=True)

    app = create_app(settings=_settings(tmp_path))
    return TestClient(app)


def _create_project(monkeypatch, tmp_path):
    from app.config import Config
    from app.models.project import ProjectManager

    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    ProjectManager.PROJECTS_DIR = str(tmp_path / "uploads" / "projects")
    os.makedirs(ProjectManager.PROJECTS_DIR, exist_ok=True)

    project = ProjectManager.create_project("Writer Test")
    ProjectManager.save_project(project)
    return project


# ── Chapters ────────────────────────────────────────────────────────


def test_chapter_crud_lifecycle(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    project = _create_project(monkeypatch, tmp_path)
    pid = project.project_id

    # Create
    resp = client.post(f"/api/writer-agent/chapters/{pid}", json={"title": "第一章"})
    assert resp.status_code == 200, resp.json()
    chapter = resp.json()["data"]
    chapter_id = chapter["chapter_id"]
    assert chapter["title"] == "第一章"

    # List
    resp = client.get(f"/api/writer-agent/chapters/{pid}")
    assert resp.status_code == 200
    chapters = resp.json()["data"]
    assert any(c["chapter_id"] == chapter_id for c in chapters)

    # Update
    resp = client.put(
        f"/api/writer-agent/chapters/detail/{chapter_id}",
        json={"project_id": pid, "title": "序章", "summary": "故事开端"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["updated"] is True

    # Delete
    resp = client.delete(f"/api/writer-agent/chapters/detail/{chapter_id}?project_id={pid}")
    assert resp.status_code == 200


# ── Presets ──────────────────────────────────────────────────────────


def test_preset_crud_lifecycle(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    project = _create_project(monkeypatch, tmp_path)
    pid = project.project_id

    # Create
    resp = client.post(
        "/api/writer-agent/presets",
        json={"project_id": pid, "name": "武侠风", "system_prompt": "你是一个武侠小说作者。", "description": "武侠风格预设"},
    )
    assert resp.status_code == 200, resp.json()
    preset = resp.json()["data"]
    preset_id = preset["preset_id"]
    assert preset["name"] == "武侠风"

    # List
    resp = client.get(f"/api/writer-agent/presets?project_id={pid}")
    assert resp.status_code == 200
    assert any(p["preset_id"] == preset_id for p in resp.json()["data"])

    # Update
    resp = client.put(
        f"/api/writer-agent/presets/{preset_id}",
        json={"project_id": pid, "name": "仙侠风"},
    )
    assert resp.status_code == 200

    # Delete
    resp = client.delete(f"/api/writer-agent/presets/{preset_id}?project_id={pid}")
    assert resp.status_code == 200


# ── Scenes ───────────────────────────────────────────────────────────


def test_scene_crud_lifecycle(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    project = _create_project(monkeypatch, tmp_path)
    pid = project.project_id

    # Create a chapter first
    resp = client.post(f"/api/writer-agent/chapters/{pid}", json={"title": "测试章节"})
    chapter_id = resp.json()["data"]["chapter_id"]

    # List scenes (empty initially)
    resp = client.get(f"/api/writer-agent/scenes/{chapter_id}?project_id={pid}")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


# ── Manuscript ───────────────────────────────────────────────────────


def test_manuscript_commit_and_list(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    project = _create_project(monkeypatch, tmp_path)
    pid = project.project_id

    # Commit a block
    resp = client.post(
        f"/api/writer-agent/manuscript/{pid}/commit",
        json={"content": "沈夜推开了宗门大殿的门。"},
    )
    assert resp.status_code == 200, resp.json()
    block = resp.json()["data"]
    block_id = block["block_id"]
    assert block_id

    # List
    resp = client.get(f"/api/writer-agent/manuscript/{pid}")
    assert resp.status_code == 200
    blocks = resp.json()["data"]
    # list_blocks returns a dict with "blocks" key
    block_list = blocks.get("blocks", blocks) if isinstance(blocks, dict) else blocks
    assert isinstance(block_list, list)
    assert len(block_list) >= 1

    # Update
    resp = client.put(
        f"/api/writer-agent/manuscript/block/{block_id}",
        json={"project_id": pid, "content": "沈夜轻轻推开了大殿的门。"},
    )
    assert resp.status_code == 200

    # Delete
    resp = client.delete(f"/api/writer-agent/manuscript/block/{block_id}?project_id={pid}")
    assert resp.status_code == 200


def test_manuscript_commit_validates_empty_content(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    project = _create_project(monkeypatch, tmp_path)
    resp = client.post(
        f"/api/writer-agent/manuscript/{project.project_id}/commit",
        json={"content": ""},
    )
    assert resp.status_code == 400


def test_manuscript_reorder_tag_move(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    project = _create_project(monkeypatch, tmp_path)
    pid = project.project_id

    # Commit two blocks
    r1 = client.post(f"/api/writer-agent/manuscript/{pid}/commit", json={"content": "段落一"})
    r2 = client.post(f"/api/writer-agent/manuscript/{pid}/commit", json={"content": "段落二"})
    id1 = r1.json()["data"]["block_id"]
    id2 = r2.json()["data"]["block_id"]

    # Reorder
    resp = client.put(f"/api/writer-agent/manuscript/{pid}/reorder", json={"block_ids": [id2, id1]})
    assert resp.status_code == 200

    # Tag
    resp = client.put(f"/api/writer-agent/manuscript/{pid}/tag", json={"block_ids": [id1, id2], "chapter_tag": "第一章"})
    assert resp.status_code == 200
    assert resp.json()["data"]["updated_count"] == 2


def test_manuscript_export(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    project = _create_project(monkeypatch, tmp_path)
    pid = project.project_id

    client.post(f"/api/writer-agent/manuscript/{pid}/commit", json={"content": "正文内容"})

    resp = client.get(f"/api/writer-agent/manuscript/{pid}/export")
    assert resp.status_code == 200
    assert "正文内容" in resp.text


def test_manuscript_continuation_context(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    project = _create_project(monkeypatch, tmp_path)
    pid = project.project_id

    resp = client.get(f"/api/writer-agent/manuscript/{pid}/continuation-context")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


# ── Outline versions ────────────────────────────────────────────────


def test_outline_version_history(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    project = _create_project(monkeypatch, tmp_path)
    pid = project.project_id

    # Create chapter
    resp = client.post(f"/api/writer-agent/chapters/{pid}", json={"title": "大纲测试"})
    chapter_id = resp.json()["data"]["chapter_id"]

    # Update outline to create a version (first update sets initial, second creates snapshot)
    client.put(
        f"/api/writer-agent/chapters/detail/{chapter_id}",
        json={"project_id": pid, "outline_json": '[{"beat": "v1"}]'},
    )
    client.put(
        f"/api/writer-agent/chapters/detail/{chapter_id}",
        json={"project_id": pid, "outline_json": '[{"beat": "v2"}]'},
    )

    # List versions
    resp = client.get(f"/api/writer-agent/chapters/detail/{chapter_id}/outline-versions?project_id={pid}")
    assert resp.status_code == 200
    versions = resp.json()["data"]
    assert isinstance(versions, list)
    assert len(versions) >= 1


# ── Run validation ──────────────────────────────────────────────────


def test_run_validates_project_id(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    # project_id is required in RunWriterAgentRequest schema → 400
    resp = client.post("/api/writer-agent/run", json={"task_type": "write_scene"})
    assert resp.status_code in (400, 422)  # 400 via our validation handler, 422 if handler not reached
    assert resp.json()["success"] is False


# ── Migrate / legacy endpoint deprecation ───────────────────────────


def test_migrate_endpoint_returns_gone_for_legacy_sqlite_backfill(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(settings=_settings(tmp_path))
    client = TestClient(app, raise_server_exceptions=False)
    project = _create_project(monkeypatch, tmp_path)
    resp = client.post(f"/api/writer-agent/migrate/{project.project_id}")
    assert resp.status_code == 410
    payload = resp.json()
    assert payload["success"] is False
    assert "legacy novel.sqlite3" in payload["error"]
