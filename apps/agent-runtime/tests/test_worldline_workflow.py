from __future__ import annotations

import json
from typing import Any

from mirofish_agents.common.context import AgentContext
from mirofish_agents.seed.sequential_reader import (
    AesGcmCredentialDecryptor,
    LLMFacilityError,
    ModuleBindingResolution,
    PostgresCredentialProvider,
    PostgresModuleBindingResolver,
)
from mirofish_agents.temporal.worker import worker_components_for_task_queue
from mirofish_agents.temporal.worldline import (
    LLMFacilityWorldlineStepRunner,
    PostgresLLMTelemetryWriter,
    PostgresWorkflowEventWriter,
    PostgresWorkflowRunStatusWriter,
    PostgresWorldlineSourceLoader,
    PostgresWorldlineCandidateEventWriter,
    WORLDLINE_STEP_MODULE_KEY,
    WORLDLINE_TASK_QUEUE,
    run_worldline_step_workflow_locally,
    worker_spec,
    worldline_step_activity,
)


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


class RaisingWorkflowEventWriter:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def write_event(
        self,
        *,
        tenant_id: str,
        project_id: str | None,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "run_id": run_id,
                "event_type": event_type,
                "payload": payload,
            }
        )
        raise self.error


class RecordingWorkflowRunStatusWriter:
    def __init__(self) -> None:
        self.failed: list[dict[str, Any]] = []
        self.completed: list[dict[str, Any]] = []

    def mark_failed(
        self,
        *,
        context: AgentContext,
        code: str,
        message: str,
    ) -> None:
        self.failed.append({"context": context, "code": code, "message": message})

    def mark_completed(
        self,
        *,
        context: AgentContext,
        result: dict[str, Any],
    ) -> None:
        self.completed.append({"context": context, "result": result})


class RecordingBindingResolver:
    def __init__(self, resolution: ModuleBindingResolution) -> None:
        self.resolution = resolution
        self.calls: list[str] = []

    def resolve_module_binding(self, *, context: AgentContext, module_key: str) -> ModuleBindingResolution:
        self.calls.append(module_key)
        return self.resolution


class RecordingCredentialProvider:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.calls: list[str] = []

    def resolve_api_key(self, *, context: AgentContext, credential_ref: str) -> str:
        self.calls.append(credential_ref)
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
                "context": context,
                "resolution": resolution,
                "api_key": api_key,
                "messages": messages,
            }
        )
        return self.response_json


class RaisingJSONChatClient:
    def __init__(self, error: Exception) -> None:
        self.error = error
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
        raise self.error


class RecordingWorldlineCandidateEventWriter:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def write_candidate_events(
        self,
        *,
        context: AgentContext,
        session_id: str,
        source_run_id: str,
        model_id: str | None,
        mode: str,
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "context": context,
                "session_id": session_id,
                "source_run_id": source_run_id,
                "model_id": model_id,
                "mode": mode,
                "events": events,
            }
        )
        return {"status": "completed", "candidate_event_count": len(events)}


class FailingWorldlineCandidateEventWriter:
    def __init__(
        self,
        code: str = "WORLDLINE_SESSION_NOT_FOUND",
        message: str = "worldline session was not admitted for this tenant/project",
    ) -> None:
        self.code = code
        self.message = message
        self.calls: list[dict[str, Any]] = []

    def write_candidate_events(
        self,
        *,
        context: AgentContext,
        session_id: str,
        source_run_id: str,
        model_id: str | None,
        mode: str,
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "context": context,
                "session_id": session_id,
                "source_run_id": source_run_id,
                "model_id": model_id,
                "mode": mode,
                "events": events,
            }
        )
        raise LLMFacilityError(self.code, self.message)


class RaisingWorldlineCandidateEventWriter:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def write_candidate_events(
        self,
        *,
        context: AgentContext,
        session_id: str,
        source_run_id: str,
        model_id: str | None,
        mode: str,
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "context": context,
                "session_id": session_id,
                "source_run_id": source_run_id,
                "model_id": model_id,
                "mode": mode,
                "events": events,
            }
        )
        raise self.error


class RecordingLLMTelemetryWriter:
    def __init__(self) -> None:
        self.activities: list[dict[str, Any]] = []
        self.usage_events: list[dict[str, Any]] = []

    def record_llm_activity(
        self,
        *,
        context: AgentContext,
        module_key: str,
        channel_id: str,
        model_id: str,
        status: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        latency_ms: int | None = None,
        cost_estimate: float | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        self.activities.append(
            {
                "context": context,
                "module_key": module_key,
                "channel_id": channel_id,
                "model_id": model_id,
                "status": status,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "latency_ms": latency_ms,
                "cost_estimate": cost_estimate,
                "error": error,
            }
        )

    def record_usage_event(
        self,
        *,
        context: AgentContext,
        module_key: str,
        usage_type: str,
        quantity: int,
        unit: str,
        metadata: dict[str, Any],
    ) -> None:
        self.usage_events.append(
            {
                "context": context,
                "module_key": module_key,
                "usage_type": usage_type,
                "quantity": quantity,
                "unit": unit,
                "metadata": metadata,
            }
        )


class RecordingWorldlineSourceLoader:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def load_sources(
        self,
        *,
        context: AgentContext,
        session_id: str,
        source_refs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "context": context,
                "session_id": session_id,
                "source_refs": source_refs,
            }
        )
        return [
            {
                "source_ref": "asset:public-1",
                "summary": "Public faction summary only.",
                "source_kind": "asset",
                "source_text": "private source text must stay server-side",
                "prompt": "hidden prompt",
                "credential_ref": "secret-ref",
            }
        ]


class EmptyWorldlineSourceLoader:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def load_sources(
        self,
        *,
        context: AgentContext,
        session_id: str,
        source_refs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "context": context,
                "session_id": session_id,
                "source_refs": source_refs,
            }
        )
        return []


