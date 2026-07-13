export type WriterMode = "draft" | "continue" | "outline" | "revise";
export type WriterModuleKey = "writer_composer" | "writer_orchestrator";
export type WriterRuntimeEventType =
  | "writer.run.started"
  | "writer.token"
  | "writer.tool.started"
  | "writer.tool.completed"
  | "writer.draft.saved"
  | "writer.revision.proposed"
  | "writer.approval.required"
  | "writer.approval.resolved"
  | "writer.run.failed"
  | "writer.run.completed"
  | "writer.run.cancelled";
export type WriterPublicEventType = "workflow.queued" | WriterRuntimeEventType;
export type WriterToolName =
  | "query_project_context"
  | "query_chapter_scene"
  | "query_assets"
  | "query_world_rules"
  | "query_character_profile"
  | "query_graph_neighbors"
  | "query_worldline_paths"
  | "query_manuscript_context"
  | "save_draft_revision";

export interface WriterLLMResolution {
  module_key: string;
  channel_id: string;
  model_id: string;
  provider: string;
  base_url: string;
  credential_ref: string;
  supports_tools: boolean;
  supports_json: boolean;
  settings: Record<string, unknown>;
}

export interface WriterReviseOptions {
  block_id: string;
  selection_text: string;
  selection_start?: number;
  selection_end?: number;
  expected_version?: number;
  action?: "rewrite" | "expand" | "condense" | "polish" | "correct" | "custom";
}

export interface WriterWorkflowInput {
  tenant_id: string;
  project_id: string;
  run_id: string;
  trace_id: string;
  requested_by: string;
  request_id?: string;
  workflow_type?: "writer_run";
  mode: WriterMode;
  chapter_id?: string;
  scene_id?: string;
  instruction: string;
  selected_asset_ids?: string[];
  graph_node_ids?: string[];
  worldline_path_ids?: string[];
  options: {
    module_key: WriterModuleKey;
    thinking_level?: "off" | "minimal" | "low" | "medium" | "high" | "xhigh";
    target_words?: number;
    review_after_write?: boolean;
    llm_resolution?: WriterLLMResolution;
    revise?: WriterReviseOptions;
    [key: string]: unknown;
  };
}

export interface WriterRuntimeEvent {
  tenant_id: string;
  project_id: string;
  run_id: string;
  workflow_type: "writer_run";
  event_type: WriterRuntimeEventType;
  payload: Record<string, unknown>;
  idempotency_key?: string;
}

export interface WriterToolRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
  chapter_id?: string;
  scene_id?: string;
  selected_asset_ids: string[];
  graph_node_ids: string[];
  worldline_path_ids: string[];
  tool_name: WriterToolName;
}

export interface WriterPublicEvent {
  event_id: string;
  run_id: string;
  project_id: string;
  sequence: number;
  event_type: WriterPublicEventType;
  payload: Record<string, unknown>;
  created_at: string;
}

export const WRITER_WORKFLOW_TYPE: "writer_run";
export const PI_WRITER_WORKFLOW_NAME: "PiWriterRunWorkflow";
export const WRITER_TASK_QUEUE: "writer-streaming";
export const WRITER_MODES: readonly WriterMode[];
export const WRITER_MODULE_KEYS: readonly WriterModuleKey[];
export const WRITER_RUNTIME_EVENT_TYPES: readonly WriterRuntimeEventType[];
export const WRITER_PUBLIC_EVENT_TYPES: readonly WriterPublicEventType[];
export const WRITER_TOOL_NAMES: readonly WriterToolName[];
