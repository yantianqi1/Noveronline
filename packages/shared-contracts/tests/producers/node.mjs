process.stdout.write(JSON.stringify({
  writer_workflow_input: {
    tenant_id: "tenant-node",
    project_id: "project-node",
    run_id: "run-node",
    trace_id: "trace-node",
    requested_by: "user-node",
    workflow_type: "writer_run",
    mode: "continue",
    chapter_id: "chapter-node",
    scene_id: "scene-node",
    instruction: "Continue the current scene.",
    worldline_session_ids: ["session-node"],
    options: { module_key: "writer_composer", review_after_write: false }
  },
  writer_runtime_event: {
    tenant_id: "tenant-node",
    project_id: "project-node",
    run_id: "run-node",
    workflow_type: "writer_run",
    event_type: "writer.draft.saved",
    payload: { draft_id: "draft-node", status: "candidate" },
    idempotency_key: "draft:node:saved"
  },
  writer_tool_request: {
    tenant_id: "tenant-node",
    project_id: "project-node",
    run_id: "run-node",
    chapter_id: "chapter-node",
    scene_id: "scene-node",
    selected_asset_ids: ["asset-node"],
    graph_node_ids: ["node-node"],
    worldline_path_ids: ["path-node"],
    worldline_session_ids: ["session-node"],
    tool_name: "query_graph_neighbors"
  },
  writer_public_event: {
    event_id: "event-node",
    run_id: "run-node",
    project_id: "project-node",
    sequence: 5,
    event_type: "writer.draft.saved",
    payload: { draft_id: "draft-node", status: "candidate" },
    created_at: "2026-07-11T00:00:02Z"
  }
}));