class FailingLLMTelemetryWriter:
    def __init__(self, code: str = "LLM_TELEMETRY_WRITE_FAILED") -> None:
        self.code = code
        self.activity_calls = 0
        self.usage_calls = 0

    def record_llm_activity(
        self,
        *,
        context: AgentContext,
        module_key: str,
        channel_id: str,
        model_id: str,
        status: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        latency_ms: int | None = None,
        cost_estimate: float | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        self.activity_calls += 1
        raise LLMFacilityError(self.code, "worldline LLM activity write failed")

    def record_usage_event(
        self,
        *,
        context: AgentContext,
        module_key: str,
        usage_type: str,
        quantity: int,
        unit: str,
        metadata: dict[str, Any],
    ) -> None:
        self.usage_calls += 1
        raise LLMFacilityError(self.code, "worldline usage event write failed")


class RaisingLLMTelemetryWriter:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.activity_calls = 0
        self.usage_calls = 0

    def record_llm_activity(
        self,
        *,
        context: AgentContext,
        module_key: str,
        channel_id: str,
        model_id: str,
        status: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        latency_ms: int | None = None,
        cost_estimate: float | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        self.activity_calls += 1
        raise self.error

    def record_usage_event(
        self,
        *,
        context: AgentContext,
        module_key: str,
        usage_type: str,
        quantity: int,
        unit: str,
        metadata: dict[str, Any],
    ) -> None:
        self.usage_calls += 1
        raise self.error


class SuccessfulWorldlineStepRunner:
    def run_step(
        self,
        *,
        context: AgentContext,
        session_id: str,
        mode: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "status": "completed",
            "session_id": session_id,
            "mode": mode,
            "step": 3,
            "candidate_event_count": 1,
            "model_id": "model-worldline",
            "prompt": "must not be persisted",
            "credential_ref": "secret-ref",
            "event_body": "private event body",
        }


class RaisingWorldlineStepRunner:
    def __init__(self, error: LLMFacilityError) -> None:
        self.error = error

    def run_step(
        self,
        *,
        context: AgentContext,
        session_id: str,
        mode: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        raise self.error


class RecordingCursor:
    def __init__(self) -> None:
        self.executions: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self.executions.append((sql, params))

    def fetchone(self) -> dict[str, str]:
        return {"event_id": "event-1"}


class RecordingConnection:
    def __init__(self) -> None:
        self.cursor_obj = RecordingCursor()
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self) -> RecordingCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


class FailingUsageInsertCursor(RecordingCursor):
    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        super().execute(sql, params)
        if "INSERT INTO usage_events" in sql:
            raise RuntimeError("usage insert failed with prompt=hidden api_key=sk-nope")


class FailingUsageInsertConnection(RecordingConnection):
    def __init__(self) -> None:
        super().__init__()
        self.cursor_obj = FailingUsageInsertCursor()


class FailingActivityInsertCursor(RecordingCursor):
    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        super().execute(sql, params)
        if "INSERT INTO llm_activity" in sql:
            raise RuntimeError("activity insert failed with prompt=hidden api_key=sk-nope")


class FailingActivityInsertConnection(RecordingConnection):
    def __init__(self) -> None:
        super().__init__()
        self.cursor_obj = FailingActivityInsertCursor()


class FailingWorkflowEventInsertCursor(RecordingCursor):
    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        super().execute(sql, params)
        if "INSERT INTO workflow_events" in sql:
            raise RuntimeError("workflow event insert failed prompt=hidden api_key=sk-nope credential_ref=secret")


class FailingWorkflowEventInsertConnection(RecordingConnection):
    def __init__(self) -> None:
        super().__init__()
        self.cursor_obj = FailingWorkflowEventInsertCursor()


class FailingWorkflowStatusUpdateCursor(RecordingCursor):
    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        super().execute(sql, params)
        if "UPDATE workflow_runs" in sql:
            raise RuntimeError("workflow status update failed prompt=hidden api_key=sk-nope credential_ref=secret")


class FailingWorkflowStatusUpdateConnection(RecordingConnection):
    def __init__(self) -> None:
        super().__init__()
        self.cursor_obj = FailingWorkflowStatusUpdateCursor()


class MissingWorkflowStatusParentCursor(RecordingCursor):
    def fetchone(self) -> dict[str, int]:
        return {"workflow_updated": 0}


class MissingWorkflowStatusParentConnection(RecordingConnection):
    def __init__(self) -> None:
        super().__init__()
        self.cursor_obj = MissingWorkflowStatusParentCursor()


class MissingWorkflowEventParentCursor(RecordingCursor):
    def fetchone(self) -> dict[str, str] | None:
        return None


class MissingWorkflowEventParentConnection(RecordingConnection):
    def __init__(self) -> None:
        super().__init__()
        self.cursor_obj = MissingWorkflowEventParentCursor()


class FailingCandidateInsertCursor(RecordingCursor):
    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        super().execute(sql, params)
        if "INSERT INTO worldline_events" in sql:
            raise RuntimeError("candidate insert failed prompt=hidden api_key=sk-nope credential_ref=secret-ref")


class FailingCandidateInsertConnection(RecordingConnection):
    def __init__(self) -> None:
        super().__init__()
        self.cursor_obj = FailingCandidateInsertCursor()


class MissingSessionCandidateCursor(RecordingCursor):
    def fetchone(self) -> dict[str, str] | None:
        return None


class MissingSessionCandidateConnection(RecordingConnection):
    def __init__(self) -> None:
        super().__init__()
        self.cursor_obj = MissingSessionCandidateCursor()


class WorldlineSourceLoaderCursor(RecordingCursor):
    def __init__(self) -> None:
        super().__init__()
        self._last_sql = ""

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self._last_sql = sql
        super().execute(sql, params)

    def fetchall(self) -> list[dict[str, Any]]:
        if "FROM assets" in self._last_sql:
            return [
                {
                    "source_kind": "asset",
                    "source_ref": "asset-1",
                    "title": "House Vale",
                    "summary": "Public asset summary.",
                    "asset_type": "faction",
                    "category": "world",
                    "prompt": "db prompt must be stripped",
                    "credential_ref": "secret-ref",
                    "source_text": "raw source text must not leave DB",
                }
            ]
        if "FROM worldline_events" in self._last_sql:
            return [
                {
                    "source_kind": "worldline_event",
                    "source_ref": "event-1",
                    "title": "Gate accord",
                    "summary": "Candidate event public summary.",
                    "kind": "political_turn",
                    "status": "candidate",
                    "event_body": "private event body must be stripped",
                }
            ]
        return []


class WorldlineSourceLoaderConnection(RecordingConnection):
    def __init__(self) -> None:
        super().__init__()
        self.cursor_obj = WorldlineSourceLoaderCursor()


class FailingWorldlineSourceLoaderCursor(RecordingCursor):
    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        super().execute(sql, params)
        raise RuntimeError("source query failed prompt=hidden api_key=sk-nope credential_ref=secret")


class FailingWorldlineSourceLoaderConnection(RecordingConnection):
    def __init__(self) -> None:
        super().__init__()
        self.cursor_obj = FailingWorldlineSourceLoaderCursor()


class WorldlineStepChainCursor:
    def __init__(self, connection: "WorldlineStepChainConnection") -> None:
        self._connection = connection
        self._last_sql = ""

    def __enter__(self) -> "WorldlineStepChainCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self._last_sql = sql
        self._connection.executions.append(
            {
                "connection": self._connection.name,
                "sql": sql,
                "params": params,
            }
        )

    def fetchone(self) -> dict[str, Any] | None:
        sql = self._last_sql
        if "FROM llm_module_bindings" in sql:
            return {
                "tenant_id": "tenant-1",
                "project_id": "project-1",
                "module_key": WORLDLINE_STEP_MODULE_KEY,
                "channel_id": "channel-worldline",
                "model_id": "model-worldline",
                "provider": "openai-compatible",
                "base_url": "https://llm.example/v1",
                "supports_json": True,
                "settings_jsonb": '{"temperature":0.4}',
            }
        if "SELECT encrypted_api_key" in sql:
            return {
                "encrypted_api_key": (
                    "aes-256-gcm:v1:ABEiM0RVZneImaq7:"
                    "87utEhTfLrnKAiv0vtWdTg==:qe3dwCoCLzMECbZ5"
                )
            }
        if "INSERT INTO worldline_events" in sql:
            return {"event_id": "event-candidate-1"}
        if "INSERT INTO workflow_events" in sql:
            return {"event_id": "event-workflow-1"}
        if "UPDATE workflow_runs" in sql:
            return {"workflow_updated": 1}
        return None


class WorldlineStepChainConnection:
    def __init__(self, *, name: str, executions: list[dict[str, Any]]) -> None:
        self.name = name
        self.executions = executions
        self.cursor_obj = WorldlineStepChainCursor(self)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self) -> WorldlineStepChainCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


class WorldlineStepChainDatabase:
    def __init__(self) -> None:
        self.executions: list[dict[str, Any]] = []
        self.connections: list[WorldlineStepChainConnection] = []

    def connect(self) -> WorldlineStepChainConnection:
        connection = WorldlineStepChainConnection(
            name=f"conn-{len(self.connections) + 1}",
            executions=self.executions,
        )
        self.connections.append(connection)
        return connection


class LedgerJSONChatClient(RecordingJSONChatClient):
    def __init__(self, response_json: dict[str, Any], ledger: list[dict[str, Any]]) -> None:
        super().__init__(response_json=response_json)
        self._ledger = ledger

    def complete_json(
        self,
        *,
        context: AgentContext,
        resolution: ModuleBindingResolution,
        api_key: str,
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        self._ledger.append(
            {
                "connection": "provider",
                "sql": "PROVIDER complete_json",
                "params": (
                    context.tenant_id,
                    context.project_id,
                    context.run_id,
                    resolution.module_key,
                    resolution.channel_id,
                    resolution.model_id,
                ),
            }
        )
        return super().complete_json(
            context=context,
            resolution=resolution,
            api_key=api_key,
            messages=messages,
        )


WORLDLINE_STEP_RUN_UUID = "550e8400-e29b-41d4-a716-446655440000"


def _context(*, run_id: str = WORLDLINE_STEP_RUN_UUID) -> AgentContext:
    return AgentContext(
        tenant_id="tenant-1",
        project_id="project-1",
        run_id=run_id,
        workflow_type="worldline_step",
        actor_user_id="user-1",
        module_key=WORLDLINE_STEP_MODULE_KEY,
        trace_id="trace-worldline-step-1",
        permissions={WORLDLINE_STEP_MODULE_KEY: ["run"]},
    )


def _payload(options: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "context": _context().model_dump(),
        "session_id": "session-1",
        "mode": "director",
        "options": options
        if options is not None
        else {
            "max_turns": 2,
            "prompt": "这段 prompt 不得公开",
            "source_text": "世界线私有素材不得公开",
            "credential_ref": "secret-ref",
            "draft": "正文草稿不得公开",
        },
    }


def _worldline_resolution() -> ModuleBindingResolution:
    return ModuleBindingResolution(
        tenant_id="tenant-1",
        project_id="project-1",
        module_key=WORLDLINE_STEP_MODULE_KEY,
        channel_id="channel-worldline",
        model_id="model-worldline",
        provider="openai-compatible",
        base_url="https://llm.example/v1",
        credential_ref="channel-worldline",
        supports_json=True,
        settings={"temperature": 0.4},
    )


def test_llm_facility_worldline_step_runner_persists_candidate_events_without_public_body() -> None:
    resolver = RecordingBindingResolver(_worldline_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-worldline")
    chat_client = RecordingJSONChatClient(
        response_json={
            "candidate_events": [
                {
                    "title": "雨夜谈判破裂",
                    "summary": "主角拒绝让渡城门控制权，联盟关系进入冻结期。",
                    "kind": "political_turn",
                    "confidence": 0.82,
                    "involved_agent_ids": ["agent-1", "agent-2"],
                    "state_change_summary": "联盟信任下降，城门控制权保持未决。",
                    "event_body": "这段完整事件正文不得公开",
                    "prompt": "provider prompt must be stripped",
                    "credential_ref": "secret-ref",
                }
            ]
        }
    )
    writer = RecordingWorldlineCandidateEventWriter()
    runner = LLMFacilityWorldlineStepRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_event_writer=writer,
    )

    result = runner.run_step(
        context=_context(),
        session_id="session-1",
        mode="director",
        options={"goal": "推进一次单世界推演", "prompt": "不应公开的用户指令"},
    )

    assert result == {
        "status": "completed",
        "module_key": WORLDLINE_STEP_MODULE_KEY,
        "model_id": "model-worldline",
        "session_id": "session-1",
        "mode": "director",
        "candidate_event_count": 1,
        "step": 1,
    }
    assert resolver.calls == [WORLDLINE_STEP_MODULE_KEY]
    assert credentials.calls == ["channel-worldline"]
    assert chat_client.calls[0]["api_key"] == "sk-worldline"
    assert chat_client.calls[0]["resolution"].module_key == WORLDLINE_STEP_MODULE_KEY
    assert writer.calls[0]["session_id"] == "session-1"
    assert writer.calls[0]["source_run_id"] == WORLDLINE_STEP_RUN_UUID
    assert writer.calls[0]["events"] == [
        {
            "step": 1,
            "title": "雨夜谈判破裂",
            "summary": "主角拒绝让渡城门控制权，联盟关系进入冻结期。",
            "kind": "political_turn",
            "confidence": 0.82,
            "involved_agent_ids": ["agent-1", "agent-2"],
            "state_change_summary": "联盟信任下降，城门控制权保持未决。",
        }
    ]
    joined = json.dumps(
        [result, writer.calls, chat_client.calls[0]["messages"]],
        ensure_ascii=False,
        default=str,
    )
    for forbidden in ["完整事件正文", "provider prompt", "secret-ref", "sk-worldline", "不应公开"]:
        assert forbidden not in joined


def test_llm_facility_worldline_step_runner_rejects_non_uuid_run_id_before_provider_call() -> None:
    resolver = RecordingBindingResolver(_worldline_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-worldline")
    chat_client = RecordingJSONChatClient(
        response_json={
            "candidate_events": [
                {
                    "title": "不应生成",
                    "summary": "无效 run id 时不应调用 provider。",
                    "kind": "director",
                }
            ]
        }
    )
    candidate_writer = RecordingWorldlineCandidateEventWriter()
    telemetry_writer = RecordingLLMTelemetryWriter()
    runner = LLMFacilityWorldlineStepRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_event_writer=candidate_writer,
        telemetry_writer=telemetry_writer,
    )

    result = runner.run_step(
        context=_context(run_id="run-worldline-step-1"),
        session_id="session-1",
        mode="director",
        options={"goal": "推进一次单世界推演"},
    )

    assert result == {
        "status": "failed",
        "error": {
            "code": "VALIDATION_FAILED",
            "message": "run_id must be a valid UUID",
        },
    }
    assert resolver.calls == []
    assert credentials.calls == []
    assert chat_client.calls == []
    assert candidate_writer.calls == []
    assert telemetry_writer.activities == []
    assert telemetry_writer.usage_events == []


def test_llm_facility_worldline_step_runner_requires_source_loader_for_source_refs() -> None:
    resolver = RecordingBindingResolver(_worldline_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-worldline")
    chat_client = RecordingJSONChatClient(
        response_json={
            "candidate_events": [
                {
                    "title": "不应生成",
                    "summary": "缺少 source loader 时不应调用 provider。",
                    "kind": "director",
                }
            ]
        }
    )
    candidate_writer = RecordingWorldlineCandidateEventWriter()
    telemetry_writer = RecordingLLMTelemetryWriter()
    runner = LLMFacilityWorldlineStepRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_event_writer=candidate_writer,
        telemetry_writer=telemetry_writer,
    )

    result = runner.run_step(
        context=_context(),
        session_id="session-1",
        mode="director",
        options={
            "goal": "推进一次单世界推演",
            "source_refs": [{"source_kind": "asset", "source_id": "asset-1"}],
        },
    )

    assert result == {
        "status": "failed",
        "error": {
            "code": "WORLDLINE_SOURCE_LOADER_UNCONFIGURED",
            "message": "worldline source loader is required when source_refs are provided",
        },
    }
    assert resolver.calls == []
    assert credentials.calls == []
    assert chat_client.calls == []
    assert candidate_writer.calls == []
    assert telemetry_writer.activities == []
    assert telemetry_writer.usage_events == []


def test_llm_facility_worldline_step_runner_uses_sanitized_source_loader_summaries() -> None:
    source_loader = RecordingWorldlineSourceLoader()
    resolver = RecordingBindingResolver(_worldline_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-worldline")
    chat_client = RecordingJSONChatClient(
        response_json={
            "candidate_events": [
                {
                    "title": "源摘要驱动的候选事件",
                    "summary": "director 使用 public source summary 生成候选事件。",
                    "kind": "director",
                }
            ]
        }
    )
    runner = LLMFacilityWorldlineStepRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_event_writer=RecordingWorldlineCandidateEventWriter(),
        source_loader=source_loader,
    )

    result = runner.run_step(
        context=_context(),
        session_id="session-1",
        mode="director",
        options={
            "goal": "推进一次单世界推演",
            "source_refs": [
                {
                    "source_kind": "asset",
                    "source_id": "asset-1",
                    "source_text": "request body private text must be stripped",
                    "credential_ref": "request-secret",
                }
            ],
        },
    )

    assert result["status"] == "completed"
    assert source_loader.calls == [
        {
            "context": _context(),
            "session_id": "session-1",
            "source_refs": [{"source_kind": "asset", "source_id": "asset-1"}],
        }
    ]
    encoded_messages = json.dumps(chat_client.calls[0]["messages"], ensure_ascii=False)
    assert "Public faction summary only." in encoded_messages
    assert "asset:public-1" in encoded_messages
    for forbidden in [
        "private source text",
        "hidden prompt",
        "secret-ref",
        "request body private text",
        "request-secret",
        "sk-worldline",
        "credential_ref",
        "source_text",
    ]:
        assert forbidden not in encoded_messages


def test_llm_facility_worldline_step_runner_fails_when_source_refs_resolve_no_summaries() -> None:
    source_loader = EmptyWorldlineSourceLoader()
    resolver = RecordingBindingResolver(_worldline_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-worldline")
    chat_client = RecordingJSONChatClient(
        response_json={
            "candidate_events": [
                {
                    "title": "不应生成",
                    "summary": "source refs 未命中时不应调用 provider。",
                    "kind": "director",
                }
            ]
        }
    )
    candidate_writer = RecordingWorldlineCandidateEventWriter()
    telemetry_writer = RecordingLLMTelemetryWriter()
    runner = LLMFacilityWorldlineStepRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_event_writer=candidate_writer,
        telemetry_writer=telemetry_writer,
        source_loader=source_loader,
    )

    result = runner.run_step(
        context=_context(),
        session_id="session-1",
        mode="director",
        options={
            "goal": "推进一次单世界推演",
            "source_refs": [{"source_kind": "asset", "source_id": "missing-asset"}],
        },
    )

    assert result == {
        "status": "failed",
        "error": {
            "code": "WORLDLINE_SOURCE_NOT_FOUND",
            "message": "worldline source_refs did not resolve to public summaries",
        },
    }
    assert source_loader.calls == [
        {
            "context": _context(),
            "session_id": "session-1",
            "source_refs": [{"source_kind": "asset", "source_id": "missing-asset"}],
        }
    ]
    assert resolver.calls == []
    assert credentials.calls == []
    assert chat_client.calls == []
    assert candidate_writer.calls == []
    assert telemetry_writer.activities == []
    assert telemetry_writer.usage_events == []


def test_postgres_worldline_source_loader_reads_only_public_metadata() -> None:
    connection = WorldlineSourceLoaderConnection()
    loader = PostgresWorldlineSourceLoader(connect=lambda: connection)

    summaries = loader.load_sources(
        context=_context(),
        session_id="session-1",
        source_refs=[
            {"source_kind": "asset", "source_id": "asset-1"},
            {"source_kind": "worldline_event", "event_id": "event-1"},
        ],
    )

    assert summaries == [
        {
            "source_kind": "asset",
            "source_ref": "asset-1",
            "title": "House Vale",
            "summary": "Public asset summary.",
            "asset_type": "faction",
            "category": "world",
        },
        {
            "source_kind": "worldline_event",
            "source_ref": "event-1",
            "title": "Gate accord",
            "summary": "Candidate event public summary.",
            "kind": "political_turn",
            "status": "candidate",
        },
    ]
    assert connection.commits == 0
    assert connection.rollbacks == 0
    assert connection.closed is True
    encoded = json.dumps([summaries, connection.cursor_obj.executions], ensure_ascii=False, default=str)
    assert "assets.content_text" not in encoded
    assert "body_text" not in encoded
    for forbidden in [
        "raw source text",
        "private event body",
        "db prompt",
        "secret-ref",
        "credential_ref",
        "source_text",
        "event_body",
    ]:
        assert forbidden not in encoded


def test_postgres_worldline_source_loader_sanitizes_query_exception_message() -> None:
    connection = FailingWorldlineSourceLoaderConnection()
    loader = PostgresWorldlineSourceLoader(connect=lambda: connection)

    try:
        loader.load_sources(
            context=_context(),
            session_id="session-1",
            source_refs=[{"source_kind": "asset", "source_id": "asset-1"}],
        )
    except LLMFacilityError as exc:
        assert exc.code == "WORLDLINE_SOURCE_LOAD_FAILED"
        assert exc.message == "worldline source load failed"
    else:  # pragma: no cover - test guard
        raise AssertionError("expected source loader failure")

    assert connection.closed is True
    encoded = json.dumps(connection.cursor_obj.executions, ensure_ascii=False, default=str)
    for forbidden in ["prompt=hidden", "api_key=sk-nope", "credential_ref=secret"]:
        assert forbidden not in encoded


def test_llm_facility_worldline_step_runner_rejects_resolution_without_provider_before_credential_call() -> None:
    resolution = _worldline_resolution()
    resolver = RecordingBindingResolver(
        ModuleBindingResolution(
            tenant_id=resolution.tenant_id,
            project_id=resolution.project_id,
            module_key=resolution.module_key,
            channel_id=resolution.channel_id,
            model_id=resolution.model_id,
            provider="",
            base_url=resolution.base_url,
            credential_ref=resolution.credential_ref,
            supports_json=resolution.supports_json,
            settings=resolution.settings,
        )
    )
    credentials = RecordingCredentialProvider(api_key="sk-worldline")
    chat_client = RecordingJSONChatClient(
        response_json={
            "candidate_events": [
                {
                    "title": "不应生成",
                    "summary": "缺少 provider 时不应调用 provider。",
                    "kind": "director",
                }
            ]
        }
    )
    candidate_writer = RecordingWorldlineCandidateEventWriter()
    telemetry_writer = RecordingLLMTelemetryWriter()
    runner = LLMFacilityWorldlineStepRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_event_writer=candidate_writer,
        telemetry_writer=telemetry_writer,
    )

    result = runner.run_step(
        context=_context(),
        session_id="session-1",
        mode="director",
        options={"goal": "推进一次单世界推演", "prompt": "隐藏指令"},
    )

    assert result == {
        "status": "failed",
        "error": {
            "code": "LLM_PROVIDER_ERROR",
            "message": "resolved LLM module is missing provider",
        },
    }
    assert resolver.calls == [WORLDLINE_STEP_MODULE_KEY]
    assert credentials.calls == []
    assert chat_client.calls == []
    assert candidate_writer.calls == []
    assert len(telemetry_writer.activities) == 1
    assert telemetry_writer.activities[0]["status"] == "failed"
    assert telemetry_writer.activities[0]["error"] == {
        "code": "LLM_PROVIDER_ERROR",
        "message": "resolved LLM module is missing provider",
    }
    assert telemetry_writer.usage_events == []
    joined = json.dumps([result, telemetry_writer.activities], ensure_ascii=False, default=str)
    for forbidden in ["sk-worldline", "隐藏指令", "prompt=", "credential_ref"]:
        assert forbidden not in joined


def test_llm_facility_worldline_step_runner_records_completed_activity_and_usage() -> None:
    resolver = RecordingBindingResolver(_worldline_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-worldline")
    chat_client = RecordingJSONChatClient(
        response_json={
            "candidate_events": [
                {
                    "title": "城门协议被暂缓",
                    "summary": "谈判双方同意推迟城门控制权交接。",
                    "kind": "political_turn",
                }
            ],
            "__llm_usage": {
                "prompt_tokens": 13,
                "completion_tokens": 21,
                "cost_estimate": 0.0042,
            },
        }
    )
    candidate_writer = RecordingWorldlineCandidateEventWriter()
    telemetry_writer = RecordingLLMTelemetryWriter()
    runner = LLMFacilityWorldlineStepRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_event_writer=candidate_writer,
        telemetry_writer=telemetry_writer,
    )

    result = runner.run_step(
        context=_context(),
        session_id="session-1",
        mode="director",
        options={"goal": "推进一次单世界推演"},
    )

    assert result["status"] == "completed"
    assert telemetry_writer.activities == [
        {
            "context": _context(),
            "module_key": WORLDLINE_STEP_MODULE_KEY,
            "channel_id": "channel-worldline",
            "model_id": "model-worldline",
            "status": "completed",
            "prompt_tokens": 13,
            "completion_tokens": 21,
            "latency_ms": telemetry_writer.activities[0]["latency_ms"],
            "cost_estimate": 0.0042,
            "error": None,
        }
    ]
    assert isinstance(telemetry_writer.activities[0]["latency_ms"], int)
    assert telemetry_writer.activities[0]["latency_ms"] >= 0
    assert telemetry_writer.usage_events == [
        {
            "context": _context(),
            "module_key": WORLDLINE_STEP_MODULE_KEY,
            "usage_type": "llm_tokens",
            "quantity": 34,
            "unit": "tokens",
            "metadata": {
                "channel_id": "channel-worldline",
                "model_id": "model-worldline",
                "provider": "openai-compatible",
                "prompt_tokens": 13,
                "completion_tokens": 21,
                "total_tokens": None,
                "cost_estimate": 0.0042,
            },
        }
    ]
    joined = json.dumps([telemetry_writer.activities, telemetry_writer.usage_events], ensure_ascii=False, default=str)
    for forbidden in ["sk-worldline", "credential_ref", "隐藏指令", "source_text"]:
        assert forbidden not in joined


def test_llm_facility_worldline_step_runner_writes_postgres_completed_activity_and_usage_atomically() -> None:
    connection = RecordingConnection()
    resolver = RecordingBindingResolver(_worldline_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-worldline")
    chat_client = RecordingJSONChatClient(
        response_json={
            "candidate_events": [
                {
                    "title": "城门协议被暂缓",
                    "summary": "谈判双方同意推迟城门控制权交接。",
                    "kind": "political_turn",
                }
            ],
            "__llm_usage": {
                "prompt_tokens": 13,
                "completion_tokens": 21,
                "cost_estimate": 0.0042,
            },
        }
    )
    runner = LLMFacilityWorldlineStepRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_event_writer=RecordingWorldlineCandidateEventWriter(),
        telemetry_writer=PostgresLLMTelemetryWriter(connect=lambda: connection),
    )

    result = runner.run_step(
        context=_context(),
        session_id="session-1",
        mode="director",
        options={"goal": "推进一次单世界推演"},
    )

    assert result["status"] == "completed"
    assert connection.commits == 1
    assert connection.closed is True
    assert len(connection.cursor_obj.executions) == 2
    assert "INSERT INTO llm_activity" in connection.cursor_obj.executions[0][0]
    assert "INSERT INTO usage_events" in connection.cursor_obj.executions[1][0]
    encoded = json.dumps(connection.cursor_obj.executions, ensure_ascii=False, default=str)
    assert WORLDLINE_STEP_RUN_UUID in encoded
    assert WORLDLINE_STEP_MODULE_KEY in encoded
    assert "channel-worldline" in encoded
    assert "model-worldline" in encoded
    assert "llm_tokens" in encoded
    assert '"prompt"' not in encoded
    for forbidden in ["sk-worldline", "credential_ref", "api_key", "source_text"]:
        assert forbidden not in encoded


def test_llm_facility_worldline_step_runner_rolls_back_postgres_completed_telemetry_when_usage_insert_fails() -> None:
    connection = FailingUsageInsertConnection()
    resolver = RecordingBindingResolver(_worldline_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-worldline")
    chat_client = RecordingJSONChatClient(
        response_json={
            "candidate_events": [
                {
                    "title": "城门协议被暂缓",
                    "summary": "谈判双方同意推迟城门控制权交接。",
                    "kind": "political_turn",
                }
            ],
            "__llm_usage": {
                "prompt_tokens": 13,
                "completion_tokens": 21,
            },
        }
    )
    candidate_writer = RecordingWorldlineCandidateEventWriter()
    runner = LLMFacilityWorldlineStepRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_event_writer=candidate_writer,
        telemetry_writer=PostgresLLMTelemetryWriter(connect=lambda: connection),
    )

    result = runner.run_step(
        context=_context(),
        session_id="session-1",
        mode="director",
        options={"goal": "推进一次单世界推演", "prompt": "隐藏指令"},
    )

    assert result == {
        "status": "failed",
        "error": {
            "code": "LLM_TELEMETRY_WRITE_FAILED",
            "message": "worldline completed telemetry write failed",
        },
    }
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed is True
    assert len(connection.cursor_obj.executions) == 2
    assert candidate_writer.calls == []
    encoded = json.dumps([result, connection.cursor_obj.executions, candidate_writer.calls], ensure_ascii=False, default=str)
    for forbidden in ["sk-worldline", "隐藏指令", "api_key", "sk-nope", "prompt=hidden", "credential_ref"]:
        assert forbidden not in encoded


def test_llm_facility_worldline_step_runner_records_total_token_usage_when_provider_omits_breakdown() -> None:
    resolver = RecordingBindingResolver(_worldline_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-worldline")
    chat_client = RecordingJSONChatClient(
        response_json={
            "candidate_events": [
                {
                    "title": "城门协议被暂缓",
                    "summary": "谈判双方同意推迟城门控制权交接。",
                    "kind": "political_turn",
                }
            ],
            "__llm_usage": {
                "total_tokens": 34,
            },
        }
    )
    telemetry_writer = RecordingLLMTelemetryWriter()
    runner = LLMFacilityWorldlineStepRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_event_writer=RecordingWorldlineCandidateEventWriter(),
        telemetry_writer=telemetry_writer,
    )

    result = runner.run_step(
        context=_context(),
        session_id="session-1",
        mode="director",
        options={"goal": "推进一次单世界推演"},
    )

    assert result["status"] == "completed"
    assert telemetry_writer.activities[0]["status"] == "completed"
    assert telemetry_writer.activities[0]["prompt_tokens"] is None
    assert telemetry_writer.activities[0]["completion_tokens"] is None
    assert telemetry_writer.usage_events == [
        {
            "context": _context(),
            "module_key": WORLDLINE_STEP_MODULE_KEY,
            "usage_type": "llm_tokens",
            "quantity": 34,
            "unit": "tokens",
            "metadata": {
                "channel_id": "channel-worldline",
                "model_id": "model-worldline",
                "provider": "openai-compatible",
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": 34,
                "cost_estimate": None,
            },
        }
    ]


def test_llm_facility_worldline_step_runner_records_failed_activity_without_usage() -> None:
    resolver = RecordingBindingResolver(_worldline_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-worldline")
    chat_client = RaisingJSONChatClient(RuntimeError("provider leaked sk-worldline prompt=隐藏指令"))
    candidate_writer = RecordingWorldlineCandidateEventWriter()
    telemetry_writer = RecordingLLMTelemetryWriter()
    runner = LLMFacilityWorldlineStepRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_event_writer=candidate_writer,
        telemetry_writer=telemetry_writer,
    )

    result = runner.run_step(
        context=_context(),
        session_id="session-1",
        mode="director",
        options={"goal": "推进一次单世界推演", "prompt": "隐藏指令"},
    )

    assert result == {
        "status": "failed",
        "error": {
            "code": "LLM_PROVIDER_ERROR",
            "message": "worldline provider call failed",
        },
    }
    assert telemetry_writer.activities == [
        {
            "context": _context(),
            "module_key": WORLDLINE_STEP_MODULE_KEY,
            "channel_id": "channel-worldline",
            "model_id": "model-worldline",
            "status": "failed",
            "prompt_tokens": None,
            "completion_tokens": None,
            "latency_ms": telemetry_writer.activities[0]["latency_ms"],
            "cost_estimate": None,
            "error": {"code": "LLM_PROVIDER_ERROR", "message": "worldline provider call failed"},
        }
    ]
    assert isinstance(telemetry_writer.activities[0]["latency_ms"], int)
    assert telemetry_writer.activities[0]["latency_ms"] >= 0
    assert telemetry_writer.usage_events == []
    assert candidate_writer.calls == []
    joined = json.dumps([result, telemetry_writer.activities, telemetry_writer.usage_events], ensure_ascii=False, default=str)
    for forbidden in ["sk-worldline", "隐藏指令", "provider leaked", "prompt=隐藏指令"]:
        assert forbidden not in joined


def test_llm_facility_worldline_step_runner_records_schema_failure_without_completed_usage() -> None:
    resolver = RecordingBindingResolver(_worldline_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-worldline")
    chat_client = RecordingJSONChatClient(
        response_json={
            "candidate_events": [
                {
                    "summary": "缺少 title，应被视为 schema failure。",
                    "kind": "political_turn",
                }
            ],
            "__llm_usage": {
                "prompt_tokens": 13,
                "completion_tokens": 21,
                "total_tokens": 34,
            },
        }
    )
    candidate_writer = RecordingWorldlineCandidateEventWriter()
    telemetry_writer = RecordingLLMTelemetryWriter()
    runner = LLMFacilityWorldlineStepRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_event_writer=candidate_writer,
        telemetry_writer=telemetry_writer,
    )

    result = runner.run_step(
        context=_context(),
        session_id="session-1",
        mode="director",
        options={"goal": "推进一次单世界推演"},
    )

    assert result == {
        "status": "failed",
        "error": {
            "code": "SCHEMA_VALIDATION_FAILED",
            "message": "title is required",
        },
    }
    assert candidate_writer.calls == []
    assert telemetry_writer.usage_events == []
    assert len(telemetry_writer.activities) == 1
    assert telemetry_writer.activities[0]["status"] == "failed"
    assert telemetry_writer.activities[0]["module_key"] == WORLDLINE_STEP_MODULE_KEY
    assert telemetry_writer.activities[0]["channel_id"] == "channel-worldline"
    assert telemetry_writer.activities[0]["model_id"] == "model-worldline"
    assert telemetry_writer.activities[0]["prompt_tokens"] is None
    assert telemetry_writer.activities[0]["completion_tokens"] is None
    assert telemetry_writer.activities[0]["error"] == {
        "code": "SCHEMA_VALIDATION_FAILED",
        "message": "title is required",
    }


def test_llm_facility_worldline_step_runner_fails_closed_when_completed_telemetry_write_fails() -> None:
    resolver = RecordingBindingResolver(_worldline_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-worldline")
    chat_client = RecordingJSONChatClient(
        response_json={
            "candidate_events": [
                {
                    "title": "城门协议被暂缓",
                    "summary": "谈判双方同意推迟城门控制权交接。",
                    "kind": "political_turn",
                }
            ],
            "__llm_usage": {
                "prompt_tokens": 13,
                "completion_tokens": 21,
            },
        }
    )
    candidate_writer = RecordingWorldlineCandidateEventWriter()
    telemetry_writer = FailingLLMTelemetryWriter()
    runner = LLMFacilityWorldlineStepRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_event_writer=candidate_writer,
        telemetry_writer=telemetry_writer,
    )

    result = runner.run_step(
        context=_context(),
        session_id="session-1",
        mode="director",
        options={"goal": "推进一次单世界推演", "prompt": "隐藏指令"},
    )

    assert result == {
        "status": "failed",
        "error": {
            "code": "LLM_TELEMETRY_WRITE_FAILED",
            "message": "worldline LLM activity write failed",
        },
    }
    assert candidate_writer.calls == []
    assert telemetry_writer.activity_calls == 1
    assert telemetry_writer.usage_calls == 0
    joined = json.dumps([result, candidate_writer.calls], ensure_ascii=False, default=str)
    for forbidden in ["sk-worldline", "隐藏指令", "prompt", "credential_ref"]:
        assert forbidden not in joined


def test_llm_facility_worldline_step_runner_sanitizes_unexpected_completed_telemetry_exception() -> None:
    resolver = RecordingBindingResolver(_worldline_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-worldline")
    chat_client = RecordingJSONChatClient(
        response_json={
            "candidate_events": [
                {
                    "title": "城门协议被暂缓",
                    "summary": "谈判双方同意推迟城门控制权交接。",
                    "kind": "political_turn",
                }
            ],
            "__llm_usage": {
                "prompt_tokens": 13,
                "completion_tokens": 21,
            },
        }
    )
    candidate_writer = RecordingWorldlineCandidateEventWriter()
    telemetry_writer = RaisingLLMTelemetryWriter(
        RuntimeError("telemetry failed prompt=隐藏指令 api_key=sk-nope credential_ref=secret")
    )
    runner = LLMFacilityWorldlineStepRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_event_writer=candidate_writer,
        telemetry_writer=telemetry_writer,
    )

    result = runner.run_step(
        context=_context(),
        session_id="session-1",
        mode="director",
        options={"goal": "推进一次单世界推演", "prompt": "隐藏指令"},
    )

    assert result == {
        "status": "failed",
        "error": {
            "code": "LLM_TELEMETRY_WRITE_FAILED",
            "message": "worldline completed telemetry write failed",
        },
    }
    assert telemetry_writer.activity_calls == 1
    assert telemetry_writer.usage_calls == 0
    assert candidate_writer.calls == []
    joined = json.dumps([result, candidate_writer.calls], ensure_ascii=False, default=str)
    for forbidden in ["sk-worldline", "隐藏指令", "sk-nope", "prompt=", "api_key", "credential_ref"]:
        assert forbidden not in joined


def test_llm_facility_worldline_step_runner_does_not_record_failed_llm_activity_after_candidate_write_failure() -> None:
    resolver = RecordingBindingResolver(_worldline_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-worldline")
    chat_client = RecordingJSONChatClient(
        response_json={
            "candidate_events": [
                {
                    "title": "城门协议被暂缓",
                    "summary": "谈判双方同意推迟城门控制权交接。",
                    "kind": "political_turn",
                }
            ],
            "__llm_usage": {
                "prompt_tokens": 13,
                "completion_tokens": 21,
            },
        }
    )
    candidate_writer = FailingWorldlineCandidateEventWriter()
    telemetry_writer = RecordingLLMTelemetryWriter()
    runner = LLMFacilityWorldlineStepRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_event_writer=candidate_writer,
        telemetry_writer=telemetry_writer,
    )

    result = runner.run_step(
        context=_context(),
        session_id="missing-session",
        mode="director",
        options={"goal": "推进一次单世界推演", "prompt": "隐藏指令"},
    )

    assert result == {
        "status": "failed",
        "error": {
            "code": "WORLDLINE_SESSION_NOT_FOUND",
            "message": "worldline session was not admitted for this tenant/project",
        },
    }
    assert len(candidate_writer.calls) == 1
    assert telemetry_writer.activities == [
        {
            "context": _context(),
            "module_key": WORLDLINE_STEP_MODULE_KEY,
            "channel_id": "channel-worldline",
            "model_id": "model-worldline",
            "status": "completed",
            "prompt_tokens": 13,
            "completion_tokens": 21,
            "latency_ms": telemetry_writer.activities[0]["latency_ms"],
            "cost_estimate": None,
            "error": None,
        }
    ]
    assert telemetry_writer.usage_events == [
        {
            "context": _context(),
            "module_key": WORLDLINE_STEP_MODULE_KEY,
            "usage_type": "llm_tokens",
            "quantity": 34,
            "unit": "tokens",
            "metadata": {
                "channel_id": "channel-worldline",
                "model_id": "model-worldline",
                "provider": "openai-compatible",
                "prompt_tokens": 13,
                "completion_tokens": 21,
                "total_tokens": None,
                "cost_estimate": None,
            },
        }
    ]
    joined = json.dumps([result, telemetry_writer.activities, telemetry_writer.usage_events], ensure_ascii=False, default=str)
    for forbidden in ["sk-worldline", "隐藏指令", "credential_ref"]:
        assert forbidden not in joined


def test_llm_facility_worldline_step_runner_sanitizes_unexpected_candidate_write_exception() -> None:
    resolver = RecordingBindingResolver(_worldline_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-worldline")
    chat_client = RecordingJSONChatClient(
        response_json={
            "candidate_events": [
                {
                    "title": "城门协议被暂缓",
                    "summary": "谈判双方同意推迟城门控制权交接。",
                    "kind": "political_turn",
                }
            ],
            "__llm_usage": {
                "prompt_tokens": 13,
                "completion_tokens": 21,
            },
        }
    )
    candidate_writer = RaisingWorldlineCandidateEventWriter(
        RuntimeError("candidate insert leaked prompt=隐藏指令 api_key=sk-nope credential_ref=secret")
    )
    telemetry_writer = RecordingLLMTelemetryWriter()
    runner = LLMFacilityWorldlineStepRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_event_writer=candidate_writer,
        telemetry_writer=telemetry_writer,
    )

    result = runner.run_step(
        context=_context(),
        session_id="session-1",
        mode="director",
        options={"goal": "推进一次单世界推演", "prompt": "隐藏指令"},
    )

    assert result == {
        "status": "failed",
        "error": {
            "code": "WORLDLINE_CANDIDATE_EVENT_WRITE_FAILED",
            "message": "worldline candidate event write failed",
        },
    }
    assert len(candidate_writer.calls) == 1
    assert [activity["status"] for activity in telemetry_writer.activities] == ["completed"]
    assert telemetry_writer.usage_events[0]["quantity"] == 34
    joined = json.dumps([result, telemetry_writer.activities, telemetry_writer.usage_events], ensure_ascii=False, default=str)
    for forbidden in ["sk-worldline", "隐藏指令", "sk-nope", "prompt=", "api_key", "credential_ref"]:
        assert forbidden not in joined


def test_llm_facility_worldline_step_runner_redacts_provider_exception_message() -> None:
    resolver = RecordingBindingResolver(_worldline_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-worldline")
    chat_client = RaisingJSONChatClient(
        RuntimeError("provider 500 leaked sk-worldline prompt=隐藏指令 source_text=私有素材")
    )
    writer = RecordingWorldlineCandidateEventWriter()
    runner = LLMFacilityWorldlineStepRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        candidate_event_writer=writer,
    )

    result = runner.run_step(
        context=_context(),
        session_id="session-1",
        mode="director",
        options={"goal": "推进一次单世界推演", "prompt": "隐藏指令", "source_text": "私有素材"},
    )

    assert result == {
        "status": "failed",
        "error": {
            "code": "LLM_PROVIDER_ERROR",
            "message": "worldline provider call failed",
        },
    }
    assert resolver.calls == [WORLDLINE_STEP_MODULE_KEY]
    assert credentials.calls == ["channel-worldline"]
    assert chat_client.calls[0]["api_key"] == "sk-worldline"
    assert writer.calls == []
    joined = json.dumps([result, chat_client.calls[0]["messages"], writer.calls], ensure_ascii=False, default=str)
    for forbidden in ["sk-worldline", "隐藏指令", "私有素材", "provider 500 leaked", "prompt=隐藏指令", "source_text"]:
        assert forbidden not in joined


def test_postgres_worldline_candidate_event_writer_inserts_only_public_metadata() -> None:
    connection = RecordingConnection()
    writer = PostgresWorldlineCandidateEventWriter(connect=lambda: connection)

    result = writer.write_candidate_events(
        context=_context(),
        session_id="session-1",
        source_run_id=WORLDLINE_STEP_RUN_UUID,
        model_id="model-worldline",
        mode="director",
        events=[
            {
                "title": "雨夜谈判破裂",
                "summary": "主角拒绝让渡城门控制权。",
                "kind": "political_turn",
                "confidence": 0.82,
                "involved_agent_ids": ["agent-1"],
                "state_change_summary": "联盟信任下降。",
                "event_body": "不得入库",
                "api_key": "sk-nope",
                "credential_ref": "secret-ref",
            }
        ],
    )

    assert result == {"status": "completed", "candidate_event_count": 1}
    assert connection.commits == 1
    assert connection.closed is True
    assert len(connection.cursor_obj.executions) == 1
    sql, params = connection.cursor_obj.executions[0]
    assert "worldline_events" in sql
    encoded = json.dumps(params, ensure_ascii=False, default=str)
    assert "雨夜谈判破裂" in encoded
    assert "political_turn" in encoded
    for forbidden in ["不得入库", "sk-nope", "secret-ref", "event_body", "api_key", "credential_ref"]:
        assert forbidden not in encoded


def test_postgres_worldline_candidate_event_writer_scopes_insert_to_admitted_session() -> None:
    connection = RecordingConnection()
    writer = PostgresWorldlineCandidateEventWriter(connect=lambda: connection)

    writer.write_candidate_events(
        context=_context(),
        session_id="session-1",
        source_run_id=WORLDLINE_STEP_RUN_UUID,
        model_id="model-worldline",
        mode="director",
        events=[
            {
                "title": "雨夜谈判破裂",
                "summary": "主角拒绝让渡城门控制权。",
                "kind": "political_turn",
            }
        ],
    )

    sql = connection.cursor_obj.executions[0][0].lower()
    assert "worldline_sessions" in sql
    assert "worldline_sessions.tenant_id" in sql
    assert "worldline_sessions.project_id" in sql
    assert "worldline_sessions.session_id" in sql


def test_postgres_worldline_candidate_event_writer_rolls_back_when_session_scope_missing() -> None:
    connection = MissingSessionCandidateConnection()
    writer = PostgresWorldlineCandidateEventWriter(connect=lambda: connection)

    try:
        writer.write_candidate_events(
            context=_context(),
            session_id="missing-session",
            source_run_id=WORLDLINE_STEP_RUN_UUID,
            model_id="model-worldline",
            mode="director",
            events=[
                {
                    "title": "雨夜谈判破裂",
                    "summary": "主角拒绝让渡城门控制权。",
                    "kind": "political_turn",
                }
            ],
        )
    except LLMFacilityError as exc:
        assert exc.code == "WORLDLINE_SESSION_NOT_FOUND"
        assert exc.message == "worldline session was not admitted for this tenant/project"
    else:
        raise AssertionError("expected missing admitted session to fail closed")

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed is True
    encoded = json.dumps(connection.cursor_obj.executions, ensure_ascii=False, default=str)
    assert "missing-session" in encoded
    for forbidden in ["api_key", "credential_ref", "prompt", "source_text"]:
        assert forbidden not in encoded


def test_postgres_worldline_candidate_event_writer_rejects_non_uuid_source_run_id() -> None:
    connection = RecordingConnection()
    writer = PostgresWorldlineCandidateEventWriter(connect=lambda: connection)

    try:
        writer.write_candidate_events(
            context=_context(),
            session_id="session-1",
            source_run_id="run-worldline-step-1",
            model_id="model-worldline",
            mode="director",
            events=[
                {
                    "title": "雨夜谈判破裂",
                    "summary": "主角拒绝让渡城门控制权。",
                    "kind": "political_turn",
                }
            ],
        )
    except LLMFacilityError as exc:
        assert exc.code == "VALIDATION_FAILED"
        assert exc.message == "source_run_id must be a valid UUID"
    else:
        raise AssertionError("expected invalid source_run_id to fail closed")

    assert connection.cursor_obj.executions == []
    assert connection.commits == 0
    assert connection.closed is False


def test_postgres_worldline_candidate_event_writer_sanitizes_db_exception_message() -> None:
    connection = FailingCandidateInsertConnection()
    writer = PostgresWorldlineCandidateEventWriter(connect=lambda: connection)

    try:
        writer.write_candidate_events(
            context=_context(),
            session_id="session-1",
            source_run_id=WORLDLINE_STEP_RUN_UUID,
            model_id="model-worldline",
            mode="director",
            events=[
                {
                    "title": "雨夜谈判破裂",
                    "summary": "主角拒绝让渡城门控制权。",
                    "kind": "political_turn",
                    "prompt": "hidden prompt",
                    "api_key": "sk-hidden",
                    "credential_ref": "hidden-ref",
                }
            ],
        )
    except LLMFacilityError as exc:
        assert exc.code == "WORLDLINE_CANDIDATE_EVENT_WRITE_FAILED"
        assert exc.message == "worldline candidate event write failed"
    else:
        raise AssertionError("expected candidate event write failure")

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed is True
    encoded = json.dumps(connection.cursor_obj.executions, ensure_ascii=False, default=str)
    assert "雨夜谈判破裂" in encoded
    for forbidden in [
        "candidate insert failed",
        "prompt=hidden",
        "api_key=sk-nope",
        "credential_ref=secret-ref",
        "hidden prompt",
        "sk-hidden",
        "hidden-ref",
    ]:
        assert forbidden not in encoded


def test_postgres_llm_telemetry_writer_records_activity_and_usage_without_credential_material() -> None:
    connection = RecordingConnection()
    writer = PostgresLLMTelemetryWriter(connect=lambda: connection)

    writer.record_llm_activity(
        context=_context(),
        module_key=WORLDLINE_STEP_MODULE_KEY,
        channel_id="channel-worldline",
        model_id="model-worldline",
        status="completed",
        prompt_tokens=13,
        completion_tokens=21,
        latency_ms=123,
        cost_estimate=0.0042,
        error=None,
    )
    writer.record_usage_event(
        context=_context(),
        module_key=WORLDLINE_STEP_MODULE_KEY,
        usage_type="llm_tokens",
        quantity=34,
        unit="tokens",
        metadata={
            "channel_id": "channel-worldline",
            "model_id": "model-worldline",
            "provider": "openai-compatible",
            "prompt_tokens": 13,
            "completion_tokens": 21,
            "credential_ref": "secret-ref",
            "api_key": "sk-nope",
        },
    )

    assert connection.commits == 2
    assert connection.closed is True
    assert len(connection.cursor_obj.executions) == 2
    assert "INSERT INTO llm_activity" in connection.cursor_obj.executions[0][0]
    assert "INSERT INTO usage_events" in connection.cursor_obj.executions[1][0]
    encoded = json.dumps(connection.cursor_obj.executions, ensure_ascii=False, default=str)
    assert "channel-worldline" in encoded
    assert "model-worldline" in encoded
    assert "llm_tokens" in encoded
    for forbidden in ["secret-ref", "sk-nope", "credential_ref", "api_key", "encrypted_api_key"]:
        assert forbidden not in encoded


def test_postgres_llm_telemetry_writer_rolls_back_when_activity_insert_fails() -> None:
    connection = FailingActivityInsertConnection()
    writer = PostgresLLMTelemetryWriter(connect=lambda: connection)

    try:
        writer.record_llm_activity(
            context=_context(),
            module_key=WORLDLINE_STEP_MODULE_KEY,
            channel_id="channel-worldline",
            model_id="model-worldline",
            status="failed",
            error={
                "code": "LLM_PROVIDER_ERROR",
                "message": "provider failed",
                "api_key": "sk-input",
                "prompt": "private worldline prompt",
                "credential_ref": "secret-ref",
            },
        )
    except LLMFacilityError as exc:
        assert exc.code == "LLM_TELEMETRY_WRITE_FAILED"
        assert exc.message == "worldline LLM activity write failed"
    else:
        raise AssertionError("expected activity insert failure")

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed is True
    assert len(connection.cursor_obj.executions) == 1
    encoded = json.dumps(connection.cursor_obj.executions, ensure_ascii=False, default=str)
    assert "LLM_PROVIDER_ERROR" in encoded
    for forbidden in ["sk-input", "private worldline prompt", "secret-ref", "sk-nope", "prompt=hidden", "credential_ref"]:
        assert forbidden not in encoded


def test_postgres_llm_telemetry_writer_rolls_back_when_usage_insert_fails() -> None:
    connection = FailingUsageInsertConnection()
    writer = PostgresLLMTelemetryWriter(connect=lambda: connection)

    try:
        writer.record_usage_event(
            context=_context(),
            module_key=WORLDLINE_STEP_MODULE_KEY,
            usage_type="llm_tokens",
            quantity=34,
            unit="tokens",
            metadata={
                "channel_id": "channel-worldline",
                "model_id": "model-worldline",
                "provider": "openai-compatible",
                "api_key": "sk-input",
                "prompt": "private usage prompt",
                "credential_ref": "secret-ref",
            },
        )
    except LLMFacilityError as exc:
        assert exc.code == "LLM_TELEMETRY_WRITE_FAILED"
        assert exc.message == "worldline usage event write failed"
    else:
        raise AssertionError("expected usage insert failure")

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed is True
    assert len(connection.cursor_obj.executions) == 1
    encoded = json.dumps(connection.cursor_obj.executions, ensure_ascii=False, default=str)
    assert "llm_tokens" in encoded
    for forbidden in ["sk-input", "private usage prompt", "secret-ref", "sk-nope", "prompt=hidden", "credential_ref"]:
        assert forbidden not in encoded


def test_postgres_llm_telemetry_writer_sanitizes_activity_error_payload_before_insert() -> None:
    connection = RecordingConnection()
    writer = PostgresLLMTelemetryWriter(connect=lambda: connection)

    writer.record_llm_activity(
        context=_context(),
        module_key=WORLDLINE_STEP_MODULE_KEY,
        channel_id="channel-worldline",
        model_id="model-worldline",
        status="failed",
        error={
            "code": "LLM_PROVIDER_ERROR",
            "message": "provider failed",
            "api_key": "sk-nope",
            "prompt": "private worldline prompt",
            "nested": {
                "credential_ref": "secret-ref",
                "safe": "visible",
            },
        },
    )

    assert connection.commits == 1
    encoded = json.dumps(connection.cursor_obj.executions[0][1], ensure_ascii=False, default=str)
    assert "LLM_PROVIDER_ERROR" in encoded
    assert "provider failed" in encoded
    assert "visible" in encoded
    for forbidden in [
        "sk-nope",
        "private worldline prompt",
        "secret-ref",
        "api_key",
        "prompt",
        "credential_ref",
    ]:
        assert forbidden not in encoded


def test_postgres_workflow_event_writer_rolls_back_and_sanitizes_error_when_insert_fails() -> None:
    connection = FailingWorkflowEventInsertConnection()
    writer = PostgresWorkflowEventWriter(connect=lambda: connection)

    try:
        writer.write_event(
            tenant_id="tenant-1",
            project_id="project-1",
            run_id=WORLDLINE_STEP_RUN_UUID,
            event_type="worldline.stage.failed",
            payload={
                "status": "failed",
                "error_code": "LLM_PROVIDER_ERROR",
                "prompt": "private prompt",
                "api_key": "sk-input",
                "credential_ref": "secret-ref",
            },
        )
    except RuntimeError as exc:
        assert str(exc) == "WORKFLOW_EVENT_WRITE_FAILED: worldline workflow event write failed"
    else:
        raise AssertionError("expected workflow event write failure")

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed is True
    assert len(connection.cursor_obj.executions) == 1
    encoded = json.dumps(connection.cursor_obj.executions, ensure_ascii=False, default=str)
    assert "worldline.stage.failed" in encoded
    assert "LLM_PROVIDER_ERROR" in encoded
    for forbidden in ["private prompt", "sk-input", "secret-ref", "prompt=hidden", "sk-nope", "credential_ref"]:
        assert forbidden not in encoded


def test_postgres_workflow_event_writer_rolls_back_when_admission_parent_missing() -> None:
    connection = MissingWorkflowEventParentConnection()
    writer = PostgresWorkflowEventWriter(connect=lambda: connection)

    try:
        writer.write_event(
            tenant_id="tenant-1",
            project_id="project-1",
            run_id=WORLDLINE_STEP_RUN_UUID,
            event_type="worldline.stage.completed",
            payload={
                "status": "completed",
                "session_id": "session-1",
                "candidate_event_count": 1,
                "prompt": "private prompt",
                "api_key": "sk-input",
                "credential_ref": "secret-ref",
            },
        )
    except RuntimeError as exc:
        assert str(exc) == "WORKFLOW_RUN_NOT_FOUND: worldline step admission parent row is missing"
    else:
        raise AssertionError("expected missing workflow parent to fail closed")

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed is True
    assert len(connection.cursor_obj.executions) == 1
    encoded = json.dumps(connection.cursor_obj.executions, ensure_ascii=False, default=str)
    assert "worldline.stage.completed" in encoded
    assert "session-1" in encoded
    for forbidden in ["private prompt", "sk-input", "secret-ref", "api_key", "credential_ref"]:
        assert forbidden not in encoded


def test_postgres_workflow_status_writer_rolls_back_and_sanitizes_error_when_update_fails() -> None:
    connection = FailingWorkflowStatusUpdateConnection()
    writer = PostgresWorkflowRunStatusWriter(connect=lambda: connection)

    try:
        writer.mark_failed(
            context=_context(),
            code="LLM_PROVIDER_ERROR",
            message="worldline provider call failed",
        )
    except RuntimeError as exc:
        assert str(exc) == "WORKFLOW_STATUS_WRITE_FAILED: worldline workflow status write failed"
    else:
        raise AssertionError("expected workflow status write failure")

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed is True
    assert len(connection.cursor_obj.executions) == 1
    encoded = json.dumps(connection.cursor_obj.executions, ensure_ascii=False, default=str)
    assert "LLM_PROVIDER_ERROR" in encoded
    assert "worldline provider call failed" in encoded
    for forbidden in ["prompt=hidden", "sk-nope", "credential_ref=secret", "api_key"]:
        assert forbidden not in encoded


def test_postgres_workflow_status_writer_rolls_back_when_admission_parent_missing() -> None:
    connection = MissingWorkflowStatusParentConnection()
    writer = PostgresWorkflowRunStatusWriter(connect=lambda: connection)

    try:
        writer.mark_completed(
            context=_context(),
            result={
                "status": "completed",
                "session_id": "session-1",
                "mode": "director",
                "candidate_event_count": 1,
                "prompt": "private prompt",
                "api_key": "sk-input",
                "credential_ref": "secret-ref",
            },
        )
    except RuntimeError as exc:
        assert str(exc) == "WORKFLOW_RUN_NOT_FOUND: worldline step admission parent row is missing"
    else:
        raise AssertionError("expected missing workflow parent to fail closed")

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed is True
    assert len(connection.cursor_obj.executions) == 1
    encoded = json.dumps(connection.cursor_obj.executions, ensure_ascii=False, default=str)
    assert "completed" in encoded
    assert "session-1" in encoded
    for forbidden in ["private prompt", "sk-input", "secret-ref", "api_key", "credential_ref"]:
        assert forbidden not in encoded


def test_worldline_step_activity_fails_closed_without_runner_and_sanitizes_payload() -> None:
    event_writer = RecordingWorkflowEventWriter()
    status_writer = RecordingWorkflowRunStatusWriter()

    result = worldline_step_activity(
        _payload(),
        step_runner=None,
        workflow_event_writer=event_writer,
        workflow_status_writer=status_writer,
    )

    assert result["status"] == "failed"
    assert result["workflow_type"] == "worldline_step"
    assert result["stage"] == "worldline_step"
    assert result["module_key"] == WORLDLINE_STEP_MODULE_KEY
    assert result["session_id"] == "session-1"
    assert result["mode"] == "director"
    assert result["error"]["code"] == "WORLDLINE_STEP_RUNNER_UNCONFIGURED"
    assert result["stage_event_persisted"] is True
    assert result["workflow_status_persisted"] is True
    assert status_writer.failed == [
        {
            "context": _context(),
            "code": "WORLDLINE_STEP_RUNNER_UNCONFIGURED",
            "message": "worldline step runner requires a configured director runtime",
        }
    ]
    assert status_writer.completed == []
    assert event_writer.events[0]["event_type"] == "worldline.stage.failed"
    assert event_writer.events[0]["payload"]["stage"] == "worldline_step"

    joined = json.dumps([result, event_writer.events, status_writer.failed], ensure_ascii=False, default=str)
    for forbidden in [
        "这段 prompt",
        "世界线私有素材",
        "secret-ref",
        "正文草稿",
        "prompt",
        "source_text",
        "credential_ref",
        "draft",
        "api_key",
        "encrypted_api_key",
        "body_text",
        "content_text",
        "manuscript",
    ]:
        assert forbidden not in joined


def test_worldline_step_activity_requires_director_permission() -> None:
    context = _context().model_copy(update={"permissions": {}})
    event_writer = RecordingWorkflowEventWriter()
    status_writer = RecordingWorkflowRunStatusWriter()

    result = worldline_step_activity(
        {"context": context.model_dump(), "session_id": "session-1", "mode": "director"},
        step_runner=None,
        workflow_event_writer=event_writer,
        workflow_status_writer=status_writer,
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "FORBIDDEN"
    assert status_writer.failed[0]["code"] == "FORBIDDEN"
    assert event_writer.events[0]["payload"]["error_code"] == "FORBIDDEN"


def test_worldline_step_activity_preserves_llm_facility_runner_error_code() -> None:
    event_writer = RecordingWorkflowEventWriter()
    status_writer = RecordingWorkflowRunStatusWriter()

    result = worldline_step_activity(
        _payload({"goal": "推进一次单世界推演"}),
        step_runner=RaisingWorldlineStepRunner(
            LLMFacilityError("LLM_MODULE_UNBOUND", "worldline_director module is not bound")
        ),
        workflow_event_writer=event_writer,
        workflow_status_writer=status_writer,
    )

    assert result["status"] == "failed"
    assert result["error"] == {
        "code": "LLM_MODULE_UNBOUND",
        "message": "worldline_director module is not bound",
    }
    assert result["stage_event_persisted"] is True
    assert result["workflow_status_persisted"] is True
    assert status_writer.failed == [
        {
            "context": _context(),
            "code": "LLM_MODULE_UNBOUND",
            "message": "worldline_director module is not bound",
        }
    ]
    assert status_writer.completed == []
    assert event_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": WORLDLINE_STEP_RUN_UUID,
            "event_type": "worldline.stage.failed",
            "payload": {
                "stage": "worldline_step",
                "activity": "worldline_step_activity",
                "status": "failed",
                "module_key": WORLDLINE_STEP_MODULE_KEY,
                "session_id": "session-1",
                "mode": "director",
                "error_code": "LLM_MODULE_UNBOUND",
                "message": "worldline_director module is not bound",
            },
        }
    ]


