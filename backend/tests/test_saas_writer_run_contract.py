from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import create_app


def test_writer_run_missing_llm_binding_returns_contract_error(tmp_path):
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/projects/proj_contract/writer-runs",
        json={
            "mode": "draft",
            "instruction": "写一段雨夜谈判。",
            "selected_asset_ids": ["ast_reference"],
            "worldline_path_ids": ["wpath_reference"],
            "options": {"module_key": "writer_composer"},
        },
    )

    assert response.status_code == 424
    payload = response.json()
    assert payload["error"]["code"] == "LLM_MODULE_UNBOUND"
    assert payload["error"]["details"]["module_key"] == "writer_composer"
    assert payload["error"]["details"]["run_id"].startswith("run_")

    run_id = payload["error"]["details"]["run_id"]
    run_response = client.get(f"/api/v1/writer-runs/{run_id}")
    assert run_response.status_code == 200
    run_payload = run_response.json()["data"]
    assert run_payload["tenant_id"] == "local_tenant"
    assert run_payload["project_id"] == "proj_contract"
    assert run_payload["status"] == "failed"
    assert run_payload["error_code"] == "LLM_MODULE_UNBOUND"
    assert run_payload["options"]["selected_asset_ids"] == ["ast_reference"]
    assert run_payload["options"]["worldline_path_ids"] == ["wpath_reference"]


def test_writer_run_preserves_selected_references_in_options():
    from app.database import get_engine
    from app.repositories.writer_run_repo import WriterRunRepository

    repo = WriterRunRepository(get_engine())
    run = repo.create_run(
        tenant_id="local_tenant",
        project_id="proj_refs",
        started_by="usr_test",
        mode="draft",
        instruction="写引用上下文",
        module_key="writer_composer",
        options={
            "selected_asset_ids": ["ast_1"],
            "worldline_path_ids": ["wpath_1"],
            "character_names": ["沈夜"],
            "graph_node_names": ["沈夜"],
        },
    )

    loaded = repo.get_run("local_tenant", run["run_id"])
    assert loaded["options"]["selected_asset_ids"] == ["ast_1"]
    assert loaded["options"]["worldline_path_ids"] == ["wpath_1"]


def test_pi_writer_event_mapper_preserves_run_context():
    from app.services.pi_writer_runtime.event_mapper import map_pi_event

    context = {
        "tenant_id": "ten_1",
        "project_id": "proj_1",
        "run_id": "run_1",
    }

    mapped = map_pi_event(
        {"type": "tool_execution_start", "toolName": "query_assets", "args": {"q": "rain"}},
        context,
    )

    assert mapped["type"] == "writer.tool.started"
    assert mapped["tenant_id"] == "ten_1"
    assert mapped["project_id"] == "proj_1"
    assert mapped["run_id"] == "run_1"
    assert mapped["payload"]["tool_name"] == "query_assets"
    assert mapped["payload"]["args"] == {"q": "rain"}


def test_writer_run_repository_saves_draft_idempotently_and_adopts_explicitly():
    from app.database import get_engine
    from app.repositories.manuscript_repo import ManuscriptRepository
    from app.repositories.writer_run_repo import WriterRunRepository

    repo = WriterRunRepository(get_engine())
    manuscript_repo = ManuscriptRepository(get_engine())
    run = repo.create_run(
        tenant_id="local_tenant",
        project_id="proj_draft",
        started_by="usr_test",
        mode="draft",
        instruction="写一个可采用草稿。",
        module_key="writer_composer",
        chapter_id="chap_1",
        scene_id="scene_1",
    )

    first = repo.save_draft_revision(
        tenant_id="local_tenant",
        project_id="proj_draft",
        run_id=run["run_id"],
        chapter_id="chap_1",
        scene_id="scene_1",
        content="第一版草稿",
        metadata={"source": "test"},
        created_by="usr_test",
    )
    second = repo.save_draft_revision(
        tenant_id="local_tenant",
        project_id="proj_draft",
        run_id=run["run_id"],
        chapter_id="chap_1",
        scene_id="scene_1",
        content="第一版草稿",
        metadata={"source": "test"},
        created_by="usr_test",
    )

    assert first["draft_id"] == second["draft_id"]
    assert repo.list_drafts_for_run("local_tenant", run["run_id"]) == [second]
    assert manuscript_repo.list_blocks("proj_draft") == []

    adoption = repo.adopt_draft_to_manuscript(
        tenant_id="local_tenant",
        draft_id=first["draft_id"],
        adopted_by="usr_test",
    )

    assert adoption["draft_id"] == first["draft_id"]
    assert adoption["block_id"].startswith("ms_")
    blocks = manuscript_repo.list_blocks("proj_draft")
    assert len(blocks) == 1
    assert blocks[0]["content"] == "第一版草稿"
    payload = json.loads(blocks[0]["payload_json"])
    assert payload["source_draft_id"] == first["draft_id"]
    assert payload["run_id"] == run["run_id"]
