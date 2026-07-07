from __future__ import annotations

import json
from typing import Any

from mirofish_agents.common.context import AgentContext
from mirofish_agents.temporal.assets import (
    ASSET_INGESTION_MODULE_KEY,
    ASSET_REINDEX_MODULE_KEY,
    ASSET_TASK_QUEUE,
    LLMFacilityAssetIngestionRunner,
    LLMFacilityStyleExtractionRunner,
    PostgresAssetCandidateWriter,
    PostgresAssetReindexer,
    PostgresStyleSourceMaterialLoader,
    STYLE_EXTRACTION_MODULE_KEY,
    asset_ingestion_activity,
    asset_reindex_activity,
    run_asset_ingestion_workflow_locally,
    run_asset_reindex_workflow_locally,
    run_style_extraction_workflow_locally,
    style_extraction_activity,
    worker_spec,
)
from mirofish_agents.seed.sequential_reader import LLMFacilityError, ModuleBindingResolution
from mirofish_agents.temporal.worker import worker_components_for_task_queue


class RecordingWorkflowEventWriter:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def write_event(
        self,
        *,
        tenant_id: str,
        project_id: str | None,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        self.events.append(
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "run_id": run_id,
                "event_type": event_type,
                "payload": payload,
            }
        )


class RecordingAssetIngestionRunner:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def ingest(
        self,
        *,
        context: AgentContext,
        module_key: str,
        material_text: str,
        hint_type: str | None,
        scope: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "context": context,
                "module_key": module_key,
                "material_text": material_text,
                "hint_type": hint_type,
                "scope": scope,
                "options": options,
            }
        )
        return self.result


class RecordingAssetReindexer:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def reindex(
        self,
        *,
        context: AgentContext,
        scope: str,
        mode: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "context": context,
                "scope": scope,
                "mode": mode,
                "options": options,
            }
        )
        return self.result


def _context() -> AgentContext:
    return AgentContext(
        tenant_id="tenant-1",
        project_id="project-1",
        run_id="run-1",
        workflow_type="asset_ingestion",
        actor_user_id="user-1",
        module_key=ASSET_INGESTION_MODULE_KEY,
        trace_id="trace-1",
        permissions={"asset_ingestion": ["run"]},
    )


def _payload() -> dict[str, Any]:
    return {
        "context": _context().model_dump(),
        "material_text": "灵气不可凭空生成。这里是用户素材正文。",
        "hint_type": "world_rule",
        "scope": "project",
        "options": {"language": "zh-CN"},
    }


def _style_context() -> AgentContext:
    return AgentContext(
        tenant_id="tenant-1",
        project_id="project-1",
        run_id="style-run-1",
        workflow_type="style_extraction",
        actor_user_id="user-1",
        module_key=STYLE_EXTRACTION_MODULE_KEY,
        trace_id="trace-style-1",
        permissions={"style_extractor": ["run"]},
    )


def _style_payload() -> dict[str, Any]:
    return {
        "context": _style_context().model_dump(),
        "material_text": "这是一段不应公开的作者文风样本文本。",
        "source_asset_id": "asset-style-source-1",
        "scope": "project",
        "options": {"language": "zh-CN", "prompt": "remove me"},
    }


def _asset_reindex_context() -> AgentContext:
    return AgentContext(
        tenant_id="tenant-1",
        project_id="project-1",
        run_id="run-asset-reindex-1",
        workflow_type="asset_reindex",
        actor_user_id="user-1",
        module_key=ASSET_REINDEX_MODULE_KEY,
        trace_id="trace-asset-reindex-1",
        permissions={"asset_reindex": ["run"]},
    )


def _asset_reindex_payload(options: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "context": _asset_reindex_context().model_dump(),
        "scope": "project",
        "mode": "keyword",
        "options": options if options is not None else {"include_disabled": False},
    }


def test_asset_ingestion_activity_requires_explicit_permission() -> None:
    context = _context().model_copy(update={"permissions": {}})

    result = asset_ingestion_activity({"context": context.model_dump(), "material_text": "素材"})

    assert result["status"] == "failed"
    assert result["error"]["code"] == "FORBIDDEN"
    assert result["tenant_id"] == "tenant-1"
    assert result["project_id"] == "project-1"
    assert result["run_id"] == "run-1"