def test_worldline_step_activity_writes_completed_event_and_status_without_private_payload() -> None:
    event_writer = RecordingWorkflowEventWriter()
    status_writer = RecordingWorkflowRunStatusWriter()

    result = worldline_step_activity(
        _payload({"prompt": "hidden prompt", "credential_ref": "hidden-ref"}),
        step_runner=SuccessfulWorldlineStepRunner(),
        workflow_event_writer=event_writer,
        workflow_status_writer=status_writer,
    )

    assert result["status"] == "completed"
    assert result["candidate_event_count"] == 1
    assert result["workflow_status_persisted"] is True
    assert result["stage_event_persisted"] is True
    assert status_writer.completed == [
        {
            "context": _context(),
            "result": {
                "session_id": "session-1",
                "mode": "director",
                "step": 3,
                "candidate_event_count": 1,
                "model_id": "model-worldline",
            },
        }
    ]
    assert status_writer.failed == []
    assert event_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": WORLDLINE_STEP_RUN_UUID,
            "event_type": "worldline.stage.completed",
            "payload": {
                "stage": "worldline_step",
                "activity": "worldline_step_activity",
                "status": "completed",
                "module_key": WORLDLINE_STEP_MODULE_KEY,
                "session_id": "session-1",
                "mode": "director",
                "step": 3,
                "candidate_event_count": 1,
                "model_id": "model-worldline",
            },
        }
    ]
    joined = json.dumps([result, event_writer.events, status_writer.completed], ensure_ascii=False, default=str)
    for forbidden in ["hidden prompt", "hidden-ref", "must not be persisted", "secret-ref", "private event body"]:
        assert forbidden not in joined


