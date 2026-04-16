"""Integration tests for /api/assets routes."""

from __future__ import annotations


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


def _client(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app(settings=_settings(tmp_path)))


# ── CRUD lifecycle ──────────────────────────────────────────────────


def test_assets_crud_lifecycle(tmp_path):
    client = _client(tmp_path)

    # Create
    resp = client.post(
        "/api/assets",
        json={"asset_type": "style", "title": "Test Style", "summary": "A test."},
    )
    assert resp.status_code == 200, resp.json()
    asset = resp.json()["data"]
    asset_id = asset["asset_id"]
    assert asset["title"] == "Test Style"
    assert asset["scope"] == "global"

    # Get
    resp = client.get(f"/api/assets/{asset_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["asset_id"] == asset_id

    # List
    resp = client.get("/api/assets")
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert any(item["asset_id"] == asset_id for item in items)

    # Update
    resp = client.put(
        f"/api/assets/{asset_id}",
        json={"title": "Updated Style"},
    )
    assert resp.status_code == 200

    # Verify update
    resp = client.get(f"/api/assets/{asset_id}")
    assert resp.json()["data"]["title"] == "Updated Style"

    # Delete
    resp = client.delete(f"/api/assets/{asset_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["deleted"] is True

    # Verify deleted
    resp = client.get(f"/api/assets/{asset_id}")
    assert resp.status_code == 404


# ── Search ──────────────────────────────────────────────────────────


def test_assets_search_validates_empty_query(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/api/assets/search", json={"query": ""})
    assert resp.status_code == 400


def test_assets_search_returns_results(tmp_path):
    client = _client(tmp_path)
    client.post("/api/assets", json={"asset_type": "style", "title": "独特武器系统"})
    resp = client.post("/api/assets/search", json={"query": "武器"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True


# ── Batch operations ────────────────────────────────────────────────


def test_assets_batch_toggle_and_categorize(tmp_path):
    client = _client(tmp_path)

    ids = []
    for i in range(3):
        resp = client.post("/api/assets", json={"asset_type": "reference", "title": f"Ref {i}"})
        ids.append(resp.json()["data"]["asset_id"])

    # Batch toggle disabled
    resp = client.post(
        "/api/assets/batch-toggle",
        json={"asset_ids": ids, "enabled": False},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["updated"] == 3

    # Batch categorize
    resp = client.post(
        "/api/assets/batch-categorize",
        json={"asset_ids": ids[:2], "category": "weapons"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["updated"] == 2


# ── Scope validation ───────────────────────────────────────────────


def test_assets_invalid_scope_returns_error(tmp_path):
    client = _client(tmp_path)
    resp = client.post(
        "/api/assets",
        json={"asset_type": "style", "title": "bad", "scope": "invalid_scope"},
    )
    assert resp.status_code == 500
    assert resp.json()["success"] is False


# ── Ingest ──────────────────────────────────────────────────────────


def test_assets_ingest_returns_task_id(tmp_path, monkeypatch):
    client = _client(tmp_path)

    async def fake_run_background(self, raw_text, **kwargs):
        return "task_fake_123"

    from app.services.assets.ingestion_agent import IngestionAgent

    monkeypatch.setattr(IngestionAgent, "run_background", fake_run_background)

    resp = client.post("/api/assets/ingest", json={"raw_text": "Some free text content"})
    assert resp.status_code == 200
    assert resp.json()["data"]["task_id"] == "task_fake_123"


def test_assets_ingest_validates_empty_text(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/api/assets/ingest", json={"raw_text": ""})
    assert resp.status_code == 400


# ── Style extract ───────────────────────────────────────────────────


def test_assets_style_extract_validates_inputs(tmp_path):
    client = _client(tmp_path)
    # Missing title
    resp = client.post("/api/assets/style-extract", json={"text": "some text", "title": ""})
    assert resp.status_code == 400
    # Missing text
    resp = client.post("/api/assets/style-extract", json={"text": "", "title": "a title"})
    assert resp.status_code == 400
