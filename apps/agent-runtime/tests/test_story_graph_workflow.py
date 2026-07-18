from __future__ import annotations

import json
from typing import Any

from mirofish_agents.common.context import AgentContext
from mirofish_agents.temporal.graph import (
    GRAPH_BOND_GENERATION_MODULE_KEY,
    GRAPH_TASK_QUEUE,
    PostgresGraphBondCandidateWriter,
    PostgresStoryGraphBuilder,
    PostgresWorkflowRunStatusWriter,
    STORY_GRAPH_BUILD_MODULE_KEY,
    _assign_graph_clusters,
    _deterministic_cluster_layout,
    _entity_name_index,
    _merge_entity_nodes,
    _story_graph_builder_from_env,
    graph_bond_generation_activity,
    story_graph_build_activity,
    worker_spec,
)
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


class RecordingWorkflowRunStatusWriter:
    def __init__(self) -> None:
        self.completed: list[dict[str, Any]] = []
        self.failed: list[dict[str, Any]] = []

    def mark_completed(
        self,
        *,
        context: AgentContext,
        result: dict[str, Any],
    ) -> None:
        self.completed.append({"context": context, "result": result})

    def mark_failed(
        self,
        *,
        context: AgentContext,
        code: str,
        message: str,
    ) -> None:
        self.failed.append({"context": context, "code": code, "message": message})