def test_worldline_step_activity_runs_db_backed_success_chain_under_same_run_id() -> None:
    database = WorldlineStepChainDatabase()
    decryptor = AesGcmCredentialDecryptor(
        key_material="000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
    )
    chat_client = LedgerJSONChatClient(
        response_json={
            "candidate_events": [
                {
                    "title": "城门协议被暂缓",
                    "summary": "谈判双方同意推迟城门控制权交接。",
                    "kind": "political_turn",
                    "confidence": 0.72,
                    "involved_agent_ids": ["agent-1", "agent-2"],
                    "state_change_summary": "联盟保持脆弱停火。",
                    "event_body": "完整事件正文不得公开",
                    "api_key": "sk-nope",
                    "credential_ref": "secret-ref",
                }
            ],
            "__llm_usage": {
                "prompt_tokens": 13,
                "completion_tokens": 21,
                "total_tokens": 34,
                "cost_estimate": 0.0042,
            },
        },
        ledger=database.executions,
    )
    runner = LLMFacilityWorldlineStepRunner(
        binding_resolver=PostgresModuleBindingResolver(connect=database.connect),
        credential_provider=PostgresCredentialProvider(connect=database.connect, decryptor=decryptor),
        chat_client=chat_client,
        candidate_event_writer=PostgresWorldlineCandidateEventWriter(connect=database.connect),
        telemetry_writer=PostgresLLMTelemetryWriter(connect=database.connect),
    )

    result = worldline_step_activity(
        _payload({"step": 4, "goal": "推进一次单世界推演", "prompt": "隐藏用户指令"}),
        step_runner=runner,
        workflow_event_writer=PostgresWorkflowEventWriter(connect=database.connect),
        workflow_status_writer=PostgresWorkflowRunStatusWriter(connect=database.connect),
    )

    assert result == {
        "tenant_id": "tenant-1",
        "project_id": "project-1",
        "run_id": WORLDLINE_STEP_RUN_UUID,
        "trace_id": "trace-worldline-step-1",
        "module_key": WORLDLINE_STEP_MODULE_KEY,
        "actor_user_id": "user-1",
        "workflow_type": "worldline_step",
        "status": "completed",
        "stage": "worldline_step",
        "session_id": "session-1",
        "mode": "director",
        "step": 4,
        "candidate_event_count": 1,
        "model_id": "model-worldline",
        "workflow_status_persisted": True,
        "stage_event_persisted": True,
    }
    assert chat_client.calls[0]["api_key"] == "sk-seed-live"
    operations = [
        "binding"
        if "FROM llm_module_bindings" in item["sql"]
        else "credential"
        if "SELECT encrypted_api_key" in item["sql"]
        else "provider"
        if item["sql"] == "PROVIDER complete_json"
        else "llm_activity"
        if "INSERT INTO llm_activity" in item["sql"]
        else "usage"
        if "INSERT INTO usage_events" in item["sql"]
        else "candidate"
        if "INSERT INTO worldline_events" in item["sql"]
        else "workflow_event"
        if "INSERT INTO workflow_events" in item["sql"]
        else "workflow_status"
        if "UPDATE workflow_runs" in item["sql"]
        else "other"
        for item in database.executions
    ]
    assert operations == [
        "binding",
        "credential",
        "provider",
        "llm_activity",
        "usage",
        "candidate",
        "workflow_event",
        "workflow_status",
    ]
    encoded = json.dumps(database.executions + [result], ensure_ascii=False, default=str)
    assert WORLDLINE_STEP_RUN_UUID in encoded
    assert "worldline_director" in encoded
    assert "worldline_events" in encoded
    assert "workflow_events" in encoded
    assert "workflow_runs" in encoded
    assert "llm_tokens" in encoded
    assert "candidate" in encoded
    for forbidden in [
        "完整事件正文",
        "隐藏用户指令",
        "sk-seed-live",
        "sk-nope",
        "secret-ref",
        "credential_ref",
        "event_body",
    ]:
        assert forbidden not in encoded
    assert all(connection.closed for connection in database.connections)
    assert sum(connection.rollbacks for connection in database.connections) == 0


