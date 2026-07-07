from __future__ import annotations

from typing import Any

from mirofish_agents.common.context import AgentContext
from mirofish_agents.seed.global_aggregator import (
    LLMFacilityGlobalAggregator,
    PostgresSeedAggregateSource,
)
from mirofish_agents.seed.sequential_reader import LLMFacilityError, ModuleBindingResolution


def _context() -> AgentContext:
    return AgentContext(
        tenant_id="tenant-1",
        project_id="project-1",
        run_id="run-1",
        workflow_type="seed_pipeline",
        actor_user_id="user-1",
        trace_id="trace-1",
        permissions={"seed_pipeline": ["run"]},
    )


def _uuid_context() -> AgentContext:
    return _context().model_copy(
        update={
            "tenant_id": "00000000-0000-0000-0000-000000000001",
            "project_id": "00000000-0000-0000-0000-000000000002",
            "actor_user_id": "00000000-0000-0000-0000-000000000003",
        }
    )


def _resolution() -> ModuleBindingResolution:
    return ModuleBindingResolution(
        tenant_id="tenant-1",
        project_id="project-1",
        module_key="anchor_point_summary",
        channel_id="channel-1",
        model_id="model-agg",
        provider="openai-compatible",
        base_url="https://llm.example/v1",
        credential_ref="channel-1",
        supports_json=True,
        settings={"temperature": 0.2},
    )


def test_llm_facility_global_aggregator_calls_provider_with_explicit_key_and_sanitized_source() -> None:
    resolver = RecordingBindingResolver(_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-aggregate")
    chat_client = RecordingJSONChatClient(
        response_json={
            "seed_analysis": {
                "overview": "雨城卷建立追踪压力。",
                "timeline_summary": "雨夜追踪后进入破晓。",
                "open_threads": ["雨夜追踪"],
            }
        }
    )
    aggregator = LLMFacilityGlobalAggregator(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        aggregate_source=StaticAggregateSource(
            {
                "segment_summaries": [
                    {
                        "segment_id": "segment-1",
                        "summary": "雨夜开场。",
                        "raw_content": "raw novel text must not reach aggregate prompt",
                    }
                ],
                "fact_counts": {"entities": 2, "relationships": 1},
                "prompt": "caller prompt must not reach aggregate prompt",
            }
        ),
    )

    result = aggregator.aggregate(context=_context(), module_key="anchor_point_summary")

    assert result["status"] == "completed"
    assert result["module_key"] == "anchor_point_summary"
    assert result["model_id"] == "model-agg"
    assert result["segment_count"] == 1
    assert result["summary_count"] == 2
    assert result["seed_analysis"]["overview"] == "雨城卷建立追踪压力。"
    assert resolver.calls == [("tenant-1", "project-1", "anchor_point_summary")]
    assert credentials.calls == [("tenant-1", "run-1", "channel-1")]
    assert chat_client.calls[0]["api_key"] == "sk-aggregate"
    prompt_body = chat_client.calls[0]["messages"][1]["content"]
    assert "雨夜开场" in prompt_body
    assert "raw novel text" not in prompt_body
    assert "caller prompt" not in prompt_body


def test_llm_facility_global_aggregator_fails_closed_when_module_is_unbound() -> None:
    resolver = RecordingBindingResolver(
        LLMFacilityError("LLM_MODULE_UNBOUND", "anchor_point_summary module is not bound")
    )
    credentials = RecordingCredentialProvider(api_key="sk-aggregate")
    chat_client = RecordingJSONChatClient(response_json={"seed_analysis": {"overview": "should not run"}})
    aggregator = LLMFacilityGlobalAggregator(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        aggregate_source=StaticAggregateSource({"segment_summaries": []}),
    )

    result = aggregator.aggregate(context=_context(), module_key="anchor_point_summary")

    assert result["status"] == "failed"
    assert result["error"]["code"] == "LLM_MODULE_UNBOUND"
    assert credentials.calls == []
    assert chat_client.calls == []


def test_llm_facility_global_aggregator_rejects_invalid_provider_schema() -> None:
    aggregator = LLMFacilityGlobalAggregator(
        binding_resolver=RecordingBindingResolver(_resolution()),
        credential_provider=RecordingCredentialProvider(api_key="sk-aggregate"),
        chat_client=RecordingJSONChatClient(response_json={"seed_analysis": "not-an-object"}),
        aggregate_source=StaticAggregateSource({"segment_summaries": []}),
    )

    result = aggregator.aggregate(context=_context(), module_key="anchor_point_summary")

    assert result["status"] == "failed"
    assert result["error"]["code"] == "SCHEMA_VALIDATION_FAILED"


def test_postgres_seed_aggregate_source_loads_public_summaries_and_counts_without_evidence() -> None:
    connection = AggregateConnection(
        segment_rows=[
            {"segment_id": "segment-1", "summary": "雨夜开场。"},
            {"segment_id": "segment-2", "summary": "破晓转场。"},
        ],
        count_rows=[
            {"fact_type": "entities", "fact_count": 2},
            {"fact_type": "relationships", "fact_count": 1},
        ],
    )
    source = PostgresSeedAggregateSource(connect=lambda: connection)
    context = _uuid_context()

    result = source.load_aggregate_input(context=context)

    assert result == {
        "segment_summaries": [
            {"segment_id": "segment-1", "summary": "雨夜开场。"},
            {"segment_id": "segment-2", "summary": "破晓转场。"},
        ],
        "fact_counts": {"entities": 2, "relationships": 1},
    }
    queries = "\n".join(connection.cursor_instance.queries).lower()
    assert "evidence_text" not in queries
    assert "raw_content" not in queries
    assert "content" not in queries
    assert connection.cursor_instance.queries[0] == "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)"
    assert connection.cursor_instance.params == [
        ("00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000003"),
        ("00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002", "run-1"),
        ("00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002", "run-1"),
    ]
    assert connection.closed is True


def test_postgres_seed_aggregate_source_sanitizes_query_failures() -> None:
    connection = FailingAggregateConnection(fail_on_execute=2)
    source = PostgresSeedAggregateSource(connect=lambda: connection)
    context = _uuid_context()
    message = ""

    try:
        source.load_aggregate_input(context=context)
    except LLMFacilityError as exc:
        assert exc.code == "SEED_AGGREGATE_SOURCE_QUERY_FAILED"
        assert exc.message == "seed aggregate source query failed"
        message = exc.message
    else:
        raise AssertionError("expected aggregate source query failure")

    assert connection.closed is True
    for forbidden in ("prompt", "api_key", "sk-hidden", "credential_ref", "raw novel"):
        assert forbidden not in message


class StaticAggregateSource:
    def __init__(self, aggregate_input: dict[str, Any]) -> None:
        self.aggregate_input = aggregate_input

    def load_aggregate_input(self, *, context: AgentContext) -> dict[str, Any]:
        return self.aggregate_input


class RecordingBindingResolver:
    def __init__(self, result: ModuleBindingResolution | LLMFacilityError) -> None:
        self.result = result
        self.calls: list[tuple[str, str | None, str]] = []

    def resolve_module_binding(self, *, context: AgentContext, module_key: str) -> ModuleBindingResolution:
        self.calls.append((context.tenant_id, context.project_id, module_key))
        if isinstance(self.result, LLMFacilityError):
            raise self.result
        return self.result


class RecordingCredentialProvider:
    def __init__(self, api_key: str | None = None, error: LLMFacilityError | None = None) -> None:
        self.api_key = api_key
        self.error = error
        self.calls: list[tuple[str, str, str]] = []

    def resolve_api_key(self, *, context: AgentContext, credential_ref: str) -> str:
        self.calls.append((context.tenant_id, context.run_id, credential_ref))
        if self.error is not None:
            raise self.error
        assert self.api_key is not None
        return self.api_key


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
                "tenant_id": context.tenant_id,
                "resolution": resolution,
                "api_key": api_key,
                "messages": messages,
            }
        )
        return self.response_json


