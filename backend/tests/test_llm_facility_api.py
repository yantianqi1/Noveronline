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


def _create_channel(client, *, name="OpenAI Main", enabled=True):
    response = client.post(
        "/api/llm/channels",
        json={
            "name": name,
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test-123456",
            "is_enabled": enabled,
            "max_concurrency": 4,
        },
    )
    assert response.status_code == 201
    return response.get_json()["data"]


def test_llm_facility_supports_channel_sync_binding_and_unbinding(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr("app.services.llm_settings_service.OpenAI", DummyOpenAI)
    app = create_app()
    client = app.test_client()

    create_payload = _create_channel(client)
    assert create_payload["name"] == "OpenAI Main"
    assert create_payload["api_key_masked"].startswith("sk-")
    assert create_payload["max_concurrency"] == 4
    assert create_payload["runtime"] == {"inflight": 0, "waiting": 0}

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
    channels = {item["channel_key"]: item for item in snapshot["channels"]}
    assert modules["story_ontology"]["binding"]["channel_key"] == channel_key
    assert modules["story_ontology"]["binding"]["model_id"] == "gpt-4.1"
    assert modules["story_ontology"]["binding"]["updated_at"]
    assert channels[channel_key]["models"][0]["model_id"] == "gpt-4.1"
    assert channels[channel_key]["last_sync_status"] == "success"
    assert channels[channel_key]["max_concurrency"] == 4
    assert channels[channel_key]["runtime"] == {"inflight": 0, "waiting": 0}

    delete_response = client.delete("/api/llm/module-bindings/story_ontology")
    assert delete_response.status_code == 200
    assert delete_response.get_json()["data"] == {
        "module_key": "story_ontology",
        "deleted": True,
    }

    deleted_snapshot = client.get("/api/llm/settings")
    assert deleted_snapshot.status_code == 200
    deleted_modules = {item["module_key"]: item for item in deleted_snapshot.get_json()["data"]["modules"]}
    assert deleted_modules["story_ontology"]["binding"] is None

    missing_delete = client.delete("/api/llm/module-bindings/story_ontology")
    assert missing_delete.status_code == 404


def test_llm_facility_rejects_binding_to_disabled_channel(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr("app.services.llm_settings_service.OpenAI", DummyOpenAI)
    app = create_app()
    client = app.test_client()

    create_payload = _create_channel(client, name="Disabled Soon")
    channel_key = create_payload["channel_key"]

    sync_response = client.post(f"/api/llm/channels/{channel_key}/sync-models")
    assert sync_response.status_code == 200

    disable_response = client.patch(
        f"/api/llm/channels/{channel_key}",
        json={"is_enabled": False},
    )
    assert disable_response.status_code == 200
    assert disable_response.get_json()["data"]["is_enabled"] is False

    bind_response = client.put(
        "/api/llm/module-bindings/story_ontology",
        json={"channel_key": channel_key, "model_id": "gpt-4.1"},
    )

    assert bind_response.status_code == 400
    assert "渠道已停用" in bind_response.get_json()["error"]


def test_llm_facility_updates_channel_concurrency(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr("app.services.llm_settings_service.OpenAI", DummyOpenAI)
    app = create_app()
    client = app.test_client()

    create_payload = _create_channel(client)
    channel_key = create_payload["channel_key"]

    update_response = client.patch(
        f"/api/llm/channels/{channel_key}",
        json={"max_concurrency": 9},
    )

    assert update_response.status_code == 200
    updated = update_response.get_json()["data"]
    assert updated["max_concurrency"] == 9
    assert updated["runtime"] == {"inflight": 0, "waiting": 0}

    snapshot = client.get("/api/llm/settings").get_json()["data"]
    channel_map = {item["channel_key"]: item for item in snapshot["channels"]}
    assert channel_map[channel_key]["max_concurrency"] == 9


def test_llm_facility_rejects_invalid_channel_concurrency(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr("app.services.llm_settings_service.OpenAI", DummyOpenAI)
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/llm/channels",
        json={
            "name": "Invalid Concurrency",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test-123456",
            "is_enabled": True,
            "max_concurrency": 0,
        },
    )

    assert response.status_code == 400
    assert "max_concurrency" in response.get_json()["error"]


def test_llm_facility_lists_worldline_auto_evolution_modules(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr("app.services.llm_settings_service.OpenAI", DummyOpenAI)
    app = create_app()
    client = app.test_client()

    snapshot_response = client.get("/api/llm/settings")
    assert snapshot_response.status_code == 200
    module_keys = {item["module_key"] for item in snapshot_response.get_json()["data"]["modules"]}

    assert "worldline_agent_prepare" in module_keys
    assert "worldline_agent_action" in module_keys
    assert "worldline_goal_evaluator" in module_keys