def test_asset_ingestion_activity_fails_closed_without_runner_and_does_not_leak_material() -> None:
    writer = RecordingWorkflowEventWriter()

    result = asset_ingestion_activity(_payload(), workflow_event_writer=writer)

    assert result["status"] == "failed"
    assert result["stage"] == "asset_ingestion"
    assert result["module_key"] == ASSET_INGESTION_MODULE_KEY
    assert result["error"]["code"] == "ASSET_INGESTION_RUNNER_UNCONFIGURED"
    assert result["stage_event_persisted"] is True
    result_json = json.dumps(result, ensure_ascii=False)
    assert "灵气不可凭空生成" not in result_json
    assert "material_text" not in result_json
    assert len(writer.events) == 1
    assert writer.events[0]["event_type"] == "asset.stage.failed"
    event_json = json.dumps(writer.events[0], ensure_ascii=False)
    assert "灵气不可凭空生成" not in event_json
    assert "material_text" not in event_json
    assert "api_key" not in event_json
    assert "credential_ref" not in event_json


def test_style_extraction_activity_fails_closed_without_runner_and_does_not_leak_material() -> None:
    writer = RecordingWorkflowEventWriter()

    result = style_extraction_activity(_style_payload(), workflow_event_writer=writer)

    assert result["status"] == "failed"
    assert result["stage"] == "style_extraction"
    assert result["module_key"] == STYLE_EXTRACTION_MODULE_KEY
    assert result["error"]["code"] == "STYLE_EXTRACTION_RUNNER_UNCONFIGURED"
    assert result["stage_event_persisted"] is True
    result_json = json.dumps(result, ensure_ascii=False)
    assert "作者文风" not in result_json
    assert "material_text" not in result_json
    assert "prompt" not in result_json
    assert len(writer.events) == 1
    assert writer.events[0]["event_type"] == "asset.stage.failed"
    event_json = json.dumps(writer.events[0], ensure_ascii=False)
    assert "作者文风" not in event_json
    assert "material_text" not in event_json
    assert "api_key" not in event_json
    assert "credential_ref" not in event_json


def test_style_extraction_local_workflow_uses_fail_closed_activity() -> None:
    result = run_style_extraction_workflow_locally(_style_payload(), workflow_event_writer=RecordingWorkflowEventWriter())

    assert result["status"] == "failed"
    assert result["workflow_type"] == "style_extraction"
    assert result["error"]["code"] == "STYLE_EXTRACTION_RUNNER_UNCONFIGURED"


def test_style_extraction_activity_records_sanitized_candidate_metadata_from_runner() -> None:
    writer = RecordingWorkflowEventWriter()
    runner = RecordingStyleExtractionRunner(
        {
            "status": "completed",
            "module_key": STYLE_EXTRACTION_MODULE_KEY,
            "model_id": "gpt-style",
            "candidate_batch_id": "style-extraction:style-run-1",
            "candidate_count": 1,
            "asset_type_counts": {"style_profile": 1},
            "style_profile": {"title": "不应公开的提取正文"},
            "prompt": "不应公开的 prompt",
        }
    )

    result = style_extraction_activity(_style_payload(), style_extraction_runner=runner, workflow_event_writer=writer)

    assert result["status"] == "completed"
    assert result["candidate_batch_id"] == "style-extraction:style-run-1"
    assert result["candidate_count"] == 1
    assert result["asset_type_counts"] == {"style_profile": 1}
    assert result["stage_event_persisted"] is True
    assert runner.calls[0]["module_key"] == STYLE_EXTRACTION_MODULE_KEY
    assert runner.calls[0]["material_text"] == _style_payload()["material_text"]
    assert runner.calls[0]["source_asset_id"] == "asset-style-source-1"
    assert runner.calls[0]["scope"] == "project"
    result_json = json.dumps(result, ensure_ascii=False)
    assert "不应公开" not in result_json
    assert "作者文风" not in result_json
    assert "prompt" not in result_json
    assert len(writer.events) == 1
    assert writer.events[0]["event_type"] == "asset.stage.completed"
    event_json = json.dumps(writer.events[0], ensure_ascii=False)
    assert "不应公开" not in event_json
    assert "作者文风" not in event_json
    assert "prompt" not in event_json


