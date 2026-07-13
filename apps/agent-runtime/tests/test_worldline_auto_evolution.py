from __future__ import annotations

import json
from typing import Any

from mirofish_agents.common.context import AgentContext
from mirofish_agents.seed.sequential_reader import ModuleBindingResolution
from mirofish_agents.temporal.worldline import (
    LLMFacilityWorldlineStepRunner,
    PostgresWorkflowEventWriter,
    PostgresWorkflowRunStatusWriter,
    PostgresWorldlineCandidateEventWriter,
    WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE,
    WORLDLINE_STEP_MODULE_KEY,
    WORLDLINE_TASK_QUEUE,
    worker_spec,
)
from mirofish_agents.temporal.worker import worker_components_for_task_queue
from mirofish_agents.temporal.worldline_auto_evolution import (
    WORLDLINE_AUTO_EVOLUTION_WORLD_SCOPE,
    WorldlineAutoEvolutionWorkflow,
    run_worldline_auto_evolution_workflow_locally,
    worldline_auto_evolution_finalize_activity,
    worldline_auto_evolution_step_activity,
)


TENANT_ID = "11111111-1111-1111-1111-111111111111"
PROJECT_ID = "22222222-2222-2222-2222-222222222222"
RUN_ID = "33333333-3333-3333-3333-333333333333"
ACTOR_ID = "44444444-4444-4444-4444-444444444444"
SESSION_ID = "55555555-5555-5555-5555-555555555555"


def _context(*, permitted: bool = True) -> AgentContext:
    permissions = {WORLDLINE_STEP_MODULE_KEY: ["run"]} if permitted else {}
    return AgentContext(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        workflow_type=WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE,
        actor_user_id=ACTOR_ID,
        module_key=WORLDLINE_STEP_MODULE_KEY,
        trace_id="trace-auto-evolution",
        permissions=permissions,
    )


def _payload(*, max_steps: int = 3, permitted: bool = True) -> dict[str, Any]:
    return {
        "context": _context(permitted=permitted).model_dump(),
        "session_id": SESSION_ID,
        "max_steps": max_steps,
        "world_scope": WORLDLINE_AUTO_EVOLUTION_WORLD_SCOPE,
        "request_id": "request-auto-1",
        "options": {
            "goal": "Advance the current world.",
            "prompt": "private prompt must not be persisted",
            "source_text": "private source must not be persisted",
            "credential_ref": "secret-ref",
        },
    }


class RecordingEventWriter:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self._identities: set[tuple[str, int | None]] = set()

    def write_event(
        self,
        *,
        tenant_id: str,
        project_id: str | None,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        identity = (event_type, payload.get("source_step_index"))
        if identity in self._identities:
            return
        self._identities.add(identity)
        self.events.append(
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "run_id": run_id,
                "event_type": event_type,
                "payload": payload,
            }
        )


class RecordingStatusWriter:
    def __init__(self) -> None:
        self.completed: list[dict[str, Any]] = []
        self.failed: list[dict[str, Any]] = []

    def mark_completed(self, *, context: AgentContext, result: dict[str, Any]) -> None:
        if not self.completed:
            self.completed.append({"context": context, "result": result})

    def mark_failed(
        self,
        *,
        context: AgentContext,
        session_id: str,
        code: str,
        message: str,
    ) -> None:
        if not self.failed:
            self.failed.append(
                {
                    "context": context,
                    "session_id": session_id,
                    "code": code,
                    "message": message,
                }
            )


class SequencedStepRunner:
    def __init__(self, *, fail_at: int | None = None) -> None:
        self.fail_at = fail_at
        self.calls: list[dict[str, Any]] = []

    def run_step(
        self,
        *,
        context: AgentContext,
        session_id: str,
        mode: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "context": context,
                "session_id": session_id,
                "mode": mode,
                "options": options,
            }
        )
        source_step_index = options["source_step_index"]
        if source_step_index == self.fail_at:
            return {
                "status": "failed",
                "error": {
                    "code": "LLM_PROVIDER_ERROR",
                    "message": "worldline provider call failed",
                },
            }
        return {
            "status": "completed",
            "model_id": "model-worldline",
            "candidate_event_count": source_step_index,
            "step": 10 + source_step_index,
        }


class LeakingFailureStepRunner:
    def run_step(
        self,
        *,
        context: AgentContext,
        session_id: str,
        mode: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "status": "failed",
            "error": {
                "code": "PRIVATE_PROVIDER_FAILURE",
                "message": "prompt=private api_key=sk-secret credential_ref=hidden",
            },
        }


