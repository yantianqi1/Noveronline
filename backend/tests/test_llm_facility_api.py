from types import SimpleNamespace

from app import create_app
from app.config import Config


class DummyModelsClient:
    def list(self):
        return SimpleNamespace(
            data=[
                SimpleNamespace(id="gpt-4.1", owned_by="openai"),
                SimpleNamespace(id="gpt-4.1-mini", owned_by="openai"),
            ]
        )


class DummyOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.models = DummyModelsClient()


def test_llm_facility_supports_channel_sync_and_module_binding(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr("app.services.llm_settings_service.OpenAI", DummyOpenAI)
    app = create_app()
    client = app.test_client()

    create_response = client.post(
        "/api/llm/channels",
        json={
            "name": "OpenAI Main",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test-123456",
            "is_enabled": True,
        },
    )

    assert create_response.status_code == 201
    create_payload = create_response.get_json()["data"]
    assert create_payload["name"] == "OpenAI Main"
    assert create_payload["api_key_masked"].startswith("sk-")

    channel_key = create_payload["channel_key"]
    sync_response = client.post(f"/api/llm/channels/{channel_key}/sync-models")
    assert sync_response.status_code == 200

    bind_response = client.put(
        "/api/llm/module-bindings/story_ontology",
        json={"channel_key": channel_key, "model_id": "gpt-4.1"},
    )
    assert bind_response.status_code == 200

    snapshot_response = client.get("/api/llm/settings")
    assert snapshot_response.status_code == 200
    snapshot = snapshot_response.get_json()["data"]

    modules = {item["module_key"]: item for item in snapshot["modules"]}
    assert modules["story_ontology"]["binding"]["channel_key"] == channel_key
    assert modules["story_ontology"]["binding"]["model_id"] == "gpt-4.1"
    assert snapshot["channels"][0]["models"][0]["model_id"] == "gpt-4.1"
    assert snapshot["channels"][0]["last_sync_status"] == "success"