class AggregateCursor:
    def __init__(self, *, segment_rows: list[dict[str, Any]], count_rows: list[dict[str, Any]]) -> None:
        self.segment_rows = segment_rows
        self.count_rows = count_rows
        self.queries: list[str] = []
        self.params: list[tuple[object, ...]] = []
        self._last_query_index = 0

    def __enter__(self) -> "AggregateCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.queries.append(query)
        self.params.append(params)
        self._last_query_index = len(self.queries)

    def fetchall(self) -> list[dict[str, Any]]:
        last_query = self.queries[self._last_query_index - 1].lower()
        if "from segment_summaries" in last_query:
            return self.segment_rows
        return self.count_rows


class AggregateConnection:
    def __init__(self, *, segment_rows: list[dict[str, Any]], count_rows: list[dict[str, Any]]) -> None:
        self.cursor_instance = AggregateCursor(segment_rows=segment_rows, count_rows=count_rows)
        self.closed = False

    def cursor(self) -> AggregateCursor:
        return self.cursor_instance

    def close(self) -> None:
        self.closed = True


class FailingAggregateCursor(AggregateCursor):
    def __init__(self, *, fail_on_execute: int) -> None:
        super().__init__(segment_rows=[], count_rows=[])
        self.fail_on_execute = fail_on_execute
        self.execute_count = 0

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.execute_count += 1
        super().execute(query, params)
        if self.execute_count == self.fail_on_execute:
            raise RuntimeError(
                "driver failure prompt=hidden api_key=sk-hidden credential_ref=secret raw novel text"
            )


class FailingAggregateConnection(AggregateConnection):
    def __init__(self, *, fail_on_execute: int) -> None:
        self.cursor_instance = FailingAggregateCursor(fail_on_execute=fail_on_execute)
        self.closed = False