def test_auto_evolution_runs_every_step_then_persists_one_terminal_completion() -> None:
    runner = SequencedStepRunner()
    event_writer = RecordingEventWriter()
    status_writer = RecordingStatusWriter()

    result = run_worldline_auto_evolution_workflow_locally(
        _payload(max_steps=3),
        step_runner=runner,
        workflow_event_writer=event_writer,
        workflow_status_writer=status_writer,
    )

    assert result["status"] == "completed"
    assert result["workflow_type"] == WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE
    assert result["completed_steps"] == 3
    assert result["candidate_event_count"] == 6
    assert result["last_step"] == 13
    assert [call["options"]["source_step_index"] for call in runner.calls] == [1, 2, 3]
    assert all(call["context"].run_id == RUN_ID for call in runner.calls)
    assert all(call["mode"] == "auto_evolution" for call in runner.calls)
    assert [event["event_type"] for event in event_writer.events] == [
        "worldline.auto_evolution.step.completed",
        "worldline.auto_evolution.step.completed",
        "worldline.auto_evolution.step.completed",
        "worldline.auto_evolution.completed",
    ]
    assert status_writer.failed == []
    assert len(status_writer.completed) == 1
    assert status_writer.completed[0]["result"]["completed_steps"] == 3
    encoded = json.dumps([result, event_writer.events, status_writer.completed, runner.calls], default=str)
    for forbidden in ["private prompt", "private source", "secret-ref", "prompt", "source_text", "credential_ref"]:
        assert forbidden not in encoded
    assert "canon" not in encoded


def test_auto_evolution_stops_at_first_failed_step_and_marks_terminal_failed() -> None:
    runner = SequencedStepRunner(fail_at=2)
    event_writer = RecordingEventWriter()
    status_writer = RecordingStatusWriter()

    result = run_worldline_auto_evolution_workflow_locally(
        _payload(max_steps=4),
        step_runner=runner,
        workflow_event_writer=event_writer,
        workflow_status_writer=status_writer,
    )

    assert result["status"] == "failed"
    assert result["source_step_index"] == 2
    assert result["error"] == {
        "code": "LLM_PROVIDER_ERROR",
        "message": "worldline provider call failed",
    }
    assert [call["options"]["source_step_index"] for call in runner.calls] == [1, 2]
    assert [event["event_type"] for event in event_writer.events] == [
        "worldline.auto_evolution.step.completed",
        "worldline.auto_evolution.step.failed",
    ]
    assert status_writer.completed == []
    assert len(status_writer.failed) == 1
    assert status_writer.failed[0]["code"] == "LLM_PROVIDER_ERROR"


def test_auto_evolution_redacts_untrusted_runner_failure_before_events_and_status() -> None:
    event_writer = RecordingEventWriter()
    status_writer = RecordingStatusWriter()

    result = run_worldline_auto_evolution_workflow_locally(
        _payload(max_steps=2),
        step_runner=LeakingFailureStepRunner(),
        workflow_event_writer=event_writer,
        workflow_status_writer=status_writer,
    )

    assert result["error"] == {
        "code": "WORLDLINE_AUTO_EVOLUTION_STEP_FAILED",
        "message": "worldline auto-evolution step failed",
    }
    encoded = json.dumps([result, event_writer.events, status_writer.failed], default=str)
    for forbidden in ["prompt=private", "api_key", "sk-secret", "credential_ref", "hidden"]:
        assert forbidden not in encoded


class RecordingResolver:
    def __init__(self) -> None:
        self.calls = 0

    def resolve_module_binding(self, *, context: AgentContext, module_key: str) -> ModuleBindingResolution:
        self.calls += 1
        return ModuleBindingResolution(
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            module_key=module_key,
            channel_id="channel-worldline",
            model_id="model-worldline",
            provider="openai-compatible",
            base_url="https://llm.example/v1",
            credential_ref="channel-worldline",
            supports_json=True,
            settings={},
        )


class RecordingCredentialProvider:
    def __init__(self) -> None:
        self.calls = 0

    def resolve_api_key(self, *, context: AgentContext, credential_ref: str) -> str:
        self.calls += 1
        return "sk-private"