def test_asset_ingestion_activity_records_sanitized_metadata_from_runner() -> None:
    writer = RecordingWorkflowEventWriter()
    runner = RecordingAssetIngestionRunner(
        {
            "status": "completed",
            "module_key": ASSET_INGESTION_MODULE_KEY,
            "model_id": "gpt-asset",
            "candidate_batch_id": "asset-candidate-batch-1",
            "candidate_count": 2,
            "asset_type_counts": {"world_rule": 1, "note": 1},
            "candidates": [{"title": "不应公开的候选正文"}],
            "prompt": "不应公开的 prompt",
        }
    )

    result = asset_ingestion_activity(_payload(), asset_ingestion_runner=runner, workflow_event_writer=writer)

    assert result["status"] == "completed"
    assert result["candidate_batch_id"] == "asset-candidate-batch-1"
    assert result["candidate_count"] == 2
    assert result["asset_type_counts"] == {"world_rule": 1, "note": 1}
    assert result["stage_event_persisted"] is True
    assert runner.calls[0]["module_key"] == ASSET_INGESTION_MODULE_KEY
    assert runner.calls[0]["material_text"] == _payload()["material_text"]
    assert runner.calls[0]["hint_type"] == "world_rule"
    assert runner.calls[0]["scope"] == "project"
    result_json = json.dumps(result, ensure_ascii=False)
    assert "不应公开" not in result_json
    assert "灵气不可凭空生成" not in result_json
    assert len(writer.events) == 1
    assert writer.events[0]["event_type"] == "asset.stage.completed"
    event_json = json.dumps(writer.events[0], ensure_ascii=False)
    assert "不应公开" not in event_json
    assert "灵气不可凭空生成" not in event_json


def test_llm_facility_asset_ingestion_runner_persists_candidate_assets_without_public_body() -> None:
    resolver = RecordingBindingResolver(_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-asset")
    chat_client = RecordingJSONChatClient(
        response_json={
            "candidates": [
                {
                    "asset_type": "world_rule",
                    "category": "world",
                    "title": "灵气守恒",
                    "summary": "灵气不可凭空生成，只能转化。",
                    "tags": ["world", "rule"],
                    "payload": {
                        "statement": "灵气只能从既有来源转化",
                        "prompt": "must be stripped before persistence",
                        "api_key": "must be stripped before persistence",
                    },
                },
                {
                    "asset_type": "note",
                    "title": "雨夜谈判素材",
                    "summary": "压迫感来自雨声与灯影。",
                },
            ]
        }
    )
    writer = RecordingCandidateAssetWriter()
    runner = LLMFacilityAssetIngestionRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_writer=writer,
    )

    result = runner.ingest(
        context=_context(),
        module_key=ASSET_INGESTION_MODULE_KEY,
        material_text="灵气不可凭空生成。这里是用户素材正文。",
        hint_type="world_rule",
        scope="project",
        options={"language": "zh-CN"},
    )

    assert result == {
        "status": "completed",
        "module_key": ASSET_INGESTION_MODULE_KEY,
        "model_id": "model-asset",
        "candidate_batch_id": "asset-ingestion:run-1",
        "candidate_count": 2,
        "asset_type_counts": {"world_rule": 1, "note": 1},
    }
    assert resolver.calls == [ASSET_INGESTION_MODULE_KEY]
    assert credentials.calls == ["channel-asset"]
    assert chat_client.calls[0]["api_key"] == "sk-asset"
    assert chat_client.calls[0]["resolution"].module_key == ASSET_INGESTION_MODULE_KEY
    assert writer.calls[0]["candidate_batch_id"] == "asset-ingestion:run-1"
    assert writer.calls[0]["scope"] == "project"
    assert writer.calls[0]["candidates"][0]["payload"] == {"statement": "灵气只能从既有来源转化"}
    result_json = json.dumps(result, ensure_ascii=False)
    assert "灵气不可凭空生成" not in result_json
    assert "灵气只能从既有来源转化" not in result_json
    assert "sk-asset" not in result_json