def test_worldline_step_activity_returns_structured_failure_when_completed_event_write_fails() -> None:
    event_writer = RaisingWorkflowEventWriter(
        RuntimeError("WORKFLOW_EVENT_WRITE_FAILED: worldline workflow event write failed")
    )
    status_writer = RecordingWorkflowRunStatusWriter()

    result = worldline_step_activity(
        _payload({"prompt": "hidden prompt", "api_key": "sk-hidden"}),
        step_runner=SuccessfulWorldlineStepRunner(),
        workflow_event_writer=event_writer,
        workflow_status_writer=status_writer,
    )

    assert result["status"] == "failed"
    assert result["error"] == {
        "code": "WORKFLOW_EVENT_WRITE_FAILED",
        "message": "worldline workflow event write failed",
    }
    assert result["stage_event_persisted"] is False
    assert result["workflow_status_persisted"] is True
    assert status_writer.completed == []
    assert status_writer.failed == [
        {
            "context": _context(),
            "code": "WORKFLOW_EVENT_WRITE_FAILED",
            "message": "worldline workflow event write failed",
        }
    ]
    assert event_writer.calls[0]["event_type"] == "worldline.stage.completed"
    joined = json.dumps([result, event_writer.calls, status_writer.failed], ensure_ascii=False, default=str)
    for forbidden in ["hidden prompt", "sk-hidden", "must not be persisted", "secret-ref", "private event body"]:
        assert forbidden not in joined