class RecordingChatClient:
    def __init__(self) -> None:
        self.calls = 0

    def complete_json(
        self,
        *,
        context: AgentContext,
        resolution: ModuleBindingResolution,
        api_key: str,
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        self.calls += 1
        return {
            "candidate_events": [
                {
                    "title": f"Candidate {self.calls}",
                    "summary": "A candidate simulation event.",
                    "kind": "director",
                }
            ]
        }


class ReplayCandidateWriter:
    def __init__(self) -> None:
        self.steps: dict[int, dict[str, Any]] = {}
        self.write_calls: list[dict[str, Any]] = []

    def read_candidate_events(
        self,
        *,
        context: AgentContext,
        session_id: str,
        source_run_id: str,
        source_step_index: int,
        workflow_type: str,
    ) -> dict[str, Any] | None:
        return self.steps.get(source_step_index)

    def write_candidate_events(
        self,
        *,
        context: AgentContext,
        session_id: str,
        source_run_id: str,
        model_id: str | None,
        mode: str,
        events: list[dict[str, Any]],
        source_step_index: int = 1,
        workflow_type: str = "worldline_step",
    ) -> dict[str, Any]:
        self.write_calls.append(
            {
                "source_run_id": source_run_id,
                "source_step_index": source_step_index,
                "workflow_type": workflow_type,
                "events": events,
            }
        )
        persisted = {
            "status": "completed",
            "candidate_event_count": len(events),
            "step": source_step_index + 20,
            "model_id": model_id,
            "source_step_index": source_step_index,
            "replayed": False,
        }
        self.steps[source_step_index] = persisted
        return persisted


def test_auto_evolution_replay_reuses_each_candidate_step_without_provider_or_duplicate_terminal() -> None:
    resolver = RecordingResolver()
    credentials = RecordingCredentialProvider()
    chat = RecordingChatClient()
    candidates = ReplayCandidateWriter()
    runner = LLMFacilityWorldlineStepRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat,
        candidate_event_writer=candidates,
    )
    events = RecordingEventWriter()
    statuses = RecordingStatusWriter()

    first = run_worldline_auto_evolution_workflow_locally(
        _payload(max_steps=3),
        step_runner=runner,
        workflow_event_writer=events,
        workflow_status_writer=statuses,
    )
    replay = run_worldline_auto_evolution_workflow_locally(
        _payload(max_steps=3),
        step_runner=runner,
        workflow_event_writer=events,
        workflow_status_writer=statuses,
    )

    assert first["status"] == replay["status"] == "completed"
    assert resolver.calls == credentials.calls == chat.calls == 3
    assert len(candidates.write_calls) == 3
    assert [call["source_step_index"] for call in candidates.write_calls] == [1, 2, 3]
    assert {call["source_run_id"] for call in candidates.write_calls} == {RUN_ID}
    assert len(events.events) == 4
    assert len(statuses.completed) == 1


class SQLRecordingCursor:
    def __init__(self, *, workflow_status: str = "queued") -> None:
        self.workflow_status = workflow_status
        self.executions: list[tuple[str, tuple[Any, ...]]] = []
        self.last_sql = ""

    def __enter__(self) -> "SQLRecordingCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self.last_sql = sql
        self.executions.append((sql, params))

    def fetchone(self) -> dict[str, Any] | None:
        if "SELECT status" in self.last_sql and "FROM worldline_sessions" in self.last_sql:
            return {"status": "running"}
        if "COUNT(*)::int AS event_count" in self.last_sql:
            return {"event_count": 0, "min_step": 0, "max_step": 0, "model_id": None}
        if "FROM workflow_runs AS workflow_run" in self.last_sql and "queued_event" in self.last_sql:
            if "SELECT workflow_run.status AS workflow_status" in self.last_sql:
                return {
                    "workflow_status": self.workflow_status,
                    "max_steps": 3,
                    "session_status": "running",
                }
            return {"active": 1}
        if "AS next_step" in self.last_sql:
            return {"next_step": 7}
        if "INSERT INTO worldline_events" in self.last_sql:
            return {"event_id": "event-1"}
        if "COUNT(DISTINCT" in self.last_sql:
            return {"completed_steps": 3, "min_step_index": 1, "max_step_index": 3}
        if "UPDATE workflow_runs" in self.last_sql:
            return {"run_id": RUN_ID}
        if "UPDATE worldline_sessions" in self.last_sql:
            return {"session_id": SESSION_ID}
        if "parent_count" in self.last_sql and "event_count" in self.last_sql:
            return {"parent_count": 1, "event_count": 1}
        return {"ok": 1}


