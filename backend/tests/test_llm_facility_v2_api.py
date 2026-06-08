from __future__ import annotations

from types import SimpleNamespace

from app import create_app
from app.config import Config


class DummyModelsClient:
    def list(self):
        return SimpleNamespace(data=[SimpleNamespace(id="gpt-v2", owned_by="test")])


class DummyOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.models = DummyModelsClient()


def test_v2_llm_facility_routes_match_legacy_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr("app.services.llm_settings_service.OpenAI", DummyOpenAI)
    app = create_app()
    client = app.test_client()

    create_response = client.post(
        "/api/v2/llm/channels",
        json={
            "name": "V2 Channel",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-v2-123456",
            "is_enabled": True,
            "max_concurrency": 3,
        },
    )
    assert create_response.status_code == 201
    created = create_response.get_json()["data"]
    channel_key = created["channel_key"]
    assert created["name"] == "V2 Channel"
    assert created["runtime"] == {"inflight": 0, "waiting": 0}

    sync_response = client.post(f"/api/v2/llm/channels/{channel_key}/sync-models")
    assert sync_response.status_code == 200

    bind_response = client.put(
        "/api/v2/llm/module-bindings/story_ontology",
        json={"channel_key": channel_key, "model_id": "gpt-v2"},
    )
    assert bind_response.status_code == 200

    settings_response = client.get("/api/v2/llm/settings")
    assert settings_response.status_code == 200
    settings = settings_response.get_json()["data"]
    modules = {item["module_key"]: item for item in settings["modules"]}
    assert modules["story_ontology"]["binding"]["model_id"] == "gpt-v2"

    update_response = client.patch(
        f"/api/v2/llm/channels/{channel_key}",
        json={"max_concurrency": 6},
    )
    assert update_response.status_code == 200
    assert update_response.get_json()["data"]["max_concurrency"] == 6

    activity_response = client.get("/api/v2/llm/activity")
    assert activity_response.status_code == 200
    assert sorted(activity_response.get_json()["data"]) == ["calls", "channels", "total_active"]

    delete_binding = client.delete("/api/v2/llm/module-bindings/story_ontology")
    assert delete_binding.status_code == 200
    assert delete_binding.get_json()["data"]["deleted"] is True

    delete_channel = client.delete(f"/api/v2/llm/channels/{channel_key}")
    assert delete_channel.status_code == 200
    assert delete_channel.get_json()["data"]["deleted"] is True