class RecordingStoryGraphBuilder:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def build(
        self,
        *,
        context: AgentContext,
        mode: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append({"context": context, "mode": mode, "options": options})
        return self.result


class RecordingBindingResolver:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def resolve_module_binding(self, *, context: AgentContext, module_key: str) -> Any:
        self.calls.append({"context": context, "module_key": module_key})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class RecordingCredentialProvider:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.calls: list[dict[str, Any]] = []

    def resolve_api_key(self, *, context: AgentContext, credential_ref: str) -> str:
        self.calls.append({"context": context, "credential_ref": credential_ref})
        return self.api_key


class RecordingJSONChatClient:
    def __init__(self, response_json: dict[str, Any]) -> None:
        self.response_json = response_json
        self.calls: list[dict[str, Any]] = []

    def complete_json(
        self,
        *,
        context: AgentContext,
        resolution: Any,
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


class RecordingGraphBondCandidateWriter:
    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.result = result or {}
        self.calls: list[dict[str, Any]] = []

    def write_candidates(
        self,
        *,
        context: AgentContext,
        candidate_batch_id: str,
        model_id: str | None,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "context": context,
                "candidate_batch_id": candidate_batch_id,
                "model_id": model_id,
                "candidates": candidates,
            }
        )
        return self.result


class RecordingGraphBondRunner:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        *,
        context: AgentContext,
        graph_id: str | None,
        node_ids: list[str],
        focus: str | None,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append({"context": context, "graph_id": graph_id, "node_ids": node_ids, "focus": focus, "options": options})
        return self.result


def _context() -> AgentContext:
    return AgentContext(
        tenant_id="tenant-1",
        project_id="project-1",
        run_id="run-story-graph-1",
        workflow_type="story_graph_build",
        actor_user_id="user-1",
        module_key=STORY_GRAPH_BUILD_MODULE_KEY,
        trace_id="trace-story-graph-1",
        permissions={STORY_GRAPH_BUILD_MODULE_KEY: ["run"]},
    )


def _payload(options: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "context": _context().model_dump(),
        "tenant_id": "tenant-1",
        "project_id": "project-1",
        "run_id": "run-story-graph-1",
        "workflow_type": "story_graph_build",
        "trace_id": "trace-story-graph-1",
        "mode": "full",
        "options": options or {},
    }


def _bond_context() -> AgentContext:
    return AgentContext(
        tenant_id="tenant-1",
        project_id="project-1",
        run_id="run-story-graph-bond-1",
        workflow_type="story_graph_bond_generation",
        actor_user_id="user-1",
        module_key=GRAPH_BOND_GENERATION_MODULE_KEY,
        trace_id="trace-story-graph-bond-1",
        permissions={GRAPH_BOND_GENERATION_MODULE_KEY: ["run"]},
    )


def _bond_payload(options: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "context": _bond_context().model_dump(),
        "tenant_id": "tenant-1",
        "project_id": "project-1",
        "run_id": "run-story-graph-bond-1",
        "workflow_type": "story_graph_bond_generation",
        "trace_id": "trace-story-graph-bond-1",
        "module_key": GRAPH_BOND_GENERATION_MODULE_KEY,
        "graph_id": "graph-1",
        "node_ids": ["node-1", "node-2"],
        "focus": "rain treaty",
        "options": options or {},
    }


def test_story_graph_build_activity_fails_closed_without_builder() -> None:
    writer = RecordingWorkflowEventWriter()

    result = story_graph_build_activity(
        _payload({"source": "seed_canon", "prompt": "hidden"}),
        graph_builder=None,
        workflow_event_writer=writer,
    )

    assert result["status"] == "failed"
    assert result["workflow_type"] == "story_graph_build"
    assert result["module_key"] == STORY_GRAPH_BUILD_MODULE_KEY
    assert result["error"]["code"] == "STORY_GRAPH_BUILDER_UNCONFIGURED"
    assert writer.events[0]["event_type"] == "graph.stage.failed"
    assert writer.events[0]["payload"]["stage"] == "story_graph_build"
    joined = json.dumps([result, writer.events], ensure_ascii=False)
    for forbidden in ["prompt", "response", "body", "content", "raw_text", "snippet", "credential_ref", "api_key"]:
        assert forbidden not in joined


def test_graph_bond_generation_activity_fails_closed_without_runner() -> None:
    writer = RecordingWorkflowEventWriter()

    result = graph_bond_generation_activity(
        _bond_payload({"generate_bonds": True, "prompt": "hidden", "nested": {"content": "secret"}}),
        bond_runner=None,
        workflow_event_writer=writer,
    )

    assert result["status"] == "failed"
    assert result["workflow_type"] == "story_graph_bond_generation"
    assert result["module_key"] == GRAPH_BOND_GENERATION_MODULE_KEY
    assert result["error"]["code"] == "GRAPH_BOND_RUNNER_UNCONFIGURED"
    assert writer.events[0]["event_type"] == "graph.stage.failed"
    assert writer.events[0]["payload"]["stage"] == "graph_bond_generation"
    joined = json.dumps([result, writer.events], ensure_ascii=False)
    for forbidden in [
        "prompt",
        "hidden",
        "secret",
        "response",
        "body",
        "content",
        "raw_text",
        "snippet",
        "credential_ref",
        "api_key",
        "node-1",
        "node-2",
        "rain treaty",
    ]:
        assert forbidden not in joined


def test_graph_bond_generation_activity_requires_module_permission() -> None:
    writer = RecordingWorkflowEventWriter()
    payload = _bond_payload()
    payload["context"] = _bond_context().model_copy(update={"permissions": {}}).model_dump()

    result = graph_bond_generation_activity(payload, bond_runner=None, workflow_event_writer=writer)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "FORBIDDEN"
    assert writer.events[0]["payload"]["error_code"] == "FORBIDDEN"


def test_graph_bond_generation_activity_requires_admitted_bond_workflow_context() -> None:
    cases = [
        (
            "workflow_type",
            _bond_context().model_copy(update={"workflow_type": "story_graph_build"}).model_dump(),
            "workflow_type must be story_graph_bond_generation",
        ),
        (
            "project_id",
            _bond_context().model_copy(update={"project_id": None}).model_dump(),
            "project_id is required",
        ),
        (
            "module_key",
            _bond_context().model_copy(update={"module_key": None}).model_dump(),
            f"module_key must be {GRAPH_BOND_GENERATION_MODULE_KEY}",
        ),
    ]

    for field_name, context_payload, expected_message in cases:
        writer = RecordingWorkflowEventWriter()
        status_writer = RecordingWorkflowRunStatusWriter()
        payload = _bond_payload()
        payload["context"] = context_payload

        result = graph_bond_generation_activity(
            payload,
            bond_runner=RecordingGraphBondRunner({"status": "completed"}),
            workflow_event_writer=writer,
            workflow_status_writer=status_writer,
        )

        assert result["status"] == "failed", field_name
        assert result["error"]["code"] == "VALIDATION_FAILED", field_name
        assert result["error"]["message"] == expected_message
        assert status_writer.completed == []
        assert status_writer.failed[-1]["code"] == "VALIDATION_FAILED"
        assert writer.events[-1]["event_type"] == "graph.stage.failed"


def test_graph_bond_generation_activity_marks_failed_when_runner_returns_failed_status() -> None:
    writer = RecordingWorkflowEventWriter()
    status_writer = RecordingWorkflowRunStatusWriter()
    runner = RecordingGraphBondRunner(
        {
            "status": "failed",
            "module_key": GRAPH_BOND_GENERATION_MODULE_KEY,
            "error": {"code": "SCHEMA_VALIDATION_FAILED", "message": "unsafe graph bond output"},
            "candidate_batch_id": "graph-bond:run-story-graph-bond-1",
        }
    )

    result = graph_bond_generation_activity(
        _bond_payload(),
        bond_runner=runner,
        workflow_event_writer=writer,
        workflow_status_writer=status_writer,
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "SCHEMA_VALIDATION_FAILED"
    assert status_writer.completed == []
    assert status_writer.failed == [
        {
            "context": _bond_context(),
            "code": "SCHEMA_VALIDATION_FAILED",
            "message": "unsafe graph bond output",
        }
    ]
    assert writer.events[-1]["event_type"] == "graph.stage.failed"
    joined = json.dumps([result, writer.events, status_writer.failed], ensure_ascii=False, default=str)
    assert "candidate_batch_id" not in joined
    assert "graph.stage.completed" not in joined


def test_llm_facility_graph_bond_runner_persists_schema_valid_candidate_metadata_without_public_secrets() -> None:
    from mirofish_agents.temporal import graph as graph_module
    from mirofish_agents.seed.sequential_reader import ModuleBindingResolution

    LLMFacilityGraphBondGenerationRunner = getattr(graph_module, "LLMFacilityGraphBondGenerationRunner")
    resolution = ModuleBindingResolution(
        tenant_id="tenant-1",
        project_id="project-1",
        module_key=GRAPH_BOND_GENERATION_MODULE_KEY,
        channel_id="channel-1",
        model_id="model-graph",
        provider="openai-compatible",
        base_url="https://llm.example/v1",
        credential_ref="channel-1",
        supports_json=True,
        settings={"temperature": 0.3},
    )
    resolver = RecordingBindingResolver(resolution)
    credentials = RecordingCredentialProvider(api_key="sk-graph-secret")
    chat_client = RecordingJSONChatClient(
        {
            "bonds": [
                {
                    "title": "雨约同盟",
                    "summary": "两名角色在雨夜密约中形成互相制衡的短期同盟。",
                    "source_entity_name": "Ari",
                    "target_entity_name": "Bryn",
                    "relationship_type": "alliance",
                    "kind": "alliance",
                    "confidence": 0.82,
                    "node_ids": ["node-1", "node-2"],
                    "selected_node_ids": ["node-1", "node-2"],
                    "selectedNodeIds": ["node-1", "node-2"],
                    "involved_node_ids": ["node-1", "node-2"],
                    "evidence_assumptions": [
                        {"summary": "共同目标来自公开图谱关系，而不是原文片段。", "snippet": "不得持久化"}
                    ],
                    "prompt": "不得持久化",
                }
            ],
            "plot_threads": [
                {
                    "title": "白塔反制线",
                    "summary": "组织开始利用同盟裂缝设置反制支线。",
                    "thread_type": "subplot",
                    "body": "不得持久化",
                }
            ],
            "conflict_triggers": [
                {
                    "title": "信物失窃",
                    "summary": "关键物件失踪触发两方互疑。",
                    "trigger_type": "artifact_loss",
                    "credential_ref": "secret-ref",
                }
            ],
        }
    )
    candidate_writer = RecordingGraphBondCandidateWriter(
        {
            "candidate_count": 3,
            "bond_candidate_count": 1,
            "plot_thread_candidate_count": 1,
            "conflict_trigger_count": 1,
        }
    )
    runner = LLMFacilityGraphBondGenerationRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_writer=candidate_writer,
    )

    result = runner.generate(
        context=_bond_context(),
        graph_id="graph-1",
        node_ids=["node-1", "node-2"],
        focus="rain treaty with raw focus text",
        options={"mode": "bonds_and_threads", "prompt": "remove me"},
    )

    assert result == {
        "status": "completed",
        "module_key": GRAPH_BOND_GENERATION_MODULE_KEY,
        "model_id": "model-graph",
        "candidate_batch_id": "graph-bond:run-story-graph-bond-1",
        "candidate_count": 3,
        "bond_candidate_count": 1,
        "plot_thread_candidate_count": 1,
        "conflict_trigger_count": 1,
    }
    assert resolver.calls[0]["module_key"] == GRAPH_BOND_GENERATION_MODULE_KEY
    assert credentials.calls[0]["credential_ref"] == "channel-1"
    assert chat_client.calls[0]["api_key"] == "sk-graph-secret"
    assert candidate_writer.calls[0]["candidate_batch_id"] == "graph-bond:run-story-graph-bond-1"
    persisted_candidates = candidate_writer.calls[0]["candidates"]
    assert [candidate["asset_type"] for candidate in persisted_candidates] == [
        "graph_bond",
        "plot_thread",
        "conflict_trigger",
    ]
    assert persisted_candidates[0]["payload"]["source_entity_name"] == "Ari"
    assert persisted_candidates[0]["payload"]["target_entity_name"] == "Bryn"
    assert persisted_candidates[0]["payload"]["relationship_type"] == "alliance"
    joined_public = json.dumps([result, candidate_writer.calls], ensure_ascii=False, default=str)
    for forbidden in [
        "sk-graph-secret",
        "credential_ref",
        "secret-ref",
        "prompt",
        "remove me",
        "不得持久化",
        "rain treaty with raw focus text",
        "node-1",
        "node-2",
    ]:
        assert forbidden not in joined_public


def test_llm_facility_graph_bond_runner_rejects_sensitive_candidate_values_before_persistence() -> None:
    from mirofish_agents.temporal import graph as graph_module
    from mirofish_agents.seed.sequential_reader import ModuleBindingResolution

    LLMFacilityGraphBondGenerationRunner = getattr(graph_module, "LLMFacilityGraphBondGenerationRunner")
    resolution = ModuleBindingResolution(
        tenant_id="tenant-1",
        project_id="project-1",
        module_key=GRAPH_BOND_GENERATION_MODULE_KEY,
        channel_id="channel-1",
        model_id="model-graph",
        provider="openai-compatible",
        base_url="https://llm.example/v1",
        credential_ref="channel-1",
        supports_json=True,
        settings={"temperature": 0.3},
    )
    candidate_writer = RecordingGraphBondCandidateWriter()
    runner = LLMFacilityGraphBondGenerationRunner(
        binding_resolver=RecordingBindingResolver(resolution),
        credential_provider=RecordingCredentialProvider(api_key="sk-graph-secret"),
        chat_client=RecordingJSONChatClient(
            {
                "bonds": [
                    {
                        "title": "雨约同盟 node-1",
                        "summary": "rain treaty with raw focus text",
                        "kind": "alliance",
                        "tags": ["story_graph", "sk-live-secret"],
                        "notes": "selected ids node-1 node-2 and prompt: leak this",
                    }
                ]
            }
        ),
        candidate_writer=candidate_writer,
    )

    result = runner.generate(
        context=_bond_context(),
        graph_id="graph-1",
        node_ids=["node-1", "node-2"],
        focus="rain treaty with raw focus text",
        options={},
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "SCHEMA_VALIDATION_FAILED"
    assert candidate_writer.calls == []
    joined = json.dumps(result, ensure_ascii=False)
    for forbidden in ["node-1", "node-2", "rain treaty with raw focus text", "sk-live-secret", "prompt: leak this"]:
        assert forbidden not in joined


def test_llm_facility_graph_bond_runner_requires_relationship_fields_before_persistence() -> None:
    from mirofish_agents.temporal import graph as graph_module
    from mirofish_agents.seed.sequential_reader import ModuleBindingResolution

    LLMFacilityGraphBondGenerationRunner = getattr(graph_module, "LLMFacilityGraphBondGenerationRunner")
    resolution = ModuleBindingResolution(
        tenant_id="tenant-1",
        project_id="project-1",
        module_key=GRAPH_BOND_GENERATION_MODULE_KEY,
        channel_id="channel-1",
        model_id="model-graph",
        provider="openai-compatible",
        base_url="https://llm.example/v1",
        credential_ref="channel-1",
        supports_json=True,
        settings={"temperature": 0.3},
    )
    candidate_writer = RecordingGraphBondCandidateWriter()
    runner = LLMFacilityGraphBondGenerationRunner(
        binding_resolver=RecordingBindingResolver(resolution),
        credential_provider=RecordingCredentialProvider(api_key="sk-graph-secret"),
        chat_client=RecordingJSONChatClient(
            {
                "bonds": [
                    {
                        "title": "雨约同盟",
                        "summary": "两名角色形成短期同盟。",
                        "kind": "alliance",
                    }
                ]
            }
        ),
        candidate_writer=candidate_writer,
    )

    result = runner.generate(
        context=_bond_context(),
        graph_id="graph-1",
        node_ids=["node-1", "node-2"],
        focus=None,
        options={},
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "SCHEMA_VALIDATION_FAILED"
    assert candidate_writer.calls == []
    joined = json.dumps(result, ensure_ascii=False)
    for forbidden in ["sk-graph-secret", "node-1", "node-2", "prompt"]:
        assert forbidden not in joined


def test_postgres_graph_bond_candidate_writer_persists_candidate_assets_without_public_node_ids_or_credentials() -> None:
    connection = FakeStoryGraphConnection({})
    writer = PostgresGraphBondCandidateWriter(connect=lambda: connection)
    context = _bond_context().model_copy(
        update={
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "actor_user_id": "22222222-2222-2222-2222-222222222222",
        }
    )

    result = writer.write_candidates(
        context=context,
        candidate_batch_id="graph-bond:run-story-graph-bond-1",
        model_id="model-graph",
        candidates=[
            {
                "asset_type": "graph_bond",
                "category": "relationship",
                "title": "雨约同盟",
                "summary": "两名角色在雨夜密约中形成互相制衡的短期同盟。",
                "tags": ["story_graph", "graph_bond"],
                "payload": {
                    "proposal_type": "graph_bond",
                    "source_entity_name": "Ari",
                    "target_entity_name": "Bryn",
                    "relationship_type": "alliance",
                    "kind": "alliance",
                    "node_ids": ["node-1", "node-2"],
                    "prompt": "hidden prompt",
                    "credential_ref": "secret-ref",
                    "evidence_assumptions": [{"summary": "公开假设", "snippet": "hidden evidence"}],
                },
            },
            {
                "asset_type": "plot_thread",
                "category": "plot",
                "title": "白塔反制线",
                "summary": "组织开始利用同盟裂缝设置反制支线。",
                "tags": ["story_graph", "plot_thread"],
                "payload": {"proposal_type": "plot_thread"},
            },
        ],
    )

    assert result == {
        "status": "completed",
        "candidate_batch_id": "graph-bond:run-story-graph-bond-1",
        "candidate_count": 2,
        "bond_candidate_count": 1,
        "plot_thread_candidate_count": 1,
        "conflict_trigger_count": 0,
    }
    executed_sql = "\n".join(query for query, _params in connection.cursor_instance.executed)
    assert "app_set_tenant_context" in executed_sql
    assert "INSERT INTO assets" in executed_sql
    assert "'candidate'" in executed_sql
    joined_params = json.dumps(connection.cursor_instance.executed, ensure_ascii=False, default=str)
    assert "graph_bond_generation" in joined_params
    assert "graph-bond:run-story-graph-bond-1" in joined_params
    assert "Ari" in joined_params
    assert "Bryn" in joined_params
    assert "alliance" in joined_params
    for forbidden in [
        "node-1",
        "node-2",
        "hidden prompt",
        "credential_ref",
        "secret-ref",
        "hidden evidence",
    ]:
        assert forbidden not in joined_params
    assert connection.committed is True
    assert connection.closed is True


def test_postgres_graph_bond_candidate_writer_scrubs_sensitive_candidate_values_in_safe_looking_fields() -> None:
    connection = FakeStoryGraphConnection({})
    writer = PostgresGraphBondCandidateWriter(connect=lambda: connection)
    context = _bond_context().model_copy(
        update={
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "actor_user_id": "22222222-2222-2222-2222-222222222222",
        }
    )

    result = writer.write_candidates(
        context=context,
        candidate_batch_id="graph-bond:run-story-graph-bond-1",
        model_id="model-graph",
        candidates=[
            {
                "asset_type": "graph_bond",
                "category": "relationship",
                "title": "雨约同盟",
                "summary": "公开摘要",
                "tags": ["story_graph", "node-1", "sk-live-secret"],
                "payload": {
                    "proposal_type": "graph_bond",
                    "kind": "alliance",
                    "notes": "node-1 node-2 should not persist",
                    "public_hint": "prompt: reveal hidden chain",
                    "summary_hint": "公开非敏感标签",
                },
            }
        ],
    )

    assert result["status"] == "completed"
    joined_params = json.dumps(connection.cursor_instance.executed, ensure_ascii=False, default=str)
    assert "公开非敏感标签" in joined_params
    for forbidden in ["node-1", "node-2", "sk-live-secret", "prompt: reveal hidden chain"]:
        assert forbidden not in joined_params


def test_story_graph_build_activity_marks_workflow_run_failed_without_builder() -> None:
    writer = RecordingWorkflowEventWriter()
    status_writer = RecordingWorkflowRunStatusWriter()

    result = story_graph_build_activity(
        _payload({"prompt": "hidden"}),
        graph_builder=None,
        workflow_event_writer=writer,
        workflow_status_writer=status_writer,
    )

    assert result["status"] == "failed"
    assert result["workflow_status_persisted"] is True
    assert status_writer.failed == [
        {
            "context": _context(),
            "code": "STORY_GRAPH_BUILDER_UNCONFIGURED",
            "message": "story graph builder requires DB-backed canon source configuration",
        }
    ]
    joined = json.dumps([result, status_writer.failed, writer.events], ensure_ascii=False, default=str)
    assert "prompt" not in joined
    assert "hidden" not in joined


def test_story_graph_build_activity_marks_workflow_run_completed_with_public_result() -> None:
    writer = RecordingWorkflowEventWriter()
    status_writer = RecordingWorkflowRunStatusWriter()
    builder = RecordingStoryGraphBuilder(
        {
            "status": "completed",
            "graph_id": "graph-1",
            "node_count": 2,
            "edge_count": 1,
            "layout_count": 1,
            "cluster_count": 1,
            "body": "hidden body",
            "api_key": "sk-hidden",
        }
    )

    result = story_graph_build_activity(
        _payload({"prompt": "hidden"}),
        graph_builder=builder,
        workflow_event_writer=writer,
        workflow_status_writer=status_writer,
    )

    assert result["status"] == "completed"
    assert result["workflow_status_persisted"] is True
    assert status_writer.completed == [
        {
            "context": _context(),
            "result": {
                "graph_id": "graph-1",
                "node_count": 2,
                "edge_count": 1,
                "layout_count": 1,
                "cluster_count": 1,
            },
        }
    ]
    assert status_writer.failed == []
    assert writer.events[-1]["event_type"] == "graph.stage.completed"
    joined = json.dumps([result, status_writer.completed, writer.events], ensure_ascii=False, default=str)
    for forbidden in ["prompt", "hidden body", "api_key", "sk-hidden"]:
        assert forbidden not in joined


def test_postgres_story_graph_builder_requires_project_context() -> None:
    builder = PostgresStoryGraphBuilder(connect=lambda: FakeStoryGraphConnection({}))
    context = _context().model_copy(update={"project_id": None})

    try:
        builder.build(context=context, mode="full", options={})
    except ValueError as exc:
        assert "project_id" in str(exc)
    else:  # pragma: no cover - guard for explicit failure
        raise AssertionError("expected project_id validation failure")


def test_postgres_workflow_run_status_writer_updates_workflow_runs_with_sanitized_result() -> None:
    connection = FakeWorkflowStatusConnection([{"workflow_updated": "1"}])
    writer = PostgresWorkflowRunStatusWriter(connect=lambda: connection)

    writer.mark_completed(
        context=_context(),
        result={
            "graph_id": "graph-1",
            "node_count": 2,
            "edge_count": 1,
            "layout_count": 1,
            "cluster_count": 1,
            "body": "hidden body",
            "api_key": "sk-hidden",
        },
    )

    query, params = connection.cursor_instance.executed[0]
    assert "UPDATE workflow_runs" in query
    assert params[0] == "completed"
    assert params[1] == "completed"
    assert "story graph ready" in params[2]
    assert params[-4:] == ("tenant-1", "project-1", "run-story-graph-1", "story_graph_build")
    joined = json.dumps(params, ensure_ascii=False)
    assert "graph-1" in joined
    assert "hidden body" not in joined
    assert "api_key" not in joined
    assert "sk-hidden" not in joined
    assert connection.committed is True
    assert connection.closed is True


def test_postgres_workflow_run_status_writer_sets_app_role_tenant_context() -> None:
    connection = FakeWorkflowStatusConnection([{"workflow_updated": "1"}])
    writer = PostgresWorkflowRunStatusWriter(connect=lambda: connection)
    context = _context().model_copy(
        update={
            "tenant_id": "11111111-1111-4111-8111-111111111111",
            "project_id": "22222222-2222-4222-8222-222222222222",
            "run_id": "33333333-3333-4333-8333-333333333333",
            "actor_user_id": "44444444-4444-4444-8444-444444444444",
        }
    )

    writer.mark_completed(context=context, result={"graph_id": "graph-1", "node_count": 2})

    assert len(connection.cursor_instance.executed) == 2
    context_query, context_params = connection.cursor_instance.executed[0]
    update_query, update_params = connection.cursor_instance.executed[1]
    assert "app_set_tenant_context" in context_query
    assert context_params == (context.tenant_id, context.actor_user_id)
    assert "UPDATE workflow_runs" in update_query
    assert update_params[-4:] == (context.tenant_id, context.project_id, context.run_id, context.workflow_type)
    assert connection.committed is True
    assert connection.closed is True


def test_postgres_workflow_run_status_writer_describes_completed_graph_bond_generation() -> None:
    connection = FakeWorkflowStatusConnection([{"workflow_updated": "1"}])
    writer = PostgresWorkflowRunStatusWriter(connect=lambda: connection)

    writer.mark_completed(
        context=_bond_context(),
        result={
            "candidate_batch_id": "graph-bond:run-story-graph-bond-1",
            "candidate_count": 4,
            "bond_candidate_count": 2,
            "plot_thread_candidate_count": 1,
            "conflict_trigger_count": 1,
            "body": "hidden body",
            "api_key": "sk-hidden",
        },
    )

    query, params = connection.cursor_instance.executed[0]
    assert "UPDATE workflow_runs" in query
    assert params[0] == "completed"
    assert params[1] == "completed"
    assert params[2] == "graph bond candidates ready: 4 candidates, 2 bonds, 1 threads, 1 triggers"
    assert params[-4:] == (
        "tenant-1",
        "project-1",
        "run-story-graph-bond-1",
        "story_graph_bond_generation",
    )
    joined = json.dumps(params, ensure_ascii=False)
    assert "graph-bond:run-story-graph-bond-1" in joined
    assert "hidden body" not in joined
    assert "api_key" not in joined
    assert "sk-hidden" not in joined
    assert connection.committed is True
    assert connection.closed is True


def test_postgres_workflow_run_status_writer_updates_bond_workflow_type_for_failed_runs() -> None:
    connection = FakeWorkflowStatusConnection([{"workflow_updated": "1"}])
    writer = PostgresWorkflowRunStatusWriter(connect=lambda: connection)

    writer.mark_failed(
        context=_bond_context(),
        code="SCHEMA_VALIDATION_FAILED",
        message="graph bond generation failed",
    )

    query, params = connection.cursor_instance.executed[0]
    assert "UPDATE workflow_runs" in query
    assert "workflow_type = %s" in query
    assert "workflow_type = 'story_graph_build'" not in query
    assert params[-4:] == (
        "tenant-1",
        "project-1",
        "run-story-graph-bond-1",
        "story_graph_bond_generation",
    )
    assert connection.committed is True
    assert connection.closed is True


def test_postgres_story_graph_builder_persists_snapshot_nodes_edges_evidence_layout_and_clusters() -> None:
    rows = {
        "fetch_entities": [
            {
                "entity_id": "entity-a",
                "canonical_name": "林澈",
                "entity_type": "character",
                "importance": "high",
                "state_summary": "雨夜谈判者。",
                "first_seen_segment_id": "segment-1",
                "metadata_jsonb": {"body": "hidden raw body", "role": "protagonist"},
            },
            {
                "entity_id": "entity-b",
                "canonical_name": "白塔会",
                "entity_type": "organization",
                "importance": "medium",
                "state_summary": "秘密组织。",
                "first_seen_segment_id": "segment-2",
                "metadata_jsonb": {"api_key": "sk-hidden", "alignment": "rival"},
            },
        ],
        "fetch_aliases": [
            {"entity_id": "entity-a", "alias": "小林"},
            {"entity_id": "entity-b", "alias": "白塔"},
        ],
        "fetch_labels": [
            {"entity_id": "entity-a", "label": "主角", "label_type": "role"},
            {"entity_id": "entity-b", "label": "势力", "label_type": "kind"},
        ],
        "fetch_relationships": [
            {
                "relationship_id": "relationship-1",
                "source_entity_name": "林澈",
                "target_entity_name": "白塔会",
                "relationship_type": "opposes",
                "summary": "林澈调查白塔会。",
                "first_seen_segment_id": "segment-3",
                "evidence_text": "这段关系原文不得出现在公开结果。",
                "metadata_jsonb": {"prompt": "hidden"},
            }
        ],
        "fetch_plot_threads": [
            {
                "thread_id": "thread-1",
                "title": "雨夜密约",
                "status": "open",
                "summary": "主线冲突开始收束。",
                "first_seen_segment_id": "segment-4",
                "evidence_text": "伏笔原文不得公开。",
                "metadata_jsonb": {"content": "hidden"},
            }
        ],
        "fetch_world_rules": [
            {
                "rule_evidence_id": "rule-1",
                "rule_text": "灵气守恒",
                "category": "magic",
                "confidence": 0.9,
                "segment_id": "segment-5",
                "evidence_text": "规则原文不得公开。",
                "metadata_jsonb": {"snippet": "hidden"},
            }
        ],
        "fetch_assets": [
            {
                "asset_id": "asset-1",
                "asset_type": "archive_entity",
                "category": "archive",
                "lifecycle": "canon",
                "title": "林澈档案",
                "summary": "可公开摘要。",
                "payload_jsonb": {"content_text": "hidden", "tier": "major"},
                "tags_jsonb": ["archive"],
            }
        ],
        "fetch_version": [{"next_version": 7}],
    }
    connection = FakeStoryGraphConnection(rows)
    builder = PostgresStoryGraphBuilder(connect=lambda: connection)

    result = builder.build(
        context=_context(),
        mode="full",
        options={"prompt": "remove me", "view_id": "world"},
    )

    assert result["status"] == "completed"
    assert result["graph_id"]
    assert result["node_count"] == 5
    assert result["edge_count"] == 1
    assert result["layout_count"] == 1
    assert result["cluster_count"] >= 1
    executed_sql = "\n".join(query for query, _params in connection.cursor_instance.executed)
    for table_name in [
        "story_graph_snapshots",
        "story_graph_nodes",
        "story_graph_edges",
        "story_graph_evidence",
        "story_graph_layouts",
        "story_graph_clusters",
    ]:
        assert table_name in executed_sql
    executed_params = [params for _query, params in connection.cursor_instance.executed]
    joined = json.dumps([result, executed_params], ensure_ascii=False, default=str)
    for forbidden in [
        "这段关系原文",
        "伏笔原文",
        "规则原文",
        "hidden raw body",
        "content_text",
        "prompt",
        "api_key",
        "snippet",
        "credential_ref",
    ]:
        assert forbidden not in joined
    assert connection.committed is True
    assert connection.closed is True


def test_postgres_story_graph_builder_builds_from_selected_analysis_assets() -> None:
    rows = {
        "fetch_assets": [
            {
                "asset_id": "asset-character-1",
                "asset_type": "character",
                "category": "characters",
                "lifecycle": "material",
                "title": "林澈",
                "summary": "雨夜谈判者。",
                "payload_jsonb": {"name": "林澈"},
                "tags_jsonb": ["pi_analysis", "character"],
            },
            {
                "asset_id": "asset-character-2",
                "asset_type": "character",
                "category": "characters",
                "lifecycle": "material",
                "title": "白塔会",
                "summary": "秘密组织。",
                "payload_jsonb": {"name": "白塔会"},
                "tags_jsonb": ["pi_analysis", "character"],
            },
            {
                "asset_id": "asset-relationship-1",
                "asset_type": "relationship",
                "category": "relationships",
                "lifecycle": "material",
                "title": "林澈 → 白塔会 / opposes",
                "summary": "林澈调查白塔会。",
                "payload_jsonb": {
                    "source_entity_name": "林澈",
                    "target_entity_name": "白塔会",
                    "relationship_type": "opposes",
                },
                "tags_jsonb": ["pi_analysis", "relationship"],
            },
            {
                "asset_id": "asset-rule-1",
                "asset_type": "world_rule",
                "category": "world",
                "lifecycle": "material",
                "title": "灵气守恒",
                "summary": "世界规则摘要。",
                "payload_jsonb": {"rule_text": "灵气守恒"},
                "tags_jsonb": ["pi_analysis", "world_rule"],
            },
        ],
        "fetch_version": [{"next_version": 1}],
    }
    connection = FakeStoryGraphConnection(rows)
    builder = PostgresStoryGraphBuilder(connect=lambda: connection)

    result = builder.build(
        context=_context(),
        mode="full",
        options={"source": "assets", "analysis_run_id": "analysis-run-1"},
    )

    assert result["status"] == "completed"
    assert result["node_count"] == 3
    assert result["edge_count"] == 1
    executed_sql = "\n".join(query for query, _params in connection.cursor_instance.executed)
    assert "source_kind = 'pi_analysis'" in executed_sql
    assert "FROM entities" not in executed_sql
    assert any(
        params[-1] == "analysis-run-1:%"
        for _query, params in connection.cursor_instance.executed
        if params and isinstance(params[-1], str) and params[-1].endswith(":%")
    )
    assert connection.committed is True


def test_story_graph_semantic_merge_deduplicates_alias_entities_and_relationship_edges() -> None:
    graph_id = "80d8a69e-6be3-47e9-94d2-b144c96bde71"
    entities = [
        {
            "entity_id": "24db71c0-9ec2-49da-9338-9ed095583ecf",
            "canonical_name": "林澈",
            "entity_type": "character",
            "importance": "high",
            "state_summary": "公开摘要 A",
            "first_seen_segment_id": None,
            "metadata_jsonb": {},
        },
        {
            "entity_id": "2d271cbf-363e-41c8-8349-2f879b006d83",
            "canonical_name": "谈判者",
            "entity_type": "character",
            "importance": "medium",
            "state_summary": "公开摘要 B",
            "first_seen_segment_id": None,
            "metadata_jsonb": {},
        },
        {
            "entity_id": "690df97d-b4cb-4356-854d-6db263bf13d8",
            "canonical_name": "白塔会",
            "entity_type": "organization",
            "importance": "medium",
            "state_summary": "公开摘要 C",
            "first_seen_segment_id": None,
            "metadata_jsonb": {},
        },
    ]
    aliases = [
        {"entity_id": "2d271cbf-363e-41c8-8349-2f879b006d83", "alias": "林澈"},
        {"entity_id": "24db71c0-9ec2-49da-9338-9ed095583ecf", "alias": "小林"},
    ]
    nodes = _merge_entity_nodes(graph_id=graph_id, entities=entities, aliases=aliases)
    repeated = _merge_entity_nodes(graph_id=graph_id, entities=list(reversed(entities)), aliases=list(reversed(aliases)))

    assert len(nodes) == 2
    assert [node["node_id"] for node in nodes] == [node["node_id"] for node in repeated]
    merged = next(node for node in nodes if node["node_type"] == "character")
    assert merged["attributes"]["merged_source_count"] == 2
    assert set(merged["attributes"]["aliases"]) == {"小林", "谈判者"}
    builder = PostgresStoryGraphBuilder(connect=lambda: FakeStoryGraphConnection({}))
    edges = builder._build_edges(
        graph_id=graph_id,
        relationships=[
            {
                "relationship_id": "relationship-a",
                "source_entity_name": "林澈",
                "target_entity_name": "白塔会",
                "relationship_type": "opposes",
                "summary": "公开关系摘要",
                "first_seen_segment_id": None,
                "metadata_jsonb": {},
            },
            {
                "relationship_id": "relationship-b",
                "source_entity_name": "谈判者",
                "target_entity_name": "白塔会",
                "relationship_type": "opposes",
                "summary": "重复关系摘要",
                "first_seen_segment_id": None,
                "metadata_jsonb": {},
            },
        ],
        node_by_entity_name=_entity_name_index(nodes),
    )

    assert len(edges) == 1
    assert edges[0]["weight"] == 2
    assert len(edges[0]["evidence"]) == 2
    assert edges[0]["attributes"]["source_count"] == 2


def test_story_graph_large_layout_persists_every_node_and_only_recommends_cluster_overview() -> None:
    graph_id = "9bc50694-1551-43fb-9b7a-9b1b192753d4"
    entities = [
        {
            "entity_id": f"00000000-0000-4000-8000-{index:012d}",
            "canonical_name": f"角色 {index:04d}",
            "entity_type": "character" if index % 2 == 0 else "organization",
            "importance": (index % 10) / 10,
            "state_summary": f"公开摘要 {index}",
            "first_seen_segment_id": None,
            "metadata_jsonb": {},
        }
        for index in range(1, 1002)
    ]
    nodes = _merge_entity_nodes(graph_id=graph_id, entities=entities, aliases=[])
    clusters = _assign_graph_clusters(graph_id=graph_id, nodes=nodes, edges=[])
    layout = _deterministic_cluster_layout(
        graph_id=graph_id,
        nodes=nodes,
        edges=[],
        clusters=clusters,
        viewport_node_budget=300,
    )
    repeated = _deterministic_cluster_layout(
        graph_id=graph_id,
        nodes=nodes,
        edges=[],
        clusters=clusters,
        viewport_node_budget=300,
    )

    assert len(nodes) == 1001
    assert len(layout["nodes"]) == 1001
    assert {item["node_id"] for item in layout["nodes"]} == {node["node_id"] for node in nodes}
    assert layout == repeated
    assert layout["schema_version"] == 3
    assert layout["strategy"] == "deterministic_force_components"
    assert layout["viewport"] == {
        "mode": "cluster_overview",
        "total_node_count": 1001,
        "total_cluster_count": 2,
        "recommended_page_size": 300,
        "omitted_node_count": 0,
        "strategy_basis": "all node positions persisted; cluster overview recommended when the interactive node budget is exceeded",
    }


def test_story_graph_force_layout_pulls_connected_nodes_closer_than_grid_baseline() -> None:
    graph_id = "a1b2c3d4-1551-43fb-9b7a-9b1b192753d4"
    nodes = [
        {
            "node_id": f"node-{index}",
            "stable_identity": f"entity:{index}",
            "node_type": "character",
            "importance": 0.5,
            "title": f"角色{index}",
        }
        for index in range(6)
    ]
    edges = [
        {"source_node_id": "node-0", "target_node_id": "node-1", "weight": 2},
        {"source_node_id": "node-1", "target_node_id": "node-2", "weight": 2},
        {"source_node_id": "node-2", "target_node_id": "node-3", "weight": 1},
        {"source_node_id": "node-3", "target_node_id": "node-4", "weight": 1},
        {"source_node_id": "node-4", "target_node_id": "node-5", "weight": 1},
        {"source_node_id": "node-0", "target_node_id": "node-5", "weight": 1},
    ]
    clusters = _assign_graph_clusters(graph_id=graph_id, nodes=nodes, edges=edges)
    layout = _deterministic_cluster_layout(
        graph_id=graph_id,
        nodes=nodes,
        edges=edges,
        clusters=clusters,
        viewport_node_budget=300,
    )
    by_id = {item["node_id"]: item for item in layout["nodes"]}
    lengths = []
    for edge in edges:
        source = by_id[edge["source_node_id"]]
        target = by_id[edge["target_node_id"]]
        lengths.append(((source["x"] - target["x"]) ** 2 + (source["y"] - target["y"]) ** 2) ** 0.5)
    average_length = sum(lengths) / len(lengths)
    # Old grid used ~180x112 cell spacing; connected force layout should stay tighter.
    assert average_length < 220
    assert layout["strategy"] == "deterministic_force_components"
    assert len(layout["clusters"]) == 1


def test_story_graph_build_activity_uses_env_db_builder_when_configured(monkeypatch: Any) -> None:
    connection = FakeStoryGraphConnection(
        {
            "fetch_entities": [],
            "fetch_aliases": [],
            "fetch_labels": [],
            "fetch_relationships": [],
            "fetch_plot_threads": [],
            "fetch_world_rules": [],
            "fetch_assets": [],
            "fetch_version": [{"next_version": 1}],
        }
    )
    monkeypatch.setenv("DATABASE_URL", "postgres://example")
    monkeypatch.setattr(
        PostgresStoryGraphBuilder,
        "from_database_url",
        classmethod(lambda cls, database_url: cls(connect=lambda: connection)),
    )
    monkeypatch.setattr(
        PostgresWorkflowRunStatusWriter,
        "from_database_url",
        classmethod(lambda cls, database_url: RecordingWorkflowRunStatusWriter()),
    )

    result = story_graph_build_activity(_payload(), graph_builder=None, workflow_event_writer=RecordingWorkflowEventWriter())

    assert result["status"] == "completed"
    assert result["node_count"] == 0
    assert result["edge_count"] == 0
    assert _story_graph_builder_from_env() is not None


def test_graph_worker_spec_registers_temporal_workflow_and_activity() -> None:
    spec = worker_spec()

    assert spec["task_queue"] == GRAPH_TASK_QUEUE
    assert "StoryGraphBuildWorkflow" in spec["workflows"]
    assert "GraphBondGenerationWorkflow" in spec["workflows"]
    assert "story_graph_build_activity" in spec["activities"]
    assert "graph_bond_generation_activity" in spec["activities"]


def test_temporal_graph_worker_registers_story_graph_activity() -> None:
    components = worker_components_for_task_queue(GRAPH_TASK_QUEUE)

    assert [workflow.__name__ for workflow in components["workflows"]] == [
        "StoryGraphBuildWorkflow",
        "GraphBondGenerationWorkflow",
    ]
    assert [activity.__name__ for activity in components["activities"]] == [
        "story_graph_build_activity",
        "graph_bond_generation_activity",
    ]


class FakeStoryGraphCursor:
    def __init__(self, rows: dict[str, list[dict[str, Any]]]) -> None:
        self.rows = {key: list(value) for key, value in rows.items()}
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.current_key: str | None = None

    def execute(self, query: str, params: tuple[Any, ...]) -> None:
        self.executed.append((query, params))
        self.current_key = self._query_key(query)

    def fetchall(self) -> list[dict[str, Any]]:
        if self.current_key is None:
            return []
        return list(self.rows.get(self.current_key, []))

    def fetchone(self) -> dict[str, Any] | None:
        if self.current_key is None:
            return None
        rows = self.rows.get(self.current_key, [])
        if rows:
            return rows.pop(0)
        return None

    def __enter__(self) -> "FakeStoryGraphCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def _query_key(self, query: str) -> str | None:
        if "max(version)" in query:
            return "fetch_version"
        if "FROM entities" in query:
            return "fetch_entities"
        if "FROM entity_aliases" in query:
            return "fetch_aliases"
        if "FROM entity_labels" in query:
            return "fetch_labels"
        if "FROM relationships" in query:
            return "fetch_relationships"
        if "FROM plot_threads" in query:
            return "fetch_plot_threads"
        if "FROM world_rule_evidence" in query:
            return "fetch_world_rules"
        if "FROM assets" in query:
            return "fetch_assets"
        return None


class FakeStoryGraphConnection:
    def __init__(self, rows: dict[str, list[dict[str, Any]]]) -> None:
        self.cursor_instance = FakeStoryGraphCursor(rows)
        self.committed = False
        self.closed = False

    def cursor(self) -> FakeStoryGraphCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True


class FakeWorkflowStatusCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = list(rows)
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, query: str, params: tuple[Any, ...]) -> None:
        self.executed.append((query, params))

    def fetchone(self) -> dict[str, Any] | None:
        if not self.rows:
            return None
        return self.rows.pop(0)

    def __enter__(self) -> "FakeWorkflowStatusCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class FakeWorkflowStatusConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.cursor_instance = FakeWorkflowStatusCursor(rows)
        self.committed = False
        self.closed = False

    def cursor(self) -> FakeWorkflowStatusCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True
