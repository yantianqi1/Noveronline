import json


print(json.dumps({
    "writer_workflow_input": {
        "tenant_id": "tenant-python",
        "project_id": "project-python",
        "run_id": "run-python",
        "trace_id": "trace-python",
        "requested_by": "user-python",
        "workflow_type": "writer_run",
        "mode": "outline",
        "instruction": "Outline the next chapter.",
        "options": {
            "module_key": "writer_orchestrator",
            "thinking_level": "medium",
            "review_after_write": True,
        },
    },
    "writer_runtime_event": {
        "tenant_id": "tenant-python",
        "project_id": "project-python",
        "run_id": "run-python",
        "workflow_type": "writer_run",
        "event_type": "writer.run.completed",
        "payload": {"status": "completed"},
        "idempotency_key": "run:python:completed",
    },
    "writer_tool_request": {
        "tenant_id": "tenant-python",
        "project_id": "project-python",
        "run_id": "run-python",
        "selected_asset_ids": [],
        "graph_node_ids": [],
        "worldline_path_ids": [],
        "tool_name": "query_character_profile",
    },
    "writer_public_event": {
        "event_id": "event-python",
        "run_id": "run-python",
        "project_id": "project-python",
        "sequence": 4,
        "event_type": "writer.run.completed",
        "payload": {"status": "completed"},
        "created_at": "2026-07-11T00:00:01Z",
    },
}))
