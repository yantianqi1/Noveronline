from __future__ import annotations

import pytest
from pydantic import ValidationError

from mirofish_agents.common.context import AgentContext


def test_agent_context_requires_tenant_run_workflow_and_trace() -> None:
    with pytest.raises(ValidationError):
        AgentContext(project_id="project-1")  # type: ignore[call-arg]


def test_agent_context_rejects_blank_required_ids() -> None:
    with pytest.raises(ValidationError):
        AgentContext(
            tenant_id=" ",
            project_id="project-1",
            run_id="run-1",
            workflow_type="hello_agent",
            trace_id="trace-1",
        )


def test_agent_context_preserves_runtime_scope_and_permissions() -> None:
    context = AgentContext(
        tenant_id="tenant-1",
        project_id="project-1",
        run_id="run-1",
        workflow_type="hello_agent",
        actor_user_id="user-1",
        module_key="maintenance",
        trace_id="trace-1",
        permissions={"hello": ["run"]},
    )

    assert context.tenant_id == "tenant-1"
    assert context.project_id == "project-1"
    assert context.run_id == "run-1"
    assert context.permissions == {"hello": ["run"]}
    assert context.to_trace_payload() == {
        "tenant_id": "tenant-1",
        "project_id": "project-1",
        "run_id": "run-1",
        "workflow_type": "hello_agent",
        "actor_user_id": "user-1",
        "trace_id": "trace-1",
        "module_key": "maintenance",
    }