def test_llm_facility_style_extraction_runner_persists_style_profile_candidate_without_public_body() -> None:
    resolver = RecordingBindingResolver(_style_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-style")
    chat_client = RecordingJSONChatClient(
        response_json={
            "style_profile": {
                "title": "冷峻雨夜谈判风格",
                "summary": "短句、低照度意象和克制动作推动压迫感。",
                "tags": ["style", "noir"],
                "payload": {
                    "diction": ["短句", "克制动词"],
                    "rhythm": "紧凑",
                    "material_text": "must be stripped before persistence",
                    "prompt": "must be stripped before persistence",
                    "api_key": "must be stripped before persistence",
                    "quotes": ["must be stripped before persistence"],
                },
            }
        }
    )
    writer = RecordingCandidateAssetWriter()
    runner = LLMFacilityStyleExtractionRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_writer=writer,
    )

    result = runner.extract_style(
        context=_style_context(),
        module_key=STYLE_EXTRACTION_MODULE_KEY,
        material_text="这是一段不应公开的作者文风样本文本。",
        source_asset_id="asset-style-source-1",
        scope="project",
        options={"language": "zh-CN", "prompt": "remove me"},
    )

    assert result == {
        "status": "completed",
        "module_key": STYLE_EXTRACTION_MODULE_KEY,
        "model_id": "model-style",
        "candidate_batch_id": "style-extraction:style-run-1",
        "candidate_count": 1,
        "asset_type_counts": {"style_profile": 1},
    }
    assert resolver.calls == [STYLE_EXTRACTION_MODULE_KEY]
    assert credentials.calls == ["channel-style"]
    assert chat_client.calls[0]["api_key"] == "sk-style"
    assert chat_client.calls[0]["resolution"].module_key == STYLE_EXTRACTION_MODULE_KEY
    assert writer.calls[0]["candidate_batch_id"] == "style-extraction:style-run-1"
    assert writer.calls[0]["scope"] == "project"
    assert writer.calls[0]["candidates"] == [
        {
            "asset_type": "style_profile",
            "category": "writing_style",
            "title": "冷峻雨夜谈判风格",
            "summary": "短句、低照度意象和克制动作推动压迫感。",
            "tags": ["style", "noir"],
            "payload": {"diction": ["短句", "克制动词"], "rhythm": "紧凑"},
        }
    ]
    result_json = json.dumps(result, ensure_ascii=False)
    assert "作者文风" not in result_json
    assert "短句" not in result_json
    assert "sk-style" not in result_json


def test_llm_facility_style_extraction_runner_loads_private_source_asset_material() -> None:
    resolver = RecordingBindingResolver(_style_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-style")
    chat_client = RecordingJSONChatClient(
        response_json={
            "style_profile": {
                "title": "源资产风格",
                "summary": "从私有素材提取出的公开摘要。",
            }
        }
    )
    writer = RecordingCandidateAssetWriter()
    source_loader = RecordingStyleSourceMaterialLoader("源资产私有正文，不得进入公开结果。")
    runner = LLMFacilityStyleExtractionRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_writer=writer,
        source_material_loader=source_loader,
    )

    result = runner.extract_style(
        context=_style_context(),
        module_key=STYLE_EXTRACTION_MODULE_KEY,
        material_text=None,
        source_asset_id="asset-style-source-1",
        scope="project",
        options={},
    )

    assert result["status"] == "completed"
    assert source_loader.calls == [
        {"context": _style_context(), "source_asset_id": "asset-style-source-1"}
    ]
    user_message = json.loads(chat_client.calls[0]["messages"][1]["content"])
    assert user_message["material_text"] == "源资产私有正文，不得进入公开结果。"
    result_json = json.dumps(result, ensure_ascii=False)
    assert "源资产私有正文" not in result_json
    assert "sk-style" not in result_json


