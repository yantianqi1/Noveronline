import json

from app.api_fastapi import draft_v2
from tests.test_writer_agent_api import _client, _create_project


def test_v2_draft_generation_events_streams_writer_orchestrator_events(tmp_path, monkeypatch):
    class FakeWriterOrchestrator:
        async def run(self, request):
            assert request["project_id"]
            assert request["task_type"] == "write_scene"
            assert request["scene_focus"] == "密信公开后的殿内反应"
            yield {"type": "orchestrator_status", "phase": "starting", "message": "fake start"}
            yield {"type": "writer_token", "token": "沈夜按下密信。"}
            yield {"type": "done", "scene_id": "sc_fake_001", "word_count": 7}

    monkeypatch.setattr(draft_v2, "WriterOrchestrator", FakeWriterOrchestrator, raising=False)
    client = _client(tmp_path, monkeypatch)
    project = _create_project(monkeypatch, tmp_path)

    response = client.post(
        "/api/v2/drafts/draft_stream_001/events",
        json={
            "project_id": project.project_id,
            "task_type": "write_scene",
            "scene_focus": "密信公开后的殿内反应",
        },
    )

    stream_text = response.text
    assert response.status_code == 200, stream_text
    assert "event: draft_started" in stream_text
    assert "event: writer_token" in stream_text
    assert "event: done" in stream_text

    payloads = [
        json.loads(line.removeprefix("data: "))
        for line in stream_text.splitlines()
        if line.startswith("data: ")
    ]
    started = next(item for item in payloads if item["type"] == "draft_started")
    assert started["draft_id"] == "draft_stream_001"
    token = next(item for item in payloads if item["type"] == "writer_token")
    assert token["token"] == "沈夜按下密信。"
    done = next(item for item in payloads if item["type"] == "done")
    assert done["draft_id"] == "draft_stream_001"
    assert done["scene_id"] == "sc_fake_001"


def test_v2_draft_create_persists_request_and_events_load_resource(tmp_path, monkeypatch):
    class FakeWriterOrchestrator:
        async def run(self, request):
            assert request["project_id"]
            assert request["scene_focus"] == "从持久化 draft request 读取"
            yield {"type": "writer_token", "token": "持久化草稿流。"}
            yield {"type": "done", "scene_id": "sc_persisted_001"}

    monkeypatch.setattr(draft_v2, "WriterOrchestrator", FakeWriterOrchestrator, raising=False)
    client = _client(tmp_path, monkeypatch)
    project = _create_project(monkeypatch, tmp_path)

    create_response = client.post(
        "/api/v2/drafts",
        json={
            "project_id": project.project_id,
            "task_type": "write_scene",
            "scene_focus": "从持久化 draft request 读取",
        },
    )

    assert create_response.status_code == 202, create_response.json()
    created = create_response.json()["data"]
    draft_id = created["draft_id"]
    assert draft_id.startswith("draft_")
    assert created["asset_id"] == draft_id
    assert created["events_url"] == f"/api/v2/drafts/{draft_id}/events"

    asset_response = client.get(f"/api/assets/{draft_id}?project_id={project.project_id}")
    assert asset_response.status_code == 200, asset_response.json()
    asset = asset_response.json()["data"]
    assert asset["asset_type"] == "draft_session"
    assert asset["payload"]["request"]["scene_focus"] == "从持久化 draft request 读取"

    stream_response = client.post(created["events_url"], json={})
    assert stream_response.status_code == 200, stream_response.text
    assert "持久化草稿流。" in stream_response.text


def test_v2_draft_revision_events_streams_writer_orchestrator_events(tmp_path, monkeypatch):
    class FakeWriterOrchestrator:
        async def run(self, request):
            assert request["project_id"]
            assert request["selected_text"] == "沈夜站在殿中。"
            assert request["user_instruction"] == "强化殿内压迫感"
            yield {"type": "orchestrator_status", "phase": "rewriting", "message": "fake revise"}
            yield {"type": "writer_token", "token": "沈夜站在殿中，沉默压住四壁。"}
            yield {"type": "done", "scene_id": "sc_revision_001", "word_count": 14}

    monkeypatch.setattr(draft_v2, "WriterOrchestrator", FakeWriterOrchestrator, raising=False)
    client = _client(tmp_path, monkeypatch)
    project = _create_project(monkeypatch, tmp_path)

    response = client.post(
        "/api/v2/drafts/draft_stream_001/revisions/rev_001/events",
        json={
            "project_id": project.project_id,
            "draft": "沈夜站在殿中。",
            "revision_instruction": "强化殿内压迫感",
        },
    )

    stream_text = response.text
    assert response.status_code == 200, stream_text
    assert "event: revision_started" in stream_text
    assert "event: writer_token" in stream_text
    assert "event: done" in stream_text

    payloads = [
        json.loads(line.removeprefix("data: "))
        for line in stream_text.splitlines()
        if line.startswith("data: ")
    ]
    started = next(item for item in payloads if item["type"] == "revision_started")
    assert started["draft_id"] == "draft_stream_001"
    assert started["revision_id"] == "rev_001"
    token = next(item for item in payloads if item["type"] == "writer_token")
    assert token["revision_id"] == "rev_001"
    assert token["token"] == "沈夜站在殿中，沉默压住四壁。"
    done = next(item for item in payloads if item["type"] == "done")
    assert done["draft_id"] == "draft_stream_001"
    assert done["revision_id"] == "rev_001"