def test_worldline_step_activity_sanitizes_completed_persistence_error_message() -> None:
    event_writer = RaisingWorkflowEventWriter(
        RuntimeError(
            "WORKFLOW_EVENT_WRITE_FAILED: writer failed with prompt=hidden api_key=sk-hidden credential_ref=secret"
        )
    )
    status_writer = RecordingWorkflowRunStatusWriter()

    result = worldline_step_activity(
        _payload({"prompt": "hidden prompt", "api_key": "sk-hidden", "credential_ref": "secret"}),
        step_runner=SuccessfulWorldlineStepRunner(),
        workflow_event_writer=event_writer,
        workflow_status_writer=status_writer,
    )

    assert result["status"] == "failed"
    assert result["error"] == {
        "code": "WORKFLOW_EVENT_WRITE_FAILED",
        "message": "worldline workflow event write failed",
    }
    assert status_writer.failed == [
        {
            "context": _context(),
            "code": "WORKFLOW_EVENT_WRITE_FAILED",
            "message": "worldline workflow event write failed",
        }
    ]
    joined = json.dumps([result, status_writer.failed, event_writer.calls], ensure_ascii=False, default=str)
    for forbidden in [
        "prompt=hidden",
        "api_key",
        "sk-hidden",
        "credential_ref",
        "secret",
        "hidden prompt",
        "must not be persisted",
        "private event body",
    ]:
        assert forbidden not in joined


def test_worldline_step_local_workflow_uses_fail_closed_activity() -> None:
    result = run_worldline_step_workflow_locally(
        _payload({"prompt": "hidden"}),
        workflow_event_writer=RecordingWorkflowEventWriter(),
        workflow_status_writer=RecordingWorkflowRunStatusWriter(),
    )

    assert result["status"] == "failed"
    assert result["workflow_type"] == "worldline_step"
    assert result["error"]["code"] == "WORLDLINE_STEP_RUNNER_UNCONFIGURED"


def test_worldline_worker_spec_registers_temporal_workflow_and_activity() -> None:
    spec = worker_spec()

    assert spec["task_queue"] == WORLDLINE_TASK_QUEUE
    assert "WorldlineStepWorkflow" in spec["workflows"]
    assert "worldline_step_activity" in spec["activities"]


def test_temporal_worldline_worker_registers_step_activity() -> None:
    components = worker_components_for_task_queue(WORLDLINE_TASK_QUEUE)

    assert [workflow.__name__ for workflow in components["workflows"]] == ["WorldlineStepWorkflow"]
    assert [activity.__name__ for activity in components["activities"]] == ["worldline_step_activity"]