class SQLRecordingConnection:
    def __init__(self, *, workflow_status: str = "queued") -> None:
        self.cursor_obj = SQLRecordingCursor(workflow_status=workflow_status)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self) -> SQLRecordingCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def test_candidate_writer_uses_same_auto_run_with_source_step_identity_and_candidate_lifecycle() -> None:
    connection = SQLRecordingConnection()
    writer = PostgresWorldlineCandidateEventWriter(connect=lambda: connection)

    result = writer.write_candidate_events(
        context=_context(),
        session_id=SESSION_ID,
        source_run_id=RUN_ID,
        model_id="model-worldline",
        mode="auto_evolution",
        events=[{"title": "Step two", "summary": "Candidate only.", "kind": "director"}],
        source_step_index=2,
        workflow_type=WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE,
    )

    assert result == {
        "status": "completed",
        "candidate_event_count": 1,
        "step": 7,
        "source_step_index": 2,
        "replayed": False,
    }
    count_query = next(item for item in connection.cursor_obj.executions if "COUNT(*)::int AS event_count" in item[0])
    assert count_query[1][-2:] == (WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE, "2")
    active_query = next(item for item in connection.cursor_obj.executions if "FROM workflow_runs AS workflow_run" in item[0])
    assert WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE in active_query[1]
    insert = next(item for item in connection.cursor_obj.executions if "INSERT INTO worldline_events" in item[0])
    state_changes = json.loads(insert[1][6])
    assert insert[1][7] == RUN_ID
    assert state_changes["source_step_index"] == 2
    assert state_changes["source_workflow_type"] == WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE
    assert "'candidate', 'simulation'" in insert[0]
    assert "canon" not in json.dumps(insert[1], default=str)


def test_postgres_auto_events_are_idempotent_by_event_type_and_source_step() -> None:
    connection = SQLRecordingConnection()
    writer = PostgresWorkflowEventWriter(connect=lambda: connection)

    writer.write_event(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        event_type="worldline.auto_evolution.step.completed",
        payload={"source_step_index": 2, "status": "completed", "prompt": "hidden"},
    )

    sql, params = next(item for item in connection.cursor_obj.executions if "existing_event AS MATERIALIZED" in item[0])
    assert "workflow_type = 'worldline_auto_evolution'" in sql
    assert "WHERE NOT EXISTS (SELECT 1 FROM existing_event)" in sql
    assert params[4:6] == ("2", "2")
    assert "hidden" not in json.dumps(params, default=str)
    assert connection.commits == 1


def test_postgres_auto_terminal_completion_validates_all_candidate_steps_and_is_replay_idempotent() -> None:
    active = SQLRecordingConnection(workflow_status="queued")
    completed = SQLRecordingConnection(workflow_status="completed")
    connections = iter([active, completed])
    writer = PostgresWorkflowRunStatusWriter(connect=lambda: next(connections))
    terminal_result = {
        "session_id": SESSION_ID,
        "mode": "auto_evolution",
        "world_scope": WORLDLINE_AUTO_EVOLUTION_WORLD_SCOPE,
        "completed_steps": 3,
        "max_steps": 3,
        "candidate_event_count": 3,
        "last_step": 9,
    }

    writer.mark_completed(context=_context(), result=terminal_result)
    writer.mark_completed(context=_context(), result=terminal_result)

    active_sql = "\n".join(sql for sql, _ in active.cursor_obj.executions)
    replay_sql = "\n".join(sql for sql, _ in completed.cursor_obj.executions)
    assert "COUNT(DISTINCT (state_changes_jsonb->>'source_step_index')::int)" in active_sql
    assert "source_workflow_type' = 'worldline_auto_evolution'" in active_sql
    assert "UPDATE workflow_runs" in active_sql
    assert "UPDATE worldline_sessions" in active_sql
    assert "UPDATE workflow_runs" not in replay_sql
    assert active.commits == completed.commits == 1


def test_worldline_auto_runtime_is_registered_on_worldline_queue() -> None:
    components = worker_components_for_task_queue(WORLDLINE_TASK_QUEUE)
    assert WorldlineAutoEvolutionWorkflow in components["workflows"]
    assert worldline_auto_evolution_step_activity in components["activities"]
    assert worldline_auto_evolution_finalize_activity in components["activities"]
    spec = worker_spec()
    assert "WorldlineAutoEvolutionWorkflow" in spec["workflows"]
    assert "worldline_auto_evolution_step_activity" in spec["activities"]
    assert "worldline_auto_evolution_finalize_activity" in spec["activities"]
