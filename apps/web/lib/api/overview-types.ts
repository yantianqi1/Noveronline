/**
 * Wire types for the Overview workbench, mirroring the Go control plane.
 * Field names are snake_case exactly as they appear on the wire. Sources:
 *  - Overview:    apps/api/internal/projectoverview/projectoverview.go
 *  - Readiness:   apps/api/internal/projectreadiness/projectreadiness.go
 *  - SourceFile:  apps/api/internal/sourcefiles/source_files.go (Record)
 *  - Seed run:    apps/api/internal/httpapi/server.go (workflowRunResponse)
 *  - Seed event:  apps/api/internal/workflows/workflow_events.go (WorkflowEvent)
 */

export type ProjectOverview = {
  project_id: string;
  status: string;
  source_file_count: number;
  seed_run_count: number;
  active_workflow_run_id: string;
  active_workflow_type: string;
  active_workflow_status: string;
  readiness_snapshot_id: string;
  readiness_run_id: string;
  ready_asset_count: number;
  ready_entity_count: number;
  ready_relationship_count: number;
  ready_world_rule_count: number;
  asset_count: number;
  graph_node_count: number;
  graph_edge_count: number;
  worldline_session_count: number;
  worldline_event_count: number;
  character_interaction_count: number;
  writer_run_count: number;
  latest_failed_workflow_run_id: string;
  latest_failed_workflow_type: string;
  latest_failed_workflow_error_code: string;
  latest_failed_workflow_updated_at: string;
  updated_at: string;
};

export type ReadinessSnapshot = {
  project_readiness_snapshot_id: string;
  project_id: string;
  run_id: string;
  ready_asset_count: number;
  ready_entity_count: number;
  ready_relationship_count: number;
  ready_world_rule_count: number;
  created_at: string;
  updated_at: string;
};

export type SourceFile = {
  file_id: string;
  upload_id: string;
  project_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  purpose: string;
  parse_status: string;
  created_at: string;
};

export type SeedRun = {
  run_id: string;
  workflow_type: string;
  project_id: string;
  status: string;
  progress: number;
  message: string;
  error_code: string;
  error_message: string;
  created_at: string;
  updated_at: string;
};

export type WorkflowEvent = {
  event_id: string;
  run_id: string;
  project_id: string;
  sequence: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

/** Generic list envelope the Go API uses for collection routes. */
export type ListResponse<T> = { items: T[] };
