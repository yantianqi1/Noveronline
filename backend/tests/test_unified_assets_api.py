"""Integration tests for /api/unified-assets routes."""

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


# ── Sources ─────────────────────────────────────────────────────────


def test_unified_sources_returns_known_list(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/api/unified-assets/sources")
    assert resp.status_code == 200
    sources = resp.json()["data"]
    assert isinstance(sources, list)
    assert len(sources) > 0


# ── List and facets ─────────────────────────────────────────────────


def test_unified_list_returns_items(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/api/unified-assets")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "items" in data or isinstance(data, list)


def test_unified_facets_returns_counts(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/api/unified-assets/facets")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


# ── Search ──────────────────────────────────────────────────────────


def test_unified_search_requires_query(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/api/unified-assets/search?q=")
    assert resp.status_code == 400


# ── Reindex ─────────────────────────────────────────────────────────


def test_unified_reindex_requires_project_id(tmp_path):
    client = _client(tmp_path)
    # Pydantic schema requires project_id (str), so omitting it → 400
    resp = client.post("/api/unified-assets/reindex", json={})
    assert resp.status_code == 400


# ── Detail ──────────────────────────────────────────────────────────


def test_unified_get_nonexistent_returns_404(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/api/unified-assets/assets/nonexistent_id")
    assert resp.status_code == 404
