import type { ToolExecutionMode } from "@earendil-works/pi-agent-core";

export interface WriterRunInput {
  tenant_id: string;
  project_id: string;
  run_id: string;
  trace_id: string;
  requested_by: string;
  mode: "draft" | "continue" | "outline" | "revise";
  chapter_id?: string;
  scene_id?: string;
  instruction: string;
  selected_asset_ids: string[];
  graph_node_ids: string[];
  worldline_path_ids: string[];
  /**
   * Worldline simulation sessions whose adopted canon events (status='canon')
   * form the ordered plot timeline the writer should follow. Fetched
   * deterministically at run start (ordered by step), not left to tool luck.
   */
  worldline_session_ids: string[];
  options: {
    module_key: "writer_composer" | "writer_orchestrator";
    thinking_level?: "off" | "minimal" | "low" | "medium" | "high" | "xhigh";
    tool_execution?: ToolExecutionMode;
    target_words?: number;
    review_after_write?: boolean;
    revise?: {
      block_id: string;
      selection_text: string;
      selection_start?: number;
      selection_end?: number;
      expected_version?: number;
      action?: "rewrite" | "expand" | "condense" | "polish" | "correct" | "custom";
    };
    thread_id?: string;
    llm_resolution?: {
      module_key: string;
      channel_id: string;
      model_id: string;
      provider: string;
      base_url: string;
      credential_ref: string;
      supports_tools: boolean;
      supports_json: boolean;
      settings: Record<string, unknown>;
    };
  };
}

export interface RuntimeContext {
  tenant_id: string;
  project_id: string;
  run_id: string;
  trace_id: string;
  requested_by: string;
  permissions: {
    tools: string[];
    can_write_draft: boolean;
  };
}

export function runtimeContextFromInput(input: WriterRunInput): RuntimeContext {
  return {
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    run_id: input.run_id,
    trace_id: input.trace_id,
    requested_by: input.requested_by,
    permissions: {
      tools: [
        "query_project_context",
        "query_chapter_scene",
        "query_assets",
        "search_assets",
        "search_manuscript",
        "fuse_recall",
        "query_world_rules",
        "query_character_profile",
        "query_graph_neighbors",
        "query_asset_relationships",
        "query_worldline_paths",
        "query_manuscript_context",
        "save_draft_revision"
      ],
      can_write_draft: true
    }
  };
}
