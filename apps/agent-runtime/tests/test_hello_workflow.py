from __future__ import annotations

from mirofish_agents.common.context import AgentContext
from mirofish_agents.temporal.hello import (
    HELLO_AGENT_TASK_QUEUE,
    hello_agent_activity,
    run_hello_workflow_locally,
    worker_spec,
)


def _context() -> AgentContext:
    return AgentContext(
        tenant_id="tenant-1",
        project_id="project-1",
        run_id="run-1",
        workflow_type="hello_agent",
        actor_user_id="user-1",
        trace_id="trace-1",
        permissions={"hello_agent": ["run"]},
    )


def test_hello_activity_requires_explicit_permission() -> None:
    context = _context().model_copy(update={"permissions": {}})

    result = hello_agent_activity(context.model_dump())

    assert result["status"] == "failed"
    assert result["error"]["code"] == "FORBIDDEN"
    assert result["tenant_id"] == "tenant-1"
    assert result["run_id"] == "run-1"


def test_local_hello_workflow_completes_with_context_and_trace_event() -> None:
    result = run_hello_workflow_locally(_context().model_dump())

    assert result["status"] == "completed"
    assert result["tenant_id"] == "tenant-1"
    assert result["project_id"] == "project-1"
    assert result["run_id"] == "run-1"
    assert result["trace_events"] == [
        {
            "event_type": "activity_completed",
            "payload": {"activity": "hello_agent_activity"},
        }
    ]


def test_worker_spec_registers_temporal_workflow_and_activity() -> None:
    spec = worker_spec()

    assert spec["task_queue"] == HELLO_AGENT_TASK_QUEUE
    assert "HelloAgentWorkflow" in spec["workflows"]
    assert "hello_agent_activity" in spec["activities"]
