from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_writer_phase2_tools_read_assets_graph_and_worldline_context():
    from app.database import get_engine
    from app.repositories.asset_repo import AssetRepository
    from app.repositories.entity_repo import EntityRepository
    from app.repositories.graph_repo import GraphRepository
    from app.repositories.world_rule_repo import WorldRuleRepository
    from app.repositories.worldline_session_repo import WorldlineSessionRepository
    from app.services.pi_writer_runtime.tools import WriterToolRegistry

    engine = get_engine()
    project_id = "proj_phase2_tools"
    context = {
        "tenant_id": "local_tenant",
        "project_id": project_id,
        "run_id": "run_phase2_tools",
    }
    timestamp = _now()

    AssetRepository(engine).create_asset(
        {
            "asset_id": "ast_style_rain",
            "project_id": project_id,
            "scope": "project",
            "asset_type": "writing_style",
            "category": "style",
            "title": "雨夜压迫感",
            "summary": "雨声、窄巷和低声谈判制造压迫感。",
            "content": "雨声像密集指节敲在瓦面。",
            "payload_json": "{}",
            "tags_json": json.dumps(["雨夜", "谈判"], ensure_ascii=False),
            "source_kind": "user_material",
            "source_ref": "fixture",
            "enabled": 1,
            "pinned": 0,
            "word_count": 14,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
    )
    EntityRepository(engine).upsert_entity(
        project_id,
        {
            "entity_id": "ent_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "major",
            "summary": "外冷内热的谈判者。",
            "core_drive": "保护宗门残部",
            "surface_mask": "冷淡",
            "hidden_tension": "害怕再次失去同伴",
            "profile_json": json.dumps({"voice": "短句"}, ensure_ascii=False),
            "created_at": timestamp,
            "updated_at": timestamp,
        },
    )
    WorldRuleRepository(engine).upsert_world_rule(
        project_id,
        {
            "evidence_id": "rule_spirit",
            "fact_text": "灵气不能凭空生成，雨夜阵法会消耗储备。",
            "segment_id": "seg_1",
            "chapter_order": 1,
            "evidence_snippet": "雨夜阵法必须借旧玉供能。",
            "created_at": timestamp,
        },
    )
    GraphRepository(engine).save_snapshot(
        project_id,
        "graph_1",
        {
            "graph_name": "测试图谱",
            "built_at": timestamp,
            "build_version": "test",
            "nodes": [
                {
                    "uuid": "node_shenye",
                    "name": "沈夜",
                    "labels": ["Character"],
                    "summary": "谈判者",
                    "attributes": {"aliases": []},
                    "evidence_refs": [],
                },
                {
                    "uuid": "node_rival",
                    "name": "祁衡",
                    "labels": ["Character"],
                    "summary": "对手",
                    "attributes": {"aliases": []},
                    "evidence_refs": [],
                },
            ],
            "edges": [
                {
                    "uuid": "edge_1",
                    "name": "旧债",
                    "fact": "沈夜与祁衡在宗门旧债上互相试探。",
                    "source_node_uuid": "node_shenye",
                    "target_node_uuid": "node_rival",
                    "attributes": {},
                    "weight": 7,
                    "evidence_refs": [],
                }
            ],
        },
    )
    WorldlineSessionRepository(engine).save_session(
        {
            "session_id": "wls_1",
            "project_id": project_id,
            "graph_id": "graph_1",
            "label": "雨夜变量",
            "status": "running",
            "simulation_goal": "测试谈判变量",
            "focus_question": "如果祁衡提前摊牌会怎样？",
            "branch_count": 1,
            "saved_paths": [
                {
                    "path_id": "wpath_rain",
                    "title": "雨夜摊牌",
                    "summary": "祁衡提前亮出旧债证据，沈夜被迫让步。",
                    "selected_event_ids": ["evt_1"],
                    "writer_instruction": "作为参考，不要自动写入正典。",
                    "lifecycle": "simulation",
                }
            ],
        }
    )

    tools = WriterToolRegistry(engine)

    assets = tools.execute("query_assets", context, {"query": "雨夜", "selected_asset_ids": []})
    assert assets["items"][0]["asset_id"] == "ast_style_rain"
    assert assets["items"][0]["title"] == "雨夜压迫感"

    rules = tools.execute("query_world_rules", context, {"query": "灵气"})
    assert rules["items"][0]["evidence_id"] == "rule_spirit"
    assert "雨夜阵法" in rules["items"][0]["fact_text"]

    profile = tools.execute("query_character_profile", context, {"name": "沈夜"})
    assert profile["entity"]["entity_id"] == "ent_shenye"
    assert profile["entity"]["core_drive"] == "保护宗门残部"

    neighbors = tools.execute("query_graph_neighbors", context, {"node_name": "沈夜"})
    assert neighbors["node"]["uuid"] == "node_shenye"
    assert neighbors["neighbors"][0]["neighbor_name"] == "祁衡"
    assert neighbors["neighbors"][0]["edge_fact"] == "沈夜与祁衡在宗门旧债上互相试探。"

    paths = tools.execute("query_worldline_paths", context, {"path_ids": ["wpath_rain"]})
    assert paths["items"][0]["path_id"] == "wpath_rain"
    assert paths["items"][0]["lifecycle"] == "simulation"
    assert "不要自动写入正典" in paths["items"][0]["writer_instruction"]


def test_writer_phase2_tools_reject_context_mismatch():
    from app.database import get_engine
    from app.services.pi_writer_runtime.errors import ToolPermissionDeniedError
    from app.services.pi_writer_runtime.tools import WriterToolRegistry

    tools = WriterToolRegistry(get_engine())

    try:
        tools.execute(
            "query_assets",
            {"tenant_id": "local_tenant", "project_id": "proj_a", "run_id": "run_1"},
            {"tenant_id": "other_tenant", "query": "x"},
        )
    except ToolPermissionDeniedError as exc:
        assert exc.code == "TOOL_PERMISSION_DENIED"
        assert "tenant_id" in str(exc)
    else:
        raise AssertionError("context mismatch should be rejected")


def test_runtime_emits_phase2_tool_events_before_draft_save():
    from app.database import get_engine
    from app.repositories.asset_repo import AssetRepository
    from app.repositories.entity_repo import EntityRepository
    from app.repositories.graph_repo import GraphRepository
    from app.repositories.writer_run_repo import WriterRunRepository
    from app.repositories.worldline_session_repo import WorldlineSessionRepository
    from app.services.pi_writer_runtime.runtime import PiWriterRuntime

    class FakeLlmAdapter:
        async def build_async_client(self, **kwargs):
            class FakeClient:
                async def chat_stream(self, messages, temperature=0.7, max_tokens=4096):
                    yield "草稿正文"

            return FakeClient()

    engine = get_engine()
    project_id = "proj_phase2_runtime"
    timestamp = _now()
    AssetRepository(engine).create_asset(
        {
            "asset_id": "ast_runtime",
            "project_id": project_id,
            "scope": "project",
            "asset_type": "writing_style",
            "category": "style",
            "title": "谈判风格",
            "summary": "克制、压迫。",
            "content": "短句推进。",
            "payload_json": "{}",
            "tags_json": "[]",
            "source_kind": "fixture",
            "source_ref": "test",
            "enabled": 1,
            "pinned": 0,
            "word_count": 4,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
    )
    EntityRepository(engine).upsert_entity(
        project_id,
        {
            "entity_id": "ent_runtime",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "major",
            "summary": "谈判者。",
            "profile_json": "{}",
            "created_at": timestamp,
            "updated_at": timestamp,
        },
    )
    GraphRepository(engine).save_snapshot(
        project_id,
        "graph_runtime",
        {
            "graph_name": "runtime",
            "built_at": timestamp,
            "build_version": "test",
            "nodes": [
                {"uuid": "node_runtime", "name": "沈夜", "labels": ["Character"], "summary": "", "attributes": {}, "evidence_refs": []}
            ],
            "edges": [],
        },
    )
    WorldlineSessionRepository(engine).save_session(
        {
            "session_id": "wls_runtime",
            "project_id": project_id,
            "graph_id": "graph_runtime",
            "label": "runtime",
            "saved_paths": [
                {
                    "path_id": "wpath_runtime",
                    "title": "路径",
                    "summary": "只作为参考。",
                    "selected_event_ids": [],
                    "writer_instruction": "不要自动采用。",
                    "lifecycle": "simulation",
                }
            ],
        }
    )
    repo = WriterRunRepository(engine)
    run = repo.create_run(
        tenant_id="local_tenant",
        project_id=project_id,
        started_by="usr_test",
        mode="draft",
        instruction="写谈判",
        module_key="writer_composer",
        options={
            "selected_asset_ids": ["ast_runtime"],
            "worldline_path_ids": ["wpath_runtime"],
            "character_names": ["沈夜"],
            "graph_node_names": ["沈夜"],
        },
    )

    import asyncio

    asyncio.run(PiWriterRuntime(repo=repo, llm_adapter=FakeLlmAdapter()).run(run))

    event_types = [event["type"] for event in repo.list_events("local_tenant", run["run_id"])]
    assert event_types.count("writer.tool.started") >= 4
    assert event_types.count("writer.tool.completed") >= 4
    completed_events = repo.list_events("local_tenant", run["run_id"])
    tool_payloads = [
        event["payload"]
        for event in completed_events
        if event["type"] == "writer.tool.completed"
    ]
    assert {payload["tool_name"] for payload in tool_payloads} >= {
        "query_assets",
        "query_character_profile",
        "query_graph_neighbors",
        "query_worldline_paths",
    }
    assert repo.list_drafts_for_run("local_tenant", run["run_id"])[0]["content"] == "草稿正文"