def test_v2_draft_revision_create_persists_request_and_events_load_resource(tmp_path, monkeypatch):
    class FakeWriterOrchestrator:
        async def run(self, request):
            assert request["project_id"]
            assert request["selected_text"] == "沈夜站在殿中。"
            assert request["user_instruction"] == "从持久化 revision request 读取"
            yield {"type": "writer_token", "token": "持久化修订流。"}
            yield {"type": "done", "scene_id": "sc_revision_persisted"}

    monkeypatch.setattr(draft_v2, "WriterOrchestrator", FakeWriterOrchestrator, raising=False)
    client = _client(tmp_path, monkeypatch)
    project = _create_project(monkeypatch, tmp_path)

    draft_response = client.post(
        "/api/v2/drafts",
        json={"project_id": project.project_id, "scene_focus": "原始草稿"},
    )
    draft_id = draft_response.json()["data"]["draft_id"]

    create_response = client.post(
        f"/api/v2/drafts/{draft_id}/revisions",
        json={
            "project_id": project.project_id,
            "draft": "沈夜站在殿中。",
            "revision_instruction": "从持久化 revision request 读取",
        },
    )

    assert create_response.status_code == 202, create_response.json()
    created = create_response.json()["data"]
    revision_id = created["revision_id"]
    assert revision_id.startswith("rev_")
    assert created["asset_id"] == revision_id
    assert created["events_url"] == f"/api/v2/drafts/{draft_id}/revisions/{revision_id}/events"

    asset_response = client.get(f"/api/assets/{revision_id}?project_id={project.project_id}")
    assert asset_response.status_code == 200, asset_response.json()
    asset = asset_response.json()["data"]
    assert asset["asset_type"] == "draft_revision"
    assert asset["payload"]["draft_id"] == draft_id
    assert asset["payload"]["request"]["revision_instruction"] == "从持久化 revision request 读取"

    stream_response = client.post(created["events_url"], json={})
    assert stream_response.status_code == 200, stream_response.text
    assert "持久化修订流。" in stream_response.text


def test_v2_draft_finalization_commits_manuscript_block(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    project = _create_project(monkeypatch, tmp_path)

    response = client.post(
        "/api/v2/drafts/draft_scene_001/finalizations",
        json={
            "project_id": project.project_id,
            "content": "沈夜把密信按在长案上，殿内所有人都沉默下来。",
            "source_scene_id": "sc_seed_001",
            "chapter_tag": "第一章",
            "pov_entity_id": "沈夜",
            "location": "玄霄宗大殿",
            "involved_entity_ids": ["沈夜", "秦昭"],
        },
    )

    assert response.status_code == 200, response.json()
    payload = response.json()["data"]
    assert payload["draft_id"] == "draft_scene_001"
    block = payload["finalization"]
    assert block["block_id"].startswith("mb_")
    assert block["content"] == "沈夜把密信按在长案上，殿内所有人都沉默下来。"
    assert block["source_scene_id"] == "sc_seed_001"
    assert block["chapter_tag"] == "第一章"
    assert block["pov_entity_id"] == "沈夜"
    assert block["location"] == "玄霄宗大殿"

    list_response = client.get(f"/api/writer-agent/manuscript/{project.project_id}")
    assert list_response.status_code == 200, list_response.json()
    blocks = list_response.json()["data"]["blocks"]
    persisted = next(item for item in blocks if item["block_id"] == block["block_id"])
    assert persisted["content"] == block["content"]
    assert persisted["source_scene_id"] == "sc_seed_001"
    assert persisted["chapter_tag"] == "第一章"


def test_v2_draft_finalization_rejects_empty_content(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    project = _create_project(monkeypatch, tmp_path)

    response = client.post(
        "/api/v2/drafts/draft_empty/finalizations",
        json={"project_id": project.project_id, "content": "  "},
    )

    assert response.status_code == 400
    assert "内容不能为空" in response.json()["error"]
