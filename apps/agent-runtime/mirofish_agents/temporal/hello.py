from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import activity, workflow

from mirofish_agents.common.context import AgentContext


HELLO_AGENT_TASK_QUEUE = "maintenance"


@activity.defn
def hello_agent_activity(context_payload: dict[str, Any]) -> dict[str, Any]:
    context = AgentContext.model_validate(context_payload)
    base = {
        "tenant_id": context.tenant_id,
        "project_id": context.project_id,
        "run_id": context.run_id,
        "workflow_type": context.workflow_type,
    }
    if not context.has_permission("hello_agent", "run"):
        return {
            **base,
            "status": "failed",
            "error": {
                "code": "FORBIDDEN",
                "message": "hello_agent run permission is required",
            },
        }
    return {
        **base,
        "status": "completed",
        "message": "Python agent runtime hello activity completed",
    }


@workflow.defn
class HelloAgentWorkflow:
    @workflow.run
    async def run(self, context_payload: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            hello_agent_activity,
            context_payload,
            start_to_close_timeout=timedelta(seconds=30),
        )


def run_hello_workflow_locally(context_payload: dict[str, Any]) -> dict[str, Any]:
    result = hello_agent_activity(context_payload)
    if result["status"] == "completed":
        result = {
            **result,
            "trace_events": [
                {
                    "event_type": "activity_completed",
                    "payload": {"activity": "hello_agent_activity"},
                }
            ],
        }
    return result


def worker_spec() -> dict[str, list[str] | str]:
    return {
        "task_queue": HELLO_AGENT_TASK_QUEUE,
        "workflows": [HelloAgentWorkflow.__name__],
        "activities": [hello_agent_activity.__name__],
    }