def test_llm_facility_style_extraction_runner_fails_closed_without_source_loader() -> None:
    resolver = RecordingBindingResolver(_style_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-style")
    chat_client = RecordingJSONChatClient(response_json={"style_profile": {"title": "unused", "summary": "unused"}})
    writer = RecordingCandidateAssetWriter()
    runner = LLMFacilityStyleExtractionRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_writer=writer,
    )

    result = runner.extract_style(
        context=_style_context(),
        module_key=STYLE_EXTRACTION_MODULE_KEY,
        material_text=None,
        source_asset_id="asset-style-source-1",
        scope="project",
        options={},
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "STYLE_SOURCE_MATERIAL_UNAVAILABLE"
    assert resolver.calls == []
    assert credentials.calls == []
    assert chat_client.calls == []
    assert writer.calls == []


def test_llm_facility_style_extraction_runner_fails_closed_on_invalid_schema() -> None:
    resolver = RecordingBindingResolver(_style_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-style")
    chat_client = RecordingJSONChatClient(response_json={"style_profile": {"title": "missing summary"}})
    writer = RecordingCandidateAssetWriter()
    runner = LLMFacilityStyleExtractionRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_writer=writer,
    )

    result = runner.extract_style(
        context=_style_context(),
        module_key=STYLE_EXTRACTION_MODULE_KEY,
        material_text="素材",
        source_asset_id=None,
        scope="project",
        options={},
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "SCHEMA_VALIDATION_FAILED"
    assert writer.calls == []


def test_postgres_style_source_material_loader_reads_tenant_project_scoped_content_text() -> None:
    connection = FakeStyleSourceMaterialConnection([{"content_text": "私有源资产正文"}])
    loader = PostgresStyleSourceMaterialLoader(connect=lambda: connection)

    material = loader.load_material(context=_style_context(), source_asset_id="asset-style-source-1")

    assert material == "私有源资产正文"
    query, params = connection.cursor_instance.executed[0]
    assert "FROM assets" in query
    assert "content_text" in query
    assert params == ("tenant-1", "project-1", "asset-style-source-1")
    assert connection.closed is True


def test_postgres_style_source_material_loader_fails_closed_for_missing_or_empty_asset() -> None:
    for rows in ([], [{"content_text": "   "}]):
        connection = FakeStyleSourceMaterialConnection(rows)
        loader = PostgresStyleSourceMaterialLoader(connect=lambda: connection)

        try:
            loader.load_material(context=_style_context(), source_asset_id="asset-style-source-1")
        except LLMFacilityError as exc:
            assert exc.code == "STYLE_SOURCE_MATERIAL_UNAVAILABLE"
        else:  # pragma: no cover - guard for explicit failure
            raise AssertionError("expected STYLE_SOURCE_MATERIAL_UNAVAILABLE")
        assert connection.closed is True


def test_llm_facility_asset_ingestion_runner_fails_closed_when_module_unbound() -> None:
    resolver = RecordingBindingResolver(
        LLMFacilityError("LLM_MODULE_UNBOUND", "asset_ingestion module is not bound")
    )
    credentials = RecordingCredentialProvider(api_key="sk-asset")
    chat_client = RecordingJSONChatClient(response_json={"candidates": []})
    writer = RecordingCandidateAssetWriter()
    runner = LLMFacilityAssetIngestionRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_writer=writer,
    )

    result = runner.ingest(
        context=_context(),
        module_key=ASSET_INGESTION_MODULE_KEY,
        material_text="素材",
        hint_type=None,
        scope="project",
        options={},
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "LLM_MODULE_UNBOUND"
    assert credentials.calls == []
    assert chat_client.calls == []
    assert writer.calls == []


def test_postgres_asset_candidate_writer_persists_candidate_assets_without_source_material_or_credentials() -> None:
    connection = FakeCandidateAssetConnection([{"asset_id": "asset-1"}, {"asset_id": "asset-2"}])
    writer = PostgresAssetCandidateWriter(connect=lambda: connection)

    result = writer.write_candidates(
        context=_context(),
        candidate_batch_id="asset-ingestion:run-1",
        model_id="model-asset",
        scope="project",
        candidates=[
            {
                "asset_type": "world_rule",
                "category": "world",
                "title": "灵气守恒",
                "summary": "灵气不可凭空生成，只能转化。",
                "tags": ["world", "rule"],
                "payload": {
                    "statement": "灵气只能从既有来源转化",
                    "material_text": "用户素材正文不得持久化",
                    "credential_ref": "secret-ref",
                },
            },
            {
                "asset_type": "note",
                "title": "雨夜谈判素材",
                "summary": "压迫感来自雨声与灯影。",
                "payload": {"api_key": "sk-secret", "detail": "只保留安全字段"},
            },
        ],
    )

    assert result == {
        "status": "completed",
        "candidate_batch_id": "asset-ingestion:run-1",
        "candidate_count": 2,
        "asset_type_counts": {"world_rule": 1, "note": 1},
    }
    assert len(connection.cursor_instance.executed) == 2
    assert all("INSERT INTO assets" in query for query, _params in connection.cursor_instance.executed)
    assert all("'candidate'" in query for query, _params in connection.cursor_instance.executed)
    joined_params = json.dumps(connection.cursor_instance.executed, ensure_ascii=False, default=str)
    assert "用户素材正文不得持久化" not in joined_params
    assert "credential_ref" not in joined_params
    assert "api_key" not in joined_params
    assert "sk-secret" not in joined_params
    assert "asset-ingestion:run-1" in joined_params
    assert connection.committed is True
    assert connection.closed is True


def test_postgres_asset_candidate_writer_can_persist_style_extraction_source_kind() -> None:
    connection = FakeCandidateAssetConnection([{"asset_id": "asset-style-1"}])
    writer = PostgresAssetCandidateWriter(connect=lambda: connection, source_kind="style_extraction")

    result = writer.write_candidates(
        context=_style_context(),
        candidate_batch_id="style-extraction:style-run-1",
        model_id="model-style",
        scope="project",
        candidates=[
            {
                "asset_type": "style_profile",
                "category": "writing_style",
                "title": "冷峻雨夜谈判风格",
                "summary": "短句、低照度意象和克制动作推动压迫感。",
                "payload": {"quotes": ["不得持久化样本文本"], "diction": ["短句"]},
            }
        ],
    )

    assert result["candidate_count"] == 1
    assert result["asset_type_counts"] == {"style_profile": 1}
    joined_params = json.dumps(connection.cursor_instance.executed, ensure_ascii=False, default=str)
    assert "style_extraction" in joined_params
    assert "style-extraction:style-run-1" in joined_params
    assert "不得持久化样本文本" not in joined_params
    assert connection.committed is True
    assert connection.closed is True


def test_local_asset_ingestion_workflow_runs_activity_with_runner() -> None:
    runner = RecordingAssetIngestionRunner(
        {
            "status": "completed",
            "candidate_batch_id": "asset-candidate-batch-1",
            "candidate_count": 1,
            "asset_type_counts": {"world_rule": 1},
        }
    )

    result = run_asset_ingestion_workflow_locally(_payload(), asset_ingestion_runner=runner)

    assert result["status"] == "completed"
    assert result["workflow_type"] == "asset_ingestion"
    assert result["candidate_batch_id"] == "asset-candidate-batch-1"


def test_asset_reindex_activity_fails_closed_without_reindexer() -> None:
    event_writer = RecordingWorkflowEventWriter()

    result = asset_reindex_activity(
        _asset_reindex_payload(),
        asset_reindexer=None,
        workflow_event_writer=event_writer,
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "ASSET_REINDEXER_UNCONFIGURED"
    assert result["module_key"] == ASSET_REINDEX_MODULE_KEY
    assert event_writer.events[-1]["event_type"] == "asset.stage.failed"
    joined_event = json.dumps(event_writer.events, ensure_ascii=False)
    for forbidden in ["raw novel text", "content_text", "search body", "embedding_chunk", "api_key", "credential_ref"]:
        assert forbidden not in joined_event


def test_asset_reindex_activity_runs_keyword_reindexer_with_sanitized_result() -> None:
    event_writer = RecordingWorkflowEventWriter()
    reindexer = RecordingAssetReindexer(
        {
            "status": "completed",
            "reindex_batch_id": "asset-reindex:run-asset-reindex-1",
            "asset_count": 2,
            "search_document_count": 2,
            "embedding_count": 0,
        }
    )

    result = run_asset_reindex_workflow_locally(
        _asset_reindex_payload(
            options={
                "include_disabled": False,
                "content": "raw novel text",
                "api_key": "sk-secret",
                "nested": {"prompt": "hidden"},
            }
        ),
        asset_reindexer=reindexer,
        workflow_event_writer=event_writer,
    )

    assert result["status"] == "completed"
    assert result["workflow_type"] == "asset_reindex"
    assert result["module_key"] == ASSET_REINDEX_MODULE_KEY
    assert result["reindex_batch_id"] == "asset-reindex:run-asset-reindex-1"
    assert result["asset_count"] == 2
    assert result["search_document_count"] == 2
    assert result["embedding_count"] == 0
    assert reindexer.calls[0]["context"].tenant_id == "tenant-1"
    assert reindexer.calls[0]["context"].project_id == "project-1"
    assert reindexer.calls[0]["context"].run_id == "run-asset-reindex-1"
    assert reindexer.calls[0]["scope"] == "project"
    assert reindexer.calls[0]["mode"] == "keyword"
    assert reindexer.calls[0]["options"] == {"include_disabled": False, "nested": {}}
    joined_result = json.dumps([result, event_writer.events], ensure_ascii=False)
    for forbidden in ["raw novel text", "content_text", "search body", "embedding_chunk", "api_key", "credential_ref"]:
        assert forbidden not in joined_result


def test_postgres_asset_reindexer_rebuilds_search_index_without_returning_body() -> None:
    connection = FakeCandidateAssetConnection([
        {
            "asset_count": 2,
            "search_document_count": 2,
            "embedding_count": 0,
        }
    ])
    reindexer = PostgresAssetReindexer(connect=lambda: connection)

    result = reindexer.reindex(
        context=_asset_reindex_context(),
        scope="project",
        mode="keyword",
        options={"include_disabled": False},
    )

    assert result["status"] == "completed"
    assert result["asset_count"] == 2
    assert result["search_document_count"] == 2
    assert result["embedding_count"] == 0
    assert result["reindex_batch_id"] == "asset-reindex:run-asset-reindex-1"
    query, params = connection.cursor_instance.executed[0]
    assert "INSERT INTO global_search_index" in query
    assert "content_text" in query
    assert params == ("tenant-1", "project-1", "run-asset-reindex-1", False)
    joined_result = json.dumps(result, ensure_ascii=False)
    for forbidden in ["content_text", "search body", "embedding_chunk", "raw novel text"]:
        assert forbidden not in joined_result
    assert connection.committed is True
    assert connection.closed is True


def test_asset_worker_spec_registers_temporal_workflow_and_activity() -> None:
    spec = worker_spec()

    assert spec["task_queue"] == ASSET_TASK_QUEUE
    assert "AssetIngestionWorkflow" in spec["workflows"]
    assert "asset_ingestion_activity" in spec["activities"]
    assert "StyleExtractionWorkflow" in spec["workflows"]
    assert "style_extraction_activity" in spec["activities"]
    assert "AssetReindexWorkflow" in spec["workflows"]
    assert "asset_reindex_activity" in spec["activities"]


def test_temporal_asset_worker_registers_asset_ingestion_activity() -> None:
    components = worker_components_for_task_queue(ASSET_TASK_QUEUE)

    assert [workflow.__name__ for workflow in components["workflows"]] == [
        "AssetIngestionWorkflow",
        "StyleExtractionWorkflow",
        "AssetReindexWorkflow",
    ]
    assert [activity.__name__ for activity in components["activities"]] == [
        "asset_ingestion_activity",
        "style_extraction_activity",
        "asset_reindex_activity",
    ]


def _resolution() -> ModuleBindingResolution:
    return ModuleBindingResolution(
        tenant_id="tenant-1",
        project_id="project-1",
        module_key=ASSET_INGESTION_MODULE_KEY,
        channel_id="channel-asset",
        model_id="model-asset",
        provider="openai-compatible",
        base_url="https://llm.example/v1",
        credential_ref="channel-asset",
        supports_json=True,
    )


def _style_resolution() -> ModuleBindingResolution:
    return ModuleBindingResolution(
        tenant_id="tenant-1",
        project_id="project-1",
        module_key=STYLE_EXTRACTION_MODULE_KEY,
        channel_id="channel-style",
        model_id="model-style",
        provider="openai-compatible",
        base_url="https://llm.example/v1",
        credential_ref="channel-style",
        supports_json=True,
    )


class RecordingStyleExtractionRunner:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def extract_style(
        self,
        *,
        context: AgentContext,
        module_key: str,
        material_text: str | None,
        source_asset_id: str | None,
        scope: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "context": context,
                "module_key": module_key,
                "material_text": material_text,
                "source_asset_id": source_asset_id,
                "scope": scope,
                "options": options,
            }
        )
        return self.result


class RecordingBindingResolver:
    def __init__(self, result: ModuleBindingResolution | LLMFacilityError) -> None:
        self.result = result
        self.calls: list[str] = []

    def resolve_module_binding(self, *, context: AgentContext, module_key: str) -> ModuleBindingResolution:
        self.calls.append(module_key)
        if isinstance(self.result, LLMFacilityError):
            raise self.result
        return self.result


class RecordingCredentialProvider:
    def __init__(self, api_key: str | None = None, error: LLMFacilityError | None = None) -> None:
        self.api_key = api_key
        self.error = error
        self.calls: list[str] = []

    def resolve_api_key(self, *, context: AgentContext, credential_ref: str) -> str:
        self.calls.append(credential_ref)
        if self.error is not None:
            raise self.error
        return self.api_key or ""


class RecordingJSONChatClient:
    def __init__(self, response_json: dict[str, Any]) -> None:
        self.response_json = response_json
        self.calls: list[dict[str, Any]] = []

    def complete_json(
        self,
        *,
        context: AgentContext,
        resolution: ModuleBindingResolution,
        api_key: str,
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "context": context,
                "resolution": resolution,
                "api_key": api_key,
                "messages": messages,
            }
        )
        return self.response_json


class RecordingCandidateAssetWriter:
    def __init__(self, error: LLMFacilityError | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def write_candidates(
        self,
        *,
        context: AgentContext,
        candidate_batch_id: str,
        model_id: str | None,
        scope: str,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "context": context,
                "candidate_batch_id": candidate_batch_id,
                "model_id": model_id,
                "scope": scope,
                "candidates": candidates,
            }
        )
        if self.error is not None:
            raise self.error
        counts: dict[str, int] = {}
        for candidate in candidates:
            asset_type = candidate["asset_type"]
            counts[asset_type] = counts.get(asset_type, 0) + 1
        return {
            "status": "completed",
            "candidate_batch_id": candidate_batch_id,
            "candidate_count": len(candidates),
            "asset_type_counts": counts,
        }


class RecordingStyleSourceMaterialLoader:
    def __init__(self, material_text: str | LLMFacilityError) -> None:
        self.material_text = material_text
        self.calls: list[dict[str, Any]] = []

    def load_material(self, *, context: AgentContext, source_asset_id: str) -> str:
        self.calls.append({"context": context, "source_asset_id": source_asset_id})
        if isinstance(self.material_text, LLMFacilityError):
            raise self.material_text
        return self.material_text


class FakeCandidateAssetCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, query: str, params: tuple[Any, ...]) -> None:
        self.executed.append((query, params))

    def fetchone(self) -> dict[str, Any] | None:
        if not self.rows:
            return None
        return self.rows.pop(0)

    def __enter__(self) -> "FakeCandidateAssetCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class FakeCandidateAssetConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.cursor_instance = FakeCandidateAssetCursor(rows)
        self.committed = False
        self.closed = False

    def cursor(self) -> FakeCandidateAssetCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True


class FakeStyleSourceMaterialCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, query: str, params: tuple[Any, ...]) -> None:
        self.executed.append((query, params))

    def fetchone(self) -> dict[str, Any] | None:
        if not self.rows:
            return None
        return self.rows.pop(0)

    def __enter__(self) -> "FakeStyleSourceMaterialCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class FakeStyleSourceMaterialConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.cursor_instance = FakeStyleSourceMaterialCursor(rows)
        self.closed = False

    def cursor(self) -> FakeStyleSourceMaterialCursor:
        return self.cursor_instance

    def close(self) -> None:
        self.closed = True
