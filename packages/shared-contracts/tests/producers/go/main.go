package main

import (
	"encoding/json"
	"os"
)

type fixtureSet struct {
	WriterWorkflowInput map[string]any `json:"writer_workflow_input"`
	WriterToolRequest   map[string]any `json:"writer_tool_request"`
	WriterRuntimeEvent  map[string]any `json:"writer_runtime_event"`
	WriterPublicEvent   map[string]any `json:"writer_public_event"`
}

func main() {
	fixtures := fixtureSet{
		WriterWorkflowInput: map[string]any{
			"tenant_id": "tenant-go", "project_id": "project-go", "run_id": "run-go",
			"trace_id": "trace-go", "requested_by": "user-go", "request_id": "request-go",
			"workflow_type": "writer_run", "mode": "draft", "instruction": "Write the next scene.",
			"selected_asset_ids": []string{"asset-go"}, "graph_node_ids": []string{"node-go"},
			"worldline_path_ids": []string{"path-go"},
			"options":            map[string]any{"module_key": "writer_composer", "target_words": 900},
		},
		WriterRuntimeEvent: map[string]any{
			"tenant_id": "tenant-go", "project_id": "project-go", "run_id": "run-go",
			"workflow_type": "writer_run", "event_type": "writer.tool.completed",
			"payload":         map[string]any{"tool_name": "query_assets", "is_error": false},
			"idempotency_key": "tool:go:completed",
		},
		WriterToolRequest: map[string]any{
			"tenant_id": "tenant-go", "project_id": "project-go", "run_id": "run-go",
			"selected_asset_ids": []string{"asset-go"}, "graph_node_ids": []string{"node-go"},
			"worldline_path_ids": []string{"path-go"}, "tool_name": "query_world_rules",
		},
		WriterPublicEvent: map[string]any{
			"event_id": "event-go", "run_id": "run-go", "project_id": "project-go", "sequence": 3,
			"event_type": "writer.tool.completed", "payload": map[string]any{"tool_name": "query_assets"},
			"created_at": "2026-07-11T00:00:00Z",
		},
	}
	if err := json.NewEncoder(os.Stdout).Encode(fixtures); err != nil {
		panic(err)
	}
}
